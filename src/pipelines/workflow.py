"""Orquestração do fluxo: ingestão (bronze) -> transformação (silver) -> análise (gold)."""

import logging
from datetime import date
from functools import partial
from pathlib import Path

import polars as pl
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from analysis.focus_error import (
    compute_forecast_errors,
    select_forecasts,
    summarize_errors,
)
from config.paths import DataLayout
from config.settings import Settings
from constants.datasets import (
    FOCUS_SILVER_NAME,
    FOCUS_SOURCE,
    GOLD_FOCUS_ERRORS,
    GOLD_FOCUS_SUMMARY,
    GOLD_PANEL,
)
from constants.series import IPCA_MONTHLY, SELIC_TARGET, SGS_SERIES, USD_SELL
from exceptions.data import IngestionError
from ingestion.cache import find_latest_snapshot, load_or_fetch_snapshot
from ingestion.focus import fetch_focus_expectations
from ingestion.sgs import fetch_sgs_series
from transformation.gold import build_monthly_panel
from transformation.silver import clean_focus_expectations, clean_sgs_series
from transformation.validation import (
    validate_focus_contract,
    validate_series_contract,
)

logger = logging.getLogger(__name__)

GOLD_FILES = (GOLD_PANEL, GOLD_FOCUS_ERRORS, GOLD_FOCUS_SUMMARY)


def _build_progress() -> Progress:
    """Cria a barra de progresso padrão do projeto (rich)."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )


def run_ingestion(
    settings: Settings, layout: DataLayout, force: bool = False, today: date | None = None
) -> dict[str, Path]:
    """Coleta SGS (432, 433, 1) e Focus para a camada bronze, de forma idempotente.

    Parameters
    ----------
    settings : Settings
        Configuração validada.
    layout : DataLayout
        Diretórios de dados.
    force : bool, optional
        Ignora o cache local e coleta novamente, by default False.
    today : date, optional
        Data de referência (snapshot e fim da janela), by default ``date.today()``.

    Returns
    -------
    dict[str, Path]
        Snapshot bronze utilizado por fonte.

    Raises
    ------
    IngestionError
        Se alguma fonte falhar.
    """
    today = today or date.today()
    cfg = settings.ingestion
    layout.ensure()
    snapshots: dict[str, Path] = {}
    with _build_progress() as progress:
        task = progress.add_task("Ingestão BCB", total=len(SGS_SERIES) + 1)
        for series in SGS_SERIES:
            fetch = partial(
                fetch_sgs_series,
                series,
                cfg.start_date,
                today,
                cfg.window_years,
                cfg.max_retries,
                cfg.retry_wait_seconds,
            )
            snapshots[series.source] = load_or_fetch_snapshot(
                series.source, fetch, layout.bronze, cfg.cache_ttl_days, force, today
            )
            progress.advance(task)
        fetch_focus = partial(
            fetch_focus_expectations,
            settings.focus.indicator,
            cfg.start_date,
            today,
            1,
            cfg.max_retries,
            cfg.retry_wait_seconds,
        )
        snapshots[FOCUS_SOURCE] = load_or_fetch_snapshot(
            FOCUS_SOURCE, fetch_focus, layout.bronze, cfg.cache_ttl_days, force, today
        )
        progress.advance(task)
    return snapshots


def _read_latest_bronze(layout: DataLayout, source: str) -> pl.DataFrame:
    """Lê o snapshot bronze mais recente de uma fonte."""
    path = find_latest_snapshot(layout.bronze, source)
    if path is None:
        raise IngestionError(f"Sem dados bronze para {source}. Execute a ingestão primeiro.")
    return pl.read_parquet(path)


def run_transformation(settings: Settings, layout: DataLayout) -> dict[str, Path]:
    """Gera silver e gold a partir do bronze e calcula o erro do Focus.

    Parameters
    ----------
    settings : Settings
        Configuração validada.
    layout : DataLayout
        Diretórios de dados.

    Returns
    -------
    dict[str, Path]
        Arquivos gold gerados (painel mensal, erros e resumo por horizonte).

    Raises
    ------
    IngestionError
        Se faltar algum snapshot bronze.
    DataContractError
        Se algum conjunto violar o contrato de dados.
    """
    layout.ensure()

    silver: dict[str, pl.DataFrame] = {}
    for series in SGS_SERIES:
        clean = clean_sgs_series(_read_latest_bronze(layout, series.source), series.name)
        validate_series_contract(clean, series.name, series.lower, series.upper, series.name)
        clean.write_parquet(layout.silver / f"{series.name}.parquet")
        silver[series.name] = clean
        logger.info("Silver %s: %d linhas", series.name, clean.height)

    focus = clean_focus_expectations(_read_latest_bronze(layout, FOCUS_SOURCE))
    validate_focus_contract(focus)
    focus.write_parquet(layout.silver / f"{FOCUS_SILVER_NAME}.parquet")
    logger.info("Silver %s: %d linhas", FOCUS_SILVER_NAME, focus.height)

    panel = build_monthly_panel(
        silver[SELIC_TARGET.name], silver[IPCA_MONTHLY.name], silver[USD_SELL.name]
    )
    forecasts = select_forecasts(
        focus, settings.focus.calculation_base, settings.focus.max_horizon_months
    )
    errors = compute_forecast_errors(forecasts, panel.select("month", IPCA_MONTHLY.name))
    summary = summarize_errors(errors)

    outputs = {
        GOLD_PANEL: panel,
        GOLD_FOCUS_ERRORS: errors,
        GOLD_FOCUS_SUMMARY: summary,
    }
    paths: dict[str, Path] = {}
    for filename, frame in outputs.items():
        paths[filename] = layout.gold / filename
        frame.write_parquet(paths[filename])
        logger.info("Gold %s: %d linhas", filename, frame.height)
    return paths


def run_pipeline(
    settings: Settings, layout: DataLayout, force: bool = False, today: date | None = None
) -> dict[str, Path]:
    """Executa ingestão e transformação em sequência.

    Returns
    -------
    dict[str, Path]
        Arquivos gold gerados.
    """
    run_ingestion(settings, layout, force=force, today=today)
    return run_transformation(settings, layout)


def ensure_gold_tables(settings: Settings, layout: DataLayout) -> dict[str, pl.DataFrame]:
    """Carrega as tabelas gold, executando o pipeline se ainda não existirem.

    Usado pelo app Streamlit: no Community Cloud o disco começa vazio (dados fora do Git),
    então a primeira execução coleta os dados do BCB.

    Parameters
    ----------
    settings : Settings
        Configuração validada.
    layout : DataLayout
        Diretórios de dados.

    Returns
    -------
    dict[str, pl.DataFrame]
        Tabelas indexadas pelo nome do arquivo gold.
    """
    if not all((layout.gold / name).is_file() for name in GOLD_FILES):
        logger.info("Tabelas gold ausentes; executando o pipeline")
        run_pipeline(settings, layout)
    return {name: pl.read_parquet(layout.gold / name) for name in GOLD_FILES}
