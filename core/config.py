# -*- coding: utf-8 -*-
"""Caminhos e constantes do AutoSIMD-FOCOS."""

import os
from pathlib import Path

APP_NOME = "AutoSIMD-FOCOS"
APP_VERSAO = "0.11"
APP_VERSAO_DATA = "22/10/2026"
REPOSITORIO = "https://github.com/engamblobs/Autosimd-Focos"

# Faixa de portas própria (8501 é o padrão do Streamlit; o AutoSIMD-DESASTRE usa 8571–8620)
PORTA_INICIAL = 8521
PORTA_FINAL = 8570

# Desenvolvedor (mesmo dos projetos AutoSIMD-DESASTRE e AutoSIMD-HIDRO); usado no "Sobre" e no PDF
DESENVOLVEDOR_NOME = "Bruno Lobão da Silva"
DESENVOLVEDOR_FUNCOES = [
    "Soldado do Corpo de Bombeiros Militar do Pará (CBMPA)",
    "Técnico de Defesa Civil — CEDEC/PA (DGR / SIMD)",
    "Bacharel em Eng. Ambiental e Energias Renováveis (UFRA)",
    "Mestrando em Gestão de Riscos e Desastres Naturais na Amazônia (UFPA)",
]
DESENVOLVEDOR_EMAIL = "engamb.lobs@gmail.com"
DESENVOLVEDOR_LATTES = "http://lattes.cnpq.br/9038468130657451"
EMAIL_SALA_MONITORAMENTO = "simdcedec@gmail.com"
TELEFONE_PLANTAO = "(91) 98899-6323"

RAIZ = Path(__file__).resolve().parent.parent

# Tabelas fixas versionadas
REFERENCIA_DIR = RAIZ / "referencia"
MUNICIPIOS_PA_CSV = REFERENCIA_DIR / "municipios_pa.csv"   # mesma tabela do AutoSIMD-DESASTRE
MUNICIPIOS_BR_CSV = REFERENCIA_DIR / "municipios_br.csv"   # Regiões Imediatas do IBGE (ferramentas/gerar_municipios_br.py)
LOGOS_DIR = REFERENCIA_DIR / "logos"
LOGO_APP = LOGOS_DIR / "AUTOSIMD-FOCOS.png"
LOGO_CBM_CEDEC = LOGOS_DIR / "CBM-CEDEC.png"
ICONE_APP = LOGOS_DIR / "AutoSIMD-FOCOS.ico"

# Bases de dados (grandes, fora do git; vão no pacote Windows). A pasta pode ser trocada por
# variável de ambiente — os testes apontam para amostras/bases.
BASES_DIR = Path(os.environ.get("AUTOSIMD_FOCOS_BASES", RAIZ / "BASES_GEOJSON"))
NOME_FOCOS_PARQUET = "bdqueimadas_consolidado.parquet"
NOME_MUNICIPIOS_DIR = "mun-brGEOJSON"          # um NM_UF_<Estado>.geojson por estado
NOME_UC_GEOJSON = "ucGEOJSON/UC-BR.geojson"    # CNUC/MMA, todo o Brasil
NOME_TI_GEOJSON = "tiGEOJSON/TI-BR.geojson"    # FUNAI, todo o Brasil


def caminho_focos(bases_dir: Path | None = None) -> Path:
    return Path(bases_dir or BASES_DIR) / NOME_FOCOS_PARQUET


def pasta_municipios(bases_dir: Path | None = None) -> Path:
    return Path(bases_dir or BASES_DIR) / NOME_MUNICIPIOS_DIR


def caminho_uc(bases_dir: Path | None = None) -> Path:
    return Path(bases_dir or BASES_DIR) / NOME_UC_GEOJSON


def caminho_ti(bases_dir: Path | None = None) -> Path:
    return Path(bases_dir or BASES_DIR) / NOME_TI_GEOJSON


# Busca automática dos focos novos no INPE sempre que o programa é aberto (docs/03 §5); 0 desliga (testes)
ATUALIZACAO_AUTOMATICA = os.environ.get("AUTOSIMD_FOCOS_ATUALIZAR", "1") != "0"
# Imagem de satélite de fundo no mapa do cenário atual; 0 desliga (testes, sem internet)
FUNDO_SATELITE = os.environ.get("AUTOSIMD_FOCOS_SATELITE", "1") != "0"
# Fonte da imagem (P22): Sentinel-2 cloudless da EOX, licença Creative Commons CC BY-NC-SA 4.0 (uso não comercial
# com crédito). Para trocar o ano ou a fonte, mude só estas duas linhas ({z}/{y}/{x} = nível/linha/coluna XYZ).
URL_SATELITE = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg"
CREDITO_SATELITE = ("Imagem: Sentinel-2 cloudless 2024 (s2maps.eu) por EOX IT Services GmbH, CC BY-NC-SA 4.0 — "
                    "contém dados Copernicus Sentinel modificados (2024)")

# Densidade de kernel dos mapas (P21) — para ajustar, mude aqui
KERNEL_DESVIO_KM = 5.0           # desvio padrão do kernel gaussiano
KERNEL_CELULA_KM = 1.0           # tamanho da célula do raster
KERNEL_MAX_CELULAS = 500         # máximo de células por lado (territórios grandes ganham células maiores)
KERNEL_MAX_CRUZES = 2000         # acima disso os focos não são marcados com cruzes

# Recorte pequeno das bases reais, usado nos testes (ferramentas/gerar_amostras.py)
AMOSTRAS_DIR = RAIZ / "amostras"
AMOSTRAS_BASES = AMOSTRAS_DIR / "bases"

# Níveis de análise (docs/02)
TIPO_MUNICIPIO = "Estado / Município"
TIPO_UC = "Unidade de Conservação (UC)"
TIPO_TI = "Terra Indígena (TI)"
TIPOS_ANALISE = [TIPO_MUNICIPIO, TIPO_UC, TIPO_TI]
SIGLA_TIPO = {TIPO_MUNICIPIO: "MUN", TIPO_UC: "UC", TIPO_TI: "TI"}

# Regras de negócio (docs/07)
UF_REGIOES_INTEGRACAO = "PA"              # Regiões de Integração só existem no Pará
VALORES_VAZIOS = {"", "NONE", "NULL", "NAN", "N/A"}
TAMANHO_CELULA_KM = 10            # grade ajustada à latitude (core/grade.py, P8)
# Frações mínimas de sobreposição para descartar "lascas" de borda entre limites que só se tocam
# (relativas à área protegida e ao território analisado)
LIMIAR_SOBREPOSICAO_AREA = 0.02
LIMIAR_SOBREPOSICAO_TERRITORIO = 0.01
TOP_ESTADO = 5
