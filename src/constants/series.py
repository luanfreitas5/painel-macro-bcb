"""Séries do SGS (BCB) usadas no projeto e seus limites de plausibilidade."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SgsSeries:
    """Descreve uma série do Sistema Gerenciador de Séries Temporais (SGS) do BCB.

    Attributes
    ----------
    code : int
        Código da série no SGS.
    name : str
        Nome da coluna usada no projeto (inglês, snake_case).
    label : str
        Rótulo legível (pt-BR) para gráficos.
    unit : str
        Unidade de medida.
    lower : float
        Limite inferior plausível (contrato de dados).
    upper : float
        Limite superior plausível (contrato de dados).
    """

    code: int
    name: str
    label: str
    unit: str
    lower: float
    upper: float

    @property
    def source(self) -> str:
        """Identificador da fonte na camada bronze (ex.: ``sgs_432``)."""
        return f"sgs_{self.code}"


SELIC_TARGET = SgsSeries(432, "selic_meta", "Meta Selic", "% a.a.", 0.0, 50.0)
IPCA_MONTHLY = SgsSeries(433, "ipca_mom", "IPCA mensal", "% a.m.", -5.0, 10.0)
USD_SELL = SgsSeries(1, "usd_brl_sell", "Dólar comercial (venda)", "R$", 0.1, 20.0)

SGS_SERIES: tuple[SgsSeries, ...] = (SELIC_TARGET, IPCA_MONTHLY, USD_SELL)
