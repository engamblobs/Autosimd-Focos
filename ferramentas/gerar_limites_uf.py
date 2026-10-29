# -*- coding: utf-8 -*-
"""Gera ``referencia/limites_uf.geojson``: contorno simplificado dos 27 estados, para o mapa de localização.

União dos municípios de cada ``NM_UF_<Estado>.geojson`` (IBGE) simplificada a ~1 km — leve o bastante para ir
no pacote e desenhar o Brasil inteiro sem ler os 600 MB de limites municipais.

    python ferramentas/gerar_limites_uf.py [--pasta PASTA_DOS_MUNICIPIOS] [--tolerancia 0.01]
"""

import argparse
import json
import sys
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.config import pasta_municipios  # noqa: E402
from core.territorios import estados_disponiveis  # noqa: E402

SAIDA = RAIZ / "referencia" / "limites_uf.geojson"


def limites_uf(pasta: Path, tolerancia: float) -> dict:
    feicoes = []
    for nome, arquivo in estados_disponiveis(pasta).items():
        with open(arquivo, encoding="utf-8") as f:
            municipios = json.load(f)["features"]
        geometria = shapely.union_all([shape(m["geometry"]) for m in municipios if m.get("geometry")])
        geometria = shapely.set_precision(geometria.simplify(tolerancia, preserve_topology=True), 0.0001)
        sigla = municipios[0]["properties"]["SIGLA_UF"]
        feicoes.append({"type": "Feature", "properties": {"NM_UF": nome, "SIGLA_UF": sigla},
                        "geometry": mapping(geometria)})
        print(f"{sigla} {nome}: {len(municipios)} municípios")
    return {"type": "FeatureCollection", "name": "limites_uf",
            "descricao": f"Contorno dos estados (união dos municípios do IBGE, simplificado a {tolerancia}°)",
            "features": feicoes}


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None, help="pasta com os NM_UF_*.geojson")
    argumentos.add_argument("--tolerancia", type=float, default=0.01, help="simplificação em graus")
    a = argumentos.parse_args()
    dados = limites_uf(a.pasta or pasta_municipios(), a.tolerancia)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(dados['features'])} estados em {SAIDA} ({SAIDA.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
