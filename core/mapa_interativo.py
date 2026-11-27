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

from core.config import CREDITO_SENTINEL_SWIR, URL_SATELITE, URL_SENTINEL_SWIR
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


def estilo_satelite(swir: bool = False) -> str:
    """Estilo do mapa base como URL ``data:`` (o Streamlit só aceita o estilo como URL). ``swir`` = por cima,
    o mosaico Sentinel-2 mais recente em realce SWIR do Painel do Fogo (WMS, P41): fogo ativo em vermelho/
    amarelo, cicatriz em marrom-escuro, vegetação em verde."""
    estilo = json.loads(json.dumps(ESTILO_SATELITE))
    if swir:
        estilo["sources"]["swir"] = {"type": "raster", "tiles": [URL_SENTINEL_SWIR], "tileSize": 256,
                                     "attribution": CREDITO_SENTINEL_SWIR}
        estilo["layers"].append({"id": "swir", "type": "raster", "source": "swir"})
    return "data:application/json;base64," + base64.b64encode(json.dumps(estilo).encode()).decode()


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


def deck_focos_recentes(recentes, territorio, municipios, rec=None, satelite: bool = True,
                        swir: bool = False) -> pdk.Deck:
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
                    map_style=estilo_satelite(swir) if satelite else None,
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


# ------------------------------------------------ Legenda com as cores como aparecem

FUNDO_TIPICO_SATELITE = (34, 48, 30)     # verde-escuro médio da floresta no Sentinel-2 cloudless


def cor_sobre_satelite(rgb, opacidade: int = OPACIDADE_GRADE, fundo=FUNDO_TIPICO_SATELITE) -> str:
    """Cor que a célula semitransparente realmente mostra sobre a imagem (mistura com o fundo)."""
    a = opacidade / 255
    r, g, b = (round(a * c + (1 - a) * f) for c, f in zip(rgb, fundo))
    return f"rgb({r},{g},{b})"


def legenda_html(recentes, rec=None) -> str:
    """Legenda do mapa interativo em HTML: pontos (cor pela idade), quadrícula (cores já misturadas com o
    satélite, como aparecem no mapa) e linhas."""
    def item(simbolo: str, texto: str) -> str:
        return f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">{simbolo}<span>{texto}</span></div>'

    def ponto(cor: str) -> str:
        return (f'<span style="flex:none;width:12px;height:12px;border-radius:50%;background:{cor};'
                'border:1.5px solid #000"></span>')

    def linha(cor: str, espessura: int) -> str:
        return f'<span style="flex:none;width:22px;height:0;border-top:{espessura}px solid {cor}"></span>'

    partes = ['<div style="font-size:13px;line-height:1.35">', "<b>Focos de calor (pontos)</b>"]
    for idade, cor in CORES_IDADE.items():
        n = int((recentes["idade"] == idade).sum()) if len(recentes) else 0
        if n:
            partes.append(item(ponto(cor), f"{idade} — {fmt_inteiro(n)}"))
    if rec is not None and rec.matriz.any():
        maximo = int(rec.matriz.max())
        periodo = f"{rec.anos[0]}–{rec.anos[-1]}" if rec.anos else ""
        degrade = ", ".join(cor_sobre_satelite(cor_da_recorrencia(1 + (maximo - 1) * k / 4, maximo))
                            for k in range(5))
        partes += [
            f'<div style="margin-top:10px"><b>Quadrícula — anos com foco em {MESES_NOME[rec.mes - 1]}</b></div>',
            f'<div style="height:14px;border-radius:3px;margin:4px 0 2px;background:linear-gradient(90deg,{degrade})">'
            "</div>",
            f'<div style="display:flex;justify-content:space-between;font-size:12px"><span>1 ano</span>'
            f"<span>{maximo} anos</span></div>",
            f'<div style="font-size:12px;color:#888">{periodo}. Onde não há quadrícula, não houve foco nesse '
            "mês.</div>",
        ]
    partes += ['<div style="margin-top:10px"><b>Linhas</b></div>',
               item(linha("rgb(0,229,255)", 3), "Território analisado"),
               item(linha("#ffffff", 1), "Limites municipais")]
    return "".join(partes) + "</div>"


# ------------------------------------------------ Vulnerabilidade a fogo e fumaça (protótipo, P42)

