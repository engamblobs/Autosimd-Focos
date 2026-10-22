# -*- coding: utf-8 -*-
"""Indicadores, rankings e séries do diagnóstico (docs/07), com a amostra real (PA e AP, 2023–2024)."""

from datetime import date

import pandas as pd
import pytest

from core.config import TIPO_TI, TIPO_UC
from core.diagnostico import (
    diagnosticar_area, diagnosticar_municipio, distribuicao_mensal, posicao, ranking, ranking_areas_protegidas,
    ranking_simples, serie_anual,
)
from core.focos import carregar_focos, no_periodo
from core.regioes import TIPO_IMEDIATA, TIPO_INTEGRACAO
from core.territorios import (
    areas_protegidas_no_territorio, areas_protegidas_padrao, estados_disponiveis, geometria_area_protegida,
    geometria_municipio,
)


@pytest.fixture(scope="module")
def df():
    return carregar_focos()


def diagnostico(df, estado, municipio, ano_inicio=2023, ano_fim=2024):
    poligono = geometria_municipio(estados_disponiveis()[estado], municipio)
    areas = areas_protegidas_no_territorio(poligono, areas_protegidas_padrao())
    return diagnosticar_municipio(df, estado, municipio, ano_inicio, ano_fim, poligono, areas)


@pytest.fixture(scope="module")
def sao_felix(df):
    return diagnostico(df, "Pará", "SÃO FÉLIX DO XINGU")


def test_resumo_sao_felix(sao_felix):
    r = sao_felix.resumo
    assert (r.focos_ano_fim, r.focos_ano_anterior, r.focos_periodo) == (7356, 2898, 10254)
    assert r.variacao_pct == pytest.approx((7356 - 2898) / 2898 * 100)
    assert r.participacao_estado_pct == pytest.approx(13.1195, abs=1e-4)
    assert (r.posicao_estado, r.total_estado) == (1, 141)
    assert (r.posicao_pais, r.total_pais) == (1, 157)         # 141 do PA + 16 do AP
    assert r.media_anual == 5127.0
    assert r.densidade == pytest.approx(5127 / r.area_km2)
    assert sao_felix.regiao == "Região Araguaia" and sao_felix.tipo_regiao == TIPO_INTEGRACAO
    assert sao_felix.sigla_uf == "PA" and sao_felix.fim_dados == date(2024, 12, 31)


def test_series(sao_felix):
    assert sao_felix.serie_anual == {2023: 2898, 2024: 7356}
    assert sum(sao_felix.mensal.values()) == 10254
    assert max(sao_felix.mensal, key=sao_felix.mensal.get) == 9           # setembro


def test_rankings_do_estado(sao_felix):
    estado = sao_felix.ranking_estado
    assert list(estado.columns) == ["Posição", "Município", "Região", "Focos (2024)", "Acumulado"]
    assert estado["Município"].tolist() == ["São Félix Do Xingu", "Altamira", "Novo Progresso", "Itaituba", "Portel"]
    assert estado.loc[0, "Acumulado"] == 10254
    assert sao_felix.top_acumulado[:3] == [("São Félix Do Xingu", 10254), ("Altamira", 9549),
                                           ("Novo Progresso", 5923)]
    regiao = sao_felix.ranking_regiao
    assert len(regiao) == 15 and regiao.loc[0, "Município"] == "São Félix Do Xingu"


def test_empate_decidido_pelo_ultimo_mes(df):
    """P2: Mojuí dos Campos e Senador José Porfírio têm 401 focos em 2024; Mojuí teve mais em dezembro."""
    tabela = ranking(df[(df["ano"] == 2024) & (df["SIGLA_UF"] == "PA")], "NM_MUN", date(2024, 12, 31))
    mojui, senador = tabela.loc["MOJUÍ DOS CAMPOS"], tabela.loc["SENADOR JOSÉ PORFÍRIO"]
    assert mojui["focos"] == senador["focos"] == 401
    assert mojui["ultimo_mes"] > senador["ultimo_mes"]
    assert senador["posicao"] == mojui["posicao"] + 1


def test_regra_de_desempate_completa():
    focos = pd.DataFrame({"m": list("AAABBBCCD"), "data": [
        "2024-01-01", "2024-12-01", "2024-12-30",      # A: 3 focos, 2 no último mês, 1 na última semana
        "2024-01-01", "2024-12-02", "2024-12-31",      # B: igual a A
        "2024-12-29", "2024-12-30",                    # C: 2 focos
        "2024-06-01"]})                                # D: 1 foco
    tabela = ranking(focos, "m", date(2024, 12, 31))
    assert tabela["posicao"].to_dict() == {"A": 1, "B": 1, "C": 3, "D": 4}   # A e B empatam nos três critérios
    focos.loc[5, "data"] = "2024-12-20"                                      # B perde o foco da última semana
    tabela = ranking(focos, "m", date(2024, 12, 31))
    assert tabela["posicao"].to_dict() == {"A": 1, "B": 2, "C": 3, "D": 4}
    assert posicao(tabela, "X") == 0


