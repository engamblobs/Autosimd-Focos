# -*- coding: utf-8 -*-
"""Atualiza a base de focos com os arquivos do INPE (o mesmo que o programa faz ao abrir; docs/03 §5).

Uso:
    python ferramentas/atualizar_base_inpe.py                       # só o servidor do INPE
    python ferramentas/atualizar_base_inpe.py --pasta "~/Downloads/FOCOS 2026"   # arquivos já baixados primeiro
    python ferramentas/atualizar_base_inpe.py --pasta ... --sem-internet
"""

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.atualizacao import atualizar_base  # noqa: E402
from core.config import BASES_DIR  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pasta", type=Path, help="pasta com focos_mensal_br_*.csv / focos_diario_br_*.csv")
    parser.add_argument("--sem-internet", action="store_true", help="usa só os arquivos da pasta")
    parser.add_argument("--bases", type=Path, default=BASES_DIR, help="pasta das bases (padrão: BASES_GEOJSON)")
    args = parser.parse_args()
    resultado = atualizar_base(args.bases, pasta_local=args.pasta.expanduser() if args.pasta else None,
                               online=not args.sem_internet)
    print(resultado.mensagem)
    if resultado.provisorios:
        print("Dias provisórios (serão baixados de novo):", ", ".join(f"{d:%d/%m}" for d in resultado.provisorios))
    if resultado.nao_publicados:
        print("Dias ainda sem arquivo no INPE:", ", ".join(f"{d:%d/%m}" for d in resultado.nao_publicados))
    return 0 if resultado.situacao in ("atualizada", "em_dia") else 1


if __name__ == "__main__":
    sys.exit(main())
