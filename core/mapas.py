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


# ------------------------------------------------------ Mapa de localização

COR_UF_DESTAQUE = "#FFB74D"
COR_TERRITORIO_LOCALIZACAO = "#D32F2F"


def _preencher(ax, geom, **estilo):
    from matplotlib.patches import Polygon as PoligonoMpl

    for parte in poligonos_de(geom):
        ax.add_patch(PoligonoMpl(np.asarray(parte.exterior.coords), closed=True, **estilo))


def mapa_localizacao(sigla_uf: str | None, territorio, nome: str, municipios=(), ufs: dict | None = None):
    """Onde fica o território: o Brasil com o estado destacado (e um retângulo no território) e o estado com os
    limites municipais e o território em vermelho. ``municipios`` = (NM_MUN, SIGLA_UF, geometria);
    ``ufs`` = ``territorios.limites_uf()``."""
    from matplotlib.patches import Rectangle

    from core.territorios import limites_uf

    ufs = limites_uf() if ufs is None else ufs
    fig, (ax_br, ax_uf) = plt.subplots(1, 2, figsize=(10, 4.6), dpi=150, gridspec_kw={"width_ratios": [1, 1.25]})
    for ax in (ax_br, ax_uf):
        ax.set_facecolor("#EAF2F8")
        ax.set_xticks([])
        ax.set_yticks([])
    for sigla, (_, geom) in ufs.items():
        destaque = sigla == sigla_uf
        _preencher(ax_br, geom, facecolor=COR_UF_DESTAQUE if destaque else "#F5F5F5", edgecolor="#757575",
                   linewidth=0.8 if destaque else 0.4, zorder=3 if destaque else 2)
        c = geom.representative_point()
        ax_br.text(c.x, c.y, sigla, fontsize=5, ha="center", va="center", color="#424242", zorder=4)
    if territorio is not None:
        x0, y0, x1, y1 = territorio.bounds
        lado = max(x1 - x0, y1 - y0, 0.6)            # territórios pequenos: retângulo visível no Brasil
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ax_br.add_patch(Rectangle((cx - lado / 2, cy - lado / 2), lado, lado, fill=False,
                                  edgecolor=COR_TERRITORIO_LOCALIZACAO, linewidth=1.4, zorder=5))
    ax_br.set_xlim(-74.5, -34)
    ax_br.set_ylim(-34.5, 6)
    ax_br.set_aspect("equal")
    ax_br.set_title("Brasil", fontsize=9, fontweight="bold")

    uf = ufs.get(sigla_uf)
    if uf is not None:
        _preencher(ax_uf, uf[1], facecolor="#FFF3E0", edgecolor="#5D4037", linewidth=1.0, zorder=1)
    for _, _, geom in municipios:
        for parte in poligonos_de(geom):
            x, y = parte.exterior.xy
            ax_uf.plot(x, y, color="#BDBDBD", linewidth=0.3, zorder=2)
    if territorio is not None:
        _preencher(ax_uf, territorio, facecolor=COR_TERRITORIO_LOCALIZACAO, edgecolor="#7F0000", linewidth=0.8,
                   alpha=0.85, zorder=3)
    referencia = uf[1] if uf is not None else territorio
    if referencia is not None:
        x0, y0, x1, y1 = referencia.bounds
        mx, my = (x1 - x0) * 0.04, (y1 - y0) * 0.04
        ax_uf.set_xlim(x0 - mx, x1 + mx)
        ax_uf.set_ylim(y0 - my, y1 + my)
        ax_uf.set_aspect(1 / np.cos(np.radians((y0 + y1) / 2)))
        if territorio is not None:                    # seta com o nome, do centro do estado para o território
            alvo = territorio.representative_point()
            centro = referencia.representative_point()
            texto = (alvo.x + (centro.x - alvo.x) * 0.55, alvo.y + (centro.y - alvo.y) * 0.55)
            ax_uf.annotate(nome, xy=(alvo.x, alvo.y), xytext=texto, fontsize=8, fontweight="bold", ha="center",
                           color="#7F0000", zorder=6,
                           bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#7F0000"},
                           arrowprops={"arrowstyle": "-|>", "color": "#7F0000", "linewidth": 1.2})
    ax_uf.set_title(f"{uf[0] if uf is not None else ''} — {nome}", fontsize=9, fontweight="bold")
    ax_uf.legend(handles=[Patch(facecolor=COR_TERRITORIO_LOCALIZACAO, edgecolor="#7F0000", label=nome),
                          Line2D([], [], color="#BDBDBD", linewidth=0.8, label="Limites municipais")],
                 loc="lower left", fontsize=7, frameon=True, framealpha=0.9)
    fig.suptitle(f"Localização — {nome}", fontsize=11, fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------- Mapas de anomalia

# Classes da anomalia: −∞ −3 −2 −1 | 1 2 3 +∞ ; com SINAL_ANOMALIA = −1 as negativas (mais focos) são vermelhas
LIMITES_ANOMALIA = [-99, -3, -2, -1, 1, 2, 3, 99]
CORES_ANOMALIA = ["#67000D", "#EF3B2C", "#FCBBA1", "#FFFFFF", "#9ECAE1", "#2171B5", "#08306B"]
VERDE_5, VERDE_1 = "#81C784", "#1B5E20"           # borda dos pontos: 5% (clara) e 1% (escura)
COR_GRUPO_MAIS, COR_GRUPO_MENOS = "#C62828", "#1565C0"
ROTULOS_ANOMALIA = ["≤ −3\nextrema", "−3 a −2\nforte", "−2 a −1\nmoderada", "comum\n|a| < 1", "1 a 2\nmoderada",
                    "2 a 3\nforte", "≥ 3\nextrema"]
TITULOS_ANOMALIA = {
    "quantidade": ("Anomalia de QUANTIDADE", "a célula tem mais (vermelho) ou menos (azul) focos do que costuma ter "
                                             "nestas datas"),
    "localizacao": ("Anomalia de LOCALIZAÇÃO", "descontado o total, os focos caíram onde não costumam cair "
                                               "(vermelho) ou faltaram onde costumam (azul)"),
    "combinada": ("Anomalia COMBINADA (quantidade e localização)", "Stouffer–Strube: (z_Q + z_L)/√(2 + 2ρ)"),
}


def mapa_anomalia(an, tipo: str, poligono, nome: str, compacto: bool = False):
    """Uma das três anomalias (``core/anomalias.py``) na grade proporcional, com pontos nas células
    significativas (q < 5% e q < 1%, Benjamini–Hochberg). ``compacto``: versão pequena, sem a frase explicativa
    nem a legenda de significância (ao lado da sazonalidade, no PDF do cenário)."""
    from matplotlib.colors import BoundaryNorm, ListedColormap

    from matplotlib import patheffects as efeitos

    from core.anomalias import DISTANCIA_GRUPO_KM, NIVEIS_SIGNIFICANCIA, grupos_significativos

    fig, ax = plt.subplots(figsize=(4.6, 4.4) if compacto else (9, 7.6), dpi=150)
    fig.subplots_adjust(top=0.86, bottom=0.24 if compacto else 0.2)
    _acabamento(ax)
    desenhar_limite(ax, poligono)
    valores = getattr(an, tipo)
    cmap, norm = ListedColormap(CORES_ANOMALIA), BoundaryNorm(LIMITES_ANOMALIA, len(CORES_ANOMALIA))
    x, y = np.meshgrid(an.grade.x, an.grade.y)
    malha = ax.pcolormesh(x, y, np.ma.masked_where(~an.informativas, valores).T, cmap=cmap, norm=norm, zorder=2,
                          edgecolors="none")
    cx, cy = np.meshgrid((an.grade.x[:-1] + an.grade.x[1:]) / 2, (an.grade.y[:-1] + an.grade.y[1:]) / 2,
                         indexing="ij")
    n5, n1 = NIVEIS_SIGNIFICANCIA
    so_5 = an.significativas(tipo, n5) & ~an.significativas(tipo, n1)
    so_1 = an.significativas(tipo, n1)
    # pontos com a cor da própria célula (não escondem a anomalia) e borda verde: clara a 5%, escura a 1%
    for selecao, tamanho, borda, espessura in ((so_5, 16, VERDE_5, 0.9), (so_1, 30, VERDE_1, 1.6)):
        ax.scatter(cx[selecao], cy[selecao], s=tamanho, c=cmap(norm(valores[selecao])), edgecolors=borda,
                   linewidths=espessura, zorder=5)
    for grupo in grupos_significativos(an, tipo):        # contorno dos grupos a 1% (até 20 km entre células)
        for parte in poligonos_de(grupo["poligono"]):
            gx, gy = parte.exterior.xy
            ax.plot(gx, gy, color=COR_GRUPO_MAIS if grupo["mais_focos"] else COR_GRUPO_MENOS, linewidth=1.1,
                    zorder=6, path_effects=[efeitos.Stroke(linewidth=2.6, foreground="white"), efeitos.Normal()])
    titulo, explicacao = TITULOS_ANOMALIA[tipo]
    km = fmt_numero(an.grade.tamanho_km, 2).rstrip("0").rstrip(",")
    if compacto:
        ax.tick_params(labelsize=5.5)
        ax.set_title(f"Anomalia combinada — {nome}\n{an.inicio:%d/%m} a {an.fim:%d/%m/%Y} × {an.anos[0]}–"
                     f"{an.anos[-1]} (grade {km} km)", fontsize=7.5, fontweight="bold")
        barra = fig.colorbar(malha, cax=fig.add_axes((0.12, 0.1, 0.76, 0.03)), orientation="horizontal",
                             spacing="uniform", ticks=[-51, -2.5, -1.5, 0, 1.5, 2.5, 51])
        barra.ax.set_xticklabels(["≤−3", "−3/−2", "−2/−1", "comum", "1/2", "2/3", "≥3"], fontsize=5.5)
        barra.set_label("negativa = mais focos · pontos = significativa (5%, 1%)", fontsize=5.5)
        return fig
    ax.set_title(f"{titulo} — {nome}\n{an.inicio:%d/%m/%Y} a {an.fim:%d/%m/%Y} × mesmas datas de "
                 f"{an.anos[0]}–{an.anos[-1]} (grade {km} × {km} km)" if an.anos else titulo,
                 fontsize=10, fontweight="bold", pad=16)
    ax.text(0.5, 1.01, explicacao, transform=ax.transAxes, ha="center", va="bottom", fontsize=7.5,
            color="#455A64")
    barra = fig.colorbar(malha, cax=fig.add_axes((0.15, 0.09, 0.7, 0.025)), orientation="horizontal",
                         spacing="uniform", ticks=[-51, -2.5, -1.5, 0, 1.5, 2.5, 51])
    barra.ax.set_xticklabels(ROTULOS_ANOMALIA, fontsize=7)
    barra.set_label("Anomalia (desvios padrão): negativa = mais focos que o comum, positiva = menos", fontsize=7.5)
    ax.legend(handles=[
        Line2D([], [], marker="o", color="none", markerfacecolor="#EEEEEE", markeredgecolor=VERDE_5,
               markeredgewidth=0.9, markersize=3.8,
               label=f"significativa a {fmt_numero(n5 * 100)}% (q < {fmt_numero(n5, 2)})"),
        Line2D([], [], marker="o", color="none", markerfacecolor="#EEEEEE", markeredgecolor=VERDE_1,
               markeredgewidth=1.6, markersize=5.4,
               label=f"significativa a {fmt_numero(n1 * 100)}% (q < {fmt_numero(n1, 2)})"),
        Line2D([], [], color=COR_GRUPO_MAIS, linewidth=1.1,
               label=f"grupo a 1% (até {DISTANCIA_GRUPO_KM} km) — mais focos"),
        Line2D([], [], color=COR_GRUPO_MENOS, linewidth=1.1,
               label=f"grupo a 1% (até {DISTANCIA_GRUPO_KM} km) — menos focos")],
        loc="lower left", fontsize=6.5, framealpha=0.9, title="Significância (Benjamini–Hochberg)", title_fontsize=6.5)
    _nota(fig, f"Total do período: {fmt_inteiro(an.total_atual)} focos × média {fmt_numero(an.total_medio, 1)} "
               f"nas mesmas datas; anomalia do território = {fmt_numero(an.anomalia_total, 2)}. Células vazias: sem "
               "foco no período nem no histórico.", centro=True)
    return fig
