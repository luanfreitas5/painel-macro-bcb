"""Erro de projeção do Focus para o IPCA mensal, por horizonte.

Definições
----------
- Horizonte ``h``: meses entre o mês da pesquisa e o mês de referência (``h = 0`` é o
  próprio mês).
- Para cada (mês de referência, horizonte) usa-se a **última** pesquisa do mês de
  pesquisa correspondente, de modo que cada previsão entra uma única vez.
- Erro = mediana projetada - IPCA realizado (pontos percentuais). Erro positivo
  significa superestimação.
"""

import polars as pl

from transformation.validation import validate_required_columns

Z_95 = 1.96


def compute_horizon_expr() -> pl.Expr:
    """Expressão do horizonte em meses entre ``survey_date`` e ``reference_month``.

    Examples
    --------
    >>> from datetime import date
    >>> df = pl.DataFrame(
    ...     {"survey_date": [date(2024, 1, 15)], "reference_month": [date(2024, 3, 1)]}
    ... )
    >>> df.select(compute_horizon_expr()).item()
    2
    """
    return (
        (pl.col("reference_month").dt.year() - pl.col("survey_date").dt.year()) * 12
        + pl.col("reference_month").dt.month()
        - pl.col("survey_date").dt.month()
    ).alias("horizon")


def select_forecasts(focus: pl.DataFrame, calculation_base: int, max_horizon: int) -> pl.DataFrame:
    """Seleciona uma previsão (mediana) por mês de referência e horizonte.

    Parameters
    ----------
    focus : pl.DataFrame
        Focus silver (``survey_date``, ``reference_month``, ``median``, ``calculation_base``).
    calculation_base : int
        Base de cálculo do Focus a usar (0 = últimos 30 dias; 1 = últimos 15 dias).
    max_horizon : int
        Maior horizonte (em meses) mantido.

    Returns
    -------
    pl.DataFrame
        Colunas ``reference_month``, ``horizon``, ``survey_date`` e ``forecast``.

    Raises
    ------
    DataContractError
        Se faltarem colunas obrigatórias.
    """
    validate_required_columns(
        focus, ["survey_date", "reference_month", "median", "calculation_base"], "focus"
    )
    return (
        focus.filter(pl.col("calculation_base") == calculation_base)
        .with_columns(compute_horizon_expr())
        .filter(pl.col("horizon").is_between(0, max_horizon))
        .sort("survey_date")
        .group_by(["reference_month", "horizon"], maintain_order=True)
        .agg(pl.col("survey_date").last(), pl.col("median").last().alias("forecast"))
        .sort(["reference_month", "horizon"])
    )


def compute_forecast_errors(forecasts: pl.DataFrame, realized: pl.DataFrame) -> pl.DataFrame:
    """Compara as previsões com o IPCA realizado.

    Parameters
    ----------
    forecasts : pl.DataFrame
        Saída de :func:`select_forecasts`.
    realized : pl.DataFrame
        Colunas ``month`` (primeiro dia do mês) e ``ipca_mom`` (IPCA realizado, %).

    Returns
    -------
    pl.DataFrame
        Colunas ``reference_month``, ``horizon``, ``survey_date``, ``forecast``,
        ``realized``, ``forecast_error`` (previsto - realizado) e ``abs_error``.
        Meses sem IPCA realizado ficam de fora.
    """
    realized_months = realized.select(
        pl.col("month").alias("reference_month"), pl.col("ipca_mom").alias("realized")
    ).drop_nulls()
    return (
        forecasts.join(realized_months, on="reference_month", how="inner")
        .with_columns((pl.col("forecast") - pl.col("realized")).alias("forecast_error"))
        .with_columns(pl.col("forecast_error").abs().alias("abs_error"))
        .sort(["reference_month", "horizon"])
    )


def summarize_errors(errors: pl.DataFrame) -> pl.DataFrame:
    """Resume o erro por horizonte: viés, MAE e RMSE, com IC de 95%.

    O IC é a aproximação normal (``1,96 * desvio / sqrt(n)``) e retorna a meia-largura.
    Como os erros de meses vizinhos são autocorrelacionados, o IC tende a ser otimista.

    Parameters
    ----------
    errors : pl.DataFrame
        Saída de :func:`compute_forecast_errors`.

    Returns
    -------
    pl.DataFrame
        Por horizonte: ``n_obs``, ``bias_pp``, ``bias_ci95_pp``, ``mae_pp``,
        ``mae_ci95_pp`` e ``rmse_pp`` (todos em pontos percentuais).

    Raises
    ------
    DataContractError
        Se faltarem colunas obrigatórias.
    """
    validate_required_columns(errors, ["horizon", "forecast_error", "abs_error"], "erros do Focus")
    return (
        errors.group_by("horizon")
        .agg(
            pl.len().alias("n_obs"),
            pl.col("forecast_error").mean().alias("bias_pp"),
            (Z_95 * pl.col("forecast_error").std() / pl.len().sqrt()).alias("bias_ci95_pp"),
            pl.col("abs_error").mean().alias("mae_pp"),
            (Z_95 * pl.col("abs_error").std() / pl.len().sqrt()).alias("mae_ci95_pp"),
            (pl.col("forecast_error") ** 2).mean().sqrt().alias("rmse_pp"),
        )
        .sort("horizon")
    )
