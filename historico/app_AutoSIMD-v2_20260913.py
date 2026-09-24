from datetime import datetime
import glob
import importlib.util
import io
import json
import os
import re
import unicodedata
import zipfile
import base64
from shapely.geometry import shape

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from PIL import Image as PILImage
import streamlit as st
import streamlit.components.v1 as components

# ReportLab para PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ----------------------------------------------------------------------
# Configurações de Caminhos e Módulos
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CORE_DIR = os.path.join(BASE_DIR, "core")
DATA_DIR = os.path.join(BASE_DIR, "data")

PATH_LOGOS_DIR = os.path.join(CORE_DIR, "logos")
PATH_BRASAO_PARA = os.path.join(
    PATH_LOGOS_DIR, "ChatGPT Image 13 de set. de 2026, 23_15_28.png"
)
PATH_CBM_CEDEC = os.path.join(PATH_LOGOS_DIR, "CBM-CEDEC.png")

FOCOS_DIR = os.path.join(DATA_DIR, "focos")
PATH_FOCOS_PARQUET = os.path.join(FOCOS_DIR, "bdqueimadas_consolidado.parquet")

GEOJSON_BASE_DIR = os.path.join(DATA_DIR, "geojson")
TI_GEOJSON_PATH = os.path.join(GEOJSON_BASE_DIR, "TI-BR.geojson")
UC_GEOJSON_PATH = os.path.join(GEOJSON_BASE_DIR, "UC-BR.geojson")
GEOJSON_DIR = os.path.join(GEOJSON_BASE_DIR, "mun-br")

PATH_KML_DIR = os.path.join(DATA_DIR, "kml")
PATH_DICIONARIO_REGIOES = os.path.join(
    CORE_DIR, "dicionario_municipios-regioes.py"
)

# Carregamento seguro do dicionário de regiões
MAPA_MUNICIPIO_REGIAO = {}
if os.path.exists(PATH_DICIONARIO_REGIOES):
    try:
        spec = importlib.util.spec_from_file_location("dicionario_regioes", PATH_DICIONARIO_REGIOES)
        dict_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dict_module)
        MAPA_MUNICIPIO_REGIAO = getattr(dict_module, "MAPA_MUNICIPIO_REGIAO", {})
    except Exception as e:
        st.warning(f"Não foi possível carregar o dicionário de regiões: {e}")

def remover_acentos(texto):
    if not texto:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )

LOOKUP_REGIAO = {m.upper(): r for m, r in MAPA_MUNICIPIO_REGIAO.items()}
for m, r in MAPA_MUNICIPIO_REGIAO.items():
    LOOKUP_REGIAO[remover_acentos(m.upper())] = r

def get_regiao_municipio(mun_name):
    if not mun_name:
        return "Não Identificada"
    mun_u = mun_name.strip().upper()
    return LOOKUP_REGIAO.get(mun_u, LOOKUP_REGIAO.get(remover_acentos(mun_u), "Não Identificada"))

def extrair_mes_data(props):
    """Extrai o mês (1-12) das propriedades do GeoJSON cobrindo múltiplos formatos e chaves do BDQueimadas/INPE."""
    chaves_data = ["DataHora", "datahora", "data_hora_gmt", "data", "date", "DATE", "acq_date", "dt"]
    val_str = None
    
    for k in chaves_data:
        if k in props and props[k]:
            val_str = str(props[k])
            break
            
    if not val_str:
        for k, v in props.items():
            if ("data" in k.lower() or "date" in k.lower()) and v:
                val_str = str(v)
                break

    if not val_str:
        return None

    # Padrão YYYY-MM-DD ou YYYY/MM/DD
    m = re.search(r"\d{4}[-/](\d{2})[-/]\d{2}", val_str)
    if m:
        return int(m.group(1))

    # Padrão DD/MM/YYYY ou DD-MM-YYYY
    m = re.search(r"\d{2}[-/](\d{2})[-/]\d{4}", val_str)
    if m:
        return int(m.group(1))

    return None

def disparar_download_automatico(data_bytes: bytes, filename: str = "pacote_completo.zip"):
    """Injeta JavaScript no browser para disparar o download automaticamente."""
    b64 = base64.b64encode(data_bytes).decode()
    js_code = f"""
        <script>
            var a = document.createElement('a');
            a.href = 'data:application/zip;base64,{b64}';
            a.download = '{filename}';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        </script>
    """
    components.html(js_code, height=0, width=0)

