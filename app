from datetime import datetime
import glob
import importlib.util
import json
import os
import re
import unicodedata
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter
import streamlit as st
import streamlit.components.v1 as components
from shapely.geometry import shape

# ----------------------------------------------------------------------
# Configurações de Caminhos
# ----------------------------------------------------------------------
PATH_LOGOS_DIR = "/home/lobs/Automacoes/AUTOSIMD-FOCOS/core/logos"
PATH_LOGO_AUTOSIMD = os.path.join(PATH_LOGOS_DIR, "AUTOSIMD-FOCOS.png")
PATH_CBM_CEDEC = os.path.join(PATH_LOGOS_DIR, "CBM-CEDEC.png")
TI_GEOJSON_PATH = "/home/lobs/SIG/BASES_GEOJSON/tiGEOJSON/TI-BR.geojson"
UC_GEOJSON_PATH = "/home/lobs/SIG/BASES_GEOJSON/ucGEOJSON/UC-BR.geojson"
DATA_DIR = "/home/lobs/SIG/FOCOS DE CALOR"
GEOJSON_DIR = "/home/lobs/SIG/BASES_GEOJSON/mun-brGEOJSON"

# Configuração do Streamlit
st.set_page_config(page_title="AutoSIMD - FOCOS", page_icon="🔥", layout="wide")

# ----------------------------------------------------------------------
# Leitura e Cache dos Dados de Focos (Carregamento Otimizado em DataFrame)
# ----------------------------------------------------------------------
@st.cache_data
def carregar_todos_focos(data_dir):
    """Lê os arquivos GeoJSON e consolida em um DataFrame otimizado em memória."""
    records = []
    files = sorted(glob.glob(os.path.join(data_dir, "*.geojson")))
    
    for filepath in files:
        m = re.search(r"\d{4}", os.path.basename(filepath))
        ano_arq = int(m.group(0)) if m else None
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                
                if geom and geom.get("type") == "Point":
                    coords = geom.get("coordinates", [])
                    if len(coords) >= 2:
                        # Extração da data/mês
                        val_str = str(props.get("DataHora") or props.get("datahora") or props.get("acq_date") or "")
                        mes = None
                        m_mes = re.search(r"\d{4}[-/](\d{2})[-/]\d{2}", val_str) or re.search(r"\d{2}[-/](\d{2})[-/]\d{4}", val_str)
                        if m_mes:
                            mes = int(m_mes.group(1))

                        records.append({
                            "lon": coords[0],
                            "lat": coords[1],
                            "ano": ano_arq,
                            "mes": mes,
                            "NM_MUN": str(props.get("NM_MUN", "")).strip().upper(),
                            "NM_UF": str(props.get("NM_UF", "")).strip().upper(),
                            "SIGLA_UF": str(props.get("SIGLA_UF", "")).strip().upper(),
                            "UC": str(props.get("UC", "")).strip().upper(),
                            "TI": str(props.get("TI", "")).strip().upper(),
                        })
    return pd.DataFrame(records)

@st.cache_data
def carregar_geometria_alvo(caminho_geojson, campo_chave, valor_busca):
    """Carrega a geometria apenas do território selecionado para desenhar o contorno no mapa."""
    if not os.path.exists(caminho_geojson):
        return None
    with open(caminho_geojson, "r", encoding="utf-8") as f:
        data = json.load(f)
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            val = str(props.get(campo_chave, "")).strip().upper()
            if val == valor_busca.strip().upper():
                return shape(feat.get("geometry"))
    return None

def obter_mapa_estados(diretorio_base):
    if not os.path.exists(diretorio_base):
        return {}
    arquivos = sorted(glob.glob(os.path.join(diretorio_base, "*.geojson")))
    return {os.path.basename(arq).replace("NM_UF_", "").replace(".geojson", ""): arq for arq in arquivos}

