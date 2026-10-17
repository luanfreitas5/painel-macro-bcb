"""Testes da versão do projeto."""

import re
from pathlib import Path

from config.version import __version__

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_is_semver():
    """A versão segue o formato ``MAJOR.MINOR.PATCH``."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_version_matches_pyproject():
    """``version.py`` e ``pyproject.toml`` (projeto e commitizen) não podem divergir."""
    content = PYPROJECT.read_text(encoding="utf-8")
    versions = re.findall(r'^version = "([^"]+)"', content, flags=re.MULTILINE)
    assert versions == [__version__, __version__]
