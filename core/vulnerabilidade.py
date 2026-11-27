# -*- coding: utf-8 -*-
"""Localidades vulneráveis a fogo e fumaça — PROTÓTIPO (P42, docs/07 §13).

Para cada localidade do IBGE no município (``core.localidades``), combina:

a) **Proximidade** dos focos da base (últimas 24 h e últimos 7 dias da base, AQUA).
b) **Cone do evento de fogo** (Painel do Fogo, ``core.painel_do_fogo``), em dois alcances:
   - *fogo*: quanto a frente do evento avança em ``HORAS_FOGO`` horas, a favor do vento. A área do evento
     cresce na velocidade de expansão medida pelo Painel do Fogo (ha/h nas últimas 24 h); o formato é a
     elipse de Anderson (1983), cuja razão comprimento/largura cresce com o vento a meia-chama
     (vento a 10 m × ``FATOR_MEIA_CHAMA``). Avanço da cabeça = a(A + v·H)·(1+e) − a(A)·(1+e), com
     a = √(A·LB/π) e e = √(1 − 1/LB²). Sem vento (< 5 km/h) o avanço é igual em todas as direções.
   - *fumaça*: até onde o vento médio das próximas ``HORAS_FUMACA`` horas leva a fumaça (velocidade × horas,
     no máximo ``ALCANCE_FUMACA_MAX_KM``), num setor de ±``ABERTURA_FUMACA_GRAUS``° na direção para onde o
     vento sopra. Só eventos **ativos**.
c) **Fumaça prevista**: PM2,5 máximo das próximas 24 h (CAMS, pelo Open-Meteo): > 25 µg/m³ = 1 ponto,
   > 50 = 2, > 75 = 3 (faixas do IQAR da Resolução CONAMA 491/2018 para 24 h: moderada, ruim e muito ruim
   ou péssima — P45, 27/11/2026).
d) **Vulnerabilidade** da localidade (1 a 3): tipo (indígena/quilombola = 3; povoado, lugarejo, núcleo rural,
   agrovila e outras = 2; cidade, vila e núcleo urbano = 1), +1 se longe da sede (> ``DISTANCIA_ISOLADA_KM``)
   e +1 se teve foco a até ``RAIO_RECORRENCIA_KM`` km em pelo menos metade dos anos do período; máximo 3.
e) **Risco** = exposição (0–3, o maior de a, b e c) × vulnerabilidade (1–3) → classes.

Todos os parâmetros ficam no início do módulo para calibrar com o usuário (P43–P46 em docs/09).
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import shapely
import shapely.geometry
from shapely.geometry import Point, Polygon

# ------------------------------------------------------------------ parâmetros do protótipo
HORAS_FOGO = 24
HORAS_FUMACA = 6
ALCANCE_FUMACA_MAX_KM = 100.0
ABERTURA_FUMACA_GRAUS = 30.0
FATOR_MEIA_CHAMA = 0.4          # vento a meia-chama ≈ 40% do vento a 10 m (vegetação aberta/semiaberta)
VENTO_CALMO_KMH = 5.0
LB_MAXIMO = 8.0
DISTANCIA_ISOLADA_KM = 30.0
RAIO_RECORRENCIA_KM = 5.0
MARGEM_BUSCA_GRAUS = 0.5         # eventos e focos até ~55 km fora do município também contam
PASSO_PM25_GRAUS = 0.1           # localidades na mesma célula de 0,1° usam o mesmo PM2,5
CLASSES_SOBREPOSICAO = {1: "1 evento", 2: "2 eventos", 3: "3 ou mais eventos"}
# µg/m³ (máximo das próximas 24 h) → pontos de exposição: faixas do índice de qualidade do ar (IQAR) da
# Resolução CONAMA 491/2018 e do Guia Técnico do MMA (2019) para PM2,5 em 24 h — boa até 25, moderada até 50,
# ruim até 75, muito ruim até 125, péssima acima (P45, 27/11/2026: "siga da CONAMA"). A escala fica em 3 pontos
# (P46): muito ruim e péssima valem 3; a qualidade do ar aparece por extenso na tabela e no PDF.
FAIXAS_PM25 = [(75.0, 3), (50.0, 2), (25.0, 1)]
FAIXAS_IQAR_PM25 = [(125.0, "Péssima"), (75.0, "Muito ruim"), (50.0, "Ruim"), (25.0, "Moderada"), (0.0, "Boa")]
PM25_PADRAO_CONAMA = 25.0        # padrão final (PF) de 24 h da CONAMA 491/2018
CLASSES_RISCO = [(0, "Sem exposição"), (2, "Baixo"), (4, "Moderado"), (6, "Alto"), (9, "Muito alto")]
CORES_CLASSE = {"Sem exposição": "#9E9E9E", "Baixo": "#FDD835", "Moderado": "#FB8C00", "Alto": "#E53935",
                "Muito alto": "#7B1FA2"}
VULNERABILIDADE_TIPO = {"Localidade Indígena": 3, "Localidade Quilombola": 3, "Povoado": 2, "Lugarejo": 2,
                        "Núcleo Rural": 2, "Agrovila do PA": 2, "Outras Localidades": 2}


METODOLOGIA_VULNERABILIDADE = f"""
**Exposição (0 a 3 pontos — vale o maior):**