# ----------------------------------------------------------------------
# Funções de Plotagem de Mapas e Gráficos
# ----------------------------------------------------------------------
def plot_polygon_shape(ax, geom, color="#1E88E5", linewidth=1.5):
    if geom is None:
        return None
    poligonos = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in poligonos:
        x, y = poly.exterior.xy
        ax.plot(x, y, color=color, linewidth=linewidth, zorder=5)
        ax.fill(x, y, color=color, alpha=0.05, zorder=4)
        for interior in poly.interiors:
            xi, yi = interior.xy
            ax.plot(xi, yi, color=color, linewidth=linewidth * 0.8, linestyle="--", zorder=5)
    
    min_x, min_y, max_x, max_y = geom.bounds
    margin_x = (max_x - min_x) * 0.05 if max_x != min_x else 0.05
    margin_y = (max_y - min_y) * 0.05 if max_y != min_y else 0.05
    ax.set_xlim(min_x - margin_x, max_x + margin_x)
    ax.set_ylim(min_y - margin_y, max_y + margin_y)
    return min_x, max_x, min_y, max_y

def gerar_mapas(df_filtrado, ano_fim, ano_inicio, nome_alvo, poligono_alvo):
    fig1, ax1 = plt.subplots(figsize=(8, 6), dpi=150)
    ax1.set_facecolor("#F8F9FA")
    bounds = plot_polygon_shape(ax1, poligono_alvo)

    df_atual = df_filtrado[df_filtrado["ano"] == ano_fim]
    if not df_atual.empty:
        ax1.scatter(df_atual["lon"], df_atual["lat"], c="#b52b27", s=18, alpha=0.8, label="Foco de Calor", zorder=3)
        ax1.set_title(f"Dispersão Espacial dos Focos em {ano_fim} — {nome_alvo} ({len(df_atual):,} focos)", fontsize=10, fontweight="bold")
    else:
        ax1.set_title(f"Dispersão Espacial dos Focos em {ano_fim} (Sem focos)", fontsize=10, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.3)
    plt.tight_layout()

    fig2, ax2 = plt.subplots(figsize=(8, 6), dpi=150)
    ax2.set_facecolor("#F8F9FA")
    bounds = plot_polygon_shape(ax2, poligono_alvo)

    if not df_filtrado.empty and bounds:
        GRID_10KM_DEG = 10.0 / 111.0
        colors_density = ["#1A237E", "#2E7D32", "#FBC02D", "#F57C00", "#D32F2F", "#6A1B9A"]
        cmap_densidade = LinearSegmentedColormap.from_list("densidade", colors_density)
        
        min_x, max_x, min_y, max_y = bounds
        x_bins = np.arange(min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
        y_bins = np.arange(min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
        
        counts, xedges, yedges = np.histogram2d(df_filtrado["lon"], df_filtrado["lat"], bins=[x_bins, y_bins])
        counts_masked = np.ma.masked_where(counts == 0, counts)
        X, Y = np.meshgrid(xedges, yedges)
        
        mesh = ax2.pcolormesh(X, Y, counts_masked.T, cmap=cmap_densidade, zorder=3, alpha=0.85, edgecolors="#888888", linewidth=0.1)
        fig2.colorbar(mesh, ax=ax2, orientation="vertical", pad=0.02, shrink=0.8).set_label("Densidade (Grade 10km)", fontsize=8)
        ax2.set_title(f"Densidade Acumulada ({ano_inicio}-{ano_fim}) — {nome_alvo}", fontsize=10, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.3)
    plt.tight_layout()

    return fig1, fig2

# ----------------------------------------------------------------------
# Interface e Barra Lateral
# ----------------------------------------------------------------------
df_focos = carregar_todos_focos(DATA_DIR)

if df_focos.empty:
    st.error("Nenhum dado de foco encontrado.")
    st.stop()

st.sidebar.title("🛠️ Parâmetros da Análise")
tipo_analise = st.sidebar.radio("🎯 Nível de Análise:", options=["Município / Estado", "Unidade de Conservação (UC)", "Terra Indígena (TI)"])
st.sidebar.divider()

poligono_alvo = None
nome_alvo = ""
df_filtrado = pd.DataFrame()

if tipo_analise == "Município / Estado":
    mapa_estados = obter_mapa_estados(GEOJSON_DIR)
    uf_sel = st.sidebar.selectbox("Selecione o Estado (UF):", options=list(mapa_estados.keys()))
    
    # Lista municípios disponíveis diretamente da base de focos + geojson do estado
    muns_uf = sorted([m for m in df_focos[df_focos["SIGLA_UF"] == uf_sel]["NM_MUN"].unique() if m])
    mun_sel = st.sidebar.selectbox("📍 Selecione o Município:", options=muns_uf if muns_uf else ["Nenhum foco encontrado"])
    
    nome_alvo = mun_sel
    poligono_alvo = carregar_geometria_alvo(mapa_estados[uf_sel], "NM_MUN", mun_sel)
    campo_filtro, valor_filtro = "NM_MUN", mun_sel

elif tipo_analise == "Unidade de Conservação (UC)":
    ucs_validas = sorted([u for u in df_focos["UC"].unique() if u and u not in ["NONE", "NULL", "NAN", "N/A", ""]])
    uc_sel = st.sidebar.selectbox("🌲 Selecione a UC:", options=ucs_validas)
    
    nome_alvo = uc_sel
    poligono_alvo = carregar_geometria_alvo(UC_GEOJSON_PATH, "name", uc_sel) or carregar_geometria_alvo(UC_GEOJSON_PATH, "NO_UC", uc_sel)
    campo_filtro, valor_filtro = "UC", uc_sel

elif tipo_analise == "Terra Indígena (TI)":
    tis_validas = sorted([t for t in df_focos["TI"].unique() if t and t not in ["NONE", "NULL", "NAN", "N/A", ""]])
    ti_sel = st.sidebar.selectbox("🏹 Selecione a TI:", options=tis_validas)
    
    nome_alvo = ti_sel
    poligono_alvo = carregar_geometria_alvo(TI_GEOJSON_PATH, "terras_indigenas", ti_sel) or carregar_geometria_alvo(TI_GEOJSON_PATH, "NO_TI", ti_sel)
    campo_filtro, valor_filtro = "TI", ti_sel

anos_disp = sorted(df_focos["ano"].dropna().unique().astype(int))
intervalo_anos = st.sidebar.slider("📅 Intervalo de Anos:", min_value=min(anos_disp), max_value=max(anos_disp), value=(min(anos_disp), max(anos_disp)))

# ----------------------------------------------------------------------
# Processamento Rápido via Pandas
# ----------------------------------------------------------------------
ano_in, ano_fim = intervalo_anos
df_escopo = df_focos[(df_focos["ano"] >= ano_in) & (df_focos["ano"] <= ano_fim)]
df_filtrado = df_escopo[df_escopo[campo_filtro] == valor_filtro.upper()]

st.title(f"Diagnóstico Territorial: {nome_alvo}")

# KPIs
col1, col2, col3 = st.columns(3)
total_atual = len(df_filtrado[df_filtrado["ano"] == ano_fim])
total_periodo = len(df_filtrado)
col1.metric(f"Focos em {ano_fim}", f"{total_atual:,}".replace(",", "."))
col2.metric("Total no Período", f"{total_periodo:,}".replace(",", "."))
col3.metric("Média Anual", f"{int(total_periodo / (ano_fim - ano_in + 1)):,}".replace(",", "."))

st.divider()

# Mapas e Gráficos
c1, c2 = st.columns(2)
with c1:
    fig_m1, fig_m2 = gerar_mapas(df_filtrado, ano_fim, ano_in, nome_alvo, poligono_alvo)
    st.pyplot(fig_m1, use_container_width=True)
with c2:
    st.pyplot(fig_m2, use_container_width=True)

# Rankings Globais Instantâneos
st.divider()
st.markdown("### 🏆 Rankings Gerais no Período Selecionado")

tab_mun, tab_uc, tab_ti = st.tabs(["📍 Top Municípios", "🌲 Top UCs", "🏹 Top TIs"])

def gerar_tabela_ranking(df_in, coluna_grupo, nome_coluna):
    df_g = df_in[df_in[coluna_grupo].isin(["", "NONE", "NULL", "NAN", "N/A"]) == False]
    counts = df_g[coluna_grupo].value_counts().reset_index()
    counts.columns = [nome_coluna, "Focos de Calor"]
    counts["Participação (%)"] = ((counts["Focos de Calor"] / len(df_in)) * 100).round(2)
    counts.index += 1
    return counts

with tab_mun:
    st.dataframe(gerar_tabela_ranking(df_escopo, "NM_MUN", "Município"), use_container_width=True)

with tab_uc:
    st.dataframe(gerar_tabela_ranking(df_escopo, "UC", "Unidade de Conservação"), use_container_width=True)

with tab_ti:
    st.dataframe(gerar_tabela_ranking(df_escopo, "TI", "Terra Indígena"), use_container_width=True)