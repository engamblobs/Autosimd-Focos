# -*- coding: utf-8 -*-
"""Leitura da base de focos e das geometrias (municípios, UCs, TIs) com a amostra real."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core import config
from core.focos import (
    COLUNAS, anos_disponiveis, areas_com_focos, carregar_focos, da_uf, municipios_da_uf, no_periodo,
)
from core.territorios import (
    area_km2, areas_protegidas_no_territorio, areas_protegidas_padrao, contar_focos_na_area, estados_disponiveis,
    geometria_area_protegida, geometria_municipio, poligonos_de, rotulo_area_protegida,
)


@pytest.fixture(scope="module")
def df():
    return carregar_focos()


@pytest.fixture(scope="module")
def sao_felix():
    return geometria_municipio(estados_disponiveis()["Pará"], "SÃO FÉLIX DO XINGU")


def test_testes_usam_a_amostra():
    assert config.BASES_DIR == config.AMOSTRAS_BASES


def test_carregar_focos(df):
    assert list(df.columns) == COLUNAS
    assert len(df) == 102_371
    assert anos_disponiveis(df) == [2023, 2024]
    assert df["SIGLA_UF"].value_counts().to_dict() == {"PA": 97_782, "AP": 4_565, "NONE": 24}
    assert (df["NM_MUN"] == df["NM_MUN"].str.upper()).all()


def test_base_ausente_devolve_vazio(tmp_path):
    vazio = carregar_focos(tmp_path / "nao_existe.parquet")
    assert vazio.empty and list(vazio.columns) == COLUNAS


def test_base_sem_coluna_e_recusada(tmp_path):
    caminho = tmp_path / "incompleta.parquet"
    pq.write_table(pa.table({"lon": [1.0], "lat": [2.0]}), caminho)
    with pytest.raises(ValueError, match="não tem as colunas"):
        carregar_focos(caminho)


def test_filtros(df):
    assert len(da_uf(df, "Pará")) == len(da_uf(df, "PA")) == 97_782
    assert len(municipios_da_uf(df, "Pará")) == 144
    assert "NONE" not in municipios_da_uf(df, "Pará")
    assert len(no_periodo(df, 2024, 2024)) == (df["ano"] == 2024).sum()
    ucs = areas_com_focos(df, "UC")
    assert "NONE" not in ucs and "ÁREA DE PROTEÇÃO AMBIENTAL TRIUNFO DO XINGU (1039)" in ucs


def test_estados_e_municipios():
    estados = estados_disponiveis()
    assert list(estados) == ["Amapá", "Pará"]
    assert geometria_municipio(estados["Pará"], "sao felix do xingu") is not None   # sem acento/minúsculas
    assert geometria_municipio(estados["Pará"], "BELÉM") is None                     # fora da amostra


def test_area_geodesica(sao_felix):
    assert area_km2(sao_felix) == pytest.approx(84_213, abs=1)    # IBGE: 84.212,9 km²
    assert area_km2(None) is None


def test_rotulo_area_protegida():
    assert rotulo_area_protegida({"terrai_nom": "Kayapó", "terrai_cod": 23001}) == "Kayapó (23001)"
    assert rotulo_area_protegida({"NOME_UC1": "FLORESTA NACIONAL DO JAMANXIM", "ID_UC0": "266"}) == \
        "FLORESTA NACIONAL DO JAMANXIM (266)"
    assert rotulo_area_protegida({}) == ""


def test_rotulo_igual_ao_da_base_de_focos(df):
    """Toda UC/TI da base de focos que toca a amostra tem polígono com o mesmo rótulo."""
    areas = areas_protegidas_padrao()
    assert geometria_area_protegida("TI", "KAYAPÓ (23001)", areas) is not None
    assert geometria_area_protegida("UC", "ÁREA DE PROTEÇÃO AMBIENTAL TRIUNFO DO XINGU (1039)", areas) is not None
    assert geometria_area_protegida("UC", "KAYAPÓ (23001)", areas) is None          # tipo errado


def test_areas_protegidas_no_municipio(sao_felix):
    areas = areas_protegidas_no_territorio(sao_felix, areas_protegidas_padrao())
    assert [a["tipo"] for a in areas] == ["TI"] * 7 + ["UC"] * 5                   # TIs primeiro
    assert [a["num"] for a in areas] == list(range(1, 13))
    assert areas[0]["nome"] == "Kayapó (23001)"
    assert areas[0]["pct_da_area"] == pytest.approx(50.5, abs=0.1)
    assert areas[7]["nome"] == "ÁREA DE PROTEÇÃO AMBIENTAL TRIUNFO DO XINGU (1039)"
    assert areas_protegidas_no_territorio(None, areas_protegidas_padrao()) == []


def test_contar_focos_na_area(df, sao_felix):
    focos = df[df["NM_MUN"] == "SÃO FÉLIX DO XINGU"]
    dentro = contar_focos_na_area(focos, sao_felix)
    assert dentro >= 0.99 * len(focos)          # quase todos (diferença de limites IBGE × INPE)
    assert contar_focos_na_area(focos.iloc[0:0], sao_felix) == 0


def test_poligonos_de(sao_felix):
    assert all(p.geom_type == "Polygon" for p in poligonos_de(sao_felix))
    assert poligonos_de(None) == []
