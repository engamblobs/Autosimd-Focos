# -*- coding: utf-8 -*-
"""Estatísticas de focos ativos do território, no modelo do Programa Queimadas/INPE (docs/07 §8).

Vale para município, UC e TI. Os focos do território são os do cruzamento ponto-no-polígono
(colunas ``NM_MUN``/``SIGLA_UF``, ``UC``, ``TI`` da base, docs/07 §1), no período em análise. Para
cada ano, os meses (semanas, dias) fora da cobertura da base ficam vazios (``NaN``, exibidos como
"-"), como no site do INPE.

Mínimo, média e máximo usam todos os anos do período **exceto o ano de referência**
(padrão: o ano final), que é o ano comparado.
"""

import calendar
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_TABELA = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
# unidade → (rótulo do eixo, dias por bloco; None = mês do calendário)
UNIDADES = {"mensal": ("Mês", None), "semanal": ("Semana", 7), "semestre1": ("Semana do semestre", 7),
            "semestre2": ("Semana do semestre", 7)}
# Semestres: (primeiro mês, último mês); semanas = blocos de 7 dias a partir do 1º dia do semestre (01/01 e
# 01/07), a última curta como a semana 53 do semanal: 26 no 1º (a 26ª com 6 ou 7 dias) e 27 no 2º (30–31/12)
SEMESTRES = {"semestre1": (1, 6), "semestre2": (7, 12)}
SEMANAS_SEMESTRE = {"semestre1": 26, "semestre2": 27}
LINHAS_RESUMO = ["Mínimo", "Média", "Máximo"]


@dataclass(frozen=True)
class ParametrosEstatisticas:
    """Parâmetros ajustáveis na tela (``None`` = padrão calculado)."""
    ano_referencia: int | None = None      # padrão: ano final do período
    mes_diario: int | None = None          # padrão: último mês com dados do ano de referência
    percentil_inferior: int = 10
    percentil_superior: int = 90
    anos_intensidade: int = 10             # janela para o ano mais e menos intenso
    series_comparativo: tuple[str, ...] = ("Máximo", "Média", "Mínimo")   # linhas dos comparativos
    mostrar_anos: bool = True              # uma linha cinza por ano no acumulado


@dataclass
class EstatisticasMunicipio:
    municipio: str                         # nome do território (município, UC ou TI) — usado nos títulos
    ano_inicio: int
    ano_fim: int
    parametros: ParametrosEstatisticas     # já com os padrões resolvidos
    inicio_dados: date                     # cobertura da base dentro do período
    fim_dados: date
    focos: pd.DataFrame                    # lon, lat, data (datetime), ano
    anos_estatistica: list[int]            # anos usados no mínimo/média/máximo
    mensal: pd.DataFrame                   # índice ano; colunas 1..12 e "Total"
    resumo_mensal: pd.DataFrame            # índice Mínimo/Média/Máximo; mesmas colunas
    diario: pd.DataFrame                   # índice "MM/AAAA"; colunas 1..31 e "Total"
    comparativos: dict[str, pd.DataFrame]  # unidade → periodo, rotulo, referencia, minimo, media, maximo
    acumulado: pd.DataFrame                # índice ano; colunas 1..12 (acumulado no ano)
    faixa_acumulado: pd.DataFrame          # mes, inferior, superior, media
    anos_intensidade: list[int] = field(default_factory=list)
    ano_mais_intenso: int | None = None
    ano_menos_intenso: int | None = None

    @property
    def ano_referencia(self) -> int:
        return self.parametros.ano_referencia

    @property
    def ano_anterior(self) -> int | None:
        anterior = self.ano_referencia - 1
        return anterior if anterior in self.mensal.index else None

    @property
    def anos_parciais(self) -> list[int]:
        """Anos que a base não cobre do começo ao fim."""
        return [a for a in self.mensal.index if not _ano_completo(a, self.inicio_dados, self.fim_dados)]


# ------------------------------------------------------------------ Apoio

def cobertura_base(df: pd.DataFrame) -> tuple[date, date]:
    """Primeiro e último dia com focos na base inteira."""
    datas = df["data"].dropna().astype(str)
    return date.fromisoformat(datas.min()), date.fromisoformat(datas.max())


def _ano_completo(ano: int, inicio: date, fim: date) -> bool:
    return inicio <= date(ano, 1, 1) and date(ano, 12, 31) <= fim


