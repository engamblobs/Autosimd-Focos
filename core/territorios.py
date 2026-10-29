# -*- coding: utf-8 -*-
"""Geometrias dos territórios analisados: municípios (IBGE), UCs (CNUC/MMA) e TIs (FUNAI).

As geometrias são lidas uma vez por arquivo e guardadas em memória (``lru_cache``):
os GeoJSON de UC e TI do Brasil inteiro têm mais de 50 MB cada.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape
from shapely.validation import make_valid

from core.config import (
    LIMIAR_SOBREPOSICAO_AREA, LIMIAR_SOBREPOSICAO_TERRITORIO, LIMITES_UF_GEOJSON, caminho_ti, caminho_uc,
    pasta_municipios,
)
from core.texto import chave_nome

try:
    from pyproj import Geod
    GEOD_WGS84 = Geod(ellps="WGS84")
except ImportError:   # sem pyproj a área (e a densidade) fica indisponível
    GEOD_WGS84 = None

CORES_AREAS_PROTEGIDAS = {"UC": "#2E7D32", "TI": "#8D4E00"}
# Campos de nome/código das bases nacionais, na ordem em que são procurados
CAMPOS_ROTULO = (("terrai_nom", "terrai_cod"), ("NOME_UC1", "ID_UC0"))


def _ler_geojson(caminho: Path) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- Municípios

def estados_disponiveis(pasta: Path | None = None) -> dict[str, Path]:
    """Nome do estado → arquivo, a partir dos ``NM_UF_<Estado>.geojson`` da pasta."""
    pasta = Path(pasta or pasta_municipios())
    if not pasta.exists():
        return {}
    return {arq.stem.removeprefix("NM_UF_"): arq for arq in sorted(pasta.glob("NM_UF_*.geojson"))}


@lru_cache(maxsize=4)
def municipios_do_estado(caminho: Path) -> dict[str, object]:
    """Chave do nome (sem acento, maiúsculas) → geometria do município."""
    if not Path(caminho).exists():
        return {}
    return {
        chave_nome(f["properties"].get("NM_MUN")): shape(f["geometry"])
        for f in _ler_geojson(caminho).get("features", [])
        if f.get("geometry") and f.get("properties", {}).get("NM_MUN")
    }


def geometria_municipio(caminho_estado: Path, municipio: str):
    return municipios_do_estado(Path(caminho_estado)).get(chave_nome(municipio))



@lru_cache(maxsize=4)
def municipios_simplificados(caminho: Path, tolerancia: float = 0.002) -> tuple[tuple[str, str, object], ...]:
    """(NM_MUN como no IBGE, SIGLA_UF, geometria simplificada a ~200 m) — limites do mapa interativo."""
    if not Path(caminho).exists():
        return ()
    return tuple(
        (str(f["properties"]["NM_MUN"]), str(f["properties"].get("SIGLA_UF", "")),
         shape(f["geometry"]).simplify(tolerancia, preserve_topology=True))
        for f in _ler_geojson(caminho).get("features", [])
        if f.get("geometry") and f.get("properties", {}).get("NM_MUN"))


@lru_cache(maxsize=1)
def limites_uf(caminho: Path | None = None) -> dict[str, tuple[str, object]]:
    """SIGLA_UF → (nome do estado, contorno simplificado), de ``referencia/limites_uf.geojson``."""
    caminho = Path(caminho or LIMITES_UF_GEOJSON)
    if not caminho.exists():
        return {}
    return {f["properties"]["SIGLA_UF"]: (f["properties"]["NM_UF"], shape(f["geometry"]))
            for f in _ler_geojson(caminho)["features"]}


def caminho_do_estado(sigla: str | None) -> Path | None:
    """Arquivo ``NM_UF_<Estado>.geojson`` do estado pela sigla (via ``referencia/limites_uf.geojson``)."""
    nome = limites_uf().get(sigla or "", (None,))[0]
    return estados_disponiveis().get(nome) if nome else None


def sigla_do_estado(caminho_estado: Path) -> str | None:
    municipios = municipios_simplificados(Path(caminho_estado))
    return municipios[0][1] if municipios else None

@lru_cache(maxsize=1)
def _municipios_brasil(pasta: Path, assinatura: tuple) -> tuple[list[tuple[str, str, str]], list]:
    nomes, geometrias = [], []
    for arquivo in sorted(Path(pasta).glob("NM_UF_*.geojson")):
        for feicao in _ler_geojson(arquivo).get("features", []):
            p = feicao.get("properties", {})
            if feicao.get("geometry") and p.get("NM_MUN"):
                nomes.append((str(p["NM_MUN"]).strip().upper(), str(p.get("NM_UF", "")).strip().upper(),
                              str(p.get("SIGLA_UF", "")).strip().upper()))
                geometrias.append(shape(feicao["geometry"]))
    return nomes, geometrias


def municipios_brasil(pasta: Path | None = None) -> tuple[list[tuple[str, str, str]], list]:
    """(NM_MUN, NM_UF, SIGLA_UF) em MAIÚSCULAS e geometria de todos os municípios dos ``NM_UF_*.geojson``.

    Lê ~600 MB (≈15 s) na primeira vez; fica em memória até algum arquivo mudar.
    """
    pasta = Path(pasta or pasta_municipios())
    assinatura = tuple((a.name, a.stat().st_mtime) for a in sorted(pasta.glob("NM_UF_*.geojson")))
    return _municipios_brasil(pasta, assinatura)


def indice_por_poligono(lon, lat, geometrias, menor_vence: bool = False) -> np.ndarray:
    """Índice da geometria que contém cada ponto (-1 = nenhuma).

    Ponto em mais de uma geometria (divisa, áreas sobrepostas): vence a de menor índice — ou, com
    ``menor_vence``, a de menor área (regra das colunas UC/TI; empate de área: a de maior índice). Reproduz a base consolidada (docs/03 §5).
    """
    pontos = shapely.points(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    resultado = np.full(len(pontos), -1, dtype=np.int64)
    if not len(pontos) or not len(geometrias):
        return resultado
    i_ponto, i_geom = shapely.STRtree(geometrias).query(pontos, predicate="intersects")
    if menor_vence:   # maiores primeiro; mesma área: a que vem depois no arquivo vence (como a ferramenta de UC/TI)
        ordem = np.lexsort((i_geom, -shapely.area(np.asarray(geometrias, dtype=object))[i_geom]))
    else:
        ordem = np.argsort(-i_geom, kind="stable")
    resultado[i_ponto[ordem]] = i_geom[ordem]          # a última escrita (a que vence) fica
    return resultado


# ------------------------------------------------------- Áreas protegidas

def rotulo_area_protegida(props: dict) -> str:
    """Rótulo igual ao gravado na base de focos: "NOME (CÓDIGO)".

    Manter igual a ``ferramentas/atualizar_area_protegida_focos.py`` se os campos mudarem.
    """
    for campo_nome, campo_codigo in CAMPOS_ROTULO:
        if props.get(campo_nome):
            return f"{str(props[campo_nome]).strip()} ({props.get(campo_codigo)})"
    return str(props.get("name", "")).strip()


@lru_cache(maxsize=2)
def carregar_areas_protegidas(caminho_uc: Path, caminho_ti: Path) -> tuple[dict, ...]:
    """UCs e TIs como geometrias válidas, sem feições repetidas (mesmo rótulo e mesmo limite).

    Cada item: ``{"tipo": "UC"|"TI", "nome": rótulo, "geom": geometria}``.
    """
    areas = []
    for tipo, caminho in (("UC", Path(caminho_uc)), ("TI", Path(caminho_ti))):
        if not caminho.exists():
            continue
        assinaturas = set()
        for feicao in _ler_geojson(caminho).get("features", []):
            if not feicao.get("geometry"):
                continue
            geom = make_valid(shape(feicao["geometry"]))
            nome = rotulo_area_protegida(feicao.get("properties", {})) or "Sem nome"
            # repetida = mesma área com o mesmo limite; áreas diferentes com o mesmo limite ficam as duas
            # (ex.: APA Miracema e RVS da Ventania, RJ)
            assinatura = (nome, round(geom.area, 8), tuple(round(b, 5) for b in geom.bounds))
            if geom.is_empty or assinatura in assinaturas:
                continue
            assinaturas.add(assinatura)
            areas.append({"tipo": tipo, "nome": nome, "geom": geom})
    return tuple(areas)


def areas_protegidas_padrao() -> tuple[dict, ...]:
    return carregar_areas_protegidas(caminho_uc(), caminho_ti())


def geometria_area_protegida(tipo: str, rotulo: str, areas: tuple[dict, ...] | None = None):
    """Geometria da UC/TI pelo rótulo da base de focos ("NOME (CÓDIGO)", maiúsculas)."""
    procurado = str(rotulo).strip().upper()
    for area in areas if areas is not None else areas_protegidas_padrao():
        if area["tipo"] == tipo and area["nome"].upper() == procurado:
            return area["geom"]
    return None


def areas_protegidas_no_territorio(poligono, areas) -> list[dict]:
    """UCs/TIs que se sobrepõem de fato ao território, com a parte recortada (docs/07 §6).

    Ordem: TIs e depois UCs, cada grupo da maior para a menor sobreposição; ``num`` numera o mapa.
    """
    if poligono is None:
        return []
    min_x, min_y, max_x, max_y = poligono.bounds
    shapely.prepare(poligono)
    resultado = []
    for area in areas:
        a_min_x, a_min_y, a_max_x, a_max_y = area["geom"].bounds
        if a_min_x > max_x or a_max_x < min_x or a_min_y > max_y or a_max_y < min_y:
            continue
        if not poligono.intersects(area["geom"]):
            continue
        recorte = area["geom"].intersection(poligono)
        if recorte.is_empty or (
            recorte.area < LIMIAR_SOBREPOSICAO_AREA * area["geom"].area
            and recorte.area < LIMIAR_SOBREPOSICAO_TERRITORIO * poligono.area
        ):
            continue
        area_recorte = area_km2(recorte)
        area_total = area_km2(area["geom"])
        resultado.append({
            "tipo": area["tipo"],
            "nome": area["nome"],
            "recorte": recorte,
            "area_km2": area_recorte,
            "pct_da_area": area_recorte / area_total * 100 if area_total else None,
        })
    resultado.sort(key=lambda a: (a["tipo"], -a["recorte"].area))
    for numero, area in enumerate(resultado, start=1):
        area["num"] = numero
    return resultado


# ------------------------------------------------------------------ Medidas

def area_km2(geom) -> float | None:
    """Área geodésica (elipsoide WGS84) em km²; None se indisponível."""
    if geom is None or GEOD_WGS84 is None:
        return None
    area_m2, _ = GEOD_WGS84.geometry_area_perimeter(geom)
    return abs(area_m2) / 1_000_000


def poligonos_de(geom) -> list:
    """Polígonos simples de qualquer geometria (MultiPolygon, GeometryCollection…)."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [p for parte in getattr(geom, "geoms", []) for p in poligonos_de(parte)]


def contar_focos_na_area(focos, geom) -> int:
    if geom is None or focos.empty:
        return 0
    return int(shapely.contains_xy(geom, focos["lon"].to_numpy(), focos["lat"].to_numpy()).sum())
