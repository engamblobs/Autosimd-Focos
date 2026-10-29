# -*- coding: utf-8 -*-
"""Estatísticas no modelo do Programa Queimadas/INPE (docs/07 §8), para município e área protegida."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
import shapely

from core.estatisticas import (
    ParametrosEstatisticas, cobertura_base, estatisticas_territorio, extremos_por_coluna, matriz_periodos, notas,
    resolver_parametros, tabela_acumulado_exibicao, tabela_comparativo_exibicao, tabela_diaria_exibicao,
    tabela_mensal_exibicao,
)
from core.focos import carregar_focos, focos_da_area, focos_do_municipio
from core.graficos_estatisticas import (
    figuras_estatisticas, interativo_acumulado, interativo_comparativo,
)
from core.produto import fechar_figuras
from core.territorios import estados_disponiveis, geometria_area_protegida, geometria_municipio

MUNICIPIO = "SÃO FÉLIX DO XINGU"


@pytest.fixture(scope="module")
def df():
    return carregar_focos()


@pytest.fixture(scope="module")
def cobertura(df):
    return cobertura_base(df)


@pytest.fixture(scope="module")
def focos(df):
    return focos_do_municipio(df, "Pará", MUNICIPIO)


@pytest.fixture(scope="module")
def est(focos, cobertura):
    return estatisticas_territorio(focos, MUNICIPIO, 2023, 2024, cobertura)


def test_cobertura_da_amostra(cobertura):
    assert cobertura == (date(2023, 1, 1), date(2024, 12, 31))


@pytest.mark.parametrize("estado, municipio", [("Pará", "SÃO FÉLIX DO XINGU"), ("Pará", "ALTAMIRA"),
                                               ("Pará", "NOVO PROGRESSO"), ("Amapá", "OIAPOQUE")])
def test_coluna_do_municipio_e_o_cruzamento_com_o_poligono(df, estado, municipio):
    """P13: os focos do município pela coluna NM_MUN são exatamente os que caem no polígono."""
    poligono = geometria_municipio(estados_disponiveis()[estado], municipio)
    dentro = shapely.contains_xy(poligono, df["lon"].to_numpy(), df["lat"].to_numpy())
    assert len(focos_do_municipio(df, estado, municipio)) == int(dentro.sum())


def test_tabela_mes_a_mes(est, focos):
    datas = pd.to_datetime(focos["data"])
    assert est.mensal.loc[2024, 8] == ((datas.dt.year == 2024) & (datas.dt.month == 8)).sum()
    assert est.mensal["Total"].sum() == len(focos)
    assert list(est.mensal.columns) == list(range(1, 13)) + ["Total"]
    # referência padrão = ano final; mínimo/média/máximo só com os outros anos (aqui, só 2023)
    assert est.ano_referencia == 2024 and est.anos_estatistica == [2023]
    assert (est.resumo_mensal.loc["Média"] == est.mensal.loc[2023]).all()
    tabela = tabela_mensal_exibicao(est)
    assert tabela.index.tolist() == ["2023", "2024", "Mínimo", "Média", "Máximo"]
    assert tabela.columns[0] == "Janeiro" and tabela.columns[-1] == "Total"


def test_meses_fora_da_cobertura_ficam_vazios(focos, cobertura):
    e = estatisticas_territorio(focos, MUNICIPIO, 2022, 2024, cobertura)   # a amostra começa em 2023
    assert e.mensal.loc[2022, list(range(1, 13))].isna().all()
    assert np.isnan(e.mensal.loc[2022, "Total"])
    assert 2022 in e.anos_parciais
    assert e.resumo_mensal.loc["Mínimo", 8] == e.mensal.loc[2023, 8]   # vazio não conta como zero


def test_dia_a_dia(est, focos):
    assert est.parametros.mes_diario == 12                  # último mês com dados
    diario = tabela_diaria_exibicao(est)
    assert diario.index.tolist() == ["12/2023", "12/2024"]
    datas = pd.to_datetime(focos["data"])
    dez_2024 = datas[(datas.dt.year == 2024) & (datas.dt.month == 12)]
    assert diario.loc["12/2024", "Total"] == len(dez_2024)
    assert diario.loc["12/2024", "31"] == (dez_2024.dt.day == 31).sum()


def test_dia_a_dia_dias_inexistentes(focos, cobertura):
    e = estatisticas_territorio(focos, MUNICIPIO, 2023, 2024, cobertura, ParametrosEstatisticas(mes_diario=2))
    assert np.isnan(e.diario.loc["02/2023", 29])            # 2023 não é bissexto
    assert not np.isnan(e.diario.loc["02/2024", 29])
    assert np.isnan(e.diario.loc["02/2024", 30])


def test_comparativos_mensal_semanal_e_semestres(est):
    """P12: mensal, semanal e os dois semestres em semanas (blocos de 7 dias desde 01/01 e 01/07)."""
    c = est.comparativos
    assert set(c) == {"mensal", "semanal", "semestre1", "semestre2"}
    assert (len(c["mensal"]), len(c["semanal"]), len(c["semestre1"]), len(c["semestre2"])) == (12, 53, 26, 27)
    assert c["semestre1"]["rotulo"].iloc[0] == "1" and c["semestre2"]["rotulo"].iloc[-1] == "27"
    for unidade in ("mensal", "semanal"):
        assert c[unidade]["referencia"].sum() == est.mensal.loc[2024, "Total"]
        assert c[unidade]["maximo"].sum() == est.mensal.loc[2023, "Total"]
    semestres = c["semestre1"]["referencia"].sum() + c["semestre2"]["referencia"].sum()
    assert semestres == est.mensal.loc[2024, "Total"]
    assert list(tabela_comparativo_exibicao(est, "semestre1").columns) == [
        "Semana do semestre", "2024", "Mínimo", "Média", "Máximo"]


def test_blocos_de_7_dias():
    focos = pd.DataFrame({"data": pd.to_datetime(["2024-01-01", "2024-01-07", "2024-01-08", "2024-12-31"]),
                          "ano": 2024})
    semanas = matriz_periodos(focos, [2024], "semanal", date(2024, 1, 1), date(2024, 12, 31))
    assert semanas.loc[2024, 1] == 2 and semanas.loc[2024, 2] == 1 and semanas.loc[2024, 53] == 1
    corte = matriz_periodos(focos, [2024], "semanal", date(2024, 1, 1), date(2024, 1, 10))
    assert corte.loc[2024, 2] == 1 and np.isnan(corte.loc[2024, 3])    # depois do fim dos dados = vazio
    s2 = matriz_periodos(focos, [2024], "semestre2", date(2024, 1, 1), date(2024, 12, 31))
    assert s2.loc[2024].sum() == 1 and s2.loc[2024, 27] == 1             # 31/12: 27ª semana (30–31/12)
    s1 = matriz_periodos(focos, [2024], "semestre1", date(2024, 1, 1), date(2024, 12, 31))
    assert s1.loc[2024, 1] == 2 and s1.loc[2024, 2] == 1 and s1.loc[2024].sum() == 3
    julho = pd.DataFrame({"data": pd.to_datetime(["2023-07-01", "2023-07-07", "2023-07-08"]), "ano": 2023})
    s2 = matriz_periodos(julho, [2023], "semestre2", date(2023, 1, 1), date(2023, 12, 31))
    assert s2.loc[2023, 1] == 2 and s2.loc[2023, 2] == 1                 # semanas contadas desde 01/07


def test_acumulado(est):
    assert est.acumulado.loc[2024, 12] == est.mensal.loc[2024, "Total"]
    assert (est.acumulado.diff(axis=1).iloc[:, 1:] >= 0).all().all()     # nunca diminui
    tabela = tabela_acumulado_exibicao(est)
    assert tabela.index.tolist()[-3:] == ["p10", "p90", "Média"]
    assert (est.faixa_acumulado["media"].to_numpy() == est.acumulado.loc[2023].to_numpy()).all()
    assert est.anos_intensidade == [2023] and est.ano_mais_intenso == est.ano_menos_intenso == 2023


def test_parametros(focos, cobertura):
    e = estatisticas_territorio(focos, MUNICIPIO, 2023, 2024, cobertura,
                                ParametrosEstatisticas(ano_referencia=2023, percentil_inferior=80,
                                                       percentil_superior=20))
    assert e.ano_referencia == 2023 and e.anos_estatistica == [2024]
    assert (e.parametros.percentil_inferior, e.parametros.percentil_superior) == (20, 80)   # ordenados
    assert e.ano_anterior is None and e.anos_intensidade == []                              # 2024 é depois
    fora = resolver_parametros(ParametrosEstatisticas(ano_referencia=1990), 2023, 2024, date(2024, 12, 31))
    assert fora.ano_referencia == 2024


def test_estatisticas_de_terra_indigena(df, cobertura):
    """P14: as mesmas estatísticas para UC e TI."""
    focos = focos_da_area(df, "TI", "KAYAPÓ (23001)")
    e = estatisticas_territorio(focos, "KAYAPÓ (23001)", 2023, 2024, cobertura)
    assert e.mensal["Total"].tolist() == [139, 3259]
    poligono = geometria_area_protegida("TI", "KAYAPÓ (23001)")
    assert shapely.contains_xy(poligono, focos["lon"].to_numpy(), focos["lat"].to_numpy()).all()
    assert "limite do território" in notas(e)[0]


def test_extremos_por_coluna():
    tabela = pd.DataFrame({"a": [1, 5, 5, 0]}, index=["x", "y", "z", "Mínimo"])
    assert extremos_por_coluna(tabela, ["x", "y", "z"]) == {"a": ({"x"}, {"y", "z"})}
    # meses com 0 não são destacados: o amarelo vai para o menor valor diferente de 0
    com_zero = pd.DataFrame({"a": [0, 3, 7], "b": [0, 0, 0]}, index=["x", "y", "z"])
    assert extremos_por_coluna(com_zero, ["x", "y", "z"]) == {"a": ({"y"}, {"z"}), "b": (set(), set())}
    # ano de referência (mesmo com o mês em andamento) acima da máxima: o vermelho vai para ele
    ref = pd.DataFrame({"jan": [3, 7, 9], "out": [3, 7, 5], "dez": [3, 7, 0]}, index=["2024", "2025", "2026"])
    e = extremos_por_coluna(ref, ["2024", "2025"], "2026")
    assert e["jan"] == ({"2024"}, {"2026"}) and e["out"] == ({"2024"}, {"2025"}) and e["dez"] == ({"2024"}, {"2025"})
    empate = extremos_por_coluna(pd.DataFrame({"m": [4, 7, 7]}, index=["a", "b", "c"]), ["a", "b"], "c")
    assert empate["m"] == ({"a"}, {"b", "c"})


def test_graficos(est):
    figuras = figuras_estatisticas(est)
    assert set(figuras) == {"sazonalidade", "comparativo_mensal", "comparativo_semanal", "comparativo_semestre1",
                            "comparativo_semestre2", "acumulado_mensal"}
    fechar_figuras(figuras)
    for unidade in ("mensal", "semanal", "semestre1", "semestre2"):
        assert "layer" in interativo_comparativo(est, unidade).to_dict()
    assert "layer" in interativo_acumulado(est).to_dict()


def test_area_sem_focos_no_periodo(df, cobertura):
    focos = focos_da_area(df, "TI", "NAO EXISTE (0)")
    e = estatisticas_territorio(focos, "NAO EXISTE (0)", 2023, 2024, cobertura)
    assert e.mensal["Total"].tolist() == [0, 0]
