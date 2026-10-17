"""Configuração de logging com handler Rich no console e arquivo diário."""

import logging
from datetime import date
from pathlib import Path

from rich.logging import RichHandler

from config.paths import LOGS_DIR


def configure_logging(level: str = "INFO", logs_dir: Path = LOGS_DIR) -> None:
    """Configura o logging do projeto (console Rich + arquivo ``log_YYYY-MM-DD.log``).

    Parameters
    ----------
    level : str, optional
        Nível de log (``DEBUG``, ``INFO``, ``WARNING`` ou ``ERROR``), by default ``"INFO"``.
    logs_dir : Path, optional
        Diretório dos arquivos de log, by default ``<raiz>/logs``.

    Examples
    --------
    >>> configure_logging("DEBUG")
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"log_{date.today():%Y-%m-%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s \t %(levelname)s \t %(name)s \t %(message)s")
    )
    logging.basicConfig(
        level=level,
        format="%(name)s - %(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False), file_handler],
        force=True,
    )
