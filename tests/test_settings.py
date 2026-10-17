"""Testes da configuração validada com Pydantic."""

from datetime import date

import pytest
from pydantic import ValidationError

from config.settings import (
    FocusSettings,
    IngestionSettings,
    LogSettings,
    Settings,
    load_settings,
)
from exceptions.configuration import ConfigurationError


def test_code_defaults_match_versioned_config():
    """Os padrões em código coincidem com o ``config.yaml`` versionado."""
    assert Settings() == load_settings()
    assert Settings().ingestion.start_date == date(2010, 1, 1)


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (IngestionSettings, {"window_years": 0}),
        (IngestionSettings, {"window_years": 11}),
        (IngestionSettings, {"cache_ttl_days": -1}),
        (IngestionSettings, {"max_retries": 0}),
        (IngestionSettings, {"retry_wait_seconds": -0.1}),
        (FocusSettings, {"calculation_base": 2}),
        (FocusSettings, {"max_horizon_months": 25}),
        (FocusSettings, {"max_horizon_months": -1}),
        (LogSettings, {"level": "TRACE"}),
        (LogSettings, {"desconhecido": 1}),
    ],
)
def test_invalid_values_are_rejected(model, kwargs):
    """Valores fora das faixas e chaves extras falham na validação."""
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (IngestionSettings, {"window_years": 1}),
        (IngestionSettings, {"window_years": 10}),
        (FocusSettings, {"max_horizon_months": 0}),
        (FocusSettings, {"max_horizon_months": 24}),
        (FocusSettings, {"calculation_base": 1}),
    ],
)
def test_boundary_values_are_accepted(model, kwargs):
    """Os extremos das faixas são válidos."""
    assert model(**kwargs)


def test_load_settings_empty_yaml_uses_defaults(tmp_path):
    """Um YAML vazio equivale à configuração padrão."""
    path = tmp_path / "vazio.yaml"
    path.write_text("", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_load_settings_overrides_selected_keys(tmp_path):
    """Chaves informadas sobrescrevem o padrão; as demais são preservadas."""
    path = tmp_path / "parcial.yaml"
    path.write_text("log:\n  level: DEBUG\ningestion:\n  start_date: 2015-06-01\n", "utf-8")
    settings = load_settings(path)
    assert settings.log.level == "DEBUG"
    assert settings.ingestion.start_date == date(2015, 6, 1)
    assert settings.focus == FocusSettings()


def test_load_settings_malformed_yaml_raises(tmp_path):
    """YAML sintaticamente inválido vira ``ConfigurationError``."""
    path = tmp_path / "quebrado.yaml"
    path.write_text("log: [nao fecha\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="inválida"):
        load_settings(path)


def test_load_settings_missing_file_message_cites_path(tmp_path):
    """A mensagem de arquivo ausente cita o caminho."""
    path = tmp_path / "ausente.yaml"
    with pytest.raises(ConfigurationError, match="não encontrado") as info:
        load_settings(path)
    assert str(path) in str(info.value)


def test_load_settings_forbids_unknown_top_level_section(tmp_path):
    """Seções desconhecidas na raiz são recusadas."""
    path = tmp_path / "extra.yaml"
    path.write_text("outra_secao:\n  a: 1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(path)
