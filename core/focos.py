# -*- coding: utf-8 -*-
"""Leitura e filtros da base de focos de calor (BDQueimadas/INPE, docs/03 e docs/05)."""

from pathlib import Path

import pandas as pd

from core.config import VALORES_VAZIOS, caminho_focos

COLUNAS = ["lon", "lat", "ano", "mes", "data", "NM_MUN", "NM_UF", "SIGLA_UF", "UC", "TI"]
COLUNAS_TEXTO = ["NM_MUN", "NM_UF", "SIGLA_UF", "UC", "TI"]


def carregar_focos(caminho: Path | str | None = None) -> pd.DataFrame:
    """Base consolidada com os textos em MAIÚSCULAS e sem espaços nas pontas.

    Arquivo ausente = DataFrame vazio com as colunas esperadas (a tela avisa).
    Coluna ausente = erro com mensagem clara.
    """
    caminho = Path(caminho or caminho_focos())
    if not caminho.exists():
        return pd.DataFrame(columns=COLUNAS)
    import pyarrow.parquet as pq

    faltando = [c for c in COLUNAS if c not in pq.read_schema(caminho).names]
    if faltando:
        raise ValueError(f"A base de focos {caminho.name} não tem as colunas: {', '.join(faltando)}.")
    df = pd.read_parquet(caminho, columns=COLUNAS)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").fillna(0).astype(int)
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").fillna(0).astype(int)
    for coluna in COLUNAS_TEXTO:
        df[coluna] = df[coluna].fillna("").astype(str).str.strip().str.upper()
    return df


def valido(serie: pd.Series) -> pd.Series:
    """Máscara dos valores preenchidos (exclui "", "NONE", "NULL"…)."""
    return ~serie.isin(VALORES_VAZIOS)


def anos_disponiveis(df: pd.DataFrame) -> list[int]:
    return sorted(int(a) for a in df["ano"].unique() if a > 0)


def da_uf(df: pd.DataFrame, nome_uf: str) -> pd.DataFrame:
    """Focos de um estado; aceita o nome por extenso ("Pará") ou a sigla ("PA")."""
    nome_uf = str(nome_uf).strip().upper()
    return df[(df["SIGLA_UF"] == nome_uf) | (df["NM_UF"] == nome_uf)]


def no_periodo(df: pd.DataFrame, ano_inicio: int, ano_fim: int) -> pd.DataFrame:
    return df[df["ano"].between(ano_inicio, ano_fim)]


def municipios_da_uf(df: pd.DataFrame, nome_uf: str) -> list[str]:
    nomes = da_uf(df, nome_uf)["NM_MUN"]
    return sorted(nomes[valido(nomes)].unique())


def areas_com_focos(df: pd.DataFrame, campo: str) -> list[str]:
    """UCs ou TIs (rótulo "NOME (CÓDIGO)") com pelo menos um foco na base."""
    return sorted(df.loc[valido(df[campo]), campo].unique())


def focos_do_municipio(df: pd.DataFrame, estado: str, municipio: str) -> pd.DataFrame:
    """Todos os focos do município (cruzamento ponto-no-polígono já gravado em NM_MUN/UF, docs/07 §1)."""
    do_estado = da_uf(df, estado)
    return do_estado[do_estado["NM_MUN"] == str(municipio).strip().upper()]


def focos_da_area(df: pd.DataFrame, campo: str, rotulo: str) -> pd.DataFrame:
    """Todos os focos da UC ou TI (coluna ``UC``/``TI``, cruzamento ponto-no-polígono)."""
    return df[df[campo] == str(rotulo).strip().upper()]
