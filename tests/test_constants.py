"""Testes das constantes do projeto (séries do SGS e nomes de artefatos)."""

from dataclasses import FrozenInstanceError

import pytest

from constants.datasets import (
    FOCUS_ENDPOINT,
    FOCUS_SILVER_NAME,
    FOCUS_SOURCE,
    GOLD_FOCUS_ERRORS,
    GOLD_FOCUS_SUMMARY,
    GOLD_PANEL,
)
from constants.series import IPCA_MONTHLY, SELIC_TARGET, SGS_SERIES, USD_SELL, SgsSeries


def test_sgs_series_contains_all_three_series():
    """O conjunto de séries cobre Selic, IPCA e dólar, nessa ordem."""
    assert SGS_SERIES == (SELIC_TARGET, IPCA_MONTHLY, USD_SELL)


def test_sgs_series_have_unique_codes_and_names():
    """Códigos, nomes e fontes não podem colidir (viram colunas e arquivos)."""
    assert len({s.code for s in SGS_SERIES}) == len(SGS_SERIES)
    assert len({s.name for s in SGS_SERIES}) == len(SGS_SERIES)
    assert len({s.source for s in SGS_SERIES}) == len(SGS_SERIES)


@pytest.mark.parametrize("series", SGS_SERIES, ids=lambda s: s.name)
def test_sgs_series_bounds_are_consistent(series):
    """O limite inferior é sempre menor que o superior."""
    assert series.lower < series.upper


@pytest.mark.parametrize(
    ("series", "code"), [(SELIC_TARGET, 432), (IPCA_MONTHLY, 433), (USD_SELL, 1)]
)
def test_sgs_series_source_follows_code(series, code):
    """A fonte bronze é derivada do código SGS."""
    assert series.code == code
    assert series.source == f"sgs_{code}"


def test_sgs_series_is_immutable():
    """A série é um dataclass congelado."""
    with pytest.raises(FrozenInstanceError):
        SELIC_TARGET.code = 1  # type: ignore[misc]


def test_sgs_series_equality_by_value():
    """Dataclasses congelados comparam por valor e são hasheáveis."""
    clone = SgsSeries(432, "selic_meta", "Meta Selic", "% a.a.", 0.0, 50.0)
    assert clone == SELIC_TARGET
    assert hash(clone) == hash(SELIC_TARGET)


def test_gold_artifacts_are_distinct_parquet_files():
    """Os três artefatos gold são arquivos parquet distintos."""
    files = {GOLD_PANEL, GOLD_FOCUS_ERRORS, GOLD_FOCUS_SUMMARY}
    assert len(files) == 3
    assert all(name.endswith(".parquet") for name in files)


def test_focus_constants_are_defined():
    """Fonte, endpoint e nome silver do Focus estão definidos."""
    assert FOCUS_SOURCE
    assert FOCUS_ENDPOINT == "ExpectativaMercadoMensais"
    assert FOCUS_SILVER_NAME
