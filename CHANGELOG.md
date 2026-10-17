# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e versionamento
[SemVer](https://semver.org/lang/pt-BR/). Atualizado pelo commitizen (`make release`).

## [Unreleased]

### Added

- Ingestão idempotente com cache local (SGS 432, 433 e 1; Focus de IPCA) na camada bronze.
- Transformação em Polars: painel mensal, variações e IPCA acumulado em 12 meses.
- Análise do erro de projeção do Focus por horizonte (viés, MAE, RMSE, IC 95%).
- Dashboard Streamlit com seleção de período e séries, gráficos Plotly e aba do Focus.
- Testes, CI (lint, tipos, segurança, testes) e pre-commit.
