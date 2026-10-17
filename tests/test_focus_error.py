"""Testes do cálculo de erro de projeção do Focus."""

import math
import statistics
from datetime import date

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from analysis.focus_error import (
    compute_forecast_errors,
    compute_horizon_expr,
    select_forecasts,
    summarize_errors,
)
from exceptions.data import DataContractError


def _focus(rows: list[tuple[date, date, float, int]]) -> pl.DataFrame:
    """Focus silver sintético: (pesquisa, mês de referência, mediana, base)."""
    return pl.DataFrame(
        rows,
        schema={
            "survey_date": pl.Date,
            "reference_month": pl.Date,
            "median": pl.Float64,
            "calculation_base": pl.Int64,
        },
        orient="row",
    )


@pytest.mark.smoke
def test_horizon_counts_months_between_survey_and_reference():
    """Horizonte 0 = próprio mês; atravessa a virada de ano."""
    surveys = pl.DataFrame(
        {
            "survey_date": [date(2024, 3, 20), date(2024, 1, 15), date(2023, 11, 2)],
            "reference_month": [date(2024, 3, 1), date(2024, 3, 1), date(2024, 2, 1)],
        }
    )
    assert surveys.select(compute_horizon_expr())["horizon"].to_list() == [0, 2, 3]


def test_select_forecasts_uses_last_survey_of_each_horizon_and_filters():
    """Mantém a última pesquisa por (mês, horizonte), a base pedida e h em [0, max]."""
    focus = _focus(
        [
            (date(2024, 1, 8), date(2024, 3, 1), 0.30, 0),
            (date(2024, 1, 22), date(2024, 3, 1), 0.35, 0),  # última de h=2
            (date(2024, 1, 22), date(2024, 3, 1), 0.99, 1),  # outra base de cálculo
            (date(2024, 4, 5), date(2024, 3, 1), 0.50, 0),  # h negativo (já passou)
            (date(2022, 1, 5), date(2024, 3, 1), 0.60, 0),  # h = 26, acima do máximo
        ]
    )
    result = select_forecasts(focus, calculation_base=0, max_horizon=12)

    assert result.height == 1
    row = result.row(0, named=True)
    assert row["horizon"] == 2
    assert row["survey_date"] == date(2024, 1, 22)
    assert row["forecast"] == pytest.approx(0.35)


def test_select_forecasts_requires_columns():
    """Sem as colunas do Focus silver, levanta erro de contrato."""
    with pytest.raises(DataContractError):
        select_forecasts(pl.DataFrame({"x": [1]}), 0, 12)


def test_forecast_error_sign_and_join_with_realized():
    """Erro = previsto - realizado; meses sem IPCA realizado ficam de fora."""
    forecasts = pl.DataFrame(
        {
            "reference_month": [date(2024, 3, 1), date(2024, 4, 1)],
            "horizon": [1, 1],
            "survey_date": [date(2024, 2, 20), date(2024, 3, 20)],
            "forecast": [0.50, 0.40],
        }
    )
    realized = pl.DataFrame({"month": [date(2024, 3, 1)], "ipca_mom": [0.40]})

    errors = compute_forecast_errors(forecasts, realized)

    assert errors.height == 1
    assert errors["forecast_error"][0] == pytest.approx(0.10)
    assert errors["abs_error"][0] == pytest.approx(0.10)


def test_summarize_errors_bias_mae_rmse_and_ci():
    """Viés, MAE, RMSE e IC calculados à mão para um horizonte."""
    errs = [0.1, -0.1, 0.3]
    errors = pl.DataFrame(
        {
            "horizon": [1, 1, 1],
            "forecast_error": errs,
            "abs_error": [abs(e) for e in errs],
        }
    )
    summary = summarize_errors(errors).row(0, named=True)

    assert summary["n_obs"] == 3
    assert summary["bias_pp"] == pytest.approx(0.1)
    assert summary["mae_pp"] == pytest.approx(0.5 / 3)
    assert summary["rmse_pp"] == pytest.approx(math.sqrt(0.11 / 3))
    std = statistics.stdev(errs)
    assert summary["bias_ci95_pp"] == pytest.approx(1.96 * std / math.sqrt(3))


def test_summarize_errors_single_observation_has_no_ci():
    """Com uma única observação o IC é indefinido (nulo), sem erro."""
    errors = pl.DataFrame({"horizon": [0], "forecast_error": [0.2], "abs_error": [0.2]})
    summary = summarize_errors(errors).row(0, named=True)

    assert summary["bias_pp"] == pytest.approx(0.2)
    assert summary["bias_ci95_pp"] is None


def test_summarize_errors_one_row_per_horizon_sorted():
    """Resultado ordenado por horizonte, uma linha por horizonte."""
    errors = pl.DataFrame(
        {
            "horizon": [2, 0, 2, 0],
            "forecast_error": [0.1, 0.2, 0.3, 0.4],
            "abs_error": [0.1, 0.2, 0.3, 0.4],
        }
    )
    assert summarize_errors(errors)["horizon"].to_list() == [0, 2]


@settings(deadline=None)
@given(
    errs=st.lists(st.floats(min_value=-5, max_value=5, allow_nan=False), min_size=2, max_size=50)
)
def test_mae_is_never_smaller_than_absolute_bias(errs):
    """Invariante (desigualdade triangular): MAE >= |viés| e RMSE >= MAE."""
    errors = pl.DataFrame(
        {
            "horizon": [0] * len(errs),
            "forecast_error": errs,
            "abs_error": [abs(e) for e in errs],
        }
    )
    summary = summarize_errors(errors).row(0, named=True)

    assert summary["mae_pp"] + 1e-9 >= abs(summary["bias_pp"])
    assert summary["rmse_pp"] + 1e-9 >= summary["mae_pp"]