def gerar_pacote_completo(
    pdf_bytes: bytes,
    metadados_str: str,
    fig_mapa: plt.Figure,
    fig_grafico: plt.Figure,
) -> bytes:
    """Gera o arquivo ZIP contendo PDF, JSON e as imagens dos gráficos/mapas em PNG."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("relatorio_diagnostico.pdf", pdf_bytes)
        zip_file.writestr("metadados.json", metadados_str)

        img_mapa_io = io.BytesIO()
        fig_mapa.savefig(img_mapa_io, format="png", bbox_inches="tight", dpi=300)
        zip_file.writestr("mapa_focos.png", img_mapa_io.getvalue())

        img_grafico_io = io.BytesIO()
        fig_grafico.savefig(img_grafico_io, format="png", bbox_inches="tight", dpi=300)
        zip_file.writestr("grafico_focos.png", img_grafico_io.getvalue())

    return zip_buffer.getvalue()

def sanitizar_nome_arquivo(valor):
    valor_ascii = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii")
    valor_ascii = re.sub(r"[^A-Za-z0-9_-]+", "_", valor_ascii).strip("_")
    return valor_ascii or "SELECIONADO"

def exportar_pacote_analise(
    df_filtrado,
    nome_alvo,
    tipo_analise,
    ano_inicio,
    ano_fim,
    poligono_alvo=None,
    figuras_mapa=None,
    figuras_grafico=None,
):
    """Monta o pacote comum de exportação para município, UC e TI."""
    tipo_abreviado = {
        "Estado / Município": "MUN",
        "Unidade de Conservação (UC)": "UC",
        "Terra Indígena (TI)": "TI",
    }.get(tipo_analise, sanitizar_nome_arquivo(tipo_analise))
    alvo_arquivo = sanitizar_nome_arquivo(nome_alvo)
    nome_base = f"Diagnostico_{tipo_abreviado}_{alvo_arquivo}"
    grade_json = generate_qgis_grid_geojson(df_filtrado, poligono_alvo)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            f"dados_{tipo_abreviado}_{alvo_arquivo}.csv",
            df_filtrado.to_csv(index=False).encode("utf-8"),
        )
        zip_file.writestr(
            "metadados.json",
            json.dumps({
                "nome_alvo": nome_alvo,
                "tipo_analise": tipo_analise,
                "ano_inicio": ano_inicio,
                "ano_fim": ano_fim,
                "total_focos": len(df_filtrado),
            }, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        nome_arquivo_grade = f"grade_10x10km_{re.sub(r'[^a-zA-Z0-9_]', '_', nome_alvo)}.geojson"
        zip_file.writestr(nome_arquivo_grade, json.dumps(grade_json, indent=2).encode("utf-8"))

        for coluna, nome_ranking in (
            ("NM_MUN", "ranking_municipios.csv"),
            ("UC", "ranking_ucs.csv"),
            ("TI", "ranking_tis.csv"),
        ):
            valores_invalidos = {"", "NONE", "NULL", "NAN", "N/A"}
            ranking = (
                df_filtrado.loc[~df_filtrado[coluna].isin(valores_invalidos), coluna]
                .value_counts()
                .rename_axis(coluna)
                .reset_index(name="Focos de Calor")
            )
            zip_file.writestr(nome_ranking, ranking.to_csv(index=False).encode("utf-8"))

        for prefixo, figuras in (("mapas", figuras_mapa), ("graficos", figuras_grafico)):
            for indice, figura in enumerate(figuras or [], start=1):
                if figura is None:
                    continue
                imagem = io.BytesIO()
                figura.savefig(imagem, format="png", bbox_inches="tight", dpi=180)
                zip_file.writestr(f"{prefixo}/{prefixo}_{indice}.png", imagem.getvalue())

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), f"{nome_base}_{ano_inicio}_{ano_fim}.zip"

# Configuração do Streamlit
st.set_page_config(
    page_title="AutoSIMD - FOCOS v2.0",
    page_icon="🔥",
    layout="wide",
    menu_items={
        "Get Help": "https://github.com/engamblobs/Autosimd-Focos",
        "Report a bug": "https://github.com/engamblobs/Autosimd-Focos/issues",
        "About": """
        ### AutoSIMD - FOCOS (v2.0)
        Desenvolvido por **Bruno Lobão da Silva**  
        *Engenheiro Ambiental | CBMPA | Defesa Civil Pará (DGR/SIMD)*
        """,
    },
)

# ----------------------------------------------------------------------
# CSS Adaptativo para Modo Claro / Escuro e Layout
# ----------------------------------------------------------------------
st.markdown("""
    <style>
    .main-header {
        text-align: center;
        font-family: Arial, sans-serif;
        line-height: 1.4;
        margin-bottom: 25px;
    }
    .main-header h2 { font-size: 22px; margin: 0; color: var(--text-color, #111111); font-weight: bold; }
    .main-header h3 { font-size: 17px; margin: 2px 0; color: var(--text-color, #333333); font-weight: normal; }
    .main-header .sub { font-size: 18px; margin-top: 6px; color: #E53935; font-weight: bold; }
    .main-header .mun { font-size: 24px; margin-top: 4px; color: #1E88E5; font-weight: bold; }
    
    .footer-container {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: var(--background-color, #FFFFFF);
        border-top: 1px solid var(--secondary-background-color, #CCCCCC);
        padding: 8px 30px;
        font-size: 12px;
        color: var(--text-color, #444444);
        display: flex;
        justify-content: space-between;
        align-items: center;
        z-index: 999;
    }
    .stApp { padding-bottom: 70px; }

    @media print {
        [data-testid="stSidebar"],
        .stButton,
        .stDownloadButton,
        button,
        header,
        footer,
        .footer-container {
            display: none !important;
        }
        .stApp {
            padding-bottom: 0 !important;
            background-color: #ffffff !important;
            color: #000000 !important;
        }
        .main .block-container {
            padding: 10px !important;
            max-width: 100% !important;
        }
        .element-container, img, div {
            page-break-inside: avoid;
        }
    }
    </style>
""", unsafe_allow_html=True)

def render_header(alvo_sel="SELECIONE"):
    col1, col2, col3 = st.columns([1.2, 5, 1.2])
    with col1:
        if os.path.exists(PATH_BRASAO_PARA):
            st.image(PATH_BRASAO_PARA, width=90)
    with col2:
        st.markdown(f"""
            <div class="main-header">
                <h2>Corpo de Bombeiros Militar do Pará</h2>
                <h3>Coordenadoria Estadual de Proteção e Defesa Civil</h3>
                <h3>Divisão de Gestão de Risco - DGR</h3>
                <h2><b>AutoSIMD - FOCOS</b></h2>
                <div class="sub">DIAGNÓSTICO AUTOMÁTICO DE FOCOS DE CALOR</div>
                <div class="mun">{alvo_sel.upper()}</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        if os.path.exists(PATH_CBM_CEDEC):
            st.image(PATH_CBM_CEDEC, width=110)
    st.divider()

def render_footer():
    st.markdown("""
        <div class="footer-container">
            <div>
                <b>RELATÓRIO AUTOMÁTICO DE FOCOS DE CALOR — ANÁLISE TERRITORIAL</b><br/>
                CBMPA | Coordenadoria Estadual de Proteção e Defesa Civil — DGR / Fonte: BDQueimadas INPE
            </div>
            <div style="text-align: right;">
                AutoSIMD - FOCOS © 2026
            </div>
        </div>
    """, unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Processamento de Dados Geospaciais
# ----------------------------------------------------------------------
@st.cache_data
def carregar_focos_consolidados(path_focos_parquet=PATH_FOCOS_PARQUET):
    """Carrega os focos consolidados; as geometrias ficam restritas aos mapas."""
    colunas = ["lon", "lat", "ano", "mes", "data", "NM_MUN", "NM_UF", "SIGLA_UF", "UC", "TI"]
    if not os.path.exists(path_focos_parquet):
        return pd.DataFrame(columns=colunas)

    df = pd.read_parquet(path_focos_parquet, columns=colunas)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").fillna(0).astype(int)
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").fillna(0).astype(int)
    for coluna in ["NM_MUN", "NM_UF", "SIGLA_UF", "UC", "TI"]:
        df[coluna] = df[coluna].fillna("").astype(str).str.strip().str.upper()
    return df

@st.cache_data
def carregar_geometria_alvo(caminho_geojson, campos_chave, valor_busca):
    """Carrega somente o polígono do alvo para desenhar os mapas."""
    if not os.path.exists(caminho_geojson):
        return None
    valor_normalizado = valor_busca.strip().upper()
    with open(caminho_geojson, "r", encoding="utf-8") as f:
        data = json.load(f)
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        for campo in campos_chave:
            if str(props.get(campo, "")).strip().upper() == valor_normalizado:
                return shape(feat.get("geometry"))
    return None

def criar_dataframe_ranking(contagem_dict, coluna_nome):
    """Converte uma contagem de áreas protegidas em tabela ordenada."""
    colunas = ["Posição", coluna_nome, "Focos de Calor", "Participação (%)"]
    if not contagem_dict:
        return pd.DataFrame(columns=colunas)

    df = pd.DataFrame(
        list(contagem_dict.items()),
        columns=[coluna_nome, "Focos de Calor"],
    ).sort_values("Focos de Calor", ascending=False).reset_index(drop=True)
    total_focos = df["Focos de Calor"].sum()
    df["Participação (%)"] = (df["Focos de Calor"] / total_focos * 100).round(2)
    df.insert(0, "Posição", range(1, len(df) + 1))
    return df

def render_rankings_areas_protegidas(df_focos, ano_inicio, ano_fim):
    """Exibe rankings de UC e TI usando os atributos dos focos processados."""
    df_periodo = df_focos[df_focos["ano"].between(ano_inicio, ano_fim)]
    valores_invalidos = {"", "NONE", "NULL", "NAN", "N/A"}
    uc_counts = df_periodo.loc[
        ~df_periodo["UC"].isin(valores_invalidos), "UC"
    ].value_counts().to_dict()
    ti_counts = df_periodo.loc[
        ~df_periodo["TI"].isin(valores_invalidos), "TI"
    ].value_counts().to_dict()
    df_ranking_uc = criar_dataframe_ranking(uc_counts, "Unidade de Conservação (UC)")
    df_ranking_ti = criar_dataframe_ranking(ti_counts, "Terra Indígena (TI)")

    st.divider()
    st.markdown("### 🏆 Ranking de Focos por Áreas Protegidas")
    tab_uc, tab_ti = st.tabs(["🌲 Ranking de UCs", "🏹 Ranking de TIs"])

    with tab_uc:
        if df_ranking_uc.empty:
            st.info("Nenhum foco registrado em Unidades de Conservação no período selecionado.")
        else:
            st.dataframe(
                df_ranking_uc,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Focos de Calor": st.column_config.NumberColumn(format="%d"),
                    "Participação (%)": st.column_config.NumberColumn(format="%.2f %%"),
                },
            )

    with tab_ti:
        if df_ranking_ti.empty:
            st.info("Nenhum foco registrado em Terras Indígenas no período selecionado.")
        else:
            st.dataframe(
                df_ranking_ti,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Focos de Calor": st.column_config.NumberColumn(format="%d"),
                    "Participação (%)": st.column_config.NumberColumn(format="%.2f %%"),
                },
            )

def find_and_parse_kml(municipio_alvo, kml_dir=PATH_KML_DIR):
    if not os.path.exists(kml_dir):
        return []
    target_norm = remover_acentos(municipio_alvo.strip().lower())
    matched_path = None
    for filename in os.listdir(kml_dir):
        if filename.lower().endswith(".kml"):
            name_part = filename.replace("NM_MUN_", "").replace(".kml", "").replace(".KML", "")
            if remover_acentos(name_part.strip().lower()) == target_norm:
                matched_path = os.path.join(kml_dir, filename)
                break
    if not matched_path:
        return []
    polygons = []
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(matched_path)
        root = tree.getroot()
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
        for coord_elem in root.iter('coordinates'):
            text = coord_elem.text
            if not text:
                continue
            coords = []
            for pt in text.strip().split():
                parts = pt.split(',')
                if len(parts) >= 2:
                    try:
                        coords.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        pass
            if len(coords) >= 3:
                polygons.append(coords)
    except Exception:
        pass
    return polygons

def draw_kml_boundary(ax, kml_polygons):
    if not kml_polygons:
        return None
    all_lons, all_lats = [], []
    for poly in kml_polygons:
        lons, lats = zip(*poly)
        all_lons.extend(lons)
        all_lats.extend(lats)
        ax.fill(lons, lats, facecolor="#E9ECEF", edgecolor="#212529", linewidth=0.9, alpha=0.55, zorder=1)
    min_x, max_x = min(all_lons), max(all_lons)
    min_y, max_y = min(all_lats), max(all_lats)
    pad_x = (max_x - min_x) * 0.03 if max_x != min_x else 0.05
    pad_y = (max_y - min_y) * 0.03 if max_y != min_y else 0.05
    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    mean_lat = (min_y + max_y) / 2.0
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)), adjustable="box")
    return (min_x, max_x, min_y, max_y)

def custom_k_formatter(x, pos):
    if x == 0:
        return "0"
    elif x >= 1000:
        val = x / 1000
        return f"{int(val)} mil" if val.is_integer() else f"{val:.1f} mil".replace(".", ",")
    return f"{int(x)}"

def carregar_geojson_ti(caminho_arquivo: str) -> dict:
    if not os.path.exists(caminho_arquivo):
        return {}
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        return json.load(f)

def carregar_geojson_uc(caminho_arquivo: str) -> dict:
    if not os.path.exists(caminho_arquivo):
        return {}
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        return json.load(f)

def extrair_dados_ti(geojson_data: dict, ti_nome: str):
    for feat in geojson_data.get("features", []):
        props = feat.get("properties", {})
        nome = props.get("name") or props.get("terras_indigenas") or props.get("NO_TI") or ""
        if nome.strip().upper() == ti_nome.strip().upper():
            return props, shape(feat.get("geometry"))
    return None, None

def extrair_dados_uc(geojson_data: dict, uc_nome: str):
    for feat in geojson_data.get("features", []):
        props = feat.get("properties", {})
        nome = (
            props.get("name")
            or props.get("nome")
            or props.get("NO_UC")
            or props.get("NM_UC")
            or ""
        )
        if nome.strip().upper() == uc_nome.strip().upper():
            return props, shape(feat.get("geometry"))
    return None, None

# ----------------------------------------------------------------------
# Geração dos Gráficos, Sazonalidade e Mapas
# ----------------------------------------------------------------------
def generate_p1_charts_figures(top5_muns, top5_focos, hist_anos, hist_focos, municipio_alvo):
    fig1, ax1 = plt.subplots(figsize=(5, 2.8), dpi=150)
    bar_colors = ["#b52b27" if m.lower() == municipio_alvo.lower() else "#a6b1e1" for m in top5_muns]
    ax1.barh(top5_muns[::-1], top5_focos[::-1], color=bar_colors[::-1])
    ax1.set_title("Top 5 Focos Historicamente (Estado)", fontsize=10, fontweight="bold")
    ax1.tick_params(axis="both", labelsize=8)
    ax1.xaxis.set_major_formatter(FuncFormatter(custom_k_formatter))
    plt.tight_layout()

    fig2, ax2 = plt.subplots(figsize=(5, 2.8), dpi=150)
    x_idxs = np.arange(len(hist_anos))
    y_vals = np.array(hist_focos)
    ax2.plot(x_idxs, y_vals, marker="o", markersize=4, color="#b52b27", linewidth=2, label="Focos")
    if len(x_idxs) > 1:
        z = np.polyfit(x_idxs, y_vals, 1)
        p = np.poly1d(z)
        ax2.plot(x_idxs, p(x_idxs), color="#333333", linestyle="--", linewidth=1.2, label="Tendência")
    ax2.set_title(f"Evolução Anual Histórica ({hist_anos[0]}-{hist_anos[-1]})", fontsize=10, fontweight="bold")
    ax2.set_xticks(x_idxs[::2])
    ax2.set_xticklabels(hist_anos[::2], rotation=45, ha="right", fontsize=7.5)
    ax2.tick_params(axis="y", labelsize=8)
    ax2.yaxis.set_major_formatter(FuncFormatter(custom_k_formatter))
    ax2.legend(fontsize=7.5, loc="upper right", frameon=False)
    plt.tight_layout()

    return fig1, fig2

def generate_seasonality_chart(monthly_counts):
    meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    valores = [monthly_counts.get(m, 0) for m in range(1, 13)]
    
    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=150)
    bars = ax.bar(meses_nomes, valores, color="#E53935", alpha=0.85, edgecolor="#B71C1C", width=0.6)
    
    max_val = max(valores) if valores else 0
    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax.annotate(f'{int(h):,}'.replace(',', '.'),
                        xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=7.5, fontweight='bold')

    ax.set_title("Sazonalidade Mensal de Focos de Calor (Distribuição Histórica Acumulada)", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(custom_k_formatter))
    
    if max_val > 0:
        ax.set_ylim(0, max_val * 1.18)
    else:
        ax.set_ylim(0, 10)

    ax.grid(axis="y", linestyle=":", alpha=0.4)
    plt.tight_layout()
    return fig

def plot_polygon_ibge(ax, geom, color="#1E88E5", linewidth=1.5, fill_alpha=0.05):
    """Desenha a geometria oficial do IBGE e define os limites de visualização."""
    if geom is None:
        return None

    poligonos = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]

    for poly in poligonos:
        x, y = poly.exterior.xy
        ax.plot(x, y, color=color, linewidth=linewidth, zorder=5)
        if fill_alpha > 0:
            ax.fill(x, y, color=color, alpha=fill_alpha, zorder=4)

        for interior in poly.interiors:
            xi, yi = interior.xy
            ax.plot(
                xi,
                yi,
                color=color,
                linewidth=linewidth * 0.8,
                linestyle="--",
                zorder=5,
            )

    min_x, min_y, max_x, max_y = geom.bounds
    margin_x = (max_x - min_x) * 0.05
    margin_y = (max_y - min_y) * 0.05
    ax.set_xlim(min_x - margin_x, max_x + margin_x)
    ax.set_ylim(min_y - margin_y, max_y + margin_y)

    return min_x, max_x, min_y, max_y

def generate_trimester_recurrence_map(
    coords_hist_mes, municipio, ano_inicio, ano_fim, poligono_municipio
):
    """Gera o mapa de distribuição sazonal por trimestre utilizando o polígono oficial do IBGE."""
    if not coords_hist_mes:
        return None

    GRID_10KM_DEG = 10.0 / 111.0
    trimestres = {
        "1º Trimestre (Jan-Mar)": [1, 2, 3],
        "2º Trimestre (Abr-Jun)": [4, 5, 6],
        "3º Trimestre (Jul-Set)": [7, 8, 9],
        "4º Trimestre (Out-Dez)": [10, 11, 12],
    }

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=180)
    axes = axes.flatten()

    for idx, (titulo_trim, meses) in enumerate(trimestres.items()):
        ax = axes[idx]
        ax.set_facecolor("#F8F9FA")

        bounds = plot_polygon_ibge(ax, poligono_municipio)

        pts_trim = [
            (lon, lat) for lon, lat, mes in coords_hist_mes if mes in meses
        ]

        if pts_trim and bounds:
            min_x, max_x, min_y, max_y = bounds
            x_bins = np.arange(
                min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG
            )
            y_bins = np.arange(
                min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG
            )

            lons, lats = zip(*pts_trim)
            counts, xedges, yedges = np.histogram2d(
                lons, lats, bins=[x_bins, y_bins]
            )
            counts_masked = np.ma.masked_where(counts == 0, counts)
            X, Y = np.meshgrid(xedges, yedges)

            mesh = ax.pcolormesh(
                X,
                Y,
                counts_masked.T,
                cmap="YlOrRd",
                zorder=3,
                alpha=0.85,
                edgecolors="#888888",
                linewidth=0.1,
            )
            cb = fig.colorbar(
                mesh, ax=ax, orientation="vertical", pad=0.02, shrink=0.7
            )
            cb.set_label("Focos Acumulados", fontsize=7)

            ax.set_title(
                f"{titulo_trim} ({len(pts_trim):,} focos)".replace(",", "."),
                fontsize=9,
                fontweight="bold",
            )
        else:
            ax.text(
                0.5,
                0.5,
                "Sem registros no trimestre",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=8,
            )
            ax.set_title(titulo_trim, fontsize=9, fontweight="bold")

        ax.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)

    fig.suptitle(
        f"Migração Sazonal Trimestral dos Focos ({ano_inicio}-{ano_fim}) — {municipio}",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout()
    return fig

def generate_map_figures(
    coords_atual,
    coords_hist_ano,
    municipio,
    ano_fim,
    ano_inicio,
    poligono_municipio,
):
    GRID_10KM_DEG = 10.0 / 111.0
    colors_density = [
        "#1A237E",
        "#2E7D32",
        "#FBC02D",
        "#F57C00",
        "#D32F2F",
        "#6A1B9A",
    ]
    cmap_densidade = LinearSegmentedColormap.from_list(
        "densidade_extensiva", colors_density
    )

    # MAPA 1: DISPERSÃO ESPACIAL
    fig1, ax1 = plt.subplots(figsize=(9, 7), dpi=180)
    ax1.set_facecolor("#F8F9FA")
    bounds = plot_polygon_ibge(ax1, poligono_municipio)

    if coords_atual:
        lons, lats = zip(*coords_atual)
        ax1.scatter(
            lons,
            lats,
            c="#b52b27",
            s=18,
            alpha=0.8,
            edgecolors="none",
            zorder=3,
            label="Foco de Calor",
        )
        ax1.set_title(
            f"1. Dispersão Espacial dos Focos em {ano_fim} — {municipio} ({len(coords_atual):,} focos)".replace(
                ",", "."
            ),
            fontsize=11,
            fontweight="bold",
        )
    else:
        ax1.text(
            0.5,
            0.5,
            f"Sem focos em {ano_fim}",
            ha="center",
            va="center",
            transform=ax1.transAxes,
        )
        ax1.set_title(
            f"1. Dispersão Espacial dos Focos em {ano_fim}",
            fontsize=11,
            fontweight="bold",
        )

    ax1.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)
    plt.tight_layout()

    # MAPA 2: DENSIDADE ESPACIAL ACUMULADA
    fig2, ax2 = plt.subplots(figsize=(9, 7), dpi=180)
    ax2.set_facecolor("#F8F9FA")
    bounds = plot_polygon_ibge(ax2, poligono_municipio)

    if coords_hist_ano and bounds:
        hlons, hlats, _ = zip(*coords_hist_ano)
        min_x, max_x, min_y, max_y = bounds
        x_bins = np.arange(
            min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG
        )
        y_bins = np.arange(
            min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG
        )
        counts, xedges, yedges = np.histogram2d(
            hlons, hlats, bins=[x_bins, y_bins]
        )
        counts_masked = np.ma.masked_where(counts == 0, counts)
        X, Y = np.meshgrid(xedges, yedges)
        mesh2 = ax2.pcolormesh(
            X,
            Y,
            counts_masked.T,
            cmap=cmap_densidade,
            zorder=3,
            alpha=0.85,
            edgecolors="#888888",
            linewidth=0.1,
        )
        cb2 = fig2.colorbar(
            mesh2, ax=ax2, orientation="vertical", pad=0.02, shrink=0.8
        )
        cb2.set_label("Concentração de Focos (Grade 10km × 10km)", fontsize=8)
        ax2.set_title(
            f"2. Densidade Espacial Acumulada ({ano_inicio}-{ano_fim}) — Grade 10 km × 10 km — {municipio}",
            fontsize=11,
            fontweight="bold",
        )

    ax2.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)
    plt.tight_layout()

    # MAPA 3: RECORRÊNCIA TEMPORAL
    fig3, ax3 = plt.subplots(figsize=(9, 7), dpi=180)
    ax3.set_facecolor("#F8F9FA")
    bounds = plot_polygon_ibge(ax3, poligono_municipio)

    if coords_hist_ano and bounds:
        min_x, max_x, min_y, max_y = bounds
        x_bins = np.arange(
            min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG
        )
        y_bins = np.arange(
            min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG
        )
        years = sorted(list(set(a for _, _, a in coords_hist_ano)))
        rec_matrix = np.zeros((len(x_bins) - 1, len(y_bins) - 1))

        for y_val in years:
            pts_y = [(lon, lat) for lon, lat, a in coords_hist_ano if a == y_val]
            if pts_y:
                lx, ly = zip(*pts_y)
                c_y, _, _ = np.histogram2d(lx, ly, bins=[x_bins, y_bins])
                rec_matrix += (c_y > 0).astype(int)

        rec_masked = np.ma.masked_where(rec_matrix == 0, rec_matrix)
        X, Y = np.meshgrid(x_bins, y_bins)
        mesh3 = ax3.pcolormesh(
            X,
            Y,
            rec_masked.T,
            cmap="plasma",
            zorder=3,
            alpha=0.85,
            edgecolors="#888888",
            linewidth=0.1,
        )
        cb3 = fig3.colorbar(
            mesh3, ax=ax3, orientation="vertical", pad=0.02, shrink=0.8
        )
        cb3.set_label("Nº de Anos com Reincidência", fontsize=8)
        ax3.set_title(
            f"3. Recorrência Temporal dos Focos ({ano_inicio}-{ano_fim}) — Grade 10 km × 10 km",
            fontsize=11,
            fontweight="bold",
        )

    ax3.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)
    plt.tight_layout()

    return fig1, fig2, fig3

