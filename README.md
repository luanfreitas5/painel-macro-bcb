# 📈 Painel Macro BCB

[![CI](https://github.com/luanfreitas5/painel-macro-bcb/actions/workflows/ci.yml/badge.svg)](https://github.com/luanfreitas5/painel-macro-bcb/actions/workflows/ci.yml)
[![Tests](https://github.com/luanfreitas5/painel-macro-bcb/actions/workflows/tests.yml/badge.svg)](https://github.com/luanfreitas5/painel-macro-bcb/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)

Dashboard Streamlit de indicadores macroeconômicos do Banco Central do Brasil e análise do **erro de projeção do Boletim Focus** para o IPCA.

## 🎯 Problema

Decisões de investimento e de política econômica dependem de indicadores espalhados em APIs distintas, com frequências diferentes (diária e mensal). Além disso, a inflação esperada pelo mercado (Focus) é usada como referência, mas raramente se mede o quanto ela acerta.

## ❓ Pergunta

> **O quanto a mediana do Focus erra o IPCA mensal, e esse erro muda com o horizonte da projeção?**
> Há viés sistemático (superestimação ou subestimação)?

## 🗂️ Dados

Todos públicos, do Banco Central (via [`python-bcb`](https://github.com/wilsonfreitas/python-bcb)):

| Fonte | Série | Frequência |
|---|---|---|
| SGS 432 | Meta Selic (% a.a.) | diária |
| SGS 433 | IPCA, variação mensal (%) | mensal |
| SGS 1 | Dólar comercial, venda (R$) | diária |
| Expectativas de Mercado | Focus: projeções mensais de IPCA (mediana) | por pesquisa |

Camadas (`data/`, **fora do Git**):

- `bronze/` — snapshots datados exatamente como recebidos (`<fonte>/<fonte>_AAAAMMDD.parquet`) + `manifest.json` com SHA-256. Nunca é modificada.
- `silver/` — limpa, tipada, sem duplicatas e validada por contrato de dados.
- `gold/` — painel mensal e tabelas do erro do Focus, consumidas pelo app.

Séries diárias são consultadas **por janelas de data** (a API do SGS limita séries diárias a 10 anos por consulta).

## 🔬 Metodologia

1. **Transformação (Polars):** Selic = último dia do mês; dólar = média e fechamento do mês; calendário mensal contínuo; variações (`selic_delta_pp`, `usd_brl_mom_pct`, `usd_brl_yoy_pct`); IPCA acumulado em 12 meses por composição: `(∏(1 + x/100) − 1) × 100`.
2. **Erro do Focus:** horizonte *h* = meses entre a pesquisa e o mês projetado (`h = 0` é o próprio mês). Para cada (mês, *h*) usa-se a **última** pesquisa do mês correspondente. Erro = mediana projetada − IPCA realizado (p.p.). Por horizonte: viés, MAE e RMSE, com IC 95% (aproximação normal).

## 🚀 Como reproduzir

Requer [uv](https://docs.astral.sh/uv/) e Python 3.10+.

```bash
make init        # uv sync --dev + hooks do pre-commit
make pipeline    # ingestão (bronze) -> silver -> gold
make app         # dashboard em http://localhost:8501
make test        # pytest com cobertura (mínimo 80%)
make quality     # lint, tipos, segurança, código morto, complexidade, docstrings
```

A ingestão é **idempotente**: reexecutar no mesmo dia reutiliza o snapshot (TTL em `configs/config.yaml`); `python src/main.py ingest --force` ignora o cache. Comandos individuais: `make ingest`, `make transform`.

Estrutura:

```
src/                config/ · constants/ · exceptions/ · ingestion/ · transformation/ · analysis/ · pipelines/
src/main.py         CLI (ingest | transform | run)
app/streamlit_app.py
configs/config.yaml configuração validada com Pydantic
data/{bronze,silver,gold}/   fora do Git
tests/  notebooks/
```

## 📊 Resultados

> Preencha após a primeira execução de `make pipeline` (os números dependem da data da coleta).

| Horizonte (meses) | n | Viés (p.p.) | MAE (p.p.) |
|---|---|---|---|
| 0 | — | — | — |
| 3 | — | — | — |
| 6 | — | — | — |
| 12 | — | — | — |

Interpretação esperada: o erro cresce com o horizonte; viés positivo indica que o Focus superestima o IPCA.

## ☁️ Deploy no Streamlit Community Cloud

1. Suba o repositório no GitHub (público) e confirme que `requirements.txt` está atualizado (`make export`).
2. Em [share.streamlit.io](https://share.streamlit.io), clique em **Create app** → **Deploy a public app from GitHub**.
3. Selecione o repositório, a branch `main` e o *Main file path*: `app/streamlit_app.py`.
4. Em **Advanced settings**, escolha Python 3.12 (ou 3.10+). Não há *secrets*: as APIs do BCB são públicas.
5. **Deploy.** Como `data/` não está no Git, o app coleta os dados na primeira abertura (alguns minutos) e depois usa o cache em disco (`st.cache_data` + Parquet). O disco do Community Cloud é efêmero: ao reiniciar, a coleta se repete.

## ⚠️ Limitações

- O IPCA realizado é o valor **atual** da série, que pode diferir do divulgado na época.
- O último mês das séries diárias pode estar incompleto (a média/fechamento mensal é parcial).
- O IC 95% ignora a autocorrelação dos erros de meses vizinhos e tende a ser otimista; não há teste formal de significância entre horizontes.
- Usa-se apenas a mediana do Focus com a base de cálculo configurada (`calculation_base`); a análise é descritiva, não causal.
- Cobertura do Focus mensal e limites da API do BCB podem mudar; falhas de rede são repetidas (`max_retries`) e depois reportadas.

## 📄 Licença

[MIT](LICENSE)
