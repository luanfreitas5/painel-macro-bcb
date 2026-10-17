"""Constantes do Focus e dos artefatos da camada gold."""

# Expectativas de mercado (Focus): endpoint OData de projeções mensais.
FOCUS_SOURCE = "focus_ipca_monthly"
FOCUS_ENDPOINT = "ExpectativaMercadoMensais"
FOCUS_SILVER_NAME = "focus_ipca_monthly"

# Artefatos da camada gold.
GOLD_PANEL = "macro_monthly.parquet"
GOLD_FOCUS_ERRORS = "focus_errors.parquet"
GOLD_FOCUS_SUMMARY = "focus_error_summary.parquet"
