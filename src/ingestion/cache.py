"""Cache local da camada bronze: snapshots datados em Parquet e manifesto.

Cada fonte tem seu diretório ``bronze/<fonte>/`` com arquivos
``<fonte>_AAAAMMDD.parquet``. Uma nova execução no mesmo dia (ou dentro do TTL)
reutiliza o snapshot existente, o que torna a ingestão idempotente. O arquivo
``bronze/manifest.json`` registra hash SHA-256, linhas e data de cada snapshot.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

from exceptions.data import IngestionError

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"


def compute_sha256(path: Path) -> str:
    """Calcula o hash SHA-256 de um arquivo (leitura em blocos).

    Parameters
    ----------
    path : Path
        Arquivo a ser verificado.

    Returns
    -------
    str
        Hash hexadecimal.
    """
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_snapshot_path(bronze_dir: Path, source: str, snapshot_date: date) -> Path:
    """Monta o caminho do snapshot de uma fonte em uma data.

    Examples
    --------
    >>> build_snapshot_path(Path("data/bronze"), "sgs_432", date(2026, 1, 5)).name
    'sgs_432_20260105.parquet'
    """
    return bronze_dir / source / f"{source}_{snapshot_date:%Y%m%d}.parquet"


def parse_snapshot_date(path: Path) -> date:
    """Extrai a data do nome de um snapshot (``<fonte>_AAAAMMDD.parquet``).

    Raises
    ------
    IngestionError
        Se o nome do arquivo não seguir o padrão.
    """
    stamp = path.stem.rsplit("_", 1)[-1]
    try:
        return datetime.strptime(stamp, "%Y%m%d").date()
    except ValueError as exc:
        raise IngestionError(f"Nome de snapshot inválido: {path.name}") from exc


def find_latest_snapshot(bronze_dir: Path, source: str) -> Path | None:
    """Retorna o snapshot mais recente de uma fonte, ou ``None`` se não houver.

    Parameters
    ----------
    bronze_dir : Path
        Diretório da camada bronze.
    source : str
        Identificador da fonte (ex.: ``sgs_432``).
    """
    snapshots = sorted((bronze_dir / source).glob(f"{source}_????????.parquet"))
    return snapshots[-1] if snapshots else None


def is_snapshot_fresh(path: Path, ttl_days: int, today: date) -> bool:
    """Indica se o snapshot ainda está dentro do TTL.

    Parameters
    ----------
    path : Path
        Snapshot a avaliar.
    ttl_days : int
        Idade máxima (em dias, exclusiva). Com ``0`` o snapshot nunca é considerado fresco.
    today : date
        Data de referência.
    """
    return (today - parse_snapshot_date(path)).days < ttl_days


def _update_manifest(bronze_dir: Path, path: Path, rows: int) -> None:
    """Registra o snapshot no manifesto (escrita atômica)."""
    manifest_path = bronze_dir / MANIFEST_NAME
    manifest: dict[str, dict[str, dict[str, object]]] = {"snapshots": {}}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = path.relative_to(bronze_dir).as_posix()
    manifest["snapshots"][key] = {
        "sha256": compute_sha256(path),
        "rows": rows,
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(manifest_path)


def write_snapshot(frame: pl.DataFrame, bronze_dir: Path, source: str, snapshot_date: date) -> Path:
    """Grava um snapshot bronze (escrita atômica) e atualiza o manifesto.

    Parameters
    ----------
    frame : pl.DataFrame
        Dados exatamente como recebidos da fonte.
    bronze_dir : Path
        Diretório da camada bronze.
    source : str
        Identificador da fonte.
    snapshot_date : date
        Data do snapshot.

    Returns
    -------
    Path
        Caminho do Parquet gravado.

    Raises
    ------
    IngestionError
        Se ``frame`` estiver vazio.
    """
    if frame.is_empty():
        raise IngestionError(f"A fonte {source} não retornou dados.")
    path = build_snapshot_path(bronze_dir, source, snapshot_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".parquet.tmp")
    frame.write_parquet(tmp_path)
    tmp_path.replace(path)
    _update_manifest(bronze_dir, path, frame.height)
    return path


def load_or_fetch_snapshot(
    source: str,
    fetch: Callable[[], pl.DataFrame],
    bronze_dir: Path,
    ttl_days: int,
    force: bool = False,
    today: date | None = None,
) -> Path:
    """Reutiliza o snapshot recente da fonte ou coleta e grava um novo.

    Parameters
    ----------
    source : str
        Identificador da fonte.
    fetch : Callable[[], pl.DataFrame]
        Função que coleta os dados quando não há snapshot válido.
    bronze_dir : Path
        Diretório da camada bronze.
    ttl_days : int
        Idade máxima do snapshot reutilizável, em dias.
    force : bool, optional
        Ignora o cache e coleta novamente, by default False.
    today : date, optional
        Data de referência, by default ``date.today()``.

    Returns
    -------
    Path
        Caminho do snapshot a ser usado.
    """
    today = today or date.today()
    latest = find_latest_snapshot(bronze_dir, source)
    if latest is not None and not force and is_snapshot_fresh(latest, ttl_days, today):
        logger.info("Cache válido para %s: %s", source, latest.name)
        return latest
    logger.info("Coletando %s na fonte externa", source)
    return write_snapshot(fetch(), bronze_dir, source, today)
