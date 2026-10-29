# -*- coding: utf-8 -*-
"""Cenário atual do Panorama do Estado (docs/07 §11) e o PDF dele, com a amostra real (PA e AP, 2023–2024)."""

import re
from datetime import date

import numpy as np
import pytest

from core.cenario import cenario_atual, dia_da_ultima_passagem, focos_no_intervalo, geojson_focos, recorrencia_do_mes
from core.estatisticas import cobertura_base, estatisticas_territorio
from core.grade import grade_do_territorio, valor_na_celula
from core.focos import carregar_focos
from core.panorama import TODAS, limite_da_regiao
from core.relatorio_cenario import gerar_relatorio_cenario, indicadores_cenario
from core.territorios import estados_disponiveis


@pytest.fixture(scope="module")
def df():
    return carregar_focos()


@pytest.fixture(scope="module")
def para(df):
    return cenario_atual(df, "Pará", TODAS, date(2024, 12, 31), cobertura_base(df)[0])


def test_ultima_passagem(df):
    assert dia_da_ultima_passagem(df, date(2024, 12, 31)) == date(2024, 12, 31)
    # dia buscado ainda sem a passagem processada (sem focos na base): vale o último dia com focos
    assert dia_da_ultima_passagem(df, date(2025, 1, 2)) == date(2024, 12, 31)


def test_24h_e_semana_no_estado(df, para):
    pa = df[df["SIGLA_UF"] == "PA"]
    assert para.dia == date(2024, 12, 31) and para.nome == "Pará" and para.regiao is None
    assert len(para.focos_24h) == (pa["data"] == "2024-12-31").sum()
    assert len(para.focos_semana) == ((pa["data"] >= "2024-12-25") & (pa["data"] <= "2024-12-31")).sum()
    i = para.nowcast.indicadores
    assert i["ultimo_dia"] == len(para.focos_24h) and i["ultimos_7"] == len(para.focos_semana)
    assert para.municipios["Última semana"].sum() == len(para.focos_semana)
    assert para.municipios["Últimas 24 h"].sum() == len(para.focos_24h)


def test_areas_protegidas_da_semana(para):
    if not para.areas.empty:
        assert set(para.areas["Tipo"]) <= {"UC", "TI"}
        em_areas = (para.focos_semana["UC"] != "NONE").sum() + (para.focos_semana["TI"] != "NONE").sum()
        assert para.areas["Última semana"].sum() == em_areas


def test_filtro_por_regiao(df, para):
    xingu = cenario_atual(df, "Pará", "Região Xingu", date(2024, 12, 31), cobertura_base(df)[0])
    assert xingu.nome == "Região Xingu"
    assert set(xingu.focos_semana["regiao"]) <= {"Região Xingu"}
    assert len(xingu.focos_semana) <= len(para.focos_semana)


def test_indicadores_e_pdf(df, para):
    rotulos = [r for r, _ in indicadores_cenario(para)]
    assert rotulos[0].startswith("Últimas 24 h — passagem de 31/12/2024")
    assert rotulos[1] == "Última semana (25/12 a 31/12)"
    limite = limite_da_regiao(estados_disponiveis()["Pará"], "PA", None)
    pdf, nome = gerar_relatorio_cenario(para, limite)
    assert nome == "Cenario_Focos_Para_20241231.pdf"
    paginas = int(re.search(rb"/Count (\d+)", pdf).group(1))
    assert pdf.startswith(b"%PDF") and paginas >= 2
    # com as estatísticas do período no fim, o PDF cresce
    est = estatisticas_territorio(df[df["SIGLA_UF"] == "PA"], "Pará", 2023, 2024, cobertura_base(df))
    com_est, _ = gerar_relatorio_cenario(para, limite, est)
    assert int(re.search(rb"/Count (\d+)", com_est).group(1)) > paginas


def test_serie_semanal_do_nowcast(df, para):
    s = para.nowcast.semanal
    assert len(s) == 13 and s["fim"].iloc[-1] == date(2024, 12, 31)
    assert ((s["fim"] - s["inicio"]).map(lambda d: d.days) == 6).all()
    pa = df[df["SIGLA_UF"] == "PA"]
    assert s["focos"].iloc[-1] == ((pa["data"] >= "2024-12-25") & (pa["data"] <= "2024-12-31")).sum()
    ultima_de_2023 = ((pa["data"] >= "2023-12-25") & (pa["data"] <= "2023-12-31")).sum()
    assert s["media"].iloc[-1] == ultima_de_2023 == s["maximo"].iloc[-1]   # só 2023 é comparável na amostra


