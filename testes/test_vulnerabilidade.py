# -*- coding: utf-8 -*-
"""Protótipo de localidades vulneráveis (P42), eventos do Painel do Fogo, Open-Meteo e vento (P40/P41).

As respostas dos serviços são as reais de 25/11/2026 para São Félix do Xingu (amostras/ao_vivo), devolvidas
pela consulta (endereço + parâmetros), já que a busca roda em paralelo — os testes nunca acessam a internet.
"""

import base64
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from core import config
from core.localidades import carregar_localidades
from core.territorios import estados_disponiveis, geometria_municipio
from core import vulnerabilidade as v

GRAVACAO = config.AMOSTRAS_DIR / "ao_vivo" / "sao_felix_do_xingu.json"
MOMENTO = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)


def repetidor(usadas=None):
    gravadas = json.loads(GRAVACAO.read_text(encoding="utf-8"))
    por_consulta = {(g["url"], json.dumps(g["parametros"], sort_keys=True)): g["resposta"] for g in gravadas}

    def obter(url, parametros=None, timeout=40):
        chave = (url, json.dumps(parametros, sort_keys=True))
        assert chave in por_consulta, f"consulta não gravada: {url} {parametros}"
        if usadas is not None:
            usadas.append(chave)
        return por_consulta[chave]
    return obter


@pytest.fixture(scope="module")
def municipio():
    geom = geometria_municipio(estados_disponiveis()["Pará"], "SÃO FÉLIX DO XINGU")
    loc = carregar_localidades("PA")
    return geom, loc[loc["municipio"] == "São Félix do Xingu"].reset_index(drop=True)


@pytest.fixture(scope="module")
def ao_vivo(municipio):
    geom, loc = municipio
    return v.buscar_dados_ao_vivo(geom, loc, repetidor())


def test_eventos_do_painel_do_fogo(ao_vivo):
    ev = ao_vivo["eventos"]
    assert ao_vivo["avisos"] == [] and len(ev) > 0
    assert ev["frente"].notna().any() and all(f.is_valid for f in ev["frente"].dropna())     # frente de fogo 24 h
    assert {"eventos", "frentes de fogo", "passagens", "vento", "PM2,5", "total"} <= set(ao_vivo["tempos"])
    assert set(ev["status"]) <= {"Ativo", "Em observação"}
    assert (ev["area_ha"] > 0).all() and (ev["expansao_ha_h"] >= 0).all()
    assert all(g.is_valid for g in ev["geometria"])
    vento = ao_vivo["vento_eventos"]
    ativos = {k for k, s in enumerate(ev["status"]) if s == "Ativo"}
    assert set(vento["ponto"]) == ativos                                # vento só nas frentes dos ativos
    assert vento["direcao_graus"].between(0, 360).all() and (vento["velocidade_kmh"] >= 0).all()
    assert ao_vivo["pm25"]["pm25"].notna().any()


def test_analise_completa(municipio, ao_vivo):
    geom, loc = municipio
    vazio = pd.DataFrame(columns=["lon", "lat", "data", "ano"])
    a = v.analisar(loc, geom, vazio, "2024-12-31", vazio, list(range(2016, 2025)), ao_vivo["eventos"],
                   ao_vivo["vento_eventos"], ao_vivo["pm25"], agora=MOMENTO)
    assert len(a.localidades) == len(loc)
    assert a.localidades["vulnerabilidade"].between(1, 3).all()
    assert a.localidades["exposicao"].between(0, 3).all()
    assert set(a.localidades["classe"]) <= set(v.CORES_CLASSE)
    assert (a.localidades["risco"] == a.localidades["exposicao"] * a.localidades["vulnerabilidade"]).all()
    assert a.localidades["risco"].is_monotonic_decreasing
    indigenas = a.localidades[a.localidades["indigena"]]
    assert (indigenas["vulnerabilidade"] == 3).all()
    # cones só de eventos ativos; quem está num cone de fumaça tem a hora de chegada
    ativos = set(a.eventos.loc[a.eventos["status"] == "Ativo", "id_evento"])
    assert {c["id_evento"] for c in a.cones} <= ativos
    com_fumaca = a.localidades[a.localidades["evento_fumaca"].notna()]
    assert (com_fumaca["exposicao"] >= 2).all() and com_fumaca["eta_fumaca_h"].notna().all()
    assert sum(v.resumo_por_classe(a).values()) == len(loc)