def test_tabela_areas(sao_felix):
    t = sao_felix.tabela_areas
    assert len(t) == 12
    kayapo = t.iloc[0]
    assert (kayapo["Nome"], kayapo["Focos em 2024"], kayapo["Focos 2023–2024"]) == ("Kayapó (23001)", 1129, 1183)


def test_municipio_de_outro_estado_usa_a_regiao_imediata(df):
    """P4: fora do Pará, Região Geográfica Imediata do IBGE."""
    d = diagnostico(df, "Amapá", "OIAPOQUE")
    assert d.sigla_uf == "AP"
    assert (d.regiao, d.tipo_regiao) == ("Oiapoque", TIPO_IMEDIATA)
    assert d.titulo_regiao == "Região Geográfica Imediata de Oiapoque"
    assert d.ranking_regiao["Município"].tolist() == ["Calçoene", "Tartarugalzinho", "Oiapoque", "Amapá",
                                                      "Pracuúba", "Cutias"]
    assert (d.resumo.posicao_estado, d.resumo.total_estado) == (6, 16)


def test_variacao_sem_ano_anterior_no_periodo(df):
    r = diagnostico(df, "Pará", "ALTAMIRA", 2024, 2024).resumo
    assert r.focos_ano_anterior is None and r.variacao_pct is None


def test_municipio_sem_poligono_nao_tem_densidade(df):
    d = diagnosticar_municipio(df, "Pará", "BELÉM", 2023, 2024)             # sem limite na amostra
    assert d.resumo.area_km2 is None and d.resumo.densidade is None
    assert d.resumo.focos_periodo == 15 and d.areas == []


def test_focos_sem_municipio_ficam_fora_do_ranking_nacional(df):
    assert (df["NM_MUN"] == "NONE").sum() == 24
    assert diagnostico(df, "Pará", "ALTAMIRA").resumo.total_pais == 157


def test_rankings_de_areas_no_estado_e_no_brasil(sao_felix):
    """P6: UCs e TIs com focos no estado e no Brasil inteiro."""
    r = sao_felix.rankings_areas
    assert set(r) == {"UC_estado", "UC_brasil", "TI_estado", "TI_brasil"}
    assert len(r["UC_estado"]) == 65 and len(r["UC_brasil"]) == 73        # o Brasil inclui as do Amapá
    assert r["TI_estado"].iloc[0, 1] == "KAYAPÓ (23001)"
    assert r["UC_estado"]["Participação (%)"].sum() == pytest.approx(100, abs=0.1)


def test_series_com_zeros():
    focos = pd.DataFrame({"ano": [2020, 2020, 2022], "mes": [8, 8, 9]})
    assert serie_anual(focos, 2019, 2022) == {2019: 0, 2020: 2, 2021: 0, 2022: 1}
    assert distribuicao_mensal(focos)[8] == 2 and distribuicao_mensal(focos)[1] == 0


def test_ranking_simples_ignora_vazios(df):
    tabela = ranking_simples(df, "UC")
    assert "NONE" not in tabela["UC"].tolist()
    assert tabela.loc[0, "UC"] == "ÁREA DE PROTEÇÃO AMBIENTAL TRIUNFO DO XINGU (1039)"


def test_ranking_areas_protegidas(df):
    ranking_ti = ranking_areas_protegidas(no_periodo(df, 2023, 2024), "TI", TIPO_TI)
    assert list(ranking_ti.columns) == ["Posição", TIPO_TI, "Focos de Calor", "Participação (%)"]
    assert ranking_ti.loc[0, TIPO_TI] == "KAYAPÓ (23001)"
    assert ranking_areas_protegidas(df.iloc[0:0], "UC", TIPO_UC).empty


def test_diagnostico_area(df):
    d = diagnosticar_area(df, TIPO_TI, "Kayapó (23001)", 2023, 2024, geometria_area_protegida("TI", "KAYAPÓ (23001)"))
    assert d.nome == "KAYAPÓ (23001)" and d.campo == "TI" and d.sigla_uf == "PA"
    assert d.serie_anual == {2023: 139, 2024: 3259}
    assert (d.focos_ano_fim, d.focos_periodo, d.media_anual) == (3259, 3398, 1699.0)
    assert d.rankings_areas["TI_estado"].iloc[0, 1] == "KAYAPÓ (23001)"
