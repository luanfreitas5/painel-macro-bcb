"""Testes da hierarquia de exceções do projeto."""

import pytest

from exceptions.base import PainelMacroError
from exceptions.configuration import ConfigurationError
from exceptions.data import DataContractError, IngestionError


@pytest.mark.parametrize("error", [ConfigurationError, IngestionError, DataContractError])
def test_specific_errors_inherit_from_base(error):
    """Todo erro específico é capturável como ``PainelMacroError``."""
    assert issubclass(error, PainelMacroError)
    with pytest.raises(PainelMacroError, match="falha"):
        raise error("falha")


def test_base_error_is_an_exception():
    """A base herda de ``Exception`` (não de ``BaseException``)."""
    assert issubclass(PainelMacroError, Exception)


def test_sibling_errors_are_not_interchangeable():
    """Um erro específico não é subclasse dos irmãos."""
    assert not issubclass(IngestionError, DataContractError)
    assert not issubclass(DataContractError, ConfigurationError)


def test_error_preserves_cause_chain():
    """``raise ... from`` mantém a causa original."""
    cause = ValueError("original")
    with pytest.raises(ConfigurationError) as info:
        raise ConfigurationError("inválida") from cause
    assert info.value.__cause__ is cause
