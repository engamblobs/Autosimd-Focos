"""
===============================================================================
AUTOSIMD-FOCOS - Módulo de Inteligência Analítica e Estatística
Sala de Informações e Monitoramento de Desastres (SIMD) / CEDEC-PA
===============================================================================
"""

import json
from pathlib import Path
from typing import Dict, Tuple
import numpy as np
import pandas as pd

# Tentativa de import do scikit-learn para clustering espacial
try:
  from sklearn.cluster import DBSCAN

  HAS_SKLEARN = True
except ImportError:
  HAS_SKLEARN = False


class AnalisadorFocosSIMD:

  def __init__(self, data_folder: str):
    self.data_folder = Path(data_folder)
    self.df = pd.DataFrame()

  def carregar_dados(self) -> pd.DataFrame:
      """Lê todos os GeoJSONs da pasta configurada e padroniza a estrutura."""
      json_files = list(self.data_folder.glob("bdqueimadas_*"))
      if not json_files:
        raise FileNotFoundError(
            f"Nenhum arquivo 'bdqueimadas_*' encontrado em: {self.data_folder}"
        )

      records = []
      print(f"[SIMD-LOADER] Lendo {len(json_files)} arquivos GeoJSON...")

      for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as f:
          try:
            data = json.load(f)
            features = data.get("features", [])
            for feat in features:
              props = feat.get("properties", {})
              coords = feat.get("geometry", {}).get("coordinates", [None, None])
              props["Longitude"] = (
                  coords[0] if coords[0] is not None else props.get("Longitude")
              )
              props["Latitude"] = (
                  coords[1] if coords[1] is not None else props.get("Latitude")
              )
              records.append(props)
          except Exception as e:
            print(f"[ERRO] Falha ao ler {file_path.name}: {e}")

      self.df = pd.DataFrame(records)
      self._preprocessar()
      print(f"[SIMD-LOADER] Base total carregada: {len(self.df):,} registros.")
      return self.df

  def _preprocessar(self):
    """Padronização de tipos de dados, sanitização e atributos temporais."""
    # DataHora
    self.df["DataHora"] = pd.to_datetime(self.df["DataHora"], errors="coerce")
    self.df = self.df.dropna(subset=["DataHora"])

    # Normalização de nomes de Município e Estado
    self.df["Municipio"] = (
        self.df["Municipio"].astype(str).str.upper().str.strip()
    )
    self.df["Estado"] = self.df["Estado"].astype(str).str.upper().str.strip()

    # Atributos Temporais
    self.df["Ano"] = self.df["DataHora"].dt.year
    self.df["Mes"] = self.df["DataHora"].dt.month
    self.df["Data"] = self.df["DataHora"].dt.date

    # Colunas Numéricas
    cols_num = ["FRP", "RiscoFogo", "Precipitacao", "DiaSemChuva"]
    for col in cols_num:
      if col in self.df.columns:
        self.df[col] = pd.to_numeric(self.df[col], errors="coerce").fillna(0.0)

  def extrair_municipio(self, municipio: str) -> pd.DataFrame:
    """Filtra o DataFrame para um município específico."""
    muni_clean = municipio.upper().strip()
    df_muni = self.df[self.df["Municipio"] == muni_clean].copy()
    if df_muni.empty:
      raise ValueError(
          f"Nenhum registro encontrado para o município: '{municipio}'"
      )
    return df_muni

  # --- 1. SÉRIE TEMPORAL E TENDÊNCIA HISTÓRICA ---
  def serie_historica_anual(self, df_muni: pd.DataFrame) -> pd.DataFrame:
    """Retorna total de focos, FRP médio e FRP total por ano."""
    resumo = (
        df_muni.groupby("Ano")
        .agg(
            total_focos=("DataHora", "count"),
            frp_medio=("FRP", "mean"),
            frp_acumulado=("FRP", "sum"),
        )
        .reset_index()
    )

    # Taxa de variação percentual ano a ano
    resumo["variacao_pct"] = resumo["total_focos"].pct_change() * 100
    return resumo

  # --- 2. SAZONALIDADE E JANELA OPERACIONAL ---
  def perfil_sazonal_mensal(self, df_muni: pd.DataFrame) -> pd.DataFrame:
    """Calcula a média, mediana e máximo histórico de focos para cada mês."""
    mensal_ano = (
        df_muni.groupby(["Ano", "Mes"]).size().reset_index(name="focos")
    )

    sazonal = (
        mensal_ano.groupby("Mes")["focos"]
        .agg(
            media_focos="mean",
            mediana_focos="median",
            max_focos="max",
            min_focos="min",
        )
        .reset_index()
    )

    # Identifica o mês de pico médio
    sazonal["mes_nome"] = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    return sazonal[["Mes", "mes_nome", "media_focos", "mediana_focos", "max_focos"]]

  # --- 3. ANOMALIAS E Z-SCORE (BASELINE 2006-2025 vs ALVO) ---
  def calcular_anomalia_zscore(
      self, df_muni: pd.DataFrame, ano_alvo: int = 2026
  ) -> pd.DataFrame:
    """Compara o volume mensal do ano alvo contra a linha de base histórica (2006-2025)

    utilizando a fórmula $Z = \\frac{X_{mês} - \\mu_{mês}}{\\sigma_{mês}}$.
    """
    df_base = df_muni[df_muni["Ano"] < ano_alvo]
    df_alvo = df_muni[df_muni["Ano"] == ano_alvo]

    # Matriz Histórica [Ano, Mes]
    base_grouped = (
        df_base.groupby(["Ano", "Mes"]).size().reset_index(name="focos")
    )

    # Média e Desvio Padrão Históricos por Mês
    stats_base = (
        base_grouped.groupby("Mes")["focos"]
        .agg(media_hist="mean", std_hist="std")
        .reset_index()
    )
    stats_base["std_hist"] = stats_base["std_hist"].replace(0, 1.0)

    # Focos do Ano Alvo
    alvo_grouped = (
        df_alvo.groupby("Mes").size().reset_index(name="focos_ano_alvo")
    )

    # Merge e cálculo de Z-Score
    resultado = pd.merge(stats_base, alvo_grouped, on="Mes", how="left").fillna(
        0
    )
    resultado["z_score"] = (
        resultado["focos_ano_alvo"] - resultado["media_hist"]
    ) / resultado["std_hist"]

    # Classificação Operacional SIMD
    def classificar_alerta(z):
      if z >= 2.0:
        return "EMERGÊNCIA (Z >= 2.0)"
      elif z >= 1.5:
        return "ALERTA (1.5 <= Z < 2.0)"
      elif z >= 1.0:
        return "ATENÇÃO (1.0 <= Z < 1.5)"
      else:
        return "NORMAL (Z < 1.0)"

    resultado["nivel_alerta"] = resultado["z_score"].apply(classificar_alerta)
    resultado["Ano"] = ano_alvo
    return resultado[
        [
            "Ano",
            "Mes",
            "focos_ano_alvo",
            "media_hist",
            "z_score",
            "nivel_alerta",
        ]
    ]

  # --- 4. DETECÇÃO DE SURTOS DIÁRIOS (BURSTS) ---
  def detectar_surtos_diarios(
      self, df_muni: pd.DataFrame, top_n: int = 5
  ) -> pd.DataFrame:
    """Identifica as datas com os maiores picos diários de focos registrados."""
    surtos = (
        df_muni.groupby("Data")
        .agg(total_focos=("DataHora", "count"), frp_max=("FRP", "max"))
        .reset_index()
        .sort_values(by="total_focos", ascending=False)
    )
    return surtos.head(top_n)

  # --- 5. CLUSTERIZAÇÃO ESPACIAL DE NÚCLEOS QUENTES ---
  def clusterizar_hotspots_dbscan(
      self, df_muni: pd.DataFrame, raio_km: float = 10.0, min_focos: int = 10
  ) -> pd.DataFrame:
    """Agrupa focos de calor próximos usando o algoritmo DBSCAN sem depender do QGIS."""
    if not HAS_SKLEARN:
      print("[AVISO] Scikit-Learn não instalado. Pulando DBSCAN.")
      return pd.DataFrame()

    df_valid = df_muni.dropna(subset=["Latitude", "Longitude"]).copy()
    if len(df_valid) < min_focos:
      return pd.DataFrame()

    # Converter Lat/Lon para Radianos para cálculo Haversine
    coords_rad = np.radians(df_valid[["Latitude", "Longitude"]])
    kms_per_radian = 6371.0088
    epsilon = raio_km / kms_per_radian

    db = DBSCAN(
        eps=epsilon, min_samples=min_focos, metric="haversine"
    ).fit(coords_rad)
    df_valid["cluster"] = db.labels_

    # Filtrar ruídos (cluster -1)
    clusters = df_valid[df_valid["cluster"] != -1]
    resumo_clusters = (
        clusters.groupby("cluster")
        .agg(
            total_focos=("DataHora", "count"),
            lat_centro=("Latitude", "mean"),
            lon_centro=("Longitude", "mean"),
            frp_acumulado=("FRP", "sum"),
        )
        .sort_values(by="total_focos", ascending=False)
        .reset_index()
    )

    return resumo_clusters