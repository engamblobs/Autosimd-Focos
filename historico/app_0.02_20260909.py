from datetime import datetime
import glob
import importlib.util
import io
import json
import os
import re
import unicodedata
import zipfile

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from PIL import Image as PILImage
import streamlit as st

# ReportLab para PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import (
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
PATH_LOGOS_DIR = "/home/lobs/Automacoes/AUTOSIMD-FOCOS/core/logos"
PATH_BRASAO_PARA = os.path.join(PATH_LOGOS_DIR, "BRASAO-PARA.png")
PATH_CBM_CEDEC = os.path.join(PATH_LOGOS_DIR, "CBM-CEDEC.png")
DATA_DIR = "/home/lobs/SIG/FOCOS DE CALOR"
PATH_KML_DIR = "/home/lobs/SIG/munKML"
PATH_DICIONARIO_REGIOES = "/home/lobs/Automacoes/AUTOSIMD-FOCOS/core/dicionario_municipios-regioes.py"

spec = importlib.util.spec_from_file_location("dicionario_regioes", PATH_DICIONARIO_REGIOES)
dict_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dict_module)
MAPA_MUNICIPIO_REGIAO = dict_module.MAPA_MUNICIPIO_REGIAO


def remover_acentos(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


LOOKUP_REGIAO = {m.upper(): r for m, r in MAPA_MUNICIPIO_REGIAO.items()}
for m, r in MAPA_MUNICIPIO_REGIAO.items():
    LOOKUP_REGIAO[remover_acentos(m.upper())] = r


def get_regiao_municipio(mun_name):
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


st.set_page_config(
    page_title="AutoSIMD - FOCOS",
    page_icon="🔥",
    layout="wide",
)

# ----------------------------------------------------------------------
# CSS Adaptativo para Modo Claro / Escuro & Fontes Ampliadas
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
    </style>
""", unsafe_allow_html=True)


def render_header(municipio_sel="SELECIONE"):
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
                <div class="sub">DIAGNÓSTICO AUTOMÁTICO DE FOCOS DE CALOR MUNICIPAL</div>
                <div class="mun">{municipio_sel.upper()} - PA</div>
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
                <b>RELATÓRIO AUTOMÁTICO DE FOCOS DE CALOR — ANÁLISE MUNICIPAL</b><br/>
                CBMPA | Coordenadoria Estadual de Proteção e Defesa Civil — DGR / Fonte: BDQueimadas INPE
            </div>
            <div style="text-align: right;">
                AutoSIMD - FOCOS © 2026
            </div>
        </div>
    """, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Processamento de Dados Geospaciais e Sazonalidade
# ----------------------------------------------------------------------
@st.cache_data
def get_available_years_and_municipalities(data_dir=DATA_DIR):
    files = sorted(glob.glob(os.path.join(data_dir, "*.geojson")))
    anos, municipios = set(), set()
    for fp in files:
        m = re.search(r"\d{4}", os.path.basename(fp))
        if m: anos.add(int(m.group(0)))
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
                for feat in data.get("features", []):
                    mun = feat.get("properties", {}).get("Municipio")
                    if mun: municipios.add(mun.strip().upper())
        except Exception: pass
    return sorted(list(anos)), sorted(list(municipios))


def find_and_parse_kml(municipio_alvo, kml_dir=PATH_KML_DIR):
    if not os.path.exists(kml_dir): return []
    target_norm = remover_acentos(municipio_alvo.strip().lower())
    matched_path = None
    for filename in os.listdir(kml_dir):
        if filename.lower().endswith(".kml"):
            name_part = filename.replace("NM_MUN_", "").replace(".kml", "").replace(".KML", "")
            if remover_acentos(name_part.strip().lower()) == target_norm:
                matched_path = os.path.join(kml_dir, filename)
                break
    if not matched_path: return []
    polygons = []
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(matched_path)
        root = tree.getroot()
        for elem in root.iter():
            if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
        for coord_elem in root.iter('coordinates'):
            text = coord_elem.text
            if not text: continue
            coords = []
            for pt in text.strip().split():
                parts = pt.split(',')
                if len(parts) >= 2:
                    try: coords.append((float(parts[0]), float(parts[1])))
                    except ValueError: pass
            if len(coords) >= 3: polygons.append(coords)
    except Exception: pass
    return polygons


def draw_kml_boundary(ax, kml_polygons):
    if not kml_polygons: return None
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
    if x == 0: return "0"
    elif x >= 1000:
        val = x / 1000
        return f"{int(val)} mil" if val.is_integer() else f"{val:.1f} mil".replace(".", ",")
    return f"{int(x)}"


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


def generate_trimester_recurrence_map(coords_hist_mes, municipio, ano_inicio, ano_fim, kml_polygons):
    """Gera um mapa em painel 2x2 com a densidade de ocorrências por trimestre em grade de 10km."""
    GRID_10KM_DEG = 10.0 / 111.0
    trimestres = [
        ("1º Trimestre (Jan - Mar)", [1, 2, 3]),
        ("2º Trimestre (Abr - Jun)", [4, 5, 6]),
        ("3º Trimestre (Jul - Set)", [7, 8, 9]),
        ("4º Trimestre (Out - Dez)", [10, 11, 12])
    ]

    fig, axes = plt.subplots(2, 2, figsize=(11, 9), dpi=180)
    axes = axes.flatten()

    all_lons = [p[0] for poly in kml_polygons for p in poly] if kml_polygons else [c[0] for c in coords_hist_mes]
    all_lats = [p[1] for poly in kml_polygons for p in poly] if kml_polygons else [c[1] for c in coords_hist_mes]

    if not all_lons or not all_lats:
        return None

    min_x, max_x = min(all_lons), max(all_lons)
    min_y, max_y = min(all_lats), max(all_lats)

    x_bins = np.arange(min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
    y_bins = np.arange(min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
    X, Y = np.meshgrid(x_bins, y_bins)

    # Calcular contagens por trimestre para determinar escala unificada
    trim_counts = []
    max_val_global = 1
    for _, meses in trimestres:
        pts = [(lon, lat) for lon, lat, m in coords_hist_mes if m in meses]
        if pts:
            lx, ly = zip(*pts)
            c, _, _ = np.histogram2d(lx, ly, bins=[x_bins, y_bins])
            trim_counts.append(c)
            if c.max() > max_val_global:
                max_val_global = c.max()
        else:
            trim_counts.append(np.zeros((len(x_bins) - 1, len(y_bins) - 1)))

    cmap = plt.cm.YlOrRd

    for idx, (label, _) in enumerate(trimestres):
        ax = axes[idx]
        ax.set_facecolor("#F8F9FA")
        draw_kml_boundary(ax, kml_polygons)

        counts = trim_counts[idx]
        counts_masked = np.ma.masked_where(counts == 0, counts)

        if counts.max() > 0:
            ax.pcolormesh(X, Y, counts_masked.T, cmap=cmap, vmin=1, vmax=max_val_global, zorder=3, alpha=0.85, edgecolors="#888888", linewidth=0.1)

        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)

    fig.subplots_adjust(right=0.88, hspace=0.22, wspace=0.15)
    cbar_ax = fig.add_axes([0.90, 0.15, 0.02, 0.7])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=1, vmax=max_val_global))
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label("Focos Acumulados na Quadrícula (Grade 10 km)", fontsize=9)

    fig.suptitle(f"Recorrência Espacial Sazonal Por Trimestre ({ano_inicio}-{ano_fim}) — {municipio}", fontsize=12, fontweight="bold", y=0.96)
    return fig


