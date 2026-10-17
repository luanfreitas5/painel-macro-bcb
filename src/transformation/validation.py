"""Contratos de dados nas fronteiras entre as camadas."""

from collections.abc import Iterable

import polars as pl

from exceptions.data import DataContractError


def validate_required_columns(frame: pl.DataFrame, required: Iterable[str], dataset: str) -> None:
    """Garante que o DataFrame contém as colunas exigidas.

    Parameters
    ----------
    frame : pl.DataFrame
        Dados a validar.
    required : Iterable[str]
        Nomes de colunas obrigatórias.
    dataset : str
        Nome do conjunto (usado na mensagem de erro).

    Raises
    ------
    DataContractError
        Se faltar alguma coluna.
    """
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataContractError(f"{dataset}: colunas ausentes {missing}")


def validate_series_contract(
    frame: pl.DataFrame, column: str, lower: float, upper: float, dataset: str
) -> None:
    """Valida uma série silver: não vazia, datas únicas e valores dentro da faixa plausível.

    Parameters
    ----------
    frame : pl.DataFrame
        Série com as colunas ``date`` e ``column``.
    column : str
        Coluna de valores.
    lower, upper : float
        Faixa plausível (inclusiva).
    dataset : str
        Nome do conjunto (usado na mensagem de erro).

    Raises
    ------
    DataContractError
        Se o contrato for violado.
    """
    validate_required_columns(frame, ["date", column], dataset)
    if frame.is_empty():
        raise DataContractError(f"{dataset}: série vazia")
    if frame["date"].is_duplicated().any():
        raise DataContractError(f"{dataset}: datas duplicadas")
    out_of_range = frame.filter(~pl.col(column).is_between(lower, upper))
    if not out_of_range.is_empty():
        raise DataContractError(
            f"{dataset}: {out_of_range.height} valores fora de [{lower}, {upper}] "
            f"(ex.: {out_of_range[column][0]})"
        )


def validate_focus_contract(frame: pl.DataFrame) -> None:
    """Valida o Focus silver: colunas, chave única e mês de referência no dia 1.

    Raises
    ------
    DataContractError
        Se o contrato for violado.
    """
    validate_required_columns(
        frame,
        ["survey_date", "reference_month", "median", "calculation_base"],
        "focus",
    )
    if frame.is_empty():
        raise DataContractError("focus: conjunto vazio")
    key = ["survey_date", "reference_month", "calculation_base"]
    if frame.select(pl.struct(key).is_duplicated().any()).item():
        raise DataContractError("focus: chave (data, mês de referência, base) duplicada")
    if (frame["reference_month"].dt.day() != 1).any():
        raise DataContractError("focus: mês de referência deve ser o primeiro dia do mês")
