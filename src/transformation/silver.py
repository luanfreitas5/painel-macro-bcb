"""Bronze -> silver: tipagem, limpeza e remoção de duplicatas."""

import polars as pl

from transformation.validation import validate_required_columns


def clean_sgs_series(raw: pl.DataFrame, name: str) -> pl.DataFrame:
    """Limpa uma série SGS bruta.

    Remove nulos e valores não finitos, elimina datas duplicadas (mantém a última) e
    ordena por data.

    Parameters
    ----------
    raw : pl.DataFrame
        Dados bronze com as colunas ``date`` e ``value``.
    name : str
        Nome da coluna de valores na saída.

    Returns
    -------
    pl.DataFrame
        Colunas ``date`` (Date) e ``name`` (Float64).

    Raises
    ------
    DataContractError
        Se faltarem as colunas ``date`` ou ``value``.
    """
    validate_required_columns(raw, ["date", "value"], name)
    return (
        raw.select(
            pl.col("date").cast(pl.Date),
            pl.col("value").cast(pl.Float64).alias(name),
        )
        .drop_nulls()
        .filter(pl.col(name).is_finite())
        .unique(subset="date", keep="last", maintain_order=True)
        .sort("date")
    )


def clean_focus_expectations(raw: pl.DataFrame) -> pl.DataFrame:
    """Limpa as expectativas mensais do Focus.

    Converte a data da pesquisa e o mês de referência (``MM/AAAA``) para ``Date``,
    renomeia as colunas para inglês e elimina chaves duplicadas.

    Parameters
    ----------
    raw : pl.DataFrame
        Dados bronze com as colunas originais da API (``Data``, ``DataReferencia``,
        ``Mediana``, ``Media``, ``DesvioPadrao``, ``numeroRespondentes``, ``baseCalculo``).

    Returns
    -------
    pl.DataFrame
        Colunas ``survey_date``, ``reference_month`` (primeiro dia do mês), ``median``,
        ``mean``, ``std``, ``n_respondents`` e ``calculation_base``.

    Raises
    ------
    DataContractError
        Se faltarem colunas obrigatórias.
    """
    validate_required_columns(
        raw,
        ["Data", "DataReferencia", "Mediana", "Media", "DesvioPadrao", "baseCalculo"],
        "focus (bronze)",
    )
    n_respondents = (
        pl.col("numeroRespondentes").cast(pl.Int64, strict=False)
        if "numeroRespondentes" in raw.columns
        else pl.lit(None, dtype=pl.Int64)
    )
    return (
        raw.select(
            pl.col("Data")
            .cast(pl.Utf8)
            .str.slice(0, 10)
            .str.to_date("%Y-%m-%d")
            .alias("survey_date"),
            pl.concat_str([pl.lit("01/"), pl.col("DataReferencia").cast(pl.Utf8)])
            .str.to_date("%d/%m/%Y")
            .alias("reference_month"),
            pl.col("Mediana").cast(pl.Float64).alias("median"),
            pl.col("Media").cast(pl.Float64).alias("mean"),
            pl.col("DesvioPadrao").cast(pl.Float64).alias("std"),
            n_respondents.alias("n_respondents"),
            pl.col("baseCalculo").cast(pl.Int64, strict=False).alias("calculation_base"),
        )
        .drop_nulls(["survey_date", "reference_month", "median", "calculation_base"])
        .unique(
            subset=["survey_date", "reference_month", "calculation_base"],
            keep="last",
            maintain_order=True,
        )
        .sort(["survey_date", "reference_month", "calculation_base"])
    )
