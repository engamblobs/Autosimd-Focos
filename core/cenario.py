# -*- coding: utf-8 -*-
"""Cenário atual do estado ou de uma região (Panorama do Estado, docs/07 §11): últimas 24 h e última semana.

O satélite de referência (AQUA_M-T, passagem da tarde) passa **uma vez por dia** e a base guarda só a
data de cada foco, então "últimas 24 h" = a passagem mais recente: o último dia com focos na base
inteira (o dia corrente fica de fora enquanto a passagem dele não foi processada pelo INPE). "Última
semana" = os 7 dias até esse dia. As médias vêm do nowcast (mesmo dia e janela de ±3 dias nos anos
anteriores, ``core/nowcast.py``).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from core.config import VALORES_VAZIOS
from core.focos import da_uf, valido
from core.grade import Grade, grade_do_territorio, recorrencia, valor_na_celula
from core.nowcast import Nowcast, nowcast_territorio
from core.panorama import TODAS, regioes_dos_focos
from core.regioes import regiao_do_municipio, tipo_regiao

DIAS_SEMANA = 7


@dataclass
class CenarioAtual:
    estado: str
    sigla_uf: str | None
    regiao: str | None                   # None = estado inteiro
    tipo_regiao: str
    dia: date                            # passagem mais recente ("últimas 24 h")
    ultimo_dia_base: date                # último dia buscado no INPE (pode estar sem a passagem ainda)
    provisorio: bool                     # o dia da passagem ainda pode receber focos
    nowcast: Nowcast                     # série de 30 dias e médias dos anos anteriores
    focos_24h: pd.DataFrame              # focos da passagem mais recente (município, região, UC, TI, lat, lon)
    focos_semana: pd.DataFrame           # focos dos 7 dias até ``dia``
    municipios: pd.DataFrame             # focos por município: 24 h e semana
    areas: pd.DataFrame                  # UCs/TIs com focos na semana
    historico_mes: pd.DataFrame | None = None   # focos (lon, lat, ano) do mesmo mês nos anos comparados do nowcast

    @property
    def nome(self) -> str:
        return self.regiao or self.estado

    @property
    def inicio_semana(self) -> date:
        return self.dia - timedelta(days=DIAS_SEMANA - 1)


def dia_da_ultima_passagem(df: pd.DataFrame, ultimo_dia_base: date) -> date:
    """Último dia com focos na base inteira, sem passar do último dia buscado."""
    com_focos = df.loc[df["data"] <= ultimo_dia_base.isoformat(), "data"]
    return date.fromisoformat(com_focos.max()) if len(com_focos) else ultimo_dia_base


def focos_do_recorte(df: pd.DataFrame, estado: str, regiao: str | None) -> tuple[pd.DataFrame, str | None, str | None]:
    """(focos do estado ou da região com a coluna ``regiao``, sigla da UF, região ou None = estado inteiro)."""
    focos = da_uf(df, estado)
    focos = focos[valido(focos["NM_MUN"])]
    sigla = focos["SIGLA_UF"].mode().iloc[0] if len(focos) else None
    focos = focos.assign(regiao=regioes_dos_focos(focos, sigla))
    if regiao and regiao != TODAS:
        return focos[focos["regiao"] == regiao], sigla, regiao
    return focos, sigla, None


def cenario_atual(df: pd.DataFrame, estado: str, regiao: str | None, ultimo_dia_base: date, inicio_base: date,
                  provisorios: list[date] | None = None) -> CenarioAtual:
    """Cenário das últimas 24 h e da última semana no estado (``regiao`` None/TODAS) ou numa região dele."""
    focos, sigla, regiao = focos_do_recorte(df, estado, regiao)
    dia = dia_da_ultima_passagem(df, ultimo_dia_base)
    nome = regiao or estado
    nowcast = nowcast_territorio(focos, nome, dia, inicio_base, dia in (provisorios or []))

    colunas = ["data", "NM_MUN", "regiao", "UC", "TI", "lat", "lon"]
    inicio = (dia - timedelta(days=DIAS_SEMANA - 1)).isoformat()
    semana = focos[(focos["data"] >= inicio) & (focos["data"] <= dia.isoformat())][colunas]
    focos_24h = semana[semana["data"] == dia.isoformat()]

    por_mun = pd.DataFrame({
        "ultimas_24h": focos_24h.groupby("NM_MUN").size(),
        "semana": semana.groupby("NM_MUN").size(),
    }).fillna(0).astype(int).sort_values(["ultimas_24h", "semana"], ascending=False)
    municipios = pd.DataFrame([{
        "Município": m.title(), "Região": regiao_do_municipio(m, sigla),
        "Últimas 24 h": int(linha.ultimas_24h), "Última semana": int(linha.semana),
    } for m, linha in por_mun.iterrows()], columns=["Município", "Região", "Últimas 24 h", "Última semana"])

    linhas = []
    for campo, tipo in (("UC", "UC"), ("TI", "TI")):
        com_area = semana[valido(semana[campo])]
        contagem = pd.DataFrame({"ultimas_24h": com_area[com_area["data"] == dia.isoformat()].groupby(campo).size(),
                                 "semana": com_area.groupby(campo).size()}).fillna(0).astype(int)
        linhas += [{"Tipo": tipo, "Área protegida": nome_area, "Últimas 24 h": int(linha.ultimas_24h),
                    "Última semana": int(linha.semana)} for nome_area, linha in contagem.iterrows()]
    areas = pd.DataFrame(linhas, columns=["Tipo", "Área protegida", "Últimas 24 h", "Última semana"])
    areas = areas.sort_values(["Última semana", "Últimas 24 h"], ascending=False, kind="stable").reset_index(drop=True)

    historico_mes = focos.loc[(focos["mes"] == dia.month) & focos["ano"].isin(nowcast.anos_comparados),
                              ["lon", "lat", "ano"]].reset_index(drop=True)
    return CenarioAtual(estado=estado, sigla_uf=sigla, regiao=regiao, tipo_regiao=tipo_regiao(sigla), dia=dia,
                        ultimo_dia_base=ultimo_dia_base, provisorio=nowcast.provisorio, nowcast=nowcast,
                        focos_24h=focos_24h.reset_index(drop=True), focos_semana=semana.reset_index(drop=True),
                        municipios=municipios, areas=areas, historico_mes=historico_mes)


# ------------------------------------------------ Exportação dos focos (P29)

SATELITE_REFERENCIA = "AQUA_M-T"
MAX_FOCOS_GEOJSON = 200_000      # por arquivo (~100 MB); acima disso a tela pede um intervalo menor


def focos_no_intervalo(df: pd.DataFrame, estado: str, regiao: str | None, inicio: date, fim: date) -> pd.DataFrame:
    """Focos do estado ou da região de ``inicio`` a ``fim`` (inclusive), com todas as colunas da base."""
    focos, _, _ = focos_do_recorte(df, estado, regiao)
    focos = focos[(focos["data"] >= inicio.isoformat()) & (focos["data"] <= fim.isoformat())]
    return focos.sort_values(["data", "NM_MUN", "lat"]).reset_index(drop=True)


def geojson_focos(focos: pd.DataFrame, tipo_regiao_: str, descricao: str) -> dict:
    """FeatureCollection de pontos (WGS 84) com todos os dados de ocorrência de cada foco."""
    def texto(valor):
        return None if valor in VALORES_VAZIOS else valor

    feicoes = [{
        "type": "Feature",
        "properties": {
            "id": n, "data": r.data, "ano": int(r.ano), "mes": int(r.mes), "latitude": float(r.lat),
            "longitude": float(r.lon), "municipio": r.NM_MUN.title(), "uf": r.NM_UF.title(), "sigla_uf": r.SIGLA_UF,
            "regiao": r.regiao, "tipo_regiao": tipo_regiao_, "unidade_conservacao": texto(r.UC),
            "terra_indigena": texto(r.TI), "satelite": SATELITE_REFERENCIA, "fonte": "BDQueimadas/INPE",
        },
        "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
    } for n, r in enumerate(focos.itertuples(), start=1)]
    return {"type": "FeatureCollection", "name": "focos_autosimd", "descricao": descricao,
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}, "features": feicoes}


# --------------------------------- Recorrência do mês × focos atuais (docs/07 §11)

@dataclass
class RecorrenciaDoMes:
    mes: int
    anos: list[int]                      # anos comparados (os do nowcast)
    grade: Grade
    matriz: np.ndarray                   # [x, y] nº de anos com foco nesse mês na célula
    atuais: pd.DataFrame                 # focos da semana com a coluna ``recorrencia`` (anos da célula)

    @property
    def em_celulas_com_historico(self) -> float | None:
        return float((self.atuais["recorrencia"] > 0).mean() * 100) if len(self.atuais) else None

    @property
    def em_celulas_frequentes(self) -> float | None:
        """% dos focos atuais em células com fogo nesse mês em pelo menos metade dos anos."""
        if not len(self.atuais) or not self.anos:
            return None
        return float((self.atuais["recorrencia"] >= len(self.anos) / 2).mean() * 100)


def recorrencia_do_mes(cen: CenarioAtual, limites) -> RecorrenciaDoMes:
    """Grade proporcional do território (docs/07 §4): em quantos anos cada célula teve foco no mês do dia da
    passagem, e em que células caíram os focos da última semana."""
    grade = grade_do_territorio(limites)
    historico = cen.historico_mes if cen.historico_mes is not None else pd.DataFrame(columns=["lon", "lat", "ano"])
    matriz = recorrencia(grade, historico["lon"], historico["lat"], historico["ano"])
    atuais = cen.focos_semana.assign(recorrencia=valor_na_celula(grade, matriz, cen.focos_semana["lon"],
                                                                 cen.focos_semana["lat"]).astype(int))
    return RecorrenciaDoMes(cen.dia.month, list(cen.nowcast.anos_comparados), grade, matriz, atuais)
