"""Fixtures sintéticas compartilhadas (nenhum dado real é usado nos testes)."""

from datetime import date

import polars as pl
import pytest


@pytest.fixture
def selic_daily() -> pl.DataFrame:
    """Meta Selic diária: 13,75 até 31/07/2023 e 12,25 a partir de 01/08/2023."""
    dates = pl.date_range(date(2023, 1, 1), date(2024, 3, 31), interval="1d", eager=True)
    return pl.DataFrame({"date": dates}).with_columns(
        pl.when(pl.col("date") < date(2023, 8, 1)).then(13.75).otherwise(12.25).alias("selic_meta")
    )


@pytest.fixture
def usd_daily() -> pl.DataFrame:
    """Dólar diário: R$ 5,00 em 2023 e R$ 5,50 a partir de 2024."""
    dates = pl.date_range(date(2023, 1, 1), date(2024, 3, 31), interval="1d", eager=True)
    return pl.DataFrame({"date": dates}).with_columns(
        pl.when(pl.col("date") < date(2024, 1, 1)).then(5.0).otherwise(5.5).alias("usd_brl_sell")
    )


@pytest.fixture
def ipca_monthly() -> pl.DataFrame:
    """IPCA mensal constante de 1,00% de jan/2023 a mar/2024 (15 meses)."""
    months = pl.date_range(date(2023, 1, 1), date(2024, 3, 1), interval="1mo", eager=True)
    return pl.DataFrame({"date": months, "ipca_mom": [1.0] * months.len()})
