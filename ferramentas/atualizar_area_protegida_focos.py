"""
Atualiza o campo TI ou UC da base de focos (bdqueimadas_consolidado.parquet)
cruzando cada foco (lon/lat) com os polígonos de uma base GeoJSON.

- Rótulo gravado: "NOME (CÓDIGO)" em maiúsculas (o código desambigua nomes repetidos).
- Foco fora de qualquer polígono recebe "NONE" (padrão da base).
- Foco dentro de mais de um polígono (áreas sobrepostas) fica com o de menor área.
- Antes de sobrescrever, a base atual é copiada para BASES_GEOJSON/backup/.

Uso:
    python ferramentas/atualizar_area_protegida_focos.py TI BASES_GEOJSON/tiGEOJSON/TI-BR.geojson \
        --campo-nome terrai_nom --campo-codigo terrai_cod
"""

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from shapely.geometry import shape
from shapely.validation import make_valid

PROJETO = Path(__file__).resolve().parent.parent
PARQUET_PADRAO = PROJETO / "BASES_GEOJSON" / "bdqueimadas_consolidado.parquet"
VALOR_VAZIO = "NONE"


def carregar_poligonos(caminho, campo_nome, campo_codigo):
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    poligonos = []
    for feat in dados["features"]:
        if not feat.get("geometry"):
            continue
        props = feat["properties"]
        nome = str(props[campo_nome]).strip()
        codigo = props.get(campo_codigo) if campo_codigo else None
        rotulo = f"{nome} ({codigo})" if codigo not in (None, "") else nome
        geom = make_valid(shape(feat["geometry"]))
        poligonos.append({"rotulo": rotulo.upper(), "geom": geom})
    return poligonos


def cruzar(lon, lat, poligonos):
    """Devolve o índice do polígono de cada ponto (-1 = fora) e quantos pontos caíram em 2+."""
    indice = np.full(len(lon), -1, dtype=np.int32)
    acertos = np.zeros(len(lon), dtype=np.uint8)
    # Maiores primeiro: os menores sobrescrevem nas sobreposições
    ordem = sorted(range(len(poligonos)), key=lambda i: -poligonos[i]["geom"].area)
    for n, i in enumerate(ordem, start=1):
        geom = poligonos[i]["geom"]
        min_x, min_y, max_x, max_y = geom.bounds
        candidatos = np.flatnonzero(
            (lon >= min_x) & (lon <= max_x) & (lat >= min_y) & (lat <= max_y)
        )
        if candidatos.size:
            shapely.prepare(geom)
            dentro = candidatos[shapely.contains_xy(geom, lon[candidatos], lat[candidatos])]
            indice[dentro] = i
            acertos[dentro] = np.minimum(acertos[dentro] + 1, 255)
        if n % 100 == 0:
            print(f"  {n}/{len(poligonos)} polígonos processados")
    return indice, int((acertos > 1).sum())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("campo", choices=["TI", "UC"], help="coluna da base de focos a atualizar")
    parser.add_argument("geojson", type=Path, help="base de polígonos (GeoJSON)")
    parser.add_argument("--campo-nome", required=True, help="propriedade com o nome da área")
    parser.add_argument("--campo-codigo", help="propriedade com o código único da área")
    parser.add_argument("--parquet", type=Path, default=PARQUET_PADRAO)
    args = parser.parse_args()

    inicio = time.time()
    print(f"Lendo polígonos de {args.geojson.name}...")
    poligonos = carregar_poligonos(args.geojson, args.campo_nome, args.campo_codigo)
    print(f"  {len(poligonos)} polígonos")

    print(f"Lendo focos de {args.parquet.name}...")
    tabela = pq.read_table(args.parquet)
    lon = tabela.column("lon").to_numpy()
    lat = tabela.column("lat").to_numpy()
    antes = tabela.column(args.campo).to_pandas()
    print(f"  {len(lon):,} focos".replace(",", "."))

    print("Cruzando pontos × polígonos...")
    indice, sobrepostos = cruzar(lon, lat, poligonos)
    rotulos = np.array([p["rotulo"] for p in poligonos] + [VALOR_VAZIO], dtype=object)
    novo = rotulos[indice]  # índice -1 aponta para VALOR_VAZIO (último)

    backup = args.parquet.parent / "backup" / (
        f"{args.parquet.stem}_antes_{args.campo}_{datetime.now():%Y%m%d_%H%M%S}.parquet"
    )
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(args.parquet, backup)
    print(f"Backup da base anterior: {backup}")

    pos = tabela.schema.get_field_index(args.campo)
    tabela = tabela.set_column(pos, tabela.schema.field(pos), pa.array(novo, type=pa.string()))
    pq.write_table(tabela, args.parquet, compression="snappy")

    em_area_antes = int((antes != VALOR_VAZIO).sum())
    em_area_depois = int((indice >= 0).sum())
    print()
    print(f"Campo {args.campo} atualizado em {time.time() - inicio:.0f}s")
    print(f"  focos em alguma {args.campo}: antes {em_area_antes:,} → depois {em_area_depois:,}".replace(",", "."))
    print(f"  {args.campo}s com pelo menos 1 foco: {len(set(indice[indice >= 0])):,}".replace(",", "."))
    print(f"  focos em áreas sobrepostas (atribuídos à menor): {sobrepostos:,}".replace(",", "."))


if __name__ == "__main__":
    main()
