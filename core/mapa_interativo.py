# -*- coding: utf-8 -*-
"""Mapa interativo dos focos dos últimos 7 dias (tela; o PDF continua com ``mapas.mapa_recentes``).

Camadas (de baixo para cima), em pydeck — o deck.gl já vem dentro do Streamlit, então funciona no pacote
offline (só a imagem de satélite precisa de internet):

1. imagem Sentinel-2 cloudless como mapa base (estilo MapLibre embutido numa URL ``data:``, sem arquivo);
2. quadrícula de recorrência do mês (``cenario.recorrencia_mensal``), semitransparente e sem contorno;
3. limites municipais do estado, clicáveis (o clique abre o diagnóstico do município);
4. contorno do território analisado;
5. focos dos últimos 7 dias, com a cor da idade (a mesma do mapa do PDF).

O deck.gl desenha numa tela separada, por cima do mapa base, e não consegue multiplicar as cores com as
do satélite; a quadrícula usa transparência, que tem o mesmo efeito de não esconder a imagem.
"""

import base64
import json
import math

import numpy as np
import pydeck as pdk

from core.config import URL_SATELITE
from core.mapas import CORES_IDADE, MESES_NOME
from core.territorios import poligonos_de
from core.texto import fmt_inteiro

CAMADA_MUNICIPIOS = "municipios"
ALTURA_PX = 560
LARGURA_PX = 900            # largura aproximada da área do mapa, para o enquadramento inicial
OPACIDADE_GRADE = 110       # 0–255
COR_TERRITORIO = [0, 229, 255]
# Escala YlOrRd (a mesma do mapa da recorrência do mês no PDF)
ESCALA_GRADE = [(255, 255, 178), (254, 204, 92), (253, 141, 60), (240, 59, 32), (189, 0, 38)]

ESTILO_SATELITE = {
    "version": 8,
    "sources": {"s2": {"type": "raster", "tiles": [URL_SATELITE], "tileSize": 256, "maxzoom": 15,
                       "attribution": "Sentinel-2 cloudless 2024 — EOX IT Services GmbH (CC BY-NC-SA 4.0)"}},
    "layers": [{"id": "s2", "type": "raster", "source": "s2"}],
}


def estilo_satelite() -> str:
    """Estilo do mapa base como URL ``data:`` (o Streamlit só aceita o estilo como URL)."""
    return "data:application/json;base64," + base64.b64encode(json.dumps(ESTILO_SATELITE).encode()).decode()


def _hex_rgb(cor: str) -> list[int]:
    return [int(cor[i:i + 2], 16) for i in (1, 3, 5)]


def _aneis(geom) -> list[list]:
    """Polígonos (exterior + furos) de uma geometria, como listas de [lon, lat]."""
    return [[[list(map(float, c)) for c in p.exterior.coords]]
            + [[list(map(float, c)) for c in furo.coords] for furo in p.interiors] for p in poligonos_de(geom)]


def cor_da_recorrencia(valor: float, maximo: float) -> list[int]:
    """Cor da escala YlOrRd para ``valor`` de 1 a ``maximo`` anos."""
    if maximo <= 1:
        return list(ESCALA_GRADE[-1])
    posicao = (valor - 1) / (maximo - 1) * (len(ESCALA_GRADE) - 1)
    i = min(int(posicao), len(ESCALA_GRADE) - 2)
    f = posicao - i
    return [round(a + (b - a) * f) for a, b in zip(ESCALA_GRADE[i], ESCALA_GRADE[i + 1])]


