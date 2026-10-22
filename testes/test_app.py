# -*- coding: utf-8 -*-
"""Interface Streamlit (roda o app.py sem navegador, com a amostra de amostras/bases)."""

import pytest
from streamlit.testing.v1 import AppTest

from core import config
from core.config import RAIZ

APP = str(RAIZ / "app.py")
TEMPO = 120


DIAGNOSTICO = "🔥 Diagnóstico"


def rodar(pagina=DIAGNOSTICO) -> AppTest:
    """Abre o programa (página inicial = Panorama do Estado) e vai para ``pagina``."""
    at = AppTest.from_file(APP, default_timeout=TEMPO).run()
    if pagina:
        at.sidebar.radio[0].set_value(pagina).run()
    assert not at.exception, at.exception
    return at


def textos(at) -> str:
    partes = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
    return "\n".join(str(p) for p in partes)


def processar(at) -> AppTest:
    botao = next(b for b in at.sidebar.button if b.label.startswith("🚀 Processar"))
    botao.click().run()
    assert not at.exception, at.exception
    return at


def test_tela_inicial():
    at = rodar()
    assert at.sidebar.radio[1].value == config.TIPO_MUNICIPIO
    assert at.sidebar.selectbox[0].value == "Pará"                  # estado padrão
    assert at.sidebar.slider[0].value == (2023, 2024)
    assert "Processar Diagnóstico Completo" in textos(at)


def test_diagnostico_municipio():
    at = rodar()
    at.sidebar.selectbox[1].set_value("SÃO FÉLIX DO XINGU").run()
    at.sidebar.checkbox[0].uncheck().run()                          # sem download automático
    processar(at)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Focos em 2024"] == "7.356"
    assert metricas["Posição no país — 2024"] == "1º de 157"
    assert metricas["Posição no estado — 2024"] == "1º de 141"
    assert metricas["Variação 2024 vs. 2023"] == "+153,8%"
    assert metricas["Densidade média anual (focos/km²/ano)"] == "0,061"
    assert "Comparativo na Região Araguaia (2024)" in textos(at)
    assert any("Diagnóstico concluído com sucesso" in s.value for s in at.success)
    assert at.get("download_button")


def test_diagnostico_municipio_com_download_automatico():
    at = rodar()
    at.sidebar.selectbox[1].set_value("NOVO PROGRESSO").run()
    processar(at)
    assert any("iniciado automaticamente" in s.value for s in at.success)


def test_municipio_fora_do_para_usa_a_regiao_imediata():
    at = rodar()
    at.sidebar.selectbox[0].set_value("Amapá").run()
    at.sidebar.selectbox[1].set_value("OIAPOQUE").run()
    at.sidebar.checkbox[0].uncheck().run()
    processar(at)
    assert "Comparativo na Região Geográfica Imediata de Oiapoque (2024)" in textos(at)
    assert "Top 5 2024 - Estado" in textos(at)


def test_municipio_sem_limite_avisa():
    at = rodar()
    at.sidebar.selectbox[1].set_value("BELÉM").run()                # fora do recorte de amostra
    processar(at)
    assert any("não encontrado" in w.value for w in at.warning)


def test_diagnostico_terra_indigena():
    at = rodar()
    at.sidebar.radio[1].set_value(config.TIPO_TI).run()
    at.sidebar.selectbox[0].set_value("KAYAPÓ (23001)").run()
    processar(at)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Focos em 2024"] == "3.259"
    assert metricas["Total no Período"] == "3.398"
    assert metricas["Posição entre as TIs do estado (PA)"] == "1º de 46"
    assert "Cenário Atual (nowcast diário)" in textos(at)                                       # P23
    assert "Estatísticas de Focos Ativos (modelo Programa Queimadas/INPE)" in textos(at)      # P14
    assert any("iniciado automaticamente" in s.value for s in at.success)                    # P7
    assert at.get("download_button")


@pytest.mark.parametrize("tipo", [config.TIPO_UC, config.TIPO_TI])
def test_opcoes_de_areas_protegidas(tipo):
    at = rodar()
    at.sidebar.radio[1].set_value(tipo).run()
    assert not at.exception
    assert "NONE" not in at.sidebar.selectbox[0].options


def test_pagina_bases():
    at = rodar("🗂️ Bases de dados")
    situacao = at.dataframe[0].value
    assert len(situacao) == 4 and set(situacao[""]) == {"✅"}
    assert {m.label: m.value for m in at.metric}["Focos"] == "102.371"


def test_base_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BASES_DIR", tmp_path)
    at = AppTest.from_file(APP, default_timeout=TEMPO).run()
    assert not at.exception
    assert any("Nenhum dado de foco encontrado" in e.value for e in at.error)


