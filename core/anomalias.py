# -*- coding: utf-8 -*-
"""Anomalias de focos de calor em relação à recorrência comum (docs/07 §12, P32).

Mesma grade proporcional do mapa de recorrência (``grade.grade_do_territorio``). Período atual = os meses do
calendário que terminam no mês do último dia com dados, até esse dia (mês = do dia 1º até ele; bimestre,
trimestre, semestre, ano = 2, 3, 6, 12 meses). Referência = as **mesmas datas** em cada ano completo anterior
(``anos``). Por célula c: x_c = focos no período atual; h_{c,a} = focos nas mesmas datas do ano a.

Unidade comum. As células têm a mesma área e os períodos têm os mesmos dias em todos os anos, então a
contagem já é proporcional à densidade (focos/km² = contagem / L²). Para pôr quantidade e localização na
mesma escala, as contagens passam pela transformação de Freeman–Tukey T(n) = √n + √(n+1) (Freeman & Tukey,
1950), que estabiliza a variância de contagens (≈ 1 para Poisson, inclusive com muitos zeros): os três índices
ficam em **desvios padrão**.

1. Quantidade — anomalia padronizada da célula em relação à própria climatologia (Wilks, 2011):
   z_Q = (T(x_c) − média_a T(h_{c,a})) / max(dp_a T(h_{c,a}), 1).
2. Localização — desvio de Freeman–Tukey do esperado se o total atual se distribuísse como de costume
   (Bishop, Fienberg & Holland, 1975; casos esperados de Kulldorff et al., 2005): r_c = T(x_c) − √(4·E_c + 1),
   E_c = X·Σ_a h_{c,a} / Σ_c Σ_a h_{c,a}; padronizado pelos mesmos resíduos de cada ano de referência (cada ano
   contra a participação dos demais), porque os focos variam bem mais que um processo de Poisson:
   z_L = (r_c − média_a r_{c,a}) / max(dp_a r_{c,a}, 1). Independe do total.
3. Combinado — Stouffer (1949) com a correção para escores correlacionados de Strube (1985):
   z_C = (z_Q + z_L) / √(2 + 2ρ), ρ = correlação entre z_Q e z_L nas células com informação.

**Sinal (pedido do usuário, 29/10/2026): anomalia = −z.** Anomalia **negativa** (vermelha) = muito **mais**
focos que o comum; **positiva** (azul) = muito **menos**. É o contrário da convenção da climatologia (WMO:
positiva = acima do normal); para inverter, troque ``SINAL_ANOMALIA``.

Significância (P32). z_Q e z_L são padronizados com a média e o desvio padrão de n anos, então o valor-p vem
da distribuição t de Student com n − 1 graus de liberdade, com o fator de intervalo de predição √(1 + 1/n)
(um ano novo comparado com n anos); z_C, combinação de dois escores, usa a normal. Como um mapa testa
centenas de células, os valores-p são corrigidos pelo controle da taxa de falsas descobertas de Benjamini &
Hochberg (1995), como recomenda Wilks (2016) para mapas em grade. Células com q < 5% e q < 1% recebem pontos
(o "stippling" dos mapas climáticos). |anomalia| < 1 = comum; 1–2 moderada; 2–3 forte; ≥ 3 extrema.
"""

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from core.grade import Grade, contagem, grade_do_territorio

PERIODOS = {"mês": 1, "bimestre": 2, "trimestre": 3, "semestre": 6, "ano": 12}
PERIODO_RELATORIO = "mês"           # período dos mapas do PDF
TAMANHO_GRADE_ANOMALIA_ESTADO = 10   # km: no cenário do estado/região a grade é fixa (pedido de 29/10/2026)
SINAL_ANOMALIA = -1                  # −1: negativa = mais focos (vermelha); +1: convenção da climatologia
NIVEIS_SIGNIFICANCIA = (0.05, 0.01)
TIPOS = {"quantidade": "anomalia de quantidade", "localizacao": "anomalia de localização",
         "combinada": "anomalia combinada"}


def freeman_tukey(n):
    n = np.asarray(n, dtype=float)
    return np.sqrt(n) + np.sqrt(n + 1)