COR_EVENTO = {"Ativo": [229, 57, 53], "Em observação": [251, 140, 0]}
COR_FRENTE = [255, 214, 0]
# cones dissolvidos pelo número de eventos sobrepostos (1, 2, 3+): fogo em vermelhos, fumaça em cinzas
CORES_CONES = {"fogo": {1: [255, 138, 101], 2: [229, 57, 53], 3: [183, 28, 28]},
               "fumaca": {1: [224, 224, 224], 2: [158, 158, 158], 3: [97, 97, 97]}}
# camadas do mapa da vulnerabilidade: rótulo, ligada e opacidade (%) iniciais
CAMADAS_VULNERABILIDADE = {
    "localidades": ("Localidades", True, 100), "focos": ("Focos de calor (7 dias)", True, 90),
    "eventos": ("Eventos de fogo", True, 80), "frentes": ("Frentes de fogo (24 h)", True, 90),
    "fogo": ("Avanço do fogo (24 h)", True, 45), "fumaca": ("Fumaça (6 h)", True, 40),
    "vento": ("Vento", True, 90),
}
# casinha (máscara branca: a cor vem de get_color)
ICONE_CASA = {"url": "data:image/svg+xml;base64," + base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
    b'<path d="M32 6 L60 30 L52 30 L52 58 L38 58 L38 42 L26 42 L26 58 L12 58 L12 30 L4 30 Z" fill="#fff" '
    b'stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>').decode(),
    "width": 64, "height": 64, "anchorY": 58, "mask": True}


def setas_de_vento(pontos, comprimento_graus: float = 0.12) -> list[dict]:
    """``pontos`` = [(lon, lat, km/h, azimute para onde sopra)] → linhas com ponta de seta (PathLayer)."""
    linhas = []
    for lon, lat, vel, para in pontos:
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (vel, para)):
            continue
        tamanho = comprimento_graus * min(max(vel / 15, 0.4), 2.0)
        a = math.radians(para)
        fim = [lon + tamanho * math.sin(a), lat + tamanho * math.cos(a)]
        ponta = [[fim[0] - tamanho * 0.35 * math.sin(a + s), fim[1] - tamanho * 0.35 * math.cos(a + s)]
                 for s in (math.radians(25), -math.radians(25))]
        info = f"<b>Vento</b><br/>{vel:.0f} km/h, soprando para {para:.0f}°"
        linhas += [{"caminho": [[lon, lat], fim], "info": info},
                   {"caminho": [ponta[0], fim, ponta[1]], "info": info}]
    return linhas


def agrupar_setas(pontos, celula_graus: float) -> list[tuple]:
    """Uma seta por célula de ``celula_graus``: média vetorial das setas que cairiam umas sobre as outras."""
    grupos: dict[tuple, list] = {}
    for lon, lat, vel, para in pontos:
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (vel, para)):
            continue
        grupos.setdefault((math.floor(lon / celula_graus), math.floor(lat / celula_graus)), []).append(
            (lon, lat, vel, para))
    saida = []
    for itens in grupos.values():
        u = sum(v * math.sin(math.radians(a)) for _, _, v, a in itens) / len(itens)
        w = sum(v * math.cos(math.radians(a)) for _, _, v, a in itens) / len(itens)
        saida.append((sum(i[0] for i in itens) / len(itens), sum(i[1] for i in itens) / len(itens),
                      sum(i[2] for i in itens) / len(itens), (math.degrees(math.atan2(u, w)) + 360) % 360))
    return saida


def vista_no_ponto(lon: float, lat: float, zoom: float = 11.5) -> pdk.ViewState:
    return pdk.ViewState(longitude=lon, latitude=lat, zoom=zoom)


