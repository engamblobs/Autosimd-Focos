"""
===============================================================================
AUTOSIMD-FOCOS - Automação de Análise de Focos de Calor Municipal
Desenvolvimento: Sala de Informações e Monitoramento de Desastres (SIMD)
                 Defesa Civil Estadual do Pará (CEDEC/PA)
===============================================================================
"""

from pathlib import Path

# Metadados do Projeto
APP_NAME = "autosimd-focos"
APP_VERSION = "1.0.0"
ORGANIZATION = "Sala de Informações e Monitoramento de Desastres (SIMD)"
ENTITY = "Defesa Civil Estadual do Pará (CEDEC/PA)"

# Caminhos Padrão de Dados
DATA_DIR = Path("/home/lobs/SIG/FOCOS DE CALOR")
STATE_TARGET = "PARÁ"
YEAR_START = 2006
YEAR_END = 2026