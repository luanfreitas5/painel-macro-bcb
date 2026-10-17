"""Coleta de séries do SGS (python-bcb) por janelas de data."""

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import polars as pl

from constants.series import SgsSeries
from exceptions.data import IngestionError
from ingestion.retry import call_with_retry

logger = logging.getLogger(__name__)

SgsGetter = Callable[..., Any]


def build_date_windows(start: date, end: date, window_years: int) -> list[tuple[date, date]]:
    """Divide ``[start, end]`` em janelas de até ``window_years`` anos-calendário.

    A API do SGS limita a consulta de séries diárias a janelas de 10 anos; por isso a
    coleta é feita em janelas menores e concatenada depois.

    Parameters
    ----------
    start : date
        Data inicial (inclusiva).
    end : date
        Data final (inclusiva).
    window_years : int
        Número de anos-calendário por janela.

    Returns
    -------
    list[tuple[date, date]]
        Janelas contíguas e sem sobreposição; vazia se ``start > end``.

    Examples
    --------
    >>> windows = build_date_windows(date(2018, 3, 10), date(2021, 6, 1), 2)
    >>> len(windows)
    2
    >>> windows[0][1]
    datetime.date(2019, 12, 31)
    """
    windows: list[tuple[date, date]] = []
    current = start
    while current <= end:
        window_end = min(date(current.year + window_years - 1, 12, 31), end)
        windows.append((current, window_end))
        current = window_end + timedelta(days=1)
    return windows


def _default_getter() -> SgsGetter:
    """Importa sob demanda o ``sgs.get`` do python-bcb."""
    from bcb import sgs

    return sgs.get


def fetch_sgs_series(
    series: SgsSeries,
    start: date,
    end: date,
    window_years: int,
    max_retries: int = 3,
    retry_wait_seconds: float = 2.0,
    getter: SgsGetter | None = None,
) -> pl.DataFrame:
    """Coleta uma série do SGS consultando por janelas de data.

    Parameters
    ----------
    series : SgsSeries
        Série a coletar.
    start, end : date
        Período da coleta (inclusivo).
    window_years : int
        Anos-calendário por janela de consulta.
    max_retries : int, optional
        Tentativas por janela, by default 3.
    retry_wait_seconds : float, optional
        Espera base entre tentativas, by default 2.0.
    getter : SgsGetter, optional
        Função compatível com ``bcb.sgs.get`` (injetável em testes); por padrão usa o python-bcb.

    Returns
    -------
    pl.DataFrame
        Colunas ``date`` (Date) e ``value`` (Float64), sem duplicatas e ordenado por data.

    Raises
    ------
    IngestionError
        Se a coleta falhar ou não retornar nenhum dado.
    """
    get = getter or _default_getter()
    frames: list[pl.DataFrame] = []
    for window_start, window_end in build_date_windows(start, end, window_years):
        logger.info("SGS %s: janela %s a %s", series.code, window_start, window_end)
        raw = call_with_retry(
            lambda ws=window_start, we=window_end: get(
                {series.name: series.code}, start=ws.isoformat(), end=we.isoformat()
            ),
            max_retries,
            retry_wait_seconds,
        )
        if raw is None or len(raw) == 0:
            continue
        frames.append(
            pl.DataFrame(
                {
                    "date": raw.index.date.tolist(),
                    "value": raw[series.name].astype(float).tolist(),
                },
                schema={"date": pl.Date, "value": pl.Float64},
            )
        )
    if not frames:
        raise IngestionError(f"A série SGS {series.code} não retornou dados de {start} a {end}.")
    return pl.concat(frames).unique(subset="date", keep="last").sort("date")
