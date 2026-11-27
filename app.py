# -*- coding: utf-8 -*-
"""AutoSIMD-FOCOS — interface Streamlit (docs/02).

Toda regra fica em ``core/``; aqui só há telas. Fluxo: escolher o território e o período na
barra lateral → processar → ver indicadores, gráficos, mapas e tabelas → baixar o pacote .zip.

    python -m streamlit run app.py
"""

import base64
from html import escape
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import altair as alt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner import get_script_run_ctx

from core import config
from core.atualizacao import CICLO_NOWCAST_H, AtualizadorFocos, situacao_da_base, versao_da_base
from core.diagnostico import DiagnosticoMunicipio, diagnosticar_area, diagnosticar_municipio
from core.estatisticas import (
    LINHAS_RESUMO, MESES_TABELA, ParametrosEstatisticas, cobertura_base, estatisticas_territorio,
    extremos_por_coluna, notas, resolver_parametros, tabela_acumulado_exibicao, tabela_comparativo_exibicao,
    tabela_diaria_exibicao, tabela_mensal_exibicao,
)
from core.focos import (
    anos_disponiveis, areas_com_focos, carregar_focos, focos_da_area, focos_do_municipio, municipios_da_uf,
)
from core.graficos_estatisticas import (
    interativo_acumulado, interativo_comparativo, interativo_nowcast, interativo_nowcast_semanal,
)
from core.grade import grade_do_territorio, nota_grade
from core.kernel import DESVIO_KERNEL_KM
from core.graficos_estatisticas import grafico_sazonalidade
from core.mapas import mapa_dispersao, mapa_recentes
from core.cenario import (
    DIAS_SEMANA, MAX_FOCOS_GEOJSON, MESES_EXTENSO, cenario_atual, focos_do_recorte, focos_no_intervalo,
    geojson_focos, recorrencia_do_mes, texto_do_cenario,
)
from core.panorama import (
    TODAS, TOP_MUNICIPIOS, estatisticas_dos_municipios, limite_da_regiao, panorama_estado, regioes_do_estado,
)
from core.relatorio_cenario import (
    anomalias_do_cenario, gerar_relatorio_cenario, indicadores_cenario, pacote_cenario,
)
from core.anomalias import TIPOS as TIPOS_ANOMALIA, texto_metodologia_markdown
from core.regioes import TIPO_IMEDIATA, TIPO_INTEGRACAO
from core.nowcast import nowcast_territorio
from core.vento import carregar_vento, chave_vento, vento_na_hora
from core.localidades import BaseLocalidadesAusente, carregar_localidades
from core.vulnerabilidade import (
    MARGEM_BUSCA_GRAUS, METODOLOGIA_VULNERABILIDADE, analisar, buscar_dados_ao_vivo, dissolver_cones,
    geojson_dos_cones, resumo_por_classe, rosa_dos_ventos,
)
from core.produto import ETAPAS_FIGURAS, fechar_figuras, figuras_anomalias, figuras_da_etapa, pacote, png
from core.territorios import (
    area_km2, areas_protegidas_no_territorio, carregar_areas_protegidas, estados_disponiveis,
    geometria_area_protegida, geometria_municipio, municipios_simplificados,
)
from core.texto import (chave_nome, fmt_densidade, fmt_inteiro, fmt_numero, fmt_percentual, fmt_posicao, nome_arquivo,
                        nome_proprio)
from core.mapa_interativo import (
    ALTURA_PX, CAMADAS_VULNERABILIDADE, deck_focos_recentes, deck_vulnerabilidade, legenda_html, legenda_vulnerabilidade_html,
    municipio_clicado,
)

st.set_page_config(
    page_title=f"{config.APP_NOME} v{config.APP_VERSAO}",
    page_icon="🔥",
    layout="wide",
    menu_items={
        "Get Help": config.REPOSITORIO,
        "Report a bug": f"{config.REPOSITORIO}/issues",
        "About": f"""
        ### {config.APP_NOME} (v{config.APP_VERSAO} — {config.APP_VERSAO_DATA})
        Desenvolvido por **{config.DESENVOLVEDOR_NOME}**
        *Engenheiro Ambiental | CBMPA | Defesa Civil Pará (DGR/SIMD)*
        """,
    },
)

st.markdown("""
    <style>
    .main-header { text-align: center; line-height: 1.3; margin-bottom: 12px; color: #1D2B23; }
    .main-header h2 { font-size: 22px; margin: 0; font-weight: bold; }
    .main-header h3 { font-size: 17px; margin: 2px 0; font-weight: normal; }
    /* linhas próximas até o nome do projeto: o Streamlit põe espaçamento próprio nos títulos */
    .main-header h2, .main-header h3 { padding: 0 !important; margin: 0 !important; line-height: 1.25 !important; }
    .main-header h2, .main-header h3 { font-family: "Fira Sans Condensed", "Fira Sans", sans-serif !important; }
    .main-header h3 { color: #4A5A50 !important; font-weight: 500 !important; }
    .main-header .sub { font-size: 15px; margin-top: 6px; color: #B23A1E; font-weight: 600; letter-spacing: .02em; }
    .main-header .ref { font-family: "Fira Sans Condensed", sans-serif; font-size: 26px; margin-top: 2px;
                        color: #0D6E7D; font-weight: 700; }
    /* boletim do cenário: o elemento de destaque da página */
    .boletim { border-left: 5px solid #B23A1E; background: #F7F8F5; padding: 14px 18px 6px 18px;
               border-radius: 0 6px 6px 0; max-width: 78ch; }
    .boletim h4 { font-family: "Fira Sans Condensed", sans-serif; font-weight: 700; font-size: 1.35rem;
                  margin: 0 0 6px 0; color: #1D2B23; padding: 0; }
    .boletim .quando { color: #6A786E; font-size: .9rem; margin-bottom: 8px; }
    .boletim p { font-size: 1.02rem; line-height: 1.55; margin: 0 0 10px 0; }
    .fichas { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 22px; }
    .ficha { border-top: 2px solid #C9D2C6; padding-top: 6px; }
    .ficha .rotulo { color: #4A5A50; font-size: .85rem; line-height: 1.25; }
    .ficha .numero { font-family: "Fira Sans Condensed", sans-serif; font-weight: 600; font-size: 1.9rem;
                     line-height: 1.15; color: #1D2B23; }
    .ficha .nota { color: #6A786E; font-size: .8rem; }
    [data-testid="stMetricLabel"] p { color: #4A5A50; font-size: .85rem; white-space: normal; }
    /* painel esquerdo: o bloco "⋯" (base INPE + sobre) fica preso no rodapé */
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
        min-height: calc(100vh - 10rem); }          /* desconta o rodapé fixo da página */
    [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > div:has(.st-key-rodape_lateral) {
        margin-top: auto; }
    .st-key-ouvinte_tabelas { display: none; }      /* só escuta o duplo clique nas tabelas */
    /* porcentagem da busca ao vivo sobre o canto inferior esquerdo do mapa da vulnerabilidade */
    .st-key-vul_carregando { position: relative; margin-top: -78px; margin-left: 14px; width: 46%; z-index: 5;
        background: rgba(29,43,35,.85); border-radius: 6px; padding: 6px 12px 2px; }
    .st-key-vul_carregando p { color: #fff !important; font-weight: 600; }
    [data-testid="stMetricLabel"] div, [data-testid="stMetricValue"] div { white-space: normal !important;
        overflow: visible !important; text-overflow: clip !important; }
    [data-testid="stMetricValue"] { font-family: "Fira Sans Condensed", sans-serif; }
    .logo-inicio { height: 38px; cursor: pointer; }
    .footer-container {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: var(--background-color, #FFFFFF);
        border-top: 1px solid var(--secondary-background-color, #CCCCCC);
        padding: 8px 30px; font-size: 12px; color: var(--text-color, #444444);
        display: flex; justify-content: space-between; align-items: center; gap: 16px;
        /* acima do painel lateral (z-index 999991 no Streamlit): o texto não é cortado quando o painel abre */
        z-index: 999992;
    }
    .stApp { padding-bottom: 70px; }
    /* espaço no fim do painel lateral para o rodapé fixo não cobrir os últimos botões */
    [data-testid="stSidebarContent"] { padding-bottom: 70px; }
    @media print {
        [data-testid="stSidebar"], .stButton, .stDownloadButton, button, header, footer, .footer-container {
            display: none !important;
        }
        .stApp { padding-bottom: 0 !important; background-color: #ffffff !important; color: #000000 !important; }
        .main .block-container { padding: 10px !important; max-width: 100% !important; }
        .element-container, img, div { page-break-inside: avoid; }
    }
    </style>
""", unsafe_allow_html=True)

NOTA_METODOLOGICA = (
    "• **Fonte dos Dados:** BDQueimadas / INPE (Satélite de referência Aqua-Tarde), atualizada com os arquivos "
    "diários e mensais do Programa Queimadas.\n"
    "• **Território:** município, UC e TI de cada foco pelo cruzamento do ponto do foco com os limites oficiais "
    "(IBGE, CNUC/MMA, FUNAI).\n"
    "• **Rankings:** empate decidido pelos focos no último mês e, depois, na última semana.\n"
    "• **Processamento:** Os dados foram processados automaticamente por algoritmos desenvolvidos "
    "**com apoio de Inteligência Artificial orientada por técnicos de Defesa Civil**.\n"
    f"• **Canais de Atendimento:** {config.EMAIL_SALA_MONITORAMENTO} | Plantão Defesa Civil: {config.TELEFONE_PLANTAO}."
)


# --------------------------------------------------------------- Peças comuns

# ------------------------------------------------- Modo dashboard (diagnóstico de município, pedido de 27/11/2026)

def modo_dashboard() -> bool:
    return bool(st.session_state.get("modo_dashboard"))


def dashboard_ativo() -> bool:
    """Dashboard no Panorama do Estado (pedido de 27/11/2026) e no diagnóstico de município; em UC/TI e em
    Bases de dados, a visualização de sempre."""
    if not modo_dashboard():
        return False
    pagina = st.session_state.get("navegacao", PAGINA_INICIAL)
    return pagina == PAGINA_INICIAL or (
        pagina == PAGINA_DIAGNOSTICO
        and st.session_state.get("diag_tipo", config.TIPO_MUNICIPIO) == config.TIPO_MUNICIPIO)


def lateral_recolhida() -> bool:
    return dashboard_ativo() and st.session_state.get("lateral_recolhida", True)


def _alternar_modo():
    st.session_state["modo_dashboard"] = not modo_dashboard()
    if modo_dashboard() and "analise" not in st.session_state:
        st.session_state["diag_municipio"] = None        # nada aberto: o título espera a escolha do município
    st.session_state["lateral_recolhida"] = True


def _alternar_lateral():
    st.session_state["lateral_recolhida"] = not st.session_state.get("lateral_recolhida", True)


def _ir_para(pagina: str):
    st.session_state["navegacao"] = pagina


def _processar_pelo_icone():
    st.session_state["processar_icone"] = True


# Painel recolhido: só uma coluna de botões-ícone, centralizados (pedido de 27/11/2026 — a versão que escondia
# os controles por CSS deixava caixas e bolinhas de seleção soltas)
CSS_LATERAL_RECOLHIDA = """<style>
    section[data-testid="stSidebar"] { width: 84px !important; min-width: 84px !important; max-width: 84px !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] { overflow-x: hidden; }
    [data-testid="stSidebarHeader"] { display: none; }
    [data-testid="stSidebarUserContent"] { padding: 14px 0 0 0 !important; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .45rem; align-items: center; }
    [data-testid="stSidebar"] [data-testid="stElementContainer"] { width: auto !important; }
    [data-testid="stSidebar"] button { width: 56px !important; min-width: 56px !important; height: 48px;
        min-height: 48px; padding: 0 !important; justify-content: center; }
    [data-testid="stSidebar"] button p { font-size: 1.45rem !important; line-height: 1 !important; margin: 0; }
    [data-testid="stSidebar"] button [data-testid="stIconMaterial"] { display: none; }   /* seta do ⋯ */
    [data-testid="stSidebar"] hr { margin: .2rem 0 !important; width: 44px; }
    [data-testid="stSidebar"] .st-key-rodape_lateral { width: auto !important; }
</style>"""

# Dashboard para TV: letras grandes e tudo numa tela
CSS_DASHBOARD = """<style>
    [data-testid="stMainBlockContainer"] { padding-top: 1.2rem; padding-bottom: 5rem; max-width: 100%; }
    [data-testid="stMainBlockContainer"] p, [data-testid="stMainBlockContainer"] li { font-size: 1.05rem; }
    [data-testid="stMainBlockContainer"] h4 { font-size: 1.35rem; margin: .2rem 0 .3rem; }
    /* título = duas caixas de seleção com cara de título (estado em azul-petróleo, município em preto) */
    .st-key-dash_titulo { gap: 0 !important; max-width: 720px; }
    .st-key-dash_titulo [role="group"] { background: transparent; border: 1px solid transparent; border-radius: 8px;
        min-height: 0; height: auto; padding: 0 4px 0 0; cursor: pointer; }
    .st-key-dash_titulo [role="group"]:hover { border-color: #C9D2C6; background: #F7F8F5; }
    .st-key-dash_titulo input { font-family: "Fira Sans Condensed", sans-serif !important; font-weight: 700 !important;
        padding: 0 !important; height: auto !important; cursor: pointer; text-overflow: ellipsis; }
    .st-key-diag_estado input, .st-key-pan_estado_tv input { font-size: 3rem !important; line-height: 1.1 !important; color: #0D6E7D !important;
        -webkit-text-fill-color: #0D6E7D; letter-spacing: .01em; }
    .st-key-diag_municipio input, .st-key-pan_regiao_tv input { font-size: 2.1rem !important; line-height: 1.15 !important; color: #1D2B23 !important;
        -webkit-text-fill-color: #1D2B23; }
    .st-key-dash_titulo input::placeholder { color: #8A968D; -webkit-text-fill-color: #8A968D; }
    .st-key-dash_titulo button[aria-label="Clear value"] { display: none; }
    .st-key-dash_titulo button[aria-label="Open"] svg { width: 2rem; height: 2rem; color: #6A786E; }
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: 2.3rem !important;
                                                                   line-height: 1.15 !important; }
    [data-testid="stMetricLabel"] p { font-size: 1.05rem !important; }
    [data-testid="stTab"] p { font-size: 1rem; }
    [class*="st-key-cartao_"] button { padding: 0 .5rem; min-height: 2rem; background: #B23A1E; color: #fff;
                                       border: none; }
    [class*="st-key-cartao_"] button p { color: #fff; font-weight: 700; }
</style>"""


