"""Dashboard Streamlit: indicadores macro do BCB e erro de projeção do Focus.

Execução local: ``make app`` (ou ``streamlit run app/streamlit_app.py``).
"""

import sys
from datetime import date
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from plotly.subplots import make_subplots

from analysis.focus_error import summarize_errors
from config.paths import DataLayout
from config.settings import load_settings
from constants.datasets import GOLD_FOCUS_ERRORS, GOLD_PANEL
from pipelines.workflow import ensure_gold_tables

st.set_page_config(page_title="Painel Macro BCB", page_icon="📈", layout="wide")

# coluna do painel gold -> (rótulo, unidade)
SERIES_OPTIONS: dict[str, tuple[str, str]] = {
    "selic_meta_eom": ("Meta Selic (fim do mês)", "% a.a."),
    "selic_delta_pp": ("Variação mensal da meta Selic", "p.p."),
    "ipca_mom": ("IPCA mensal", "% a.m."),
    "ipca_12m": ("IPCA acumulado em 12 meses", "%"),
    "usd_brl_mean": ("Dólar (venda) — média mensal", "R$"),
    "usd_brl_mom_pct": ("Dólar — variação mensal da média", "%"),
    "usd_brl_yoy_pct": ("Dólar — variação em 12 meses da média", "%"),
}
DEFAULT_SERIES = ["selic_meta_eom", "ipca_12m", "usd_brl_mean"]
COLORS = {"line": "#1f77b4", "forecast": "#d62728", "realized": "#2ca02c"}


@st.cache_data(show_spinner="Carregando dados do BCB (a primeira execução pode demorar)...")
def load_tables() -> dict[str, pl.DataFrame]:
    """Carrega as tabelas gold, executando o pipeline se necessário."""
    return ensure_gold_tables(load_settings(), DataLayout.default())


def plot_indicators(panel: pl.DataFrame, columns: list[str]) -> go.Figure:
    """Um subgráfico por série selecionada, com eixo de tempo compartilhado."""
    labels = [f"{SERIES_OPTIONS[col][0]} ({SERIES_OPTIONS[col][1]})" for col in columns]
    fig = make_subplots(
        rows=len(columns), cols=1, shared_xaxes=True, subplot_titles=labels, vertical_spacing=0.08
    )
    for row, col in enumerate(columns, start=1):
        fig.add_trace(
            go.Scatter(
                x=panel["month"].to_list(),
                y=panel[col].to_list(),
                mode="lines",
                line={"color": COLORS["line"]},
                name=SERIES_OPTIONS[col][0],
            ),
            row=row,
            col=1,
        )
    fig.update_layout(height=280 * len(columns), showlegend=False, margin={"t": 40})
    return fig


def plot_forecast_vs_realized(errors: pl.DataFrame, horizon: int) -> go.Figure:
    """Mediana projetada pelo Focus (horizonte escolhido) contra o IPCA realizado."""
    data = errors.filter(pl.col("horizon") == horizon).sort("reference_month")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data["reference_month"].to_list(),
            y=data["realized"].to_list(),
            name="IPCA realizado",
            line={"color": COLORS["realized"]},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data["reference_month"].to_list(),
            y=data["forecast"].to_list(),
            name=f"Focus (mediana, h={horizon})",
            line={"color": COLORS["forecast"], "dash": "dot"},
        )
    )
    fig.update_layout(
        yaxis_title="IPCA mensal (%)", xaxis_title="Mês de referência", hovermode="x unified"
    )
    return fig


def plot_metric_by_horizon(summary: pl.DataFrame, value: str, ci: str, title: str) -> go.Figure:
    """Barras de uma métrica por horizonte, com barras de erro de IC 95%."""
    fig = go.Figure(
        go.Bar(
            x=summary["horizon"].to_list(),
            y=summary[value].to_list(),
            error_y={"type": "data", "array": summary[ci].fill_null(0).to_list()},
            marker_color=COLORS["line"],
        )
    )
    fig.update_layout(title=title, xaxis_title="Horizonte (meses à frente)", yaxis_title="p.p.")
    return fig


