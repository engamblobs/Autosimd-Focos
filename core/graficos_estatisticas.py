# -*- coding: utf-8 -*-
"""Gráficos das estatísticas do município (docs/10 §5).

Duas versões com a mesma informação e as mesmas cores do Programa Queimadas/INPE:
- estáticas (matplotlib): PDF e PNGs do pacote — quem chama fecha as figuras;
- interativas (Altair): tela, com dica ao passar o mouse, zoom e legenda clicável.
"""

import altair as alt
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from core.estatisticas import MESES_CURTOS, UNIDADES, EstatisticasMunicipio  # noqa: E402
from core.texto import fmt_inteiro, fmt_milhar_eixo  # noqa: E402

AZUL_REFERENCIA = "#2F6FE4"
ROXO_ANTERIOR = "#6A3DE8"
VERMELHO_MAXIMO = "#E53935"
LARANJA_MEDIA = "#F59E0B"
VERDE_MINIMO = "#10A36B"
CINZA_ANOS = "#B8B8B8"
CINZA_FAIXA = "#DDDDDD"
TITULOS_COMPARATIVO = {"mensal": "Comparativo mensal", "semanal": "Comparativo semanal",
                       "semestre1": "Comparativo 1º semestre", "semestre2": "Comparativo 2º semestre"}
PASSO_ROTULOS = {"mensal": 1, "semanal": 4, "semestre1": 15, "semestre2": 15}


# -------------------------------------------------------------- Estáticos

