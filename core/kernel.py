# -*- coding: utf-8 -*-
"""Densidade de kernel dos focos (docs/07 §4).

Kernel gaussiano com desvio padrão de ``DESVIO_KERNEL_KM`` sobre um raster de ~1 km (maior em
territórios muito grandes, até ``MAX_CELULAS`` por lado), recortado pelo limite do território.
Resultado em focos/km²; a soma da densidade × área das células = nº de focos (menos o que o
kernel espalha para fora do limite). Só numpy (sem scipy, que não vai no pacote Windows).
"""

import math
from dataclasses import dataclass

import numpy as np
import shapely

from core.config import KERNEL_CELULA_KM, KERNEL_DESVIO_KM, KERNEL_MAX_CELULAS

DESVIO_KERNEL_KM = KERNEL_DESVIO_KM        # parâmetros em core/config.py (P21)
CELULA_KERNEL_KM = KERNEL_CELULA_KM
MAX_CELULAS = KERNEL_MAX_CELULAS
KM_POR_GRAU_LAT = 110.574
KM_POR_GRAU_LON_EQUADOR = 111.320


@dataclass
class Kernel:
    x: np.ndarray                 # bordas em longitude
    y: np.ndarray                 # bordas em latitude
    densidade: np.ndarray         # [y, x] em focos/km² (NaN fora do limite)
    celula_km: float
    desvio_km: float


def _gaussiana(sigma_celulas: float) -> np.ndarray:
    raio = max(1, int(math.ceil(4 * sigma_celulas)))
    x = np.arange(-raio, raio + 1)
    pesos = np.exp(-0.5 * (x / sigma_celulas) ** 2)
    return pesos / pesos.sum()


def _suavizar(matriz: np.ndarray, pesos: np.ndarray) -> np.ndarray:
    """Convolução separável (linhas e colunas) com bordas zeradas."""
    linhas = np.apply_along_axis(lambda v: np.convolve(v, pesos, mode="same"), 0, matriz)
    return np.apply_along_axis(lambda v: np.convolve(v, pesos, mode="same"), 1, linhas)


def densidade_kernel(lons, lats, limites, poligono=None, desvio_km: float = DESVIO_KERNEL_KM,
                     celula_km: float = CELULA_KERNEL_KM, max_celulas: int = MAX_CELULAS) -> Kernel:
    """``limites`` = (min_x, min_y, max_x, max_y) do território; a área é ampliada em 3 desvios."""
    min_x, min_y, max_x, max_y = limites
    lat0 = math.radians((min_y + max_y) / 2)
    kx, ky = KM_POR_GRAU_LON_EQUADOR * math.cos(lat0), KM_POR_GRAU_LAT
    margem = 3 * desvio_km
    largura, altura = (max_x - min_x) * kx + 2 * margem, (max_y - min_y) * ky + 2 * margem
    celula = max(celula_km, max(largura, altura) / max_celulas)
    nx, ny = int(math.ceil(largura / celula)), int(math.ceil(altura / celula))
    x = min_x - margem / kx + np.arange(nx + 1) * celula / kx
    y = min_y - margem / ky + np.arange(ny + 1) * celula / ky

    contagem, _, _ = np.histogram2d(np.asarray(lats, dtype=float), np.asarray(lons, dtype=float), bins=[y, x])
    densidade = _suavizar(contagem, _gaussiana(desvio_km / celula)) / celula ** 2
    if poligono is not None:
        cx, cy = np.meshgrid((x[:-1] + x[1:]) / 2, (y[:-1] + y[1:]) / 2)
        dentro = shapely.contains_xy(poligono, cx.ravel(), cy.ravel()).reshape(cx.shape)
        densidade = np.where(dentro, densidade, np.nan)
    return Kernel(x, y, densidade, celula, desvio_km)