- **Proximidade dos focos da base** (AQUA): foco do último dia a até 5 km = 3; foco da última semana a até
  5 km, ou do último dia a até 10 km = 2; foco da última semana a até 20 km = 1.
- **Evento de fogo** (Painel do Fogo: ≥ 3 focos VIIRS com buffers de 400 m que se cruzam, área ≥ 1 km²; ativo =
  detecção nas últimas 48 h, em observação = 2 a 4 dias):
  - *avanço do fogo em {HORAS_FOGO} h* — a área cresce na velocidade de expansão medida pelo Painel do Fogo
    (média das últimas 24 h, ha/h) no formato da elipse de Anderson (1983): quanto mais vento, mais comprida.
    Vento a meia-chama = {FATOR_MEIA_CHAMA:.0%} do vento a 10 m; abaixo de {VENTO_CALMO_KMH:.0f} km/h o fogo
    avança igual para todos os lados. Localidade dentro = 3 pontos, com a hora prevista de chegada;
  - *fumaça nas próximas {HORAS_FUMACA} h* — setor de ±{ABERTURA_FUMACA_GRAUS:.0f}° na direção para onde o
    vento médio sopra, com alcance = velocidade × {HORAS_FUMACA} h (até {ALCANCE_FUMACA_MAX_KM:.0f} km). Só
    eventos ativos. Dentro = 2 pontos.
- **Fumaça prevista (PM2,5)** — máximo das próximas 24 h (CAMS): acima de 25 µg/m³ = 1, de 50 = 2, de 75 = 3
  (faixas do índice de qualidade do ar da Resolução CONAMA 491/2018 para 24 h: moderada, ruim, muito ruim ou
  péssima; o padrão final da CONAMA é {PM25_PADRAO_CONAMA:.0f} µg/m³).

**Vulnerabilidade (1 a 3):** aldeia indígena ou comunidade quilombola = 3; povoado, lugarejo, núcleo rural,
agrovila e outras localidades = 2; cidade, vila e núcleo urbano = 1; +1 se a mais de
{DISTANCIA_ISOLADA_KM:.0f} km da sede; +1 se teve foco a até {RAIO_RECORRENCIA_KM:.0f} km em pelo menos metade
dos anos do período. Máximo 3.

**Risco = exposição × vulnerabilidade:** 0 sem exposição · 1–2 baixo · 3–4 moderado · 6 alto · 9 muito alto.