def grafico_comparativo(est: EstatisticasMunicipio, unidade: str):
    """Barras do ano de referência + linhas de máximo, média e mínimo dos demais anos."""
    estatisticas = est.parametros.series_comparativo
    dados = est.comparativos[unidade]
    rotulo, _ = UNIDADES[unidade]
    x = np.arange(len(dados))
    fig, ax = plt.subplots(figsize=(10, 3.6), dpi=150)
    ax.bar(x, dados["referencia"].fillna(0), color=AZUL_REFERENCIA, width=0.6 if unidade == "mensal" else 0.8,
           label=str(est.ano_referencia), zorder=3)
    for nome, coluna, cor in (("Máximo", "maximo", VERMELHO_MAXIMO), ("Média", "media", LARANJA_MEDIA),
                              ("Mínimo", "minimo", VERDE_MINIMO)):
        if nome in estatisticas:
            ax.plot(x, dados[coluna], color=cor, marker="o" if unidade in ("mensal", "semanal") else None,
                    markersize=3 if unidade != "mensal" else 4, linewidth=1.6 if unidade != "semestre1" else 1.2, label=f"{nome} ({est.anos_estatistica[0]}–{est.anos_estatistica[-1]})"
                    if est.anos_estatistica else nome, zorder=4)
    rotulos = dados["rotulo"].tolist()
    passo = PASSO_ROTULOS[unidade]
    ax.set_xticks(x[::passo])
    ax.set_xticklabels(rotulos[::passo], fontsize=8)
    ax.set_xlabel(rotulo, fontsize=8)
    ax.set_ylabel("Nº de focos", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.grid(axis="y", linestyle=":", alpha=0.5, zorder=0)
    ax.set_title(f"{TITULOS_COMPARATIVO[unidade]}: {est.municipio.title()} — {est.ano_referencia} × mínimo, "
                 "média e máximo", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7.5, frameon=False, ncol=4, loc="upper left")
    fig.tight_layout()
    return fig


def grafico_acumulado(est: EstatisticasMunicipio):
    """Total acumulado no ano, mês a mês: uma linha por ano, faixa de percentis, média e destaques."""
    p = est.parametros
    mostrar_anos = p.mostrar_anos
    x = np.arange(12)
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=150)
    if mostrar_anos:
        for ano in est.anos_estatistica:
            ax.plot(x, est.acumulado.loc[ano], color=CINZA_ANOS, linewidth=0.7, alpha=0.7, zorder=1)
    faixa = est.faixa_acumulado
    ax.fill_between(x, faixa["inferior"], faixa["superior"], color=CINZA_FAIXA, alpha=0.8, zorder=0,
                    label=f"p{p.percentil_inferior}–p{p.percentil_superior}")
    ax.plot(x, faixa["media"], color=LARANJA_MEDIA, linewidth=2, label="Média", zorder=3)
    for ano, cor, estilo, nome in _destaques(est):
        ax.plot(x, est.acumulado.loc[ano], color=cor, linewidth=2.2 if estilo == "-" else 1.6, linestyle=estilo,
                label=nome, zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels(MESES_CURTOS, fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.set_ylabel("Focos acumulados no ano", fontsize=8)
    ax.grid(linestyle=":", alpha=0.5)
    ax.set_title(f"Cumulativo mensal: {est.municipio.title()} ({est.ano_inicio}–{est.ano_fim})",
                 fontsize=10, fontweight="bold")
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="upper left")
    fig.tight_layout()
    return fig


def _destaques(est: EstatisticasMunicipio) -> list[tuple[int, str, str, str]]:
    """(ano, cor, estilo, legenda) das linhas destacadas no acumulado."""
    linhas = [(est.ano_referencia, AZUL_REFERENCIA, "-", f"{est.ano_referencia} (referência)")]
    if est.ano_anterior:
        linhas.append((est.ano_anterior, ROXO_ANTERIOR, "-", f"{est.ano_anterior} (anterior)"))
    if est.ano_mais_intenso:
        linhas.append((est.ano_mais_intenso, VERMELHO_MAXIMO, "--", f"{est.ano_mais_intenso} (mais intenso)"))
    if est.ano_menos_intenso and est.ano_menos_intenso != est.ano_mais_intenso:
        linhas.append((est.ano_menos_intenso, VERDE_MINIMO, "--", f"{est.ano_menos_intenso} (menos intenso)"))
    return linhas


def grafico_sazonalidade(est: EstatisticasMunicipio):
    """Sazonalidade mensal: média dos anos do período (barras), faixa p10–p90 e o ano de referência (linha)."""
    p = est.parametros
    meses = est.mensal[list(range(1, 13))]
    base = meses.loc[[a for a in est.anos_estatistica if a in meses.index]]
    media = base.mean()
    inferior = base.quantile(p.percentil_inferior / 100)
    superior = base.quantile(p.percentil_superior / 100)
    referencia = meses.loc[est.ano_referencia] if est.ano_referencia in meses.index else None
    x = np.arange(12)
    fig, ax = plt.subplots(figsize=(10, 3.4), dpi=150)
    anos = f"{est.anos_estatistica[0]}–{est.anos_estatistica[-1]}" if est.anos_estatistica else ""
    ax.bar(x, media.fillna(0), color="#E53935", alpha=0.8, edgecolor="#B71C1C", width=0.6,
           label=f"Média mensal ({anos})", zorder=2)
    ax.errorbar(x, media.fillna(0), yerr=[(media - inferior).clip(lower=0).fillna(0),
                                          (superior - media).clip(lower=0).fillna(0)],
                fmt="none", ecolor="#424242", elinewidth=1.1, capsize=4, zorder=3,
                label=f"p{p.percentil_inferior}–p{p.percentil_superior}")
    if referencia is not None:
        ax.plot(x, referencia, color=AZUL_REFERENCIA, marker="o", linewidth=2, zorder=4,
                label=str(est.ano_referencia))
    for i, valor in enumerate(media):
        if valor == valor and valor > 0:
            ax.annotate(fmt_inteiro(round(valor)), xy=(i, valor), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7, fontweight="bold", zorder=5)
    ax.set_xticks(x)
    ax.set_xticklabels(MESES_CURTOS, fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.set_ylabel("Focos no mês", fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.4, zorder=0)
    ax.set_title(f"Sazonalidade Mensal de Focos de Calor — média, p{p.percentil_inferior}–p{p.percentil_superior} "
                 f"e {est.ano_referencia}", fontsize=11, fontweight="bold")
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    return fig


def figuras_estatisticas(est: EstatisticasMunicipio) -> dict:
    return {
        "sazonalidade": grafico_sazonalidade(est),
        "comparativo_mensal": grafico_comparativo(est, "mensal"),
        "comparativo_semanal": grafico_comparativo(est, "semanal"),
        "comparativo_semestre1": grafico_comparativo(est, "semestre1"),
        "comparativo_semestre2": grafico_comparativo(est, "semestre2"),
        "acumulado_mensal": grafico_acumulado(est),
    }


# ------------------------------------------------------------- Interativos

def interativo_comparativo(est: EstatisticasMunicipio, unidade: str) -> alt.LayerChart:
    estatisticas = est.parametros.series_comparativo
    dados = est.comparativos[unidade].copy()
    rotulo, _ = UNIDADES[unidade]
    ordem = dados["rotulo"].tolist()
    eixo_x = alt.X("rotulo:N", sort=ordem, title=rotulo,
                   axis=alt.Axis(labelAngle=0 if unidade == "mensal" else -45,
                                 values=ordem[::PASSO_ROTULOS[unidade]]))
    ano = str(est.ano_referencia)

    barras = alt.Chart(dados).mark_bar(color=AZUL_REFERENCIA, opacity=0.9).encode(
        x=eixo_x, y=alt.Y("referencia:Q", title="Nº de focos", axis=alt.Axis(format="d")),
        tooltip=[alt.Tooltip("rotulo:N", title=rotulo), alt.Tooltip("referencia:Q", title=ano, format=".0f")],
    )
    longo = dados.melt(id_vars=["rotulo"], value_vars=["maximo", "media", "minimo"], var_name="serie",
                       value_name="valor")
    longo["serie"] = longo["serie"].map({"maximo": "Máximo", "media": "Média", "minimo": "Mínimo"})
    longo = longo[longo["serie"].isin(estatisticas)]
    legenda = alt.selection_point(fields=["serie"], bind="legend")
    linhas = alt.Chart(longo).mark_line(point=unidade in ("mensal", "semanal")).encode(
        x=eixo_x, y="valor:Q",
        color=alt.Color("serie:N", title=f"{ano} × demais anos",
                        scale=alt.Scale(domain=["Máximo", "Média", "Mínimo"],
                                        range=[VERMELHO_MAXIMO, LARANJA_MEDIA, VERDE_MINIMO])),
        opacity=alt.condition(legenda, alt.value(1), alt.value(0.12)),
        tooltip=[alt.Tooltip("rotulo:N", title=rotulo), alt.Tooltip("serie:N", title="Série"),
                 alt.Tooltip("valor:Q", title="Focos", format=".0f")],
    ).add_params(legenda)
    return (barras + linhas).properties(
        title=f"{TITULOS_COMPARATIVO[unidade]}: {est.municipio.title()} — barras = {ano}", height=320,
    ).interactive(bind_y=False)


def interativo_acumulado(est: EstatisticasMunicipio) -> alt.LayerChart:
    p = est.parametros
    mostrar_anos = p.mostrar_anos
    acumulado = est.acumulado.copy()
    acumulado.columns = MESES_CURTOS
    longo = (acumulado.reset_index().melt(id_vars="ano", var_name="mes", value_name="valor").dropna())
    eixo_x = alt.X("mes:N", sort=MESES_CURTOS, title="Mês", axis=alt.Axis(labelAngle=0))
    camadas = []

    faixa = est.faixa_acumulado.assign(mes=MESES_CURTOS)
    camadas.append(alt.Chart(faixa).mark_area(color=CINZA_FAIXA, opacity=0.8).encode(
        x=eixo_x, y=alt.Y("inferior:Q", title="Focos acumulados no ano", axis=alt.Axis(format="d")), y2="superior:Q",
        tooltip=[alt.Tooltip("mes:N", title="Mês"),
                 alt.Tooltip("inferior:Q", title=f"p{p.percentil_inferior}", format=".0f"),
                 alt.Tooltip("superior:Q", title=f"p{p.percentil_superior}", format=".0f")],
    ))
    if mostrar_anos:
        demais = longo[longo["ano"].isin(est.anos_estatistica)]
        camadas.append(alt.Chart(demais).mark_line(color=CINZA_ANOS, strokeWidth=0.8, opacity=0.7).encode(
            x=eixo_x, y="valor:Q", detail="ano:N",
            tooltip=[alt.Tooltip("ano:N", title="Ano"), alt.Tooltip("mes:N", title="Mês"),
                     alt.Tooltip("valor:Q", title="Acumulado", format=".0f")],
        ))

    series = [faixa.assign(serie="Média", valor=faixa["media"])[["mes", "serie", "valor"]]]
    nomes, cores = ["Média"], [LARANJA_MEDIA]
    for ano, cor, _, nome in _destaques(est):
        series.append(longo[longo["ano"] == ano].assign(serie=nome)[["mes", "serie", "valor"]])
        nomes.append(nome)
        cores.append(cor)
    destaque = pd.concat(series)
    legenda = alt.selection_point(fields=["serie"], bind="legend")
    camadas.append(alt.Chart(destaque).mark_line(strokeWidth=2.4, point=True).encode(
        x=eixo_x, y="valor:Q",
        color=alt.Color("serie:N", title=f"Faixa cinza = p{p.percentil_inferior}–p{p.percentil_superior}",
                        scale=alt.Scale(domain=nomes, range=cores), sort=nomes),
        opacity=alt.condition(legenda, alt.value(1), alt.value(0.1)),
        tooltip=[alt.Tooltip("serie:N", title="Série"), alt.Tooltip("mes:N", title="Mês"),
                 alt.Tooltip("valor:Q", title="Acumulado", format=".0f")],
    ).add_params(legenda))
    return alt.layer(*camadas).properties(
        title=f"Cumulativo mensal: {est.municipio.title()} ({est.ano_inicio}–{est.ano_fim})", height=380,
    ).interactive(bind_y=False)


SERIES_NOWCAST = {"maximo": "Máximo do dia", "media": "Média do dia", "media_janela": "Média ±3 dias (7 dias)"}


def grafico_nowcast(nowcast):
    """Versão estática do gráfico do cenário atual (PDF e PNG)."""
    dados = nowcast.serie
    x = np.arange(len(dados))
    fig, ax = plt.subplots(figsize=(10, 3.4), dpi=150)
    ax.bar(x, dados["focos"], color=AZUL_REFERENCIA, width=0.7, label=str(nowcast.ultimo_dia.year), zorder=3)
    for coluna, cor, estilo in (("maximo", VERMELHO_MAXIMO, "-"), ("media", LARANJA_MEDIA, "-"),
                                ("media_janela", VERDE_MINIMO, "--")):
        ax.plot(x, dados[coluna], color=cor, linestyle=estilo, marker="o", markersize=2.5, linewidth=1.5,
                label=SERIES_NOWCAST[coluna], zorder=4)
    ax.set_xticks(x[::2])
    ax.set_xticklabels([d.strftime("%d/%m") for d in dados["data"]][::2], rotation=45, ha="right", fontsize=7)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_milhar_eixo))
    ax.set_ylabel("Focos no dia", fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.5, zorder=0)
    periodo = (f" — anos anteriores: {nowcast.anos_comparados[0]}–{nowcast.anos_comparados[-1]}"
               if nowcast.anos_comparados else "")
    ax.set_title(f"Focos por dia nos últimos {len(dados)} dias — {nowcast.municipio.title()}{periodo}",
                 fontsize=10, fontweight="bold")
    ax.legend(fontsize=7.5, frameon=False, ncol=4, loc="upper left")
    fig.tight_layout()
    return fig


