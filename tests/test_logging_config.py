"""Testes da configuração de logging (console Rich + arquivo diário)."""

import logging
from datetime import date

import pytest
from rich.logging import RichHandler

from config.logging import configure_logging


@pytest.fixture
def root_logger():
    """Entrega o logger raiz e restaura handlers e nível após o teste."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield root
    for handler in root.handlers[:]:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def _flush(root: logging.Logger) -> None:
    """Força a escrita dos handlers no disco."""
    for handler in root.handlers:
        handler.flush()


def test_configure_logging_creates_daily_file(tmp_path, root_logger):
    """O arquivo ``log_YYYY-MM-DD.log`` é criado (inclusive o diretório)."""
    logs_dir = tmp_path / "logs" / "aninhado"
    configure_logging("INFO", logs_dir)
    assert (logs_dir / f"log_{date.today():%Y-%m-%d}.log").is_file()


def test_configure_logging_installs_rich_and_file_handlers(tmp_path, root_logger):
    """Há exatamente um handler Rich e um de arquivo, com o nível pedido."""
    configure_logging("DEBUG", tmp_path)
    assert sum(isinstance(h, RichHandler) for h in root_logger.handlers) == 1
    assert sum(isinstance(h, logging.FileHandler) for h in root_logger.handlers) == 1
    assert root_logger.level == logging.DEBUG


def test_configure_logging_is_idempotent(tmp_path, root_logger):
    """Chamadas repetidas substituem os handlers, sem duplicar."""
    configure_logging("INFO", tmp_path)
    configure_logging("INFO", tmp_path)
    assert len(root_logger.handlers) == 2


def test_file_log_uses_tab_separated_format(tmp_path, root_logger):
    """O arquivo registra ``data <tab> nível <tab> logger <tab> mensagem``."""
    configure_logging("INFO", tmp_path)
    logging.getLogger("teste.modulo").info("mensagem de teste")
    _flush(root_logger)
    content = next(tmp_path.glob("log_*.log")).read_text(encoding="utf-8")
    fields = [field.strip() for field in content.strip().split("\t")]
    assert fields[1:] == ["INFO", "teste.modulo", "mensagem de teste"]


def test_level_filters_lower_severity(tmp_path, root_logger):
    """Mensagens abaixo do nível configurado não chegam ao arquivo."""
    configure_logging("WARNING", tmp_path)
    logging.getLogger("teste").info("ignorada")
    logging.getLogger("teste").warning("registrada")
    _flush(root_logger)
    content = next(tmp_path.glob("log_*.log")).read_text(encoding="utf-8")
    assert "registrada" in content
    assert "ignorada" not in content