def _blocos(ano: int, unidade: str) -> list[tuple[int, date, date]]:
    """(número, primeiro dia, último dia) de cada mês/semana (do ano ou do semestre) no ano."""
    _, dias = UNIDADES[unidade]
    if dias is None:
        return [(m, date(ano, m, 1), date(ano, m, calendar.monthrange(ano, m)[1])) for m in range(1, 13)]
    inicio, fim_periodo = date(ano, 1, 1), date(ano, 12, 31)
    if unidade in SEMESTRES:
        m0, m1 = SEMESTRES[unidade]
        inicio, fim_periodo = date(ano, m0, 1), date(ano, m1, calendar.monthrange(ano, m1)[1])
    blocos, n = [], 1
    while inicio <= fim_periodo:
        blocos.append((n, inicio, min(inicio + timedelta(days=dias - 1), fim_periodo)))
        inicio, n = inicio + timedelta(days=dias), n + 1
    return blocos


def numero_do_bloco(datas: pd.Series, unidade: str) -> pd.Series:
    """Número do bloco de cada data; vazio para datas fora do semestre."""
    _, dias = UNIDADES[unidade]
    if dias is None:
        return datas.dt.month
    if unidade in SEMESTRES:
        m0, m1 = SEMESTRES[unidade]
        inicio = pd.to_datetime(pd.DataFrame({"year": datas.dt.year, "month": m0, "day": 1}))
        semana = ((datas - inicio).dt.days // dias + 1).astype("float")
        return semana.where(datas.dt.month.between(m0, m1))
    return (datas.dt.dayofyear - 1) // dias + 1


def rotulos_dos_blocos(unidade: str) -> list[str]:
    _, dias = UNIDADES[unidade]
    if dias is None:
        return MESES_CURTOS
    if unidade in SEMESTRES:
        return [str(n) for n in range(1, SEMANAS_SEMESTRE[unidade] + 1)]
    return [str(n) for n in range(1, 54)]


def matriz_periodos(focos: pd.DataFrame, anos: list[int], unidade: str, inicio: date, fim: date) -> pd.DataFrame:
    """Focos por ano × bloco (mês, semana ou quinzena); ``NaN`` nos blocos fora da cobertura."""
    n_blocos = len(rotulos_dos_blocos(unidade))
    if focos.empty:
        contagem = pd.DataFrame()
    else:
        com_bloco = focos.assign(bloco=numero_do_bloco(focos["data"], unidade)).dropna(subset=["bloco"])
        contagem = (com_bloco.assign(bloco=com_bloco["bloco"].astype(int))
                    .groupby(["ano", "bloco"]).size().unstack(fill_value=0))
    matriz = contagem.reindex(index=anos, columns=range(1, n_blocos + 1), fill_value=0).astype(float)
    for ano in anos:
        cobertos = {n for n, i, f in _blocos(ano, unidade) if i <= fim and f >= inicio}
        for bloco in matriz.columns:
            if bloco not in cobertos:
                matriz.loc[ano, bloco] = np.nan
    matriz.index.name, matriz.columns.name = "ano", unidade
    return matriz


def resumo(matriz: pd.DataFrame, anos: list[int]) -> pd.DataFrame:
    """Mínimo, média e máximo de cada coluna, só com os anos dados (ignora vazios)."""
    base = matriz.loc[[a for a in anos if a in matriz.index]]
    return pd.DataFrame([base.min(), base.mean(), base.max()], index=LINHAS_RESUMO)


def resolver_parametros(p: ParametrosEstatisticas, ano_inicio: int, ano_fim: int, fim_dados: date
                        ) -> ParametrosEstatisticas:
    ano_ref = p.ano_referencia if p.ano_referencia and ano_inicio <= p.ano_referencia <= ano_fim else ano_fim
    mes = p.mes_diario
    if not mes:
        mes = fim_dados.month if ano_ref == fim_dados.year else 12
    inferior, superior = sorted((int(p.percentil_inferior), int(p.percentil_superior)))
    return replace(p, ano_referencia=ano_ref, mes_diario=mes, percentil_inferior=inferior,
                   percentil_superior=superior,
                   anos_intensidade=max(1, min(int(p.anos_intensidade), ano_fim - ano_inicio)))


# --------------------------------------------------------------- Tabelas

def tabela_diaria(focos: pd.DataFrame, anos: list[int], mes: int, inicio: date, fim: date) -> pd.DataFrame:
    """Focos por dia do mês ``mes`` em cada ano dado; "-" (NaN) em dias inexistentes ou sem cobertura."""
    linhas = {}
    for ano in anos:
        no_mes = focos[(focos["data"].dt.year == ano) & (focos["data"].dt.month == mes)]
        por_dia = no_mes["data"].dt.day.value_counts()
        dias_no_mes = calendar.monthrange(ano, mes)[1]
        valores = {}
        for dia in range(1, 32):
            coberto = dia <= dias_no_mes and inicio <= date(ano, mes, dia) <= fim
            valores[dia] = float(por_dia.get(dia, 0)) if coberto else np.nan
        valores["Total"] = np.nansum(list(valores.values())) if any(pd.notna(v) for v in valores.values()) \
            else np.nan
        linhas[f"{mes:02d}/{ano}"] = valores
    return pd.DataFrame.from_dict(linhas, orient="index")


def comparativo(matriz: pd.DataFrame, ano_ref: int, anos_estatistica: list[int], unidade: str) -> pd.DataFrame:
    estat = resumo(matriz, anos_estatistica)
    return pd.DataFrame({
        "periodo": matriz.columns,
        "rotulo": rotulos_dos_blocos(unidade)[:len(matriz.columns)],
        "referencia": matriz.loc[ano_ref].to_numpy() if ano_ref in matriz.index else np.nan,
        "minimo": estat.loc["Mínimo"].to_numpy(),
        "media": estat.loc["Média"].to_numpy(),
        "maximo": estat.loc["Máximo"].to_numpy(),
    })


def acumulado_mensal(mensal: pd.DataFrame, inicio: date, fim: date) -> pd.DataFrame:
    """Total acumulado no ano até cada mês; vazio nos meses depois do fim da cobertura."""
    meses = mensal[list(range(1, 13))]
    acumulado = meses.fillna(0).cumsum(axis=1)
    for ano in acumulado.index:
        for m in range(1, 13):
            if date(ano, m, 1) > fim:
                acumulado.loc[ano, m] = np.nan
    return acumulado


# ------------------------------------------------------------- Principal

def estatisticas_territorio(focos: pd.DataFrame, nome: str, ano_inicio: int, ano_fim: int,
                            cobertura: tuple[date, date], parametros: ParametrosEstatisticas | None = None
                            ) -> EstatisticasMunicipio:
    """Tabelas e séries das estatísticas de um território.

    ``focos`` = focos do território (``DiagnosticoMunicipio.focos`` ou ``DiagnosticoArea.focos``);
    ``cobertura`` = primeiro e último dia da base inteira (``cobertura_base``).
    """
    inicio_base, fim_base = cobertura
    inicio = max(inicio_base, date(ano_inicio, 1, 1))
    fim = min(fim_base, date(ano_fim, 12, 31))
    p = resolver_parametros(parametros or ParametrosEstatisticas(), ano_inicio, ano_fim, fim)
    focos = focos[focos["ano"].between(ano_inicio, ano_fim)]
    focos = focos[["lon", "lat", "data", "ano"]].assign(data=pd.to_datetime(focos["data"]))
    municipio = nome

    anos = list(range(ano_inicio, ano_fim + 1))
    anos_estat = [a for a in anos if a != p.ano_referencia]

    mensal = matriz_periodos(focos, anos, "mensal", inicio, fim)
    mensal["Total"] = mensal.sum(axis=1, min_count=1)
    resumo_mensal = resumo(mensal, anos_estat)

    anos_diario = [a for a in (p.ano_referencia - 1, p.ano_referencia) if a in anos]
    diario = tabela_diaria(focos, anos_diario, p.mes_diario, inicio, fim)

    comparativos = {"mensal": comparativo(mensal[list(range(1, 13))], p.ano_referencia, anos_estat, "mensal")}
    for unidade in ("semanal", "semestre1", "semestre2"):
        comparativos[unidade] = comparativo(matriz_periodos(focos, anos, unidade, inicio, fim),
                                            p.ano_referencia, anos_estat, unidade)

    acumulado = acumulado_mensal(mensal, inicio, fim)
    base_faixa = acumulado.loc[anos_estat] if anos_estat else acumulado.iloc[0:0]
    faixa = pd.DataFrame({
        "mes": range(1, 13),
        "inferior": base_faixa.quantile(p.percentil_inferior / 100).to_numpy() if len(base_faixa) else np.nan,
        "superior": base_faixa.quantile(p.percentil_superior / 100).to_numpy() if len(base_faixa) else np.nan,
        "media": base_faixa.mean().to_numpy() if len(base_faixa) else np.nan,
    })

    # Ano mais/menos intenso: anos completos antes do ano de referência, nos últimos N
    completos = [a for a in anos_estat if a < p.ano_referencia and _ano_completo(a, inicio, fim)]
    janela = completos[-p.anos_intensidade:]
    totais = mensal.loc[janela, "Total"] if janela else pd.Series(dtype=float)

    return EstatisticasMunicipio(
        municipio=municipio, ano_inicio=ano_inicio, ano_fim=ano_fim, parametros=p,
        inicio_dados=inicio, fim_dados=fim, focos=focos,
        anos_estatistica=anos_estat, mensal=mensal, resumo_mensal=resumo_mensal, diario=diario,
        comparativos=comparativos, acumulado=acumulado, faixa_acumulado=faixa, anos_intensidade=janela,
        ano_mais_intenso=int(totais.idxmax()) if len(totais) else None,
        ano_menos_intenso=int(totais.idxmin()) if len(totais) else None,
    )


# ------------------------------------------------- Tabelas para exibir/exportar

def tabela_mensal_exibicao(est: EstatisticasMunicipio) -> pd.DataFrame:
    """Tabela "ano × mês" do INPE: anos, depois Mínimo, Média e Máximo (sem o ano de referência)."""
    corpo = pd.concat([est.mensal, est.resumo_mensal.round(0)])
    corpo.columns = MESES_TABELA + ["Total"]
    corpo.index = [str(i) for i in corpo.index]
    corpo.index.name = "Ano"
    return corpo


def tabela_diaria_exibicao(est: EstatisticasMunicipio) -> pd.DataFrame:
    tabela = est.diario.copy()
    tabela.columns = [str(c) for c in tabela.columns]
    tabela.index.name = "Mês/Ano"
    return tabela


def tabela_comparativo_exibicao(est: EstatisticasMunicipio, unidade: str) -> pd.DataFrame:
    rotulo, _ = UNIDADES[unidade]
    tabela = est.comparativos[unidade].copy()
    tabela["periodo"] = MESES_TABELA if unidade == "mensal" else tabela["rotulo"]
    tabela = tabela.drop(columns="rotulo")
    tabela["media"] = tabela["media"].round(1)
    return tabela.rename(columns={"periodo": rotulo, "referencia": str(est.ano_referencia), "minimo": "Mínimo",
                                  "media": "Média", "maximo": "Máximo"})


def tabela_acumulado_exibicao(est: EstatisticasMunicipio) -> pd.DataFrame:
    p = est.parametros
    tabela = est.acumulado.copy()
    tabela.columns = MESES_CURTOS
    faixa = est.faixa_acumulado.set_index("mes").T
    faixa.index = [f"p{p.percentil_inferior}", f"p{p.percentil_superior}", "Média"]
    faixa.columns = MESES_CURTOS
    tabela.index = [str(a) for a in tabela.index]
    tabela = pd.concat([tabela, faixa.round(0)])
    tabela.index.name = "Ano"
    return tabela


def extremos_por_coluna(tabela: pd.DataFrame, linhas: list[str], recorde: str | None = None
                        ) -> dict[str, tuple[set, set]]:
    """Coluna → (linhas com o mínimo, linhas com o máximo), considerando só ``linhas`` (destaque do INPE).

    Zero nunca é destacado: o mínimo é o menor valor diferente de 0, e a coluna só com zeros fica sem destaque.
    ``recorde`` = linha do ano de referência: quando o valor dela (mesmo de um mês em andamento) passa da
    máxima da série ou empata com ela, o vermelho vai para ela e sai do maior dos outros anos; ela nunca é o
    mínimo (um mês incompleto seria quase sempre o menor).
    """
    resultado = {}
    for coluna in tabela.columns:
        valores = tabela.loc[[linha for linha in linhas if linha in tabela.index], coluna].dropna()
        valores = valores[valores != 0]
        if valores.empty:
            atual = tabela.at[recorde, coluna] if recorde in tabela.index else None
            resultado[coluna] = (set(), {recorde} if atual is not None and atual == atual and atual > 0 else set())
            continue
        minimos, maximos = set(valores.index[valores == valores.min()]), set(valores.index[valores == valores.max()])
        atual = tabela.at[recorde, coluna] if recorde in tabela.index else None
        if atual is not None and atual == atual and atual > 0 and atual >= valores.max():
            maximos = {recorde} | (maximos if atual == valores.max() else set())
        resultado[coluna] = (minimos, maximos)
    return resultado


def notas(est: EstatisticasMunicipio) -> list[str]:
    p = est.parametros
    textos = [
        f"Focos dentro do limite do território (cruzamento ponto-no-polígono), de {est.inicio_dados:%d/%m/%Y} "
        f"a {est.fim_dados:%d/%m/%Y}.",
        f"Mínimo, média e máximo usam os anos do período da análise, sem o ano de referência ({p.ano_referencia}).",
        "Semanas são blocos de 7 dias a partir de 1º de janeiro; nos semestres (1º: janeiro a junho; 2º: julho a "
        "dezembro), a partir do 1º dia do semestre, com a última semana mais curta.",
    ]
    if est.anos_intensidade:
        textos.append(f"Ano mais e menos intenso: entre os {len(est.anos_intensidade)} anos completos anteriores "
                      f"ao ano de referência ({est.anos_intensidade[0]}–{est.anos_intensidade[-1]}), pelo total anual.")
    if est.anos_parciais:
        textos.append("Anos com dados parciais (a base não cobre o ano todo): "
                      + ", ".join(str(a) for a in est.anos_parciais) + ".")
    return textos
