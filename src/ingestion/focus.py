"""Coleta das expectativas mensais do Focus (OData/Olinda) via python-bcb."""

import logging
from collections.abc import Callable
from datetime import date
from typing import Any, cast

import pandas as pd
import polars as pl

from constants.datasets import FOCUS_ENDPOINT
from exceptions.data import IngestionError
from ingestion.retry import call_with_retry
from ingestion.sgs import build_date_windows

logger = logging.getLogger(__name__)

FocusWindowFetcher = Callable[[str, date, date], pd.DataFrame]

_QUERY_LIMIT = 100_000


def query_focus_window(indicator: str, start: date, end: date) -> pd.DataFrame:
    """Consulta o Focus (projeções mensais) para um indicador e uma janela de datas.

    Parameters
    ----------
    indicator : str
        Indicador (ex.: ``"IPCA"``).
    start, end : date
        Janela de datas da pesquisa (``Data``), inclusiva.

    Returns
    -------
    pd.DataFrame
        Resposta da API, sem transformações.
    """
    from bcb import Expectativas

    endpoint = cast(Any, Expectativas().get_endpoint(FOCUS_ENDPOINT))
    is_indicator = endpoint.Indicador == indicator
    return (
        endpoint.query()
        .filter(is_indicator)
        .filter(endpoint.Data >= start.isoformat())
        .filter(endpoint.Data <= end.isoformat())
        .limit(_QUERY_LIMIT)
        .collect()
    )


def fetch_focus_expectations(
    indicator: str,
    start: date,
    end: date,
    window_years: int = 1,
    max_retries: int = 3,
    retry_wait_seconds: float = 2.0,
    window_fetcher: FocusWindowFetcher | None = None,
) -> pl.DataFrame:
    """Coleta as expectativas mensais do Focus consultando por janelas de data.

    Parameters
    ----------
    indicator : str
        Indicador (ex.: ``"IPCA"``).
    start, end : date
        Período da coleta (inclusivo).
    window_years : int, optional
        Anos-calendário por janela (1 mantém cada resposta pequena), by default 1.
    max_retries : int, optional
        Tentativas por janela, by default 3.
    retry_wait_seconds : float, optional
        Espera base entre tentativas, by default 2.0.
    window_fetcher : FocusWindowFetcher, optional
        Substituto de :func:`query_focus_window` (injetável em testes).

    Returns
    -------
    pl.DataFrame
        Respostas concatenadas, com as colunas originais da API e sem linhas duplicadas.

    Raises
    ------
    IngestionError
        Se a coleta falhar ou não retornar dados.
    """
    fetch = window_fetcher or query_focus_window
    frames: list[pl.DataFrame] = []
    for window_start, window_end in build_date_windows(start, end, window_years):
        logger.info("Focus %s: janela %s a %s", indicator, window_start, window_end)
        raw = call_with_retry(
            lambda ws=window_start, we=window_end: fetch(indicator, ws, we),
            max_retries,
            retry_wait_seconds,
        )
        if raw is not None and len(raw) > 0:
            frames.append(pl.from_pandas(raw))
    if not frames:
        raise IngestionError(f"O Focus não retornou dados para {indicator} de {start} a {end}.")
    return pl.concat(frames, how="vertical_relaxed").unique(maintain_order=True)
