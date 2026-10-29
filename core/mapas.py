# -*- coding: utf-8 -*-
"""Mapas do diagnóstico (docs/10 §3): densidade de kernel, recorrência, migração trimestral e cenário atual.

Mapas 1, 2 e 4: densidade de kernel dos focos (``core/kernel.py``) com cada foco marcado por uma
pequena cruz preta. Mapa 3: recorrência na grade proporcional ao território, ajustada à latitude (``core/grade.py``).
Todos desenham o limite oficial do território (IBGE, CNUC ou FUNAI). Quem chama fecha as figuras.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from core.config import KERNEL_MAX_CRUZES, TAMANHO_CELULA_KM  # noqa: E402
from core.fundo_satelite import (  # noqa: E402
    CREDITO_SATELITE, lonlat_para_mercator, mercator_para_lat, mercator_para_lon, mosaico,
)
from core.grade import Grade, fmt_km, grade_do_territorio, nota_grade, recorrencia  # noqa: E402
from core.kernel import densidade_kernel  # noqa: E402
from core.territorios import CORES_AREAS_PROTEGIDAS, poligonos_de  # noqa: E402
from core.texto import fmt_inteiro, fmt_numero  # noqa: E402

COR_LIMITE = "#1E88E5"
FUNDO = "#F8F9FA"
CMAP_KERNEL = LinearSegmentedColormap.from_list(
    "kernel_focos", ["#FFF5B8", "#FECC5C", "#FD8D3C", "#F03B20", "#BD0026", "#5C0011"])
TRIMESTRES = {
    "1º Trimestre (Jan-Mar)": (1, 2, 3),
    "2º Trimestre (Abr-Jun)": (4, 5, 6),
    "3º Trimestre (Jul-Set)": (7, 8, 9),
    "4º Trimestre (Out-Dez)": (10, 11, 12),
}
LIMIAR_KERNEL = 0.02          # densidades abaixo de 2% do máximo ficam transparentes
NOTA_KERNEL = ("Densidade de kernel gaussiano (desvio de {desvio} km, células de {celula} km), em focos por "
               "100 km², recortada pelo limite do território; {cruzes}.")
MAX_CRUZES = KERNEL_MAX_CRUZES   # acima disso as cruzes viram um borrão e escondem o kernel (core/config.py)
ESTILO_CRUZES = {"marker": "+", "c": "#333333", "s": 5, "linewidths": 0.3, "alpha": 0.35}


def desenhar_limite(ax, geom, cor: str = COR_LIMITE, espessura: float = 1.5, transparencia: float = 0.05):
    """Contorno (e furos tracejados) do território; ajusta a extensão do eixo com 5% de margem."""
    if geom is None:
        return None
    for poligono in poligonos_de(geom):
        x, y = poligono.exterior.xy
        ax.plot(x, y, color=cor, linewidth=espessura, zorder=5)
        if transparencia > 0:
            ax.fill(x, y, color=cor, alpha=transparencia, zorder=1)
        for furo in poligono.interiors:
            xi, yi = furo.xy
            ax.plot(xi, yi, color=cor, linewidth=espessura * 0.8, linestyle="--", zorder=5)
    min_x, min_y, max_x, max_y = geom.bounds
    margem_x, margem_y = (max_x - min_x) * 0.05, (max_y - min_y) * 0.05
    ax.set_xlim(min_x - margem_x, max_x + margem_x)
    ax.set_ylim(min_y - margem_y, max_y + margem_y)
    ax.set_aspect(1 / np.cos(np.radians((min_y + max_y) / 2)), adjustable="box")   # proporção real na latitude
    return geom.bounds


def _grade_colorida(ax, grade: Grade, valores, cmap, fig, rotulo: str, encolher: float = 0.8):
    mascarado = np.ma.masked_where(valores == 0, valores)
    x, y = np.meshgrid(grade.x, grade.y)
    malha = ax.pcolormesh(x, y, mascarado.T, cmap=cmap, zorder=3, alpha=0.85, edgecolors="white", linewidth=0.3)
    barra = fig.colorbar(malha, ax=ax, orientation="vertical", pad=0.02, shrink=encolher)
    barra.set_label(rotulo, fontsize=8 if encolher >= 0.8 else 7)


def _kernel(ax, fig, focos, poligono, limites, encolher: float = 0.8):
    """Densidade de kernel + cruzes dos focos; devolve o kernel (ou None sem focos)."""
    if not len(focos) or limites is None:
        return None
    k = densidade_kernel(focos["lon"], focos["lat"], limites, poligono)
    por_100km2 = k.densidade * 100
    maximo = np.nanmax(por_100km2) if np.isfinite(por_100km2).any() else 0
    mascarado = np.ma.masked_where(~np.isfinite(por_100km2) | (por_100km2 < LIMIAR_KERNEL * maximo), por_100km2)
    x, y = np.meshgrid(k.x, k.y)
    malha = ax.pcolormesh(x, y, mascarado, cmap=CMAP_KERNEL, zorder=2, alpha=0.85, shading="flat",
                          rasterized=True)
    barra = fig.colorbar(malha, ax=ax, orientation="vertical", pad=0.02, shrink=encolher)
    barra.set_label("Densidade de focos (por 100 km²)", fontsize=8 if encolher >= 0.8 else 7)
    k.focos_marcados = len(focos) <= MAX_CRUZES
    if k.focos_marcados:
        ax.scatter(focos["lon"], focos["lat"], zorder=4, **ESTILO_CRUZES)
    return k


def _nota(fig, texto: str, centro: bool = False):
    fig.text(0.5 if centro else 0.01, 0.005, texto, fontsize=6.5, color="#555555", ha="center" if centro else "left",
             va="bottom", wrap=True)


def _texto_kernel(k) -> str:
    cruzes = ("+ cinza = cada foco" if getattr(k, "focos_marcados", True)
              else f"focos não marcados individualmente (mais de {fmt_inteiro(MAX_CRUZES)})")
    return NOTA_KERNEL.format(desvio=fmt_numero(k.desvio_km), celula=fmt_numero(k.celula_km, 1), cruzes=cruzes)


def _sem_dados(ax, texto: str):
    ax.text(0.5, 0.5, texto, ha="center", va="center", transform=ax.transAxes, fontsize=9)


def _acabamento(ax):
    ax.set_facecolor(FUNDO)
    ax.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=0)


# ------------------------------------------------------------------- Mapas

def _desenhar_areas_protegidas(ax, ax_legenda, areas: list[dict], linhas_legenda: int):
    for area in areas:
        cor = CORES_AREAS_PROTEGIDAS[area["tipo"]]
        for parte in poligonos_de(area["recorte"]):
            x, y = parte.exterior.xy
            ax.plot(x, y, color=cor, linewidth=1.0, zorder=3.5, linestyle="-" if area["tipo"] == "UC" else "--")
        ponto = area["recorte"].representative_point()
        ax.text(ponto.x, ponto.y, str(area["num"]), fontsize=7, fontweight="bold", color=cor,
                ha="center", va="center", zorder=6,
                bbox={"boxstyle": "circle,pad=0.2", "fc": "white", "ec": cor, "lw": 0.8})
    ax.legend(handles=[
        Patch(facecolor="none", edgecolor=CORES_AREAS_PROTEGIDAS["UC"], label="Unidade de Conservação (UC)"),
        Patch(facecolor="none", edgecolor=CORES_AREAS_PROTEGIDAS["TI"], linestyle="--", label="Terra Indígena (TI)"),
        Line2D([], [], marker="+", color="none", markeredgecolor="#333333", markersize=5, label="Foco de Calor"),
    ], loc="best", fontsize=7, framealpha=0.9)

    ax_legenda.axis("off")
    ax_legenda.set_title("Áreas protegidas no território (área sobreposta ao município)",
                         fontsize=8, fontweight="bold", loc="left")
    for i, area in enumerate(areas):
        coluna, linha = divmod(i, linhas_legenda)
        nome = area["nome"] if len(area["nome"]) <= 48 else area["nome"][:47] + "…"
        area_txt = f" — {fmt_numero(area['area_km2'])} km²" if area["area_km2"] else ""
        ax_legenda.text(0.5 * coluna, 1 - (linha + 1) / (linhas_legenda + 0.5),
                        f"{area['num']}. [{area['tipo']}] {nome}{area_txt}", fontsize=6.5,
                        color=CORES_AREAS_PROTEGIDAS[area["tipo"]], transform=ax_legenda.transAxes, va="center")


def mapa_dispersao(focos_ano, poligono, nome: str, ano_fim: int, areas: list[dict] | None = None,
                   numero: str = "1. "):
    """Mapa 1: densidade de kernel dos focos do ano final; com UCs/TIs sobrepostas ao território, quando houver."""
    if areas:
        linhas_legenda = (len(areas) + 1) // 2
        altura_legenda = 0.45 + 0.2 * linhas_legenda
        fig, (ax, ax_legenda) = plt.subplots(2, 1, figsize=(9, 7 + altura_legenda), dpi=180,
                                             gridspec_kw={"height_ratios": [7, altura_legenda]})
    else:
        fig, ax = plt.subplots(figsize=(9, 7), dpi=180)
    _acabamento(ax)
    limites = desenhar_limite(ax, poligono)
    if areas:
        _desenhar_areas_protegidas(ax, ax_legenda, areas, linhas_legenda)
    k = _kernel(ax, fig, focos_ano, poligono, limites)
    if k is not None:
        ax.set_title(f"{numero}Densidade dos Focos em {ano_fim} — {nome} ({fmt_inteiro(len(focos_ano))} focos)",
                     fontsize=11, fontweight="bold")
    else:
        _sem_dados(ax, f"Sem focos em {ano_fim}")
        ax.set_title(f"{numero}Densidade dos Focos em {ano_fim}", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    if k is not None:
        _nota(fig, _texto_kernel(k))
    return fig


def mapa_densidade(focos, poligono, nome: str, ano_inicio: int, ano_fim: int):
    """Mapa 2: densidade de kernel dos focos acumulados no período."""
    fig, ax = plt.subplots(figsize=(9, 7), dpi=180)
    _acabamento(ax)
    limites = desenhar_limite(ax, poligono)
    k = _kernel(ax, fig, focos, poligono, limites)
    if k is None:
        _sem_dados(ax, f"Sem focos em {ano_inicio}-{ano_fim}")
    ax.set_title(f"2. Densidade Espacial Acumulada ({ano_inicio}-{ano_fim}) — {nome}", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    if k is not None:
        _nota(fig, _texto_kernel(k))
    return fig


def mapa_recorrencia(focos, poligono, ano_inicio: int, ano_fim: int):
    """Mapa 3: em quantos anos do período cada célula da grade (proporcional ao território) teve fogo."""
    fig, ax = plt.subplots(figsize=(9, 7), dpi=180)
    _acabamento(ax)
    limites = desenhar_limite(ax, poligono)
    grade = None
    if len(focos) and limites:
        grade = grade_do_territorio(limites)
        _grade_colorida(ax, grade, recorrencia(grade, focos["lon"], focos["lat"], focos["ano"]), "plasma", fig,
                        "Nº de Anos com Reincidência")
    else:
        _sem_dados(ax, f"Sem focos em {ano_inicio}-{ano_fim}")
    km = fmt_km(grade.tamanho_km if grade is not None else
                grade_do_territorio(limites).tamanho_km if limites else TAMANHO_CELULA_KM)
    ax.set_title(f"3. Recorrência Temporal dos Focos ({ano_inicio}-{ano_fim}) — Grade {km} × {km} km",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    if grade is not None:
        _nota(fig, nota_grade(grade))
    return fig


def mapa_trimestral(focos, poligono, nome: str, ano_inicio: int, ano_fim: int):
    """Mapa 4: densidade de kernel por trimestre (migração sazonal). None quando não há focos."""
    focos = focos[focos["mes"].between(1, 12)]
    if focos.empty:
        return None
    fig, eixos = plt.subplots(2, 2, figsize=(12, 10), dpi=180)
    ultimo = None
    for ax, (titulo, meses) in zip(eixos.flatten(), TRIMESTRES.items()):
        _acabamento(ax)
        limites = desenhar_limite(ax, poligono)
        no_trimestre = focos[focos["mes"].isin(meses)]
        k = _kernel(ax, fig, no_trimestre, poligono, limites, encolher=0.7)
        if k is not None:
            ultimo = k
            ax.set_title(f"{titulo} ({fmt_inteiro(len(no_trimestre))} focos)", fontsize=9, fontweight="bold")
        else:
            _sem_dados(ax, "Sem registros no trimestre")
            ax.set_title(titulo, fontsize=9, fontweight="bold")
    fig.suptitle(f"Migração Sazonal Trimestral dos Focos ({ano_inicio}-{ano_fim}) — {nome}",
                 fontsize=12, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    if ultimo is not None:
        _nota(fig, _texto_kernel(ultimo))
    return fig


# ------------------------------------------------------------- Cenário atual

CORES_IDADE = {"Último dia": "#FF1744", "1–2 dias antes": "#FF9100", "3–6 dias antes": "#FFEA00",
               "7–29 dias antes": "#E0E0E0"}
COR_LIMITE_SATELITE = "#00E5FF"
CORES_AREAS_SATELITE = {"UC": "#76FF03", "TI": "#FFAB40"}


def _em_mercator(geom):
    from shapely import transform
    return transform(geom, lambda xy: np.column_stack(lonlat_para_mercator(xy[:, 0], xy[:, 1])))


def mapa_recentes(recentes, poligono, nome: str, ultimo_dia, dias: int, areas: list[dict] | None = None,
                  fundo: bool | None = None):
    """Nowcast: focos dos últimos ``dias`` dias sobre imagem de satélite (Sentinel-2 cloudless), cor pela idade.

    Desenhado em Web Mercator (EPSG:3857) para encaixar nos tiles; os eixos mostram graus.
    Sem internet (ou ``fundo=False``), sai sem a imagem e com aviso.
    """
    from core import config
    fundo = config.FUNDO_SATELITE if fundo is None else fundo
    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    imagem = None
    if poligono is not None:
        geom = _em_mercator(poligono)
        min_x, min_y, max_x, max_y = geom.bounds
        margem_x, margem_y = (max_x - min_x) * 0.05, (max_y - min_y) * 0.05
        ax.set_xlim(min_x - margem_x, max_x + margem_x)
        ax.set_ylim(min_y - margem_y, max_y + margem_y)
        if fundo:
            lon0, lat0 = mercator_para_lon(min_x - margem_x), mercator_para_lat(min_y - margem_y)
            lon1, lat1 = mercator_para_lon(max_x + margem_x), mercator_para_lat(max_y + margem_y)
            imagem = mosaico((float(lon0), float(lat0), float(lon1), float(lat1)))
        if imagem is not None:
            ax.imshow(imagem[0], extent=imagem[1], origin="upper", zorder=0, interpolation="bilinear")
        for parte in poligonos_de(geom):
            x, y = parte.exterior.xy
            ax.plot(x, y, color=COR_LIMITE_SATELITE if imagem is not None else COR_LIMITE, linewidth=1.8, zorder=5)
        for area in areas or []:
            cor = CORES_AREAS_SATELITE[area["tipo"]] if imagem is not None else CORES_AREAS_PROTEGIDAS[area["tipo"]]
            for parte in poligonos_de(_em_mercator(area["recorte"])):
                x, y = parte.exterior.xy
                ax.plot(x, y, color=cor, linewidth=0.9, zorder=4, linestyle="-" if area["tipo"] == "UC" else "--")
        ax.set_aspect("equal")
    if imagem is None:
        ax.set_facecolor(FUNDO)
    px, py = lonlat_para_mercator(recentes["lon"], recentes["lat"]) if len(recentes) else ([], [])
    px, py = np.asarray(px), np.asarray(py)
    for i, (idade, cor) in enumerate(reversed(CORES_IDADE.items())):
        selecao = (recentes["idade"] == idade).to_numpy() if len(recentes) else np.array([], dtype=bool)
        if selecao.any():
            ax.scatter(px[selecao], py[selecao], c=cor, s=26, edgecolors="black", linewidths=0.5, zorder=6 + i,
                       label=f"{idade} ({fmt_inteiro(int(selecao.sum()))})")
    if len(recentes):                    # legenda centralizada abaixo do mapa (não cobre focos)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=4, fontsize=7, frameon=False,
                  title="Idade do foco", title_fontsize=7)
    else:
        _sem_dados(ax, f"Sem focos nos últimos {dias} dias")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{mercator_para_lon(v):.1f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{mercator_para_lat(v):.1f}"))
    ax.tick_params(labelsize=7)
    ax.set_title(f"Focos nos últimos {dias} dias até {ultimo_dia:%d/%m/%Y} — {nome} ({fmt_inteiro(len(recentes))} focos)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    _nota(fig, CREDITO_SATELITE if imagem is not None else
          "Imagem de satélite indisponível (sem conexão com a internet).", centro=True)
    return fig


MESES_NOME = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
              "novembro", "dezembro"]


def mapa_recorrencia_mes(rec, poligono, nome: str, dia):
    """Recorrência dos focos no mês (grade proporcional) com os focos da última semana por cima (PDF do cenário)."""
    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    _acabamento(ax)
    desenhar_limite(ax, poligono)
    periodo = f"{rec.anos[0]}–{rec.anos[-1]}" if rec.anos else "sem anos anteriores"
    if rec.matriz.any():
        _grade_colorida(ax, rec.grade, rec.matriz, "YlOrRd", fig, f"Anos com foco em {MESES_NOME[rec.mes - 1]}")
    if len(rec.atuais):
        ax.scatter(rec.atuais["lon"], rec.atuais["lat"], s=10, c="#0D47A1", edgecolors="white", linewidths=0.4,
                   zorder=6, label=f"Focos da última semana ({fmt_inteiro(len(rec.atuais))})")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), fontsize=7, frameon=False)
    elif not rec.matriz.any():
        _sem_dados(ax, f"Sem focos em {MESES_NOME[rec.mes - 1]}")
    km = fmt_km(rec.grade.tamanho_km)
    ax.set_title(f"Recorrência em {MESES_NOME[rec.mes - 1]} ({periodo}) × focos até {dia:%d/%m/%Y} — {nome}\n"
                 f"Grade {km} × {km} km", fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _nota(fig, nota_grade(rec.grade), centro=True)
    return fig
