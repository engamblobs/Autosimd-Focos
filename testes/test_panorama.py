# -*- coding: utf-8 -*-
"""Panorama do estado (página inicial, docs/07 §10), com a amostra real (PA e AP, 2023–2024)."""

from datetime import date

import pytest

from core.estatisticas import cobertura_base
from core.focos import carregar_focos
from core.panorama import TODAS, limite_da_regiao, panorama_estado, regioes_do_estado
from core.regioes import TIPO_IMEDIATA, TIPO_INTEGRACAO
from core.territorios import estados_disponiveis


@pytest.fixture(scope="module")
def df():
    return carregar_focos()


@pytest.fixture(scope="module")
def para(df):
    return panorama_estado(df, "Pará", 2023, 2024, TODAS, cobertura_base(df)[0])


def test_regioes_do_estado(df):
    assert len(regioes_do_estado(df, "Pará")) == 12                  # Regiões de Integração
    assert "Oiapoque" in regioes_do_estado(df, "Amapá")              # Regiões Geográficas Imediatas


def test_indicadores_do_estado(df, para):
    pa = df[df["SIGLA_UF"] == "PA"]
    assert para.regiao is None and para.nome == "Pará" and para.tipo_regiao == TIPO_INTEGRACAO
    assert para.fim_dados == date(2024, 12, 31)
    i = para.indicadores
    assert i["focos_ano_ate_data"] == (pa["ano"] == 2024).sum() == 56069
    assert i["ano_anterior_ate_data"] == (pa["ano"] == 2023).sum() == 41713
    assert i["variacao_ano_anterior_pct"] == pytest.approx((56069 - 41713) / 41713 * 100)
    assert i["ultimos_7"] == (pa["data"] >= "2024-12-25").sum()
    assert i["municipios_com_focos"] == 141
    assert para.serie_anual == {2023: 41713, 2024: 56069}


def test_tabela_por_regiao(para):
    tabela = para.por_regiao
    assert len(tabela) == 12
    assert tabela["Focos (2024)"].sum() == 56069
    assert tabela["% do estado (2024)"].sum() == pytest.approx(100, abs=0.2)
    assert list(tabela.columns)[1] == TIPO_INTEGRACAO


def test_filtro_por_regiao(df):
    xingu = panorama_estado(df, "Pará", 2023, 2024, "Região Xingu")
    assert xingu.nome == "Região Xingu" and xingu.por_regiao.empty
    assert set(xingu.focos["regiao"]) == {"Região Xingu"}
    assert xingu.ranking_municipios["Município"].tolist()[:3] == ["Altamira", "Pacajá", "Uruará"]
    assert xingu.indicadores["focos_ano_ate_data"] == 10821


def test_outro_estado_usa_regioes_imediatas(df):
    amapa = panorama_estado(df, "Amapá", 2023, 2024)
    assert amapa.tipo_regiao == TIPO_IMEDIATA and amapa.sigla_uf == "AP"
    assert TIPO_IMEDIATA in amapa.por_regiao.columns


def test_media_ignora_ano_sem_cobertura_desde_janeiro(df):
    """A média do mesmo período não usa anos que a base não cobre desde 1º de janeiro."""
    p = panorama_estado(df, "Pará", 2022, 2024, inicio_base=date(2023, 1, 1))     # a amostra começa em 2023
    assert p.indicadores["media_ate_data"] == 41713


def test_limite_da_regiao():
    caminho = estados_disponiveis()["Pará"]
    assert limite_da_regiao(caminho, "PA", None) is not None
    assert limite_da_regiao(caminho, "PA", "Região Xingu") is not None          # Altamira na amostra
    assert limite_da_regiao(caminho, "PA", "Região Guajará") is None            # sem limite na amostra