def test_valor_na_celula():
    grade = grade_do_territorio((0.0, 0.0, 0.3, 0.3), 10)
    matriz = np.zeros(grade.forma)
    matriz[1, 1] = 5
    lon, lat = (grade.x[1] + grade.x[2]) / 2, (grade.y[1] + grade.y[2]) / 2
    assert valor_na_celula(grade, matriz, [lon, 10.0], [lat, 10.0]).tolist() == [5, 0]   # fora da grade = 0


def test_recorrencia_do_mes(para):
    limite = limite_da_regiao(estados_disponiveis()["Pará"], "PA", None)
    rec = recorrencia_do_mes(para, limite.bounds)
    assert rec.mes == 12 and rec.anos == [2023]
    assert rec.matriz.max() <= 1 and len(rec.atuais) == len(para.focos_semana)
    assert 0 <= rec.em_celulas_frequentes <= rec.em_celulas_com_historico <= 100


def test_exportacao_geojson(df):
    focos = focos_no_intervalo(df, "Pará", None, date(2024, 9, 1), date(2024, 9, 7))
    pa = df[df["SIGLA_UF"] == "PA"]
    assert len(focos) == ((pa["data"] >= "2024-09-01") & (pa["data"] <= "2024-09-07")).sum()
    geo = geojson_focos(focos, "Região de Integração", "teste")
    assert len(geo["features"]) == len(focos)
    f = geo["features"][0]
    assert f["geometry"]["type"] == "Point" and f["geometry"]["coordinates"] == [f["properties"]["longitude"],
                                                                                f["properties"]["latitude"]]
    assert {"data", "municipio", "uf", "regiao", "unidade_conservacao", "terra_indigena", "satelite"} <= set(
        f["properties"])
    assert all(x["properties"]["unidade_conservacao"] != "NONE" for x in geo["features"])   # vazio = null
    xingu = focos_no_intervalo(df, "Pará", "Região Xingu", date(2024, 9, 1), date(2024, 9, 7))
    assert set(xingu["regiao"]) <= {"Região Xingu"} and len(xingu) <= len(focos)


def test_texto_e_municipios_acima_da_maxima(df, para):
    from core.cenario import em_territorio, texto_do_cenario
    from core.panorama import COLUNAS_ACIMA, estatisticas_dos_municipios, panorama_estado

    assert em_territorio("Pará") == "no Pará" and em_territorio("Bahia") == "na Bahia"
    assert em_territorio("Goiás") == "em Goiás" and em_territorio("Região Xingu") == "na Região Xingu"
    pan = panorama_estado(df, "Pará", 2023, 2024, TODAS, cobertura_base(df)[0])
    acima = pan.acima_no_mes
    assert list(acima.columns) == COLUNAS_ACIMA
    assert (acima["Focos no mês"] > acima["Máxima anterior"]).all()
    textos = texto_do_cenario(para, acima, pan.anos_recorde)
    assert textos[0].startswith("Na passagem mais recente do satélite de referência (31/12/2024)")
    assert "no Pará" in textos[0]
    assert any("máxima histórica" in t for t in textos)
    assert not any("fim do relatório" in t for t in textos)                     # só no PDF
    est = estatisticas_dos_municipios(pan.focos, list(acima["Município"])[:2], 2023, 2024, cobertura_base(df))
    limite = limite_da_regiao(estados_disponiveis()["Pará"], "PA", None)
    pngs = {}
    pdf, nome = gerar_relatorio_cenario(para, limite, acima_no_mes=acima, anos_recorde=pan.anos_recorde,
                                        sazonalidades=est, pngs=pngs)
    assert pdf.startswith(b"%PDF") and all(f"sazonalidade_{m}" in pngs for m in est)

    import io
    import zipfile

    from core.relatorio_cenario import pacote_cenario
    zip_, nome_zip = pacote_cenario(para, pdf, nome, pngs, acima, {"type": "FeatureCollection", "features": []})
    arquivos = zipfile.ZipFile(io.BytesIO(zip_)).namelist()
    assert nome_zip == "Cenario_Completo_Para_20241231.zip" and nome in arquivos and "metadados.json" in arquivos
    assert "tabelas/municipios_acima_da_maxima_no_mes.csv" in arquivos
    assert any(a.startswith("imagens/sazonalidade_") for a in arquivos)
