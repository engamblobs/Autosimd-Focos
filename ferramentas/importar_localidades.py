# -*- coding: utf-8 -*-
"""Converte os KML de localidades do IBGE (Censo 2022, um arquivo por município) em duas tabelas Parquet.

Entrada: a pasta baixada do IBGE, com uma subpasta por UF (``PA/abaetetuba_1500107_localidades_2022.kml``...).
Saída, em ``BASES_GEOJSON/localidades/`` (docs/03 §7, docs/06 §9):

- ``localidades_ibge_2022.parquet`` — um ponto por localidade (cidades, vilas, povoados, aldeias, comunidades
  quilombolas, agrovilas...). Uma mesma localidade aparece em duas pastas do KML quando também é indígena,
  quilombola ou agrovila de assentamento (ex.: "06. Povoados" e "09. Localidades Indígenas"): aqui ela é uma
  linha só, com a categoria principal e as marcas ``indigena``, ``quilombola`` e ``agrovila_pa``.
- ``territorios_quilombolas_2022.parquet`` — polígonos dos territórios quilombolas (pasta "13. Referência";
  geometria em WKB). O território que cruza vários municípios vem repetido em cada KML: fica um por código.

Os limites municipais da pasta "13. Referência" não são importados (o programa já tem os do IBGE).

    python ferramentas/importar_localidades.py PASTA_DOS_KML [--saida PASTA]
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import shapely
from shapely.geometry import Polygon

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.config import pasta_localidades  # noqa: E402
from core.localidades import (  # noqa: E402
    COLUNAS_LOCALIDADES, NOME_LOCALIDADES, NOME_QUILOMBOLAS, TEMATICAS,
)

NS = "{http://www.opengis.net/kml/2.2}"
PASTA_REFERENCIA = "13. Referência"


def _anel(texto: str) -> list[tuple[float, float]]:
    return [tuple(map(float, p.split(",")[:2])) for p in texto.split()]


def _poligonos(placemark) -> list[Polygon]:
    saida = []
    for pol in placemark.iter(NS + "Polygon"):
        externo = pol.find(f"{NS}outerBoundaryIs//{NS}coordinates")
        internos = [_anel(c.text) for c in pol.findall(f"{NS}innerBoundaryIs//{NS}coordinates")]
        if externo is not None:
            saida.append(Polygon(_anel(externo.text), internos))
    return saida


def ler_kml(arquivo: Path) -> tuple[list[dict], list[dict]]:
    """Pontos de localidade e polígonos de território quilombola de um KML municipal."""
    pontos, quilombolas, pastas = [], [], []
    for evento, el in ET.iterparse(arquivo, events=("start", "end")):
        if el.tag == NS + "Folder":
            if evento == "start":
                pastas.append(el.get("id") or "")
            else:
                pastas.pop()
                el.clear()
        elif evento == "end" and el.tag == NS + "Placemark":
            atributos = {s.get("name"): (s.text or "").strip() for s in el.iter(NS + "SimpleData")}
            ponto = el.find(f".//{NS}Point/{NS}coordinates")
            if ponto is not None:
                lon, lat = map(float, ponto.text.strip().split(",")[:2])
                pontos.append({**atributos, "lon": lon, "lat": lat})
            elif pastas and pastas[0] == PASTA_REFERENCIA and "COD_TQ" in atributos:
                quilombolas.append({"codigo": int(atributos["COD_TQ"]), "nome": atributos.get("NOM_TQ", ""),
                                    "partes": _poligonos(el)})
            el.clear()
    return pontos, quilombolas


def tabela_localidades(pontos: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(pontos)
    df["tematica"] = df["CT_LOCALIDADE"].isin(TEMATICAS)
    marcas = df.groupby("CD_LOCALIDADE")["CT_LOCALIDADE"].agg(set)
    # categoria principal: a da pasta geral (povoado, vila...); só temática quando a localidade não tem outra
    df = df.sort_values(["CD_LOCALIDADE", "tematica"]).drop_duplicates("CD_LOCALIDADE")
    df = df.assign(
        indigena=df["CD_LOCALIDADE"].map(lambda c: "Localidade Indígena" in marcas[c]),
        quilombola=df["CD_LOCALIDADE"].map(lambda c: "Localidade Quilombola" in marcas[c]),
        agrovila_pa=df["CD_LOCALIDADE"].map(lambda c: "Agrovila do PA" in marcas[c]),
    ).rename(columns={"CD_LOCALIDADE": "cd_localidade", "NM_LOCALIDADE": "nome", "CT_LOCALIDADE": "categoria",
                      "CD_MUN": "cd_mun", "NM_MUN": "municipio", "SIGLA_UF": "sigla_uf"})
    df["cd_mun"] = df["cd_mun"].astype("int32")
    df = df[COLUNAS_LOCALIDADES].sort_values(["sigla_uf", "municipio", "nome"]).reset_index(drop=True)
    for coluna in ("categoria", "municipio", "sigla_uf"):
        df[coluna] = df[coluna].astype("category")
    return df


def tabela_quilombolas(territorios: list[dict]) -> pd.DataFrame:
    por_codigo: dict[int, dict] = {}
    for t in territorios:
        atual = por_codigo.setdefault(t["codigo"], {"codigo": t["codigo"], "nome": t["nome"], "partes": []})
        atual["partes"] += t["partes"]
    linhas = []
    for t in por_codigo.values():
        geometria = shapely.make_valid(shapely.union_all(t["partes"]))
        linhas.append({"codigo": t["codigo"], "nome": t["nome"],
                       "geometria": shapely.to_wkb(shapely.set_precision(geometria, 0.000001))})
    return pd.DataFrame(linhas, columns=["codigo", "nome", "geometria"]).sort_values("codigo") \
        .reset_index(drop=True)


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("pasta", type=Path, help="pasta com as subpastas por UF e os KML municipais")
    argumentos.add_argument("--saida", type=Path, default=None, help="padrão: BASES_GEOJSON/localidades")
    a = argumentos.parse_args()
    arquivos = sorted(a.pasta.glob("*/*.kml"))
    if not arquivos:
        sys.exit(f"ERRO: nenhum KML em {a.pasta}/<UF>/")
    inicio, pontos, quilombolas = time.time(), [], []
    for i, arquivo in enumerate(arquivos, 1):
        p, q = ler_kml(arquivo)
        pontos += p
        quilombolas += q
        if i % 500 == 0:
            print(f"  {i}/{len(arquivos)} arquivos")
    saida = a.saida or pasta_localidades()
    saida.mkdir(parents=True, exist_ok=True)
    localidades = tabela_localidades(pontos)
    localidades.to_parquet(saida / NOME_LOCALIDADES, compression="zstd", index=False)
    territorios = tabela_quilombolas(quilombolas)
    territorios.to_parquet(saida / NOME_QUILOMBOLAS, compression="zstd", index=False)
    entrada_mb = sum(f.stat().st_size for f in arquivos) / 1e6
    saida_mb = sum((saida / n).stat().st_size for n in (NOME_LOCALIDADES, NOME_QUILOMBOLAS)) / 1e6
    print(f"{len(arquivos)} KML ({entrada_mb:.0f} MB) → {len(localidades)} localidades e {len(territorios)} "
          f"territórios quilombolas ({saida_mb:.1f} MB) em {saida} — {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
