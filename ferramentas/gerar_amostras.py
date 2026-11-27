# -*- coding: utf-8 -*-
"""Gera ``amostras/bases/`` — recorte pequeno das bases reais, com a mesma estrutura de BASES_GEOJSON/.

Usado pelos testes (docs/04 §3). Conteúdo:
- focos do Pará e do Amapá em ANOS (inclui os focos sem município/UF desses anos);
- polígonos de MUNICIPIOS_PA e MUNICIPIOS_AP;
- UCs e TIs que tocam esses municípios;
- localidades do IBGE desses municípios e os territórios quilombolas que os tocam (só se a base existir).

Uso:
    python ferramentas/gerar_amostras.py [--so-localidades]
"""

import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.config import (  # noqa: E402
    AMOSTRAS_BASES, NOME_FOCOS_PARQUET, NOME_LOCALIDADES_DIR, NOME_MUNICIPIOS_DIR, NOME_TI_GEOJSON, NOME_UC_GEOJSON,
)
from core.localidades import NOME_LOCALIDADES, NOME_QUILOMBOLAS  # noqa: E402

ORIGEM = RAIZ / "BASES_GEOJSON"
ANOS = [2023, 2024]
UFS = ["PA", "AP", "NONE"]
MUNICIPIOS_PA = ["São Félix do Xingu", "Altamira", "Novo Progresso"]
MUNICIPIOS_AP = ["Oiapoque"]


def gravar_geojson(original: dict, feicoes: list, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)
    saida = {k: v for k, v in original.items() if k != "features"} | {"features": feicoes}
    destino.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print(f"  {destino.relative_to(RAIZ)}: {len(feicoes)} feições, {destino.stat().st_size / 1e6:.1f} MB")


def uniao_dos_municipios():
    territorios = []
    for estado, nomes in (("Pará", MUNICIPIOS_PA), ("Amapá", MUNICIPIOS_AP)):
        dados = json.loads((ORIGEM / f"{NOME_MUNICIPIOS_DIR}/NM_UF_{estado}.geojson").read_text(encoding="utf-8"))
        territorios += [shape(f["geometry"]) for f in dados["features"] if f["properties"]["NM_MUN"] in nomes]
    return unary_union(territorios)


def amostrar_localidades(uniao):
    origem, destino = ORIGEM / NOME_LOCALIDADES_DIR, AMOSTRAS_BASES / NOME_LOCALIDADES_DIR
    if not (origem / NOME_LOCALIDADES).exists():
        print(f"  (sem {origem / NOME_LOCALIDADES}: amostra de localidades não gerada)")
        return
    destino.mkdir(parents=True, exist_ok=True)
    localidades = pd.read_parquet(origem / NOME_LOCALIDADES)
    nomes = MUNICIPIOS_PA + MUNICIPIOS_AP
    amostra = localidades[localidades["municipio"].isin(nomes)].reset_index(drop=True)
    amostra.to_parquet(destino / NOME_LOCALIDADES, compression="zstd", index=False)
    quilombolas = pd.read_parquet(origem / NOME_QUILOMBOLAS)
    tocam = shapely.intersects(shapely.from_wkb(quilombolas["geometria"].to_numpy()), uniao)
    quilombolas[tocam].reset_index(drop=True).to_parquet(destino / NOME_QUILOMBOLAS, compression="zstd", index=False)
    print(f"  {destino.relative_to(RAIZ)}: {len(amostra)} localidades, {int(tocam.sum())} territórios quilombolas")


def main():
    if "--so-localidades" in sys.argv:
        amostrar_localidades(uniao_dos_municipios())
        return
    if AMOSTRAS_BASES.exists():
        shutil.rmtree(AMOSTRAS_BASES)

    tabela = pq.read_table(ORIGEM / NOME_FOCOS_PARQUET)
    filtro = pc.and_(pc.is_in(tabela["ano"], value_set=pa.array(ANOS, type=tabela["ano"].type)),
                     pc.is_in(tabela["SIGLA_UF"], value_set=pa.array(UFS)))
    amostra = tabela.filter(filtro)
    destino = AMOSTRAS_BASES / NOME_FOCOS_PARQUET
    destino.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(amostra, destino, compression="zstd")
    print(f"  {destino.relative_to(RAIZ)}: {amostra.num_rows} focos, {destino.stat().st_size / 1e6:.1f} MB")

    territorios = []
    for estado, nomes in (("Pará", MUNICIPIOS_PA), ("Amapá", MUNICIPIOS_AP)):
        arquivo = f"{NOME_MUNICIPIOS_DIR}/NM_UF_{estado}.geojson"
        dados = json.loads((ORIGEM / arquivo).read_text(encoding="utf-8"))
        feicoes = [f for f in dados["features"] if f["properties"]["NM_MUN"] in nomes]
        territorios += [shape(f["geometry"]) for f in feicoes]
        gravar_geojson(dados, feicoes, AMOSTRAS_BASES / arquivo)
    uniao = unary_union(territorios)

    for arquivo in (NOME_UC_GEOJSON, NOME_TI_GEOJSON):
        dados = json.loads((ORIGEM / arquivo).read_text(encoding="utf-8"))
        feicoes = [f for f in dados["features"] if f.get("geometry") and shape(f["geometry"]).intersects(uniao)]
        gravar_geojson(dados, feicoes, AMOSTRAS_BASES / arquivo)
    amostrar_localidades(uniao)


if __name__ == "__main__":
    main()