def vista(limites, largura_px: int = LARGURA_PX, altura_px: int = ALTURA_PX) -> pdk.ViewState:
    """Enquadramento inicial que mostra todo o retângulo ``limites`` (Web Mercator)."""
    min_x, min_y, max_x, max_y = limites

    def y_merc(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    dx = max(max_x - min_x, 1e-4) / 360
    dy = max(y_merc(max_y) - y_merc(min_y), 1e-6) / (2 * math.pi)
    # no deck.gl o mundo inteiro tem 512 px no zoom 0
    zoom = min(math.log2(largura_px / 512 / dx), math.log2(altura_px / 512 / dy)) - 0.1
    return pdk.ViewState(longitude=(min_x + max_x) / 2, latitude=(min_y + max_y) / 2, zoom=max(1.0, zoom))


def linhas_grade(rec) -> list[dict]:
    """Células com recorrência > 0: polígono, cor e texto."""
    grade, matriz = rec.grade, rec.matriz
    maximo = float(matriz.max()) if matriz.size else 0
    linhas = []
    for i, j in zip(*np.nonzero(matriz)):
        x0, x1, y0, y1 = (float(v) for v in (grade.x[i], grade.x[i + 1], grade.y[j], grade.y[j + 1]))
        linhas.append({"poligono": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                       "cor": cor_da_recorrencia(matriz[i, j], maximo) + [OPACIDADE_GRADE]})
    return linhas


def linhas_municipios(municipios) -> list[dict]:
    """``municipios`` = (NM_MUN, SIGLA_UF, geometria) — um registro por parte do polígono."""
    return [{"poligono": anel, "nome": nome, "uf": uf,
             "info": f"<b>{nome} ({uf})</b><br/>Clique para abrir o diagnóstico do município"}
            for nome, uf, geom in municipios for anel in _aneis(geom)]


def linhas_focos(recentes) -> list[dict]:
    linhas = []
    for r in recentes.itertuples():
        areas = [f"{tipo}: {nome}" for tipo, nome in (("UC", r.UC), ("TI", r.TI)) if nome not in ("NONE", "")]
        linhas.append({"posicao": [float(r.lon), float(r.lat)], "cor": _hex_rgb(CORES_IDADE[r.idade]) + [235],
                       "info": f"<b>Foco em {r.data:%d/%m/%Y}</b> ({r.idade})<br/>"
                               f"{r.lat:.4f}, {r.lon:.4f}" + "".join(f"<br/>{a}" for a in areas)})
    return linhas


def deck_focos_recentes(recentes, territorio, municipios, rec=None, satelite: bool = True) -> pdk.Deck:
    """Mapa interativo: ``recentes`` = focos dos últimos 7 dias (lon, lat, data, idade, UC, TI); ``territorio`` =
    polígono analisado (enquadramento e contorno); ``municipios`` = limites clicáveis; ``rec`` = recorrência do mês."""
    camadas = []
    if rec is not None and rec.matriz.any():
        camadas.append(pdk.Layer("PolygonLayer", data=linhas_grade(rec), id="recorrencia", get_polygon="poligono",
                                 get_fill_color="cor", stroked=False, pickable=False))
    camadas.append(pdk.Layer(
        "PolygonLayer", data=linhas_municipios(municipios), id=CAMADA_MUNICIPIOS, get_polygon="poligono",
        filled=True, get_fill_color=[0, 0, 0, 1], stroked=True, get_line_color=[255, 255, 255, 150],
        line_width_min_pixels=0.8, pickable=True, auto_highlight=True, highlight_color=[255, 255, 255, 50]))
    if territorio is not None:
        camadas.append(pdk.Layer(
            "PathLayer", data=[{"caminho": anel} for partes in _aneis(territorio) for anel in partes[:1]],
            id="territorio", get_path="caminho", get_color=COR_TERRITORIO, width_min_pixels=2.5, pickable=False))
    if len(recentes):
        camadas.append(pdk.Layer("ScatterplotLayer", data=linhas_focos(recentes), id="focos", get_position="posicao",
                                 get_fill_color="cor", get_line_color=[0, 0, 0, 220], stroked=True,
                                 line_width_min_pixels=0.6, radius_min_pixels=3.5, radius_max_pixels=7,
                                 get_radius=300, pickable=True))
    limites = territorio.bounds if territorio is not None else (
        float(recentes["lon"].min()), float(recentes["lat"].min()), float(recentes["lon"].max()),
        float(recentes["lat"].max()))
    return pdk.Deck(layers=camadas, initial_view_state=vista(limites),
                    map_style=estilo_satelite() if satelite else None,
                    tooltip={"html": "{info}", "style": {"fontSize": "12px", "backgroundColor": "#263238",
                                                         "color": "white"}})


def legenda(recentes, rec=None) -> list[tuple[str, str]]:
    """(cor CSS, rótulo) para a legenda em HTML abaixo do mapa."""
    itens = []
    for idade, cor in CORES_IDADE.items():
        n = int((recentes["idade"] == idade).sum()) if len(recentes) else 0
        if n:
            itens.append((cor, f"{idade} ({fmt_inteiro(n)})"))
    if rec is not None and rec.matriz.any():
        mes, maximo = MESES_NOME[rec.mes - 1], int(rec.matriz.max())
        periodo = f"{rec.anos[0]}–{rec.anos[-1]}" if rec.anos else ""
        for valor, texto in ((1, "1 ano"), (maximo, f"{maximo} anos")):
            r, g, b = cor_da_recorrencia(valor, maximo)
            itens.append((f"rgba({r},{g},{b},0.6)", f"Quadrícula: foco em {mes} em {texto} ({periodo})"))
    return itens


def municipio_clicado(selecao) -> str | None:
    """Nome do município do clique (estado de ``st.pydeck_chart(..., on_select=...)``)."""
    try:
        objetos = selecao["selection"]["objects"].get(CAMADA_MUNICIPIOS) or []
    except (KeyError, TypeError, AttributeError):
        return None
    return objetos[0].get("nome") if objetos else None
