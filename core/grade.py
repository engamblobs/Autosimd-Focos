# -*- coding: utf-8 -*-
"""Grade regular de 10 km × 10 km (docs/07 §4): contagem, recorrência e GeoJSON para o QGIS.

A grade é **ajustada à latitude do território** (P8): 10 km em latitude são sempre ~0,090°, mas 10 km
em longitude são 0,090° no Equador e 0,104° em −30° (Rio Grande do Sul). Com o ajuste, toda célula
tem ~100 km² em qualquer parte do país e as contagens de lugares diferentes são comparáveis. Começa
uma célula a sudoeste do território. É a mesma grade nos mapas e no GeoJSON.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.config import TAMANHO_CELULA_KM
from core.kernel import KM_POR_GRAU_LAT, KM_POR_GRAU_LON_EQUADOR
from core.texto import fmt_numero


@dataclass
class Grade:
    x: np.ndarray            # bordas em longitude
    y: np.ndarray            # bordas em latitude
    latitude_ref: float = 0.0

    @property
    def forma(self) -> tuple[int, int]:
        return len(self.x) - 1, len(self.y) - 1

    @property
    def passo_x(self) -> float:
        return float(self.x[1] - self.x[0])

    @property
    def passo_y(self) -> float:
        return float(self.y[1] - self.y[0])


def passos_em_graus(latitude: float, tamanho_km: float = TAMANHO_CELULA_KM) -> tuple[float, float]:
    """(longitude, latitude) em graus de uma célula de ``tamanho_km`` na latitude dada."""
    return (tamanho_km / (KM_POR_GRAU_LON_EQUADOR * math.cos(math.radians(latitude))),
            tamanho_km / KM_POR_GRAU_LAT)


def grade_do_territorio(limites: tuple[float, float, float, float],
                        tamanho_km: float = TAMANHO_CELULA_KM) -> Grade:
    """``limites`` = (min_x, min_y, max_x, max_y), como ``geometria.bounds``."""
    min_x, min_y, max_x, max_y = limites
    latitude = (min_y + max_y) / 2
    passo_x, passo_y = passos_em_graus(latitude, tamanho_km)
    return Grade(
        np.arange(min_x - passo_x, max_x + 2 * passo_x, passo_x),
        np.arange(min_y - passo_y, max_y + 2 * passo_y, passo_y),
        latitude,
    )


def nota_grade(grade: Grade) -> str:
    """Observação sobre o ajuste da grade (mapas e relatórios, P8)."""
    return (f"Grade de {TAMANHO_CELULA_KM} km × {TAMANHO_CELULA_KM} km ajustada à latitude do território "
            f"({fmt_numero(grade.latitude_ref, 1)}°): {fmt_numero(grade.passo_y, 3)}° de latitude × "
            f"{fmt_numero(grade.passo_x, 3)}° de longitude, para que todas as células tenham a mesma área "
            f"(~{TAMANHO_CELULA_KM ** 2} km²) em qualquer parte do país e as contagens sejam comparáveis.")


def contagem(grade: Grade, lons, lats) -> np.ndarray:
    """Focos por célula (matriz [x, y])."""
    if len(lons) == 0:
        return np.zeros(grade.forma)
    valores, _, _ = np.histogram2d(np.asarray(lons), np.asarray(lats), bins=[grade.x, grade.y])
    return valores


def recorrencia(grade: Grade, lons, lats, anos) -> np.ndarray:
    """Em quantos anos diferentes cada célula teve pelo menos um foco."""
    lons, lats, anos = np.asarray(lons), np.asarray(lats), np.asarray(anos)
    matriz = np.zeros(grade.forma)
    for ano in np.unique(anos):
        no_ano = anos == ano
        matriz += (contagem(grade, lons[no_ano], lats[no_ano]) > 0).astype(int)
    return matriz


def grade_qgis(focos: pd.DataFrame, poligono=None, tamanho_km: float = TAMANHO_CELULA_KM) -> dict:
    """FeatureCollection com as células que têm focos: ``cell_id``, ``focos_acumulados``, ``recorrencia_anos``.

    Limites = polígono do território; sem polígono, a extensão dos próprios focos.
    """
    vazia = {"type": "FeatureCollection", "name": "grade_autosimd_qgis", "features": []}
    if focos.empty:
        return vazia
    if poligono is not None:
        limites = poligono.bounds
    else:
        limites = (focos["lon"].min(), focos["lat"].min(), focos["lon"].max(), focos["lat"].max())
    grade = grade_do_territorio(limites, tamanho_km)
    total = contagem(grade, focos["lon"], focos["lat"])
    anos = recorrencia(grade, focos["lon"], focos["lat"], focos["ano"])

    feicoes = []
    for i, j in zip(*np.nonzero(total)):          # mesma ordem do laço x → y
        x0, x1, y0, y1 = grade.x[i], grade.x[i + 1], grade.y[j], grade.y[j + 1]
        feicoes.append({
            "type": "Feature",
            "properties": {"cell_id": len(feicoes) + 1, "focos_acumulados": int(total[i, j]),
                           "recorrencia_anos": int(anos[i, j])},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]},
        })
    return {**vazia, "descricao": nota_grade(grade), "features": feicoes}


# ------------------------------------------------- Risco de recorrência (KML)

CLASSES_RISCO = [   # (código, rótulo, cor RGB)
    ("baixo", "Risco baixo", "#FFEB3B"),
    ("moderado", "Risco moderado", "#FB8C00"),
    ("alto", "Risco alto", "#E53935"),
    ("muito_alto", "Risco muito alto", "#6A1B1A"),
]


def risco_de_recorrencia(focos: pd.DataFrame, poligono=None) -> dict:
    """Células da grade com foco classificadas pelos quartis da recorrência e dissolvidas por classe.

    Quartis (Q1, Q2, Q3) dos anos de recorrência das células com pelo menos um foco: baixo ≤ Q1 <
    moderado ≤ Q2 < alto ≤ Q3 < muito alto. Com poucos valores distintos (ex.: período de 2 anos),
    quartis iguais deixam classes vazias. Devolve ``{"quartis": (q1, q2, q3), "classes": [...]}``,
    cada classe com ``codigo``, ``rotulo``, ``cor``, ``anos`` (mín., máx.), ``celulas``, ``geometria``.
    """
    import shapely
    from shapely.geometry import box

    vazio = {"quartis": None, "grade": None,
             "classes": [{"codigo": c, "rotulo": r, "cor": cor, "anos": None, "celulas": 0, "geometria": None}
                         for c, r, cor in CLASSES_RISCO]}
    if focos.empty:
        return vazio
    limites = poligono.bounds if poligono is not None else (
        focos["lon"].min(), focos["lat"].min(), focos["lon"].max(), focos["lat"].max())
    grade = grade_do_territorio(limites)
    anos = recorrencia(grade, focos["lon"], focos["lat"], focos["ano"])
    com_fogo = anos[anos > 0]
    q1, q2, q3 = (float(q) for q in np.quantile(com_fogo, [0.25, 0.5, 0.75]))
    classe = np.full(anos.shape, -1)
    classe[anos > 0] = 3
    classe[(anos > 0) & (anos <= q3)] = 2
    classe[(anos > 0) & (anos <= q2)] = 1
    classe[(anos > 0) & (anos <= q1)] = 0
    resultado = {"quartis": (q1, q2, q3), "grade": grade, "classes": []}
    for n, (codigo, rotulo, cor) in enumerate(CLASSES_RISCO):
        indices = list(zip(*np.nonzero(classe == n)))
        caixas = [box(grade.x[i], grade.y[j], grade.x[i + 1], grade.y[j + 1]) for i, j in indices]
        valores = [int(anos[i, j]) for i, j in indices]
        resultado["classes"].append({
            "codigo": codigo, "rotulo": rotulo, "cor": cor, "celulas": len(caixas),
            "anos": (min(valores), max(valores)) if valores else None,
            "geometria": shapely.union_all(caixas) if caixas else None,
        })
    return resultado


def _cor_kml(cor_hex: str, opacidade: int) -> str:
    """#RRGGBB → aabbggrr (ordem do KML)."""
    r, g, b = cor_hex[1:3], cor_hex[3:5], cor_hex[5:7]
    return f"{opacidade:02x}{b}{g}{r}"