def test_sem_dados_ao_vivo_usa_so_a_base(municipio):
    geom, loc = municipio
    x0, y0, x1, y1 = geom.bounds
    focos = pd.DataFrame({"lon": [(x0 + x1) / 2], "lat": [(y0 + y1) / 2], "data": [pd.Timestamp("2024-12-31")],
                          "ano": [2024]})
    a = v.analisar(loc, geom, focos, "2024-12-31", focos, [2024], agora=MOMENTO)
    assert a.eventos.empty and not a.cones and a.localidades["pm25_max"].isna().all()
    perto = a.localidades[a.localidades["foco_24h_km"] <= 5]
    assert (perto["exposicao"] == 3).all()
    assert (a.localidades["foco_7d_km"] >= a.localidades["foco_24h_km"] - 1e-9).all()


def test_elipse_de_anderson():
    assert v.razao_comprimento_largura(0) == pytest.approx(1.0, abs=0.01)
    assert v.razao_comprimento_largura(30) > v.razao_comprimento_largura(10) > 1
    assert v.razao_comprimento_largura(500) == v.LB_MAXIMO
    # sem expansão o fogo não avança; com vento a cabeça avança mais que sem vento
    assert v.avanco_da_frente_km(100, 0, 20, 24) == 0
    assert v.avanco_da_frente_km(100, 5, 30, 24) > v.avanco_da_frente_km(100, 5, 0, 24) > 0
    assert v.abertura_fogo_graus(2) == 180 and v.abertura_fogo_graus(40) < 45


def test_vento_medio_e_rosa():
    hora = pd.Timestamp("2026-11-25 12:00")
    vento = pd.DataFrame({"hora": [hora + pd.Timedelta(hours=h) for h in range(6)], "velocidade_kmh": [10.0] * 6,
                          "direcao_graus": [90.0] * 6})               # vem do leste → sopra para oeste
    vel, para = v.vento_medio(vento, hora, 6)
    assert vel == pytest.approx(10) and para == pytest.approx(270)
    assert v.rosa_dos_ventos(270) == "O" and v.rosa_dos_ventos(0) == "N" and v.rosa_dos_ventos(float("nan")) == "—"


def test_setor_em_lon_lat():
    proj = v.Projecao(-52.0, -6.0)
    cone = v.setor(proj, (0, 0), 90, 50, 30)                         # 50 km para o leste
    x0, y0, x1, y1 = cone.bounds
    assert x0 == pytest.approx(-52.0, abs=0.01) and x1 > -51.6 and abs(y1 - y0) < 0.5


# ------------------------------------------------------------------ Open-Meteo e vento por quadrícula

def resposta_vento(n, horas=4):
    tempos = [f"2026-11-25T{h:02d}:00" for h in range(horas)]
    return [{"hourly": {"time": tempos, "wind_speed_10m": [5.0 + k] * horas, "wind_direction_10m": [90.0] * horas,
                        "wind_gusts_10m": [9.0] * horas}} for k in range(n)]


def test_open_meteo_em_lotes():
    from core.open_meteo import LOTE, vento_horario
    pedidos = []

    def obter(url, parametros=None, timeout=40):
        n = len(parametros["latitude"].split(","))
        pedidos.append(n)
        return resposta_vento(n)
    pontos = [(-52 + i * 0.01, -6.0) for i in range(LOTE + 30)]
    df = vento_horario(pontos, obter=obter)
    assert pedidos == [LOTE, 30] and df["ponto"].nunique() == LOTE + 30
    assert list(df.columns) == ["ponto", "hora", "velocidade_kmh", "direcao_graus", "rajada_kmh"]


