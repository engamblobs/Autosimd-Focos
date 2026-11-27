# -*- coding: utf-8 -*-
"""Localidades do IBGE (Censo 2022) e territórios quilombolas — docs/03 §7, docs/06 §9.

As tabelas são geradas uma vez a partir dos KML do IBGE por ``ferramentas/importar_localidades.py`` e ficam em
``BASES_GEOJSON/localidades/``. Base ausente = erro claro (``BaseLocalidadesAusente``), nunca tabela vazia.
"""

from pathlib import Path

import pandas as pd
import shapely

from core.config import pasta_localidades

NOME_LOCALIDADES = "localidades_ibge_2022.parquet"
NOME_QUILOMBOLAS = "territorios_quilombolas_2022.parquet"
COLUNAS_LOCALIDADES = ["cd_localidade", "nome", "categoria", "indigena", "quilombola", "agrovila_pa",
                       "cd_mun", "municipio", "sigla_uf", "lon", "lat"]
# pastas "temáticas" do KML: a localidade costuma estar também numa pasta geral (povoado, vila...)
TEMATICAS = {"Localidade Indígena", "Localidade Quilombola", "Agrovila do PA"}


class BaseLocalidadesAusente(FileNotFoundError):
    pass


def _arquivo(nome: str, bases_dir: Path | None) -> Path:
    caminho = pasta_localidades(bases_dir) / nome
    if not caminho.exists():
        raise BaseLocalidadesAusente(
            f"Base de localidades não encontrada: {caminho}. Gere com "
            "python ferramentas/importar_localidades.py <pasta dos KML do IBGE>.")
    return caminho


def carregar_localidades(sigla_uf: str | None = None, bases_dir: Path | None = None) -> pd.DataFrame:
    """Localidades (um ponto cada), de uma UF ou do Brasil inteiro."""
    filtro = [("sigla_uf", "==", sigla_uf)] if sigla_uf else None
    df = pd.read_parquet(_arquivo(NOME_LOCALIDADES, bases_dir), filters=filtro)
    faltando = set(COLUNAS_LOCALIDADES) - set(df.columns)
    if faltando:
        raise ValueError(f"Base de localidades sem as colunas {sorted(faltando)}.")
    return df


def carregar_territorios_quilombolas(bases_dir: Path | None = None) -> pd.DataFrame:
    """Territórios quilombolas: código, nome e ``geometria`` (shapely)."""
    df = pd.read_parquet(_arquivo(NOME_QUILOMBOLAS, bases_dir))
    return df.assign(geometria=shapely.from_wkb(df["geometria"].to_numpy()))
