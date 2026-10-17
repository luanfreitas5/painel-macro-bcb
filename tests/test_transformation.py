"""Testes da transformação (silver e gold)."""

import math
from datetime import date

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from exceptions.data import DataContractError
from transformation.gold import build_monthly_panel, compute_accumulated_12m
from transformation.silver import clean_focus_expectations, clean_sgs_series
from transformation.validation import (
    validate_focus_contract,
    validate_series_contract,
)


@pytest.mark.smoke
def test_monthly_panel_aligns_frequencies(selic_daily, usd_daily, ipca_monthly):
    """Séries diárias e mensal viram uma linha por mês, sem lacunas."""
    panel = build_monthly_panel(selic_daily, ipca_monthly, usd_daily)

    assert panel.height == 15
    assert panel["month"].is_unique().all()
    assert panel["month"][0] == date(2023, 1, 1)
    assert panel["month"][-1] == date(2024, 3, 1)


def test_monthly_panel_levels_and_variations(selic_daily, usd_daily, ipca_monthly):
    """Selic usa o último dia do mês; dólar usa a média; variações comparam meses vizinhos."""
    panel = build_monthly_panel(selic_daily, ipca_monthly, usd_daily).sort("month")
    by_month = {row["month"]: row for row in panel.iter_rows(named=True)}

    assert by_month[date(2023, 7, 1)]["selic_meta_eom"] == pytest.approx(13.75)
    assert by_month[date(2023, 8, 1)]["selic_meta_eom"] == pytest.approx(12.25)
    assert by_month[date(2023, 8, 1)]["selic_delta_pp"] == pytest.approx(-1.5)
    assert by_month[date(2024, 1, 1)]["usd_brl_mean"] == pytest.approx(5.5)
    assert by_month[date(2024, 1, 1)]["usd_brl_mom_pct"] == pytest.approx(10.0)
    assert by_month[date(2024, 1, 1)]["usd_brl_yoy_pct"] == pytest.approx(10.0)
    assert by_month[date(2023, 1, 1)]["selic_delta_pp"] is None


def test_ipca_12m_is_compounded_not_summed(selic_daily, usd_daily, ipca_monthly):
    """IPCA 12m compõe as variações (1,01^12 - 1) e é nulo antes de 12 meses de histórico."""
    panel = build_monthly_panel(selic_daily, ipca_monthly, usd_daily)

    assert panel["ipca_12m"][:11].is_null().all()
    assert panel["ipca_12m"][11] == pytest.approx((1.01**12 - 1) * 100)


def test_missing_ipca_month_keeps_calendar_and_nulls_following_windows(
    selic_daily, usd_daily, ipca_monthly
):
    """Um mês de IPCA ausente não desloca o calendário e invalida as 12 janelas seguintes."""
    gap = ipca_monthly.filter(pl.col("date") != date(2023, 6, 1))
    panel = build_monthly_panel(selic_daily, gap, usd_daily)

    assert panel.height == 15
    june = panel.filter(pl.col("month") == date(2023, 6, 1))
    assert june["ipca_mom"].is_null().all()
    assert panel["ipca_12m"].is_null().all()  # nenhuma janela de 12 meses sem a lacuna


@settings(deadline=None)
@given(
    values=st.lists(
        st.floats(min_value=-1.0, max_value=3.0, allow_nan=False), min_size=12, max_size=36
    )
)
def test_accumulated_12m_matches_naive_product(values):
    """Invariante: o acumulado em 12m é o produtório das 12 últimas variações."""
    result = pl.DataFrame({"x": values}).select(compute_accumulated_12m("x").alias("r"))["r"][-1]
    expected = (math.prod(1 + v / 100 for v in values[-12:]) - 1) * 100
    assert result == pytest.approx(expected, rel=1e-9, abs=1e-9)


def test_clean_sgs_series_drops_nulls_duplicates_and_sorts():
    """Remove nulos/NaN, mantém a última duplicata por data e ordena."""
    raw = pl.DataFrame(
        {
            "date": [date(2024, 1, 3), date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 4)],
            "value": [3.0, 1.0, 2.0, None],
        }
    )
    clean = clean_sgs_series(raw, "x")

    assert clean.columns == ["date", "x"]
    assert clean["date"].to_list() == [date(2024, 1, 2), date(2024, 1, 3)]
    assert clean["x"].to_list() == [2.0, 3.0]


def test_clean_sgs_series_requires_columns():
    """Falha com erro de contrato quando faltam colunas."""
    with pytest.raises(DataContractError):
        clean_sgs_series(pl.DataFrame({"date": [date(2024, 1, 1)]}), "x")


def _raw_focus() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Indicador": ["IPCA", "IPCA"],
            "Data": ["2024-01-08", "2024-01-08"],
            "DataReferencia": ["03/2024", "03/2024"],
            "Media": [0.40, 0.41],
            "Mediana": [0.38, 0.39],
            "DesvioPadrao": [0.1, 0.1],
            "numeroRespondentes": [100, 90],
            "baseCalculo": [0, 1],
        }
    )


def test_clean_focus_expectations_parses_dates_and_renames():
    """Converte data da pesquisa e mês de referência (MM/AAAA) e renomeia as colunas."""
    clean = clean_focus_expectations(_raw_focus())

    assert clean.columns == [
        "survey_date",
        "reference_month",
        "median",
        "mean",
        "std",
        "n_respondents",
        "calculation_base",
    ]
    assert clean["reference_month"].to_list() == [date(2024, 3, 1)] * 2
    assert clean["survey_date"][0] == date(2024, 1, 8)
    validate_focus_contract(clean)


def test_validate_series_contract_rejects_duplicates_and_out_of_range():
    """O contrato rejeita datas duplicadas, valores fora da faixa e séries vazias."""
    ok = pl.DataFrame({"date": [date(2024, 1, 1), date(2024, 1, 2)], "x": [1.0, 2.0]})
    validate_series_contract(ok, "x", 0, 10, "x")

    duplicated = pl.DataFrame({"date": [date(2024, 1, 1)] * 2, "x": [1.0, 2.0]})
    with pytest.raises(DataContractError, match="duplicadas"):
        validate_series_contract(duplicated, "x", 0, 10, "x")

    with pytest.raises(DataContractError, match="fora de"):
        validate_series_contract(ok, "x", 0, 1.5, "x")

    with pytest.raises(DataContractError, match="vazia"):
        validate_series_contract(ok.clear(), "x", 0, 10, "x")


def test_validate_focus_contract_rejects_duplicate_key():
    """A chave (pesquisa, mês de referência, base) deve ser única."""
    clean = clean_focus_expectations(_raw_focus())
    with pytest.raises(DataContractError, match="duplicada"):
        validate_focus_contract(pl.concat([clean, clean]))