Limites: o vento é o de 10 m dos modelos globais (resolução de ~10–25 km), sem relevo nem fogo modificando o
vento; a fumaça segue em linha reta (sem trajetória); a área dos eventos do Painel do Fogo superestima eventos
pequenos. Serve para **priorizar e comparar**, não para prever com precisão.
"""


@dataclass
class AnaliseVulnerabilidade:
    localidades: pd.DataFrame
    eventos: pd.DataFrame                    # resumo por evento + vento (direção para onde sopra, km/h)
    cones: list[dict] = field(default_factory=list)   # {"id_evento", "tipo": fogo|fumaca, "poligono" lon/lat}
    momento: datetime | None = None
    avisos: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ geometria local (km)

class Projecao:
    """Plano local em km (equiretangular no centro do município) — erro < 1% em algumas centenas de km."""

    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0 = lon0, lat0
        self.kx, self.ky = 111.32 * math.cos(math.radians(lat0)), 110.57

    def xy(self, lon, lat):
        return (np.asarray(lon, dtype=float) - self.lon0) * self.kx, (np.asarray(lat, dtype=float) - self.lat0) * self.ky

    def lonlat(self, x, y):
        return np.asarray(x) / self.kx + self.lon0, np.asarray(y) / self.ky + self.lat0

    def geom_km(self, geom):
        return shapely.transform(geom, lambda c: np.column_stack(self.xy(c[:, 0], c[:, 1])))

    def geom_lonlat(self, geom):
        return shapely.transform(geom, lambda c: np.column_stack(self.lonlat(c[:, 0], c[:, 1])))


def _azimute(dx, dy):
    """Azimute (graus a partir do norte, sentido horário)."""
    return (np.degrees(np.arctan2(dx, dy)) + 360) % 360


def _diferenca_angular(a, b):
    return np.abs((np.asarray(a) - np.asarray(b) + 180) % 360 - 180)


def razao_comprimento_largura(vento_10m_kmh: float) -> float:
    """Elipse de Anderson (1983); vento a meia-chama em mi/h."""
    u = vento_10m_kmh * FATOR_MEIA_CHAMA * 0.6214
    lb = 0.936 * math.exp(0.2566 * u) + 0.461 * math.exp(-0.1548 * u) - 0.397
    return float(min(max(lb, 1.0), LB_MAXIMO))


def avanco_da_frente_km(area_ha: float, expansao_ha_h: float, vento_kmh: float, horas: float) -> float:
    """Quanto a cabeça do fogo avança em ``horas`` (km), pela elipse de Anderson."""
    if expansao_ha_h <= 0 or area_ha <= 0:
        return 0.0
    a0, a1 = area_ha * 1e4, (area_ha + expansao_ha_h * horas) * 1e4          # m²
    if vento_kmh < VENTO_CALMO_KMH:
        return (math.sqrt(a1 / math.pi) - math.sqrt(a0 / math.pi)) / 1000
    lb = razao_comprimento_largura(vento_kmh)
    e = math.sqrt(1 - 1 / lb ** 2)
    return (math.sqrt(a1 * lb / math.pi) - math.sqrt(a0 * lb / math.pi)) * (1 + e) / 1000


def abertura_fogo_graus(vento_kmh: float) -> float:
    if vento_kmh < VENTO_CALMO_KMH:
        return 180.0
    return max(20.0, math.degrees(math.atan(1 / razao_comprimento_largura(vento_kmh))) + 10)


def setor(proj: Projecao, origem_km, azimute: float, alcance_km: float, abertura: float, n: int = 24) -> Polygon:
    """Setor circular (cone) em lon/lat, a partir da borda do evento (aproximada pelo centro + raio)."""
    x0, y0 = origem_km
    if abertura >= 180:
        poligono = Point(x0, y0).buffer(alcance_km, 32)
    else:
        angulos = np.radians(np.linspace(azimute - abertura, azimute + abertura, n))
        pontos = [(x0, y0)] + [(x0 + alcance_km * math.sin(a), y0 + alcance_km * math.cos(a)) for a in angulos]
        poligono = Polygon(pontos)
    return proj.geom_lonlat(poligono)


# ------------------------------------------------------------------ vento dos eventos

def vento_medio(vento: pd.DataFrame, inicio, horas: int) -> tuple[float, float]:
    """(velocidade km/h, azimute PARA ONDE sopra) da média vetorial das próximas ``horas`` horas."""
    janela = vento[(vento["hora"] >= inicio) & (vento["hora"] < inicio + pd.Timedelta(hours=horas))]
    if janela.empty:
        janela = vento.iloc[(vento["hora"] - inicio).abs().argsort()[:1]]
    para = np.radians((janela["direcao_graus"].to_numpy(dtype=float) + 180) % 360)
    v = janela["velocidade_kmh"].to_numpy(dtype=float)
    u, w = float(np.mean(v * np.sin(para))), float(np.mean(v * np.cos(para)))
    return float(np.mean(v)), float(_azimute(u, w))


# ------------------------------------------------------------------ análise

def _classe(risco: int) -> str:
    for limite, nome in CLASSES_RISCO:
        if risco <= limite:
            return nome
    return CLASSES_RISCO[-1][1]


def recorrencia_ao_redor(proj: Projecao, loc_x, loc_y, historico: pd.DataFrame, anos: list[int]) -> np.ndarray:
    """Fração dos ``anos`` com pelo menos um foco a até RAIO_RECORRENCIA_KM da localidade."""
    if historico.empty or not anos or len(loc_x) == 0:
        return np.zeros(len(loc_x))
    hx, hy = proj.xy(historico["lon"], historico["lat"])
    anos_foco = historico["ano"].to_numpy()
    resultado = np.zeros(len(loc_x))
    for k, (x, y) in enumerate(zip(loc_x, loc_y)):
        perto = (hx - x) ** 2 + (hy - y) ** 2 <= RAIO_RECORRENCIA_KM ** 2
        resultado[k] = len(set(anos_foco[perto]) & set(anos)) / len(anos)
    return resultado


def qualidade_do_ar(pm25) -> str:
    """Faixa do IQAR (CONAMA 491/2018) para o PM2,5 de 24 h; "" sem dado."""
    if pm25 is None or pd.isna(pm25):
        return ""
    return next(nome for limite, nome in FAIXAS_IQAR_PM25 if pm25 > limite or limite == 0.0)


def analisar(localidades: pd.DataFrame, municipio_geom, focos_recentes: pd.DataFrame, ultimo_dia,
             historico: pd.DataFrame, anos: list[int], eventos: pd.DataFrame | None = None,
             vento_eventos: pd.DataFrame | None = None, pm25: pd.DataFrame | None = None,
             agora=None) -> AnaliseVulnerabilidade:
    """``localidades`` (core.localidades) do município; ``focos_recentes`` = focos da base (lon, lat, data) dos
    últimos 7 dias até ``ultimo_dia`` perto do município; ``historico`` = focos (lon, lat, ano) do período;
    ``eventos`` = ``painel_do_fogo.resumo_por_evento``; ``vento_eventos`` = ``open_meteo.vento_horario`` com
    ``ponto`` = posição do evento em ``eventos``; ``pm25`` = ``open_meteo.pm25_horario`` com ``ponto`` =
    posição da localidade em ``localidades``. Sem eventos, vento ou PM2,5, esses itens ficam vazios."""
    agora = pd.Timestamp(agora or datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None)
    centro = municipio_geom.centroid
    proj = Projecao(centro.x, centro.y)
    loc = localidades.reset_index(drop=True).copy()
    loc["ponto"] = np.arange(len(loc))          # posição original (o ``ponto`` do PM2,5 hora a hora)
    lx, ly = proj.xy(loc["lon"], loc["lat"])
    avisos = []

    # d) vulnerabilidade
    sede = loc[loc["categoria"] == "Cidade"]
    if len(sede):
        sx, sy = proj.xy(sede["lon"].iloc[:1], sede["lat"].iloc[:1])
        loc["dist_sede_km"] = np.hypot(lx - sx[0], ly - sy[0]).round(1)
    else:
        loc["dist_sede_km"] = np.nan
        avisos.append("Sede municipal não encontrada entre as localidades: isolamento não calculado.")
    tipo = loc["categoria"].astype(str).map(VULNERABILIDADE_TIPO).fillna(1).astype(int)
    tipo = np.where(loc["indigena"] | loc["quilombola"], 3, tipo)
    loc["recorrencia"] = recorrencia_ao_redor(proj, lx, ly, historico, anos).round(2)
    loc["vulnerabilidade"] = np.minimum(3, tipo + (loc["dist_sede_km"] > DISTANCIA_ISOLADA_KM).astype(int)
                                        + (loc["recorrencia"] >= 0.5).astype(int))

    # a) proximidade dos focos da base
    dia = pd.Timestamp(ultimo_dia)
    datas = pd.to_datetime(focos_recentes["data"]).dt.normalize() if len(focos_recentes) else pd.Series([], dtype="datetime64[ns]")
    fx, fy = proj.xy(focos_recentes["lon"], focos_recentes["lat"]) if len(focos_recentes) else (np.array([]), np.array([]))
    ultimo = (datas == dia).to_numpy() if len(focos_recentes) else np.array([], dtype=bool)
    dist = np.hypot(lx[:, None] - fx[None, :], ly[:, None] - fy[None, :]) if len(fx) else np.full((len(loc), 0), np.inf)
    loc["foco_24h_km"] = dist[:, ultimo].min(axis=1, initial=np.inf).round(1) if ultimo.any() else np.inf
    loc["foco_7d_km"] = dist.min(axis=1, initial=np.inf).round(1)
    loc["focos_7d_10km"] = (dist <= 10).sum(axis=1)
    prox = np.select([loc["foco_24h_km"] <= 5, (loc["foco_7d_km"] <= 5) | (loc["foco_24h_km"] <= 10),
                      loc["foco_7d_km"] <= 20], [3, 2, 1], 0)

    # b) cones dos eventos de fogo
    loc["evento_fogo"], loc["eta_fogo_h"] = pd.NA, np.nan
    loc["evento_fumaca"], loc["eta_fumaca_h"] = pd.NA, np.nan
    cones, linhas_eventos = [], []
    eventos = eventos if eventos is not None else pd.DataFrame()
    for k, ev in enumerate(eventos.itertuples()):
        # origem do cone = frente de fogo das últimas 24 h (onde o fogo está agora); sem ela, o evento inteiro
        frente = getattr(ev, "frente", None)
        origem = frente if frente is not None and not frente.is_empty else ev.geometria
        geom_km = proj.geom_km(origem)
        c = geom_km.centroid
        vento = vento_eventos[vento_eventos["ponto"] == k] if vento_eventos is not None else pd.DataFrame()
        if len(vento):
            vel_fogo, az_fogo = vento_medio(vento, agora, HORAS_FOGO)
            vel_fumaca, az_fumaca = vento_medio(vento, agora, HORAS_FUMACA)
        else:
            vel_fogo = vel_fumaca = az_fogo = az_fumaca = np.nan
        ativo = ev.status == "Ativo"
        avanco = avanco_da_frente_km(ev.area_ha, ev.expansao_ha_h, 0 if np.isnan(vel_fogo) else vel_fogo,
                                     HORAS_FOGO) if ativo else 0.0
        abertura = abertura_fogo_graus(0 if np.isnan(vel_fogo) else vel_fogo)
        alcance_fumaca = min(vel_fumaca * HORAS_FUMACA, ALCANCE_FUMACA_MAX_KM) if ativo and not np.isnan(vel_fumaca) else 0.0
        raio = math.sqrt(max(geom_km.area, 0) / math.pi)
        dist_ev = shapely.distance(geom_km, shapely.points(lx, ly))
        azim = _azimute(lx - c.x, ly - c.y)
        if avanco > 0:
            dentro = (dist_ev <= avanco) & ((_diferenca_angular(azim, az_fogo) <= abertura) | np.isnan(az_fogo)
                                            if abertura < 180 else True)
            eta = dist_ev / (avanco / HORAS_FOGO)
            melhor = dentro & (np.isnan(loc["eta_fogo_h"].to_numpy(dtype=float)) | (eta < loc["eta_fogo_h"].to_numpy(dtype=float)))
            loc.loc[melhor, "evento_fogo"], loc.loc[melhor, "eta_fogo_h"] = ev.id_evento, eta[melhor].round(1)
            cones.append({"id_evento": ev.id_evento, "tipo": "fogo",
                          "poligono": setor(proj, (c.x, c.y), az_fogo if not np.isnan(az_fogo) else 0, raio + avanco,
                                            abertura)})
        if alcance_fumaca > 0:
            dentro = (dist_ev <= alcance_fumaca) & (_diferenca_angular(azim, az_fumaca) <= ABERTURA_FUMACA_GRAUS)
            eta = dist_ev / max(vel_fumaca, 1e-6)
            melhor = dentro & (np.isnan(loc["eta_fumaca_h"].to_numpy(dtype=float)) | (eta < loc["eta_fumaca_h"].to_numpy(dtype=float)))
            loc.loc[melhor, "evento_fumaca"], loc.loc[melhor, "eta_fumaca_h"] = ev.id_evento, eta[melhor].round(1)
            cones.append({"id_evento": ev.id_evento, "tipo": "fumaca",
                          "poligono": setor(proj, (c.x, c.y), az_fumaca, raio + alcance_fumaca, ABERTURA_FUMACA_GRAUS)})
        lon_c, lat_c = proj.lonlat(c.x, c.y)
        linhas_eventos.append({"id_evento": ev.id_evento, "status": ev.status, "inicio": ev.inicio,
                               "ultima_deteccao": ev.ultima_deteccao, "area_ha": round(float(ev.area_ha), 1),
                               "expansao_ha_h": round(float(ev.expansao_ha_h), 2),
                               "severidade": ev.severidade, "vento_kmh": round(vel_fumaca, 1) if not np.isnan(vel_fumaca) else np.nan,
                               "vento_para_graus": round(az_fumaca) if not np.isnan(az_fumaca) else np.nan,
                               "avanco_24h_km": round(avanco, 2), "alcance_fumaca_km": round(alcance_fumaca, 1),
                               "dist_sede_km": round(float(shapely.distance(geom_km, Point(*proj.xy(sede["lon"].iloc[0], sede["lat"].iloc[0])))), 1) if len(sede) else np.nan,
                               "lon": float(lon_c), "lat": float(lat_c), "geometria": ev.geometria,
                               "frente": frente if frente is not None and not frente.is_empty else None})
    cone = np.where(loc["evento_fogo"].notna(), 3, np.where(loc["evento_fumaca"].notna(), 2, 0))

    # c) PM2,5 previsto
    if pm25 is not None and len(pm25):
        janela = pm25[(pm25["hora"] >= agora) & (pm25["hora"] < agora + pd.Timedelta(hours=24))]
        maximo = janela.groupby("ponto")["pm25"].max()
        loc["pm25_max"] = maximo.reindex(range(len(loc))).to_numpy()
    else:
        loc["pm25_max"] = np.nan
    pm = np.select([loc["pm25_max"] > lim for lim, _ in FAIXAS_PM25], [p for _, p in FAIXAS_PM25], 0)

    loc["qualidade_ar"] = [qualidade_do_ar(v) for v in loc["pm25_max"]]
    loc["exposicao"] = np.maximum.reduce([prox, cone, pm]).astype(int)
    loc["motivo"] = [_motivo(r, a, c, m) for r, a, c, m in zip(loc.itertuples(), prox, cone, pm)]
    loc["perfil"] = [_perfil(t, d, r) for t, d, r in zip(tipo, loc["dist_sede_km"] > DISTANCIA_ISOLADA_KM,
                                                          loc["recorrencia"] >= 0.5)]
    loc["criterios"] = (tipo + (loc["dist_sede_km"] > DISTANCIA_ISOLADA_KM).astype(int)
                        + (loc["recorrencia"] >= 0.5).astype(int)).astype(int)
    loc["risco"] = (loc["exposicao"] * loc["vulnerabilidade"]).astype(int)
    loc["classe"] = loc["risco"].map(_classe)
    loc = loc.sort_values(["risco", "exposicao", "foco_24h_km"], ascending=[False, False, True]).reset_index(drop=True)
    colunas_eventos = ["id_evento", "status", "inicio", "ultima_deteccao", "area_ha", "expansao_ha_h", "severidade",
                       "vento_kmh", "vento_para_graus", "avanco_24h_km", "alcance_fumaca_km", "dist_sede_km",
                       "lon", "lat", "geometria", "frente"]
    return AnaliseVulnerabilidade(loc, pd.DataFrame(linhas_eventos, columns=colunas_eventos), cones,
                                  agora.to_pydatetime(), avisos)


TIPO_PERFIL = {3: "indígena/quilombola", 2: "comunidade rural", 1: "área urbana"}


def _perfil(tipo: int, isolada: bool, recorrente: bool) -> str:
    """Descrição da vulnerabilidade (P46: a escala de 1 a 3 não muda; o perfil diz o que pesou)."""
    partes = [TIPO_PERFIL.get(int(tipo), "área urbana")]
    if isolada:
        partes.append(f"isolada (> {DISTANCIA_ISOLADA_KM:.0f} km da sede)")
    if recorrente:
        partes.append("fogo recorrente ao redor")
    return " · ".join(partes)


def _motivo(loc, prox: int, cone: int, pm: int) -> str:
    """O que levou à exposição (os critérios que deram a nota máxima): para a lista de prioridade do PDF."""
    topo = max(prox, cone, pm)
    if topo == 0:
        return ""
    motivos = []
    if cone == topo and not pd.isna(loc.eta_fogo_h):
        motivos.append(f"fogo a caminho (~{loc.eta_fogo_h:.0f} h)")
    elif cone == topo and not pd.isna(loc.eta_fumaca_h):
        motivos.append(f"fumaça do evento a caminho (~{loc.eta_fumaca_h:.0f} h)")
    if prox == topo:
        motivos.append(f"foco a {loc.foco_24h_km:.0f} km nas últimas 24 h" if loc.foco_24h_km <= 10
                       else f"foco a {loc.foco_7d_km:.0f} km na última semana")
    if pm == topo:
        motivos.append(f"ar {loc.qualidade_ar.lower()} (PM2,5 {loc.pm25_max:.0f} µg/m³)")
    return "; ".join(motivos)


def _pm25_das_localidades(localidades: pd.DataFrame, obter) -> pd.DataFrame:
    """PM2,5 numa grade de ``PASSO_PM25_GRAUS`` (o CAMS tem ~0,4°): localidades vizinhas dividem o mesmo ponto,
    o que corta as consultas sem perder nada; ``ponto`` = posição da localidade."""
    from core.open_meteo import pm25_horario
    if localidades.empty:
        return pd.DataFrame(columns=["ponto", "hora", "pm25"])
    celula = list(zip(np.round(localidades["lon"].to_numpy() / PASSO_PM25_GRAUS).astype(int),
                      np.round(localidades["lat"].to_numpy() / PASSO_PM25_GRAUS).astype(int)))
    unicas = list(dict.fromkeys(celula))
    pm = pm25_horario([(x * PASSO_PM25_GRAUS, y * PASSO_PM25_GRAUS) for x, y in unicas], obter=obter)
    posicao = {c: k for k, c in enumerate(unicas)}
    por_celula = {k: g.drop(columns="ponto") for k, g in pm.groupby("ponto")}
    partes = [por_celula[posicao[c]].assign(ponto=i) for i, c in enumerate(celula) if posicao[c] in por_celula]
    return pd.concat(partes, ignore_index=True)[["ponto", "hora", "pm25"]]


ETAPAS_AO_VIVO = ("eventos", "frentes de fogo", "passagens", "vento", "PM2,5")


def buscar_dados_ao_vivo(municipio_geom, localidades: pd.DataFrame, obter=None, progresso=None) -> dict:
    """Eventos de fogo e frentes (Painel do Fogo), vento nas frentes dos eventos ativos e PM2,5 das
    localidades (Open-Meteo). As consultas independentes vão em paralelo; cada parte que falhar vira um
    aviso e a análise segue sem ela. ``tempos`` = segundos de cada etapa; ``progresso(fração)`` é chamado a
    cada etapa concluída (a tela mostra a porcentagem enquanto busca em segundo plano)."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from core.open_meteo import vento_horario
    from core.painel_do_fogo import buscar_eventos, buscar_frentes, buscar_passagens, resumo_por_evento
    from core.rede import SemDadosAoVivo, obter_json
    obter = obter or obter_json
    x0, y0, x1, y1 = municipio_geom.bounds
    m = MARGEM_BUSCA_GRAUS
    limites, recorte = (x0 - m, y0 - m, x1 + m, y1 + m), municipio_geom.buffer(m)
    dados = {"eventos": None, "vento_eventos": None, "pm25": None, "passagens": None, "avisos": [], "tempos": {},
             "buscado_em": datetime.now(timezone.utc)}
    inicio = time.perf_counter()

    def cronometrar(nome, funcao, *args):
        t0 = time.perf_counter()
        try:
            return funcao(*args)
        finally:
            dados["tempos"][nome] = round(time.perf_counter() - t0, 1)
            avisar()

    def avisar():
        if progresso is not None:
            feitas = sum(1 for e in ETAPAS_AO_VIVO if e in dados["tempos"])
            progresso(min(feitas / len(ETAPAS_AO_VIVO), 1.0))

    with ThreadPoolExecutor(4) as executor:
        f_eventos = executor.submit(cronometrar, "eventos", buscar_eventos, limites, obter, recorte, False)
        f_frentes = executor.submit(cronometrar, "frentes de fogo", buscar_frentes, limites, obter)
        f_pm25 = executor.submit(cronometrar, "PM2,5", _pm25_das_localidades, localidades, obter)
        try:
            ev = f_eventos.result()
            f_passagens = executor.submit(cronometrar, "passagens", buscar_passagens,
                                          list(ev.eventos["id_evento"]), obter)
            try:
                frentes = f_frentes.result()
            except SemDadosAoVivo as erro:
                frentes = {}
                dados["avisos"].append(f"Frentes de fogo: {erro} — os cones partem do evento inteiro.")
            ev.eventos["frente"] = [frentes.get(i) for i in ev.eventos["id_evento"]]
            # vento só no centro da frente dos eventos ativos (os cones são só deles)
            ativos = [k for k, s in enumerate(ev.eventos["status"]) if s == "Ativo"]
            centros = [(g.centroid.x, g.centroid.y) for g in
                       (ev.eventos["frente"].iloc[k] if ev.eventos["frente"].iloc[k] is not None
                        else ev.eventos["geometria"].iloc[k] for k in ativos)]
            f_vento = executor.submit(cronometrar, "vento", vento_horario, centros, 2, obter) if centros else None
            if f_vento is None:
                dados["tempos"]["vento"] = 0.0           # sem evento ativo: nada a buscar
                avisar()
            ev.passagens = f_passagens.result()
            dados["eventos"] = resumo_por_evento(ev)
            dados["passagens"] = ev.passagens
            if f_vento is not None:
                vento = f_vento.result()
                vento["ponto"] = [ativos[p] for p in vento["ponto"]]
                dados["vento_eventos"] = vento
        except SemDadosAoVivo as erro:
            dados["avisos"].append(f"Eventos de fogo/vento: {erro}")
        try:
            dados["pm25"] = f_pm25.result()
        except SemDadosAoVivo as erro:
            dados["avisos"].append(f"PM2,5: {erro}")
    for etapa in ETAPAS_AO_VIVO:                     # etapas puladas por falha contam como concluídas
        dados["tempos"].setdefault(etapa, 0.0)
    dados["tempos"]["total"] = round(time.perf_counter() - inicio, 1)
    if progresso is not None:
        progresso(1.0)
    return dados