def inicio_do_periodo(fim: date, meses: int) -> date:
    """1º dia do mês ``meses − 1`` meses antes do mês de ``fim``."""
    total = fim.year * 12 + fim.month - 1 - (meses - 1)
    return date(total // 12, total % 12 + 1, 1)


def _anos_antes(d: date, k: int) -> date:
    try:
        return d.replace(year=d.year - k)
    except ValueError:                    # 29/02
        return date(d.year - k, 2, 28)


def residuo_localizacao(observado: np.ndarray, referencia: np.ndarray) -> np.ndarray:
    """Desvio de Freeman–Tukey de ``observado`` em relação ao total observado distribuído como a
    ``referencia``: T(x) − √(4E + 1), E = Σx · ref / Σref."""
    total_ref = referencia.sum()
    esperado = observado.sum() * referencia / total_ref if total_ref else np.zeros_like(referencia, dtype=float)
    return freeman_tukey(observado) - np.sqrt(4 * esperado + 1)


# ----------------------------------------------------------- Significância (sem scipy)

def _cdf_t(gl: int):
    """Função de distribuição da t de Student com ``gl`` graus de liberdade (tabela integrada numericamente)."""
    x = np.linspace(0, 60, 120_001)
    log_c = math.lgamma((gl + 1) / 2) - math.lgamma(gl / 2) - 0.5 * math.log(gl * math.pi)
    pdf = np.exp(log_c - (gl + 1) / 2 * np.log1p(x ** 2 / gl))
    cdf = 0.5 + np.concatenate([[0], np.cumsum((pdf[1:] + pdf[:-1]) / 2 * np.diff(x))])
    return lambda v: np.interp(np.abs(v), x, np.minimum(cdf, 1.0))


def p_valor_t(z: np.ndarray, n_anos: int) -> np.ndarray:
    """Bicaudal: novo ano × média de ``n_anos`` anos (intervalo de predição, t com n − 1 graus de liberdade)."""
    if n_anos < 3:
        return np.ones_like(z, dtype=float)
    t = np.asarray(z, dtype=float) / math.sqrt(1 + 1 / n_anos)
    return 2 * (1 - _cdf_t(n_anos - 1)(t))


def p_valor_normal(z: np.ndarray) -> np.ndarray:
    z = np.abs(np.asarray(z, dtype=float))
    return np.vectorize(math.erfc)(z / math.sqrt(2)) if z.size else z


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """Valores-q (taxa de falsas descobertas) de Benjamini & Hochberg (1995)."""
    p = np.asarray(p, dtype=float)
    if not p.size:
        return p
    ordem = np.argsort(p)
    m = len(p)
    q = p[ordem] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    saida = np.empty(m)
    saida[ordem] = np.minimum(q, 1)
    return saida


# ----------------------------------------------------------------- Cálculo

@dataclass
class Anomalias:
    grade: Grade
    periodo: str                          # "mês", "bimestre"...
    inicio: date
    fim: date
    anos: list[int]
    atual: np.ndarray                     # [x, y] focos no período atual
    media: np.ndarray                     # [x, y] média histórica das mesmas datas
    quantidade: np.ndarray                # anomalias (já com o sinal SINAL_ANOMALIA)
    localizacao: np.ndarray
    combinada: np.ndarray
    q: dict                               # tipo → [x, y] valor-q (Benjamini–Hochberg; 1 nas células sem informação)
    total_atual: int
    total_medio: float
    anomalia_total: float                 # do território inteiro (com o sinal SINAL_ANOMALIA)
    rho: float

    @property
    def informativas(self) -> np.ndarray:
        """Células com algum foco no período atual ou na média histórica."""
        return (self.atual > 0) | (self.media > 0)

    def significativas(self, tipo: str, nivel: float) -> np.ndarray:
        return self.informativas & (self.q[tipo] < nivel)


def calcular_anomalias(focos: pd.DataFrame, limites, fim: date, periodo: str, anos: list[int],
                       grade: Grade | None = None) -> Anomalias:
    """``focos`` = focos do território (lon, lat, data ISO) que cubram ``anos`` e o ano de ``fim``."""
    grade = grade or grade_do_territorio(limites)
    inicio = inicio_do_periodo(fim, PERIODOS[periodo])

    def no_periodo(a: date, b: date) -> np.ndarray:
        selecao = focos[(focos["data"] >= a.isoformat()) & (focos["data"] <= b.isoformat())]
        return contagem(grade, selecao["lon"], selecao["lat"])

    atual = no_periodo(inicio, fim)
    historico = np.stack([no_periodo(_anos_antes(inicio, fim.year - a), _anos_antes(fim, fim.year - a))
                          for a in anos]) if anos else np.zeros((0, *atual.shape))
    n = len(anos)

    def padronizar(valor, referencia):
        dp = referencia.std(axis=0, ddof=1) if n > 1 else np.ones_like(valor)
        return (valor - referencia.mean(axis=0)) / np.maximum(dp, 1)

    t_hist = freeman_tukey(historico)
    z_q = padronizar(freeman_tukey(atual), t_hist) if n else np.zeros_like(atual)
    soma_hist = historico.sum(axis=0) if n else np.zeros_like(atual)
    r_hist = np.stack([residuo_localizacao(h, soma_hist - h) for h in historico]) if n else np.zeros((0,) + atual.shape)
    z_l = padronizar(residuo_localizacao(atual, soma_hist), r_hist) if n else np.zeros_like(atual)

    informativas = (atual > 0) | (soma_hist > 0)
    rho = 0.0
    if informativas.sum() > 2 and np.std(z_q[informativas]) > 0 and np.std(z_l[informativas]) > 0:
        rho = float(np.clip(np.corrcoef(z_q[informativas], z_l[informativas])[0, 1], 0, 1))
    z_c = (z_q + z_l) / np.sqrt(2 + 2 * rho)

    q = {}
    for tipo, z, teste in (("quantidade", z_q, lambda v: p_valor_t(v, n)),
                           ("localizacao", z_l, lambda v: p_valor_t(v, n)), ("combinada", z_c, p_valor_normal)):
        valores = np.ones_like(z, dtype=float)
        if informativas.any():
            valores[informativas] = benjamini_hochberg(teste(z[informativas]))
        q[tipo] = valores

    totais = historico.sum(axis=(1, 2)) if n else np.zeros(0)
    t_tot = freeman_tukey(totais)
    z_total = (float((freeman_tukey(atual.sum()) - t_tot.mean()) / max(t_tot.std(ddof=1), 1)) if n > 1 else 0.0)
    return Anomalias(grade, periodo, inicio, fim, list(anos), atual, historico.mean(axis=0) if n else atual * 0,
                     SINAL_ANOMALIA * z_q, SINAL_ANOMALIA * z_l, SINAL_ANOMALIA * z_c, q, int(atual.sum()),
                     float(totais.mean()) if n else 0.0, SINAL_ANOMALIA * z_total, rho)


def classe(anomalia: float) -> str:
    """Classe da anomalia (com o sinal do programa: negativa = mais focos)."""
    a = abs(anomalia)
    if a < 1:
        return "comum"
    nivel = "moderada" if a < 2 else "forte" if a < 3 else "extrema"
    mais = (anomalia < 0) == (SINAL_ANOMALIA < 0)
    return f"{nivel} — {'mais' if mais else 'menos'} focos"


def resumo(an: Anomalias, tipo: str) -> dict:
    """Contagens para o texto do relatório."""
    valores = getattr(an, tipo)[an.informativas]
    mais = valores * SINAL_ANOMALIA > 0
    return {"celulas": int(an.informativas.sum()),
            "fortes_mais": int(((np.abs(valores) >= 2) & mais).sum()),
            "fortes_menos": int(((np.abs(valores) >= 2) & ~mais).sum()),
            "sig_5": int(an.significativas(tipo, 0.05).sum()), "sig_1": int(an.significativas(tipo, 0.01).sum())}


TEXTO_METODOLOGIA = (
    "<b>Como ler.</b> Cada célula da grade compara os focos do período com as mesmas datas dos anos anteriores. "
    "Anomalia <b>negativa (vermelho) = mais focos</b> que o comum; <b>positiva (azul) = menos focos</b>; em "
    "desvios padrão (|a| &lt; 1 comum; 1–2 moderada; 2–3 forte; ≥ 3 extrema). Pontos = células com anomalia "
    "estatisticamente significativa (ponto pequeno: 5%; grande: 1%). "
    "<b>Quantidade:</b> a célula tem mais ou menos focos do que costuma ter nestas datas (anomalia padronizada; "
    "Wilks, 2011). <b>Localização:</b> descontado o total do território, os focos caíram onde não costumam cair, "
    "ou faltaram onde costumam (desvio de Freeman–Tukey em relação ao esperado pela participação histórica de "
    "cada célula — Bishop, Fienberg &amp; Holland, 1975; Kulldorff et al., 2005 — padronizado pela variação dos "
    "anos de referência). <b>Combinada:</b> as duas juntas, pelo método de Stouffer com a correção de Strube (1985) "
    "para escores correlacionados. As contagens passam pela transformação de Freeman–Tukey (1950), que põe "
    "quantidade e localização na mesma unidade. <b>Significância:</b> t de Student para um ano novo comparado com "
    "os anos de referência (normal na combinada), com a correção de Benjamini &amp; Hochberg (1995) para os "
    "muitos testes do mapa, como recomenda Wilks (2016). Contorno vermelho (azul) = grupo de células significativas "
    "a 1% com mais (menos) focos, a até 20 km umas das outras. Em territórios com poucos focos no período quase "
    "nenhuma célula é significativa: a anomalia aparece, mas não se distingue da variação comum. "
    "<b>Sobre as cores:</b> a convenção da climatologia é anomalia positiva = acima do normal; aqui o sinal foi "
    "invertido (negativa = mais focos, em vermelho) por se tratar de focos de calor — mostrar o aumento de fogo em "
    "azul, cor associada a algo positivo, poderia levar o leitor a uma interpretação equivocada."
)


def texto_metodologia_markdown() -> str:
    """O mesmo texto, para a tela (Markdown)."""
    return (TEXTO_METODOLOGIA.replace("<b>", "**").replace("</b>", "**").replace("&lt;", "<").replace("&amp;", "&"))


# --------------------------------------------- Grupos de células significativas

DISTANCIA_GRUPO_KM = 20               # células significativas a até 20 km ficam no mesmo grupo
MINIMO_CELULAS_GRUPO = 2
NIVEL_GRUPO = 0.01


def grupos_significativos(an: Anomalias, tipo: str, nivel: float = NIVEL_GRUPO,
                          distancia_km: float = DISTANCIA_GRUPO_KM, minimo: int = MINIMO_CELULAS_GRUPO) -> list[dict]:
    """Grupos de células significativas (q < ``nivel``) do mesmo sinal a até ``distancia_km`` umas das outras.

    Fechamento morfológico em km: expande ``distancia_km``/2 (células separadas por até ``distancia_km`` se
    juntam) e encolhe metade disso, deixando ~``distancia_km``/4 de margem com cantos arredondados — o contorno
    envolve o grupo sem cobrir as células da borda. Devolve
    ``{"mais_focos": bool, "celulas": n, "poligono": geometria em graus}``.
    """
    import shapely
    from shapely import affinity
    from shapely.geometry import box

    from core.kernel import KM_POR_GRAU_LAT, KM_POR_GRAU_LON_EQUADOR

    g = an.grade
    kx = KM_POR_GRAU_LON_EQUADOR * math.cos(math.radians(g.latitude_ref))
    ky = KM_POR_GRAU_LAT
    raio = distancia_km / 2
    valores = getattr(an, tipo)
    significativas = an.significativas(tipo, nivel)
    grupos = []
    for mais in (True, False):
        sinal = (valores * SINAL_ANOMALIA > 0) if mais else (valores * SINAL_ANOMALIA < 0)
        indices = list(zip(*np.nonzero(significativas & sinal)))
        if len(indices) < minimo:
            continue
        caixas = [box(g.x[i] * kx, g.y[j] * ky, g.x[i + 1] * kx, g.y[j + 1] * ky) for i, j in indices]
        unido = shapely.union_all([c.buffer(raio) for c in caixas])
        centros = shapely.points([((g.x[i] + g.x[i + 1]) / 2 * kx, (g.y[j] + g.y[j + 1]) / 2 * ky) for i, j in indices])
        for parte in getattr(unido, "geoms", [unido]):
            n = int(shapely.contains(parte, centros).sum())
            if n < minimo:
                continue
            contorno = parte.buffer(-raio / 2)
            if contorno.is_empty:
                continue
            grupos.append({"mais_focos": mais, "celulas": n,
                           "poligono": affinity.scale(contorno, 1 / kx, 1 / ky, origin=(0, 0))})
    return grupos