def test_open_meteo_resposta_inesperada():
    from core.open_meteo import vento_horario
    from core.rede import SemDadosAoVivo
    with pytest.raises(SemDadosAoVivo):
        vento_horario([(-52, -6), (-51, -6)], obter=lambda *a, **k: {"erro": True})


def test_coleta_do_vento(tmp_path):
    import shutil
    from core import vento
    shutil.copy(config.AMOSTRAS_BASES / config.NOME_FOCOS_PARQUET, tmp_path / config.NOME_FOCOS_PARQUET)
    assert vento.chave_vento(tmp_path) == {"ligado": False, "estado": None}
    vento.gravar_chave_vento(True, "Pará", tmp_path)
    assert vento.chave_vento(tmp_path) == {"ligado": True, "estado": "Pará"}

    sigla, pontos = vento.quadriculas_com_focos("Pará", tmp_path)
    assert sigla == "PA" and 0 < len(pontos) <= vento.LIMITE_QUADRICULAS
    assert all(math.isclose((lon / 0.25) % 1, 0.5, abs_tol=1e-6) for lon, _ in pontos)     # centros da grade

    def obter(url, parametros=None, timeout=40):
        return resposta_vento(len(parametros["latitude"].split(",")))
    agora = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    frase = vento.coletar_vento("Pará", tmp_path, obter, agora)
    assert f"{len(pontos)} quadrículas" in frase
    df = vento.carregar_vento(tmp_path)
    assert len(df) == len(pontos) * 4 and set(df["sigla_uf"]) == {"PA"}
    vento.coletar_vento("Pará", tmp_path, obter, agora)                 # coletar de novo não duplica
    assert len(vento.carregar_vento(tmp_path)) == len(pontos) * 4
    uma = vento.vento_na_hora(df, pd.Timestamp("2026-11-25 02:10"), "PA")
    assert len(uma) == len(pontos) and (uma["hora"] == pd.Timestamp("2026-11-25 02:00")).all()


def test_vento_sem_internet_vira_frase(tmp_path):
    import shutil
    from core import vento
    from core.rede import SemDadosAoVivo
    shutil.copy(config.AMOSTRAS_BASES / config.NOME_FOCOS_PARQUET, tmp_path / config.NOME_FOCOS_PARQUET)

    def sem_rede(*a, **k):
        raise SemDadosAoVivo("rede indisponível")
    assert "rede indisponível" in vento.coletar_vento("Pará", tmp_path, sem_rede)
    assert not (tmp_path / vento.ARQUIVO_VENTO).exists()


def test_thread_so_busca_vento_com_a_chave_ligada(tmp_path, monkeypatch):
    from core import atualizacao, vento
    from core.atualizacao import AtualizadorFocos, ResultadoAtualizacao
    chamadas = []
    monkeypatch.setattr(config, "DADOS_AO_VIVO", True)
    monkeypatch.setattr(vento, "coletar_vento", lambda estado, pasta: chamadas.append(estado) or "Vento: ok")
    at = AtualizadorFocos(tmp_path, atualizar_fn=lambda *a, **k: ResultadoAtualizacao("em_dia", "ok"))
    at.executar_uma_vez()
    assert chamadas == [] and at.estado["vento"] is None
    vento.gravar_chave_vento(True, "Amapá", tmp_path)
    at.executar_uma_vez()
    assert chamadas == ["Amapá"] and at.estado["vento"] == "Vento: ok"


# ------------------------------------------------------------------ Sentinel-2 SWIR e mapa

def test_camada_sentinel_swir():
    from core.mapa_interativo import estilo_satelite
    estilo = json.loads(base64.b64decode(estilo_satelite(swir=True).split(",", 1)[1]))
    assert [c["id"] for c in estilo["layers"]] == ["s2", "swir"]
    url = estilo["sources"]["swir"]["tiles"][0]
    assert "painel_do_fogo:sentinel_swir" in url and "{bbox-epsg-3857}" in url
    assert "swir" not in json.loads(base64.b64decode(estilo_satelite().split(",", 1)[1]))["sources"]


