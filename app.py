# -*- coding: utf-8 -*-
"""AutoSIMD-FOCOS — interface Streamlit (docs/02).

Toda regra fica em ``core/``; aqui só há telas. Fluxo: escolher o território e o período na
barra lateral → processar → ver indicadores, gráficos, mapas e tabelas → baixar o pacote .zip.

    python -m streamlit run app.py
"""

import base64
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
from core.graficos_estatisticas import interativo_acumulado, interativo_comparativo, interativo_nowcast
from core.grade import grade_do_territorio, nota_grade
from core.kernel import DESVIO_KERNEL_KM
from core.graficos_estatisticas import grafico_sazonalidade
from core.mapas import mapa_dispersao, mapa_recentes
from core.panorama import TODAS, limite_da_regiao, panorama_estado, regioes_do_estado
from core.regioes import TIPO_IMEDIATA, TIPO_INTEGRACAO
from core.nowcast import nowcast_territorio
from core.produto import fechar_figuras, figuras_territorio, pacote, png
from core.territorios import (
    area_km2, areas_protegidas_no_territorio, carregar_areas_protegidas, estados_disponiveis,
    geometria_area_protegida, geometria_municipio,
)
from core.texto import fmt_densidade, fmt_inteiro, fmt_numero, fmt_percentual, fmt_posicao

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
    .main-header { text-align: center; font-family: Arial, sans-serif; line-height: 1.4; margin-bottom: 25px; }
    .main-header h2 { font-size: 22px; margin: 0; font-weight: bold; }
    .main-header h3 { font-size: 17px; margin: 2px 0; font-weight: normal; }
    .main-header .sub { font-size: 18px; margin-top: 6px; color: #E53935; font-weight: bold; }
    .main-header .ref { font-size: 24px; margin-top: 4px; color: #1E88E5; font-weight: bold; }
    .footer-container {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: var(--background-color, #FFFFFF);
        border-top: 1px solid var(--secondary-background-color, #CCCCCC);
        padding: 8px 30px; font-size: 12px; color: var(--text-color, #444444);
        display: flex; justify-content: space-between; align-items: center; z-index: 999;
    }
    .stApp { padding-bottom: 70px; }
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
                <h2><b>{config.APP_NOME}</b></h2>
                <div class="sub">DIAGNÓSTICO AUTOMÁTICO DE FOCOS DE CALOR</div>
                <div class="ref">{subtitulo.upper()}</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        if config.LOGO_CBM_CEDEC.exists():
            st.image(str(config.LOGO_CBM_CEDEC), width=110)
    st.divider()


def render_footer():
    st.markdown(f"""
        <div class="footer-container">
            <div><b>RELATÓRIO AUTOMÁTICO DE FOCOS DE CALOR — ANÁLISE TERRITORIAL</b><br/>
            CBMPA | Coordenadoria Estadual de Proteção e Defesa Civil — DGR / Fonte: BDQueimadas INPE</div>
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
                   opcoes_regioes, panorama_em_cache, figuras_panorama):
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


@st.fragment(run_every=5)
def painel_atualizacao(recarregar_ao_mudar: bool):
    """Situação da base e da busca no INPE (barra lateral); reexecuta sozinho a cada 5 s.

    Quando a base muda, os dados em memória são descartados; no Panorama e em Bases de dados a página
    recarrega; no Diagnóstico só avisa, para não apagar a análise aberta.
    """
    atualizador = obter_atualizador(str(config.BASES_DIR))
    estado = atualizador.instantaneo()
    versao = versao_da_base(config.BASES_DIR)
    vista = st.session_state.setdefault("versao_base_vista", versao)
    if versao != vista and not estado["em_execucao"]:
        st.session_state["versao_base_vista"] = versao
        limpar_caches_da_base()
        if recarregar_ao_mudar:
            st.rerun(scope="app")
        st.toast("🛰️ Focos novos incorporados à base — valem para a próxima análise processada.")

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
    st.toggle(f"Nowcast (busca a cada {CICLO_NOWCAST_H} h)", value=atualizador.nowcast, key="toggle_nowcast",
              on_change=_ao_mudar_nowcast,
              help=f"Ligado: busca focos novos no INPE agora e depois a cada {CICLO_NOWCAST_H} horas, em segundo "
                   "plano. Desligado: só a busca de quando o programa abre. A escolha fica salva.")


def mostrar_figura(figura, coluna=st):
    if figura is not None:
        coluna.pyplot(figura, width="stretch")


def tabela(df: pd.DataFrame, **kwargs):
    st.dataframe(df, hide_index=True, width="stretch", **kwargs)


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


def botao_pacote(pacote_, rotulo: str):
    st.download_button(rotulo, pacote_.conteudo, file_name=pacote_.nome, mime="application/zip", type="primary",
                       width="stretch", on_click="ignore")


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
    """Controles da barra lateral; None se faltar base de municípios."""
    caminho = str(config.caminho_focos())
    st.sidebar.title("🛠️ Parâmetros da Análise")
    tipo = st.sidebar.radio("🎯 Escolha o Nível de Análise:", config.TIPOS_ANALISE)
    p = {"tipo": tipo, "estado": None, "caminho_estado": None}

    if tipo == config.TIPO_MUNICIPIO:
        estados = estados_disponiveis()
        if not estados:
            st.sidebar.error(f"Nenhum arquivo GeoJSON de estado encontrado em {config.pasta_municipios()}.")
            return None
        nomes_estados = list(estados)
        p["estado"] = st.sidebar.selectbox("Selecione o Estado (UF):", nomes_estados,
                                           index=nomes_estados.index("Pará") if "Pará" in estados else 0)
        p["caminho_estado"] = estados[p["estado"]]
        municipios = opcoes_municipios(caminho, p["estado"])
        p["nome"] = st.sidebar.selectbox("📍 Selecione o Município:", municipios or ["SELECIONE"])
    else:
        rotulo = ("🌲 Selecione a Unidade de Conservação (UC):" if tipo == config.TIPO_UC
                  else "🏹 Selecione a Terra Indígena (TI):")
        p["nome"] = st.sidebar.selectbox(rotulo, opcoes_areas(caminho, config.SIGLA_TIPO[tipo])) or "SELECIONE"

    anos = anos_disponiveis(df)
    p["ano_inicio"], p["ano_fim"] = st.sidebar.slider("📅 Intervalo de Anos:", min_value=anos[0], max_value=anos[-1],
                                                      value=(anos[0], anos[-1]), step=1)
    st.sidebar.divider()
    st.sidebar.subheader("Opções de Download")
    p["download_automatico"] = st.sidebar.checkbox(
        "Baixar automaticamente o pacote completo (Relatório PDF, Metadados e Imagens PNG)", value=True)
    p["processar"] = st.sidebar.button("🚀 Processar Diagnóstico Completo", type="primary", width="stretch")
    return p


def sobre():
    st.sidebar.divider()
    with st.sidebar.expander("ℹ️ Sobre o Sistema & Desenvolvedor"):
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
    with st.spinner("Processando geodados, sazonalidade e gerando mapas..."):
        est = estatisticas_territorio(diag.focos, diag.municipio, diag.ano_inicio, diag.ano_fim, cobertura(caminho),
                                      parametros_do_relatorio(chave))
        figuras = figuras_territorio(diag, est, nowcast)
    if diag.poligono is None:
        st.warning(f"Limite de {diag.nome} não encontrado: mapas sem contorno e densidade indisponível.", icon="🗺️")

    if municipio:
        resumo_municipio(diag, p)
    else:
        resumo_area(diag)
    if nowcast is not None:
        st.divider()
        secao_nowcast(diag, nowcast)

    st.divider()
    st.markdown("### 📈 Diagnóstico Geral e Análise de Sazonalidade")
    if municipio:
        g1, g2 = st.columns(2)
        mostrar_figura(figuras["top_estado"], g1)
        mostrar_figura(figuras["evolucao"], g2)
    else:
        mostrar_figura(figuras["evolucao"], st.columns([1, 1])[0])
    st.markdown("#### 🗓️ Padrão Sazonal de Incidência (média mensal, p10–p90 e ano de referência)")
    mostrar_figura(figuras["sazonalidade"])

    if municipio:
        st.divider()
        st.markdown("### 📋 Tabelas de Ranking e Comparativo Regional")
        t1, t2 = st.columns(2)
        with t1:
            st.markdown(f"**Top {len(diag.ranking_estado)} {diag.ano_fim} - Estado**")
            tabela(diag.ranking_estado)
        with t2:
            st.markdown(f"**Comparativo na {diag.titulo_regiao} ({diag.ano_fim})**")
            if diag.ranking_regiao.empty:
                st.caption("Região do município não identificada.")
            else:
                tabela(diag.ranking_regiao)

    st.divider()
    st.markdown("### 🗺️ Mapeamento Espacial e Sazonalidade Trimestral")
    st.caption(f"Mapas 1, 2 e 4: densidade de kernel gaussiano (desvio de {fmt_numero(DESVIO_KERNEL_KM)} km); "
               "cada foco marcado com uma cruz preta.")
    mostrar_figura(figuras["mapa_dispersao"])
    if municipio:
        if diag.areas:
            st.markdown("**🌲 Unidades de Conservação e Terras Indígenas no Município**")
            tabela(diag.tabela_areas)
        else:
            st.caption("Nenhuma Unidade de Conservação ou Terra Indígena da base sobreposta a este município.")
    mostrar_figura(figuras["mapa_densidade"])
    mostrar_figura(figuras["mapa_recorrencia"])
    if figuras["mapa_trimestral"] is not None:
        st.markdown("#### 🔄 Migração Espacial Sazonal (densidade de kernel por trimestre)")
        mostrar_figura(figuras["mapa_trimestral"])

    rankings_areas(diag)

    st.divider()
    secao_estatisticas(diag.focos, diag.municipio, diag.ano_inicio, diag.ano_fim, chave)

    st.divider()
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

    st.divider()
    st.markdown("### 📥 Central de Exportação do Pacote Completo")
    if diag.focos.empty:
        st.warning("Sem dados para exportar no período")
    else:
        with st.spinner("Montando o relatório PDF e o pacote..."):
            pacote_ = pacote(diag, figuras, est, nowcast)
        if st.session_state.pop("baixar_agora", False):
            disparar_download_automatico(pacote_.conteudo, pacote_.nome)
            st.success("✅ Diagnóstico concluído! O download do pacote completo em ZIP foi iniciado automaticamente.")
        else:
            st.success("✅ Diagnóstico concluído com sucesso!")
        botao_pacote(pacote_, "📦 BAIXAR PACOTE COMPLETO (.ZIP) — PDF, Excel, GeoJSON e Imagens PNG")
        st.caption("O pacote ZIP contém o Relatório PDF Oficial diagramado, Planilha Excel com séries temporais e "
                   "as estatísticas no modelo INPE, Grade QGIS .geojson, tabelas em CSV e todas as imagens/mapas "
                   "em formato PNG.")
    fechar_figuras(figuras)


# ------------------------------------------------- Cenário atual (nowcast)

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
    figura = mapa_recentes(recentes, diag.poligono, diag.municipio, ultimo, dias, getattr(diag, "areas", None))
    mostrar_figura(figura)
    plt.close(figura)
    with st.expander(f"Lista dos {fmt_inteiro(len(recentes))} focos"):
        tabela(recentes.assign(data=[d.strftime("%d/%m/%Y") for d in recentes["data"]])
               .drop(columns="dias_atras").rename(columns={"data": "Data", "idade": "Idade", "lat": "Latitude",
                                                           "lon": "Longitude"}))
    st.caption("No relatório PDF e no pacote, o mapa mostra os últimos 7 dias.")


# ------------------------------------------- Estatísticas (modelo INPE)

COR_TABELA_MINIMO = "background-color: #FFD54F; font-weight: bold"
COR_TABELA_MAXIMO = "background-color: #E53935; color: white; font-weight: bold"
COR_LINHA_RESUMO = {"Mínimo": "background-color: #FBC02D; font-weight: bold",
                    "Média": "background-color: #FB8C00; font-weight: bold",
                    "Máximo": "background-color: #E53935; color: white; font-weight: bold"}
ABAS_COMPARATIVOS = {"Comparativo mensal": "mensal", "Comparativo semanal": "semanal",
                     "Comparativo 1º semestre": "semestre1", "Comparativo 2º semestre": "semestre2"}


def chave_analise(p: dict) -> tuple:
    return p["tipo"], p["estado"], p["nome"], p["ano_inicio"], p["ano_fim"]


def parametros_do_relatorio(chave: tuple) -> ParametrosEstatisticas:
    """Parâmetros aplicados ao PDF/pacote nesta análise (padrão até o usuário aplicar outros)."""
    guardado = st.session_state.get("parametros_relatorio")
    return guardado[1] if guardado and guardado[0] == chave else ParametrosEstatisticas()


def estilo_inpe(tabela_: pd.DataFrame, linhas_destaque: list[str]):
    """Menor valor de cada coluna em amarelo e maior em vermelho; linhas Mínimo/Média/Máximo coloridas."""
    extremos = extremos_por_coluna(tabela_, linhas_destaque)

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
                       prefixo: str = "est_"):
    """Estatísticas no modelo do Programa Queimadas/INPE; os controles só refazem esta seção.

    ``chave`` = análise do diagnóstico (oferece aplicar os parâmetros ao relatório); None no Panorama.
    """
    st.markdown("### 📊 Estatísticas de Focos Ativos (modelo Programa Queimadas/INPE)")
    caminho = str(config.caminho_focos())
    parametros = controles_estatisticas(ano_inicio, ano_fim, prefixo)
    est = estatisticas_territorio(focos, nome, ano_inicio, ano_fim, cobertura(caminho), parametros)
    for nota in notas(est):
        st.caption(nota)

    abas = st.tabs(["Mês a mês", "Dia a dia", *ABAS_COMPARATIVOS, "Acumulado mensal"])
    with abas[0]:
        st.markdown(f"**Total de focos detectados em cada mês ({ano_inicio}–{ano_fim})**")
        st.dataframe(estilo_inpe(tabela_mensal_exibicao(est), [str(a) for a in est.anos_estatistica]),
                     width="stretch", height=min(40 + 35 * (len(est.mensal) + 3), 900))
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
        intensos = (f"Últimos {len(est.anos_intensidade)} anos completos: mais intenso **{est.ano_mais_intenso}**, "
                    f"menos intenso **{est.ano_menos_intenso}**." if est.anos_intensidade
                    else "Sem anos completos antes do ano de referência para indicar o mais e o menos intenso.")
        st.markdown(intensos)
        with st.expander("Ver tabela"):
            st.dataframe(tabela_acumulado_exibicao(est).style.format(lambda v: "-" if pd.isna(v) else fmt_numero(v)),
                         width="stretch")
    st.caption("Passe o mouse para ver os valores, use a roda do mouse para aproximar e clique na legenda para "
               "destacar uma série.")

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
    render_header(f"{p['tipo']}: {p['nome']}")
    if p["processar"]:
        st.session_state["analise"] = chave_analise(p)
        st.session_state["baixar_agora"] = p["download_automatico"]
        st.session_state.pop("parametros_relatorio", None)
        for chave in [c for c in st.session_state if str(c).startswith("est_")]:
            del st.session_state[chave]          # controles das estatísticas voltam ao padrão
    if st.session_state.get("analise") != chave_analise(p):
        st.info("👈 Defina o território e o período no painel à esquerda e clique em "
                "**Processar Diagnóstico Completo**.")
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


def pagina_panorama():
    """Página inicial: estatísticas do estado, com filtro pelas regiões dele."""
    caminho = str(config.caminho_focos())
    df = base_focos(caminho)
    render_header("PANORAMA DO ESTADO")
    estados = estados_disponiveis()
    if df.empty or not estados:
        st.error(f"Nenhum dado de foco encontrado: a base {config.caminho_focos()} não existe. "
                 "Veja a página 🗂️ Bases de dados.")
        return
    anos = anos_disponiveis(df)
    nomes_estados = list(estados)
    c1, c2, c3 = st.columns([1.3, 2, 2.2])
    estado = c1.selectbox("Estado", nomes_estados, index=nomes_estados.index("Pará") if "Pará" in estados else 0,
                          key="pan_estado")
    regioes = opcoes_regioes(caminho, estado)
    tipo = TIPO_INTEGRACAO if estado == "Pará" else TIPO_IMEDIATA
    regiao = c2.selectbox(f"Filtrar por {tipo}", [TODAS, *regioes], key="pan_regiao")
    ano_inicio, ano_fim = c3.slider("Período", min_value=anos[0], max_value=anos[-1], value=(anos[0], anos[-1]),
                                    step=1, key="pan_anos")
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
        tabela(pan.por_regiao)
    st.markdown(f"### 📋 Municípios com mais focos em {ano_fim}{ate} — {pan.nome}")
    st.caption("Empate decidido pelos focos no último mês e, depois, na última semana dos dados.")
    tabela(pan.ranking_municipios)

    st.divider()
    secao_estatisticas(pan.focos, pan.nome, ano_inicio, ano_fim, prefixo="pan_est_")


PAGINAS = {
    "🏠 Panorama do Estado": pagina_panorama,
    "🔥 Diagnóstico": pagina_diagnostico,
    "🗂️ Bases de dados": pagina_bases,
}


def main():
    pagina = st.sidebar.radio("Navegação", list(PAGINAS), label_visibility="collapsed")
    st.sidebar.divider()
    if config.caminho_focos().exists():
        with st.sidebar:
            painel_atualizacao(recarregar_ao_mudar=PAGINAS[pagina] is not pagina_diagnostico)
        st.sidebar.divider()
    PAGINAS[pagina]()
    sobre()
    render_footer()


main()
