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

Coleta de 17/10/2026 · painel mensal de jan/2010 a out/2026 (202 meses) · erro = mediana do Focus − IPCA realizado (p.p.), IC 95% entre parênteses.

| Horizonte (meses) | n | Viés (p.p.) | MAE (p.p.) | RMSE (p.p.) |
|---|---|---|---|---|
| 0 | 201 | −0,014 (± 0,015) | 0,082 (± 0,010) | 0,109 |
| 3 | 198 | −0,062 (± 0,046) | 0,244 (± 0,032) | 0,333 |
| 6 | 195 | −0,073 (± 0,048) | 0,260 (± 0,033) | 0,351 |
| 12 | 189 | −0,088 (± 0,049) | 0,265 (± 0,034) | 0,356 |

Tabela completa (horizontes 0 a 12) em `data/gold/focus_error_summary.parquet`.

**Leitura:**

- **O erro cresce com o horizonte, mas satura.** O MAE vai de 0,08 p.p. (mês corrente) a ~0,25 p.p. em 3 meses e praticamente estabiliza a partir daí (0,26 p.p. em 6 e 12 meses); o ganho de informação do Focus se concentra nos primeiros meses.
- **Viés levemente negativo: o Focus tende a subestimar o IPCA mensal.** Em `h = 0` o viés não se distingue de zero; de `h = 1` em diante o IC 95% exclui zero e o viés se aproxima de −0,09 p.p. em 12 meses. A magnitude é pequena frente ao MAE (cerca de um terço), ou seja, o erro é dominado por dispersão, não por viés.
- **Ressalva estatística:** os ICs ignoram a autocorrelação dos erros (ver Limitações) e são otimistas; o último mês (out/2026) pode estar incompleto.

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
