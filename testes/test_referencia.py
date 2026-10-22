# -*- coding: utf-8 -*-
"""Tabelas fixas: Regiões de Integração (referencia/municipios_pa.csv), logos e formatação."""

import pandas as pd
import pytest

from core import config
from core.focos import carregar_focos, municipios_da_uf
from core.regioes import (
    SEM_REGIAO, TIPO_IMEDIATA, TIPO_INTEGRACAO, carregar_regioes, regiao_do_municipio, tipo_regiao, titulo_regiao,
)
from core.texto import (
    chave_nome, fmt_densidade, fmt_milhar_eixo, fmt_numero, fmt_percentual, fmt_posicao, nome_arquivo,
)


def test_municipios_pa_tem_144_e_12_regioes():
    tabela = pd.read_csv(config.MUNICIPIOS_PA_CSV, sep=";", dtype=str)
    assert len(tabela) == 144
    assert tabela["regiao_integracao"].nunique() == 12
    assert len(carregar_regioes()) == 144


def test_todo_municipio_do_pa_na_base_tem_regiao():
    for municipio in municipios_da_uf(carregar_focos(), "Pará"):
        assert regiao_do_municipio(municipio) != SEM_REGIAO, municipio


@pytest.mark.parametrize("nome, regiao", [
    ("SÃO FÉLIX DO XINGU", "Região Araguaia"),
    ("sao felix do xingu", "Região Araguaia"),        # sem acento e minúsculas
    ("PAU D'ARCO", "Região Araguaia"),
    ("BELÉM", "Região Guajará"),
    ("NOVO PROGRESSO", "Região Tapajós"),
])
def test_regiao_do_municipio(nome, regiao):
    assert regiao_do_municipio(nome) == regiao


def test_regiao_de_integracao_no_para_e_imediata_nos_demais():
    """P4: fora do Pará, Região Geográfica Imediata do IBGE (2017)."""
    assert regiao_do_municipio("BONITO", "PA") == "Região Rio Caeté"
    assert regiao_do_municipio("BONITO", "BA") == "Irecê"          # homônimo em outro estado
    assert regiao_do_municipio("PORTO VELHO", "RO") == "Porto Velho"
    assert regiao_do_municipio("BOA ESPERANÇA DO NORTE", "MT") == "Sorriso"    # criado depois de 2017
    assert regiao_do_municipio("", "PA") == SEM_REGIAO
    assert regiao_do_municipio("NAO EXISTE", "BA") == SEM_REGIAO
    assert tipo_regiao("PA") == TIPO_INTEGRACAO and tipo_regiao("ba") == TIPO_IMEDIATA
    assert titulo_regiao("Irecê", "BA") == "Região Geográfica Imediata de Irecê"
    assert titulo_regiao("Região Araguaia", "PA") == "Região Araguaia"


def test_municipios_br():
    tabela = pd.read_csv(config.MUNICIPIOS_BR_CSV, sep=";", dtype=str, keep_default_na=False)
    assert len(tabela) == 5573 and tabela["cd_mun"].is_unique
    assert (tabela["regiao_imediata"] == "").sum() == 2                       # as duas lagoas do RS
    assert not tabela.duplicated(["sigla_uf", "nm_mun"]).any()
    pa = tabela[tabela["sigla_uf"] == "PA"]
    assert len(pa) == 144 and (pa["regiao_integracao"] != "").all()


def test_logos_existem():
    for caminho in (config.LOGO_APP, config.LOGO_CBM_CEDEC, config.ICONE_APP):
        assert caminho.is_file(), caminho


def test_formatacao_brasileira():
    assert fmt_numero(1234567.891, 1) == "1.234.567,9"
    assert fmt_percentual(4.5138) == "4,5%"
    assert fmt_percentual(-88.73, sinal=True) == "-88,7%"
    assert fmt_percentual(None) == "—"
    assert fmt_posicao(4, 4288) == "4º de 4288"
    assert fmt_posicao(0, 141) == "Sem focos"
    assert fmt_densidade(0.0604257) == "0,060"
    assert fmt_densidade(None) == "—"
    assert [fmt_milhar_eixo(v) for v in (0, 500, 2000, 2500)] == ["0", "500", "2 mil", "2,5 mil"]


def test_nomes():
    assert chave_nome("  São Félix do Xingu ") == "SAO FELIX DO XINGU"
    assert nome_arquivo("SÃO FÉLIX DO XINGU") == "SAO_FELIX_DO_XINGU"
    assert nome_arquivo("ESTAÇÃO ECOLÓGICA DA TERRA DO MEIO (47)") == "ESTACAO_ECOLOGICA_DA_TERRA_DO_MEIO_47"
    assert nome_arquivo("???") == "SELECIONADO"
