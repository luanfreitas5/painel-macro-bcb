"""Exceções de configuração."""

from exceptions.base import PainelMacroError


class ConfigurationError(PainelMacroError):
    """Configuração ausente ou inválida."""
