# -*- coding: utf-8 -*-
"""Eventos de fogo do Painel do Fogo (CENSIPAM), pelo serviço WFS público (sem chave).

Metodologia do Painel do Fogo (FAQ da plataforma; Faria et al., 2022):

- cada foco VIIRS (S-NPP, NOAA-20, NOAA-21) ganha um buffer de 400 m; quando **3 ou mais** buffers se
  cruzam e a área é **≥ 1 km²**, nasce um **evento de fogo** (polígono);
- focos MODIS só aumentam eventos que já existem; cada nova passagem de satélite que toca o evento soma área;
- **status**: ativo (1) = detecção nas últimas 48 h; em observação (2) = última detecção há 2–4 dias; depois
  disso o evento é extinto e sai do serviço;
- por passagem (camada de indicadores): área acumulada, incremento de área, horas desde o início,
  **velocidade de expansão (ha/h)**, FRP médio e o **indicador de severidade para acionamento** (MACBETH:
  área, duração, incremento e FRP).

A área do buffer superestima a área queimada de eventos pequenos: serve para comparar eventos, não para
medir a queimada.

O filtro por UF do serviço não funciona (os campos de município/UF vêm como listas Java); por isso a busca é
pelo retângulo do território e o recorte é feito aqui.
"""

from dataclasses import dataclass

import pandas as pd
import shapely
from shapely.geometry import shape

from core.config import URL_PAINEL_DO_FOGO_WFS
from core.rede import SemDadosAoVivo, obter_json

CAMADA_EVENTOS = "painel_do_fogo:mv_evento_filtro"
CAMADA_INDICADORES = "painel_do_fogo:mv_indicadores_queimadas"
CAMADA_FRENTES = "painel_do_fogo:mv_deteccoes_classificadas"     # "Frente de Fogo (24h)"
STATUS = {1: "Ativo", 2: "Em observação"}
CAMPOS_INDICADORES = ["id_evento", "dt_passagem", "area_acumulada_ha", "delta_area_ha", "ve_expansao_ha_hora",
                      "frp_med", "q_focos", "peso_global_passagem", "tempo_acumulado_horas"]


@dataclass
class EventosDeFogo:
    eventos: pd.DataFrame          # um por evento (colunas em ``tabela_eventos``) + ``geometria`` (shapely)
    passagens: pd.DataFrame        # indicadores por passagem de satélite (CAMPOS_INDICADORES)


def _wfs(parametros: dict, obter) -> dict:
    resposta = obter(URL_PAINEL_DO_FOGO_WFS, {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                                              "outputFormat": "application/json", "srsName": "EPSG:4326",
                                              **parametros})
    if not isinstance(resposta, dict) or "features" not in resposta:
        raise SemDadosAoVivo("Resposta inesperada do Painel do Fogo.")
    return resposta


def _bbox(limites) -> str:
    x0, y0, x1, y1 = limites
    return f"{x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f},EPSG:4326"


def buscar_frentes(limites, obter=obter_json) -> dict:
    """Frente de fogo das últimas 24 h de cada evento (camada "Frente de Fogo (24h)": os agrupamentos de focos
    recentes de cada evento): ``{id_evento: polígono}`` (união das partes). É onde o fogo está agora — origem
    do cone e ponto do vento (pedido de 25/11/2026)."""
    dados = _wfs({"typeNames": CAMADA_FRENTES, "bbox": _bbox(limites), "count": "10000"}, obter)
    partes: dict[int, list] = {}
    for f in dados["features"]:
        p, geom = f.get("properties") or {}, f.get("geometry")
        if geom and p.get("id_evento") is not None:
            partes.setdefault(int(p["id_evento"]), []).append(shapely.make_valid(shape(geom)))
    return {ev: shapely.union_all(g) for ev, g in partes.items()}