def render_indicators_tab(panel: pl.DataFrame, columns: list[str]) -> None:
    """Aba de indicadores macro."""
    if not columns:
        st.info("Selecione ao menos uma série na barra lateral.")
        return
    st.plotly_chart(plot_indicators(panel, columns), use_container_width=True)
    with st.expander("Ver dados"):
        st.dataframe(panel.select("month", *columns), use_container_width=True)


def render_focus_tab(errors: pl.DataFrame) -> None:
    """Aba de erro de projeção do Focus."""
    if errors.is_empty():
        st.warning("Sem projeções do Focus com IPCA realizado no período selecionado.")
        return
    summary = summarize_errors(errors)
    horizons = sorted(summary["horizon"].to_list())
    horizon = st.select_slider(
        "Horizonte da projeção (meses à frente)", options=horizons, value=horizons[0]
    )
    horizon = cast(int, horizon)

    st.plotly_chart(plot_forecast_vs_realized(errors, horizon), use_container_width=True)
    left, right = st.columns(2)
    left.plotly_chart(
        plot_metric_by_horizon(
            summary, "bias_pp", "bias_ci95_pp", "Viés (previsto − realizado), IC 95%"
        ),
        use_container_width=True,
    )
    right.plotly_chart(
        plot_metric_by_horizon(summary, "mae_pp", "mae_ci95_pp", "Erro absoluto médio, IC 95%"),
        use_container_width=True,
    )
    st.subheader("Resumo por horizonte (p.p. do IPCA mensal)")
    st.dataframe(summary, use_container_width=True)
    st.caption(
        "Viés positivo = o Focus superestima o IPCA. IC 95% por aproximação normal; "
        "erros de meses vizinhos são autocorrelacionados, então o IC tende a ser otimista."
    )


def render_about_tab() -> None:
    """Aba com metodologia e limitações."""
    st.markdown(
        """
**Fontes (Banco Central do Brasil)**: SGS 432 (meta Selic), 433 (IPCA mensal) e 1 (dólar venda);
Expectativas de Mercado (Focus), projeções mensais de IPCA.

**Metodologia do erro do Focus**: para cada mês de referência e horizonte *h* (meses entre a
pesquisa e o mês projetado) usa-se a última pesquisa do mês correspondente. Erro = mediana
projetada − IPCA realizado (p.p.). Viés = média do erro; MAE = média do erro absoluto.

**Limitações**: o IPCA realizado é o valor atual (pode diferir do divulgado na época);
o último mês das séries pode estar incompleto; IC desconsidera autocorrelação dos erros.
"""
    )


def main() -> None:
    """Monta a página: filtros na barra lateral e três abas."""
    st.title("📈 Painel Macro — Banco Central do Brasil")
    tables = load_tables()
    panel = tables[GOLD_PANEL]
    errors = tables[GOLD_FOCUS_ERRORS]

    min_month = cast(date, panel["month"].min())
    max_month = cast(date, panel["month"].max())
    default_start = max(min_month, date(max_month.year - 10, max_month.month, 1))
    with st.sidebar:
        st.header("Filtros")
        start, end = st.slider(
            "Período",
            min_value=min_month,
            max_value=max_month,
            value=(default_start, max_month),
            format="MM/YYYY",
        )
        columns = st.multiselect(
            "Séries",
            options=list(SERIES_OPTIONS),
            default=DEFAULT_SERIES,
            format_func=lambda col: f"{SERIES_OPTIONS[col][0]} ({SERIES_OPTIONS[col][1]})",
        )

    panel_period = panel.filter(pl.col("month").is_between(start, end))
    errors_period = errors.filter(pl.col("reference_month").is_between(start, end))

    tab_indicators, tab_focus, tab_about = st.tabs(
        ["Indicadores", "Focus: erro de projeção", "Sobre"]
    )
    with tab_indicators:
        render_indicators_tab(panel_period, columns)
    with tab_focus:
        render_focus_tab(errors_period)
    with tab_about:
        render_about_tab()


main()
