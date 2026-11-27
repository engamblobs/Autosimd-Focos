# -*- coding: utf-8 -*-
"""Consultas JSON aos serviços públicos de dados ao vivo (Painel do Fogo, Open-Meteo).

Sem internet ou resposta inesperada = ``SemDadosAoVivo`` com mensagem clara; quem chama decide o aviso.
"""

import json
import urllib.parse
import urllib.request

from core.config import APP_NOME, APP_VERSAO

TEMPO_REDE_S = 40


class SemDadosAoVivo(Exception):
    pass


def obter_json(url: str, parametros: dict | None = None, timeout: int = TEMPO_REDE_S):
    """GET ``url?parametros`` e devolve o JSON. Parâmetros com valores já prontos (texto)."""
    endereco = url + ("?" + urllib.parse.urlencode(parametros, safe=",:()'") if parametros else "")
    pedido = urllib.request.Request(endereco, headers={"User-Agent": f"{APP_NOME}/{APP_VERSAO}"})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            corpo = resposta.read()
    except OSError as erro:
        raise SemDadosAoVivo(f"Não foi possível acessar {url.split('?')[0]}: {erro}") from erro
    try:
        return json.loads(corpo)
    except ValueError as erro:
        raise SemDadosAoVivo(f"Resposta inesperada de {url.split('?')[0]} (não é JSON).") from erro