def interativo_nowcast(nowcast) -> alt.LayerChart:
    """Focos por dia nos últimos 30 dias × média e máximo do mesmo dia nos anos anteriores."""
    dados = nowcast.serie.assign(dia=[d.strftime("%d/%m") for d in nowcast.serie["data"]]).drop(columns="data")
    ordem = dados["dia"].tolist()
    eixo_x = alt.X("dia:N", sort=ordem, title="Dia", axis=alt.Axis(labelAngle=-45))
    rotulo_ano = str(nowcast.ultimo_dia.year)
    barras = alt.Chart(dados).mark_bar(color=AZUL_REFERENCIA, opacity=0.9).encode(
        x=eixo_x, y=alt.Y("focos:Q", title="Nº de focos", axis=alt.Axis(format="d")),
        tooltip=[alt.Tooltip("dia:N", title="Dia"), alt.Tooltip("focos:Q", title=rotulo_ano, format=".0f")],
    )
    longo = dados.melt(id_vars=["dia"], value_vars=["maximo", "media", "media_janela"], var_name="serie",
                       value_name="valor")
    longo["serie"] = longo["serie"].map(SERIES_NOWCAST)
    periodo = (f"{nowcast.anos_comparados[0]}–{nowcast.anos_comparados[-1]}" if nowcast.anos_comparados else "")
    legenda = alt.selection_point(fields=["serie"], bind="legend")
    linhas = alt.Chart(longo).mark_line(point=True).encode(
        x=eixo_x, y="valor:Q",
        color=alt.Color("serie:N", title=f"Anos anteriores ({periodo})",
                        scale=alt.Scale(domain=list(SERIES_NOWCAST.values()),
                                        range=[VERMELHO_MAXIMO, LARANJA_MEDIA, VERDE_MINIMO])),
        opacity=alt.condition(legenda, alt.value(1), alt.value(0.12)),
        tooltip=[alt.Tooltip("dia:N", title="Dia"), alt.Tooltip("serie:N", title="Série"),
                 alt.Tooltip("valor:Q", title="Focos", format=".1f")],
    ).add_params(legenda)
    return (barras + linhas).properties(
        title=f"Focos por dia nos últimos {len(dados)} dias — {nowcast.municipio.title()} (barras = {rotulo_ano})",
        height=300,
    ).interactive(bind_y=False)
