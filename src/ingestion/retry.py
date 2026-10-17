"""Novas tentativas para chamadas de rede."""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import requests

from exceptions.data import IngestionError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def call_with_retry(func: Callable[[], T], max_retries: int, wait_seconds: float) -> T:
    """Executa ``func`` repetindo em caso de falha transitória de rede.

    Parameters
    ----------
    func : Callable[[], T]
        Função sem argumentos que realiza a chamada.
    max_retries : int
        Número máximo de tentativas (>= 1).
    wait_seconds : float
        Espera base entre tentativas; a espera cresce linearmente (``wait * tentativa``).

    Returns
    -------
    T
        Resultado de ``func``.

    Raises
    ------
    IngestionError
        Se todas as tentativas falharem.

    Examples
    --------
    >>> call_with_retry(lambda: 42, max_retries=3, wait_seconds=0)
    42
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (requests.RequestException, ValueError) as exc:  # noqa: PERF203
            last_error = exc
            logger.warning("Tentativa %d/%d falhou: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(wait_seconds * attempt)
    raise IngestionError(f"Falha após {max_retries} tentativas: {last_error}") from last_error
