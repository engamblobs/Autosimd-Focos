# -*- coding: utf-8 -*-
"""Localidades do IBGE e territórios quilombolas (docs/03 §7): conversão dos KML e leitura do Parquet."""

import importlib.util

import pytest

from core.config import AMOSTRAS_BASES, RAIZ
from core.localidades import (
    COLUNAS_LOCALIDADES, BaseLocalidadesAusente, carregar_localidades, carregar_territorios_quilombolas,
)

KML = RAIZ / "amostras" / "kml_localidades"


def ferramenta():
    spec = importlib.util.spec_from_file_location("importar_localidades",
                                                  RAIZ / "ferramentas" / "importar_localidades.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_le_a_amostra():
    df = carregar_localidades()
    assert list(df.columns) == COLUNAS_LOCALIDADES and len(df) > 0
    assert df["cd_localidade"].is_unique
    assert set(df["sigla_uf"].astype(str)) <= {"PA", "AP"}
    sede = df[(df["categoria"] == "Cidade") & (df["municipio"] == "Novo Progresso")]
    assert len(sede) == 1 and sede.iloc[0]["cd_mun"] == 1505031
    assert df["lon"].between(-75, -30).all() and df["lat"].between(-35, 6).all()
    assert set(carregar_localidades("AP")["sigla_uf"].astype(str)) == {"AP"}


def test_territorios_quilombolas():
    tq = carregar_territorios_quilombolas()
    assert len(tq) >= 1 and all(g.is_valid and not g.is_empty for g in tq["geometria"])


def test_base_ausente(tmp_path):
    with pytest.raises(BaseLocalidadesAusente, match="importar_localidades"):
        carregar_localidades(bases_dir=tmp_path)


def test_conversao_dos_kml(tmp_path):
    imp = ferramenta()
    pontos, quilombolas = [], []
    for arquivo in sorted(KML.glob("*/*.kml")):
        p, q = imp.ler_kml(arquivo)
        pontos += p
        quilombolas += q
    df = imp.tabela_localidades(pontos)
    assert list(df.columns) == COLUNAS_LOCALIDADES
    assert df["cd_localidade"].is_unique and len(df) <= len(pontos)
    assert set(df["municipio"].astype(str)) == {"Novo Progresso", "Melgaço"}
    assert (df["categoria"] == "Cidade").sum() == 2                       # as duas sedes municipais
    tq = imp.tabela_quilombolas(quilombolas)
    assert list(tq["nome"]) == ["Gurupá Mirim, Jocojo, Flexinha, Carrazedo"]   # Melgaço tem um território


def test_localidade_em_duas_pastas_vira_uma_linha():
    imp = ferramenta()
    base = {"CD_MUN": "1500107", "NM_MUN": "Teste", "SIGLA_UF": "PA", "NM_LOCALIDADE": "Aldeia X",
            "CD_LOCALIDADE": "150010700001", "lon": -50.0, "lat": -3.0}
    df = imp.tabela_localidades([{**base, "CT_LOCALIDADE": "Localidade Indígena"},
                                 {**base, "CT_LOCALIDADE": "Povoado"}])
    assert len(df) == 1
    linha = df.iloc[0]
    assert linha["categoria"] == "Povoado" and linha["indigena"] and not linha["quilombola"]


def test_amostra_existe():
    assert (AMOSTRAS_BASES / "localidades").is_dir()