def test_estatisticas_do_municipio():
    at = rodar()
    at.sidebar.selectbox[1].set_value("SÃO FÉLIX DO XINGU").run()
    at.sidebar.checkbox[0].uncheck().run()
    processar(at)
    assert "Estatísticas de Focos Ativos (modelo Programa Queimadas/INPE)" in textos(at)
    assert at.selectbox(key="est_ano").value == 2024
    graficos = at.get("vega_lite_chart")
    assert len(graficos) == 6               # nowcast + comparativos mensal, semanal, 2 semestres + acumulado
    assert any("O relatório PDF e o pacote usam estes parâmetros" in c.value for c in at.caption)

    # ajustar um parâmetro não perde o diagnóstico e oferece aplicar ao relatório
    at.selectbox(key="est_ano").set_value(2023).run()
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Focos em 2024"] == "7.356"
    assert any("ainda usam os parâmetros anteriores" in i.value for i in at.info)
    at.button(key="est_aplicar").click().run()
    assert not at.exception
    assert any("O relatório PDF e o pacote usam estes parâmetros" in c.value for c in at.caption)
    assert at.selectbox(key="est_ano").value == 2023


def test_resultado_continua_na_tela_e_some_ao_mudar_o_territorio():
    at = rodar()
    at.sidebar.selectbox[1].set_value("NOVO PROGRESSO").run()
    at.sidebar.checkbox[0].uncheck().run()
    processar(at)
    at.run()                                                        # outra interação qualquer
    assert {m.label: m.value for m in at.metric}["Focos em 2024"] == "4.787"
    at.sidebar.selectbox[1].set_value("ALTAMIRA").run()
    assert not at.metric
    assert "Processar Diagnóstico Completo" in textos(at)


def test_nowcast_e_painel_da_base():
    at = rodar()
    assert any("Dados até **31/12/2024**" in m.value for m in at.sidebar.markdown)
    at.sidebar.selectbox[1].set_value("SÃO FÉLIX DO XINGU").run()
    at.sidebar.checkbox[0].uncheck().run()
    processar(at)
    assert "Cenário Atual (nowcast diário)" in textos(at)
    metricas = {m.label: m.value for m in at.metric}
    assert "Últimos 7 dias" in metricas and "No ano até 31/12" in metricas
    at.select_slider(key="nowcast_dias").set_value(30).run()
    assert not at.exception


@pytest.fixture
def bases_temporarias(tmp_path, monkeypatch):
    import shutil
    destino = tmp_path / "bases"
    shutil.copytree(config.AMOSTRAS_BASES, destino)
    monkeypatch.setattr(config, "BASES_DIR", destino)
    return destino


def test_abre_com_a_base_local_sem_esperar_a_busca(bases_temporarias, monkeypatch):
    """A busca no INPE roda em segundo plano: a tela abre enquanto ela ainda não terminou."""
    import threading
    from core import atualizacao
    entrou, liberar = threading.Event(), threading.Event()

    def servidor_lento(url):
        entrou.set()
        liberar.wait(20)
        raise atualizacao.SemConexao("rede indisponível")
    monkeypatch.setattr(atualizacao, "listar", servidor_lento)
    monkeypatch.setattr(config, "ATUALIZACAO_AUTOMATICA", True)
    try:
        at = rodar(None)                                             # Panorama abre com a base local
        assert any("Dados até **31/12/2024**" in m.value for m in at.sidebar.markdown)
        assert entrou.wait(10)                                       # a busca começou e continua presa
        at.run()
        assert not at.exception
        assert any("⏳" in c.value for c in at.sidebar.caption)      # "busca em andamento" no painel
    finally:
        liberar.set()


def test_toggle_nowcast_liga_e_busca(bases_temporarias, monkeypatch):
    import time
    from core import atualizacao
    chamadas = []

    def sem_rede(url):
        chamadas.append(url)
        raise atualizacao.SemConexao("rede indisponível")
    monkeypatch.setattr(atualizacao, "listar", sem_rede)
    at = rodar(None)
    toggle = at.sidebar.toggle(key="toggle_nowcast")
    assert toggle.value is False and "4 h" in toggle.label
    toggle.set_value(True).run()
    assert not at.exception
    assert atualizacao.nowcast_ligado(bases_temporarias)
    for _ in range(50):                                              # a thread busca na hora
        if chamadas:
            break
        time.sleep(0.1)
    assert chamadas
    assert not any(b.label.startswith("🔄 Buscar") for b in at.sidebar.button)   # o botão antigo saiu


def test_panorama_do_estado():
    at = rodar(None)
    assert "Panorama do Estado" in at.sidebar.radio[0].value
    assert at.selectbox(key="pan_estado").value == "Pará"
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Focos em 2024"] == "56.069"
    assert metricas["Mesmo período de 2023"] == "41.713"
    at.selectbox(key="pan_regiao").set_value("Região Xingu").run()
    assert not at.exception
    assert "Região Xingu — focos de calor em 2024" in textos(at)
    assert "Estatísticas de Focos Ativos (modelo Programa Queimadas/INPE)" in textos(at)
