# -*- coding: utf-8 -*-
"""Todos os testes usam o recorte real de amostras/bases (ferramentas/gerar_amostras.py).

A variável precisa ser definida antes de ``core.config`` ser importado.
"""

import os
from pathlib import Path

os.environ["AUTOSIMD_FOCOS_BASES"] = str(Path(__file__).resolve().parent.parent / "amostras" / "bases")
os.environ["AUTOSIMD_FOCOS_ATUALIZAR"] = "0"     # os testes nunca acessam o servidor do INPE
os.environ["AUTOSIMD_FOCOS_SATELITE"] = "0"      # nem os tiles de satélite
