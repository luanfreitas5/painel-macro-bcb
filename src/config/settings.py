"""Configuração do projeto, carregada de YAML e validada com Pydantic."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config.paths import CONFIG_FILE
from exceptions.configuration import ConfigurationError


class IngestionSettings(BaseModel):
    """Parâmetros da ingestão (SGS e Focus)."""

    model_config = ConfigDict(extra="forbid")

    start_date: date = date(2010, 1, 1)
    window_years: int = Field(default=5, ge=1, le=10)
    cache_ttl_days: int = Field(default=1, ge=0)
    max_retries: int = Field(default=3, ge=1)
    retry_wait_seconds: float = Field(default=2.0, ge=0)


class FocusSettings(BaseModel):
    """Parâmetros da análise do erro do Focus."""

    model_config = ConfigDict(extra="forbid")

    indicator: str = "IPCA"
    calculation_base: Literal[0, 1] = 0
    max_horizon_months: int = Field(default=12, ge=0, le=24)


class LogSettings(BaseModel):
    """Parâmetros de logging."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class Settings(BaseModel):
    """Configuração global do projeto."""

    model_config = ConfigDict(extra="forbid")

    ingestion: IngestionSettings = IngestionSettings()
    focus: FocusSettings = FocusSettings()
    log: LogSettings = LogSettings()


def load_settings(path: Path = CONFIG_FILE) -> Settings:
    """Carrega e valida a configuração a partir de um arquivo YAML.

    Parameters
    ----------
    path : Path, optional
        Caminho do YAML, by default ``configs/config.yaml``.

    Returns
    -------
    Settings
        Configuração validada.

    Raises
    ------
    ConfigurationError
        Se o arquivo não existir, não for um YAML válido ou violar o esquema.

    Examples
    --------
    >>> settings = load_settings()
    >>> settings.focus.max_horizon_months
    12
    """
    if not path.is_file():
        raise ConfigurationError(f"Arquivo de configuração não encontrado: {path}")
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Settings.model_validate(content)
    except (yaml.YAMLError, ValidationError) as exc:
        raise ConfigurationError(f"Configuração inválida em {path}: {exc}") from exc