def buscar_eventos(limites, obter=obter_json, recorte=None, com_passagens: bool = True) -> EventosDeFogo:
    """Eventos ativos e em observação no retângulo ``limites`` (lon/lat); ``recorte`` = polígono opcional
    (fica só o evento que toca nele)."""
    dados = _wfs({"typeNames": CAMADA_EVENTOS, "bbox": _bbox(limites), "count": "5000"}, obter)
    linhas = []
    for f in dados["features"]:
        p, geom = f.get("properties") or {}, f.get("geometry")
        if not geom or p.get("id_status_evento") not in STATUS:
            continue
        geometria = shapely.make_valid(shape(geom))
        if recorte is not None and not geometria.intersects(recorte):
            continue
        linhas.append({"id_evento": int(p["id_evento"]), "status": STATUS[p["id_status_evento"]],
                       "inicio": pd.to_datetime(p.get("dt_minima"), utc=True),
                       "ultima_deteccao": pd.to_datetime(p.get("dt_maxima"), utc=True),
                       "deteccoes": int(p.get("qtd_deteccoes") or 0),
                       "area_km2": float(p.get("area_total_evento") or 0.0),
                       "geometria": geometria})
    eventos = pd.DataFrame(linhas, columns=["id_evento", "status", "inicio", "ultima_deteccao", "deteccoes",
                                            "area_km2", "geometria"])
    passagens = buscar_passagens(list(eventos["id_evento"]), obter) if com_passagens else None
    return EventosDeFogo(eventos, passagens)


def buscar_passagens(ids: list[int], obter=obter_json) -> pd.DataFrame:
    """Indicadores de cada passagem de satélite dos eventos ``ids`` (sem a geometria, que é pesada)."""
    if not ids:
        return pd.DataFrame(columns=CAMPOS_INDICADORES)
    partes = []
    for i in range(0, len(ids), 200):
        lote = ",".join(str(int(x)) for x in ids[i:i + 200])
        dados = _wfs({"typeNames": CAMADA_INDICADORES, "propertyName": ",".join(CAMPOS_INDICADORES),
                      "CQL_FILTER": f"id_evento IN ({lote})"}, obter)
        partes.append(pd.DataFrame([f.get("properties") or {} for f in dados["features"]],
                                   columns=CAMPOS_INDICADORES))
    df = pd.concat(partes, ignore_index=True)
    df["dt_passagem"] = pd.to_datetime(df["dt_passagem"], utc=True)
    return df.sort_values(["id_evento", "dt_passagem"]).reset_index(drop=True)


def resumo_por_evento(ev: EventosDeFogo, horas: int = 24) -> pd.DataFrame:
    """Última passagem de cada evento + velocidade de expansão média das passagens das últimas ``horas``
    (as passagens sem incremento entram como zero)."""
    p = ev.passagens
    if p.empty:
        return ev.eventos.assign(area_ha=ev.eventos["area_km2"] * 100, expansao_ha_h=0.0, frp_medio=float("nan"),
                                 severidade=float("nan"), passagens=0)
    ultima = p.groupby("id_evento").tail(1).set_index("id_evento")
    limite = p.groupby("id_evento")["dt_passagem"].transform("max") - pd.Timedelta(hours=horas)
    recentes = p[p["dt_passagem"] >= limite]
    expansao = recentes.groupby("id_evento").apply(_expansao_media, include_groups=False)
    resumo = ev.eventos.set_index("id_evento").assign(
        area_ha=ultima["area_acumulada_ha"], expansao_ha_h=expansao, frp_medio=ultima["frp_med"],
        severidade=ultima["peso_global_passagem"], passagens=p.groupby("id_evento").size())
    resumo["area_ha"] = resumo["area_ha"].fillna(resumo["area_km2"] * 100)
    return resumo.fillna({"expansao_ha_h": 0.0, "passagens": 0}).reset_index()


def _expansao_media(passagens: pd.DataFrame) -> float:
    """Área ganha ÷ horas decorridas entre a primeira e a última passagem da janela (ha/h)."""
    if len(passagens) < 2:
        return float(passagens["ve_expansao_ha_hora"].fillna(0).iloc[-1]) if len(passagens) else 0.0
    horas = (passagens["dt_passagem"].iloc[-1] - passagens["dt_passagem"].iloc[0]).total_seconds() / 3600
    ganho = float(passagens["delta_area_ha"].iloc[1:].fillna(0).clip(lower=0).sum())
    return ganho / horas if horas > 0 else 0.0