def render_header(subtitulo: str = ""):
    col1, col2, col3 = st.columns([2, 4.4, 1.2])
    with col1:
        if config.LOGO_APP.exists():
            st.image(str(config.LOGO_APP), width=210)
    with col2:
        st.markdown(f"""
            <div class="main-header">
                <h2>Corpo de Bombeiros Militar do Pará</h2>
                <h3>Coordenadoria Estadual de Proteção e Defesa Civil</h3>
                <h3>Divisão de Gestão de Risco - DGR</h3>
                <h3>Sala de Informações e Monitoramento de Desastres (SIMD)</h3>
                <h2><b>{config.APP_NOME} v{config.APP_VERSAO}</b></h2>
                <div class="sub">DIAGNÓSTICO AUTOMÁTICO DE FOCOS DE CALOR</div>
                <div class="ref">{subtitulo.upper()}</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        if config.LOGO_CBM_CEDEC.exists():
            st.image(str(config.LOGO_CBM_CEDEC), width=110)
    st.divider()


@st.cache_data(show_spinner=False)
def logo_base64(caminho: str) -> str:
    return base64.b64encode(Path(caminho).read_bytes()).decode()


def render_footer():
    logo = (f'<img class="logo-inicio" title="Ir para a página inicial" alt="AutoSIMD-FOCOS" '
            f'src="data:image/png;base64,{logo_base64(str(config.LOGO_APP))}"/>'
            if config.LOGO_APP.exists() else "")
    st.markdown(f"""
        <div class="footer-container">
            <div style="display:flex;align-items:center;gap:14px">{logo}<div>
            <b>RELATÓRIO AUTOMÁTICO DE FOCOS DE CALOR — ANÁLISE TERRITORIAL</b><br/>
            CBMPA | Coordenadoria Estadual de Proteção e Defesa Civil — DGR / Fonte: BDQueimadas INPE</div></div>
            <div style="text-align: right;">{config.APP_NOME} v{config.APP_VERSAO} © 2026</div>
        </div>
    """, unsafe_allow_html=True)


# Caminhos lidos a cada execução (não fixados na importação) para os testes poderem trocar a pasta
@st.cache_resource(show_spinner="Carregando a base de focos...")
def base_focos(caminho: str) -> pd.DataFrame:
    """Base inteira em memória, compartilhada entre as sessões (somente leitura)."""
    return carregar_focos(caminho)


@st.cache_data(show_spinner=False)
def cobertura(caminho: str):
    return cobertura_base(base_focos(caminho))


def areas_protegidas():
    return carregar_areas_protegidas(config.caminho_uc(), config.caminho_ti())


@st.cache_resource(show_spinner=False, max_entries=4)
def diagnostico(caminho: str, tipo: str, estado: str | None, caminho_estado, nome: str, ano_inicio: int,
                ano_fim: int):
    """Diagnóstico guardado em memória: ajustar as estatísticas ou baixar não refaz o cálculo.

    Devolve ``None`` para UC/TI sem limite na base de polígonos.
    """
    df = base_focos(caminho)
    if tipo == config.TIPO_MUNICIPIO:
        poligono = geometria_municipio(caminho_estado, nome)
        areas = areas_protegidas_no_territorio(poligono, areas_protegidas())
        return diagnosticar_municipio(df, estado, nome, ano_inicio, ano_fim, poligono, areas)
    poligono = geometria_area_protegida(config.SIGLA_TIPO[tipo], nome, areas_protegidas())
    return None if poligono is None else diagnosticar_area(df, tipo, nome, ano_inicio, ano_fim, poligono)


@st.cache_resource(show_spinner=False, max_entries=4)
def nowcast_do_territorio(caminho: str, tipo: str, estado: str | None, nome: str, ultimo_dia, provisorio: bool):
    """Cenário atual: todos os focos do município, UC ou TI na base (todos os anos), até o último dia (P23)."""
    df = base_focos(caminho)
    focos = (focos_do_municipio(df, estado, nome) if tipo == config.TIPO_MUNICIPIO
             else focos_da_area(df, config.SIGLA_TIPO[tipo], nome))
    return nowcast_territorio(focos, nome, ultimo_dia, cobertura(caminho)[0], provisorio)


@st.cache_data(show_spinner=False)
def opcoes_municipios(caminho: str, estado: str) -> list[str]:
    return municipios_da_uf(base_focos(caminho), estado)


@st.cache_data(show_spinner=False)
def opcoes_areas(caminho: str, campo: str) -> list[str]:
    return areas_com_focos(base_focos(caminho), campo)


def limpar_caches_da_base():
    """Depois de gravar focos novos: tudo que veio da base é recalculado."""
    for funcao in (base_focos, cobertura, diagnostico, nowcast_do_territorio, opcoes_municipios, opcoes_areas,
                   opcoes_regioes, panorama_em_cache, figuras_panorama, cenario_em_cache, recorrencia_do_cenario,
                   anomalias_cenario_png):
        funcao.clear()


@st.cache_resource(show_spinner=False)
def obter_atualizador(bases_dir: str) -> AtualizadorFocos:
    """Uma thread de atualização por processo, compartilhada pelas sessões (modelo do AutoSIMD-HIDRO).

    O programa abre com a base local; a busca no INPE acontece em segundo plano.
    """
    atualizador = AtualizadorFocos(Path(bases_dir))
    atualizador.iniciar(buscar_ao_abrir=config.ATUALIZACAO_AUTOMATICA)
    return atualizador


def _ao_mudar_nowcast():
    obter_atualizador(str(config.BASES_DIR)).definir_nowcast(st.session_state["toggle_nowcast"])


def estado_em_analise() -> str:
    """Estado da página aberta (Panorama ou Diagnóstico); o vento é buscado só para ele (P40)."""
    if st.session_state.get("navegacao") == PAGINA_DIAGNOSTICO:
        return st.session_state.get("diag_estado") or "Pará"
    return st.session_state.get("pan_estado") or "Pará"


def _ao_mudar_vento():
    obter_atualizador(str(config.BASES_DIR)).definir_vento(st.session_state["toggle_vento"], estado_em_analise())


def acompanhar_estado_do_vento():
    """Com o vento ligado, trocar de estado na página passa a buscar o vento do estado novo."""
    chave = chave_vento(config.BASES_DIR)
    if chave["ligado"] and chave["estado"] != estado_em_analise():
        obter_atualizador(str(config.BASES_DIR)).definir_vento(True, estado_em_analise())


SEGUNDOS_ABERTO_DEPOIS = 5


@st.fragment(run_every=2)
def painel_atualizacao(recarregar_ao_mudar: bool, compacto: bool = False):
    """Situação da base e da busca no INPE (barra lateral); reexecuta sozinho a cada 5 s.

    Quando a base muda, os dados em memória são descartados; no Panorama e em Bases de dados a página
    recarrega; no Diagnóstico só avisa, para não apagar a análise aberta. Numa execução da página
    inteira (clique num botão, por exemplo) a página já vem logo depois do painel com a base nova:
    recarregar de novo descartaria o clique.
    """
    atualizador = obter_atualizador(str(config.BASES_DIR))
    estado = atualizador.instantaneo()
    versao = versao_da_base(config.BASES_DIR)
    vista = st.session_state.setdefault("versao_base_vista", versao)
    if versao != vista and not estado["em_execucao"]:
        st.session_state["versao_base_vista"] = versao
        limpar_caches_da_base()
        contexto = get_script_run_ctx()
        if recarregar_ao_mudar and contexto is not None and contexto.fragment_ids_this_run:
            st.rerun(scope="app")
        st.toast("🛰️ Focos novos incorporados à base — valem para a próxima análise processada.")

    # aberto durante a busca e por 5 s depois dela; recolhido no resto do tempo (o rótulo muda para o
    # Streamlit tratar como outro bloco e respeitar o "expanded")
    # os 5 s contam de quando esta tela mostra o fim da busca (o recálculo da página pode demorar mais que isso)
    if estado["em_execucao"]:
        st.session_state["base_aberta_ate"] = None
    elif "base_aberta_ate" in st.session_state and st.session_state["base_aberta_ate"] is None:
        st.session_state["base_aberta_ate"] = datetime.now() + timedelta(seconds=SEGUNDOS_ABERTO_DEPOIS)
    ate = st.session_state.get("base_aberta_ate")
    recem = ate is not None and datetime.now() < ate
    if estado["em_execucao"]:
        rotulo, aberto = "⏳ Atualizando a base de focos (INPE)…", True
    elif recem:
        rotulo, aberto = "✅ Base de focos atualizada", True
    else:
        rotulo, aberto = "⋯  Base de focos (INPE) e sobre o sistema", False
    if compacto:      # painel recolhido: o mesmo conteúdo num balão aberto pelo ícone
        with st.popover(rotulo.split(" ", 1)[0], help=rotulo.split(" ", 1)[1].strip()):
            conteudo_base(atualizador, estado)
            st.divider()
            conteudo_sobre()
        return
    with st.expander(rotulo, expanded=aberto):
        conteudo_base(atualizador, estado)
        st.divider()
        conteudo_sobre()


def conteudo_base(atualizador, estado):
    st.markdown("**🛰️ Base de focos (INPE)**")
    situacao = situacao_da_base(config.BASES_DIR)
    if situacao["ultimo_dia"]:
        texto = f"Dados até **{situacao['ultimo_dia']:%d/%m/%Y}**"
        if situacao["ultimo_dia"] in situacao["provisorios"]:
            texto += " (dia ainda parcial)"
        st.markdown(texto)
    if estado["em_execucao"]:
        st.caption(f"⏳ {estado['etapa']} — busca iniciada às {estado['inicio']:%H:%M} ({estado['gatilho']}). "
                   "Pode continuar usando o programa.")
    else:
        resultado = estado["ultimo_resultado"]
        if resultado is not None:
            icone = "✅" if resultado.situacao in ("atualizada", "em_dia") else "⚠️"
            st.caption(f"{icone} {estado['ultimo_fim']:%H:%M} — {resultado.mensagem}")
        elif situacao["ultima_busca"]:
            st.caption(f"Última busca no INPE: {situacao['ultima_busca'].astimezone():%d/%m/%Y %H:%M}")
        if estado["proxima"]:
            st.caption(f"Próxima busca: {estado['proxima']:%d/%m %H:%M}")
    chave = chave_vento(config.BASES_DIR)
    st.toggle("Vento (Open-Meteo)", value=chave["ligado"], key="toggle_vento", on_change=_ao_mudar_vento,
              help="Ligado: junto com cada busca de focos, busca o vento a 10 m (atual e próximas 48 h) nas "
                   "quadrículas de 0,25° com foco na última semana do estado em análise. A escolha fica salva.")
    if chave["ligado"] and estado.get("vento"):
        st.caption(estado["vento"])
    st.toggle(f"Nowcast (busca a cada {CICLO_NOWCAST_H} h)", value=atualizador.nowcast, key="toggle_nowcast",
              on_change=_ao_mudar_nowcast,
              help=f"Ligado: busca focos novos no INPE agora e depois a cada {CICLO_NOWCAST_H} horas, em segundo "
                   "plano. Desligado: só a busca de quando o programa abre. A escolha fica salva.")


def mostrar_figura(figura, coluna=st, cache: dict | None = None):
    """``cache`` = figuras do diagnóstico guardadas na sessão: a imagem é gerada uma vez só."""
    if figura is None:
        return
    if isinstance(figura, bytes):                 # PNG já pronto (mapas guardados do Panorama)
        coluna.image(figura, width="stretch")
        return
    if cache is None:
        coluna.pyplot(figura, width="stretch")
        return
    pngs = cache["png"]
    if id(figura) not in pngs:
        pngs[id(figura)] = png(figura, dpi=110)
    coluna.image(pngs[id(figura)], width="stretch")


def cache_do_diagnostico(chave_figuras: tuple) -> dict:
    """Figuras, imagens e pacote do diagnóstico aberto, guardados na sessão: mexer em qualquer controle da
    página não refaz nada; trocar de território, período, base ou parâmetros do relatório refaz."""
    cache = st.session_state.get("figuras_cache")
    if not cache or cache["chave"] != chave_figuras:
        if cache:
            fechar_figuras({f"{e}_{k}": f for e, figs in cache["etapas"].items() for k, f in figs.items()})
        cache = {"chave": chave_figuras, "etapas": {}, "png": {}, "pacote": None, "mapas_recentes": {}}
        st.session_state["figuras_cache"] = cache
    return cache


def figuras_etapa(cache: dict, etapa: str, diag, est, nowcast, texto: str) -> dict:
    if etapa not in cache["etapas"]:
        with st.spinner(texto):
            cache["etapas"][etapa] = figuras_da_etapa(etapa, diag, est, nowcast)
    return cache["etapas"][etapa]


def todas_as_figuras(cache: dict, diag, est, nowcast) -> dict:
    figuras = {}
    for etapa in ETAPAS_FIGURAS:
        figuras.update(figuras_etapa(cache, etapa, diag, est, nowcast, "Gerando as figuras do relatório..."))
    return figuras


COLUNA_MUNICIPIO = "Município"
PREFIXO_TABELA_MUNICIPIO = "tab_mun_"
PREFIXO_TABELA_MAPA = "tab_mapa_"        # dois cliques numa linha = centralizar o mapa nela

# Duplo clique no nome de um município, em qualquer tabela marcada por ``tabela(..., chave=, estado=)``: o
# script lê o texto da célula selecionada (a tabela de acessibilidade do st.dataframe) e o nome da coluna.
_JS_DUPLO_CLIQUE = """
export default function(componente) {
    const { setTriggerValue } = componente;
    const aoDuploClique = (evento) => {
        const caixa = evento.target.closest('[class*="st-key-%s"], [class*="st-key-%s"]');
        if (!caixa) return;
        const chave = [...caixa.classList].find((c) => c.startsWith('st-key-')).slice(7);
        setTimeout(() => {      // a célula selecionada só é marcada depois do clique
            const celula = caixa.querySelector('td[aria-selected="true"]');
            if (!celula) return;
            const cabecalho = celula.closest('table')?.querySelector(
                'th[aria-colindex="' + celula.getAttribute('aria-colindex') + '"]');
            setTriggerValue('duplo', {chave, coluna: cabecalho ? cabecalho.textContent : null,
                                      texto: celula.textContent, t: Date.now()});
        }, 300);
    };
    const aoClicar = (evento) => {          // logo do rodapé = página inicial (sem recarregar a página)
        if (evento.target.closest('.logo-inicio')) setTriggerValue('inicio', Date.now());
    };
    document.addEventListener('dblclick', aoDuploClique, true);
    document.addEventListener('click', aoClicar, true);
    return () => {
        document.removeEventListener('dblclick', aoDuploClique, true);
        document.removeEventListener('click', aoClicar, true);
    };
}
""" % (PREFIXO_TABELA_MUNICIPIO, PREFIXO_TABELA_MAPA)
_ouvinte_duplo_clique = st.components.v2.component("duplo_clique_tabela", js=_JS_DUPLO_CLIQUE)


def _ao_duplo_clique():
    clique = (st.session_state.get("ouvinte_tabelas") or {}).get("duplo") or {}
    chave, texto = str(clique.get("chave") or ""), str(clique.get("texto") or "").strip()
    if chave.startswith(PREFIXO_TABELA_MAPA):
        alvos = st.session_state.get("alvos_do_mapa", {}).get(chave.removeprefix(PREFIXO_TABELA_MAPA), {})
        if (clique.get("coluna"), texto) in alvos:
            st.session_state["alvo_mapa"] = alvos[(clique.get("coluna"), texto)]
        return
    estado = st.session_state.get("tabelas_municipio", {}).get(chave.removeprefix(PREFIXO_TABELA_MUNICIPIO))
    if clique.get("coluna") == COLUNA_MUNICIPIO and texto and estado:
        abrir_diagnostico(texto, estado)


def _ao_clicar_no_logo():
    st.session_state["navegacao"] = PAGINA_INICIAL


def ouvinte_duplo_clique():
    _ouvinte_duplo_clique(key="ouvinte_tabelas", on_duplo_change=_ao_duplo_clique,
                          on_inicio_change=_ao_clicar_no_logo)


def tabela_que_aponta_no_mapa(df: pd.DataFrame, chave: str, alvos: dict, **kwargs):
    """Dois cliques numa célula da coluna-chave (ex.: o nome da localidade) centralizam o mapa nela.
    ``alvos`` = {(coluna, texto da célula): (lon, lat)}."""
    st.session_state.setdefault("alvos_do_mapa", {})[chave] = alvos
    with st.container(key=PREFIXO_TABELA_MAPA + chave):
        st.dataframe(df, hide_index=True, width="stretch", **kwargs)


def tabela(df, chave: str | None = None, estado: str | None = None, **kwargs):
    """``chave`` + ``estado``: dois cliques no nome de um município abrem o diagnóstico dele."""
    dados = getattr(df, "data", df)                     # Styler → DataFrame
    if chave and estado and COLUNA_MUNICIPIO in dados.columns:
        st.session_state.setdefault("tabelas_municipio", {})[chave] = estado
        with st.container(key=PREFIXO_TABELA_MUNICIPIO + chave):
            st.dataframe(df, hide_index=True, width="stretch", **kwargs)
    else:
        st.dataframe(df, hide_index=True, width="stretch", **kwargs)


COR_RECORDE = "background-color: #B71C1C; color: white; font-weight: bold"


def tabela_com_recordes(df: pd.DataFrame, recordes: pd.DataFrame | None, anos: tuple[int, int] | None,
                        altura: int | None = None, chave: str | None = None, estado: str | None = None):
    """Tabela com as células acima da máxima histórica (mesmas datas dos anos anteriores) em vermelho."""
    extra = {"height": altura} if altura else {}
    extra.update(chave=chave, estado=estado)
    if recordes is None or df.empty or not recordes.to_numpy().any():
        tabela(df, **extra)
        if recordes is not None and anos:
            st.caption(f"Nenhum valor acima da máxima histórica das mesmas datas ({anos[0]}–{anos[1]}).")
        return
    cores = pd.DataFrame(np.where(recordes.to_numpy(dtype=bool), COR_RECORDE, ""), index=df.index, columns=df.columns)
    estilo = df.style.apply(lambda _: cores, axis=None)
    tabela(estilo.format({c: fmt_numero for c in df.select_dtypes("number").columns if "%" not in c})
           .format({c: lambda v: fmt_numero(v, 1) for c in df.columns if "%" in c}), **extra)
    st.markdown(f'<span style="background:#B71C1C;color:white;padding:1px 6px;font-weight:bold">valor</span> '
                f"acima da máxima histórica das mesmas datas em {anos[0]}–{anos[1]} (ano até a data, último mês e "
                "última semana).", unsafe_allow_html=True)


def disparar_download_automatico(conteudo: bytes, nome: str):
    """Inicia o download no navegador sem clique (opção da barra lateral)."""
    b64 = base64.b64encode(conteudo).decode()
    components.html(f"""
        <script>
            var a = document.createElement('a');
            a.href = 'data:application/zip;base64,{b64}';
            a.download = '{nome}';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        </script>
    """, height=0, width=0)


def botao_pacote(pacote_, rotulo: str, ajuda: str | None = None, chave: str = "botao_pacote"):
    st.download_button(rotulo, pacote_.conteudo, file_name=pacote_.nome, mime="application/zip", type="primary",
                       width="stretch", on_click="ignore", help=ajuda, key=chave)


def rankings_areas(diag):
    """UCs e TIs com focos no estado e no Brasil inteiro, no período (P6)."""
    formato = {"Focos de Calor": st.column_config.NumberColumn(format="%d"),
               "Participação (%)": st.column_config.NumberColumn(format="%.2f %%")}
    estado = diag.estado if isinstance(diag, DiagnosticoMunicipio) else (diag.sigla_uf or "—")
    st.divider()
    st.markdown("### 🏆 Ranking de Focos por Áreas Protegidas")
    st.caption("Ordem: mais focos no período; empate decidido pelos focos no último mês e, depois, na última "
               "semana dos dados.")
    abas = st.tabs([f"🌲 UCs no estado ({estado})", "🌲 UCs no Brasil", f"🏹 TIs no estado ({estado})",
                    "🏹 TIs no Brasil"])
    for aba, chave, vazio in zip(abas, ("UC_estado", "UC_brasil", "TI_estado", "TI_brasil"),
                                 ("Unidades de Conservação do estado", "Unidades de Conservação",
                                  "Terras Indígenas do estado", "Terras Indígenas")):
        with aba:
            ranking = diag.rankings_areas[chave]
            if ranking.empty:
                st.info(f"Nenhum foco registrado em {vazio} no período selecionado.")
            else:
                tabela(ranking, column_config=formato)


# ------------------------------------------------------------ Barra lateral

def parametros_analise(df: pd.DataFrame) -> dict | None:
    """Controles da barra lateral; None se faltar base de municípios.

    No dashboard, estado e município são escolhidos no título do painel (``titulo_dashboard``); com o painel
    recolhido, nada daqui é desenhado e os valores vêm da sessão (ver ``CHAVES_DO_PAINEL``)."""
    caminho = str(config.caminho_focos())
    no_titulo, recolhida = dashboard_ativo(), lateral_recolhida()
    ss = st.session_state
    if recolhida:
        tipo = config.TIPO_MUNICIPIO
    else:
        st.sidebar.button("📄 Visualização legado" if modo_dashboard() else "📺 Visualização dashboard",
                          key="botao_modo", on_click=_alternar_modo, width="stretch",
                          help="Diagnóstico de município em painel único (para TV) ou na visualização de sempre, "
                               "em abas.")
        st.sidebar.title("🛠️ Parâmetros da Análise")
        tipo = st.sidebar.radio("🎯 Escolha o Nível de Análise:", config.TIPOS_ANALISE, key="diag_tipo")
    p = {"tipo": tipo, "estado": None, "caminho_estado": None}

    if tipo == config.TIPO_MUNICIPIO:
        estados = estados_disponiveis()
        if not estados:
            st.sidebar.error(f"Nenhum arquivo GeoJSON de estado encontrado em {config.pasta_municipios()}.")
            return None
        nomes_estados = list(estados)
        if ss.get("diag_estado") not in estados:     # padrão Pará (o clique no mapa também escolhe)
            ss["diag_estado"] = "Pará" if "Pará" in estados else nomes_estados[0]
        if no_titulo:
            p["estado"] = ss["diag_estado"]
        else:
            p["estado"] = st.sidebar.selectbox("Selecione o Estado (UF):", nomes_estados, key="diag_estado")
        p["caminho_estado"] = estados[p["estado"]]
        municipios = opcoes_municipios(caminho, p["estado"])
        if no_titulo:
            if ss.get("diag_municipio") not in municipios:
                ss["diag_municipio"] = None          # aguardando a escolha no título
            p["nome"] = ss["diag_municipio"]
            if not recolhida:
                st.sidebar.caption("📍 Estado e município: escolha no título do painel.")
        else:
            if ss.get("diag_municipio") not in (municipios or ["SELECIONE"]):
                ss.pop("diag_municipio", None)      # outro estado: volta ao primeiro município
            p["nome"] = st.sidebar.selectbox("📍 Selecione o Município:", municipios or ["SELECIONE"],
                                             key="diag_municipio")
    else:
        texto = ("🌲 Selecione a Unidade de Conservação (UC):" if tipo == config.TIPO_UC
                 else "🏹 Selecione a Terra Indígena (TI):")
        p["nome"] = st.sidebar.selectbox(texto, opcoes_areas(caminho, config.SIGLA_TIPO[tipo]),
                                         key="diag_area") or "SELECIONE"

    anos = anos_disponiveis(df)
    faixa = ss.get("diag_anos")
    if not faixa or faixa[0] < anos[0] or faixa[1] > anos[-1] or faixa[0] > faixa[1]:
        ss["diag_anos"] = (anos[0], anos[-1])
    ss.setdefault("diag_download", True)
    if recolhida:
        p["ano_inicio"], p["ano_fim"] = ss["diag_anos"]
        p["download_automatico"] = ss["diag_download"]
        p["processar"] = ss.pop("processar_icone", False)
    else:
        p["ano_inicio"], p["ano_fim"] = st.sidebar.slider("📅 Intervalo de Anos:", min_value=anos[0],
                                                          max_value=anos[-1], step=1, key="diag_anos")
        st.sidebar.divider()
        st.sidebar.subheader("Opções de Download")
        p["download_automatico"] = st.sidebar.checkbox(
            "Baixar automaticamente o pacote completo (Relatório PDF, Metadados e Imagens PNG)", key="diag_download")
        p["processar"] = st.sidebar.button("🚀 Processar Diagnóstico Completo", type="primary", width="stretch")
    if ss.pop("processar_pelo_mapa", False):     # clique no mapa, dois cliques na tabela ou escolha no título
        p["processar"], p["download_automatico"] = True, False
    if not p.get("nome"):
        p["processar"] = False
    return p


def conteudo_sobre():
    st.markdown("**ℹ️ Sobre o Sistema & Desenvolvedor**")
    if True:
        st.markdown(f"**{config.APP_NOME}** `v{config.APP_VERSAO}` — {config.APP_VERSAO_DATA}")
        st.caption("Diagnóstico Territorial de Focos de Calor")
        funcoes = "\n".join(f"* {f}" for f in config.DESENVOLVEDOR_FUNCOES)
        st.markdown(f"""
**Desenvolvedor:**
**{config.DESENVOLVEDOR_NOME}**

{funcoes}

---
📧 **Contato:** [{config.DESENVOLVEDOR_EMAIL}](mailto:{config.DESENVOLVEDOR_EMAIL})
📜 **Lattes:** [Currículo Lattes]({config.DESENVOLVEDOR_LATTES})
🐙 **GitHub:** [Autosimd-Focos]({config.REPOSITORIO})
""")
        st.caption("Código desenvolvido com auxílio de Inteligência Artificial, com revisão e testes da "
                   "equipe técnica da CEDEC/PA.")


# ------------------------------------------------------------ Resumo executivo

def resumo_municipio(diag, p: dict):
    r, ano_inicio, ano_fim = diag.resumo, diag.ano_inicio, diag.ano_fim
    st.markdown(f"### 📌 Resumo Executivo — {diag.nome} ({ano_inicio} a {ano_fim})")
    k1, k2, k3 = st.columns(3)
    k1.metric(f"Focos em {ano_fim}", fmt_inteiro(r.focos_ano_fim),
              help=f"Total de focos de calor detectados no município em {ano_fim}.")
    k2.metric(f"Posição no país — {ano_fim}", fmt_posicao(r.posicao_pais, r.total_pais),
              help=f"Posição do município entre todos os municípios do Brasil com focos em {ano_fim}. "
                   "Municípios de mesmo nome em estados diferentes são contados separadamente; no empate, "
                   "vence quem teve mais focos no último mês e, depois, na última semana.")
    k3.metric(f"Posição no estado — {ano_fim}", fmt_posicao(r.posicao_estado, r.total_estado),
              help=f"Posição do município entre os municípios do estado ({p['estado']}) considerando apenas "
                   f"os focos de {ano_fim}.")
    k4, k5, k6 = st.columns(3)
    k4.metric(f"Participação no total do estado ({ano_fim})", fmt_percentual(r.participacao_estado_pct),
              help=f"Percentual dos focos do estado ({p['estado']}) em {ano_fim} que ocorreram neste município.")
    k5.metric(f"Variação {ano_fim} vs. {ano_fim - 1}", fmt_percentual(r.variacao_pct, sinal=True),
              help=f"Variação percentual dos focos do município em {ano_fim} em relação a {ano_fim - 1}. "
                   "Exibe '—' sem ano anterior no período ou com zero focos nele.")
    area = f"({fmt_numero(r.area_km2)} km²)." if r.area_km2 else "(área indisponível)."
    k6.metric("Densidade média anual (focos/km²/ano)", fmt_densidade(r.densidade),
              help=f"Média anual de focos no município ({fmt_numero(r.media_anual, 1)} focos/ano em "
                   f"{ano_inicio}–{ano_fim}) dividida pela área do polígono {area}")


def resumo_area(diag):
    ano_fim, campo = diag.ano_fim, diag.campo
    rotulo = config.TIPO_UC if campo == "UC" else config.TIPO_TI

    def posicao(chave):
        tabela_ = diag.rankings_areas[chave]
        linha = tabela_[tabela_[rotulo] == diag.nome]
        return fmt_posicao(int(linha["Posição"].iloc[0]), len(tabela_)) if len(linha) else "Sem focos"
    area = area_km2(diag.poligono)
    st.markdown(f"### 📌 Resumo da Análise ({diag.ano_inicio} - {ano_fim})")
    k1, k2, k3 = st.columns(3)
    k1.metric(f"Focos em {ano_fim}", fmt_inteiro(diag.focos_ano_fim))
    k2.metric("Total no Período", fmt_inteiro(diag.focos_periodo))
    k3.metric("Média Anual", fmt_inteiro(round(diag.media_anual)))
    k4, k5, k6 = st.columns(3)
    k4.metric(f"Posição entre as {campo}s do estado ({diag.sigla_uf or '—'})", posicao(f"{campo}_estado"),
              help="No período, entre as áreas do mesmo tipo com focos no estado com mais focos desta área.")
    k5.metric(f"Posição entre as {campo}s do Brasil", posicao(f"{campo}_brasil"))
    k6.metric("Densidade média anual (focos/km²/ano)", fmt_densidade(diag.media_anual / area if area else None),
              help=f"Média anual de focos dividida pela área da {campo} ({fmt_numero(area or 0)} km²).")


# ------------------------------------------------------------ Diagnóstico

def mostrar_territorio(df: pd.DataFrame, p: dict):
    """Diagnóstico completo de um município, UC ou TI."""
    caminho = str(config.caminho_focos())
    municipio = p["tipo"] == config.TIPO_MUNICIPIO
    with st.spinner("Processando geodados, sazonalidade e gerando mapas..."):
        diag = diagnostico(caminho, p["tipo"], p["estado"], p["caminho_estado"], p["nome"], p["ano_inicio"],
                           p["ano_fim"])
    if diag is None:
        st.error("Não foi possível obter a geometria do território selecionado.")
        return
    chave = chave_analise(p)
    situacao = situacao_da_base(config.BASES_DIR)
    nowcast = None
    if situacao["ultimo_dia"]:
        nowcast = nowcast_do_territorio(caminho, p["tipo"], p["estado"], diag.municipio, situacao["ultimo_dia"],
                                        situacao["ultimo_dia"] in situacao["provisorios"])
    with st.spinner("Calculando as estatísticas..."):
        est = estatisticas_territorio(diag.focos, diag.municipio, diag.ano_inicio, diag.ano_fim, cobertura(caminho),
                                      parametros_do_relatorio(chave))
    cache = cache_do_diagnostico((chave, situacao["ultimo_dia"], versao_da_base(config.BASES_DIR),
                                  repr(parametros_do_relatorio(chave))))
    if diag.poligono is None:
        st.warning(f"Limite de {diag.nome} não encontrado: mapas sem contorno e densidade indisponível.", icon="🗺️")

    if municipio and modo_dashboard():
        mostrar_dashboard(df, p, diag, est, nowcast, cache, situacao, chave)
        if lateral_recolhida():
            with st.sidebar:
                exportar_pacote(df, diag, cache, est, nowcast, situacao, municipio, modo="icone")
        return

    nomes = ["Resumo", "Cenário atual", "Gráficos e rankings", "Mapas", "Anomalias",
             "Áreas protegidas", "Estatísticas (modelo INPE)", "Metodologia"]
    if municipio:
        nomes.append("Vulnerabilidade (protótipo)")
    abas = st.tabs(nomes)
    with abas[0]:
        if municipio:
            resumo_municipio(diag, p)
        else:
            resumo_area(diag)
        st.markdown("#### 🧭 Localização")
        figuras = figuras_etapa(cache, "resumo", diag, est, nowcast, "Desenhando o mapa de localização...")
        mostrar_figura(figuras["localizacao"], st.columns([3, 1])[0], cache)
    with abas[1]:
        if nowcast is None:
            st.info("Sem dados recentes da base para o cenário atual.")
        else:
            secao_nowcast(diag, nowcast)
    with abas[2]:
        figuras = figuras_etapa(cache, "graficos", diag, est, nowcast, "Gerando os gráficos...")
        st.markdown("### 📈 Diagnóstico Geral e Análise de Sazonalidade")
        if municipio:
            g1, g2 = st.columns(2)
            mostrar_figura(figuras["top_estado"], g1, cache)
            mostrar_figura(figuras["evolucao"], g2, cache)
        else:
            mostrar_figura(figuras["evolucao"], st.columns([1, 1])[0], cache)
        st.markdown("#### 🗓️ Padrão Sazonal de Incidência (média mensal, p10–p90 e ano de referência)")
        mostrar_figura(figuras["sazonalidade"], cache=cache)

        if municipio:
            st.markdown("### 📋 Tabelas de Ranking e Comparativo Regional")
            t1, t2 = st.columns(2)
            with t1:
                st.markdown(f"**Top {len(diag.ranking_estado)} {diag.ano_fim} - Estado**")
                tabela(diag.ranking_estado, chave="diag_estado", estado=diag.estado)
            with t2:
                st.markdown(f"**Comparativo na {diag.titulo_regiao} ({diag.ano_fim})**")
                if diag.ranking_regiao.empty:
                    st.caption("Região do município não identificada.")
                else:
                    tabela(diag.ranking_regiao, chave="diag_regiao", estado=diag.estado)
    with abas[3]:
        figuras = figuras_etapa(cache, "mapas", diag, est, nowcast, "Desenhando os mapas...")
        st.markdown("### 🗺️ Mapeamento Espacial e Sazonalidade Trimestral")
        st.caption(f"Mapas 1, 2 e 4: densidade de kernel gaussiano (desvio de {fmt_numero(DESVIO_KERNEL_KM)} km); "
                   "cada foco marcado com uma cruz preta.")
        mostrar_figura(figuras["mapa_dispersao"], cache=cache)
        if municipio:
            if diag.areas:
                st.markdown("**🌲 Unidades de Conservação e Terras Indígenas no Município**")
                tabela(diag.tabela_areas)
            else:
                st.caption("Nenhuma Unidade de Conservação ou Terra Indígena da base sobreposta a este município.")
        mostrar_figura(figuras["mapa_densidade"], cache=cache)
        mostrar_figura(figuras["mapa_recorrencia"], cache=cache)
        if figuras["mapa_trimestral"] is not None:
            st.markdown("#### 🔄 Migração Espacial Sazonal (densidade de kernel por trimestre)")
            mostrar_figura(figuras["mapa_trimestral"], cache=cache)
    with abas[4]:
        figuras = figuras_etapa(cache, "anomalias", diag, est, nowcast, "Calculando as anomalias...")
        mostrar_anomalias({tipo: figuras.get(f"anomalia_{tipo}") for tipo in TIPOS_ANOMALIA}, diag.municipio,
                          cache)
    with abas[5]:
        rankings_areas(diag)
    with abas[6]:
        secao_estatisticas(diag.focos, diag.municipio, diag.ano_inicio, diag.ano_fim, chave)
    with abas[7]:
        st.markdown("### 📐 Síntese Espacial e Metodologia")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**Parâmetros Técnicos e Operacionais**")
            grade = nota_grade(grade_do_territorio(diag.poligono.bounds)) if diag.poligono is not None else "—"
            focos_ano = diag.focos[diag.focos["ano"] == diag.ano_fim]
            tabela(pd.DataFrame([
                {"Parâmetro": "Ocorrências Ano Atual",
                 "Diagnóstico": f"{fmt_inteiro(len(focos_ano))} focos mapeados em {diag.ano_fim}"},
                {"Parâmetro": "Acumulado Histórico",
                 "Diagnóstico": f"{fmt_inteiro(len(diag.focos))} focos ({diag.ano_inicio}-{diag.ano_fim})"},
                {"Parâmetro": "Grade Geospacial", "Diagnóstico": grade},
                {"Parâmetro": "Densidade de kernel", "Diagnóstico": f"Gaussiano, desvio de {fmt_numero(DESVIO_KERNEL_KM)} km"},
                {"Parâmetro": "Aplicação Operacional", "Diagnóstico": "Definição de rotas de sobrevoo e bases de combate"},
            ]))
        with s2:
            st.markdown("**Nota Metodológica Oficial**")
            st.info(NOTA_METODOLOGICA)

    if municipio:
        with abas[8]:
            secao_vulnerabilidade(df, diag, situacao)
    with st.sidebar, st.container(border=True):
        exportar_pacote(df, diag, cache, est, nowcast, situacao, municipio)


def _proximo_mapa(nome: str, total: int):
    st.session_state[f"dash_{nome}"] = (st.session_state.get(f"dash_{nome}", 0) + 1) % total


def cartao_de_mapa(nome: str, opcoes: list[tuple[str, object]], cache: dict, vazio: str = ""):
    """Cartão com um mapa; o botão no canto alterna entre os mapas do mesmo tipo."""
    opcoes = [(titulo, figura) for titulo, figura in opcoes if figura is not None]
    if not opcoes:
        if vazio:
            with st.container(border=True, key=f"cartao_{nome}"):
                st.caption(vazio)
        return
    atual = st.session_state.get(f"dash_{nome}", 0) % len(opcoes)
    with st.container(border=True, key=f"cartao_{nome}"):
        c_titulo, c_botao = st.columns([5, 1], vertical_alignment="center")
        c_titulo.markdown(f"**{opcoes[atual][0]}**")
        if len(opcoes) > 1:
            c_botao.button("⇄", key=f"botao_{nome}", on_click=_proximo_mapa, args=(nome, len(opcoes)),
                           help=f"Ver: {opcoes[(atual + 1) % len(opcoes)][0]}", width="stretch")
        mostrar_figura(opcoes[atual][1], cache=cache)


def _ao_escolher_estado():
    st.session_state["diag_municipio"] = None        # lista nova; espera a escolha do município


def _ao_escolher_municipio():
    if st.session_state.get("diag_municipio"):
        st.session_state["processar_pelo_mapa"] = True   # abre o diagnóstico do município escolhido


def titulo_dashboard(legenda: str = ""):
    """Título do dashboard ("PARÁ: / Oriximiná") feito de duas caixas de seleção (pedido de 27/11/2026): trocar o
    estado carrega os municípios dele e espera; escolher o município processa o diagnóstico."""
    estado = st.session_state["diag_estado"]
    with st.container(key="dash_titulo"):
        st.selectbox("Estado", list(estados_disponiveis()), key="diag_estado", on_change=_ao_escolher_estado,
                     format_func=lambda e: f"{e.upper()}:", label_visibility="collapsed")
        st.selectbox("Município", opcoes_municipios(str(config.caminho_focos()), estado), key="diag_municipio",
                     index=None, placeholder="Escolha o município…", format_func=nome_proprio,
                     on_change=_ao_escolher_municipio, label_visibility="collapsed")
        if legenda:
            st.caption(legenda)


def mostrar_dashboard(df, p: dict, diag, est, nowcast, cache: dict, situacao: dict, chave: tuple):
    """Diagnóstico de município num painel só, para TV (modelo do usuário, 27/11/2026).

    Esquerda: localização + estado/município, sazonalidade, estatísticas (interativas), comparativo da região.
    Direita: resumo executivo, mapas (densidade ⇄ ano ⇄ trimestres, recorrência, anomalias ⇄ tipos),
    mapa da vulnerabilidade (busca ao vivo sozinha, com a porcentagem) e localidades por risco.
    As partes aparecem na ordem em que ficam prontas."""
    esquerda, direita = st.columns([1, 1.5], gap="medium")
    with esquerda:
        figuras = figuras_etapa(cache, "resumo", diag, est, nowcast, "Desenhando a localização...")
        c_mapa, c_titulo = st.columns([1, 1.9], vertical_alignment="center")
        mostrar_figura(figuras["localizacao"], c_mapa, cache)
        with c_titulo:
            titulo_dashboard(f"{diag.ano_inicio}–{diag.ano_fim} · dados até {situacao['ultimo_dia']:%d/%m/%Y}"
                             if situacao["ultimo_dia"] else f"{diag.ano_inicio}–{diag.ano_fim}")
    with direita:
        resumo_municipio(diag, p)
    with esquerda:
        graficos = figuras_etapa(cache, "graficos", diag, est, nowcast, "Gerando os gráficos...")
        with st.container(border=True):
            mostrar_figura(graficos["sazonalidade"], cache=cache)
    with direita:
        mapas = figuras_etapa(cache, "mapas", diag, est, nowcast, "Desenhando os mapas...")
        anomalias = figuras_etapa(cache, "anomalias", diag, est, nowcast, "Calculando as anomalias...")
        densidade = [("Densidade acumulada", mapas["mapa_densidade"]),
                     (f"Densidade em {diag.ano_fim}", mapas["mapa_dispersao"]),
                     ("Densidade por trimestre", mapas["mapa_trimestral"])]
        tipos_anomalia = [(f"Anomalia — {t}", anomalias.get(f"anomalia_{tipo}"))
                          for t, tipo in zip(("quantidade", "localização", "combinada"), TIPOS_ANOMALIA)]
        validos = [d for d in densidade if d[1] is not None]
        trimestral = validos and validos[st.session_state.get("dash_densidade", 0) % len(validos)][0].endswith(
            "trimestre")
        if trimestral:            # o mapa por trimestre ocupa a linha toda; os outros dois vão embaixo
            cartao_de_mapa("densidade", densidade, cache)
            c1, c2 = st.columns(2)
        else:
            c0, c1, c2 = st.columns(3)
            with c0:
                cartao_de_mapa("densidade", densidade, cache)
        with c1:
            cartao_de_mapa("recorrencia", [("Recorrência", mapas["mapa_recorrencia"])], cache)
        with c2:
            cartao_de_mapa("anomalia", tipos_anomalia, cache,
                           "Anomalias indisponíveis: são precisos pelo menos 3 anos completos de referência no "
                           "período.")
    with esquerda:
        with st.container(border=True):
            secao_estatisticas(diag.focos, diag.municipio, diag.ano_inicio, diag.ano_fim, chave, compacto=True)
        st.markdown(f"#### Comparativo na {diag.titulo_regiao} ({diag.ano_fim})")
        if diag.ranking_regiao.empty:
            st.caption("Região do município não identificada.")
        else:
            tabela(diag.ranking_regiao, chave="diag_regiao", estado=diag.estado, height=390)
    with direita:
        secao_vulnerabilidade(df, diag, situacao, dashboard=True)
    with esquerda, st.container(border=True, key="dash_downloads"):     # a caixa vermelha do modelo
        exportar_pacote(df, diag, cache, est, nowcast, situacao, True, modo="caixa")


def pacote_do_diagnostico(df, diag, cache, est, nowcast, situacao: dict, municipio: bool):
    """Pacote do diagnóstico, montado uma vez por análise; None enquanto os dados ao vivo da vulnerabilidade
    ainda chegam (o boletim vai anexado ao PDF completo e solto no pacote — pedido de 27/11/2026)."""
    vulnerabilidade, marca = None, "sem vulnerabilidade"
    if municipio:
        dados = dados_vulnerabilidade(df, diag, situacao)
        if "erro" not in dados:
            if dados["carregando"]:
                return None
            vulnerabilidade = {"analise": dados["analise"], "municipio": diag.municipio, "estado": diag.estado,
                               "municipio_geom": diag.poligono, "ao_vivo": dados["ao_vivo"],
                               "ultimo_dia_base": situacao["ultimo_dia"], "fundo": config.FUNDO_SATELITE}
            marca = dados["marca"]
    if cache["pacote"] is None or cache["pacote"][0] != marca:
        figuras = todas_as_figuras(cache, diag, est, nowcast)
        with st.spinner("Montando os relatórios PDF e o pacote..."):
            cache["pacote"] = (marca, pacote(diag, figuras, est, nowcast, vulnerabilidade))
    return cache["pacote"][1]


def botoes_de_download(pacote_):
    """Os três downloads (pedido de 27/11/2026): resumido, completo (com a vulnerabilidade) e o pacote inteiro."""
    st.download_button("📄 Diagnóstico resumido (PDF)", pacote_.pdf_resumido, file_name=pacote_.nome_pdf_resumido,
                       mime="application/pdf", on_click="ignore", width="stretch", key="baixar_resumido",
                       help="Resumo, cenário atual, gráficos, os 4 mapas numa página e as estatísticas.")
    st.download_button("📑 Diagnóstico completo (PDF)", pacote_.pdf, file_name=pacote_.nome_pdf,
                       mime="application/pdf", on_click="ignore", width="stretch", key="baixar_completo",
                       help="Tudo do diagnóstico, com o boletim das localidades sob risco anexado no fim.")
    botao_pacote(pacote_, "📦 Pacote completo (.zip)",
                 ajuda="Os dois PDFs, o boletim da vulnerabilidade, planilhas, GeoJSON para o QGIS, CSV e as imagens.")


def exportar_pacote(df, diag, cache, est, nowcast, situacao: dict, municipio: bool, modo: str = "lateral"):
    """Downloads do diagnóstico. ``modo``: "lateral" (painel esquerdo do legado), "caixa" (dashboard, abaixo do
    comparativo) ou "icone" (painel recolhido: só o ⬇️ do pacote)."""
    if diag.focos.empty:
        if modo != "icone":
            st.warning("Sem dados para exportar no período")
        return
    pacote_ = pacote_do_diagnostico(df, diag, cache, est, nowcast, situacao, municipio)
    if modo == "icone":
        if pacote_ is not None:
            botao_pacote(pacote_, "⬇️", ajuda="Baixar o pacote completo (PDFs, planilhas, GeoJSON, PNG)",
                         chave="icone_pacote")
        return
    st.markdown("**📦 Downloads do diagnóstico**")
    if pacote_ is None:
        st.caption("⏳ Preparando os arquivos: aguardando os focos, o vento e a fumaça ao vivo para o boletim das "
                   "localidades…")
        for rotulo in ("📄 Diagnóstico resumido (PDF)", "📑 Diagnóstico completo (PDF)", "📦 Pacote completo (.zip)"):
            st.button(rotulo, disabled=True, width="stretch", key=f"espera_{rotulo[:2]}")
        return
    if st.session_state.pop("baixar_agora", False):
        disparar_download_automatico(pacote_.conteudo, pacote_.nome)
        st.success("✅ Diagnóstico concluído! O download do pacote completo em ZIP foi iniciado automaticamente.")
    elif modo == "lateral":
        st.success("✅ Diagnóstico concluído com sucesso!")
    botoes_de_download(pacote_)


# ------------------------------------------------- Cenário atual (nowcast)

def localidades_do_municipio(sigla_uf: str | None, municipio: str) -> pd.DataFrame:
    loc = carregar_localidades(sigla_uf)
    return loc[loc["municipio"].astype(str).map(chave_nome) == chave_nome(municipio)].reset_index(drop=True)


def _buscar_ao_vivo(chave: tuple, poligono, localidades):
    st.session_state["vulnerabilidade_ao_vivo"] = (chave, buscar_dados_ao_vivo(poligono, localidades))


@st.cache_resource(show_spinner=False)
def executor_ao_vivo():
    from concurrent.futures import ThreadPoolExecutor
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="ao-vivo")


def busca_em_segundo_plano(chave: tuple, poligono, localidades) -> tuple:
    """Começa (uma vez por município) a busca dos eventos, do vento e da fumaça sem travar a página;
    devolve (futuro, progresso) — progresso["fracao"] vai de 0 a 1."""
    buscas = st.session_state.setdefault("buscas_ao_vivo", {})
    if chave not in buscas:
        progresso = {"fracao": 0.0}
        futuro = executor_ao_vivo().submit(buscar_dados_ao_vivo, poligono, localidades, None,
                                           lambda f: progresso.update(fracao=f))
        buscas.clear()
        buscas[chave] = (futuro, progresso)
    return buscas[chave]


@st.fragment(run_every=1)
def indicador_de_carregamento(chave: tuple):
    """Porcentagem da busca ao vivo sobre o mapa; ao terminar, refaz a página com os dados (e some)."""
    futuro, progresso = st.session_state.get("buscas_ao_vivo", {}).get(chave, (None, None))
    if futuro is None:
        return
    if futuro.done():
        st.rerun()
    fracao = progresso["fracao"]
    st.progress(max(fracao, 0.03), text=f"Buscando focos, vento e fumaça… {fracao:.0%}")


def dados_vulnerabilidade(df: pd.DataFrame, diag, situacao: dict) -> dict:
    """Análise das localidades do município — a mesma na tela, no pacote e no PDF completo (pedido de 27/11/2026).
    Começa a busca ao vivo em segundo plano; ``carregando`` = ainda buscando. ``{"erro": (nível, texto)}`` sem
    limite ou sem localidades. A análise fica na sessão até mudar o município, a base ou os dados ao vivo."""
    if diag.poligono is None:
        return {"erro": ("warning", "Sem o limite do município não há como fazer esta análise.")}
    sigla = diag.sigla_uf or (str(diag.focos["SIGLA_UF"].iloc[0]) if len(diag.focos) else None)
    try:
        localidades = localidades_do_municipio(sigla, diag.municipio)
    except BaseLocalidadesAusente as erro:
        return {"erro": ("info", str(erro))}
    if localidades.empty:
        return {"erro": ("info", "Nenhuma localidade do IBGE neste município.")}
    chave = (diag.estado, diag.municipio)
    guardado = st.session_state.get("vulnerabilidade_ao_vivo")
    ao_vivo = guardado[1] if guardado and guardado[0] == chave else None
    carregando, falha = False, None
    if ao_vivo is None and config.DADOS_AO_VIVO:
        futuro, _ = busca_em_segundo_plano(chave, diag.poligono, localidades)
        if futuro.done():
            try:
                ao_vivo = futuro.result()
                st.session_state["vulnerabilidade_ao_vivo"] = (chave, ao_vivo)
            except Exception as erro:           # nunca derruba a página
                falha = erro
        else:
            carregando = True
    ultimo = pd.Timestamp(situacao["ultimo_dia"] or diag.fim_dados)
    x0, y0, x1, y1 = diag.poligono.bounds
    m = MARGEM_BUSCA_GRAUS
    perto = df[df["lon"].between(x0 - m, x1 + m) & df["lat"].between(y0 - m, y1 + m)]
    datas = pd.to_datetime(perto["data"])
    recentes = perto[(datas > ultimo - pd.Timedelta(days=7)) & (datas <= ultimo + pd.Timedelta(days=1))]
    marca = (chave, diag.ano_inicio, diag.ano_fim, ultimo, ao_vivo["buscado_em"] if ao_vivo else None)
    salvo = st.session_state.get("vul_analise")
    if salvo and salvo[0] == marca:
        analise = salvo[1]
    else:
        historico = perto[perto["ano"].between(diag.ano_inicio, diag.ano_fim)]
        with st.spinner("Calculando a exposição das localidades..."):
            analise = analisar(localidades, diag.poligono, recentes, ultimo, historico,
                               list(range(diag.ano_inicio, diag.ano_fim + 1)),
                               ao_vivo["eventos"] if ao_vivo else None,
                               ao_vivo["vento_eventos"] if ao_vivo else None, ao_vivo["pm25"] if ao_vivo else None)
        st.session_state["vul_analise"] = (marca, analise)
    return {"chave": chave, "sigla": sigla, "localidades": localidades, "ao_vivo": ao_vivo, "carregando": carregando,
            "falha": falha, "recentes": recentes, "ultimo": ultimo, "analise": analise, "marca": marca}


def secao_vulnerabilidade(df: pd.DataFrame, diag, situacao: dict, dashboard: bool = False):
    """Protótipo (P42): localidades do IBGE × focos, eventos de fogo do Painel do Fogo, vento e PM2,5.
    Os dados ao vivo são buscados sozinhos, em segundo plano, depois que a página carrega (com a porcentagem
    sobre o mapa). ``dashboard`` = só o mapa e a tabela das localidades."""
    if dashboard:
        st.markdown(f"#### 🏘️ Localidades vulneráveis a fogo e fumaça")
    else:
        st.markdown(f"### 🏘️ Localidades vulneráveis a fogo e fumaça — {diag.municipio.title()}")
    st.caption("**Protótipo** para avaliação: pesos, distâncias e classes (docs/09, P43–P46) ainda podem ser "
               "calibrados com as ocorrências. "
               "Focos da base (AQUA), eventos de fogo do Painel do Fogo (CENSIPAM), vento e PM2,5 previstos do "
               "Open-Meteo, localidades do IBGE (Censo 2022).")
    dados = dados_vulnerabilidade(df, diag, situacao)
    if "erro" in dados:
        getattr(st, dados["erro"][0])(dados["erro"][1])
        return
    chave, localidades, ao_vivo, carregando = dados["chave"], dados["localidades"], dados["ao_vivo"], dados["carregando"]
    if dados.get("falha"):
        st.warning(f"Não foi possível buscar os dados ao vivo: {dados['falha']}")
    c1, c2 = st.columns([1.3, 3])
    if config.DADOS_AO_VIVO and not dashboard:
        c1.button("🔄 Buscar de novo agora", key="vul_buscar", width="stretch",
                  on_click=_buscar_ao_vivo, args=(chave, diag.poligono, localidades),
                  help="Painel do Fogo (eventos ativos e em observação) e Open-Meteo (vento e PM2,5 das próximas "
                       "24 h). A primeira busca é feita sozinha quando a página abre; este botão busca de novo.")
    if dashboard:
        pass
    elif carregando:
        c2.caption("Buscando os eventos de fogo, o vento e a fumaça em segundo plano — o mapa se atualiza sozinho.")
    elif ao_vivo:
        tempos = ao_vivo.get("tempos", {})
        c2.caption(f"Dados ao vivo buscados às {ao_vivo['buscado_em'].astimezone():%H:%M de %d/%m}"
                   + (f" em {fmt_numero(tempos['total'], 1)} s" if "total" in tempos else "") + ". "
                   "Sem eles, a análise usa só a proximidade dos focos da base e a vulnerabilidade.")
        for aviso in ao_vivo["avisos"]:
            st.warning(aviso)
    else:
        c2.caption("Por enquanto só com os focos da base (proximidade) e a vulnerabilidade de cada localidade. "
                   "Busque os dados ao vivo para incluir os eventos de fogo, os cones de vento e a fumaça prevista.")
    analise, recentes, ultimo = dados["analise"], dados["recentes"], dados["ultimo"]
    sigla = dados["sigla"]
    x0, y0, x1, y1 = diag.poligono.bounds
    m = MARGEM_BUSCA_GRAUS
    for aviso in analise.avisos:
        st.caption(f"⚠️ {aviso}")

    classes = resumo_por_classe(analise)
    ev = analise.eventos
    fichas = [("Localidades analisadas", fmt_inteiro(len(analise.localidades)), "IBGE 2022, no município"),
              ("Risco muito alto / alto", f"{classes['Muito alto']} / {classes['Alto']}", "exposição × vulnerabilidade"),
              ("Risco moderado", fmt_inteiro(classes["Moderado"]), ""),
              ("Eventos de fogo", fmt_inteiro(len(ev)) if ao_vivo else "—",
               f"{int((ev['status'] == 'Ativo').sum())} ativos" if ao_vivo and len(ev) else "busque os dados ao vivo")]
    if not dashboard:
        st.markdown('<div class="fichas">' + "".join(
            f'<div class="ficha"><div class="rotulo">{escape(r)}</div><div class="numero">{escape(v)}</div>'
            f'<div class="nota">{escape(n)}</div></div>' for r, v, n in fichas) + "</div>", unsafe_allow_html=True)

    vento = carregar_vento(config.BASES_DIR)
    if len(vento):
        vento = vento_na_hora(vento, pd.Timestamp.now(tz="UTC").tz_localize(None), sigla)
        vento = vento[vento["lon"].between(x0 - m, x1 + m) & vento["lat"].between(y0 - m, y1 + m)]
    cones = dissolver_cones(analise.cones)
    c_camadas, c_swir, c_exportar, c_centro = st.columns([1, 1.6, 1.3, 1])
    with c_camadas.popover("🗂️ Camadas", width="stretch"):
        camadas = {}
        for nome, (rotulo, ligada, opacidade) in CAMADAS_VULNERABILIDADE.items():
            a, b = st.columns([1.3, 1])
            camadas[nome] = (a.checkbox(rotulo, value=ligada, key=f"vul_cam_{nome}"),
                             b.slider("Opacidade", 0, 100, opacidade, 5, key=f"vul_op_{nome}", format="%d%%",
                                      label_visibility="collapsed"))
    swir = config.FUNDO_SATELITE and config.DADOS_AO_VIVO and c_swir.toggle(
        "Sentinel-2 em realce de fogo (SWIR)", key="vul_swir")
    c_exportar.download_button(
        "⬇️ Cones em GeoJSON", geojson_dos_cones(cones), on_click="ignore", width="stretch", disabled=not cones,
        file_name=f"cones_fogo_fumaca_{nome_arquivo(diag.municipio)}_{analise.momento:%Y%m%d_%H%M}.geojson",
        mime="application/geo+json", help="Avanço do fogo (24 h) e fumaça (6 h), dissolvidos pelo número de "
                                          "eventos sobrepostos (1, 2, 3 ou mais).")
    alvo = st.session_state.get("alvo_mapa")
    if alvo and c_centro.button("↺ Ver o município", width="stretch", key="vul_centro"):
        st.session_state.pop("alvo_mapa", None)
        alvo = None
    datas = pd.to_datetime(recentes["data"]).dt.normalize()
    atras = (ultimo.normalize() - datas).dt.days
    focos_mapa = recentes.assign(data=datas, idade=np.select([atras <= 0, atras <= 2], ["Último dia",
                                                                                         "1–2 dias antes"],
                                                             "3–6 dias antes"))
    c_mapa, c_legenda = st.columns([3.2, 1])
    with c_mapa:
        # trocar o alvo (dois cliques na tabela) recria o mapa já centralizado nele
        st.pydeck_chart(deck_vulnerabilidade(analise, diag.poligono, vento, config.FUNDO_SATELITE, swir,
                                             focos_mapa, cones, camadas, alvo),
                        height=ALTURA_PX, key=f"vul_mapa_{alvo}")
        if carregando:                       # sobre o canto do mapa, some quando os dados chegam
            with st.container(key="vul_carregando"):
                indicador_de_carregamento(chave)
    with c_legenda, st.container(border=True):
        st.markdown(legenda_vulnerabilidade_html(), unsafe_allow_html=True)
    if not len(vento):
        st.caption("Setas de vento só nos eventos. Ligue **Vento** no painel ⋯ para ver o vento das quadrículas "
                   "com focos do estado.")

    st.markdown("#### Localidades por risco")
    loc = analise.localidades
    marcas = np.where(loc["indigena"], "indígena", np.where(loc["quilombola"], "quilombola",
                                                            np.where(loc["agrovila_pa"], "agrovila", "")))
    distancia = lambda s: s.where(np.isfinite(s.astype(float)))      # noqa: E731
    tabela_loc = pd.DataFrame({
        "Risco": loc["classe"], "Localidade": loc["nome"], "Tipo": loc["categoria"].astype(str), "Marca": marcas,
        "Vulnerab.": loc["vulnerabilidade"], "Exposição": loc["exposicao"], "Motivo": loc["motivo"],
        "Perfil": loc["perfil"], "Foco 24 h (km)": distancia(loc["foco_24h_km"]), "Foco 7 dias (km)": distancia(loc["foco_7d_km"]),
        "Focos a 10 km (7 dias)": loc["focos_7d_10km"],
        "Fogo chega em (h)": loc["eta_fogo_h"], "Fumaça chega em (h)": loc["eta_fumaca_h"],
        "PM2,5 máx. 24 h": loc["pm25_max"].round(0), "Qualidade do ar (CONAMA)": loc["qualidade_ar"],
        "Dist. da sede (km)": loc["dist_sede_km"], "Anos com foco a 5 km": (loc["recorrencia"] * 100).round(0)})
    tabela_que_aponta_no_mapa(
        tabela_loc, "vul_localidades",
        {("Localidade", str(n)): (float(x), float(y)) for n, x, y in zip(loc["nome"], loc["lon"], loc["lat"])},
        height=320 if dashboard else 420, column_config={
        "Anos com foco a 5 km": st.column_config.NumberColumn(format="%d%%"),
        "Foco 24 h (km)": st.column_config.NumberColumn(format="%.1f"),
        "Foco 7 dias (km)": st.column_config.NumberColumn(format="%.1f")})
    if dashboard:
        return
    if ao_vivo and len(ev):
        st.markdown("#### Eventos de fogo perto do município (Painel do Fogo)")
        tabela_que_aponta_no_mapa(pd.DataFrame({
            "Evento": ev["id_evento"].astype(str), "Status": ev["status"],
            "Início": [d.tz_convert("America/Belem").strftime("%d/%m %H:%M") for d in ev["inicio"]],
            "Última detecção": [d.tz_convert("America/Belem").strftime("%d/%m %H:%M") for d in ev["ultima_deteccao"]],
            "Área (ha)": ev["area_ha"], "Expansão (ha/h, 24 h)": ev["expansao_ha_h"],
            "Severidade": ev["severidade"].round(1), "Vento (km/h)": ev["vento_kmh"],
            "Vento para": [rosa_dos_ventos(a) for a in ev["vento_para_graus"]],
            "Avanço do fogo 24 h (km)": ev["avanco_24h_km"], "Alcance da fumaça 6 h (km)": ev["alcance_fumaca_km"],
            "Dist. da sede (km)": ev["dist_sede_km"]}).sort_values(["Status", "Severidade"], ascending=[True, False]),
            "vul_eventos", {("Evento", str(e)): (float(x), float(y)) for e, x, y in zip(ev["id_evento"], ev["lon"],
                                                                                    ev["lat"])},
            height=320)
    with st.expander("📐 Como o protótipo calcula"):
        st.markdown(METODOLOGIA_VULNERABILIDADE)


@st.fragment
def secao_nowcast(diag, n):
    """Situação dos últimos dias no município (resolução diária), independente do período escolhido."""
    i, ultimo = n.indicadores, n.ultimo_dia
    st.markdown("### 🛰️ Cenário Atual (nowcast diário)")
    legenda = f"Focos do satélite de referência em {diag.municipio.title()} até {ultimo:%d/%m/%Y}"
    legenda += " — **o último dia ainda é parcial** (o INPE publica ao longo do dia)." if n.provisorio else "."
    if n.anos_comparados:
        legenda += (f" Comparação com o mesmo dia (e com a média de ±3 dias) nos anos "
                    f"{n.anos_comparados[0]}–{n.anos_comparados[-1]}.")
    st.caption(legenda)

    def comparado(valor, media):
        if media != media:                       # sem anos anteriores para comparar
            return None
        diferenca = round(valor - media)
        return f"{'+' if diferenca >= 0 else '-'}{fmt_inteiro(abs(diferenca))} vs. média ({fmt_inteiro(round(media))})"

    c = st.columns(5)
    c[0].metric(f"Focos em {ultimo:%d/%m}", fmt_inteiro(i["ultimo_dia"]),
                comparado(i["ultimo_dia"], i["media_ultimo_dia"]), delta_color="inverse")
    c[1].metric("Dia anterior", fmt_inteiro(i["dia_anterior"]))
    c[2].metric("Últimos 7 dias", fmt_inteiro(i["ultimos_7"]), comparado(i["ultimos_7"], i["media_7"]),
                delta_color="inverse")
    c[3].metric("Últimos 30 dias", fmt_inteiro(i["ultimos_30"]), comparado(i["ultimos_30"], i["media_30"]),
                delta_color="inverse")
    c[4].metric(f"No ano até {ultimo:%d/%m}", fmt_inteiro(i["acumulado_ano"]),
                fmt_percentual(i["variacao_acumulado_pct"], sinal=True) + " vs. média"
                if i["variacao_acumulado_pct"] is not None else None, delta_color="inverse",
                help=f"{i['posicao_acumulado']}º maior acumulado até esta data entre {i['anos_ranking']} anos.")

    st.altair_chart(interativo_nowcast(n), width="stretch")
    dias = st.select_slider("Focos no mapa e na lista: últimos", options=[1, 3, 7, 15, 30], value=7,
                            format_func=lambda d: f"{d} dia" + ("s" if d > 1 else ""), key="nowcast_dias")
    recentes = n.recentes(dias)
    guardados = (st.session_state.get("figuras_cache") or {}).get("mapas_recentes", {})
    if dias not in guardados:          # mapa sobre o satélite: gerado uma vez por diagnóstico e período de dias
        with st.spinner("Desenhando o mapa dos focos recentes..."):
            figura = mapa_recentes(recentes, diag.poligono, diag.municipio, ultimo, dias,
                                   getattr(diag, "areas", None))
            guardados[dias] = png(figura, dpi=110)
            plt.close(figura)
    st.image(guardados[dias], width="stretch")
    with st.expander(f"Lista dos {fmt_inteiro(len(recentes))} focos"):
        tabela(recentes.assign(data=[d.strftime("%d/%m/%Y") for d in recentes["data"]])
               .drop(columns="dias_atras").rename(columns={"data": "Data", "idade": "Idade", "lat": "Latitude",
                                                           "lon": "Longitude"}))
    st.caption("No relatório PDF e no pacote, o mapa mostra os últimos 7 dias.")


# ------------------------------------------- Estatísticas (modelo INPE)

COR_TABELA_MINIMO = "background-color: #FFD54F; font-weight: bold"
COR_TABELA_MAXIMO = "background-color: #B23A1E; color: white; font-weight: bold"
COR_LINHA_RESUMO = {"Mínimo": "background-color: #FBC02D; font-weight: bold",
                    "Média": "background-color: #FB8C00; font-weight: bold",
                    "Máximo": "background-color: #B23A1E; color: white; font-weight: bold"}
ABAS_COMPARATIVOS = {"Comparativo mensal": "mensal", "Comparativo semanal": "semanal",
                     "Comparativo 1º semestre": "semestre1", "Comparativo 2º semestre": "semestre2"}


def chave_analise(p: dict) -> tuple:
    return p["tipo"], p["estado"], p["nome"], p["ano_inicio"], p["ano_fim"]


def parametros_do_relatorio(chave: tuple) -> ParametrosEstatisticas:
    """Parâmetros aplicados ao PDF/pacote nesta análise (padrão até o usuário aplicar outros)."""
    guardado = st.session_state.get("parametros_relatorio")
    return guardado[1] if guardado and guardado[0] == chave else ParametrosEstatisticas()


def estilo_inpe(tabela_: pd.DataFrame, linhas_destaque: list[str], recorde: str | None = None):
    """Menor valor de cada coluna em amarelo e maior em vermelho (o ano ``recorde`` quando passa da máxima);
    linhas Mínimo/Média/Máximo coloridas."""
    extremos = extremos_por_coluna(tabela_, linhas_destaque, recorde)

    def cores(coluna):
        minimos, maximos = extremos[coluna.name]
        return [COR_TABELA_MAXIMO if i in maximos else COR_TABELA_MINIMO if i in minimos
                else COR_LINHA_RESUMO.get(i, "") for i in coluna.index]

    return tabela_.style.apply(cores, axis=0).format(lambda v: "-" if pd.isna(v) else fmt_numero(v))


def controles_estatisticas(ano_inicio: int, ano_fim: int, prefixo: str) -> ParametrosEstatisticas:
    anos = list(range(ano_inicio, ano_fim + 1))
    c1, c2, c3, c4 = st.columns(4)
    ano_ref = c1.selectbox("Ano de referência (comparado)", anos[::-1], key=f"{prefixo}ano",
                           help="Ano das barras e das linhas destacadas. Mínimo, média e máximo usam os demais "
                                "anos do período da análise.")
    meses = [None] + list(range(1, 13))
    mes = c2.selectbox("Mês da tabela dia a dia", meses, key=f"{prefixo}mes",
                       format_func=lambda m: "Último mês com dados" if m is None else MESES_TABELA[m - 1])
    percentis = c3.slider("Faixa de percentis (sazonalidade e acumulado)", 0, 100, (10, 90), step=5,
                          key=f"{prefixo}percentis")
    janela = c4.slider("Anos para o mais/menos intenso", 1, max(2, len(anos) - 1), min(10, max(1, len(anos) - 1)),
                       key=f"{prefixo}janela", help="Anos completos imediatamente anteriores ao ano de referência.")
    c5, c6 = st.columns([3, 1])
    series = c5.multiselect("Linhas dos comparativos", LINHAS_RESUMO[::-1], default=LINHAS_RESUMO[::-1],
                            key=f"{prefixo}series")
    mostrar_anos = c6.toggle("Uma linha por ano no acumulado", value=True, key=f"{prefixo}anos")
    return ParametrosEstatisticas(ano_referencia=ano_ref, mes_diario=mes, percentil_inferior=percentis[0],
                                  percentil_superior=percentis[1], anos_intensidade=janela,
                                  series_comparativo=tuple(series), mostrar_anos=mostrar_anos)


@st.fragment
def secao_estatisticas(focos: pd.DataFrame, nome: str, ano_inicio: int, ano_fim: int, chave: tuple | None = None,
                       prefixo: str = "est_", compacto: bool = False):
    """Estatísticas no modelo do Programa Queimadas/INPE; os controles só refazem esta seção.

    ``chave`` = análise do diagnóstico (oferece aplicar os parâmetros ao relatório); None no Panorama.
    ``compacto`` = dashboard: controles num botão, abre no acumulado, tabela mês a mês com altura fixa (rola nos
    dois sentidos; o botão de tela cheia da tabela mostra a planilha inteira).
    """
    if compacto:
        c_titulo, c_parametros = st.columns([3, 1], vertical_alignment="bottom")
        c_titulo.markdown("#### 📊 Estatísticas (modelo INPE)")
        with c_parametros.popover("⚙️ Parâmetros", width="stretch"):
            parametros = controles_estatisticas(ano_inicio, ano_fim, prefixo)
    else:
        st.markdown("### 📊 Estatísticas de Focos Ativos (modelo Programa Queimadas/INPE)")
        parametros = controles_estatisticas(ano_inicio, ano_fim, prefixo)
    caminho = str(config.caminho_focos())
    est = estatisticas_territorio(focos, nome, ano_inicio, ano_fim, cobertura(caminho), parametros)
    if not compacto:
        for nota in notas(est):
            st.caption(nota)

    abas = st.tabs(["Mês a mês", "Dia a dia", *ABAS_COMPARATIVOS, "Acumulado mensal"],
                   default="Acumulado mensal" if compacto else None)
    with abas[0]:
        st.markdown(f"**Total de focos detectados em cada mês ({ano_inicio}–{ano_fim})**")
        st.dataframe(estilo_inpe(tabela_mensal_exibicao(est), [str(a) for a in est.anos_estatistica],
                                 str(est.ano_referencia)),
                     width="stretch", height=340 if compacto else min(40 + 35 * (len(est.mensal) + 3), 900))
    with abas[1]:
        st.markdown(f"**Total de focos detectados dia a dia — {MESES_TABELA[est.parametros.mes_diario - 1]}**")
        st.dataframe(estilo_inpe(tabela_diaria_exibicao(est), []), width="stretch")
        st.caption("Não é recomendada a comparação dos valores diários, apenas dos totais mensais.")
    for aba, unidade in zip(abas[2:6], ABAS_COMPARATIVOS.values()):
        with aba:
            st.altair_chart(interativo_comparativo(est, unidade), width="stretch")
            with st.expander("Ver tabela"):
                tabela(tabela_comparativo_exibicao(est, unidade))
    with abas[6]:
        st.altair_chart(interativo_acumulado(est), width="stretch")
        if not est.anos_intensidade:
            st.caption("Sem anos completos antes do ano de referência para indicar o mais e o menos intenso.")
        with st.expander("Ver tabela"):
            st.dataframe(tabela_acumulado_exibicao(est).style.format(lambda v: "-" if pd.isna(v) else fmt_numero(v)),
                         width="stretch")
    if not compacto:
        st.caption("Passe o mouse para ver os valores, use a roda do mouse para aproximar e clique na legenda "
                   "para destacar uma série.")

    if chave is None:
        return
    no_relatorio = parametros_do_relatorio(chave)
    iguais = resolver_parametros(no_relatorio, ano_inicio, ano_fim, est.fim_dados) == est.parametros
    if iguais:
        st.caption("✅ O relatório PDF e o pacote usam estes parâmetros.")
    else:
        st.info("O relatório PDF e o pacote ainda usam os parâmetros anteriores.", icon="ℹ️")
        if st.button("📄 Usar estes parâmetros no relatório (PDF e pacote)", key="est_aplicar"):
            st.session_state["parametros_relatorio"] = (chave, parametros)
            st.rerun()


# ------------------------------------------------------------------ Páginas

def mapa_do_estado(estado: str):
    """Abertura do Diagnóstico: focos da última semana no estado, com a recorrência do mês; clique = diagnóstico."""
    caminho = str(config.caminho_focos())
    situacao = situacao_da_base(config.BASES_DIR)
    caminho_estado = estados_disponiveis().get(estado)
    if situacao["ultimo_dia"] is None or caminho_estado is None:
        return
    provisorios = tuple(situacao["provisorios"])
    with st.spinner("Montando o mapa do estado..."):
        cen = cenario_em_cache(caminho, estado, TODAS, situacao["ultimo_dia"], provisorios)
        rec = recorrencia_do_cenario(caminho, caminho_estado, estado, TODAS, situacao["ultimo_dia"], provisorios)
    st.markdown(f"### 🗺️ {estado}: focos de {cen.inicio_semana:%d/%m} a {cen.dia:%d/%m/%Y}")
    mostrar_mapa_interativo("mapa_abertura", cen.nowcast.recentes(DIAS_SEMANA),
                            limite_da_regiao(caminho_estado, cen.sigla_uf, None), estado, rec)


def pagina_diagnostico():
    df = base_focos(str(config.caminho_focos()))
    if df.empty:
        render_header()
        st.error(f"Nenhum dado de foco encontrado: a base {config.caminho_focos()} não existe. "
                 "Veja a página 🗂️ Bases de dados.")
        return
    p = parametros_analise(df)
    if p is None:
        render_header()
        return
    if p["processar"]:
        st.session_state["analise"] = chave_analise(p)
    if dashboard_ativo():          # no dashboard, a tela inteira é do painel (sem o cabeçalho institucional)
        st.markdown(CSS_DASHBOARD, unsafe_allow_html=True)
        if st.session_state.get("analise") != chave_analise(p) and not p["processar"]:
            titulo_dashboard()
            st.info("☝️ Escolha o estado e o município no título — ou clique num município do mapa.")
            mapa_do_estado(p.get("estado") or "Pará")
            return
    else:
        render_header(f"{p['tipo']}: {p['nome']}")
    if p["processar"]:
        st.session_state["analise"] = chave_analise(p)
        st.session_state["baixar_agora"] = p["download_automatico"]
        st.session_state.pop("parametros_relatorio", None)
        for chave in [c for c in st.session_state if str(c).startswith("est_")]:
            del st.session_state[chave]          # controles das estatísticas voltam ao padrão
    if st.session_state.get("analise") != chave_analise(p):
        st.info("👈 Defina o território e o período no painel à esquerda e clique em "
                "**Processar Diagnóstico Completo** — ou clique num município do mapa.")
        mapa_do_estado(p.get("estado") or "Pará")
    else:
        mostrar_territorio(df, p)


def date_br(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y")


def _situacao_arquivo(nome: str, caminho) -> dict:
    existe = caminho.exists()
    tamanho = (sum(f.stat().st_size for f in caminho.glob("*.geojson")) if caminho.is_dir()
               else caminho.stat().st_size) if existe else 0
    return {
        "": "✅" if existe else "⛔",
        "Base": nome,
        "Arquivo": str(caminho.relative_to(config.BASES_DIR)) if existe else str(caminho),
        "Tamanho (MB)": round(tamanho / 1e6, 1) if existe else None,
        "Modificado em": datetime.fromtimestamp(caminho.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if existe else "",
    }


def pagina_bases():
    render_header("BASES DE DADOS")
    st.subheader("Arquivos em uso")
    st.caption(f"Pasta das bases: `{config.BASES_DIR}`")
    tabela(pd.DataFrame([
        _situacao_arquivo("Focos de calor (BDQueimadas/INPE)", config.caminho_focos()),
        _situacao_arquivo("Limites municipais (IBGE), um arquivo por estado", config.pasta_municipios()),
        _situacao_arquivo("Unidades de Conservação (CNUC/MMA)", config.caminho_uc()),
        _situacao_arquivo("Terras Indígenas (FUNAI)", config.caminho_ti()),
    ]))

    df = base_focos(str(config.caminho_focos()))
    if not df.empty:
        st.subheader("Conteúdo da base de focos")
        datas = df["data"].dropna().astype(str)
        c = st.columns(4)
        c[0].metric("Focos", fmt_inteiro(len(df)))
        c[1].metric("Anos", f"{df['ano'].min()}–{df['ano'].max()}")
        c[2].metric("Foco mais recente", pd.to_datetime(datas.max()).strftime("%d/%m/%Y") if len(datas) else "—")
        c[3].metric("Estados com limites", len(estados_disponiveis()))
        tabela(df["ano"].value_counts().sort_index().rename_axis("Ano").reset_index(name="Focos"))

    st.subheader("Atualização automática (INPE)")
    situacao = situacao_da_base(config.BASES_DIR)
    if situacao["provisorios"]:
        st.caption("Dias provisórios (baixados de novo na próxima busca): "
                   + ", ".join(f"{d:%d/%m/%Y}" for d in situacao["provisorios"]))
    if situacao["historico"]:
        tabela(pd.DataFrame([{
            "Em": datetime.fromisoformat(h["em"]).astimezone().strftime("%d/%m/%Y %H:%M"),
            "Dias": f"{date_br(h['de'])} a {date_br(h['ate'])}", "Arquivos": len(h["arquivos"]),
            "Focos novos": h["focos_novos"], "Total na base": h["total"],
        } for h in reversed(situacao["historico"])]))
    else:
        st.caption("Nenhuma atualização registrada ainda.")

    st.subheader("Como atualizar")
    st.markdown("""
A base de focos é atualizada em segundo plano com os arquivos diários e mensais do INPE: quando o programa abre
(ele já começa com a base local) e, com o **Nowcast** ligado na barra lateral, na hora e depois a cada 4 horas; quando um mês termina, os dias que vieram dos arquivos
diários são trocados pelo arquivo mensal consolidado. Para trocar uma base inteira, substitua o arquivo na pasta
das bases **mantendo exatamente o mesmo nome** e reabra o programa:

- `bdqueimadas_consolidado.parquet` — focos de calor;
- `mun-brGEOJSON/NM_UF_<Estado>.geojson` — municípios;
- `ucGEOJSON/UC-BR.geojson` — Unidades de Conservação;
- `tiGEOJSON/TI-BR.geojson` — Terras Indígenas.

Depois de trocar UC ou TI, refaça as colunas `UC`/`TI` da base de focos com
`ferramentas/atualizar_area_protegida_focos.py` e confira com `ferramentas/verificar_base.py` (docs/03).
""")


# ------------------------------------------------------- Panorama do estado

@st.cache_data(show_spinner=False)
def opcoes_regioes(caminho: str, estado: str) -> list[str]:
    return regioes_do_estado(base_focos(caminho), estado)


@st.cache_resource(show_spinner=False, max_entries=8)
def panorama_em_cache(caminho: str, estado: str, ano_inicio: int, ano_fim: int, regiao: str):
    return panorama_estado(base_focos(caminho), estado, ano_inicio, ano_fim, regiao, cobertura(caminho)[0])


@st.cache_data(show_spinner=False, max_entries=8)
def figuras_panorama(caminho: str, caminho_estado, estado: str, ano_inicio: int, ano_fim: int, regiao: str):
    """PNG do mapa de kernel do ano final e da sazonalidade (guardados: a página recarrega com frequência)."""
    pan = panorama_em_cache(caminho, estado, ano_inicio, ano_fim, regiao)
    limite = limite_da_regiao(caminho_estado, pan.sigla_uf, pan.regiao)
    focos_ano = pan.focos[pan.focos["ano"] == ano_fim]
    est = estatisticas_territorio(pan.focos, pan.nome, ano_inicio, ano_fim, cobertura(caminho))
    figuras = {"mapa": mapa_dispersao(focos_ano, limite, pan.nome, ano_fim, numero=""),
               "sazonalidade": grafico_sazonalidade(est)}
    imagens = {chave: png(figura, dpi=110) for chave, figura in figuras.items()}
    fechar_figuras(figuras)
    return imagens


# ------------------------------------------------------------ Mapa interativo

PAGINA_DIAGNOSTICO = "🔥 Diagnóstico"


def municipio_do_mapa(nome: str, opcoes: list[str]) -> str | None:
    """Opção da barra lateral que corresponde ao município clicado (nomes do IBGE × da base)."""
    return next((o for o in opcoes if chave_nome(o) == chave_nome(nome)), None)


def abrir_diagnostico_do_mapa(chave: str, estado: str):
    """Callback do clique no mapa: escolhe o município na barra lateral e processa o diagnóstico."""
    if nome := municipio_clicado(st.session_state.get(chave)):
        abrir_diagnostico(nome, estado)


def abrir_diagnostico(nome: str, estado: str):
    """Escolhe o município na barra lateral e processa o diagnóstico (clique no mapa, dois cliques na tabela)."""
    escolhido = municipio_do_mapa(nome, opcoes_municipios(str(config.caminho_focos()), estado))
    if escolhido is None:
        st.session_state["aviso_mapa"] = f"{nome}: nenhum foco na base — não há diagnóstico para abrir."
        return
    st.session_state.update(navegacao=PAGINA_DIAGNOSTICO, diag_tipo=config.TIPO_MUNICIPIO, diag_estado=estado,
                            diag_municipio=escolhido, processar_pelo_mapa=True)


def mostrar_mapa_interativo(chave: str, recentes, territorio, estado: str | None, rec=None):
    """Focos recentes sobre satélite, quadrícula de recorrência do mês e limites municipais clicáveis."""
    caminho_estado = estados_disponiveis().get(estado) if estado else None
    municipios = municipios_simplificados(Path(caminho_estado)) if caminho_estado else ()
    swir = config.FUNDO_SATELITE and config.DADOS_AO_VIVO and st.toggle(
        "Sentinel-2 em realce de fogo (SWIR — Painel do Fogo)", key=f"{chave}_swir",
        help="Mosaico das imagens Sentinel-2 mais recentes do Painel do Fogo (CENSIPAM): fogo ativo em "
             "vermelho/amarelo, área queimada em marrom-escuro, vegetação em verde. A passagem é a cada ~5 dias; "
             "nuvens aparecem em branco/azul-claro.")
    deck = deck_focos_recentes(recentes, territorio, municipios, rec, config.FUNDO_SATELITE, swir)
    c_mapa, c_legenda = st.columns([3.2, 1])
    with c_mapa:
        st.pydeck_chart(deck, height=ALTURA_PX, key=chave, selection_mode="single-object",
                        on_select=(lambda: abrir_diagnostico_do_mapa(chave, estado)) if estado else "ignore")
    with c_legenda, st.container(border=True):
        st.markdown(legenda_html(recentes, rec), unsafe_allow_html=True)
    st.caption("Role para aproximar, arraste para mover; passe o mouse num foco para ver a data"
               + (" e **clique num município para abrir o diagnóstico dele**." if estado else ".")
               + " Imagem: Sentinel-2 cloudless 2024 (EOX, CC BY-NC-SA 4.0)."
               + (f" {config.CREDITO_SENTINEL_SWIR}." if swir else ""))


@st.cache_resource(show_spinner=False, max_entries=8)
def recorrencia_do_cenario(caminho: str, caminho_estado, estado: str, regiao: str, ultimo_dia, provisorios: tuple):
    cen = cenario_em_cache(caminho, estado, regiao, ultimo_dia, provisorios)
    limite = limite_da_regiao(caminho_estado, cen.sigla_uf, cen.regiao)
    return recorrencia_do_mes(cen, limite.bounds) if limite is not None else None


@st.cache_resource(show_spinner=False, max_entries=8)
def cenario_em_cache(caminho: str, estado: str, regiao: str, ultimo_dia, provisorios: tuple):
    return cenario_atual(base_focos(caminho), estado, regiao, ultimo_dia, cobertura(caminho)[0], list(provisorios))


def secao_cenario_estado(caminho: str, caminho_estado, estado: str, regiao: str, ano_inicio: int, ano_fim: int,
                          abas=None):
    """Cenário atual do estado/região: últimas 24 h e última semana, com o PDF para exportar."""
    situacao = situacao_da_base(config.BASES_DIR)
    if situacao["ultimo_dia"] is None:
        return
    provisorios = tuple(situacao["provisorios"])
    with st.spinner("Montando o cenário atual..."):
        cen = cenario_em_cache(caminho, estado, regiao, situacao["ultimo_dia"], provisorios)
    atual = panorama_em_cache(caminho, estado, ano_inicio, cen.dia.year, regiao)
    with abas[0]:
        st.markdown(f"### {cen.nome}: focos nas últimas 24 horas e na última semana")
        st.caption(f"Últimas 24 h = passagem mais recente do satélite de referência processada pelo INPE "
                   f"({cen.dia:%d/%m/%Y}{', ainda parcial' if cen.provisorio else ''}); última semana = "
                   f"{cen.inicio_semana:%d/%m} a {cen.dia:%d/%m}.")
        # o mapa abre a página: é o que a sala de situação olha primeiro
        limite = limite_da_regiao(caminho_estado, cen.sigla_uf, cen.regiao)
        rec = recorrencia_do_cenario(caminho, caminho_estado, estado, regiao, situacao["ultimo_dia"], provisorios)
        mostrar_mapa_interativo("mapa_panorama", cen.nowcast.recentes(DIAS_SEMANA), limite, estado, rec)

        # boletim (texto) ao lado dos indicadores
        c_boletim, c_numeros = st.columns([1.35, 1], gap="large")
        with c_boletim:
            paragrafos = "".join(f"<p>{escape(p)}</p>"
                                 for p in texto_do_cenario(cen, atual.acima_no_mes, atual.anos_recorde))
            st.markdown(f'<div class="boletim"><h4>Boletim de {cen.dia:%d/%m/%Y}</h4>'
                        f'<div class="quando">Gerado automaticamente com a base buscada no BDQueimadas/INPE até '
                        f'{cen.ultimo_dia_base:%d/%m/%Y}, do satélite de referência AQUA-Tarde (AQUA_M-T)</div>'
                        f'{paragrafos}</div>', unsafe_allow_html=True)
        with c_numeros:
            fichas = []
            for rotulo, valor in indicadores_cenario(cen):
                numero, _, nota = valor.partition(" (")
                nota = nota.rstrip(")")
                fichas.append(f'<div class="ficha"><div class="rotulo">{escape(rotulo)}</div>'
                              f'<div class="numero">{escape(numero)}</div>'
                              f'<div class="nota">{escape(nota) if nota else "&nbsp;"}</div></div>')
            st.markdown(f'<div class="fichas">{"".join(fichas)}</div>', unsafe_allow_html=True)
            st.caption("Médias = mesmos dias nos anos anteriores que a base cobre por inteiro.")

        c1, c2 = st.columns([1.1, 1])
        with c1:
            st.altair_chart(interativo_nowcast_semanal(cen.nowcast), width="stretch")
        with c2:
            listas = st.tabs(["Municípios", "UCs e TIs", f"Focos de {cen.dia:%d/%m}"])
            with listas[0]:
                tabela(cen.municipios, chave="cen_municipios", estado=estado, height=260)
            with listas[1]:
                if cen.areas.empty:
                    st.caption("Nenhum foco em área protegida na última semana.")
                else:
                    tabela(cen.areas, height=260)
            with listas[2]:
                tabela(cen.focos_24h.assign(NM_MUN=cen.focos_24h["NM_MUN"].str.title()).rename(columns={
                    "data": "Data", "NM_MUN": "Município", "regiao": "Região", "lat": "Latitude", "lon": "Longitude"}),
                    chave="cen_focos", estado=estado, height=260)

    with abas[1]:
        municipios_acima_da_maxima(caminho, cen, atual, ano_inicio, estado)

    with abas[2]:
        with st.spinner("Calculando as anomalias do mês..."):
            mostrar_anomalias(anomalias_cenario_png(caminho, caminho_estado, estado, regiao, situacao["ultimo_dia"],
                                                    provisorios), cen.nome)

    with st.sidebar.container():
        downloads_cenario(caminho, caminho_estado, estado, regiao, cen, atual, ano_inicio, ano_fim, situacao)


def downloads_cenario(caminho: str, caminho_estado, estado: str, regiao: str, cen, atual, ano_inicio: int,
                      ano_fim: int, situacao: dict):
    """Relatório e pacote do cenário (PDF) e focos em GeoJSON: no painel esquerdo ou na caixa do dashboard."""
    st.markdown("**📄 Relatório do cenário (PDF)**")
    st.caption(f"Inclui no fim as estatísticas de focos ativos de {ano_inicio}–{ano_fim} (período do filtro).")
    chave = (estado, regiao, cen.dia, situacao["ultimo_dia"], len(cen.focos_semana), ano_inicio, ano_fim)
    if st.button("📄 Gerar relatório e pacote", key="cenario_gerar", width="stretch"):
        with st.spinner("Gerando o relatório e o pacote do cenário..."):
            limite = limite_da_regiao(caminho_estado, cen.sigla_uf, cen.regiao)
            pan = panorama_em_cache(caminho, estado, ano_inicio, ano_fim, regiao)
            est = estatisticas_territorio(pan.focos, pan.nome, ano_inicio, ano_fim, cobertura(caminho))
            sazonalidades = estatisticas_dos_municipios(atual.focos, list(atual.acima_no_mes["Município"]),
                                                        ano_inicio, cen.dia.year, cobertura(caminho)) \
                if atual.acima_no_mes is not None else {}
            pngs = {}
            pdf, nome_pdf = gerar_relatorio_cenario(cen, limite, est, pan.focos, acima_no_mes=atual.acima_no_mes,
                                                    anos_recorde=atual.anos_recorde, sazonalidades=sazonalidades,
                                                    pngs=pngs)
            semana = focos_no_intervalo(base_focos(caminho), estado, regiao, cen.inicio_semana, cen.dia)
            geo = geojson_focos(semana, cen.tipo_regiao, f"Focos da última semana — {cen.nome}")
            st.session_state["cenario_pdf"] = (chave, pdf, nome_pdf,
                                               *pacote_cenario(cen, pdf, nome_pdf, pngs, atual.acima_no_mes, geo))
    guardado = st.session_state.get("cenario_pdf")
    if guardado and guardado[0] == chave:
        st.download_button("⬇️ Baixar relatório do cenário (PDF)", guardado[1], file_name=guardado[2],
                           mime="application/pdf", type="primary", on_click="ignore", key="cenario_baixar")
        st.download_button("📦 Baixar pacote completo do cenário (.zip)", guardado[3], file_name=guardado[4],
                           mime="application/zip", on_click="ignore", key="cenario_baixar_zip")
    exportar_focos_geojson(caminho, estado, regiao, cen)


def _copiar(origem: str, destino: str):
    st.session_state[destino] = st.session_state[origem]


def panorama_dashboard(caminho: str, estados: dict, anos: list[int]):
    """Panorama do estado num painel só, para TV (pedido de 27/11/2026), no mesmo modelo do diagnóstico de
    município. Esquerda: título (estado e região são caixas de seleção), focos por semana no último trimestre,
    sazonalidade do estado, estatísticas (interativas) e downloads. Direita: indicadores do cenário, mapa
    interativo, municípios da última semana (dois cliques = diagnóstico) com o mapa de anomalia (⇄), e os
    municípios acima da máxima com a sazonalidade de cada um (um clique troca)."""
    ss = st.session_state
    nomes = list(estados)
    if ss.get("pan_estado") not in estados:
        ss["pan_estado"] = "Pará" if "Pará" in estados else nomes[0]
    situacao = situacao_da_base(config.BASES_DIR)
    esquerda, direita = st.columns([1, 1.5], gap="medium")
    # chaves próprias (_tv): com a mesma chave do seletor do legado, a caixa mostrava o texto antigo
    with esquerda, st.container(key="dash_titulo"):
        ss["pan_estado_tv"] = ss["pan_estado"]
        estado = st.selectbox("Estado", nomes, key="pan_estado_tv", format_func=lambda e: f"{e.upper()}:",
                              label_visibility="collapsed", on_change=_copiar, args=("pan_estado_tv", "pan_estado"))
        tipo = TIPO_INTEGRACAO if estado == "Pará" else TIPO_IMEDIATA
        opcoes = [TODAS, *opcoes_regioes(caminho, estado)]
        if ss.get("pan_regiao") not in opcoes:
            ss["pan_regiao"] = TODAS
        ss["pan_regiao_tv"] = ss["pan_regiao"]
        regiao = st.selectbox(f"Filtrar por {tipo}", opcoes, key="pan_regiao_tv", label_visibility="collapsed",
                              format_func=lambda r: "Estado inteiro" if r == TODAS else r,
                              on_change=_copiar, args=("pan_regiao_tv", "pan_regiao"))
        c_legenda, c_periodo = st.columns([2, 1], vertical_alignment="center")
        with c_periodo.popover("📅 Período", width="stretch"):
            ano_inicio, ano_fim = st.slider("Período", min_value=anos[0], max_value=anos[-1],
                                            value=(anos[0], anos[-1]), step=1, key="pan_anos")
        c_legenda.caption(f"{ano_inicio}–{ano_fim} · dados até {situacao['ultimo_dia']:%d/%m/%Y}"
                          if situacao["ultimo_dia"] else f"{ano_inicio}–{ano_fim}")
    if situacao["ultimo_dia"] is None:
        st.info("Sem dados recentes na base para o cenário atual.")
        return
    caminho_estado = estados[estado]
    provisorios = tuple(situacao["provisorios"])
    with st.spinner("Montando o cenário atual..."):
        cen = cenario_em_cache(caminho, estado, regiao, situacao["ultimo_dia"], provisorios)
    atual = panorama_em_cache(caminho, estado, ano_inicio, cen.dia.year, regiao)
    with direita:
        st.markdown(f"#### 📌 {cen.nome}: últimas 24 horas e última semana ({cen.dia:%d/%m/%Y}"
                    f"{', parcial' if cen.provisorio else ''})")
        indicadores = indicadores_cenario(cen)
        for linha in range(0, len(indicadores), 3):
            for coluna, (rotulo, valor) in zip(st.columns(3), indicadores[linha:linha + 3]):
                numero, _, nota = valor.partition(" (")
                coluna.metric(rotulo, numero, help=nota.rstrip(")") or None)
        limite = limite_da_regiao(caminho_estado, cen.sigla_uf, cen.regiao)
        rec = recorrencia_do_cenario(caminho, caminho_estado, estado, regiao, situacao["ultimo_dia"], provisorios)
        mostrar_mapa_interativo("mapa_panorama", cen.nowcast.recentes(DIAS_SEMANA), limite, estado, rec)
    with esquerda:
        with st.container(border=True):
            st.altair_chart(interativo_nowcast_semanal(cen.nowcast), width="stretch")
        with st.spinner("Desenhando a sazonalidade..."):
            imagens = figuras_panorama(caminho, caminho_estado, estado, ano_inicio, ano_fim, regiao)
        with st.container(border=True):
            st.image(imagens["sazonalidade"], width="stretch")
    with direita:
        c_tabela, c_anomalia = st.columns([1.15, 1])
        with c_tabela:
            st.markdown(f"**Municípios com focos na última semana** — dois cliques abrem o diagnóstico")
            tabela(cen.municipios, chave="cen_municipios", estado=estado, height=430)
        with c_anomalia:
            with st.spinner("Calculando as anomalias do mês..."):
                anomalias = anomalias_cenario_png(caminho, caminho_estado, estado, regiao, situacao["ultimo_dia"],
                                                  provisorios)
            cartao_de_mapa("anomalia_estado", [(f"Anomalia do mês — {n}", anomalias.get(t)) for t, n in
                                               (("quantidade", "quantidade"), ("localizacao", "localização"),
                                                ("combinada", "combinada"))], cache=None,
                           vazio="Anomalias indisponíveis: são precisos pelo menos 3 anos completos de referência.")
        municipios_acima_da_maxima(caminho, cen, atual, ano_inicio, estado, lado_a_lado=True)
    with esquerda:
        with st.container(border=True):
            pan = panorama_em_cache(caminho, estado, ano_inicio, ano_fim, regiao)
            secao_estatisticas(pan.focos, pan.nome, ano_inicio, ano_fim, prefixo="pan_est_", compacto=True)
        with st.container(border=True, key="dash_downloads_estado"):
            downloads_cenario(caminho, caminho_estado, estado, regiao, cen, atual, ano_inicio, ano_fim, situacao)


def municipios_acima_da_maxima(caminho: str, cen, atual, ano_inicio: int, estado: str, lado_a_lado: bool = False):
    """Municípios com mais focos no mês (até o dia) do que em qualquer ano anterior nas mesmas datas."""
    acima = atual.acima_no_mes
    if acima is None or atual.anos_recorde is None:
        return
    mes = MESES_EXTENSO[cen.dia.month - 1]
    st.markdown(f"#### 🔺 Municípios acima da máxima histórica em {mes} (1º a {cen.dia:%d/%m} × "
                f"{atual.anos_recorde[0]}–{atual.anos_recorde[1]})")
    if acima.empty:
        st.caption("Nenhum município ultrapassou a máxima histórica das mesmas datas.")
        return
    acima = acima.reset_index(drop=True)
    nomes = list(acima["Município"])

    def ao_clicar():                # um clique num município: a sazonalidade abaixo passa a ser a dele
        celulas = st.session_state["pan_acima_tabela"]["selection"]["cells"]
        if celulas and 0 <= celulas[0][0] < len(nomes):
            st.session_state["pan_acima_mun"] = nomes[celulas[0][0]]

    c_tabela, c_grafico = st.columns([1, 1.1]) if lado_a_lado else (st.container(), st.container())
    with c_tabela:
        tabela(acima, chave="acima", estado=estado, key="pan_acima_tabela", on_select=ao_clicar,
               selection_mode="single-cell", height=330 if lado_a_lado else "auto",
               column_config={"Ano da máxima": st.column_config.NumberColumn(format="%d"),
                              "Vezes a máxima": st.column_config.NumberColumn(format="%.1f ×")})
    if st.session_state.get("pan_acima_mun") not in nomes:
        st.session_state.pop("pan_acima_mun", None)
    with c_grafico:
        escolhido = st.selectbox("Sazonalidade do município", nomes, key="pan_acima_mun",
                                 help="Um clique num município da tabela também troca. No PDF e no pacote do "
                                      "cenário vai a sazonalidade de todos.")
        est = estatisticas_dos_municipios(atual.focos, [escolhido], ano_inicio, cen.dia.year, cobertura(caminho))
        figura = grafico_sazonalidade(est[escolhido])
        mostrar_figura(figura, st if lado_a_lado else st.columns([3, 1])[0])
        plt.close(figura)


def mostrar_anomalias(figuras: dict, nome: str, cache: dict | None = None):
    """Os três mapas de anomalia em abas (os mesmos do PDF), com a nota de como ler."""
    st.markdown(f"### 🌡️ Anomalias de focos de calor — {nome}")
    if not any(f is not None for f in figuras.values()):
        st.info("Anomalias indisponíveis: são precisos pelo menos 3 anos completos de referência no período "
                "(e o limite do território).")
        return
    abas = st.tabs(["Quantidade", "Localização", "Combinada"])
    for aba, figura in zip(abas, figuras.values()):
        with aba:
            if figura is None:
                st.caption("Sem dados.")
            elif isinstance(figura, bytes):
                st.image(figura, width="stretch")
            else:
                mostrar_figura(figura, st.columns([3, 1])[0], cache)
    with st.expander("Como ler e metodologia"):
        st.markdown(texto_metodologia_markdown())


@st.cache_data(show_spinner=False, max_entries=8)
def anomalias_cenario_png(caminho: str, caminho_estado, estado: str, regiao: str, ultimo_dia, provisorios: tuple):
    """PNG dos três mapas de anomalia do estado/região (grade de 10 km), guardados entre as execuções."""
    cen = cenario_em_cache(caminho, estado, regiao, ultimo_dia, provisorios)
    limite = limite_da_regiao(caminho_estado, cen.sigla_uf, cen.regiao)
    figuras = figuras_anomalias(anomalias_do_cenario(cen, limite, focos_do_recorte(base_focos(caminho), estado,
                                                                                    regiao)[0]), limite, cen.nome)
    imagens = {tipo: png(figuras[f"anomalia_{tipo}"], dpi=110) if f"anomalia_{tipo}" in figuras else None
               for tipo in TIPOS_ANOMALIA}
    fechar_figuras(figuras)
    return imagens


def exportar_focos_geojson(caminho: str, estado: str, regiao: str, cen):
    """P29: todos os focos do estado/região entre duas datas, em GeoJSON, com os dados de cada ocorrência."""
    st.markdown("**🗺️ Focos de calor em GeoJSON**")
    inicio_base = cobertura(caminho)[0]
    d1, d2 = st.columns(2)
    inicio = d1.date_input("Data inicial", value=cen.inicio_semana, min_value=inicio_base,
                           max_value=cen.ultimo_dia_base, format="DD/MM/YYYY", key="geo_inicio")
    fim = d2.date_input("Data final", value=cen.dia, min_value=inicio_base, max_value=cen.ultimo_dia_base,
                        format="DD/MM/YYYY", key="geo_fim")
    if inicio > fim:
        st.warning("A data inicial é depois da final.")
        return
    chave = (estado, regiao, inicio, fim, cen.ultimo_dia_base)
    if st.button("⬇️ Baixar pontos de focos de calor", key="geo_gerar"):
        with st.spinner("Selecionando os focos..."):
            focos = focos_no_intervalo(base_focos(caminho), estado, regiao, inicio, fim)
            if len(focos) > MAX_FOCOS_GEOJSON:
                st.session_state["geo_focos"] = (chave, None, len(focos))
            else:
                descricao = (f"Focos de calor do satélite de referência AQUA_M-T (BDQueimadas/INPE) — {cen.nome}, "
                             f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}. Município, UC e TI pelo cruzamento do ponto com os "
                             f"limites oficiais. Gerado por {config.APP_NOME} v{config.APP_VERSAO}.")
                dados = json.dumps(geojson_focos(focos, cen.tipo_regiao, descricao), ensure_ascii=False)
                st.session_state["geo_focos"] = (chave, dados.encode("utf-8"), len(focos))
    guardado = st.session_state.get("geo_focos")
    if guardado and guardado[0] == chave:
        if guardado[1] is None:
            st.warning(f"{fmt_inteiro(guardado[2])} focos no intervalo: acima do limite de "
                       f"{fmt_inteiro(MAX_FOCOS_GEOJSON)} por arquivo. Diminua o intervalo ou escolha uma região.")
        else:
            st.download_button(f"⬇️ Baixar {fmt_inteiro(guardado[2])} focos (GeoJSON)", guardado[1],
                               file_name=f"Focos_{nome_arquivo(cen.nome)}_{inicio:%Y%m%d}_{fim:%Y%m%d}.geojson",
                               mime="application/geo+json", type="primary", on_click="ignore", key="geo_baixar")


def pagina_panorama():
    """Página inicial: estatísticas do estado, com filtro pelas regiões dele."""
    caminho = str(config.caminho_focos())
    df = base_focos(caminho)
    painel = dashboard_ativo()
    if painel:
        st.markdown(CSS_DASHBOARD, unsafe_allow_html=True)
    else:
        render_header("PANORAMA DO ESTADO")
    if not lateral_recolhida():
        st.sidebar.button("📄 Visualização legado" if modo_dashboard() else "📺 Visualização dashboard",
                          key="botao_modo", on_click=_alternar_modo, width="stretch",
                          help="Panorama em painel único (para TV) ou na visualização de sempre, em abas.")
    estados = estados_disponiveis()
    if df.empty or not estados:
        st.error(f"Nenhum dado de foco encontrado: a base {config.caminho_focos()} não existe. "
                 "Veja a página 🗂️ Bases de dados.")
        return
    anos = anos_disponiveis(df)
    nomes_estados = list(estados)
    if painel:
        panorama_dashboard(caminho, estados, anos)
        return
    c1, c2, c3 = st.columns([1.3, 2, 2.2])
    estado = c1.selectbox("Estado", nomes_estados, index=nomes_estados.index("Pará") if "Pará" in estados else 0,
                          key="pan_estado")
    regioes = opcoes_regioes(caminho, estado)
    tipo = TIPO_INTEGRACAO if estado == "Pará" else TIPO_IMEDIATA
    regiao = c2.selectbox(f"Filtrar por {tipo}", [TODAS, *regioes], key="pan_regiao")
    ano_inicio, ano_fim = c3.slider("Período", min_value=anos[0], max_value=anos[-1], value=(anos[0], anos[-1]),
                                    step=1, key="pan_anos")
    abas = st.tabs(["Cenário atual", "Municípios acima da máxima", "Anomalias do mês", f"Ano de {ano_fim}",
                    "Estatísticas (modelo INPE)"])
    secao_cenario_estado(caminho, estados[estado], estado, regiao, ano_inicio, ano_fim, abas)
    with abas[3]:
        with st.spinner("Calculando o panorama..."):
            pan = panorama_em_cache(caminho, estado, ano_inicio, ano_fim, regiao)
        i, fim = pan.indicadores, pan.fim_dados
        ate = f" até {fim:%d/%m}" if fim.year == ano_fim and fim < date(ano_fim, 12, 31) else ""

        st.markdown(f"### 📌 {pan.nome} — focos de calor em {ano_fim}{ate}")
        st.caption("Satélite de referência (AQUA_M-T); município de cada foco pelo cruzamento com o limite do IBGE. "
                   f"Comparações com o mesmo período (1º de janeiro{ate or ' a 31 de dezembro'}) dos anos anteriores "
                   "do período que a base cobre por inteiro.")
        k = st.columns(3)
        k[0].metric(f"Focos em {ano_fim}{ate}", fmt_inteiro(i["focos_ano_ate_data"]),
                    fmt_percentual(i["variacao_ano_anterior_pct"], sinal=True) + f" vs. {ano_fim - 1}"
                    if i["variacao_ano_anterior_pct"] is not None else None, delta_color="inverse")
        k[1].metric(f"Mesmo período de {ano_fim - 1}", fmt_inteiro(i["ano_anterior_ate_data"] or 0))
        k[2].metric("Média do mesmo período", fmt_inteiro(round(i["media_ate_data"])) if i["media_ate_data"] else "—",
                    fmt_percentual(i["variacao_media_pct"], sinal=True) + " (ano atual vs. média)"
                    if i["variacao_media_pct"] is not None else None, delta_color="inverse")
        k = st.columns(3)
        k[0].metric(f"Últimos 7 dias (até {fim:%d/%m})", fmt_inteiro(i["ultimos_7"]))
        k[1].metric("Últimos 30 dias", fmt_inteiro(i["ultimos_30"]))
        k[2].metric(f"Municípios com focos em {ano_fim}", fmt_inteiro(i["municipios_com_focos"]))

        caminho_estado = estados[estado]
        with st.spinner("Desenhando o mapa e a sazonalidade..."):
            imagens = figuras_panorama(caminho, caminho_estado, estado, ano_inicio, ano_fim, regiao)
        g1, g2 = st.columns([1.1, 1])
        with g1:
            st.markdown(f"#### 🗺️ Densidade dos focos em {ano_fim}")
            st.image(imagens["mapa"], width="stretch")
        with g2:
            st.markdown("#### 📈 Focos por ano")
            serie = pd.DataFrame({"Ano": [str(a) for a in pan.serie_anual], "Focos": list(pan.serie_anual.values())})
            st.altair_chart(alt.Chart(serie).mark_bar(color="#b52b27").encode(
                x=alt.X("Ano:N", axis=alt.Axis(labelAngle=-45)), y=alt.Y("Focos:Q", axis=alt.Axis(format="d")),
                tooltip=["Ano", alt.Tooltip("Focos:Q", format="d")]).properties(height=330), width="stretch")
            st.image(imagens["sazonalidade"], width="stretch")

        st.divider()
        if pan.regiao is None and not pan.por_regiao.empty:
            st.markdown(f"### 🧭 Focos por {pan.tipo_regiao} — {ano_fim}")
            tabela_com_recordes(pan.por_regiao, pan.recordes_regiao, pan.anos_recorde)
        st.markdown(f"### 📋 Municípios com mais focos em {ano_fim}{ate} — {pan.nome}")
        st.caption("Empate decidido pelos focos no último mês e, depois, na última semana dos dados.")
        recordes = pan.recordes_municipios
        tabela_com_recordes(pan.ranking_municipios.head(TOP_MUNICIPIOS),
                            recordes.head(TOP_MUNICIPIOS) if recordes is not None else None, pan.anos_recorde,
                            chave="pan_top", estado=estado)
        if len(pan.ranking_municipios) > TOP_MUNICIPIOS:
            with st.expander(f"Ver todos os {len(pan.ranking_municipios)} municípios com focos em {ano_fim}"):
                tabela_com_recordes(pan.ranking_municipios, recordes, pan.anos_recorde, altura=600,
                                    chave="pan_todos", estado=estado)


    with abas[4]:
        secao_estatisticas(pan.focos, pan.nome, ano_inicio, ano_fim, prefixo="pan_est_")


PAGINA_INICIAL = "🏠 Panorama do Estado"
PAGINAS = {
    "🏠 Panorama do Estado": pagina_panorama,
    "🔥 Diagnóstico": pagina_diagnostico,
    "🗂️ Bases de dados": pagina_bases,
}


# widgets do painel esquerdo que somem com ele recolhido (ou vão para o título do dashboard): reatribuir no
# começo da execução impede o Streamlit de apagar o valor quando o widget não é desenhado
CHAVES_DO_PAINEL = ("navegacao", "diag_tipo", "diag_estado", "diag_municipio", "diag_anos", "diag_download",
                    "pan_estado", "pan_regiao", "pan_anos")


def trilho_de_icones():
    """Painel esquerdo recolhido (dashboard): uma coluna de botões-ícone que funcionam como os do painel aberto."""
    st.markdown(CSS_LATERAL_RECOLHIDA, unsafe_allow_html=True)
    atual = st.session_state.get("navegacao", PAGINA_INICIAL)
    st.markdown(f"<style>.st-key-icone_pagina_{list(PAGINAS).index(atual)} button {{ background: #E3EEEC; "
                "border: 2px solid #0D6E7D; }</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.button("☰", key="botao_lateral", on_click=_alternar_lateral, help="Mostrar todo o painel esquerdo")
        st.divider()
        for i, pagina in enumerate(PAGINAS):
            st.button(pagina.split(" ", 1)[0], key=f"icone_pagina_{i}", help=pagina.split(" ", 1)[1],
                      on_click=_ir_para, args=(pagina,))
        st.divider()
        st.button("📄", key="botao_modo", on_click=_alternar_modo, help="Voltar à visualização legado (em abas)")
        if atual == PAGINA_DIAGNOSTICO:
            st.button("🚀", key="icone_processar", type="primary", on_click=_processar_pelo_icone,
                      help="Processar o diagnóstico do município escolhido no título")


def main():
    for chave in CHAVES_DO_PAINEL:
        if chave in st.session_state:
            st.session_state[chave] = st.session_state[chave]
    recolhida = lateral_recolhida()
    if recolhida:
        trilho_de_icones()
        pagina = st.session_state.get("navegacao", PAGINA_INICIAL)
    else:
        if dashboard_ativo():
            st.sidebar.button("« Recolher o painel", key="botao_lateral", on_click=_alternar_lateral,
                              help="Deixar só os ícones")
        pagina = st.sidebar.radio("Navegação", list(PAGINAS), label_visibility="collapsed", key="navegacao")
        st.sidebar.divider()
    PAGINAS[pagina]()
    acompanhar_estado_do_vento()
    if aviso := st.session_state.pop("aviso_mapa", None):
        st.toast(aviso, icon="⚠️")
    # sempre no rodapé do painel esquerdo (o CSS empurra este bloco para baixo)
    with st.sidebar, st.container(key="rodape_lateral"):
        ouvinte_duplo_clique()
        if config.caminho_focos().exists():
            painel_atualizacao(recarregar_ao_mudar=PAGINAS[pagina] is not pagina_diagnostico,
                               compacto=lateral_recolhida())
        elif recolhida:
            with st.popover("⋯", help="Sobre o sistema"):
                conteudo_sobre()
        else:
            with st.expander("⋯  Sobre o sistema"):
                conteudo_sobre()
    render_footer()

main()
