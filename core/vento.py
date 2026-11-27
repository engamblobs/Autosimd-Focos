# -*- coding: utf-8 -*-
"""Vento a 10 m por quadrícula de 0,25°, buscado junto com o nowcast (P40, docs/03 §8).

- Só busca se o usuário ligar a chave "Vento" (acima da do nowcast); a escolha fica em ``vento.json``,
  com o **estado em análise** (o da página aberta).
- Só nas quadrículas de 0,25° (~28 km) que tiveram foco nos últimos ``DIAS_FOCOS`` dias da base — no estado
  inteiro passaria do limite gratuito do Open-Meteo (10 mil consultas por dia).
- Guarda a previsão hora a hora (o dia anterior e as próximas 48 h) em ``vento.parquet``; cada coleta
  substitui as horas repetidas e o arquivo guarda ``DIAS_GUARDADOS`` dias.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from core.config import BASES_DIR, NOME_FOCOS_PARQUET
from core.open_meteo import vento_horario
from core.rede import SemDadosAoVivo, obter_json

ARQUIVO_VENTO = "vento.parquet"
ARQUIVO_CHAVE_VENTO = "vento.json"
PASSO_GRAUS = 0.25
DIAS_FOCOS = 7
DIAS_GUARDADOS = 30
LIMITE_QUADRICULAS = 1500          # segurança: 6 coletas por dia × 1.500 < 10 mil consultas
COLUNAS_VENTO = ["sigla_uf", "lon", "lat", "hora", "velocidade_kmh", "direcao_graus", "rajada_kmh", "coletado_em"]


def _pasta(bases_dir) -> Path:
    return Path(bases_dir or BASES_DIR)


def chave_vento(bases_dir: Path | None = None) -> dict:
    """{"ligado": bool, "estado": "Pará"} — desligado se o arquivo não existe ou é inválido."""
    try:
        dados = json.loads((_pasta(bases_dir) / ARQUIVO_CHAVE_VENTO).read_text(encoding="utf-8"))
        return {"ligado": bool(dados.get("ligado")), "estado": dados.get("estado")}
    except (OSError, ValueError, AttributeError):
        return {"ligado": False, "estado": None}


def gravar_chave_vento(ligado: bool, estado: str | None, bases_dir: Path | None = None):
    (_pasta(bases_dir) / ARQUIVO_CHAVE_VENTO).write_text(
        json.dumps({"ligado": bool(ligado), "estado": estado}, ensure_ascii=False), encoding="utf-8")


def centro_da_quadricula(valor, passo: float = PASSO_GRAUS):
    return (np.floor(np.asarray(valor, dtype=float) / passo) + 0.5) * passo


def quadriculas_com_focos(estado: str, bases_dir: Path | None = None, dias: int = DIAS_FOCOS
                          ) -> tuple[str | None, list[tuple[float, float]]]:
    """(sigla da UF, centros das quadrículas de 0,25° com foco nos últimos ``dias`` dias da base)."""
    caminho = _pasta(bases_dir) / NOME_FOCOS_PARQUET
    if not caminho.exists():
        return None, []
    nome = str(estado).strip().upper()
    tabela = pq.read_table(caminho, columns=["lon", "lat", "data", "NM_UF", "SIGLA_UF"]).to_pandas()
    focos = tabela[(tabela["NM_UF"].str.upper() == nome) | (tabela["SIGLA_UF"].str.upper() == nome)]
    if focos.empty:
        return None, []
    datas = pd.to_datetime(focos["data"]).dt.normalize()
    recentes = focos[datas > datas.max() - pd.Timedelta(days=dias)]
    centros = pd.DataFrame({"lon": centro_da_quadricula(recentes["lon"]),
                            "lat": centro_da_quadricula(recentes["lat"])}).drop_duplicates()
    centros = centros.sort_values(["lat", "lon"]).head(LIMITE_QUADRICULAS)
    return str(focos["SIGLA_UF"].iloc[0]), [(float(x), float(y)) for x, y in zip(centros["lon"], centros["lat"])]


def coletar_vento(estado: str, bases_dir: Path | None = None, obter=obter_json, agora=None) -> str:
    """Busca e grava o vento do ``estado``; devolve uma frase para o painel. Erros viram frase, não exceção."""
    sigla, pontos = quadriculas_com_focos(estado, bases_dir)
    if not pontos:
        return f"Vento: nenhum foco em {estado} nos últimos {DIAS_FOCOS} dias da base — nada a buscar."
    try:
        df = vento_horario(pontos, obter=obter)
    except SemDadosAoVivo as erro:
        return f"Vento: {erro}"
    agora = agora or datetime.now(timezone.utc)
    df = df.assign(sigla_uf=sigla, lon=[pontos[i][0] for i in df["ponto"]], lat=[pontos[i][1] for i in df["ponto"]],
                   coletado_em=pd.Timestamp(agora).tz_convert("UTC").tz_localize(None))
    gravar_vento(df[COLUNAS_VENTO], bases_dir, agora)
    return f"Vento: {len(pontos)} quadrículas de {estado} atualizadas às {agora.astimezone():%H:%M}."


def gravar_vento(novo: pd.DataFrame, bases_dir: Path | None = None, agora=None):
    caminho = _pasta(bases_dir) / ARQUIVO_VENTO
    tabela = novo
    if caminho.exists():
        tabela = pd.concat([pd.read_parquet(caminho), novo], ignore_index=True)
    tabela = tabela.sort_values("coletado_em").drop_duplicates(["sigla_uf", "lon", "lat", "hora"], keep="last")
    corte = pd.Timestamp(agora or datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None) \
        - pd.Timedelta(days=DIAS_GUARDADOS)
    tabela = tabela[tabela["hora"] >= corte].sort_values(["sigla_uf", "hora", "lat", "lon"])
    temporario = caminho.with_name(caminho.name + ".tmp")
    tabela.to_parquet(temporario, index=False, compression="zstd")
    os.replace(temporario, caminho)


def carregar_vento(bases_dir: Path | None = None) -> pd.DataFrame:
    caminho = _pasta(bases_dir) / ARQUIVO_VENTO
    if not caminho.exists():
        return pd.DataFrame(columns=COLUNAS_VENTO)
    return pd.read_parquet(caminho)


def vento_na_hora(vento: pd.DataFrame, hora, sigla_uf: str | None = None) -> pd.DataFrame:
    """Uma linha por quadrícula: a previsão mais próxima de ``hora`` (UTC, sem fuso)."""
    if vento.empty:
        return vento
    v = vento if sigla_uf is None else vento[vento["sigla_uf"] == sigla_uf]
    hora = pd.Timestamp(hora)
    v = v.assign(_dist=(v["hora"] - hora).abs())
    return v.sort_values("_dist").drop_duplicates(["lon", "lat"]).drop(columns="_dist")
