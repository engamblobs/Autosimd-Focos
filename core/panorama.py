# -*- coding: utf-8 -*-
"""Panorama do estado (página inicial, docs/07 §10): indicadores, regiões e municípios.

O estado pode ser filtrado por região — Região de Integração no Pará, Região Geográfica Imediata
nos demais estados (``core/regioes.py``). Os focos de cada município são os do cruzamento
ponto-no-polígono (colunas da base, docs/07 §1).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import shapely

from core.diagnostico import fim_dos_dados, ranking, serie_anual
from core.focos import da_uf, no_periodo, valido
from core.regioes import SEM_REGIAO, regiao_do_municipio, tipo_regiao
from core.territorios import municipios_do_estado

TODAS = "Todas as regiões"
TOP_MUNICIPIOS = 15


@dataclass
class PanoramaEstado:
    estado: str                          # "Pará"
    sigla_uf: str | None
    regiao: str | None                   # None = estado inteiro
    tipo_regiao: str
    ano_inicio: int
    ano_fim: int
    fim_dados: date                      # último dia com focos até 31/12 do ano final
    focos: pd.DataFrame                  # do estado/região, todos os anos (com a coluna "regiao")
    serie_anual: dict[int, int]
    indicadores: dict
    por_regiao: pd.DataFrame             # uma linha por região (só com o estado inteiro)
    ranking_municipios: pd.DataFrame

    @property
    def nome(self) -> str:
        return self.regiao or self.estado

    @property
    def focos_periodo(self) -> pd.DataFrame:
        return self.focos[self.focos["ano"].between(self.ano_inicio, self.ano_fim)]


def regioes_dos_focos(focos: pd.DataFrame, sigla_uf) -> pd.Series:
    """Região de cada foco (pelo município), calculada uma vez por nome de município."""
    por_nome = {m: regiao_do_municipio(m, sigla_uf) for m in focos["NM_MUN"].unique()}
    return focos["NM_MUN"].map(por_nome)


def regioes_do_estado(df: pd.DataFrame, estado: str) -> list[str]:
    focos = da_uf(df, estado)
    focos = focos[valido(focos["NM_MUN"])]
    sigla = focos["SIGLA_UF"].mode().iloc[0] if len(focos) else None
    return sorted(r for r in regioes_dos_focos(focos, sigla).unique() if r != SEM_REGIAO)


def _mesmo_periodo(focos: pd.DataFrame, ano: int, ate: date) -> int:
    """Focos de 1º de janeiro até o mesmo dia/mês de ``ate`` no ``ano``."""
    try:
        fim = ate.replace(year=ano)
    except ValueError:                   # 29/02
        fim = date(ano, 2, 28)
    return int(((focos["data"] >= f"{ano}-01-01") & (focos["data"] <= fim.isoformat())).sum())


def panorama_estado(df: pd.DataFrame, estado: str, ano_inicio: int, ano_fim: int, regiao: str | None = None,
                    inicio_base: date | None = None) -> PanoramaEstado:
    """Panorama do estado (ou de uma região dele) no período ``ano_inicio``–``ano_fim``.

    A média "do mesmo período" usa só os anos que a base cobre desde 1º de janeiro (``inicio_base`` =
    primeiro dia da base; 2002 começa em 04/07 e fica de fora).
    """
    focos = da_uf(df, estado)
    focos = focos[valido(focos["NM_MUN"])]
    sigla = focos["SIGLA_UF"].mode().iloc[0] if len(focos) else None
    focos = focos.assign(regiao=regioes_dos_focos(focos, sigla))
    if regiao and regiao != TODAS:
        focos = focos[focos["regiao"] == regiao]
    else:
        regiao = None
    periodo = no_periodo(focos, ano_inicio, ano_fim)
    fim = fim_dos_dados(no_periodo(df, ano_inicio, ano_fim), ano_fim)

    # Ano final até o último dia dos dados × mesmo período dos anos anteriores do período
    no_ano = _mesmo_periodo(focos, ano_fim, fim)
    anteriores = {a: _mesmo_periodo(focos, a, fim) for a in range(ano_inicio, ano_fim)
                  if inicio_base is None or date(a, 1, 1) >= inicio_base}
    ano_anterior = anteriores.get(ano_fim - 1)
    media = sum(anteriores.values()) / len(anteriores) if anteriores else None
    recentes = focos[(focos["data"] > (fim - timedelta(days=7)).isoformat()) & (focos["data"] <= fim.isoformat())]
    ultimos_30 = focos[(focos["data"] > (fim - timedelta(days=30)).isoformat()) & (focos["data"] <= fim.isoformat())]
    ano_final = periodo[periodo["ano"] == ano_fim]
    indicadores = {
        "focos_ano_ate_data": no_ano,
        "ano_anterior_ate_data": ano_anterior,
        "variacao_ano_anterior_pct": (no_ano - ano_anterior) / ano_anterior * 100 if ano_anterior else None,
        "media_ate_data": media,
        "variacao_media_pct": (no_ano - media) / media * 100 if media else None,
        "ultimos_7": len(recentes),
        "ultimos_30": len(ultimos_30),
        "municipios_com_focos": int(ano_final["NM_MUN"].nunique()),
        "focos_periodo": len(periodo),
    }

    por_regiao = pd.DataFrame()
    if regiao is None:
        tabela = ranking(ano_final[ano_final["regiao"] != SEM_REGIAO], "regiao", fim)
        acumulado = periodo.groupby("regiao").size()
        total = int(tabela["focos"].sum()) if len(tabela) else 0
        por_regiao = pd.DataFrame([{
            "Posição": f"{linha.posicao}º",
            tipo_regiao(sigla): nome,
            f"Focos ({ano_fim})": int(linha.focos),
            f"% do estado ({ano_fim})": round(linha.focos / total * 100, 1) if total else 0.0,
            f"Acumulado {ano_inicio}–{ano_fim}": int(acumulado.get(nome, 0)),
            "Municípios com focos": int(ano_final.loc[ano_final["regiao"] == nome, "NM_MUN"].nunique()),
        } for nome, linha in tabela.iterrows()])

    municipios = ranking(ano_final, "NM_MUN", fim)
    acumulado_mun = periodo.groupby("NM_MUN").size()
    ranking_municipios = pd.DataFrame([{
        "Posição": f"{linha.posicao}º",
        "Município": nome.title(),
        "Região": regiao_do_municipio(nome, sigla),
        f"Focos ({ano_fim})": int(linha.focos),
        "Último mês": int(linha.ultimo_mes),
        "Última semana": int(linha.ultima_semana),
        f"Acumulado {ano_inicio}–{ano_fim}": int(acumulado_mun.get(nome, 0)),
    } for nome, linha in municipios.head(TOP_MUNICIPIOS).iterrows()])

    return PanoramaEstado(estado=estado, sigla_uf=sigla, regiao=regiao, tipo_regiao=tipo_regiao(sigla),
                          ano_inicio=ano_inicio, ano_fim=ano_fim, fim_dados=fim, focos=focos,
                          serie_anual=serie_anual(periodo, ano_inicio, ano_fim), indicadores=indicadores,
                          por_regiao=por_regiao, ranking_municipios=ranking_municipios)


@lru_cache(maxsize=8)
def limite_da_regiao(caminho_estado: Path, sigla_uf: str, regiao: str | None):
    """Polígono do estado ou da região (união dos municípios); None se não houver limites."""
    municipios = municipios_do_estado(Path(caminho_estado))
    if not municipios:
        return None
    if regiao:
        geometrias = [g for nome, g in municipios.items() if regiao_do_municipio(nome, sigla_uf) == regiao]
    else:
        geometrias = list(municipios.values())
    return shapely.union_all(geometrias).buffer(0) if geometrias else None