def deck_vulnerabilidade(analise, municipio_geom, vento_grade=None, satelite: bool = True, swir: bool = False,
                         focos=None, cones=None, camadas: dict | None = None, alvo=None) -> pdk.Deck:
    """Localidades (casinhas pela classe de risco), focos da base, eventos e frentes de fogo, cones dissolvidos
    de fogo e fumaça e setas de vento. ``camadas`` = {nome: (ligada, opacidade 0–100)}; ``alvo`` = (lon, lat)
    para centralizar (dois cliques na tabela)."""
    from core.vulnerabilidade import CORES_CLASSE
    estado = {n: (ligada, op) for n, (_, ligada, op) in CAMADAS_VULNERABILIDADE.items()} | (camadas or {})

    def ligada(nome):
        return estado[nome][0]

    def opacidade(nome):
        return estado[nome][1] / 100

    lista = []
    for tipo in ("fumaca", "fogo"):
        if not ligada(tipo):
            continue
        dados = [{"poligono": anel, "cor": CORES_CONES[tipo][c["sobreposicao"]] + [170],
                  "info": f"<b>{'Avanço do fogo em 24 h' if tipo == 'fogo' else 'Fumaça nas próximas 6 h'}</b>"
                          f"<br/>{c['classe']} sobrepostos"}
                 for c in (cones or []) if c["tipo"] == tipo for partes in _aneis(c["poligono"]) for anel in partes[:1]]
        if dados:
            lista.append(pdk.Layer("PolygonLayer", id=f"cones_{tipo}", data=dados, get_polygon="poligono",
                                   get_fill_color="cor", stroked=False, pickable=True, opacity=opacidade(tipo)))
    ev = analise.eventos
    if len(ev) and ligada("eventos"):
        lista.append(pdk.Layer(
            "PolygonLayer", id="eventos", get_polygon="poligono", get_fill_color="cor", stroked=True,
            get_line_color=[255, 255, 255, 220], line_width_min_pixels=1, pickable=True, opacity=opacidade("eventos"),
            data=[{"poligono": anel, "cor": COR_EVENTO.get(e.status, [229, 57, 53]) + [200],
                   "info": f"<b>Evento de fogo {e.id_evento}</b> ({e.status})<br/>{e.area_ha:.0f} ha · "
                           f"expansão {e.expansao_ha_h:.1f} ha/h<br/>última detecção "
                           f"{e.ultima_deteccao.tz_convert('America/Belem'):%d/%m %H:%M}"}
                  for e in ev.itertuples() for partes in _aneis(e.geometria) for anel in partes[:1]]))
        # o polígono tem poucos km: um losango no centro deixa o evento visível no zoom do município
        lista.append(pdk.Layer(
            "ScatterplotLayer", id="eventos_centro", get_position="posicao", get_fill_color="cor",
            get_line_color=[255, 255, 255, 255], stroked=True, line_width_min_pixels=1.5, get_radius=600,
            radius_min_pixels=4, radius_max_pixels=10, pickable=True, opacity=opacidade("eventos"),
            data=[{"posicao": [float(e.lon), float(e.lat)], "cor": COR_EVENTO.get(e.status, [229, 57, 53]) + [255],
                   "info": f"<b>Evento de fogo {e.id_evento}</b> ({e.status})<br/>{e.area_ha:.0f} ha · "
                           f"expansão {e.expansao_ha_h:.1f} ha/h"} for e in ev.itertuples()]))
    if len(ev) and ligada("frentes") and "frente" in ev:
        dados = [{"poligono": anel, "info": f"<b>Frente de fogo (24 h)</b><br/>Evento {e.id_evento}"}
                 for e in ev.itertuples() if e.frente is not None for partes in _aneis(e.frente) for anel in partes[:1]]
        if dados:
            lista.append(pdk.Layer("PolygonLayer", id="frentes", data=dados, get_polygon="poligono",
                                   get_fill_color=COR_FRENTE + [230], stroked=True, get_line_color=[0, 0, 0, 200],
                                   line_width_min_pixels=0.8, pickable=True, opacity=opacidade("frentes")))
    lista.append(pdk.Layer(
        "PathLayer", id="municipio", data=[{"caminho": anel} for partes in _aneis(municipio_geom) for anel in partes[:1]],
        get_path="caminho", get_color=COR_TERRITORIO, width_min_pixels=2.5, pickable=False))
    if focos is not None and len(focos) and ligada("focos"):
        lista.append(pdk.Layer("ScatterplotLayer", id="focos", data=linhas_focos(focos), get_position="posicao",
                               get_fill_color="cor", get_line_color=[0, 0, 0, 220], stroked=True,
                               line_width_min_pixels=0.5, radius_min_pixels=2.5, radius_max_pixels=5, get_radius=250,
                               pickable=True, opacity=opacidade("focos")))
    if ligada("vento"):
        setas = []
        if vento_grade is not None and len(vento_grade):
            setas += [(r.lon, r.lat, r.velocidade_kmh, (r.direcao_graus + 180) % 360) for r in vento_grade.itertuples()]
        setas += [(e.lon, e.lat, e.vento_kmh, e.vento_para_graus) for e in ev.itertuples()]
        x0, y0, x1, y1 = municipio_geom.bounds
        celula = max(x1 - x0, y1 - y0) / 10            # ~10 setas no lado maior do município
        setas = agrupar_setas(setas, celula)
        if setas:
            lista.append(pdk.Layer("PathLayer", id="vento", data=setas_de_vento(setas, celula * 0.45),
                                   get_path="caminho", get_color=[255, 255, 255, 240], width_min_pixels=1.8,
                                   pickable=True, opacity=opacidade("vento")))
    loc = analise.localidades
    if len(loc) and ligada("localidades"):
        dados = [{"posicao": [float(r.lon), float(r.lat)], "cor": _hex_rgb(CORES_CLASSE[r.classe]) + [255],
                  "tamanho": 9 + 2 * int(r.vulnerabilidade), "icone": ICONE_CASA,
                  "info": f"<b>{r.nome}</b> ({r.categoria})<br/>Risco: {r.classe} · vulnerabilidade "
                          f"{int(r.vulnerabilidade)}<br/>foco mais perto (7 dias): "
                          + (f"{r.foco_7d_km:.1f} km" if math.isfinite(r.foco_7d_km) else "—")}
                 for r in loc.itertuples()]
        lista.append(pdk.Layer("IconLayer", id="localidades", data=dados, get_position="posicao", get_icon="icone",
                               get_size="tamanho", size_units="'pixels'", get_color="cor", pickable=True,
                               opacity=opacidade("localidades")))
    vista_inicial = vista_no_ponto(*alvo) if alvo else vista(municipio_geom.bounds)
    return pdk.Deck(layers=lista, initial_view_state=vista_inicial,
                    map_style=estilo_satelite(swir) if satelite else None,
                    tooltip={"html": "{info}", "style": {"fontSize": "12px", "backgroundColor": "#263238",
                                                         "color": "white"}})


