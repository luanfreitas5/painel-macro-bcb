"""Testes de integração do pipeline (sem rede): bronze sintético -> silver -> gold."""

from datetime import date

import polars as pl
import pytest

from config.paths import DataLayout
from config.settings import Settings, load_settings
from constants.datasets import (
    FOCUS_SOURCE,
    GOLD_FOCUS_ERRORS,
    GOLD_FOCUS_SUMMARY,
    GOLD_PANEL,
)
from constants.series import SGS_SERIES
from exceptions.configuration import ConfigurationError
from exceptions.data import IngestionError
from ingestion.cache import write_snapshot
from pipelines import workflow
from pipelines.workflow import (
    ensure_gold_tables,
    run_ingestion,
    run_pipeline,
    run_transformation,
)

SNAPSHOT_DATE = date(2026, 1, 10)


def _write_synthetic_bronze(layout: DataLayout) -> None:
    """Grava 2 anos de dados sintéticos (2023-2024) nas quatro fontes bronze."""
    days = pl.date_range(date(2023, 1, 1), date(2024, 12, 31), interval="1d", eager=True)
    months = pl.date_range(date(2023, 1, 1), date(2024, 12, 1), interval="1mo", eager=True)
    daily_values = {"selic_meta": 12.0, "usd_brl_sell": 5.0}
    for series in SGS_SERIES:
        if series.name == "ipca_mom":
            frame = pl.DataFrame({"date": months, "value": [0.4] * months.len()})
        else:
            frame = pl.DataFrame({"date": days, "value": [daily_values[series.name]] * days.len()})
        write_snapshot(frame, layout.bronze, series.source, SNAPSHOT_DATE)

    rows = []
    for reference in months:
        for horizon in range(4):
            month_index = reference.year * 12 + reference.month - 1 - horizon
            survey = date(month_index // 12, month_index % 12 + 1, 15)
            rows.append(
                {
                    "Indicador": "IPCA",
                    "Data": survey.isoformat(),
                    "DataReferencia": f"{reference.month:02d}/{reference.year}",
                    "Media": 0.5,
                    "Mediana": 0.5,
                    "DesvioPadrao": 0.1,
                    "numeroRespondentes": 50,
                    "baseCalculo": 0,
                }
            )
    write_snapshot(pl.DataFrame(rows), layout.bronze, FOCUS_SOURCE, SNAPSHOT_DATE)


@pytest.mark.integration
def test_run_transformation_builds_gold_with_expected_error(tmp_path):
    """Previsão constante de 0,5 contra IPCA de 0,4 gera viés de +0,1 p.p. em todo horizonte."""
    layout = DataLayout(tmp_path)
    _write_synthetic_bronze(layout)

    paths = run_transformation(Settings(), layout)

    assert set(paths) == {GOLD_PANEL, GOLD_FOCUS_ERRORS, GOLD_FOCUS_SUMMARY}
    summary = pl.read_parquet(paths[GOLD_FOCUS_SUMMARY])
    assert summary["horizon"].to_list() == [0, 1, 2, 3]
    assert summary["bias_pp"].to_list() == pytest.approx([0.1] * 4)
    assert summary["mae_pp"].to_list() == pytest.approx([0.1] * 4)
    panel = pl.read_parquet(paths[GOLD_PANEL])
    assert panel.height == 24
    assert (layout.silver / "focus_ipca_monthly.parquet").is_file()


@pytest.mark.integration
def test_ensure_gold_tables_reads_existing_without_pipeline(tmp_path):
    """Com as tabelas gold já existentes, o app não dispara coleta."""
    layout = DataLayout(tmp_path)
    _write_synthetic_bronze(layout)
    run_transformation(Settings(), layout)

    tables = ensure_gold_tables(Settings(), layout)

    assert set(tables) == {GOLD_PANEL, GOLD_FOCUS_ERRORS, GOLD_FOCUS_SUMMARY}


def test_run_transformation_without_bronze_raises(tmp_path):
    """Sem ingestão prévia, a transformação falha com mensagem clara."""
    with pytest.raises(IngestionError, match="Execute a ingestão"):
        run_transformation(Settings(), DataLayout(tmp_path))


def test_load_settings_validates_yaml(tmp_path):
    """YAML válido é carregado; chaves desconhecidas e valores inválidos falham na partida."""
    good = tmp_path / "good.yaml"
    good.write_text("focus:\n  max_horizon_months: 6\n", encoding="utf-8")
    assert load_settings(good).focus.max_horizon_months == 6

    unknown = tmp_path / "unknown.yaml"
    unknown.write_text("focus:\n  horizonte: 6\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(unknown)

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("ingestion:\n  window_years: 30\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(invalid)

    with pytest.raises(ConfigurationError):
        load_settings(tmp_path / "ausente.yaml")


def test_default_config_file_is_valid():
    """O configs/config.yaml versionado passa na validação."""
    assert load_settings().focus.indicator == "IPCA"


def _fake_frame() -> pl.DataFrame:
    """Frame mínimo devolvido pelos coletores falsos."""
    return pl.DataFrame({"date": [date(2024, 1, 1)], "value": [1.0]})


@pytest.mark.integration
def test_run_ingestion_fetches_all_sources_then_uses_cache(tmp_path, monkeypatch):
    """Coleta 3 séries SGS + Focus; a segunda execução usa o cache e ``force`` recoleta."""
    calls: list[str] = []

    def fake_sgs(series, *args):
        calls.append(series.source)
        return _fake_frame()

    def fake_focus(indicator, *args):
        calls.append(FOCUS_SOURCE)
        return _fake_frame()

    monkeypatch.setattr(workflow, "fetch_sgs_series", fake_sgs)
    monkeypatch.setattr(workflow, "fetch_focus_expectations", fake_focus)
    layout = DataLayout(tmp_path)
    today = date(2026, 1, 10)

    snapshots = run_ingestion(Settings(), layout, today=today)

    expected_sources = {s.source for s in SGS_SERIES} | {FOCUS_SOURCE}
    assert set(snapshots) == expected_sources
    assert all(path.is_file() for path in snapshots.values())
    assert sorted(calls) == sorted(expected_sources)

    run_ingestion(Settings(), layout, today=today)
    assert len(calls) == len(expected_sources)  # cache: nenhuma coleta nova

    run_ingestion(Settings(), layout, force=True, today=today)
    assert len(calls) == 2 * len(expected_sources)


def test_run_pipeline_runs_ingestion_before_transformation(tmp_path, monkeypatch):
    """O pipeline completo encadeia ingestão e transformação, repassando os argumentos."""
    order: list[tuple] = []
    sentinel = {GOLD_PANEL: tmp_path / "x.parquet"}

    def fake_ingestion(*args, **kwargs):
        order.append(("ingest", kwargs))
        return {}

    def fake_transformation(*args, **kwargs):
        order.append(("transform", kwargs))
        return sentinel

    monkeypatch.setattr(workflow, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(workflow, "run_transformation", fake_transformation)

    result = run_pipeline(Settings(), DataLayout(tmp_path), force=True, today=date(2026, 1, 10))

    assert [step for step, _ in order] == ["ingest", "transform"]
    assert order[0][1] == {"force": True, "today": date(2026, 1, 10)}
    assert result is sentinel


def test_ensure_gold_tables_runs_pipeline_when_missing(tmp_path, monkeypatch):
    """Sem tabelas gold, o pipeline é disparado e as tabelas são lidas em seguida."""

    def fake_pipeline(settings, layout):
        layout.ensure()
        for name in workflow.GOLD_FILES:
            _fake_frame().write_parquet(layout.gold / name)

    monkeypatch.setattr(workflow, "run_pipeline", fake_pipeline)

    tables = ensure_gold_tables(Settings(), DataLayout(tmp_path))

    assert set(tables) == set(workflow.GOLD_FILES)
    assert all(frame.height == 1 for frame in tables.values())
