# -*- coding: utf-8 -*-
"""Fundo de imagem de satélite para o mapa do cenário atual (docs/10 §6).

Baixa os "tiles" XYZ da fonte de ``core.config.URL_SATELITE`` (Sentinel-2 cloudless da EOX, licença
aberta CC BY-NC-SA 4.0, P22) e monta um mosaico em
Web Mercator (EPSG:3857). Precisa de internet; sem ela, o mapa sai sem fundo e avisa. Os tiles
ficam só na memória do programa.
"""

import io
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import numpy as np
from PIL import Image

from core.config import APP_NOME, APP_VERSAO, CREDITO_SATELITE, URL_SATELITE  # noqa: F401 (crédito usado nos mapas)
RAIO_TERRA = 6378137.0
TAMANHO_TILE = 256
MAX_TILES = 30            # até ~5 × 6 tiles (≈1300–1500 px, a largura do mapa) por mapa
DOWNLOADS_SIMULTANEOS = 8
TEMPO_REDE_S = 15


def lonlat_para_mercator(lon, lat):
    lon, lat = np.asarray(lon, dtype=float), np.clip(np.asarray(lat, dtype=float), -85.05, 85.05)
    return RAIO_TERRA * np.radians(lon), RAIO_TERRA * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def mercator_para_lon(x):
    return np.degrees(np.asarray(x) / RAIO_TERRA)


def mercator_para_lat(y):
    return np.degrees(2 * np.arctan(np.exp(np.asarray(y) / RAIO_TERRA)) - np.pi / 2)


def _tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


@lru_cache(maxsize=512)
def _baixar_tile(zoom: int, x: int, y: int) -> bytes:
    pedido = urllib.request.Request(URL_SATELITE.format(x=x, y=y, z=zoom),
                                    headers={"User-Agent": f"{APP_NOME}/{APP_VERSAO}"})
    with urllib.request.urlopen(pedido, timeout=TEMPO_REDE_S) as resposta:
        return resposta.read()


def mosaico(limites_lonlat: tuple[float, float, float, float]):
    """(imagem RGB, extensão [x0, x1, y0, y1] em metros EPSG:3857) cobrindo os limites; None sem internet."""
    min_x, min_y, max_x, max_y = limites_lonlat
    for zoom in range(17, 1, -1):                   # o maior zoom que cabe em MAX_TILES
        x0, y0 = _tile(min_x, max_y, zoom)          # canto noroeste
        x1, y1 = _tile(max_x, min_y, zoom)
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= MAX_TILES:
            break
    imagem = Image.new("RGB", ((x1 - x0 + 1) * TAMANHO_TILE, (y1 - y0 + 1) * TAMANHO_TILE))
    posicoes = [(tx, ty) for tx in range(x0, x1 + 1) for ty in range(y0, y1 + 1)]
    try:
        with ThreadPoolExecutor(DOWNLOADS_SIMULTANEOS) as executor:
            tiles = list(executor.map(lambda t: _baixar_tile(zoom, *t), posicoes))
        for (tx, ty), conteudo in zip(posicoes, tiles):
            tile = Image.open(io.BytesIO(conteudo)).convert("RGB")
            imagem.paste(tile, ((tx - x0) * TAMANHO_TILE, (ty - y0) * TAMANHO_TILE))
    except (OSError, ValueError):
        return None
    n = 2 ** zoom
    mundo = 2 * math.pi * RAIO_TERRA
    extensao = [x0 / n * mundo - mundo / 2, (x1 + 1) / n * mundo - mundo / 2,
                mundo / 2 - (y1 + 1) / n * mundo, mundo / 2 - y0 / n * mundo]
    return np.asarray(imagem), extensao
