# -*- coding: utf-8 -*-
"""Gráficos do diagnóstico (docs/10 §2), em matplotlib. Quem chama fecha as figuras."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from core.texto import fmt_milhar_eixo  # noqa: E402

VERMELHO = "#b52b27"
AZUL_CLARO = "#a6b1e1"
CINZA_TENDENCIA = "#333333"


def grafico_top_estado(top: list[tuple[str, int]], municipio: str):
    """Barras horizontais dos municípios com mais focos no estado no período; o analisado em vermelho."""
    nomes = [m for m, _ in top]
    valores = [n for _, n in top]
    cores = [VERMELHO if m.lower() == municipio.lower() else AZUL_CLARO for m in nomes]
    fig, ax = plt.subplots(figsize=(5, 2.8), dpi=150)
    ax.barh(nomes[::-1], valores[::-1], color=cores[::-1])
    ax.set_title(f"Top {len(top)} Focos Historicamente (Estado)", fontsize=10, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)
    ax.xaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    fig.tight_layout()
    return fig


def grafico_evolucao_tendencia(serie: dict[int, int]):
    """Focos por ano com reta de tendência (mínimos quadrados)."""
    anos = [str(a) for a in serie]
    x = np.arange(len(anos))
    y = np.array(list(serie.values()))
    fig, ax = plt.subplots(figsize=(5, 2.8), dpi=150)
    ax.plot(x, y, marker="o", markersize=4, color=VERMELHO, linewidth=2, label="Focos")
    if len(x) > 1:
        ax.plot(x, np.poly1d(np.polyfit(x, y, 1))(x), color=CINZA_TENDENCIA, linestyle="--", linewidth=1.2,
                label="Tendência")
    ax.set_title(f"Evolução Anual Histórica ({anos[0]}-{anos[-1]})", fontsize=10, fontweight="bold")
    ax.set_xticks(x[::2])
    ax.set_xticklabels(anos[::2], rotation=45, ha="right", fontsize=7.5)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.legend(fontsize=7.5, loc="upper right", frameon=False)
    fig.tight_layout()
    return fig


# ------------------------------------------------- Cenário atual do estado (docs/10 §8)

AZUL_SEMANA = "#90CAF9"
AZUL_24H = "#1565C0"


def grafico_municipios_cenario(municipios, n: int = 15):
    """Barras horizontais dos municípios com mais focos na semana, com as últimas 24 h por cima."""
    top = municipios.sort_values(["Última semana", "Últimas 24 h"], ascending=False).head(n)
    fig, ax = plt.subplots(figsize=(10, 0.28 * max(len(top), 4) + 1.2), dpi=150)
    nomes = top["Município"].tolist()[::-1]
    ax.barh(nomes, top["Última semana"].tolist()[::-1], color=AZUL_SEMANA, label="Última semana")
    ax.barh(nomes, top["Últimas 24 h"].tolist()[::-1], color=AZUL_24H, height=0.45, label="Últimas 24 h")
    for y, valor in enumerate(top["Última semana"].tolist()[::-1]):
        ax.text(valor, y, f" {valor}", va="center", fontsize=7)
    ax.set_title(f"Municípios com mais focos na última semana (top {len(top)})", fontsize=10, fontweight="bold")
    ax.tick_params(axis="both", labelsize=7.5)
    ax.xaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    return fig


def grafico_regioes_cenario(focos_semana, dia, tipo_regiao: str):
    """Focos da semana por região: barras com a parte das últimas 24 h."""
    semana = focos_semana.groupby("regiao").size()
    ultimas = focos_semana[focos_semana["data"] == dia.isoformat()].groupby("regiao").size()
    ordem = semana.sort_values().index
    fig, ax = plt.subplots(figsize=(10, 0.3 * max(len(ordem), 4) + 1.2), dpi=150)
    ax.barh(ordem, semana[ordem], color=AZUL_SEMANA, label="Última semana")
    ax.barh(ordem, ultimas.reindex(ordem, fill_value=0), color=AZUL_24H, height=0.45, label="Últimas 24 h")
    for y, valor in enumerate(semana[ordem]):
        ax.text(valor, y, f" {valor}", va="center", fontsize=7)
    ax.set_title(f"Focos da última semana por {tipo_regiao}", fontsize=10, fontweight="bold")
    ax.tick_params(axis="both", labelsize=7.5)
    ax.xaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    return fig


def grafico_dias_areas_cenario(focos_semana, inicio, dias: int = 7):
    """Focos por dia da semana, empilhados: em UC, em TI e fora de áreas protegidas."""
    from datetime import timedelta

    datas = [(inicio + timedelta(days=k)).isoformat() for k in range(dias)]
    uc = focos_semana["UC"] != "NONE"
    ti = (focos_semana["TI"] != "NONE") & ~uc
    grupos = (("Fora de áreas protegidas", ~uc & ~ti, "#B0BEC5"), ("Em Unidade de Conservação", uc, "#2E7D32"),
              ("Em Terra Indígena", ti, "#EF6C00"))
    x = np.arange(dias)
    base = np.zeros(dias)
    fig, ax = plt.subplots(figsize=(10, 3.0), dpi=150)
    for rotulo, mascara, cor in grupos:
        valores = focos_semana[mascara].groupby("data").size().reindex(datas, fill_value=0).to_numpy()
        ax.bar(x, valores, bottom=base, color=cor, width=0.6, label=rotulo, zorder=3)
        base = base + valores
    for xi, total in zip(x, base):
        ax.text(xi, total, f"{int(total)}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{d[8:10]}/{d[5:7]}" for d in datas], fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.set_ylabel("Focos no dia", fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.5, zorder=0)
    ax.set_title("Focos por dia na última semana — dentro e fora de áreas protegidas", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="upper left")
    ax.set_ylim(0, max(base.max(), 1) * 1.25)
    fig.tight_layout()
    return fig
