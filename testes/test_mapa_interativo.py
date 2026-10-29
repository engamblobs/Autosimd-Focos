# -*- coding: utf-8 -*-
"""Mapa interativo dos focos recentes, limites dos estados e mapa de localização (docs/10 §3)."""

import base64
import json
from datetime import date

import pytest

from core.cenario import cenario_atual, recorrencia_do_mes
from core.estatisticas import cobertura_base
from core.focos import carregar_focos
from core.mapa_interativo import (
    CAMADA_MUNICIPIOS, cor_da_recorrencia, deck_focos_recentes, estilo_satelite, legenda, municipio_clicado, vista,
)
from core.mapas import mapa_localizacao
from core.panorama import TODAS, limite_da_regiao
from core.produto import fechar_figuras
from core.territorios import (
    caminho_do_estado, estados_disponiveis, geometria_municipio, limites_uf, municipios_simplificados,
)


@pytest.fixture(scope="module")
def cenario():
    df = carregar_focos()
    cen = cenario_atual(df, "Pará", TODAS, date(2024, 12, 31), cobertura_base(df)[0])
    limite = limite_da_regiao(estados_disponiveis()["Pará"], "PA", None)
    return cen, limite, recorrencia_do_mes(cen, limite.bounds)


def test_limites_dos_estados():
    ufs = limites_uf()
    assert len(ufs) == 27 and ufs["PA"][0] == "Pará"
    assert all(geom.is_valid and not geom.is_empty for _, geom in ufs.values())
    assert caminho_do_estado("PA").name == "NM_UF_Pará.geojson"      # amostra: só PA e AP
    assert caminho_do_estado("SP") is None and caminho_do_estado(None) is None


def test_municipios_simplificados():
    caminho = estados_disponiveis()["Pará"]
    municipios = municipios_simplificados(caminho)
    total = len(json.loads(caminho.read_text(encoding="utf-8"))["features"])     # amostra: recorte do Pará
    assert len(municipios) == total > 0 and {uf for _, uf, _ in municipios} == {"PA"}
    assert all(g.is_valid for _, _, g in municipios)


def test_deck_com_as_camadas(cenario):
    cen, limite, rec = cenario
    recentes = cen.nowcast.recentes(7)
    deck = deck_focos_recentes(recentes, limite, municipios_simplificados(estados_disponiveis()["Pará"]), rec)
    camadas = {c.id: c for c in deck.layers}
    assert list(camadas) == ["recorrencia", CAMADA_MUNICIPIOS, "territorio", "focos"]
    assert camadas[CAMADA_MUNICIPIOS].pickable and not camadas["recorrencia"].pickable
    assert len(camadas["focos"].data) == len(recentes)
    assert len(camadas["recorrencia"].data) == int((rec.matriz > 0).sum())
    estilo = json.loads(base64.b64decode(deck.map_style.split(",", 1)[1]))
    assert estilo["layers"][0]["type"] == "raster" and estilo_satelite() == deck.map_style
    assert json.loads(deck.to_json())                                    # serializável para o Streamlit
    sem_internet = deck_focos_recentes(recentes, limite, (), rec, satelite=False)
    assert sem_internet.map_style is None


def test_enquadramento_e_cores():
    v = vista((-58.9, -9.9, -46.0, 2.6))                                 # Pará inteiro
    assert 4.5 < v.zoom < 6 and v.longitude == pytest.approx(-52.45)
    assert vista((-47.8, -0.9, -47.4, -0.5)).zoom > v.zoom              # município pequeno: mais zoom
    assert cor_da_recorrencia(1, 10) == [255, 255, 178] and cor_da_recorrencia(10, 10) == [189, 0, 38]


def test_legenda_e_clique(cenario):
    cen, _, rec = cenario
    itens = legenda(cen.nowcast.recentes(7), rec)
    assert any("Quadrícula: foco em dezembro" in texto for _, texto in itens)
    assert municipio_clicado({"selection": {"objects": {CAMADA_MUNICIPIOS: [{"nome": "Belém"}]}}}) == "Belém"
    assert municipio_clicado({"selection": {"objects": {"focos": [{"info": "x"}]}}}) is None
    assert municipio_clicado(None) is None


def test_mapa_de_localizacao():
    caminho = estados_disponiveis()["Pará"]
    figura = mapa_localizacao("PA", geometria_municipio(caminho, "NOVO PROGRESSO"), "Novo Progresso",
                              municipios_simplificados(caminho))
    try:
        assert len(figura.axes) == 2 and "Novo Progresso" in figura.axes[1].get_title()
        assert any(t.get_text() == "Novo Progresso" for t in figura.axes[1].texts)      # seta com o nome
    finally:
        fechar_figuras({"f": figura})