def test_mapa_da_vulnerabilidade(municipio, ao_vivo):
    from core.mapa_interativo import deck_vulnerabilidade, legenda_vulnerabilidade_html, setas_de_vento
    geom, loc = municipio
    vazio = pd.DataFrame(columns=["lon", "lat", "data", "ano"])
    a = v.analisar(loc, geom, vazio, "2024-12-31", vazio, [2024], ao_vivo["eventos"], ao_vivo["vento_eventos"],
                   ao_vivo["pm25"], agora=MOMENTO)
    cones = v.dissolver_cones(a.cones)
    deck = deck_vulnerabilidade(a, geom, satelite=False, cones=cones)
    camadas = {c.id for c in deck.layers}
    assert {"eventos", "frentes", "municipio", "vento", "localidades"} <= camadas
    assert deck_vulnerabilidade(a, geom, satelite=False, cones=cones, alvo=(-52.0, -6.0)).initial_view_state.zoom > 10
    desligadas = deck_vulnerabilidade(a, geom, satelite=False, cones=cones,
                                      camadas={"vento": (False, 90), "localidades": (True, 30)})
    assert "vento" not in {c.id for c in desligadas.layers}
    assert next(c for c in desligadas.layers if c.id == "localidades").opacity == pytest.approx(0.3)
    camadas_json = {c["id"]: c for c in json.loads(deck.to_json())["layers"]}
    assert camadas_json["localidades"]["@@type"] == "IconLayer"           # casinhas, não pontos
    assert camadas_json["localidades"]["sizeUnits"] == "pixels"           # "@@=pixels" deixa o mapa cinza
    assert not any(str(valor).startswith("@@=") and valor not in ("@@=cor", "@@=posicao", "@@=raio", "@@=poligono",
                                                                   "@@=caminho", "@@=icone", "@@=tamanho")
                   for c in camadas_json.values() for valor in c.values())
    assert len(setas_de_vento([(-52, -6, 10, 90), (-52, -6, float("nan"), 90)])) == 2     # 1 seta = 2 linhas
    assert "Muito alto" in legenda_vulnerabilidade_html()


def test_pm25_numa_grade_de_celulas(municipio):
    geom, loc = municipio
    pedidos = []

    def obter(url, parametros=None, timeout=40):
        n = len(parametros["latitude"].split(","))
        pedidos.append(n)
        return [{"hourly": {"time": ["2026-11-25T18:00"], "pm2_5": [float(k)]}} for k in range(n)]
    pm = v._pm25_das_localidades(loc, obter)
    assert sum(pedidos) < len(loc)                                       # localidades vizinhas dividem o ponto
    assert set(pm["ponto"]) == set(range(len(loc)))


def test_cones_dissolvidos_pela_sobreposicao():
    from shapely.geometry import box
    cones = [{"id_evento": 1, "tipo": "fumaca", "poligono": box(0, 0, 2, 2)},
             {"id_evento": 2, "tipo": "fumaca", "poligono": box(1, 0, 3, 2)},
             {"id_evento": 3, "tipo": "fumaca", "poligono": box(1.5, 0, 4, 2)},
             {"id_evento": 1, "tipo": "fogo", "poligono": box(10, 10, 11, 11)}]
    d = {(c["tipo"], c["sobreposicao"]): c["poligono"] for c in v.dissolver_cones(cones)}
    assert d[("fumaca", 3)].area == pytest.approx(0.5 * 2)              # x de 1,5 a 2
    assert d[("fumaca", 2)].area == pytest.approx((0.5 + 1.0) * 2)       # x 1–1,5 e 2–3
    assert d[("fumaca", 1)].area == pytest.approx((1 + 1) * 2)           # x 0–1 e 3–4
    assert d[("fogo", 1)].area == pytest.approx(1) and ("fogo", 2) not in d
    gj = json.loads(v.geojson_dos_cones(v.dissolver_cones(cones)))
    assert len(gj["features"]) == 4 and {f["properties"]["classe"] for f in gj["features"]} >= {"3 ou mais eventos"}