def generate_map_figures(coords_atual, coords_hist_ano, municipio, ano_fim, ano_inicio, kml_polygons):
    GRID_10KM_DEG = 10.0 / 111.0
    colors_density = ["#1A237E", "#2E7D32", "#FBC02D", "#F57C00", "#D32F2F", "#6A1B9A"]
    cmap_densidade = LinearSegmentedColormap.from_list("densidade_extensiva", colors_density)

    fig1, ax1 = plt.subplots(figsize=(9, 7), dpi=180)
    ax1.set_facecolor("#F8F9FA")
    bounds = draw_kml_boundary(ax1, kml_polygons)
    if coords_atual:
        lons, lats = zip(*coords_atual)
        ax1.scatter(lons, lats, c="#b52b27", s=18, alpha=0.8, edgecolors="none", zorder=3, label="Foco de Calor")
        ax1.set_title(f"1. Dispersão Espacial dos Focos em {ano_fim} — {municipio} ({len(coords_atual):,} focos)".replace(",", "."), fontsize=11, fontweight="bold")
    else:
        ax1.text(0.5, 0.5, f"Sem focos em {ano_fim}", ha="center", va="center", transform=ax1.transAxes)
        ax1.set_title(f"1. Dispersão Espacial dos Focos em {ano_fim}", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)
    plt.tight_layout()

    fig2, ax2 = plt.subplots(figsize=(9, 7), dpi=180)
    ax2.set_facecolor("#F8F9FA")
    bounds = draw_kml_boundary(ax2, kml_polygons)
    if coords_hist_ano and bounds:
        hlons, hlats, _ = zip(*coords_hist_ano)
        min_x, max_x, min_y, max_y = bounds
        x_bins = np.arange(min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
        y_bins = np.arange(min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
        counts, xedges, yedges = np.histogram2d(hlons, hlats, bins=[x_bins, y_bins])
        counts_masked = np.ma.masked_where(counts == 0, counts)
        X, Y = np.meshgrid(xedges, yedges)
        mesh2 = ax2.pcolormesh(X, Y, counts_masked.T, cmap=cmap_densidade, zorder=3, alpha=0.85, edgecolors="#888888", linewidth=0.1)
        cb2 = fig2.colorbar(mesh2, ax=ax2, orientation="vertical", pad=0.02, shrink=0.8)
        cb2.set_label("Concentração de Focos (Grade 10km × 10km)", fontsize=8)
        ax2.set_title(f"2. Densidade Espacial Acumulada ({ano_inicio}-{ano_fim}) — Grade 10 km × 10 km — {municipio}", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)
    plt.tight_layout()

    fig3, ax3 = plt.subplots(figsize=(9, 7), dpi=180)
    ax3.set_facecolor("#F8F9FA")
    bounds = draw_kml_boundary(ax3, kml_polygons)
    if coords_hist_ano and bounds:
        min_x, max_x, min_y, max_y = bounds
        x_bins = np.arange(min_x - GRID_10KM_DEG, max_x + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
        y_bins = np.arange(min_y - GRID_10KM_DEG, max_y + 2 * GRID_10KM_DEG, GRID_10KM_DEG)
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
        mesh3 = ax3.pcolormesh(X, Y, rec_masked.T, cmap="plasma", zorder=3, alpha=0.85, edgecolors="#888888", linewidth=0.1)
        cb3 = fig3.colorbar(mesh3, ax=ax3, orientation="vertical", pad=0.02, shrink=0.8)
        cb3.set_label("Nº de Anos com Reincidência", fontsize=8)
        ax3.set_title(f"3. Recorrência Temporal dos Focos ({ano_inicio}-{ano_fim}) — Grade 10 km × 10 km", fontsize=11, fontweight="bold")
    ax3.grid(True, linestyle=":", alpha=0.25, color="#CCCCCC", zorder=2)
    plt.tight_layout()

    return fig1, fig2, fig3


def generate_qgis_grid_geojson(coords_hist, kml_bounds, cell_size_deg=10.0/111.0):
    if not kml_bounds or not coords_hist: return None
    min_x, max_x, min_y, max_y = kml_bounds
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
# Interface do Usuário (Streamlit)
# ----------------------------------------------------------------------
anos_disponiveis, municipios_disponiveis = get_available_years_and_municipalities()

if not anos_disponiveis:
    st.error("Nenhum arquivo GeoJSON encontrado no diretório de dados.")
    st.stop()

st.sidebar.title("🛠️ Parâmetros da Análise")
municipio_selecionado = st.sidebar.selectbox(
    "📍 Selecione o Município:",
    options=municipios_disponiveis,
    index=municipios_disponiveis.index("ALTAMIRA") if "ALTAMIRA" in municipios_disponiveis else 0
)

intervalo_anos = st.sidebar.slider(
    "📅 Intervalo de Anos:",
    min_value=min(anos_disponiveis),
    max_value=max(anos_disponiveis),
    value=(min(anos_disponiveis), max(anos_disponiveis)),
    step=1
)

st.sidebar.divider()
st.sidebar.subheader("📦 Produtos para Exportação")
exp_excel = st.sidebar.checkbox("📊 Planilha Excel (.xlsx)", value=True)
exp_images = st.sidebar.checkbox("🖼️ Imagens dos Mapas/Gráficos (.png)", value=True)
exp_qgis = st.sidebar.checkbox("🗺️ Camada de Grade QGIS (.geojson)", value=True)

btn_processar = st.sidebar.button("🚀 Processar Diagnóstico Completo", type="primary", use_container_width=True)

render_header(municipio_selecionado)

if btn_processar:
    ano_inicio_sel, ano_fim_sel = intervalo_anos
    mun_upper = municipio_selecionado.strip().upper()

    with st.spinner("Processando geodados, sazonalidade e gerando mapeamentos..."):
        files = sorted(glob.glob(os.path.join(DATA_DIR, "*.geojson")))
        focos_por_ano_mun = {}
        acumulado_historico = {}
        coords_historico_ano = []
        coords_historico_mes = []
        coords_ano_atual = []
        monthly_counts_mun = {m: 0 for m in range(1, 13)}

        for filepath in files:
            m = re.search(r"\d{4}", os.path.basename(filepath))
            if not m: continue
            ano = int(m.group(0))
            if ano < ano_inicio_sel or ano > ano_fim_sel: continue

            if ano not in focos_por_ano_mun: focos_por_ano_mun[ano] = {}

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    mun = props.get("Municipio")
                    if mun:
                        m_u = mun.strip().upper()
                        focos_por_ano_mun[ano][m_u] = focos_por_ano_mun[ano].get(m_u, 0) + 1
                        acumulado_historico[m_u] = acumulado_historico.get(m_u, 0) + 1

                        if m_u == mun_upper:
                            mes_val = extrair_mes_data(props)
                            if mes_val and 1 <= mes_val <= 12:
                                monthly_counts_mun[mes_val] += 1

                            if geom and geom.get("type") == "Point":
                                coords = geom.get("coordinates", [])
                                if len(coords) >= 2:
                                    coords_historico_ano.append((coords[0], coords[1], ano))
                                    if mes_val:
                                        coords_historico_mes.append((coords[0], coords[1], mes_val))
                                    if ano == ano_fim_sel:
                                        coords_ano_atual.append((coords[0], coords[1]))

        regiao_alvo = get_regiao_municipio(mun_upper)
        focos_ano_atual = focos_por_ano_mun.get(ano_fim_sel, {}).get(mun_upper, 0)
        ano_ant = ano_fim_sel - 1 if (ano_fim_sel - 1) in focos_por_ano_mun else None
        focos_ano_ant = focos_por_ano_mun.get(ano_ant, {}).get(mun_upper, 0) if ano_ant else 0

        var_anual_pct = (((focos_ano_atual - focos_ano_ant) / focos_ano_ant) * 100) if focos_ano_ant > 0 else 0.0
        total_estado_ano = sum(focos_por_ano_mun.get(ano_fim_sel, {}).values())
        peso_est_pct = (focos_ano_atual / total_estado_ano * 100) if total_estado_ano > 0 else 0.0

        ranking_acumulado = sorted(acumulado_historico.items(), key=lambda x: x[1], reverse=True)
        muns_acum = [m[0] for m in ranking_acumulado]
        pos_hist = muns_acum.index(mun_upper) + 1 if mun_upper in muns_acum else 0

        ranking_atual = sorted(focos_por_ano_mun.get(ano_fim_sel, {}).items(), key=lambda x: x[1], reverse=True)
        muns_atual = [m[0] for m in ranking_atual]
        pos_atual = muns_atual.index(mun_upper) + 1 if mun_upper in muns_atual else 0

        # -------------------------------------------------------------
        # 1. EXIBIÇÃO: RESUMO EXECUTIVO (KPIs)
        # -------------------------------------------------------------
        st.markdown(f"### 📌 Resumo Executivo — {municipio_selecionado.title()} ({ano_inicio_sel} a {ano_fim_sel})")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(f"Focos em {ano_fim_sel}", f"{focos_ano_atual:,}".replace(",", "."))
        k2.metric("Ranking Histórico", f"{pos_hist}º lugar")
        k3.metric(f"Ranking em {ano_fim_sel}", f"{pos_atual}º lugar")
        k4.metric("Peso Estadual", f"{peso_est_pct:.1f}%".replace(".", ","))
        k5.metric("Variação Anual", f"{var_anual_pct:+.1f}%".replace(".", ","))

        st.divider()

        # -------------------------------------------------------------
        # 2. EXIBIÇÃO: GRÁFICOS COMPARATIVOS E SAZONALIDADE
        # -------------------------------------------------------------
        st.markdown("### 📈 Diagnóstico Geral e Análise de Sazonalidade")
        top5_muns = [m[0].title() for m in ranking_acumulado[:5]]
        top5_focos = [m[1] for m in ranking_acumulado[:5]]
        anos_grafico = [str(a) for a in sorted(list(focos_por_ano_mun.keys()))]
        focos_grafico = [focos_por_ano_mun[int(a)].get(mun_upper, 0) for a in anos_grafico]

        fig_chart1, fig_chart2 = generate_p1_charts_figures(top5_muns, top5_focos, anos_grafico, focos_grafico, municipio_selecionado)
        g_col1, g_col2 = st.columns(2)
        with g_col1: st.pyplot(fig_chart1, use_container_width=True)
        with g_col2: st.pyplot(fig_chart2, use_container_width=True)

        st.markdown("#### 🗓️ Padrão Sazonal de Incidência (Distribuição Mensal)")
        fig_sazonalidade = generate_seasonality_chart(monthly_counts_mun)
        st.pyplot(fig_sazonalidade, use_container_width=True)

        st.divider()

        # -------------------------------------------------------------
        # 3. EXIBIÇÃO: TABELAS DE RANKING
        # -------------------------------------------------------------
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
                    "Acumulado": acumulado_historico.get(m[0], 0)
                }
                for idx, m in enumerate(ranking_atual[:5], start=1)
            ])
            st.dataframe(df_est, use_container_width=True, hide_index=True)

        with t_col2:
            st.markdown(f"**Comparativo na {regiao_alvo} ({ano_fim_sel})**")
            muns_reg = [m for m in focos_por_ano_mun.get(ano_fim_sel, {}).keys() if get_regiao_municipio(m).lower() == regiao_alvo.lower()]
            ranking_reg = sorted([(m, focos_por_ano_mun[ano_fim_sel][m]) for m in muns_reg], key=lambda x: x[1], reverse=True)
            tot_reg = sum(c for _, c in ranking_reg)
            df_reg = pd.DataFrame([
                {
                    "Posição": f"{idx}º",
                    "Município": m[0].title(),
                    f"Focos ({ano_fim_sel})": m[1],
                    "% Região": f"{(m[1]/tot_reg*100):.1f}%".replace(".", ",") if tot_reg > 0 else "0%"
                }
                for idx, m in enumerate(ranking_reg, start=1)
            ])
            st.dataframe(df_reg, use_container_width=True, hide_index=True)

        st.divider()

        # -------------------------------------------------------------
        # 4. EXIBIÇÃO: MAPAS GEOSPACIAIS COMPLETOS E TRIMESTRAIS
        # -------------------------------------------------------------
        st.markdown("### 🗺️ Mapeamento Espacial e Sazonalidade Trimestral")
        kml_poly = find_and_parse_kml(municipio_selecionado)
        fig_map1, fig_map2, fig_map3 = generate_map_figures(
            coords_ano_atual, coords_historico_ano, municipio_selecionado,
            ano_fim_sel, ano_inicio_sel, kml_poly
        )

        st.pyplot(fig_map1, use_container_width=True)
        st.pyplot(fig_map2, use_container_width=True)
        st.pyplot(fig_map3, use_container_width=True)

        # Novo Mapa: Recorrência Sazonal Espacial Trimestral
        fig_map_trimestre = generate_trimester_recurrence_map(
            coords_historico_mes, municipio_selecionado, ano_inicio_sel, ano_fim_sel, kml_poly
        )
        if fig_map_trimestre:
            st.markdown("#### 🔄 Migração Espacial Sazonal (Concentração em Grade 10 km por Trimestre)")
            st.pyplot(fig_map_trimestre, use_container_width=True)

        st.divider()

        # -------------------------------------------------------------
        # 5. SÍNTESE ESPACIAL E METODOLOGIA
        # -------------------------------------------------------------
        st.markdown("### 📐 Síntese Espacial e Metodologia")

        s_col1, s_col2 = st.columns([1, 1])

        with s_col1:
            st.markdown("**Parâmetros Técnicos e Operacionais**")
            df_sintese = pd.DataFrame([
                {"Parâmetro": "Ocorrências Ano Atual", "Diagnóstico": f"{len(coords_ano_atual):,} focos mapeados em {ano_fim_sel}".replace(",", ".")},
                {"Parâmetro": "Acumulado Histórico", "Diagnóstico": f"{len(coords_historico_ano):,} focos ({ano_inicio_sel}-{ano_fim_sel})".replace(",", ".")},
                {"Parâmetro": "Grade Geospacial", "Diagnóstico": "Células de 10 km × 10 km (~0.09°)"},
                {"Parâmetro": "Aplicação Operacional", "Diagnóstico": "Definição de rotas de sobrevoo e bases de combate"}
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

        # -------------------------------------------------------------
        # 6. PAINEL DE DOWNLOADS
        # -------------------------------------------------------------
        st.markdown("### 📥 Exportação de Arquivos Brutos e Produtos")
        d1, d2, d3 = st.columns(3)

        if exp_excel:
            df_hist_export = pd.DataFrame([
                {"Ano": a, "Focos": focos_por_ano_mun.get(a, {}).get(mun_upper, 0)}
                for a in range(ano_inicio_sel, ano_fim_sel + 1)
            ])
            meses_nomes = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            df_sazonal_export = pd.DataFrame([
                {"Mês": meses_nomes[m-1], "Focos_Acumulados": monthly_counts_mun[m]}
                for m in range(1, 13)
            ])

            buf_excel = io.BytesIO()
            with pd.ExcelWriter(buf_excel, engine='openpyxl') as writer:
                df_hist_export.to_excel(writer, sheet_name="Evolucao_Historica", index=False)
                df_sazonal_export.to_excel(writer, sheet_name="Sazonalidade_Mensal", index=False)
            buf_excel.seek(0)
            d1.download_button(
                "📊 Baixar Planilha (.xlsx)", buf_excel,
                file_name=f"estatisticas_{mun_upper}_{ano_inicio_sel}_{ano_fim_sel}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        if exp_images:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for idx, fig_item in enumerate([fig_map1, fig_map2, fig_map3], start=1):
                    b = io.BytesIO()
                    fig_item.savefig(b, format="png", bbox_inches="tight")
                    zip_file.writestr(f"mapa_{idx}_{mun_upper}.png", b.getvalue())
                
                if fig_map_trimestre:
                    b_trim = io.BytesIO()
                    fig_map_trimestre.savefig(b_trim, format="png", bbox_inches="tight")
                    zip_file.writestr(f"mapa_sazonalidade_trimestral_{mun_upper}.png", b_trim.getvalue())

                b_saz = io.BytesIO()
                fig_sazonalidade.savefig(b_saz, format="png", bbox_inches="tight")
                zip_file.writestr(f"grafico_sazonalidade_{mun_upper}.png", b_saz.getvalue())

            zip_buf.seek(0)
            d2.download_button(
                "🖼️ Baixar Imagens PNG (.zip)", zip_buf,
                file_name=f"imagens_{mun_upper}.zip",
                mime="application/zip",
                use_container_width=True
            )

        if exp_qgis:
            lons = [c[0] for c in coords_historico_ano] if coords_historico_ano else [-53.0]
            lats = [c[1] for c in coords_historico_ano] if coords_historico_ano else [-3.0]
            bounds = (min(lons), max(lons), min(lats), max(lats))
            grid_json = generate_qgis_grid_geojson(coords_historico_ano, bounds)
            if grid_json:
                d3.download_button(
                    "🗺️ Baixar Grade QGIS (.geojson)", json.dumps(grid_json, indent=2).encode('utf-8'),
                    file_name=f"grade_10km_{mun_upper}.geojson",
                    mime="application/json",
                    use_container_width=True
                )

else:
    st.info("👈 Defina o município e o período no painel à esquerda e clique em **Processar Diagnóstico Completo**.")

render_footer()