def generate_qgis_grid_geojson(df_filtrado, poligono_alvo, cell_size_deg=10.0/111.0):
    if poligono_alvo is not None and hasattr(poligono_alvo, "bounds"):
        min_x, min_y, max_x, max_y = poligono_alvo.bounds
    elif not df_filtrado.empty:
        min_x, max_x = df_filtrado["lon"].min(), df_filtrado["lon"].max()
        min_y, max_y = df_filtrado["lat"].min(), df_filtrado["lat"].max()
    else:
        return {"type": "FeatureCollection", "features": []}

    if df_filtrado.empty:
        return {"type": "FeatureCollection", "features": []}

    coords_hist = list(
        df_filtrado[["lon", "lat", "ano"]].itertuples(index=False, name=None)
    )
    hlons, hlats, hyears = zip(*coords_hist)
    x_bins = np.arange(min_x - cell_size_deg, max_x + 2 * cell_size_deg, cell_size_deg)
    y_bins = np.arange(min_y - cell_size_deg, max_y + 2 * cell_size_deg, cell_size_deg)
    counts_total, _, _ = np.histogram2d(hlons, hlats, bins=[x_bins, y_bins])
    years = sorted(list(set(hyears)))
    rec_matrix = np.zeros((len(x_bins) - 1, len(y_bins) - 1))
    for y_val in years:
        pts_y = [(lon, lat) for lon, lat, a in coords_hist if a == y_val]
        if pts_y:
            lx, ly = zip(*pts_y)
            c_y, _, _ = np.histogram2d(lx, ly, bins=[x_bins, y_bins])
            rec_matrix += (c_y > 0).astype(int)

    features = []
    cell_id = 1
    for i in range(len(x_bins) - 1):
        for j in range(len(y_bins) - 1):
            val_focos = int(counts_total[i, j])
            val_rec = int(rec_matrix[i, j])
            if val_focos > 0:
                x0, x1 = x_bins[i], x_bins[i+1]
                y0, y1 = y_bins[j], y_bins[j+1]
                feat = {
                    "type": "Feature",
                    "properties": {"cell_id": cell_id, "focos_acumulados": val_focos, "recorrencia_anos": val_rec},
                    "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
                }
                features.append(feat)
                cell_id += 1
    return {"type": "FeatureCollection", "name": "grade_autosimd_qgis", "features": features}

