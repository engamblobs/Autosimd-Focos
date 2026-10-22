# -*- coding: utf-8 -*-
"""Gera ``referencia/municipios_br.csv``: municípios do Brasil com a Região Geográfica Imediata e a
Intermediária do IBGE (2017) e, no Pará, a Região de Integração (docs/06 §3, P4).

Fonte das regiões: ``referencia/fontes/regioes_geograficas_composicao_por_municipios_2017_20180911.xls``
(IBGE). O .xls é convertido com o LibreOffice (``soffice``). Os nomes vêm dos limites
``mun-brGEOJSON`` (a mesma grafia da coluna NM_MUN da base de focos), ligados pelo código IBGE.

Uso:
    python ferramentas/gerar_municipios_br.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.config import MUNICIPIOS_BR_CSV, MUNICIPIOS_PA_CSV, REFERENCIA_DIR, pasta_municipios  # noqa: E402

XLS = REFERENCIA_DIR / "fontes" / "regioes_geograficas_composicao_por_municipios_2017_20180911.xls"


def ler_xls(caminho: Path) -> pd.DataFrame:
    with tempfile.TemporaryDirectory() as pasta:
        subprocess.run(["soffice", "--headless", "--convert-to", "csv:Text - txt - csv (StarCalc):44,34,76",
                        "--outdir", pasta, str(caminho)], check=True, capture_output=True)
        return pd.read_csv(Path(pasta) / f"{caminho.stem}.csv", dtype=str)


def main():
    regioes = ler_xls(XLS)
    limites = []
    for arquivo in sorted(pasta_municipios().glob("NM_UF_*.geojson")):
        for feicao in json.loads(arquivo.read_text(encoding="utf-8"))["features"]:
            p = feicao["properties"]
            limites.append({"cd_mun": str(p["CD_MUN"]), "nm_mun": str(p["NM_MUN"]).strip().upper(),
                            "nm_uf": str(p["NM_UF"]).strip().upper(), "sigla_uf": p["SIGLA_UF"],
                            # usados só para municípios criados depois de 2017 (ex.: Boa Esperança do Norte-MT)
                            "_cd_rgi": p.get("CD_RGI") or "", "_rgi": p.get("NM_RGI") or "",
                            "_cd_rgint": p.get("CD_RGINT") or "", "_rgint": p.get("NM_RGINT") or ""})
    tabela = pd.DataFrame(limites).merge(
        regioes.rename(columns={"CD_GEOCODI": "cd_mun", "cod_rgi": "cd_rgi", "nome_rgi": "regiao_imediata",
                                "cod_rgint": "cd_rgint", "nome_rgint": "regiao_intermediaria"}
                       ).drop(columns="nome_mun"), on="cd_mun", how="left")
    faltando = tabela["regiao_imediata"].isna()
    for coluna, reserva in (("cd_rgi", "_cd_rgi"), ("regiao_imediata", "_rgi"), ("cd_rgint", "_cd_rgint"),
                            ("regiao_intermediaria", "_rgint")):
        tabela.loc[faltando, coluna] = tabela.loc[faltando, reserva]
    tabela = tabela.drop(columns=["_cd_rgi", "_rgi", "_cd_rgint", "_rgint"])
    pa = pd.read_csv(MUNICIPIOS_PA_CSV, sep=";", dtype=str)[["ibge", "regiao_integracao"]]
    tabela = tabela.merge(pa.rename(columns={"ibge": "cd_mun"}), on="cd_mun", how="left").fillna("")
    sem_regiao = tabela[tabela["regiao_imediata"] == ""]
    tabela.sort_values(["sigla_uf", "nm_mun"]).to_csv(MUNICIPIOS_BR_CSV, sep=";", index=False)
    print(f"{MUNICIPIOS_BR_CSV.relative_to(RAIZ)}: {len(tabela)} municípios, "
          f"{tabela['regiao_imediata'].ne('').sum()} com Região Imediata")
    if len(sem_regiao):
        print("Sem Região Imediata no IBGE (áreas dos limites que não são municípios):",
              ", ".join(f"{r.nm_mun}-{r.sigla_uf}" for r in sem_regiao.itertuples()))


if __name__ == "__main__":
    main()
