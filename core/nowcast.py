# -*- coding: utf-8 -*-
"""Cenário atual (nowcast) do município, em resolução diária (docs/07 §9).

Independe do período escolhido na barra lateral: usa todos os focos do território na base (cruzamento
ponto-no-polígono, colunas ``NM_MUN``/``SIGLA_UF``, docs/07 §1), até o último dia da base (que pode
ser provisório, ``core/atualizacao.py``). Compara cada dia recente com o mesmo dia do calendário nos
anos anteriores e com a média de uma janela de 7 dias em volta dele (±3 dias, P20).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

DIAS_SERIE = 30
MEIA_JANELA = 3            # janela de 7 dias: o dia ±3
FAIXAS_IDADE = [(0, 0, "Último dia"), (1, 2, "1–2 dias antes"), (3, 6, "3–6 dias antes"), (7, 29, "7–29 dias antes")]


@dataclass
class Nowcast:
    municipio: str
    ultimo_dia: date
    provisorio: bool                       # o último dia ainda pode receber focos
    focos: pd.DataFrame                    # focos recentes (até DIAS_SERIE dias): lon, lat, data, dias_atras, idade, UC, TI
    serie: pd.DataFrame                    # data, focos, media, maximo (mesmo dia), media_janela (±3 dias)
    anos_comparados: list[int]
    indicadores: dict

    def recentes(self, dias: int) -> pd.DataFrame:
        return self.focos[self.focos["dias_atras"] < dias]


def _mesmo_dia(dia: date, ano: int) -> date | None:
    try:
        return dia.replace(year=ano)
    except ValueError:                     # 29/02 em ano não bissexto
        return None


def nowcast_territorio(focos: pd.DataFrame, nome: str, ultimo_dia: date, inicio_base: date,
                       provisorio: bool = False, dias: int = DIAS_SERIE) -> Nowcast:
    """``focos`` = todos os focos do território na base (todos os anos); ``ultimo_dia`` = último dia da
    base (``atualizacao.situacao_da_base``).

    Anos comparados: os anteriores ao do último dia que a base cobre desde 1º de janeiro
    (``inicio_base`` = primeiro dia da base; 2002 começa em 04/07 e fica de fora).
    """
    municipio = nome
    primeiro_ano_completo = inicio_base.year if inicio_base == date(inicio_base.year, 1, 1) else inicio_base.year + 1
    anos = list(range(primeiro_ano_completo, ultimo_dia.year))
    focos = focos[focos["ano"] <= ultimo_dia.year]
    focos = focos.assign(data=pd.to_datetime(focos["data"]).dt.date)
    por_dia = focos["data"].value_counts()

    inicio = ultimo_dia - timedelta(days=dias - 1)
    linhas = []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        anteriores = [por_dia.get(d, 0) for a in anos if (d := _mesmo_dia(dia, a))]
        janela = [por_dia.get(d + timedelta(days=k), 0) for a in anos if (d := _mesmo_dia(dia, a))
                  for k in range(-MEIA_JANELA, MEIA_JANELA + 1)]
        linhas.append({"data": dia, "focos": int(por_dia.get(dia, 0)),
                       "media": float(np.mean(anteriores)) if anteriores else np.nan,
                       "maximo": float(np.max(anteriores)) if anteriores else np.nan,
                       "media_janela": float(np.mean(janela)) if janela else np.nan})
    serie = pd.DataFrame(linhas)

    recentes = focos[focos["data"] >= inicio].copy()
    recentes["dias_atras"] = [(ultimo_dia - d).days for d in recentes["data"]]
    recentes["idade"] = [next(n for a, b, n in FAIXAS_IDADE if a <= x <= b) for x in recentes["dias_atras"]]
    recentes = recentes.sort_values(["data", "lat"], ascending=[False, True])[
        ["data", "dias_atras", "idade", "lat", "lon", "UC", "TI"]].reset_index(drop=True)

    # Acumulado no ano até o mesmo dia/mês, comparado com os anos anteriores
    def acumulado(ano: int) -> int | None:
        fim = _mesmo_dia(ultimo_dia, ano) or date(ano, 2, 28)
        return int(((focos["data"] >= date(ano, 1, 1)) & (focos["data"] <= fim)).sum())

    acumulados = {a: acumulado(a) for a in anos}
    atual = acumulado(ultimo_dia.year)
    media_acumulado = float(np.mean(list(acumulados.values()))) if acumulados else np.nan
    soma_7 = int(serie["focos"].tail(7).sum())
    media_7 = float(serie["media"].tail(7).sum()) if anos else np.nan
    indicadores = {
        "ultimo_dia": int(serie["focos"].iloc[-1]),
        "media_ultimo_dia": float(serie["media"].iloc[-1]),
        "dia_anterior": int(serie["focos"].iloc[-2]) if dias > 1 else None,
        "ultimos_7": soma_7,
        "media_7": media_7,
        "ultimos_30": int(serie["focos"].sum()),
        "media_30": float(serie["media"].sum()) if anos else np.nan,
        "acumulado_ano": atual,
        "media_acumulado": media_acumulado,
        "variacao_acumulado_pct": (atual - media_acumulado) / media_acumulado * 100 if media_acumulado else None,
        # 1 = o ano com mais focos até esta data entre os comparados (empate = mesma posição)
        "posicao_acumulado": 1 + sum(v > atual for v in acumulados.values()),
        "anos_ranking": len(acumulados) + 1,
    }
    return Nowcast(municipio, ultimo_dia, provisorio, recentes, serie, anos, indicadores)
