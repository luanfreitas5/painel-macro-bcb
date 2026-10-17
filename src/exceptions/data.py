"""Exceções relacionadas a dados (ingestão e contrato)."""

from exceptions.base import PainelMacroError


class IngestionError(PainelMacroError):
    """Falha ao coletar ou armazenar dados de uma fonte externa."""


class DataContractError(PainelMacroError):
    """Dados que violam o contrato esperado (colunas, tipos, faixas, unicidade)."""
