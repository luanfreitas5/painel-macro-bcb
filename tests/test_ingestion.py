"""Testes da ingestão: janelas de data, retry, cache idempotente e coletores."""

import json
from datetime import date

import pandas as pd
import polars as pl
import pytest
import requests

from constants.series import SELIC_TARGET
from exceptions.data import IngestionError
from ingestion.cache import (
    compute_sha256,
    find_latest_snapshot,
    is_snapshot_fresh,
    load_or_fetch_snapshot,
)
from ingestion.focus import fetch_focus_expectations
from ingestion.retry import call_with_retry
from ingestion.sgs import build_date_windows, fetch_sgs_series


@pytest.mark.smoke
def test_build_date_windows_splits_by_calendar_years():
    """Janelas contíguas de N anos-calendário, sem sobreposição."""
    windows = build_date_windows(date(2015, 3, 10), date(2026, 2, 1), 5)
    assert windows == [
        (date(2015, 3, 10), date(2019, 12, 31)),
        (date(2020, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2026, 2, 1)),
    ]


def test_build_date_windows_empty_when_start_after_end():
    """Período invertido gera lista vazia."""
    assert build_date_windows(date(2025, 1, 2), date(2025, 1, 1), 5) == []


def test_call_with_retry_recovers_from_transient_failure():
    """Falha transitória é repetida e o resultado final é devolvido."""
    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] < 2:
            raise requests.ConnectionError("rede")
        return 7

    assert call_with_retry(flaky, max_retries=3, wait_seconds=0) == 7
    assert calls["n"] == 2


def test_call_with_retry_raises_ingestion_error_when_exhausted():
    """Esgotadas as tentativas, levanta IngestionError."""

    def always_fails() -> int:
        raise requests.Timeout("timeout")

    with pytest.raises(IngestionError, match="2 tentativas"):
        call_with_retry(always_fails, max_retries=2, wait_seconds=0)


def _fake_sgs_getter(calls: list[tuple[str, str]]):
    def getter(codes, start, end):
        calls.append((start, end))
        index = pd.date_range(start, end, freq="MS")
        return pd.DataFrame({"selic_meta": [1.0] * len(index)}, index=index)

    return getter


def test_fetch_sgs_series_queries_by_window_and_dedupes():
    """Consulta uma vez por janela e devolve datas únicas e ordenadas."""
    calls: list[tuple[str, str]] = []
    frame = fetch_sgs_series(
        SELIC_TARGET, date(2019, 1, 1), date(2021, 6, 30), 1, getter=_fake_sgs_getter(calls)
    )

    assert len(calls) == 3  # 2019, 2020, 2021
    assert frame.columns == ["date", "value"]
    assert frame["date"].is_unique().all()
    assert frame["date"].is_sorted()
    assert frame.schema["date"] == pl.Date


def test_fetch_sgs_series_raises_when_empty():
    """Sem nenhum dado retornado, levanta IngestionError."""
    with pytest.raises(IngestionError):
        fetch_sgs_series(
            SELIC_TARGET,
            date(2020, 1, 1),
            date(2020, 12, 31),
            1,
            getter=lambda codes, start, end: pd.DataFrame(),
        )


def test_fetch_focus_expectations_concatenates_windows():
    """Concatena as janelas e remove linhas idênticas."""

    def window(indicator, start, end):
        return pd.DataFrame(
            {"Indicador": [indicator], "Data": [start.isoformat()], "Mediana": [0.4]}
        )

    frame = fetch_focus_expectations(
        "IPCA", date(2022, 1, 1), date(2023, 12, 31), 1, window_fetcher=window
    )
    assert frame.height == 2


def test_load_or_fetch_snapshot_is_idempotent(tmp_path):
    """Segunda execução no mesmo dia reutiliza o snapshot; force coleta de novo."""
    calls = {"n": 0}

    def fetch() -> pl.DataFrame:
        calls["n"] += 1
        return pl.DataFrame({"date": [date(2024, 1, 1)], "value": [1.0]})

    today = date(2026, 1, 10)
    first = load_or_fetch_snapshot("src_a", fetch, tmp_path, ttl_days=1, today=today)
    second = load_or_fetch_snapshot("src_a", fetch, tmp_path, ttl_days=1, today=today)

    assert first == second
    assert calls["n"] == 1

    load_or_fetch_snapshot("src_a", fetch, tmp_path, ttl_days=1, force=True, today=today)
    assert calls["n"] == 2


def test_snapshot_expires_after_ttl_and_manifest_has_hash(tmp_path):
    """Snapshot vencido é recoletado em novo arquivo datado; o manifesto guarda o SHA-256."""

    def fetch() -> pl.DataFrame:
        return pl.DataFrame({"date": [date(2024, 1, 1)], "value": [1.0]})

    old = load_or_fetch_snapshot("src_a", fetch, tmp_path, ttl_days=1, today=date(2026, 1, 10))
    new = load_or_fetch_snapshot("src_a", fetch, tmp_path, ttl_days=1, today=date(2026, 1, 11))

    assert old != new
    assert find_latest_snapshot(tmp_path, "src_a") == new
    assert is_snapshot_fresh(new, 1, date(2026, 1, 11))
    assert not is_snapshot_fresh(new, 1, date(2026, 1, 12))
    assert not is_snapshot_fresh(new, 0, date(2026, 1, 11))

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["snapshots"]["src_a/src_a_20260111.parquet"]
    assert entry["sha256"] == compute_sha256(new)
    assert entry["rows"] == 1


def test_empty_fetch_is_not_cached(tmp_path):
    """Coleta vazia levanta erro e não deixa snapshot para trás."""
    with pytest.raises(IngestionError):
        load_or_fetch_snapshot("src_a", pl.DataFrame, tmp_path, ttl_days=1)
    assert find_latest_snapshot(tmp_path, "src_a") is None
