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