def _anel_kml(coordenadas) -> str:
    return " ".join(f"{x:.6f},{y:.6f},0" for x, y in coordenadas)


def _poligono_kml(poligono) -> str:
    furos = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{_anel_kml(f.coords)}</coordinates></LinearRing>"
                    f"</innerBoundaryIs>" for f in poligono.interiors)
    return (f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{_anel_kml(poligono.exterior.coords)}"
            f"</coordinates></LinearRing></outerBoundaryIs>{furos}</Polygon>")


def kml_risco(classe: dict, territorio: str, periodo: str, quartis, nota: str, area_km2=None) -> str:
    """Um arquivo KML com o polígono dissolvido de uma classe de risco de recorrência."""
    from xml.sax.saxutils import escape

    if quartis is None:
        criterio = "Sem focos no período."
    else:
        q = [fmt_numero(v, 2) for v in quartis]
        criterio = (f"Quartis da recorrência (anos com fogo por célula de 10 km, só células com foco): "
                    f"Q1 = {q[0]}, Q2 = {q[1]}, Q3 = {q[2]}. Baixo ≤ Q1 &lt; Moderado ≤ Q2 &lt; Alto ≤ Q3 &lt; "
                    f"Muito alto.")
    if classe["geometria"] is None:
        detalhe = "Nenhuma célula nesta classe (quartis iguais ou sem focos)."
        corpo = ""
    else:
        a0, a1 = classe["anos"]
        anos = f"{a0} ano(s)" if a0 == a1 else f"{a0} a {a1} anos"
        area = f"; área ≈ {fmt_numero(area_km2)} km²" if area_km2 else ""
        detalhe = f"{classe['celulas']} células; recorrência de {anos}{area}."
        geometria = classe["geometria"]
        partes = list(getattr(geometria, "geoms", [geometria]))
        poligonos = "".join(_poligono_kml(p) for p in partes if p.geom_type == "Polygon")
        corpo = (f"<Placemark><name>{escape(classe['rotulo'])}</name><styleUrl>#estilo</styleUrl>"
                 f"<description>{escape(detalhe)}</description>"
                 f"<MultiGeometry>{poligonos}</MultiGeometry></Placemark>")
    descricao = f"{escape(territorio)} — {escape(periodo)}. {escape(detalhe)} {criterio} {escape(nota)}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(classe['rotulo'])} — {escape(territorio)}</name>"
        f"<description>{descricao}</description>"
        f'<Style id="estilo"><LineStyle><color>{_cor_kml(classe["cor"], 0xFF)}</color><width>1.5</width></LineStyle>'
        f"<PolyStyle><color>{_cor_kml(classe['cor'], 0x99)}</color></PolyStyle></Style>"
        f"{corpo}</Document></kml>\n"
    )
