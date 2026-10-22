# -*- coding: utf-8 -*-
"""Região do município para o comparativo regional (docs/07 §3, P4).

- Pará: **Região de Integração** (``referencia/municipios_pa.csv``, a mesma do AutoSIMD-DESASTRE);
- demais estados: **Região Geográfica Imediata** do IBGE (2017), em ``referencia/municipios_br.csv``.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from core.config import MUNICIPIOS_BR_CSV, MUNICIPIOS_PA_CSV, UF_REGIOES_INTEGRACAO
from core.texto import chave_nome

SEM_REGIAO = "Não Identificada"
TIPO_INTEGRACAO = "Região de Integração"
TIPO_IMEDIATA = "Região Geográfica Imediata"


@lru_cache(maxsize=4)
def carregar_regioes(caminho: Path = MUNICIPIOS_PA_CSV) -> dict[str, str]:
    """Pará: nome do município (chave sem acento, maiúsculas) → Região de Integração.

    As variações de grafia da coluna ``variacoes`` (separadas por ``|``) também viram chave.
    """
    tabela = pd.read_csv(caminho, sep=";", dtype=str, keep_default_na=False)
    regioes = {}
    for linha in tabela.itertuples():
        for nome in [linha.nome_oficial, *filter(None, linha.variacoes.split("|"))]:
            regioes[chave_nome(nome)] = linha.regiao_integracao
    return regioes


@lru_cache(maxsize=2)
def carregar_regioes_imediatas(caminho: Path = MUNICIPIOS_BR_CSV) -> dict[tuple[str, str], str]:
    """(sigla da UF, chave do nome do município) → Região Geográfica Imediata."""
    tabela = pd.read_csv(caminho, sep=";", dtype=str, keep_default_na=False)
    return {(linha.sigla_uf, chave_nome(linha.nm_mun)): linha.regiao_imediata
            for linha in tabela.itertuples() if linha.regiao_imediata}


def tipo_regiao(sigla_uf) -> str:
    return TIPO_INTEGRACAO if str(sigla_uf).upper() == UF_REGIOES_INTEGRACAO else TIPO_IMEDIATA


def regiao_do_municipio(municipio: str, sigla_uf: str = UF_REGIOES_INTEGRACAO) -> str:
    """Nome da região (Integração no Pará, Imediata nos demais); "Não Identificada" se desconhecido."""
    if not municipio or not sigla_uf:
        return SEM_REGIAO
    sigla_uf = str(sigla_uf).upper()
    if sigla_uf == UF_REGIOES_INTEGRACAO:
        return carregar_regioes().get(chave_nome(municipio), SEM_REGIAO)
    return carregar_regioes_imediatas().get((sigla_uf, chave_nome(municipio)), SEM_REGIAO)


def titulo_regiao(regiao: str, sigla_uf) -> str:
    """"Região Araguaia" (Pará, o nome já diz) ou "Região Geográfica Imediata de Porto Velho"."""
    return regiao if tipo_regiao(sigla_uf) == TIPO_INTEGRACAO else f"{TIPO_IMEDIATA} de {regiao}"
