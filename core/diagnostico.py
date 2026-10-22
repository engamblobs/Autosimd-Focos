# -*- coding: utf-8 -*-
"""Cálculos do diagnóstico (docs/07): indicadores, rankings, séries anual e mensal.

Dois níveis de análise:
- município (``diagnosticar_municipio``): indicadores completos, rankings no estado, no país e
  na região (de Integração no Pará, Geográfica Imediata nos demais), UCs/TIs sobrepostas;
- área protegida, UC ou TI (``diagnosticar_area``): focos dentro da área.

Os focos de cada território são os das colunas ``NM_MUN``/``SIGLA_UF``, ``UC`` e ``TI`` da base, que
são o cruzamento ponto-no-polígono já calculado (conferido na base inteira, docs/07 §1).

Nada aqui desenha ou depende do Streamlit; as figuras ficam em ``graficos.py`` e ``mapas.py``.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from core.config import TIPO_TI, TIPO_UC, TOP_ESTADO
from core.focos import da_uf, no_periodo, valido
from core.regioes import SEM_REGIAO, regiao_do_municipio, tipo_regiao, titulo_regiao
from core.territorios import area_km2, contar_focos_na_area
from core.texto import fmt_percentual

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = [m[:3] for m in MESES]
CAMPO_AREA = {TIPO_UC: "UC", TIPO_TI: "TI"}
COLUNAS_RANKING = ["focos", "ultimo_mes", "ultima_semana"]


# ------------------------------------------------------------- Peças comuns

def serie_anual(focos: pd.DataFrame, ano_inicio: int, ano_fim: int) -> dict[int, int]:
    """Focos por ano, com zero nos anos sem focos."""
    contagem = focos["ano"].value_counts()
    return {ano: int(contagem.get(ano, 0)) for ano in range(ano_inicio, ano_fim + 1)}


def distribuicao_mensal(focos: pd.DataFrame) -> dict[int, int]:
    """Focos acumulados por mês (1–12) no período."""
    contagem = focos["mes"].value_counts()
    return {mes: int(contagem.get(mes, 0)) for mes in range(1, 13)}


def fim_dos_dados(focos: pd.DataFrame, ano_fim: int) -> date:
    """Último dia com focos até 31/12 do ano final (referência do desempate)."""
    datas = focos.loc[focos["ano"] <= ano_fim, "data"]
    return date.fromisoformat(datas.max()) if len(datas) else date(ano_fim, 12, 31)


def ranking(focos: pd.DataFrame, chave, fim: date) -> pd.DataFrame:
    """Ranking por ``chave`` (coluna ou lista): mais focos primeiro.

    Desempate (P2): mais focos no último mês (do 1º dia do mês de ``fim`` até ``fim``) e, se ainda
    empatar, na última semana (os 7 dias até ``fim``). Empate nos três = mesma posição; na listagem,
    ordem alfabética. Colunas: ``focos``, ``ultimo_mes``, ``ultima_semana``, ``posicao``.
    """
    chave = chave if isinstance(chave, list) else [chave]
    focos = focos[valido(focos[chave[-1]])]
    if focos.empty:
        return pd.DataFrame(columns=COLUNAS_RANKING + ["posicao"])
    tabela = focos.groupby(chave).size().to_frame("focos")
    for coluna, inicio in (("ultimo_mes", fim.replace(day=1)), ("ultima_semana", fim - timedelta(days=6))):
        recorte = focos[(focos["data"] >= inicio.isoformat()) & (focos["data"] <= fim.isoformat())]
        tabela[coluna] = recorte.groupby(chave).size().reindex(tabela.index, fill_value=0)
    tabela = tabela.sort_index().sort_values(COLUNAS_RANKING, ascending=False, kind="stable")
    criterio = list(tabela[COLUNAS_RANKING].itertuples(index=False, name=None))
    posicoes = []
    for i, valor in enumerate(criterio):
        posicoes.append(posicoes[-1] if i and valor == criterio[i - 1] else i + 1)
    tabela["posicao"] = posicoes
    return tabela


def posicao(tabela: pd.DataFrame, chave) -> int:
    """Posição de ``chave`` no ``ranking``; 0 = fora do ranking (sem focos)."""
    return int(tabela.loc[chave, "posicao"]) if chave in tabela.index else 0


def ranking_simples(focos: pd.DataFrame, coluna: str, fim: date | None = None) -> pd.DataFrame:
    """Contagem de focos por município, UC ou TI (CSV do pacote), na ordem do ranking, sem vazios."""
    fim = fim or (date.fromisoformat(focos["data"].max()) if len(focos) else date.today())
    tabela = ranking(focos, coluna, fim)
    return tabela["focos"].rename("Focos de Calor").rename_axis(coluna).reset_index()


def ranking_areas_protegidas(focos_periodo: pd.DataFrame, campo: str, rotulo: str,
                             fim: date | None = None) -> pd.DataFrame:
    """Ranking das UCs ou TIs com participação no total de focos em áreas desse tipo."""
    colunas = ["Posição", rotulo, "Focos de Calor", "Participação (%)"]
    fim = fim or (date.fromisoformat(focos_periodo["data"].max()) if len(focos_periodo) else date.today())
    tabela = ranking(focos_periodo, campo, fim)
    if tabela.empty:
        return pd.DataFrame(columns=colunas)
    return pd.DataFrame({
        "Posição": tabela["posicao"].to_numpy(),
        rotulo: tabela.index.to_numpy(),
        "Focos de Calor": tabela["focos"].to_numpy(),
        "Participação (%)": (tabela["focos"] / tabela["focos"].sum() * 100).round(2).to_numpy(),
    })


def rankings_areas_protegidas(focos_periodo_brasil: pd.DataFrame, focos_periodo_estado: pd.DataFrame,
                              fim: date) -> dict[str, pd.DataFrame]:
    """UCs e TIs com focos no estado e no Brasil inteiro, no período (P6)."""
    return {
        f"{campo}_{escopo}": ranking_areas_protegidas(focos, campo, tipo, fim)
        for campo, tipo in (("UC", TIPO_UC), ("TI", TIPO_TI))
        for escopo, focos in (("estado", focos_periodo_estado), ("brasil", focos_periodo_brasil))
    }


def _variacao(atual: int, anterior: int | None) -> float | None:
    """Variação % em relação ao ano anterior; None sem ano anterior no período ou com zero focos nele."""
    if not anterior:
        return None
    return (atual - anterior) / anterior * 100


def _sigla_uf(focos: pd.DataFrame, padrao: str | None = None) -> str | None:
    siglas = focos["SIGLA_UF"]
    siglas = siglas[valido(siglas)]
    if not siglas.empty:
        return siglas.mode().iloc[0]
    return padrao.upper() if padrao and len(padrao) == 2 else None


# ---------------------------------------------------------------- Município

@dataclass
class ResumoMunicipio:
    """Indicadores do resumo executivo (docs/07 §2)."""
    focos_ano_fim: int
    focos_ano_anterior: int | None       # None quando o ano anterior está fora do período
    variacao_pct: float | None
    participacao_estado_pct: float
    posicao_pais: int
    total_pais: int
    posicao_estado: int
    total_estado: int
    focos_periodo: int
    media_anual: float
    area_km2: float | None
    densidade: float | None              # focos/km²/ano


@dataclass
class DiagnosticoMunicipio:
    estado: str                          # como no nome do arquivo GeoJSON ("Pará")
    sigla_uf: str | None
    municipio: str                       # como na base de focos (MAIÚSCULAS)
    ano_inicio: int
    ano_fim: int
    regiao: str
    poligono: object
    focos: pd.DataFrame                  # do município, no período
    focos_estado: pd.DataFrame           # do estado, no período
    resumo: ResumoMunicipio
    serie_anual: dict[int, int]
    mensal: dict[int, int]
    top_acumulado: list[tuple[str, int]]
    ranking_estado: pd.DataFrame
    ranking_regiao: pd.DataFrame
    rankings_areas: dict[str, pd.DataFrame] = field(default_factory=dict)
    fim_dados: date | None = None
    areas: list[dict] = field(default_factory=list)
    tabela_areas: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def nome(self) -> str:
        return self.municipio.title()

    @property
    def focos_ano_fim(self) -> pd.DataFrame:
        return self.focos[self.focos["ano"] == self.ano_fim]

    @property
    def tipo_regiao(self) -> str:
        return tipo_regiao(self.sigla_uf)

    @property
    def titulo_regiao(self) -> str:
        return titulo_regiao(self.regiao, self.sigla_uf)


def tabela_ranking_estado(no_ano: pd.DataFrame, acumulado: pd.DataFrame, sigla_uf, ano_fim: int,
                          n: int = TOP_ESTADO) -> pd.DataFrame:
    """Os ``n`` primeiros do estado no ano final (ordem do ``ranking``)."""
    return pd.DataFrame([{
        "Posição": f"{linha.posicao}º",
        "Município": municipio.title(),
        "Região": regiao_do_municipio(municipio, sigla_uf),
        f"Focos ({ano_fim})": int(linha.focos),
        "Acumulado": int(acumulado["focos"].get(municipio, 0)),
    } for municipio, linha in no_ano.head(n).iterrows()],
        columns=["Posição", "Município", "Região", f"Focos ({ano_fim})", "Acumulado"])


def tabela_ranking_regiao(focos_ano: pd.DataFrame, regiao: str, sigla_uf, ano_fim: int, fim: date) -> pd.DataFrame:
    """Municípios da mesma região com focos no ano final, posição refeita dentro da região."""
    colunas = ["Posição", "Município", f"Focos ({ano_fim})", "% Região"]
    if regiao == SEM_REGIAO:
        return pd.DataFrame(columns=colunas)
    municipios = [m for m in focos_ano["NM_MUN"].unique() if regiao_do_municipio(m, sigla_uf) == regiao]
    tabela = ranking(focos_ano[focos_ano["NM_MUN"].isin(municipios)], "NM_MUN", fim)
    total = int(tabela["focos"].sum()) if len(tabela) else 0
    return pd.DataFrame([{
        "Posição": f"{linha.posicao}º",
        "Município": municipio.title(),
        f"Focos ({ano_fim})": int(linha.focos),
        "% Região": fmt_percentual(linha.focos / total * 100) if total else "0%",
    } for municipio, linha in tabela.iterrows()], columns=colunas)


def tabela_areas_no_municipio(areas: list[dict], focos: pd.DataFrame, ano_inicio: int, ano_fim: int) -> pd.DataFrame:
    focos_ano = focos[focos["ano"] == ano_fim]
    return pd.DataFrame([{
        "Nº": a["num"],
        "Tipo": a["tipo"],
        "Nome": a["nome"],
        "Área no município (km²)": round(a["area_km2"]) if a["area_km2"] else None,
        "% da área protegida no município": round(a["pct_da_area"], 1) if a["pct_da_area"] is not None else None,
        f"Focos em {ano_fim}": contar_focos_na_area(focos_ano, a["recorte"]),
        f"Focos {ano_inicio}–{ano_fim}": contar_focos_na_area(focos, a["recorte"]),
    } for a in areas])


def diagnosticar_municipio(df: pd.DataFrame, estado: str, municipio: str, ano_inicio: int, ano_fim: int,
                           poligono=None, areas: list[dict] | None = None) -> DiagnosticoMunicipio:
    """Diagnóstico de um município no período ``ano_inicio``–``ano_fim`` (inclusive).

    ``df`` = base inteira (o ranking nacional usa todos os estados); ``areas`` = UCs/TIs já
    recortadas pelo município (``territorios.areas_protegidas_no_territorio``).
    """
    municipio = municipio.strip().upper()
    periodo = no_periodo(df, ano_inicio, ano_fim)
    focos_estado = da_uf(periodo, estado)
    focos_estado = focos_estado[valido(focos_estado["NM_MUN"])]
    focos = focos_estado[focos_estado["NM_MUN"] == municipio]
    sigla_uf = _sigla_uf(focos_estado, estado)
    fim = fim_dos_dados(periodo, ano_fim)

    estado_ano = focos_estado[focos_estado["ano"] == ano_fim]
    no_ano_fim = ranking(estado_ano, "NM_MUN", fim)
    acumulado = ranking(focos_estado, "NM_MUN", fim)

    serie = serie_anual(focos, ano_inicio, ano_fim)
    focos_ano_fim = serie[ano_fim]
    focos_ano_anterior = serie.get(ano_fim - 1)
    total_estado_ano = len(estado_ano)

    # País: (UF, município), para não somar homônimos de estados diferentes
    pais = periodo[(periodo["ano"] == ano_fim) & valido(periodo["NM_MUN"]) & valido(periodo["SIGLA_UF"])]
    no_pais = ranking(pais, ["SIGLA_UF", "NM_MUN"], fim)

    n_anos = ano_fim - ano_inicio + 1
    media_anual = len(focos) / n_anos
    area = area_km2(poligono)
    regiao = regiao_do_municipio(municipio, sigla_uf)
    resumo = ResumoMunicipio(
        focos_ano_fim=focos_ano_fim,
        focos_ano_anterior=focos_ano_anterior,
        variacao_pct=_variacao(focos_ano_fim, focos_ano_anterior),
        participacao_estado_pct=focos_ano_fim / total_estado_ano * 100 if total_estado_ano else 0.0,
        posicao_pais=posicao(no_pais, (sigla_uf, municipio)),
        total_pais=len(no_pais),
        posicao_estado=posicao(no_ano_fim, municipio),
        total_estado=len(no_ano_fim),
        focos_periodo=len(focos),
        media_anual=media_anual,
        area_km2=area,
        densidade=media_anual / area if area else None,
    )
    areas = areas or []
    return DiagnosticoMunicipio(
        estado=estado, sigla_uf=sigla_uf, municipio=municipio, ano_inicio=ano_inicio, ano_fim=ano_fim,
        regiao=regiao, poligono=poligono, focos=focos, focos_estado=focos_estado, resumo=resumo,
        serie_anual=serie, mensal=distribuicao_mensal(focos),
        top_acumulado=[(m.title(), int(n)) for m, n in acumulado["focos"].head(TOP_ESTADO).items()],
        ranking_estado=tabela_ranking_estado(no_ano_fim, acumulado, sigla_uf, ano_fim),
        ranking_regiao=tabela_ranking_regiao(estado_ano, regiao, sigla_uf, ano_fim, fim),
        rankings_areas=rankings_areas_protegidas(periodo, focos_estado, fim), fim_dados=fim,
        areas=areas, tabela_areas=tabela_areas_no_municipio(areas, focos, ano_inicio, ano_fim),
    )


# ------------------------------------------------------------ Área protegida

@dataclass
class DiagnosticoArea:
    tipo: str                            # TIPO_UC ou TIPO_TI
    nome: str                            # rótulo da base ("NOME (CÓDIGO)")
    ano_inicio: int
    ano_fim: int
    poligono: object
    focos: pd.DataFrame                  # dentro da área, no período
    serie_anual: dict[int, int]
    mensal: dict[int, int]
    sigla_uf: str | None = None          # estado com mais focos da área (rankings "no estado")
    rankings_areas: dict[str, pd.DataFrame] = field(default_factory=dict)
    fim_dados: date | None = None

    @property
    def campo(self) -> str:
        return CAMPO_AREA[self.tipo]

    @property
    def focos_ano_fim(self) -> int:
        return self.serie_anual[self.ano_fim]

    @property
    def focos_periodo(self) -> int:
        return len(self.focos)

    @property
    def media_anual(self) -> float:
        return self.focos_periodo / len(self.serie_anual)

    @property
    def municipio(self) -> str:          # nome usado nos títulos (mesmo atributo do DiagnosticoMunicipio)
        return self.nome


def diagnosticar_area(df: pd.DataFrame, tipo: str, nome: str, ano_inicio: int, ano_fim: int,
                      poligono=None) -> DiagnosticoArea:
    """Focos atribuídos à UC/TI na base (coluna UC ou TI, docs/07 §6), no período."""
    nome = nome.strip().upper()
    periodo = no_periodo(df, ano_inicio, ano_fim)
    focos = periodo[periodo[CAMPO_AREA[tipo]] == nome]
    sigla_uf = _sigla_uf(focos)
    fim = fim_dos_dados(periodo, ano_fim)
    focos_estado = periodo[periodo["SIGLA_UF"] == sigla_uf] if sigla_uf else periodo.iloc[0:0]
    return DiagnosticoArea(tipo=tipo, nome=nome, ano_inicio=ano_inicio, ano_fim=ano_fim, poligono=poligono,
                           focos=focos, serie_anual=serie_anual(focos, ano_inicio, ano_fim),
                           mensal=distribuicao_mensal(focos), sigla_uf=sigla_uf,
                           rankings_areas=rankings_areas_protegidas(periodo, focos_estado, fim), fim_dados=fim)
