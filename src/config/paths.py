"""Caminhos do projeto, centralizados com ``pathlib.Path``."""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "configs" / "config.yaml"
LOGS_DIR = ROOT / "logs"


@dataclass(frozen=True)
class DataLayout:
    """Layout medalhão (bronze, silver, gold) a partir de um diretório raiz de dados.

    Parameters
    ----------
    root : Path
        Diretório que contém ``bronze/``, ``silver/`` e ``gold/``.

    Examples
    --------
    >>> layout = DataLayout(Path("data"))
    >>> layout.bronze
    PosixPath('data/bronze')
    """

    root: Path

    @classmethod
    def default(cls) -> "DataLayout":
        """Retorna o layout padrão do repositório (``<raiz>/data``)."""
        return cls(ROOT / "data")

    @property
    def bronze(self) -> Path:
        """Dados exatamente como recebidos (snapshots datados, imutáveis)."""
        return self.root / "bronze"

    @property
    def silver(self) -> Path:
        """Dados limpos, tipados, sem duplicatas e validados."""
        return self.root / "silver"

    @property
    def gold(self) -> Path:
        """Dados prontos para análise e para o painel."""
        return self.root / "gold"

    def ensure(self) -> None:
        """Cria os diretórios das três camadas, se ainda não existirem."""
        for layer in (self.bronze, self.silver, self.gold):
            layer.mkdir(parents=True, exist_ok=True)