def legenda_vulnerabilidade_html() -> str:
    from core.vulnerabilidade import CORES_CLASSE

    def item(simbolo, texto):
        return f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">{simbolo}<span>{texto}</span></div>'

    def casa(cor):
        return (f'<svg width="14" height="14" viewBox="0 0 64 64" style="flex:none"><path d="M32 6 L60 30 L52 30 '
                f'L52 58 L38 58 L38 42 L26 42 L26 58 L12 58 L12 30 L4 30 Z" fill="{cor}" stroke="#000" '
                'stroke-width="3"/></svg>')

    def ponto(cor):
        return (f'<span style="flex:none;width:10px;height:10px;border-radius:50%;background:{cor};'
                'border:1.5px solid #000"></span>')

    def area(cor):
        return f'<span style="flex:none;width:16px;height:12px;background:{cor};border:1px solid #fff"></span>'

    def rgb(c, a=1):
        return f"rgba({c[0]},{c[1]},{c[2]},{a})"

    partes = ['<div style="font-size:13px;line-height:1.35"><b>Localidades — risco</b>']
    partes += [item(casa(cor), nome) for nome, cor in CORES_CLASSE.items()]
    partes += ['<div style="font-size:12px;color:#888">Casa maior = localidade mais vulnerável.</div>',
               '<div style="margin-top:8px"><b>Focos de calor (base, 7 dias)</b></div>']
    partes += [item(ponto(cor), idade) for idade, cor in CORES_IDADE.items() if not idade.startswith("7")]
    partes += ['<div style="margin-top:8px"><b>Eventos de fogo (Painel do Fogo)</b></div>',
               item(area(rgb(COR_EVENTO["Ativo"])), "Ativo (últimas 48 h)"),
               item(area(rgb(COR_EVENTO["Em observação"])), "Em observação (2 a 4 dias)"),
               item(area(rgb(COR_FRENTE)), "Frente de fogo (24 h)"),
               '<div style="margin-top:8px"><b>Avanço do fogo (24 h) — eventos sobrepostos</b></div>']
    partes += [item(area(rgb(c, 0.7)), f"{n}{'+' if n == 3 else ''}") for n, c in CORES_CONES["fogo"].items()]
    partes += ['<div style="margin-top:8px"><b>Fumaça (6 h) — eventos sobrepostos</b></div>']
    partes += [item(area(rgb(c, 0.7)), f"{n}{'+' if n == 3 else ''}") for n, c in CORES_CONES["fumaca"].items()]
    partes += [item('<span style="flex:none;width:16px;text-align:center;color:#555">➜</span>',
                    "Vento a 10 m (para onde sopra; setas próximas viram uma)"),
               item('<span style="flex:none;width:16px;height:0;border-top:3px solid rgb(0,229,255)"></span>',
                    "Município")]
    return "".join(partes) + "</div>"
