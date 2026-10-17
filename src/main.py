"""Ponto de entrada (CLI) do pipeline.

Uso
---
    python src/main.py ingest            # bronze (idempotente, com cache)
    python src/main.py transform         # silver + gold + erro do Focus
    python src/main.py run --force       # tudo, ignorando o cache local
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.logging import configure_logging
from config.paths import CONFIG_FILE, DataLayout
from config.settings import load_settings
from pipelines.workflow import run_ingestion, run_pipeline, run_transformation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Interpreta os argumentos de linha de comando.

    Parameters
    ----------
    argv : list[str], optional
        Argumentos (padrão: ``sys.argv[1:]``).

    Returns
    -------
    argparse.Namespace
        Comando, caminho da configuração, diretório de dados e flag ``force``.
    """
    parser = argparse.ArgumentParser(description="Painel macro BCB — pipeline de dados")
    parser.add_argument("command", choices=["ingest", "transform", "run"])
    parser.add_argument("--config", type=Path, default=CONFIG_FILE, help="YAML de configuração")
    parser.add_argument("--data-dir", type=Path, default=None, help="Raiz de data/ (camadas)")
    parser.add_argument("--force", action="store_true", help="Ignora o cache local da ingestão")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Executa o comando solicitado.

    Returns
    -------
    int
        Código de saída (0 em caso de sucesso).
    """
    args = parse_args(argv)
    settings = load_settings(args.config)
    configure_logging(settings.log.level)
    layout = DataLayout(args.data_dir) if args.data_dir else DataLayout.default()

    if args.command == "ingest":
        run_ingestion(settings, layout, force=args.force)
    elif args.command == "transform":
        run_transformation(settings, layout)
    else:
        run_pipeline(settings, layout, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