def test_setas_de_vento_agrupadas():
    from core.mapa_interativo import agrupar_setas
    setas = agrupar_setas([(-52.01, -6.01, 10, 90), (-52.02, -6.02, 10, 90), (-50.0, -6.0, 5, 0)], 0.5)
    assert len(setas) == 2
    junta = min(setas, key=lambda s: s[0])
    assert junta[2] == pytest.approx(10) and junta[3] == pytest.approx(90)


def test_progresso_da_busca(municipio):
    geom, loc = municipio
    fracoes = []
    v.buscar_dados_ao_vivo(geom, loc, repetidor(), progresso=fracoes.append)
    assert fracoes[-1] == 1.0 and all(0 < f <= 1 for f in fracoes)
    assert fracoes == sorted(fracoes) or max(fracoes) == 1.0


def test_qualidade_do_ar_conama():
    """P45 (27/11/2026): faixas do IQAR da CONAMA 491/2018 para PM2,5 em 24 h."""
    from core.vulnerabilidade import qualidade_do_ar
    assert [qualidade_do_ar(v) for v in (10, 25, 26, 50.5, 75, 80, 130)] == [
        "Boa", "Boa", "Moderada", "Ruim", "Ruim", "Muito ruim", "Péssima"]
    assert qualidade_do_ar(float("nan")) == ""


def test_perfil_descreve_sem_mudar_a_escala():
    """P46: a vulnerabilidade continua de 1 a 3; o perfil diz o que pesou."""
    from core.vulnerabilidade import _perfil
    assert _perfil(3, True, True) == "indígena/quilombola · isolada (> 30 km da sede) · fogo recorrente ao redor"
    assert _perfil(1, False, False) == "área urbana"


def test_pdf_e_pacote_da_vulnerabilidade(municipio, ao_vivo):
    """P47 (27/11/2026): boletim em PDF só desta seção (docs/10 §9.1) e o pacote com GeoJSON e planilha."""
    import io
    import re
    import zipfile

    from core.relatorio_vulnerabilidade import gerar_pdf_vulnerabilidade, pacote_vulnerabilidade, texto_da_situacao
    geom, loc = municipio
    vazio = pd.DataFrame(columns=["lon", "lat", "data", "ano"])
    a = v.analisar(loc, geom, vazio, "2024-12-31", vazio, list(range(2016, 2025)), ao_vivo["eventos"],
                   ao_vivo["vento_eventos"], ao_vivo["pm25"], agora=MOMENTO)
    pdf, nome, figuras = gerar_pdf_vulnerabilidade(a, "SÃO FÉLIX DO XINGU", "Pará", geom, ao_vivo, fundo=False)
    assert nome.startswith("localidades_risco_fogo_") and nome.endswith(".pdf")
    assert pdf.startswith(b"%PDF") and len(re.findall(rb"/Type /Page\b", pdf)) >= 4     # situação, lista, eventos, método
    assert figuras["severidade"] is not None and figuras["pm25"] is not None
    assert texto_da_situacao(a).endswith(".")
    conteudo, nome_zip = pacote_vulnerabilidade(pdf, nome, a, figuras)
    arquivos = set(zipfile.ZipFile(io.BytesIO(conteudo)).namelist())
    assert {nome, "localidades.geojson", "eventos_de_fogo.geojson", "cones_fogo_fumaca.geojson",
            "localidades_e_eventos.xlsx", "figuras/mapa.png"} <= arquivos
    assert nome_zip == nome.replace(".pdf", ".zip")
    geo = json.loads(zipfile.ZipFile(io.BytesIO(conteudo)).read("localidades.geojson"))
    assert len(geo["features"]) == len(loc)