def dissolver_cones(cones: list[dict]) -> list[dict]:
    """Cones do mesmo tipo dissolvidos pelo número de cones que se sobrepõem em cada lugar (1, 2, 3 ou mais):
    quanto mais eventos mandam fogo ou fumaça para o mesmo lugar, maior a classe (pedido de 25/11/2026).
    Faces exatas (``polygonize`` das bordas), não grade."""
    saida = []
    for tipo in ("fogo", "fumaca"):
        poligonos = [c["poligono"] for c in cones if c["tipo"] == tipo]
        if not poligonos:
            continue
        faces = list(shapely.get_parts(shapely.polygonize([shapely.union_all([p.boundary for p in poligonos])])))
        pontos = [f.representative_point() for f in faces]
        contagem = [sum(p.covers(pt) for p in poligonos) for pt in pontos]
        for n in (1, 2, 3):
            grupo = [f for f, c in zip(faces, contagem) if (c >= 3 if n == 3 else c == n)]
            if grupo:
                saida.append({"tipo": tipo, "sobreposicao": n, "classe": CLASSES_SOBREPOSICAO[n],
                              "poligono": shapely.make_valid(shapely.union_all(grupo))})
    return saida


def geojson_dos_cones(cones_dissolvidos: list[dict]) -> str:
    import json
    feicoes = [{"type": "Feature", "geometry": shapely.geometry.mapping(c["poligono"]),
                "properties": {"tipo": "avanço do fogo em 24 h" if c["tipo"] == "fogo" else "fumaça em 6 h",
                               "sobreposicao": c["sobreposicao"], "classe": c["classe"]}}
               for c in cones_dissolvidos]
    return json.dumps({"type": "FeatureCollection", "features": feicoes}, ensure_ascii=False)


def resumo_por_classe(analise: AnaliseVulnerabilidade) -> dict[str, int]:
    contagem = analise.localidades["classe"].value_counts()
    return {nome: int(contagem.get(nome, 0)) for _, nome in CLASSES_RISCO}


def rosa_dos_ventos(azimute: float) -> str:
    if azimute is None or (isinstance(azimute, float) and math.isnan(azimute)):
        return "—"
    nomes = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]
    return nomes[int((azimute % 360 + 22.5) // 45) % 8]
