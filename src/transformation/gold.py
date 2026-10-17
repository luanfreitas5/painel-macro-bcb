"""Silver -> gold: painel mensal com frequências alinhadas, variações e IPCA em 12 meses."""

from datetime import date
from typing import cast

import polars as pl

from constants.series import IPCA_MONTHLY, SELIC_TARGET, USD_SELL


def compute_accumulated_12m(column: str = "ipca_mom", window: int = 12) -> pl.Expr:
    """Expressão do índice acumulado em ``window`` meses a partir de variações mensais (%).

    Compõe as variações: ``(prod(1 + x/100) - 1) * 100`` sobre janelas móveis. Janelas com
    qualquer mês ausente resultam em nulo.

    Parameters
    ----------
    column : str, optional
        Coluna com a variação mensal em %, by default ``"ipca_mom"``.
    window : int, optional
        Tamanho da janela em meses, by default 12.

    Returns
    -------
    pl.Expr
        Expressão com a variação acumulada em %.

    Examples
    --------
    >>> df = pl.DataFrame({"x": [1.0] * 12})
    >>> round(df.select(compute_accumulated_12m("x")).to_series()[-1], 4)
    12.6825
    """
    log_growth = (1 + pl.col(column) / 100).log()
    return (log_growth.rolling_sum(window_size=window, min_samples=window).exp() - 1) * 100


def build_monthly_panel(selic: pl.DataFrame, ipca: pl.DataFrame, usd: pl.DataFrame) -> pl.DataFrame:
    """Alinha as séries em frequência mensal e calcula variações.

    - Meta Selic (diária): valor do último dia do mês (``selic_meta_eom``).
    - Dólar (diário): média mensal (``usd_brl_mean``) e fechamento do mês (``usd_brl_eom``).
    - IPCA (mensal): já mensal (``ipca_mom``).

    Os meses são reindexados em uma sequência contínua para que ``diff``/``pct_change``
    sempre comparem meses adjacentes. O último mês pode estar incompleto.

    Parameters
    ----------
    selic, usd : pl.DataFrame
        Séries silver diárias (``date`` + ``selic_meta`` / ``usd_brl_sell``).
    ipca : pl.DataFrame
        Série silver mensal (``date`` + ``ipca_mom``).

    Returns
    -------
    pl.DataFrame
        Uma linha por mês (``month`` = primeiro dia) com níveis e variações:
        ``selic_delta_pp``, ``usd_brl_mom_pct``, ``usd_brl_yoy_pct`` e ``ipca_12m``.
    """
    selic_monthly = (
        selic.sort("date")
        .group_by_dynamic("date", every="1mo")
        .agg(pl.col(SELIC_TARGET.name).last().alias("selic_meta_eom"))
        .rename({"date": "month"})
    )
    usd_monthly = (
        usd.sort("date")
        .group_by_dynamic("date", every="1mo")
        .agg(
            pl.col(USD_SELL.name).mean().alias("usd_brl_mean"),
            pl.col(USD_SELL.name).last().alias("usd_brl_eom"),
        )
        .rename({"date": "month"})
    )
    ipca_monthly = ipca.select(
        pl.col("date").dt.truncate("1mo").alias("month"), pl.col(IPCA_MONTHLY.name)
    ).unique(subset="month", keep="last")

    frames = (selic_monthly, usd_monthly, ipca_monthly)
    first = min(cast(date, frame["month"].min()) for frame in frames)
    last = max(cast(date, frame["month"].max()) for frame in frames)

    return (
        pl.DataFrame({"month": pl.date_range(first, last, interval="1mo", eager=True)})
        .join(selic_monthly, on="month", how="left")
        .join(usd_monthly, on="month", how="left")
        .join(ipca_monthly, on="month", how="left")
        .sort("month")
        .with_columns(
            pl.col("selic_meta_eom").diff().alias("selic_delta_pp"),
            (pl.col("usd_brl_mean").pct_change() * 100).alias("usd_brl_mom_pct"),
            (pl.col("usd_brl_mean").pct_change(12) * 100).alias("usd_brl_yoy_pct"),
            compute_accumulated_12m(IPCA_MONTHLY.name).alias("ipca_12m"),
        )
    )
