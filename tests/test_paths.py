"""Testes dos caminhos centralizados e do layout medalhão."""

import dataclasses
from pathlib import Path

import pytest

from config.paths import CONFIG_FILE, LOGS_DIR, ROOT, DataLayout


def test_root_points_to_repository_root():
    """A raiz contém o ``pyproject.toml`` e o diretório ``src``."""
    assert (ROOT / "pyproject.toml").is_file()
    assert (ROOT / "src").is_dir()


def test_constants_are_derived_from_root():
    """Arquivo de configuração e logs ficam sob a raiz."""
    assert CONFIG_FILE == ROOT / "configs" / "config.yaml"
    assert CONFIG_FILE.is_file()
    assert LOGS_DIR == ROOT / "logs"


def test_layout_layers(tmp_path):
    """Cada camada é um subdiretório da raiz de dados."""
    layout = DataLayout(tmp_path)
    assert layout.bronze == tmp_path / "bronze"
    assert layout.silver == tmp_path / "silver"
    assert layout.gold == tmp_path / "gold"


def test_layout_default_uses_repository_data_dir():
    """O layout padrão aponta para ``<raiz>/data``."""
    assert DataLayout.default().root == ROOT / "data"


def test_layout_ensure_creates_layers_and_is_idempotent(tmp_path):
    """``ensure`` cria as três camadas e pode ser chamado repetidamente."""
    layout = DataLayout(tmp_path / "novo" / "data")
    layout.ensure()
    layout.ensure()
    assert all(p.is_dir() for p in (layout.bronze, layout.silver, layout.gold))


def test_layout_is_immutable(tmp_path):
    """O layout é congelado."""
    layout = DataLayout(tmp_path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        layout.root = Path("outro")  # type: ignore[misc]