# ----------------------------------------------------------------------
# Geração Automática de Relatório PDF Completo (ReportLab)
# ----------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    """Canvas personalizado para adicionar rodapé e numeração no formato 'Página X de Y'."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#444444"))
        
        self.setStrokeColor(colors.HexColor("#B71C1C"))
        self.setLineWidth(1)
        self.line(30, 32, 565, 32)
        
        footer_text = "AutoSIMD - FOCOS | CBMPA - Coordenadoria Estadual de Proteção e Defesa Civil (DGR)"
        page_text = f"Página {self._pageNumber} de {page_count}"
        
        self.drawString(30, 20, footer_text)
        self.drawRightString(565, 20, page_text)
        self.restoreState()

def fig_to_rl_image(fig, target_width=520, dpi=150):
    """Converte uma figura do Matplotlib em um objeto Image do ReportLab mantendo a proporção."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi)
    buf.seek(0)
    pil_img = PILImage.open(buf)
    w, h = pil_img.size
    aspect = h / float(w)
    target_height = target_width * aspect
    buf.seek(0)
    return Image(buf, width=target_width, height=target_height)

def _get_pdf_styles():
    """Retorna os estilos formatados para o documento ReportLab."""
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.HexColor("#111111"),
            alignment=1,
        ),
        "sub_title": ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#E53935"),
            alignment=1,
        ),
        "mun_title": ParagraphStyle(
            "DocMunTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.HexColor("#1E88E5"),
            alignment=1,
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#B71C1C"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "cell_style": ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            alignment=1,
        ),
        "cell_bold": ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=1,
        ),
        "sub": ParagraphStyle(
            "Sub", parent=styles["Normal"], fontSize=8.5, alignment=1
        ),
        "note": ParagraphStyle(
            "Note",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#333333"),
        ),
    }

def _build_pdf_header(municipio, ano_inicio, ano_fim, styles):
    """Constrói o cabeçalho oficial com brasões e títulos."""
    img_brasao = (
        Image(PATH_BRASAO_PARA, width=50, height=60)
        if os.path.exists(PATH_BRASAO_PARA)
        else ""
    )
    img_cedec = (
        Image(PATH_CBM_CEDEC, width=60, height=60)
        if os.path.exists(PATH_CBM_CEDEC)
        else ""
    )

    header_text = [
        Paragraph(
            "<b>CORPO DE BOMBEIROS MILITAR DO PARÁ</b>", styles["title"]
        ),
        Paragraph(
            "Coordenadoria Estadual de Proteção e Defesa Civil — DGR",
            styles["sub"],
        ),
        Paragraph(
            "<b>AutoSIMD - FOCOS — DIAGNÓSTICO MUNICIPAL</b>", styles["sub_title"]
        ),
        Paragraph(
            f"<b>{municipio.upper()} ({ano_inicio} - {ano_fim})</b>",
            styles["mun_title"],
        ),
    ]

    header_table = Table(
        [[img_brasao, header_text, img_cedec]], colWidths=[65, 405, 65]
    )
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ])
    )

    return [
        header_table,
        Spacer(1, 6),
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#B71C1C"),
            spaceAfter=8,
        ),
    ]

def _build_pdf_kpis(kpis, styles):
    """Constrói a tabela de resumo executivo/KPIs."""
    kpi_data = [
        [
            Paragraph("<b>Focos no Ano</b>", styles["cell_bold"]),
            Paragraph("<b>Ranking Histórico</b>", styles["cell_bold"]),
            Paragraph("<b>Ranking no Ano</b>", styles["cell_bold"]),
            Paragraph("<b>Peso Estadual</b>", styles["cell_bold"]),
            Paragraph("<b>Variação Anual</b>", styles["cell_bold"]),
        ],
        [
            Paragraph(
                f"{kpis['focos_ano_atual']:,}".replace(",", "."),
                styles["cell_style"],
            ),
            Paragraph(f"{kpis['pos_hist']}º lugar", styles["cell_style"]),
            Paragraph(f"{kpis['pos_atual']}º lugar", styles["cell_style"]),
            Paragraph(
                f"{kpis['peso_est_pct']:.1f}%".replace(".", ","),
                styles["cell_style"],
            ),
            Paragraph(
                f"{kpis['var_anual_pct']:+.1f}%".replace(".", ","),
                styles["cell_style"],
            ),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[107] * 5)
    kpi_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )

    return [
        Paragraph(
            "📌 Resumo Executivo — Indicadores Chave", styles["section_heading"]
        ),
        kpi_table,
        Spacer(1, 10),
    ]

def _build_pdf_charts(fig_chart1, fig_chart2, fig_sazonalidade, styles):
    """Renderiza a seção de gráficos comparativos e de sazonalidade."""
    elements = [
        Paragraph(
            "📈 Diagnóstico Geral e Análise de Sazonalidade",
            styles["section_heading"],
        )
    ]

    img_c1 = fig_to_rl_image(fig_chart1, target_width=255)
    img_c2 = fig_to_rl_image(fig_chart2, target_width=255)
    charts_table = Table([[img_c1, img_c2]], colWidths=[265, 265])
    charts_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ])
    )
    elements.extend([charts_table, Spacer(1, 6)])

    if fig_sazonalidade:
        img_saz = fig_to_rl_image(fig_sazonalidade, target_width=520)
        elements.extend([img_saz, Spacer(1, 10)])

    elements.append(PageBreak())
    return elements

def _build_pdf_maps(fig_map1, fig_map2, fig_map3, fig_map_trimestre, styles):
    """Insere os mapas geospaciais gerados."""
    elements = [
        Paragraph(
            "🗺️ Mapeamento Espacial de Focos de Calor", styles["section_heading"]
        )
    ]

    for fig in [fig_map1, fig_map2, fig_map3, fig_map_trimestre]:
        if fig:
            img_m = fig_to_rl_image(fig, target_width=480)
            elements.extend([img_m, Spacer(1, 8)])

    return elements

def _build_pdf_tables_and_notes(df_est, df_reg, ano_fim, styles):
    """Monta a seção final com tabelas comparativas sequenciais e nota metodológica."""
    elements = [
        Paragraph(
            "📋 Tabelas Comparativas e Nota Metodológica",
            styles["section_heading"],
        )
    ]

    # 1. Tabela Ranking Estadual
    elements.append(
        Paragraph("<b>Ranking Estadual (Top Municípios)</b>", styles["cell_bold"])
    )
    elements.append(Spacer(1, 4))

    t_est_data = [
        ["Pos", "Município", "Região", f"Focos ({ano_fim})", "Acumulado"]
    ]
    for _, row in df_est.iterrows():
        t_est_data.append([
            str(row["Posição"]),
            str(row["Município"]),
            str(row["Região"]),
            str(row[f"Focos ({ano_fim})"]),
            str(row["Acumulado"]),
        ])

    t_est_table = Table(
        t_est_data, colWidths=[40, 180, 140, 80, 80], repeatRows=1
    )
    t_est_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    elements.extend([t_est_table, Spacer(1, 10)])

    # 2. Tabela Ranking Regional
    elements.append(
        Paragraph(
            "<b>Ranking na Região de Integração</b>", styles["cell_bold"]
        )
    )
    elements.append(Spacer(1, 4))

    t_reg_data = [["Pos", "Município", f"Focos ({ano_fim})", "% Região"]]
    for _, row in df_reg.iterrows():
        t_reg_data.append([
            str(row["Posição"]),
            str(row["Município"]),
            str(row[f"Focos ({ano_fim})"]),
            str(row["% Região"]),
        ])

    t_reg_table = Table(
        t_reg_data, colWidths=[40, 240, 120, 120], repeatRows=1
    )
    t_reg_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    elements.extend([t_reg_table, Spacer(1, 12)])

    # 3. Nota Metodológica
    note_p = Paragraph(
        "<b>Nota Metodológica Oficial:</b><br/>"
        "• <b>Fonte dos Dados:</b> BDQueimadas / INPE (Satélite de referência Aqua-Tarde).<br/>"
        "• <b>Processamento:</b> Os dados foram processados por algoritmos desenvolvidos com apoio de Inteligência Artificial orientada por técnicos de Defesa Civil.<br/>"
        "• <b>Canais de Atendimento:</b> simdcedec@gmail.com | Plantão Defesa Civil: (91) 98899-6323.",
        styles["note"],
    )
    elements.append(note_p)

    return elements

def generate_pdf_report(
    municipio,
    regiao_alvo,
    ano_inicio,
    ano_fim,
    kpis,
    df_est,
    df_reg,
    fig_chart1,
    fig_chart2,
    fig_sazonalidade,
    fig_map1,
    fig_map2,
    fig_map3,
    fig_map_trimestre,
):
    """Gera o documento PDF orquestrando os módulos individuais de seções."""
    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buf,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=45,
    )

    styles = _get_pdf_styles()
    story = []

    story.extend(_build_pdf_header(municipio, ano_inicio, ano_fim, styles))
    story.extend(_build_pdf_kpis(kpis, styles))
    story.extend(
        _build_pdf_charts(fig_chart1, fig_chart2, fig_sazonalidade, styles)
    )
    story.extend(
        _build_pdf_maps(
            fig_map1, fig_map2, fig_map3, fig_map_trimestre, styles
        )
    )
    story.extend(_build_pdf_tables_and_notes(df_est, df_reg, ano_fim, styles))

    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_buf.seek(0)
    return pdf_buf.getvalue()

@st.cache_data
def carregar_geojson_estado(caminho_arquivo: str) -> dict:
    """Carrega o GeoJSON do estado selecionado e armazena em cache."""
    if not os.path.exists(caminho_arquivo):
        return {}
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        return json.load(f)

def obter_mapa_estados(diretorio_base: str) -> dict:
    """Mapeia os arquivos disponíveis na pasta (ex: {'Acre': '/caminho/NM_UF_Acre.geojson'})."""
    if not os.path.exists(diretorio_base):
        return {}
    arquivos = sorted(glob.glob(os.path.join(diretorio_base, "*.geojson")))
    mapa = {}
    for arq in arquivos:
        nome_estado = (
            os.path.basename(arq).replace("NM_UF_", "").replace(".geojson", "")
        )
        mapa[nome_estado] = arq
    return mapa

def extrair_dados_municipio(geojson_data: dict, municipio_nome: str):
    """Retorna as propriedades IBGE (dict) e a geometria (objeto Shapely) do município."""
    for feat in geojson_data.get("features", []):
        props = feat.get("properties", {})
        if props.get("NM_MUN", "").strip().upper() == municipio_nome.strip().upper():
            geometria_shapely = shape(feat.get("geometry"))
            return props, geometria_shapely
    return None, None

# ----------------------------------------------------------------------
# Interface do Usuário (Streamlit)
# ----------------------------------------------------------------------
df_focos = carregar_focos_consolidados(PATH_FOCOS_PARQUET)

if df_focos.empty:
    st.error("Nenhum dado de foco encontrado no diretório de dados.")
    st.stop()

anos_disponiveis = sorted(df_focos["ano"].dropna().astype(int).unique())

st.sidebar.title("🛠️ Parâmetros da Análise")

tipo_analise = st.sidebar.radio(
    "🎯 Escolha o Nível de Análise:",
    options=["Estado / Município", "Unidade de Conservação (UC)", "Terra Indígena (TI)"],
)

props_ibge = {}
poligono_municipio = None
nome_alvo = "SELECIONE"

if tipo_analise == "Estado / Município":
    mapa_estados = obter_mapa_estados(GEOJSON_DIR)

    if not mapa_estados:
        st.sidebar.error("Nenhum arquivo GeoJSON de estado encontrado no diretório!")
        st.stop()

    estado_selecionado = st.sidebar.selectbox(
        "Selecione o Estado (UF):",
        options=list(mapa_estados.keys()),
        index=0,
    )
    nome_uf = estado_selecionado.strip().upper()
    municipios_uf = sorted(
        municipio for municipio in df_focos.loc[
            (df_focos["SIGLA_UF"] == nome_uf)
            | (df_focos["NM_UF"] == nome_uf),
            "NM_MUN",
        ].unique() if municipio
    )
    municipio_selecionado = st.sidebar.selectbox(
        "📍 Selecione o Município:",
        options=municipios_uf if municipios_uf else ["SELECIONE"],
    )
    poligono_municipio = carregar_geometria_alvo(
        mapa_estados[estado_selecionado], ("NM_MUN",), municipio_selecionado
    )
    nome_alvo = municipio_selecionado
    campo_filtro = "NM_MUN"
    valor_filtro = municipio_selecionado.strip().upper()
else:
    if tipo_analise == "Unidade de Conservação (UC)":
        campo_rotulo = "🌲 Selecione a Unidade de Conservação (UC):"
        campo_filtro = "UC"
        chaves_geometria = ("name", "nome", "NO_UC", "NM_UC")
    else:
        campo_rotulo = "🏹 Selecione a Terra Indígena (TI):"
        campo_filtro = "TI"
        chaves_geometria = ("name", "terras_indigenas", "NO_TI")

    valores_validos = {"", "NONE", "NULL", "NAN", "N/A"}
    nomes_alvos = sorted(
        valor for valor in df_focos[campo_filtro].unique()
        if valor and valor not in valores_validos
    )
    nome_alvo = st.sidebar.selectbox(campo_rotulo, options=nomes_alvos)
    valor_filtro = nome_alvo.strip().upper()
    caminho_alvo = UC_GEOJSON_PATH if campo_filtro == "UC" else TI_GEOJSON_PATH
    poligono_municipio = carregar_geometria_alvo(
        caminho_alvo, chaves_geometria, nome_alvo
    )

# 5. Seleção do Período
intervalo_anos = st.sidebar.slider(
    "📅 Intervalo de Anos:",
    min_value=min(anos_disponiveis),
    max_value=max(anos_disponiveis),
    value=(min(anos_disponiveis), max(anos_disponiveis)),
    step=1
)

st.sidebar.divider()
st.sidebar.subheader("Opções de Download")
baixar_pacote_auto = st.sidebar.checkbox(
    "Baixar automaticamente o pacote completo (Relatório PDF, Metadados e Imagens PNG)",
    value=True,
)

btn_processar = st.sidebar.button("🚀 Processar Diagnóstico Completo", type="primary", use_container_width=True)

st.sidebar.divider()
with st.sidebar.expander("ℹ️ Sobre o Sistema & Desenvolvedor"):
    st.markdown("**AutoSIMD - FOCOS** `v2.0`")
    st.caption("Diagnóstico Territorial de Focos de Calor")
    st.markdown("""
    **Desenvolvedor:**  
    **Bruno Lobão da Silva**  
    * Soldado do Corpo de Bombeiros Militar do Pará (CBMPA)  
    * Técnico de Defesa Civil — CEDEC/PA (DGR / SIMD)  
    * Bacharel em Eng. Ambiental e Energias Renováveis (UFRA)  
    * Mestrando em Gestão de Riscos e Desastres Naturais na Amazônia (UFPA)  

    ---
    📧 **Contato:** [engamb.lobs@gmail.com](mailto:engamb.lobs@gmail.com)  
    📜 **Lattes:** [Currículo Lattes](http://lattes.cnpq.br/9038468130657451)  
    🐙 **GitHub:** [Autosimd-Focos](https://github.com/engamblobs/Autosimd-Focos)
    """)

render_header(f"{tipo_analise}: {nome_alvo}")

if btn_processar and tipo_analise != "Estado / Município":
    if poligono_municipio is None:
        st.error("Não foi possível obter a geometria do território selecionado.")
        st.stop()

    ano_inicio_sel, ano_fim_sel = intervalo_anos
    df_escopo = df_focos[
        (df_focos["ano"] >= ano_inicio_sel)
        & (df_focos["ano"] <= ano_fim_sel)
    ]
    df_filtrado = df_escopo[df_escopo[campo_filtro] == valor_filtro]
    focos_por_ano = {
        ano: int((df_filtrado["ano"] == ano).sum())
        for ano in range(ano_inicio_sel, ano_fim_sel + 1)
    }
    coords_historico_ano = list(
        df_filtrado[["lon", "lat", "ano"]].itertuples(index=False, name=None)
    )
    coords_historico_mes = list(
        df_filtrado[df_filtrado["mes"].between(1, 12)][["lon", "lat", "mes"]]
        .itertuples(index=False, name=None)
    )
    coords_ano_atual = list(
        df_filtrado[df_filtrado["ano"] == ano_fim_sel][["lon", "lat"]]
        .itertuples(index=False, name=None)
    )
    monthly_counts = {
        mes: int(df_filtrado["mes"].eq(mes).sum())
        for mes in range(1, 13)
    }

    focos_atual = focos_por_ano.get(ano_fim_sel, 0)
    focos_total = sum(focos_por_ano.values())
    media_anual = focos_total / len(focos_por_ano) if focos_por_ano else 0

    st.markdown(f"### 📌 Resumo da Análise ({ano_inicio_sel} - {ano_fim_sel})")
    k1, k2, k3 = st.columns(3)
    k1.metric(f"Focos em {ano_fim_sel}", f"{focos_atual:,}".replace(",", "."))
    k2.metric("Total no Período", f"{focos_total:,}".replace(",", "."))
    k3.metric("Média Anual", f"{media_anual:,.0f}".replace(",", "."))

    st.divider()
    chart_col, history_col = st.columns(2)
    with chart_col:
        st.markdown("#### 🗓️ Distribuição Mensal Sazonal")
        st.pyplot(generate_seasonality_chart(monthly_counts), use_container_width=True)
    with history_col:
        st.markdown("#### 📈 Evolução Anual dos Focos")
        fig_hist, ax_hist = plt.subplots(figsize=(5, 2.8), dpi=150)
        anos_hist = list(focos_por_ano.keys())
        valores_hist = list(focos_por_ano.values())
        ax_hist.plot(anos_hist, valores_hist, marker="o", color="#b52b27", linewidth=2)
        ax_hist.set_title("Evolução Histórica", fontsize=10, fontweight="bold")
        ax_hist.yaxis.set_major_formatter(FuncFormatter(custom_k_formatter))
        ax_hist.grid(axis="y", linestyle=":", alpha=0.4)
        plt.tight_layout()
        st.pyplot(fig_hist, use_container_width=True)

    st.divider()
    st.markdown("### 🗺️ Mapeamento Espacial")
    fig_map1, fig_map2, fig_map3 = generate_map_figures(
        coords_ano_atual,
        coords_historico_ano,
        nome_alvo,
        ano_fim_sel,
        ano_inicio_sel,
        poligono_municipio,
    )
    st.pyplot(fig_map1, use_container_width=True)
    st.pyplot(fig_map2, use_container_width=True)
    st.pyplot(fig_map3, use_container_width=True)

    fig_map_trimestre = generate_trimester_recurrence_map(
        coords_historico_mes,
        nome_alvo,
        ano_inicio_sel,
        ano_fim_sel,
        poligono_municipio,
    )
    if fig_map_trimestre:
        st.markdown("#### 🔄 Migração Espacial Sazonal por Trimestre")
        st.pyplot(fig_map_trimestre, use_container_width=True)

    render_rankings_areas_protegidas(df_focos, ano_inicio_sel, ano_fim_sel)
    if df_filtrado.empty:
        st.warning("Sem dados para exportar no período")
    else:
        pacote_bytes, nome_zip = exportar_pacote_analise(
            df_filtrado=df_filtrado,
            nome_alvo=nome_alvo,
            tipo_analise=tipo_analise,
            ano_inicio=ano_inicio_sel,
            ano_fim=ano_fim_sel,
            poligono_alvo=poligono_municipio,
            figuras_mapa=[fig_map1, fig_map2, fig_map3, fig_map_trimestre],
            figuras_grafico=[generate_seasonality_chart(monthly_counts)],
        )
        st.markdown("### 📥 Central de Exportação do Pacote Completo")
        st.download_button(
            label="📦 BAIXAR PACOTE COMPLETO (.ZIP) — Dados, Rankings e Imagens PNG",
            data=pacote_bytes,
            file_name=nome_zip,
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )
    st.success(f"Diagnóstico territorial de {nome_alvo} concluído com sucesso.")
    st.stop()

if btn_processar:
    ano_inicio_sel, ano_fim_sel = intervalo_anos
    mun_upper = municipio_selecionado.strip().upper()

    with st.spinner("Processando geodados, sazonalidade e gerando mapas..."):
        df_escopo = df_focos[
            (df_focos["ano"] >= ano_inicio_sel)
            & (df_focos["ano"] <= ano_fim_sel)
        ]
        focos_por_ano_mun = {
            ano: df_escopo[df_escopo["ano"] == ano]["NM_MUN"]
            .value_counts()
            .to_dict()
            for ano in range(ano_inicio_sel, ano_fim_sel + 1)
        }
        acumulado_historico = df_escopo["NM_MUN"].value_counts().to_dict()
        df_municipio = df_escopo[df_escopo["NM_MUN"] == mun_upper]
        coords_historico_ano = list(
            df_municipio[["lon", "lat", "ano"]].itertuples(index=False, name=None)
        )
        coords_historico_mes = list(
            df_municipio[df_municipio["mes"].between(1, 12)][["lon", "lat", "mes"]]
            .itertuples(index=False, name=None)
        )
        coords_ano_atual = list(
            df_municipio[df_municipio["ano"] == ano_fim_sel][["lon", "lat"]]
            .itertuples(index=False, name=None)
        )
        monthly_counts_mun = {
            mes: int(df_municipio["mes"].eq(mes).sum())
            for mes in range(1, 13)
        }

        regiao_alvo = get_regiao_municipio(mun_upper)
        focos_ano_atual = focos_por_ano_mun.get(ano_fim_sel, {}).get(
            mun_upper, 0
        )

        ano_ant = (
            ano_fim_sel - 1 if (ano_fim_sel - 1) in focos_por_ano_mun else None
        )
        focos_ano_ant = (
            focos_por_ano_mun.get(ano_ant, {}).get(mun_upper, 0)
            if ano_ant
            else 0
        )

        var_anual_pct = (
            (((focos_ano_atual - focos_ano_ant) / focos_ano_ant) * 100)
            if focos_ano_ant > 0
            else 0.0
        )
        total_estado_ano = sum(focos_por_ano_mun.get(ano_fim_sel, {}).values())
        peso_est_pct = (
            (focos_ano_atual / total_estado_ano * 100)
            if total_estado_ano > 0
            else 0.0
        )

        ranking_acumulado = sorted(
            acumulado_historico.items(), key=lambda x: x[1], reverse=True
        )
        muns_acum = [m[0] for m in ranking_acumulado]
        pos_hist = (
            muns_acum.index(mun_upper) + 1 if mun_upper in muns_acum else 0
        )

        ranking_atual = sorted(
            focos_por_ano_mun.get(ano_fim_sel, {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )
        muns_atual = [m[0] for m in ranking_atual]
        pos_atual = (
            muns_atual.index(mun_upper) + 1 if mun_upper in muns_atual else 0
        )

        # Exibição de KPIs
        st.markdown(
            f"### 📌 Resumo Executivo — {municipio_selecionado.title()} ({ano_inicio_sel} a {ano_fim_sel})"
        )
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(
            f"Focos em {ano_fim_sel}", f"{focos_ano_atual:,}".replace(",", ".")
        )
        k2.metric("Ranking Histórico", f"{pos_hist}º lugar")
        k3.metric(f"Ranking em {ano_fim_sel}", f"{pos_atual}º lugar")
        k4.metric("Peso Estadual", f"{peso_est_pct:.1f}%".replace(".", ","))
        k5.metric("Variação Anual", f"{var_anual_pct:+.1f}%".replace(".", ","))

        st.divider()

        # Construção dos gráficos comparativos
        st.markdown("### 📈 Diagnóstico Geral e Análise de Sazonalidade")
        top5_muns = [m[0].title() for m in ranking_acumulado[:5]]
        top5_focos = [m[1] for m in ranking_acumulado[:5]]
        anos_grafico = [str(a) for a in sorted(list(focos_por_ano_mun.keys()))]
        focos_grafico = [
            focos_por_ano_mun[int(a)].get(mun_upper, 0) for a in anos_grafico
        ]

        fig_chart1, fig_chart2 = generate_p1_charts_figures(
            top5_muns,
            top5_focos,
            anos_grafico,
            focos_grafico,
            municipio_selecionado,
        )
        g_col1, g_col2 = st.columns(2)
        with g_col1:
            st.pyplot(fig_chart1, use_container_width=True)
        with g_col2:
            st.pyplot(fig_chart2, use_container_width=True)

        st.markdown("#### 🗓️ Padrão Sazonal de Incidência (Distribuição Mensal)")
        fig_sazonalidade = generate_seasonality_chart(monthly_counts_mun)
        st.pyplot(fig_sazonalidade, use_container_width=True)

        st.divider()

        # Tabelas de Ranking
        st.markdown("### 📋 Tabelas de Ranking e Comparativo Regional")
        t_col1, t_col2 = st.columns(2)

        with t_col1:
            st.markdown(f"**Top 5 Estado ({ano_fim_sel})**")
            df_est = pd.DataFrame([
                {
                    "Posição": f"{idx}º",
                    "Município": m[0].title(),
                    "Região": get_regiao_municipio(m[0]),
                    f"Focos ({ano_fim_sel})": m[1],
                    "Acumulado": acumulado_historico.get(m[0], 0),
                }
                for idx, m in enumerate(ranking_atual[:5], start=1)
            ])
            st.dataframe(df_est, use_container_width=True, hide_index=True)

        with t_col2:
            st.markdown(f"**Comparativo na {regiao_alvo} ({ano_fim_sel})**")
            muns_reg = [
                m
                for m in focos_por_ano_mun.get(ano_fim_sel, {}).keys()
                if get_regiao_municipio(m).lower() == regiao_alvo.lower()
            ]
            ranking_reg = sorted(
                [(m, focos_por_ano_mun[ano_fim_sel][m]) for m in muns_reg],
                key=lambda x: x[1],
                reverse=True,
            )
            tot_reg = sum(c for _, c in ranking_reg)
            df_reg = pd.DataFrame([
                {
                    "Posição": f"{idx}º",
                    "Município": m[0].title(),
                    f"Focos ({ano_fim_sel})": m[1],
                    "% Região": (
                        f"{(m[1]/tot_reg*100):.1f}%".replace(".", ",")
                        if tot_reg > 0
                        else "0%"
                    ),
                }
                for idx, m in enumerate(ranking_reg, start=1)
            ])
            st.dataframe(df_reg, use_container_width=True, hide_index=True)

        st.divider()

        # Mapeamento Espacial
        st.markdown("### 🗺️ Mapeamento Espacial e Sazonalidade Trimestral")

        fig_map1, fig_map2, fig_map3 = generate_map_figures(
            coords_ano_atual,
            coords_historico_ano,
            municipio_selecionado,
            ano_fim_sel,
            ano_inicio_sel,
            poligono_municipio,
        )

        st.pyplot(fig_map1, use_container_width=True)
        st.pyplot(fig_map2, use_container_width=True)
        st.pyplot(fig_map3, use_container_width=True)

        fig_map_trimestre = generate_trimester_recurrence_map(
            coords_historico_mes,
            municipio_selecionado,
            ano_inicio_sel,
            ano_fim_sel,
            poligono_municipio,
        )
        if fig_map_trimestre:
            st.markdown(
                "#### 🔄 Migração Espacial Sazonal (Concentração em Grade 10 km por Trimestre)"
            )
            st.pyplot(fig_map_trimestre, use_container_width=True)

        render_rankings_areas_protegidas(df_focos, ano_inicio_sel, ano_fim_sel)

        st.divider()

        # Síntese Espacial
        st.markdown("### 📐 Síntese Espacial e Metodologia")
        s_col1, s_col2 = st.columns([1, 1])

        with s_col1:
            st.markdown("**Parâmetros Técnicos e Operacionais**")
            df_sintese = pd.DataFrame([
                {
                    "Parâmetro": "Ocorrências Ano Atual",
                    "Diagnóstico": f"{len(coords_ano_atual):,} focos mapeados em {ano_fim_sel}".replace(
                        ",", "."
                    ),
                },
                {
                    "Parâmetro": "Acumulado Histórico",
                    "Diagnóstico": f"{len(coords_historico_ano):,} focos ({ano_inicio_sel}-{ano_fim_sel})".replace(
                        ",", "."
                    ),
                },
                {
                    "Parâmetro": "Grade Geospacial",
                    "Diagnóstico": "Células de 10 km × 10 km (~0.09°)",
                },
                {
                    "Parâmetro": "Aplicação Operacional",
                    "Diagnóstico": (
                        "Definição de rotas de sobrevoo e bases de combate"
                    ),
                },
            ])
            st.dataframe(df_sintese, use_container_width=True, hide_index=True)

        with s_col2:
            st.markdown("**Nota Metodológica Oficial**")
            st.info(
                "• **Fonte dos Dados:** BDQueimadas / INPE (Satélite de referência Aqua-Tarde).\n"
                "• **Processamento:** Os dados foram processados automaticamente por algoritmos desenvolvidos "
                "**com apoio de Inteligência Artificial orientada por técnicos de Defesa Civil**.\n"
                "• **Canais de Atendimento:** simdcedec@gmail.com | Plantão Defesa Civil: (91) 98899-6323."
            )

        st.divider()

        # Compilação e construção do ZIP completo
        df_hist_export = pd.DataFrame([
            {"Ano": a, "Focos": focos_por_ano_mun.get(a, {}).get(mun_upper, 0)}
            for a in range(ano_inicio_sel, ano_fim_sel + 1)
        ])
        meses_nomes = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        df_sazonal_export = pd.DataFrame([
            {"Mês": meses_nomes[m - 1], "Focos_Acumulados": monthly_counts_mun.get(m, 0)}
            for m in range(1, 13)
        ])
        buf_excel = io.BytesIO()
        with pd.ExcelWriter(buf_excel, engine="openpyxl") as writer:
            df_hist_export.to_excel(
                writer, sheet_name="Evolucao_Historica", index=False
            )
            df_sazonal_export.to_excel(
                writer, sheet_name="Sazonalidade_Mensal", index=False
            )
        buf_excel.seek(0)
        excel_bytes = buf_excel.getvalue()

        grid_json = generate_qgis_grid_geojson(df_municipio, poligono_municipio)
        qgis_bytes = json.dumps(grid_json, indent=2).encode("utf-8")

        kpis_dict = {
            "focos_ano_atual": focos_ano_atual,
            "pos_hist": pos_hist,
            "pos_atual": pos_atual,
            "peso_est_pct": peso_est_pct,
            "var_anual_pct": var_anual_pct,
        }
        pdf_bytes = generate_pdf_report(
            municipio_selecionado,
            regiao_alvo,
            ano_inicio_sel,
            ano_fim_sel,
            kpis_dict,
            df_est,
            df_reg,
            fig_chart1,
            fig_chart2,
            fig_sazonalidade,
            fig_map1,
            fig_map2,
            fig_map3,
            fig_map_trimestre,
        )

        master_zip_buf = io.BytesIO()
        with zipfile.ZipFile(master_zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            alvo_arquivo = sanitizar_nome_arquivo(nome_alvo)
            zf.writestr(
                f"dados_MUN_{alvo_arquivo}.csv",
                df_municipio.to_csv(index=False).encode("utf-8"),
            )
            zf.writestr(
                "metadados.json",
                json.dumps({
                    "nome_alvo": nome_alvo,
                    "tipo_analise": tipo_analise,
                    "ano_inicio": ano_inicio_sel,
                    "ano_fim": ano_fim_sel,
                    "total_focos": len(df_municipio),
                }, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            valores_invalidos = {"", "NONE", "NULL", "NAN", "N/A"}
            for coluna, nome_ranking in (
                ("NM_MUN", "ranking_municipios.csv"),
                ("UC", "ranking_ucs.csv"),
                ("TI", "ranking_tis.csv"),
            ):
                ranking = (
                    df_escopo.loc[~df_escopo[coluna].isin(valores_invalidos), coluna]
                    .value_counts()
                    .rename_axis(coluna)
                    .reset_index(name="Focos de Calor")
                )
                zf.writestr(nome_ranking, ranking.to_csv(index=False).encode("utf-8"))
            if pdf_bytes:
                zf.writestr(
                    f"relatorio_diagnostico_{alvo_arquivo}_{ano_inicio_sel}_{ano_fim_sel}.pdf",
                    pdf_bytes,
                )
            if excel_bytes:
                zf.writestr(
                    f"estatisticas_{alvo_arquivo}_{ano_inicio_sel}_{ano_fim_sel}.xlsx",
                    excel_bytes,
                )
            if qgis_bytes:
                nome_arquivo_grade = f"grade_10x10km_{re.sub(r'[^a-zA-Z0-9_]', '_', nome_alvo)}.geojson"
                zf.writestr(nome_arquivo_grade, qgis_bytes)

            b_c1 = io.BytesIO()
            fig_chart1.savefig(
                b_c1, format="png", bbox_inches="tight", dpi=180
            )
            zf.writestr(
                f"imagens/grafico_top5_estado_{alvo_arquivo}.png", b_c1.getvalue()
            )

            b_c2 = io.BytesIO()
            fig_chart2.savefig(
                b_c2, format="png", bbox_inches="tight", dpi=180
            )
            zf.writestr(
                f"imagens/grafico_evolucao_historica_{alvo_arquivo}.png",
                b_c2.getvalue(),
            )

            b_saz = io.BytesIO()
            fig_sazonalidade.savefig(
                b_saz, format="png", bbox_inches="tight", dpi=180
            )
            zf.writestr(
                f"imagens/grafico_sazonalidade_{alvo_arquivo}.png",
                b_saz.getvalue(),
            )

            b_m1 = io.BytesIO()
            fig_map1.savefig(b_m1, format="png", bbox_inches="tight", dpi=180)
            zf.writestr(
                f"imagens/mapa_1_dispersao_{alvo_arquivo}.png", b_m1.getvalue()
            )

            b_m2 = io.BytesIO()
            fig_map2.savefig(b_m2, format="png", bbox_inches="tight", dpi=180)
            zf.writestr(
                f"imagens/mapa_2_densidade_{alvo_arquivo}.png", b_m2.getvalue()
            )

            b_m3 = io.BytesIO()
            fig_map3.savefig(b_m3, format="png", bbox_inches="tight", dpi=180)
            zf.writestr(
                f"imagens/mapa_3_recorrencia_{alvo_arquivo}.png", b_m3.getvalue()
            )

            if fig_map_trimestre:
                b_mt = io.BytesIO()
                fig_map_trimestre.savefig(
                    b_mt, format="png", bbox_inches="tight", dpi=180
                )
                zf.writestr(
                    f"imagens/mapa_4_sazonalidade_trimestral_{alvo_arquivo}.png",
                    b_mt.getvalue(),
                )

        master_zip_buf.seek(0)
        zip_final_bytes = master_zip_buf.getvalue()

        # Central de Exportação e Download Automático
        st.markdown("### 📥 Central de Exportação do Pacote Completo")

        nome_zip = (
            f"Diagnostico_MUN_{sanitizar_nome_arquivo(nome_alvo)}_"
            f"{ano_inicio_sel}_{ano_fim_sel}.zip"
        )

        if df_municipio.empty:
            st.warning("Sem dados para exportar no período")
        elif baixar_pacote_auto:
            disparar_download_automatico(zip_final_bytes, filename=nome_zip)
            st.success(
                "✅ Diagnóstico concluído! O download do pacote completo em ZIP foi iniciado automaticamente."
            )
        elif not baixar_pacote_auto:
            st.success("✅ Diagnóstico concluído com sucesso!")

        st.download_button(
            label="📦 BAIXAR PACOTE COMPLETO (.ZIP) — PDF, Excel, GeoJSON e Imagens PNG",
            data=zip_final_bytes,
            file_name=nome_zip,
            mime="application/zip",
            type="primary",
            use_container_width=True,
            disabled=df_municipio.empty,
        )
        st.caption(
            "O pacote ZIP contém o Relatório PDF Oficial diagramado, Planilha Excel com séries temporais, Grade QGIS .geojson e todas as imagens/mapas em formato PNG."
        )

else:
    st.info(
        "👈 Defina o município e o período no painel à esquerda e clique em **Processar Diagnóstico Completo**."
    )

render_footer()