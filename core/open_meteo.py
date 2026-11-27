# -*- coding: utf-8 -*-
"""Vento a 10 m e PM2,5 previstos, hora a hora, pelo Open-Meteo (gratuito, sem chave, CC BY 4.0).

Uma consulta aceita vários pontos (latitude e longitude separadas por vírgula); mandamos em lotes de
``LOTE`` pontos. Horários em UTC. Direção do vento = de onde ele vem (convenção meteorológica, graus).
"""

import pandas as pd

from core.config import URL_OPEN_METEO, URL_OPEN_METEO_AR
from core.rede import SemDadosAoVivo, obter_json

LOTE = 100
VARIAVEIS_VENTO = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"]


def _lotes(pontos, tamanho=LOTE):
    pontos = list(pontos)
    for i in range(0, len(pontos), tamanho):
        yield pontos[i:i + tamanho]


def _consultar(url: str, pontos, variaveis: list[str], extra: dict, obter=obter_json) -> pd.DataFrame:
    """Tabela longa: ``ponto`` (posição na lista), ``hora`` (UTC) e uma coluna por variável."""
    linhas, inicio = [], 0
    for lote in _lotes(pontos):
        resposta = obter(url, {
            "latitude": ",".join(f"{lat:.4f}" for _, lat in lote),
            "longitude": ",".join(f"{lon:.4f}" for lon, _ in lote),
            "hourly": ",".join(variaveis), "timezone": "GMT", **extra})
        respostas = resposta if isinstance(resposta, list) else [resposta]
        if len(respostas) != len(lote) or any("hourly" not in r for r in respostas):
            raise SemDadosAoVivo(f"Resposta inesperada do Open-Meteo ({url}).")
        for k, r in enumerate(respostas):
            horas = r["hourly"]
            tabela = pd.DataFrame({v: horas.get(v) for v in variaveis})
            tabela.insert(0, "hora", pd.to_datetime(horas["time"]))
            tabela.insert(0, "ponto", inicio + k)
            linhas.append(tabela)
        inicio += len(lote)
    return pd.concat(linhas, ignore_index=True) if linhas else pd.DataFrame(columns=["ponto", "hora", *variaveis])


def vento_horario(pontos, dias: int = 2, obter=obter_json) -> pd.DataFrame:
    """``pontos`` = [(lon, lat)]. Colunas: ponto, hora, velocidade_kmh, direcao_graus, rajada_kmh."""
    df = _consultar(URL_OPEN_METEO, pontos, VARIAVEIS_VENTO,
                    {"wind_speed_unit": "kmh", "forecast_days": dias, "past_days": 1}, obter)
    return df.rename(columns={"wind_speed_10m": "velocidade_kmh", "wind_direction_10m": "direcao_graus",
                              "wind_gusts_10m": "rajada_kmh"})


def pm25_horario(pontos, dias: int = 2, obter=obter_json) -> pd.DataFrame:
    """PM2,5 (µg/m³) previsto pelo CAMS. Colunas: ponto, hora, pm25."""
    df = _consultar(URL_OPEN_METEO_AR, pontos, ["pm2_5"], {"forecast_days": dias}, obter)
    return df.rename(columns={"pm2_5": "pm25"})
