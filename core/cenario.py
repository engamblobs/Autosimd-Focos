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
from core.texto import fmt_inteiro

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


def recorrencia_mensal(historico: pd.DataFrame, atuais: pd.DataFrame, limites, mes: int,
                       anos: list[int]) -> RecorrenciaDoMes:
    """Grade proporcional do território (docs/07 §4): em quantos ``anos`` cada célula teve foco no ``mes``
    (``historico`` = focos com lon, lat, ano e mes) e em que células caíram os focos ``atuais``."""
    grade = grade_do_territorio(limites)
    if "mes" in historico.columns:
        historico = historico[(historico["mes"] == mes) & historico["ano"].isin(anos)]
    matriz = recorrencia(grade, historico["lon"], historico["lat"], historico["ano"])
    atuais = atuais.assign(recorrencia=valor_na_celula(grade, matriz, atuais["lon"], atuais["lat"]).astype(int))
    return RecorrenciaDoMes(mes, list(anos), grade, matriz, atuais)


def recorrencia_do_mes(cen: CenarioAtual, limites) -> RecorrenciaDoMes:
    """Recorrência do mês da passagem × focos da última semana no estado/região."""
    historico = cen.historico_mes if cen.historico_mes is not None else pd.DataFrame(columns=["lon", "lat", "ano"])
    return recorrencia_mensal(historico, cen.focos_semana, limites, cen.dia.month, cen.nowcast.anos_comparados)


# ------------------------------------------------------- Texto do cenário atual

MESES_EXTENSO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                 "outubro", "novembro", "dezembro"]


# preposição com o nome do estado ("no Pará", "na Bahia", "em Goiás")
_NO = {"Acre", "Amapá", "Amazonas", "Ceará", "Distrito Federal", "Espírito Santo", "Maranhão", "Mato Grosso",
       "Mato Grosso do Sul", "Pará", "Paraná", "Piauí", "Rio de Janeiro", "Rio Grande do Norte", "Rio Grande do Sul",
       "Tocantins"}
_NA = {"Bahia", "Paraíba"}


def em_territorio(nome: str) -> str:
    """"no Pará", "na Bahia", "em Goiás", "na Região Xingu"."""
    if nome in _NO:
        return f"no {nome}"
    if nome in _NA or nome.startswith("Região"):
        return f"na {nome}"
    return f"em {nome}"


def _comparacao(valor: float, media: float) -> str:
    if media != media or not media:
        return ""
    diferenca = (valor - media) / media * 100
    if abs(diferenca) < 5:
        return f", próximo da média dos mesmos dias nos anos anteriores ({fmt_inteiro(round(media))})"
    lado = "acima" if diferenca > 0 else "abaixo"
    return (f", {fmt_inteiro(round(abs(diferenca)))}% {lado} da média dos mesmos dias nos anos anteriores "
            f"({fmt_inteiro(round(media))})")


def texto_do_cenario(cen: CenarioAtual, acima_no_mes: pd.DataFrame | None = None,
                     anos_recorde: tuple[int, int] | None = None, max_citados: int = 8,
                     no_relatorio: bool = False) -> list[str]:
    """Parágrafos que apresentam o cenário atual (tela e PDF do cenário), só com números calculados."""
    i = cen.nowcast.indicadores
    nome, dia = cen.nome, cen.dia
    parcial = " (dia ainda parcial)" if cen.provisorio else ""
    textos = [
        f"Na passagem mais recente do satélite de referência ({dia:%d/%m/%Y}{parcial}) foram detectados "
        f"{fmt_inteiro(i['ultimo_dia'])} focos de calor {em_territorio(nome)}"
        f"{_comparacao(i['ultimo_dia'], i['media_ultimo_dia'])}. "
        f"Na última semana ({cen.inicio_semana:%d/%m} a {dia:%d/%m}) foram {fmt_inteiro(i['ultimos_7'])} focos"
        f"{_comparacao(i['ultimos_7'], i['media_7'])}, em {fmt_inteiro(cen.focos_semana['NM_MUN'].nunique())} "
        "municípios."]
    variacao = i["variacao_acumulado_pct"]
    if variacao is not None:
        lado = "acima" if variacao >= 0 else "abaixo"
        textos.append(f"No ano, até {dia:%d/%m}, são {fmt_inteiro(i['acumulado_ano'])} focos, "
                      f"{fmt_inteiro(round(abs(variacao)))}% {lado} da média do mesmo período — o "
                      f"{i['posicao_acumulado']}º maior acumulado até esta data entre {i['anos_ranking']} anos.")
    if acima_no_mes is not None and anos_recorde:
        mes = MESES_EXTENSO[dia.month - 1]
        periodo = f"{anos_recorde[0]}–{anos_recorde[1]}"
        if acima_no_mes.empty:
            textos.append(f"Nenhum município {em_territorio(nome)} ultrapassou, em {mes} (de 1º a {dia:%d/%m}), a "
                          f"máxima histórica de focos das mesmas datas ({periodo}).")
        else:
            citados = []
            for _, r in acima_no_mes.head(max_citados).iterrows():
                ano = r["Ano da máxima"]
                antes = ("nenhum foco antes nessas datas" if pd.isna(ano)
                         else f"máxima anterior {fmt_inteiro(r['Máxima anterior'])} em {int(ano)}")
                citados.append(f"{r['Município']} ({fmt_inteiro(r['Focos no mês'])} focos; {antes})")
            resto = len(acima_no_mes) - len(citados)
            textos.append(
                f"Em {mes} (de 1º a {dia:%d/%m}), {len(acima_no_mes)} município(s) já ultrapassaram a máxima "
                f"histórica de focos das mesmas datas ({periodo}): " + "; ".join(citados)
                + (f"; e mais {resto}." if resto > 0 else ".")
                + (" A sazonalidade de cada um está no fim do relatório." if no_relatorio else ""))
    em_uc, em_ti = int((cen.focos_semana["UC"] != "NONE").sum()), int((cen.focos_semana["TI"] != "NONE").sum())
    if em_uc or em_ti:
        texto = (f"Na última semana, {fmt_inteiro(em_uc)} focos ocorreram em Unidades de Conservação e "
                 f"{fmt_inteiro(em_ti)} em Terras Indígenas")
        if not cen.areas.empty:
            a = cen.areas.iloc[0]
            texto += (f"; a área protegida com mais focos foi {a['Área protegida']} "
                      f"({fmt_inteiro(a['Última semana'])})")
        textos.append(texto + ".")
    return textos
