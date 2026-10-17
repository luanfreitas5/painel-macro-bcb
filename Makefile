# --- Configuração ----------------------------------------------------------
# 'src' vira raiz do path ao rodar o script diretamente.
RUN := uv run python src/main.py

# PYTHONHASHSEED precisa ser exportado ANTES do interpretador iniciar.
export PYTHONHASHSEED := 42

.DEFAULT_GOAL := help
.PHONY: help init install lock export \
	lint typecheck security deadcode complexity docstrings modernize quality \
	test smoke coverage hooks pre-commit update-hooks release \
	ingest transform pipeline app \
	jupyter clean

help:  ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Ambiente ---------------------------------------------------------------
init:  ## Instala dependências e hooks do pre-commit
	$(MAKE) install
	$(MAKE) hooks

install:  ## Instala dependências (runtime + dev)
	uv sync --dev

lock:  ## Gera/atualiza o uv.lock (commitar o arquivo)
	uv lock

export:  ## Exporta requirements.txt (runtime) para o Streamlit Community Cloud
	uv export --no-dev --no-hashes --no-emit-project -o requirements.txt

# --- Pipeline ---------------------------------------------------------------
ingest:  ## Baixa as séries do BCB para data/bronze (idempotente, com cache)
	$(RUN) ingest

transform:  ## Gera data/silver e data/gold a partir do bronze
	$(RUN) transform

pipeline:  ## Executa ingestão + transformação + análise do Focus
	$(RUN) run

app:  ## Sobe o dashboard Streamlit (http://localhost:8501)
	uv run streamlit run app/streamlit_app.py

# --- Qualidade --------------------------------------------------------------
lint:  ## Lint e formatação com ruff
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## Type checking estático (basedPyright)
	uv run basedpyright

security:  ## Análise de segurança (bandit + pip-audit)
	uv run bandit -r src -c pyproject.toml
	uv run pip-audit

deadcode:  ## Detecta código morto (vulture)
	uv run vulture src

complexity:  ## Limites de complexidade (xenon)
	uv run xenon --max-absolute B --max-modules A --max-average A src

docstrings:  ## Cobertura de docstrings (interrogate)
	uv run interrogate -v src

modernize:  ## Sugestões de modernização (refurb)
	uv run refurb src

quality: lint typecheck security deadcode complexity docstrings modernize  ## Suíte completa de qualidade (espelha o CI)

# --- Testes -----------------------------------------------------------------
test:  ## Roda os testes com cobertura
	uv run pytest -m "not slow"

smoke:  ## Roda apenas os smoke tests
	uv run pytest -m smoke -q --no-cov

coverage:  ## Gera o relatório de cobertura em HTML
	uv run pytest -m "not slow" --cov-report=html
	@echo "Relatório disponível em htmlcov/index.html"

# --- Git / releases ---------------------------------------------------------
hooks:  ## Instala os hooks do pre-commit e gera o baseline do detect-secrets
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	uv run detect-secrets scan > .secrets.baseline

pre-commit:  ## Roda todos os hooks em todos os arquivos
	uv run pre-commit run --all-files

update-hooks:  ## Atualiza as versões dos hooks
	uv run pre-commit autoupdate

release:  ## Nova release (versão + CHANGELOG + tag)
	uv run cz bump --changelog

# --- Utilitários ------------------------------------------------------------
jupyter:  ## Abre o JupyterLab
	uv run jupyter lab

clean:  ## Remove caches e artefatos temporários (não toca em data/)
	rm -rf .pytest_cache .ruff_cache .hypothesis htmlcov coverage.xml
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
