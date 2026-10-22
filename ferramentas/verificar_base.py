# -*- coding: utf-8 -*-
"""Confere se as colunas NM_MUN, NM_UF, SIGLA_UF, UC e TI da base de focos são o cruzamento
ponto-no-polígono com os limites (IBGE, CNUC, FUNAI) — docs/07 §1 (P13).

Se tudo bater, as colunas são o cruzamento já calculado e o programa pode filtrar por elas
(rápido) sem mudar a metodologia. Diferenças são listadas por coluna.

Uso:
    python ferramentas/verificar_base.py [--anos 2024 2025]
"""

import argparse
import sys
import time
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.atualizacao import no_formato_da_base  # noqa: E402
from core.focos import carregar_focos  # noqa: E402


def verificar(df, progresso=print) -> dict[str, int]:
    """Número de focos em que cada coluna difere do cruzamento com os polígonos."""
    inicio = time.time()
    refeito = no_formato_da_base(df[["lon", "lat", "data"]].reset_index(drop=True))
    progresso(f"  cruzamento de {len(df):,} focos em {time.time() - inicio:.0f}s".replace(",", "."))
    return {c: int((refeito[c].to_numpy() != df[c].to_numpy()).sum())
            for c in ("NM_MUN", "NM_UF", "SIGLA_UF", "UC", "TI")}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--anos", type=int, nargs="*", help="só estes anos (padrão: a base inteira)")
    args = parser.parse_args()
    df = carregar_focos()
    if args.anos:
        df = df[df["ano"].isin(args.anos)]
    print(f"Conferindo {len(df):,} focos...".replace(",", "."))
    diferencas = {}
    for ano in sorted(df["ano"].unique()):
        do_ano = df[df["ano"] == ano]
        for coluna, n in verificar(do_ano, progresso=lambda _: None).items():
            diferencas[coluna] = diferencas.get(coluna, 0) + n
        print(f"  {ano}: {len(do_ano):,} focos conferidos".replace(",", "."), flush=True)
    sem_municipio = int((df["NM_MUN"] == "NONE").sum())
    print(f"Focos sem município (NONE) na base: {sem_municipio}")
    for coluna, n in diferencas.items():
        print(f"  {coluna}: {'OK' if n == 0 else f'{n} diferença(s)'}")
    return 0 if not any(diferencas.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
