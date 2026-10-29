# -*- coding: utf-8 -*-
"""Anomalias de focos de calor (core/anomalias.py, docs/07 §12) com dados sintéticos de resultado conhecido."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.anomalias import (
    SINAL_ANOMALIA, benjamini_hochberg, calcular_anomalias, classe, freeman_tukey, inicio_do_periodo, p_valor_normal,
    p_valor_t, residuo_localizacao, resumo,
)
from core.grade import grade_do_territorio

LIMITES = (0.0, 0.0, 0.9, 0.9)          # 10 × 10 células de 10 km
GRADE = grade_do_territorio(LIMITES, 10)
ANOS = list(range(2006, 2020))
FIM = date(2020, 10, 28)
CELULAS = {"A": (0.05, 0.05), "B": (0.45, 0.45), "C": (0.85, 0.85)}


def focos_em(ano: int, quantos: dict) -> list[dict]:
    """``quantos`` = célula → nº de focos, todos em 15/10 do ano (dentro do mês do período)."""
    return [{"lon": CELULAS[c][0], "lat": CELULAS[c][1], "data": f"{ano}-10-15"} for c, n in quantos.items()
            for _ in range(n)]


def base(atual: dict) -> pd.DataFrame:
    linhas = []
    for i, ano in enumerate(ANOS):
        extra = i % 3                                               # variação natural entre os anos
        linhas += focos_em(ano, {"A": 10 + extra, "B": 4 + (2 - extra)})
    return pd.DataFrame(linhas + focos_em(2020, atual))


def celula(an, nome: str, campo: str):
    lon, lat = CELULAS[nome]
    i, j = np.searchsorted(GRADE.x, lon) - 1, np.searchsorted(GRADE.y, lat) - 1
    return getattr(an, campo)[i, j] if campo != "q" else {t: v[i, j] for t, v in an.q.items()}


def test_periodos_em_meses():
    assert inicio_do_periodo(date(2026, 10, 28), 1) == date(2026, 10, 1)        # mês: do dia 1º até o dia
    assert inicio_do_periodo(date(2026, 10, 28), 3) == date(2026, 8, 1)         # trimestre: ago–out
    assert inicio_do_periodo(date(2026, 2, 5), 6) == date(2025, 9, 1)           # atravessa o ano
    assert inicio_do_periodo(date(2026, 10, 28), 12) == date(2025, 11, 1)


def test_significancia():
    assert p_valor_normal(np.array([1.96, 2.576])) == pytest.approx([0.05, 0.01], abs=1e-4)
    # t de Student com 22 graus de liberdade: 2,074 → 5%; 2,819 → 1% (com o fator de predição √(1 + 1/n))
    fator = np.sqrt(1 + 1 / 23)
    assert p_valor_t(np.array([2.0739, 2.8188]) * fator, 23) == pytest.approx([0.05, 0.01], abs=1e-4)
    assert benjamini_hochberg(np.array([0.01, 0.04, 0.03, 0.2])) == pytest.approx([0.04, 0.0533, 0.0533, 0.2],
                                                                                  abs=1e-3)
    assert freeman_tukey(0) == pytest.approx(1.0)
    igual = np.array([[4.0, 2.0]])
    assert residuo_localizacao(igual, igual * 10) == pytest.approx(freeman_tukey(igual) - np.sqrt(4 * igual + 1))


def test_ano_comum_nao_tem_anomalia():
    an = calcular_anomalias(base({"A": 11, "B": 5}), LIMITES, FIM, "mês", ANOS, GRADE)
    for nome in ("A", "B"):
        assert abs(celula(an, nome, "quantidade")) < 1 and abs(celula(an, nome, "localizacao")) < 1
        assert min(celula(an, nome, "q").values()) > 0.05
    assert an.inicio == date(2020, 10, 1) and an.total_atual == 16


def test_mais_focos_e_anomalia_negativa_vermelha():
    an = calcular_anomalias(base({"A": 40, "B": 18}), LIMITES, FIM, "mês", ANOS, GRADE)   # ~×3, mesma proporção
    assert SINAL_ANOMALIA == -1
    assert celula(an, "A", "quantidade") <= -2 and celula(an, "B", "quantidade") <= -2    # negativa = mais focos
    assert abs(celula(an, "A", "localizacao")) < 1.5                                     # mesmo lugar de sempre
    assert celula(an, "A", "q")["quantidade"] < 0.05 and an.anomalia_total <= -2
    assert classe(-2.5) == "forte — mais focos" and classe(1.2) == "moderada — menos focos"
    assert classe(0.3) == "comum"


def test_focos_em_lugar_novo_e_anomalia_de_localizacao():
    an = calcular_anomalias(base({"A": 4, "B": 4, "C": 8}), LIMITES, FIM, "mês", ANOS, GRADE)  # outro lugar
    assert celula(an, "C", "localizacao") <= -2 and celula(an, "C", "combinada") <= -2
    assert celula(an, "A", "localizacao") >= 1                                            # faltou onde costuma
    r = resumo(an, "localizacao")
    assert r["celulas"] == 3 and r["fortes_mais"] >= 1 and r["sig_1"] <= r["sig_5"]


def test_mapa_e_secao_do_pdf():
    from shapely.geometry import box

    from core.mapas import mapa_anomalia
    from core.produto import fechar_figuras, figuras_anomalias
    from core.relatorio_pdf import anomalias_pdf, estilos_pdf

    an = calcular_anomalias(base({"A": 4, "B": 4, "C": 8}), LIMITES, FIM, "mês", ANOS, GRADE)
    figuras = figuras_anomalias(an, box(*LIMITES), "Teste")
    try:
        assert set(figuras) == {"anomalia_quantidade", "anomalia_localizacao", "anomalia_combinada"}
        assert "LOCALIZAÇÃO" in figuras["anomalia_localizacao"].axes[0].get_title()
        assert len(anomalias_pdf(figuras, estilos_pdf())) >= 6               # título, nota e os 3 mapas
        assert anomalias_pdf({}, estilos_pdf()) == []
        fechar_figuras({"m": mapa_anomalia(an, "quantidade", None, "Sem limite")})
    finally:
        fechar_figuras(figuras)
    assert figuras_anomalias(None, None, "x") == {}


def test_grupos_de_celulas_significativas():
    from core.anomalias import grupos_significativos

    perto = {(0.05, 0.05): 30, (0.15, 0.05): 30, (0.25, 0.05): 30, (0.85, 0.85): 30}   # 3 vizinhas + 1 isolada
    linhas = []
    for i, ano in enumerate(ANOS):
        linhas += [{"lon": x, "lat": y, "data": f"{ano}-10-15"} for (x, y) in perto for _ in range(1 + i % 2)]
    linhas += [{"lon": x, "lat": y, "data": "2020-10-15"} for (x, y), n in perto.items() for _ in range(n)]
    an = calcular_anomalias(pd.DataFrame(linhas), LIMITES, FIM, "mês", ANOS, GRADE)
    grupos = grupos_significativos(an, "quantidade")
    assert len(grupos) == 1 and grupos[0]["mais_focos"] and grupos[0]["celulas"] == 3   # a isolada fica de fora
    poligono = grupos[0]["poligono"]
    from shapely.geometry import Point
    assert all(poligono.contains(Point(x, y)) for (x, y) in list(perto)[:3])
    assert not poligono.contains(Point(0.85, 0.85))
