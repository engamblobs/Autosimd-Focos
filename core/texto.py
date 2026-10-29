# -*- coding: utf-8 -*-
"""Normalização de nomes e formatação de números no padrão brasileiro."""

import re
import unicodedata


def remover_acentos(texto) -> str:
    if not texto:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")


def chave_nome(texto) -> str:
    """Chave de comparação de nomes: maiúsculas, sem acento e sem espaços nas pontas."""
    return remover_acentos(str(texto or "").strip().upper())


def nome_arquivo(valor) -> str:
    """Trecho seguro para nome de arquivo: ASCII, sem espaços nem pontuação."""
    ascii_ = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii")
    ascii_ = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_).strip("_")
    return ascii_ or "SELECIONADO"


def fmt_numero(valor, casas: int = 0) -> str:
    """1234.5 → "1.234,5"."""
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_inteiro(valor) -> str:
    return fmt_numero(int(valor))


def fmt_percentual(valor, casas: int = 1, sinal: bool = False) -> str:
    if valor is None:
        return "—"
    return (f"{valor:+.{casas}f}%" if sinal else f"{valor:.{casas}f}%").replace(".", ",")


def fmt_posicao(posicao: int, total: int) -> str:
    """Posição no ranking; 0 = território sem focos no recorte."""
    return f"{posicao}º de {total}" if posicao else "Sem focos"


def fmt_densidade(densidade) -> str:
    return "—" if densidade is None else fmt_numero(densidade, 3)


def fmt_milhar_eixo(x, _pos=None) -> str:
    """Rótulo de eixo: 2500 → "2,5 mil"."""
    if x == 0:
        return "0"
    if x >= 1000:
        mil = x / 1000
        return f"{int(mil)} mil" if float(mil).is_integer() else f"{mil:.1f} mil".replace(".", ",")
    return f"{int(x)}"


def neutralizar_formulas(livro) -> None:
    """Grava como texto as células que o openpyxl tomaria por fórmula (texto dos dados que começa com "=")."""
    for aba in livro.worksheets:
        for linha in aba.iter_rows():
            for celula in linha:
                if celula.data_type == "f":
                    celula.data_type = "s"
