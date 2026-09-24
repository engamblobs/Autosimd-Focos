from datetime import datetime
import glob
import importlib.util
import io
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
from PIL import Image as PILImage

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
# Configurações e Dicionários Institucionais
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


LOOKUP_REGIAO = {}
for mun, reg in MAPA_MUNICIPIO_REGIAO.items():
    LOOKUP_REGIAO[mun.upper()] = reg
    LOOKUP_REGIAO[remover_acentos(mun.upper())] = reg


def get_regiao_municipio(mun_name):
    mun_upper = mun_name.strip().upper()
    return LOOKUP_REGIAO.get(mun_upper, LOOKUP_REGIAO.get(remover_acentos(mun_upper), "Não Identificada"))


# ----------------------------------------------------------------------
# Leitor KML e Ajuste Proporcional Espacial
# ----------------------------------------------------------------------
def find_and_parse_kml(municipio_alvo, kml_dir=PATH_KML_DIR):
    if not os.path.exists(kml_dir):
        print(f"Aviso: Diretório KML não encontrado em {kml_dir}")
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
        print(f"Aviso: Arquivo KML para '{municipio_alvo}' não encontrado em {kml_dir}")
        return []

    polygons = []
    try:
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
                        lon, lat = float(parts[0]), float(parts[1])
                        coords.append((lon, lat))
                    except ValueError:
                        pass
            if len(coords) >= 3:
                polygons.append(coords)
    except Exception as e:
        print(f"Erro ao ler arquivo KML {matched_path}: {e}")

    return polygons


def draw_kml_boundary(ax, kml_polygons):
    """Desenha o polígono territorial e aplica aspecto cartográfico real (Sem distorção)."""
    if not kml_polygons:
        return None

    all_lons, all_lats = [], []
    for poly in kml_polygons:
        lons, lats = zip(*poly)
        all_lons.extend(lons)
        all_lats.extend(lats)
        ax.fill(lons, lats, facecolor="#E9ECEF", edgecolor="#212529", linewidth=0.8, alpha=0.55, zorder=1)

    min_x, max_x = min(all_lons), max(all_lons)
    min_y, max_y = min(all_lats), max(all_lats)

    pad_x = (max_x - min_x) * 0.05 if max_x != min_x else 0.05
    pad_y = (max_y - min_y) * 0.05 if max_y != min_y else 0.05

    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)

    # Mantém a proporção real 1:1 ajustada pela latitude média
    mean_lat = (min_y + max_y) / 2.0
    aspect = 1.0 / np.cos(np.radians(mean_lat))
    ax.set_aspect(aspect, adjustable="box")

    return (min_x, max_x, min_y, max_y)


def create_proportional_image(buf, max_w=520, max_h=150):
    """Calcula o tamanho da imagem no PDF mantendo estritamente a proporção original do Matplotlib."""
    buf.seek(0)
    pil_img = PILImage.open(buf)
    w, h = pil_img.size
    img_aspect = w / h

    target_w = max_w
    target_h = target_w / img_aspect

    if target_h > max_h:
        target_h = max_h
        target_w = target_h * img_aspect

    buf.seek(0)
    return Image(buf, width=target_w, height=target_h)


# ----------------------------------------------------------------------
# Processamento de GeoJSON
# ----------------------------------------------------------------------
def load_data_from_geojsons(data_dir=DATA_DIR, municipio_alvo="SANTARÉM", uf="PA"):
    files = sorted(glob.glob(os.path.join(data_dir, "*.geojson")))
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo GeoJSON encontrado em: {data_dir}")

    focos_por_ano_mun = {}
    acumulado_historico = {}
    anos_processados = set()

    coords_ano_atual = []
    coords_historico_ano = []

    mun_alvo_upper = municipio_alvo.strip().upper()

    for filepath in files:
        filename = os.path.basename(filepath)
        match = re.search(r"\d{4}", filename)
        if not match:
            continue

        ano = int(match.group(0))
        anos_processados.add(ano)

        if ano not in focos_por_ano_mun:
            focos_por_ano_mun[ano] = {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)
                features = geojson_data.get("features", [])

                for feat in features:
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    mun = props.get("Municipio")

                    if mun:
                        mun_upper = mun.strip().upper()
                        focos_por_ano_mun[ano][mun_upper] = focos_por_ano_mun[ano].get(mun_upper, 0) + 1
                        acumulado_historico[mun_upper] = acumulado_historico.get(mun_upper, 0) + 1

                        if mun_upper == mun_alvo_upper and geom and geom.get("type") == "Point":
                            coords = geom.get("coordinates", [])
                            if len(coords) >= 2:
                                lon, lat = coords[0], coords[1]
                                coords_historico_ano.append((lon, lat, ano))

        except Exception as e:
            print(f"Erro ao ler {filename}: {e}")

    anos_ordenados = sorted(list(anos_processados))
    ano_inicio = anos_ordenados[0]
    ano_fim = anos_ordenados[-1]

    for lon, lat, ano in coords_historico_ano:
        if ano == ano_fim:
            coords_ano_atual.append((lon, lat))

    regiao_alvo = get_regiao_municipio(mun_alvo_upper)

    focos_ano_atual = focos_por_ano_mun.get(ano_fim, {}).get(mun_alvo_upper, 0)
    ano_anterior = ano_fim - 1 if (ano_fim - 1) in focos_por_ano_mun else None
    focos_ano_anterior = focos_por_ano_mun.get(ano_anterior, {}).get(mun_alvo_upper, 0) if ano_anterior else 0

    variacao_anual_pct = (
        ((focos_ano_atual - focos_ano_anterior) / focos_ano_anterior * 100)
        if focos_ano_anterior > 0 else 0.0
    )

    total_estado_ano_atual = sum(focos_por_ano_mun.get(ano_fim, {}).values())
    peso_estadual_pct = (focos_ano_atual / total_estado_ano_atual * 100) if total_estado_ano_atual > 0 else 0.0

    ranking_acumulado = sorted(acumulado_historico.items(), key=lambda x: x[1], reverse=True)
    muns_acumulado = [m[0] for m in ranking_acumulado]
    pos_historico = muns_acumulado.index(mun_alvo_upper) + 1 if mun_alvo_upper in muns_acumulado else 0

    ranking_ano_atual = sorted(focos_por_ano_mun.get(ano_fim, {}).items(), key=lambda x: x[1], reverse=True)
    muns_atual = [m[0] for m in ranking_ano_atual]
    pos_ano_atual = muns_atual.index(mun_alvo_upper) + 1 if mun_alvo_upper in muns_atual else 0

    anos_grafico = [str(a) for a in anos_ordenados]
    focos_grafico = [focos_por_ano_mun[int(a)].get(mun_alvo_upper, 0) for a in anos_grafico]

    top5_muns = [m[0].title() for m in ranking_acumulado[:5]]
    top5_focos = [m[1] for m in ranking_acumulado[:5]]

    tabela_ranking_estado = []
    for idx, (m_name, count_atual) in enumerate(ranking_ano_atual[:5], start=1):
        tabela_ranking_estado.append({
            "posicao": f"{idx}º",
            "municipio": m_name.title(),
            "regiao": get_regiao_municipio(m_name),
            "focos_atual": count_atual,
            "acumulado": acumulado_historico.get(m_name, 0),
        })

    muns_da_regiao = [
        m_name for m_name in focos_por_ano_mun.get(ano_fim, {}).keys()
        if get_regiao_municipio(m_name).lower() == regiao_alvo.lower()
    ]

    ranking_regional = sorted(
        [(m, focos_por_ano_mun[ano_fim][m]) for m in muns_da_regiao],
        key=lambda x: x[1],
        reverse=True
    )

    total_focos_regiao = sum(cnt for _, cnt in ranking_regional)

    tabela_ranking_regional = []
    for idx, (m_name, count_atual) in enumerate(ranking_regional, start=1):
        pct_regiao = (count_atual / total_focos_regiao * 100) if total_focos_regiao > 0 else 0.0
        tabela_ranking_regional.append({
            "posicao": f"{idx}º",
            "municipio": m_name.title(),
            "focos_atual": count_atual,
            "acumulado": acumulado_historico.get(m_name, 0),
            "pct_regiao": pct_regiao
        })

    kml_polygons = find_and_parse_kml(municipio_alvo, kml_dir=PATH_KML_DIR)

    return {
        "municipio": municipio_alvo.title(),
        "uf": uf,
        "regiao": regiao_alvo,
        "ano_inicio": ano_inicio,
        "ano_fim": ano_fim,
        "data_analise": datetime.now().strftime("%d/%m/%Y"),
        "fonte": "BDQueimadas / INPE (Aqua-Tarde)",
        "kpis": {
            "focos_ano_atual": focos_ano_atual,
            "ranking_historico": f"{pos_historico}º lugar",
            "densidade_posicao": f"{pos_ano_atual}º lugar",
            "peso_estadual_pct": peso_estadual_pct,
            "variacao_anual_pct": variacao_anual_pct,
        },
        "top5_estado": {"municipios": top5_muns, "focos": top5_focos},
        "historico_municipio": {"anos": anos_grafico, "focos": focos_grafico},
        "tabela_ranking_estado": tabela_ranking_estado,
        "tabela_ranking_regional": tabela_ranking_regional,
        "coords_ano_atual": coords_ano_atual,
        "coords_historico_ano": coords_historico_ano,
        "kml_polygons": kml_polygons,
    }


# ----------------------------------------------------------------------
# Suporte Canvas e Gráficos da P1
# ----------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
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
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#444444"))
        self.setStrokeColor(colors.HexColor("#CCCCCC"))
        self.setLineWidth(0.5)
        self.line(30, 32, 565, 32)

        self.drawString(30, 20, "RELATÓRIO AUTOMÁTICO DE FOCOS DE CALOR — ANÁLISE MUNICIPAL")
        self.drawString(30, 10, "CBMPA | Coordenadoria Estadual de Proteção e Defesa Civil — DGR / Fonte: BDQueimadas INPE")
        self.drawRightString(565, 20, f"Página {self._pageNumber} de {page_count}")
        self.restoreState()


def custom_k_formatter(x, pos):
    if x == 0:
        return "0"
    elif x >= 1000:
        val = x / 1000
        if val.is_integer():
            return f"{int(val)} mil"
        return f"{val:.1f} mil".replace(".", ",")
    return f"{int(x)}"


def generate_p1_charts(top5_muns, top5_focos, hist_anos, hist_focos, municipio_alvo):
    fig1, ax1 = plt.subplots(figsize=(3.5, 1.6), dpi=150)
    bar_colors = ["#b52b27" if m.lower() == municipio_alvo.lower() else "#a6b1e1" for m in top5_muns]

    ax1.barh(top5_muns[::-1], top5_focos[::-1], color=bar_colors[::-1])
    ax1.set_title("Top 5 Focos Historicamente (Estado)", fontsize=8, fontweight="bold")
    ax1.tick_params(axis="both", labelsize=6.5)
    ax1.xaxis.set_major_formatter(FuncFormatter(custom_k_formatter))
    plt.tight_layout()

    buf1 = io.BytesIO()
    plt.savefig(buf1, format="png")
    plt.close(fig1)
    buf1.seek(0)

    fig2, ax2 = plt.subplots(figsize=(3.5, 1.6), dpi=150)
    x_idxs = np.arange(len(hist_anos))
    y_vals = np.array(hist_focos)

    ax2.plot(x_idxs, y_vals, marker="o", markersize=2.5, color="#b52b27", linewidth=1.5, label="Focos")

    if len(x_idxs) > 1:
        z = np.polyfit(x_idxs, y_vals, 1)
        p = np.poly1d(z)
        ax2.plot(x_idxs, p(x_idxs), color="#333333", linestyle="--", linewidth=1.1, label="Tendência")

    ax2.set_title(f"Evolução Anual Histórica ({hist_anos[0]}-{hist_anos[-1]})", fontsize=8, fontweight="bold")
    ax2.set_xticks(x_idxs[::2])
    ax2.set_xticklabels(hist_anos[::2], rotation=45, ha="right", fontsize=5.5)
    ax2.tick_params(axis="y", labelsize=6)
    ax2.yaxis.set_major_formatter(FuncFormatter(custom_k_formatter))
    ax2.legend(fontsize=5.5, loc="upper right", frameon=False)
    plt.tight_layout()

    buf2 = io.BytesIO()
    plt.savefig(buf2, format="png")
    plt.close(fig2)
    buf2.seek(0)

    return Image(buf1, width=260, height=120), Image(buf2, width=260, height=120)


# ----------------------------------------------------------------------
# Gerador dos 3 Mapas Proporcionais
# ----------------------------------------------------------------------
def generate_p2_maps(coords_atual, coords_hist_ano, municipio, ano_fim, ano_inicio, kml_polygons):
    """Gera os 3 mapas empilhados garantindo proporção e enquadramento real KML."""
    
    # 1. Dispersão Espacial
    fig1, ax1 = plt.subplots(figsize=(7, 2.3), dpi=200)
    ax1.set_facecolor("#F8F9FA")
    draw_kml_boundary(ax1, kml_polygons)

    if coords_atual:
        lons, lats = zip(*coords_atual)
        ax1.scatter(lons, lats, c="#b52b27", s=8, alpha=0.8, edgecolors="none", zorder=3)
        ax1.set_title(f"1. Dispersão Espacial dos Focos ({ano_fim}) — {municipio} ({len(coords_atual):,} focos)".replace(",", "."), fontsize=8, fontweight="bold", pad=4)
    else:
        ax1.text(0.5, 0.5, f"Sem focos registrados em {ano_fim}", ha="center", va="center", fontsize=8, transform=ax1.transAxes)
        ax1.set_title(f"1. Dispersão Espacial ({ano_fim})", fontsize=8, fontweight="bold")

    ax1.tick_params(axis="both", labelsize=5.5)
    ax1.grid(True, linestyle=":", alpha=0.4, color="#AAAAAA", zorder=2)
    plt.tight_layout()

    buf1 = io.BytesIO()
    plt.savefig(buf1, format="png")
    plt.close(fig1)

    # 2. Densidade Espacial (Hexbin)
    fig2, ax2 = plt.subplots(figsize=(7, 2.3), dpi=200)
    ax2.set_facecolor("#F8F9FA")
    draw_kml_boundary(ax2, kml_polygons)

    if coords_hist_ano:
        hlons, hlats, _ = zip(*coords_hist_ano)
        hb = ax2.hexbin(hlons, hlats, gridsize=40, cmap="YlOrRd", mincnt=1, alpha=0.82, zorder=3)
        cb = fig2.colorbar(hb, ax=ax2, orientation="vertical", pad=0.015, shrink=0.85)
        cb.ax.tick_params(labelsize=5.5)
        cb.set_label("Concentração", fontsize=5.5)
        ax2.set_title(f"2. Densidade Espacial Acumulada ({ano_inicio}-{ano_fim}) — {municipio} ({len(coords_hist_ano):,} focos)".replace(",", "."), fontsize=8, fontweight="bold", pad=4)
    else:
        ax2.text(0.5, 0.5, "Sem dados históricos georreferenciados", ha="center", va="center", fontsize=8, transform=ax2.transAxes)
        ax2.set_title("2. Densidade Espacial Histórica", fontsize=8, fontweight="bold")

    ax2.tick_params(axis="both", labelsize=5.5)
    ax2.grid(True, linestyle=":", alpha=0.4, color="#AAAAAA", zorder=2)
    plt.tight_layout()

    buf2 = io.BytesIO()
    plt.savefig(buf2, format="png")
    plt.close(fig2)

    # 3. Recorrência Temporária (Reincidência em Grade)
    fig3, ax3 = plt.subplots(figsize=(7, 2.3), dpi=200)
    ax3.set_facecolor("#F8F9FA")
    draw_kml_boundary(ax3, kml_polygons)

    if coords_hist_ano:
        grid_size = 0.02
        recorrencia_grid = {}
        for lon, lat, ano in coords_hist_ano:
            bx = round(lon / grid_size) * grid_size
            by = round(lat / grid_size) * grid_size
            if (bx, by) not in recorrencia_grid:
                recorrencia_grid[(bx, by)] = set()
            recorrencia_grid[(bx, by)].add(ano)

        rx = [k[0] for k in recorrencia_grid.keys()]
        ry = [k[1] for k in recorrencia_grid.keys()]
        rcount = [len(v) for v in recorrencia_grid.values()]

        sc = ax3.scatter(rx, ry, c=rcount, cmap="plasma", s=12, alpha=0.85, marker="s", zorder=3)
        cb3 = fig3.colorbar(sc, ax=ax3, orientation="vertical", pad=0.015, shrink=0.85)
        cb3.ax.tick_params(labelsize=5.5)
        cb3.set_label("Anos Reincidentes", fontsize=5.5)
        ax3.set_title(f"3. Recorrência Temporal ({ano_inicio}-{ano_fim}) — Reincidência em Grade (~2km)", fontsize=8, fontweight="bold", pad=4)
    else:
        ax3.text(0.5, 0.5, "Sem dados para cálculo de recorrência", ha="center", va="center", fontsize=8, transform=ax3.transAxes)
        ax3.set_title("3. Recorrência Espacial dos Focos", fontsize=8, fontweight="bold")

    ax3.tick_params(axis="both", labelsize=5.5)
    ax3.grid(True, linestyle=":", alpha=0.4, color="#AAAAAA", zorder=2)
    plt.tight_layout()

    buf3 = io.BytesIO()
    plt.savefig(buf3, format="png")
    plt.close(fig3)

    img1 = create_proportional_image(buf1, max_w=520, max_h=150)
    img2 = create_proportional_image(buf2, max_w=520, max_h=150)
    img3 = create_proportional_image(buf3, max_w=520, max_h=150)

    return img1, img2, img3


def build_centered_table(image_obj):
    t = Table([[image_obj]], colWidths=[520])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ----------------------------------------------------------------------
# Construtor do PDF
# ----------------------------------------------------------------------
def generate_full_report(dados, output_filename="relatorio_completo_santarem.pdf"):
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=20,
        bottomMargin=45,
    )

    title_style = ParagraphStyle(
        "HeaderTitle", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#111111"), alignment=1
    )
    kpi_number_style = ParagraphStyle(
        "KpiNum", fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#b52b27"), alignment=1
    )
    kpi_label_style = ParagraphStyle(
        "KpiLabel", fontName="Helvetica", fontSize=6, leading=8, textColor=colors.HexColor("#333333"), alignment=1
    )
    section_title = ParagraphStyle(
        "SecTitle", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#1A365D"), spaceBefore=3, spaceAfter=2
    )
    body_style = ParagraphStyle(
        "BodyTextCustom", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#222222")
    )
    meth_title_style = ParagraphStyle(
        "MethTitle", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#1A365D"), spaceAfter=3
    )
    meth_sub_style = ParagraphStyle(
        "MethSub", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#b52b27"), spaceBefore=4, spaceAfter=1
    )
    meth_text_style = ParagraphStyle(
        "MethText", fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#333333"), spaceAfter=2
    )

    # Estilos compactados da Tabela de Síntese Espacial
    tbl_header_style = ParagraphStyle(
        "TblHeader", fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=colors.white
    )
    tbl_cell_style = ParagraphStyle(
        "TblCell", fontName="Helvetica", fontSize=6.5, leading=8, textColor=colors.HexColor("#222222")
    )

    elements = []

    # ==================================================================
    # PÁGINA 1: DIAGNÓSTICO MUNICIPAL
    # ==================================================================
    img_esq = Image(PATH_BRASAO_PARA, width=42, height=48) if os.path.exists(PATH_BRASAO_PARA) else Paragraph("<b>[PARÁ]</b>", body_style)
    img_dir = Image(PATH_CBM_CEDEC, width=60, height=44) if os.path.exists(PATH_CBM_CEDEC) else Paragraph("<b>[CBM]</b>", body_style)

    header_text = Paragraph(
        "Corpo de Bombeiros Militar do Pará<br/>"
        "Coordenadoria Estadual de Proteção e Defesa Civil<br/>"
        "Divisão de Gestão de Risco - DGR<br/>"
        "<font color='#b52b27'><b>DIAGNÓSTICO AUTOMÁTICO DE FOCOS DE CALOR MUNICIPAL</b></font><br/>"
        f"<b>{dados['municipio'].upper()} - {dados['uf']}</b>",
        title_style,
    )

    header_table = Table([[img_esq, header_text, img_dir]], colWidths=[65, 405, 65])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))

    meta_data = [[
        Paragraph(f"<b>Município:</b> {dados['municipio']}", body_style),
        Paragraph(f"<b>Região:</b> {dados['regiao']}", body_style),
        Paragraph(f"<b>Período:</b> {dados['ano_inicio']} a {dados['ano_fim']}", body_style),
        Paragraph(f"<b>Data:</b> {dados['data_analise']}", body_style),
        Paragraph(f"<b>Fonte:</b> {dados['fonte']}", body_style),
    ]]
    meta_table = Table(meta_data, colWidths=[110, 115, 110, 85, 115])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F3F5")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7DE")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E1E4E8")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 4))

    kpi_data = [
        [
            Paragraph(f"{dados['kpis']['focos_ano_atual']:,}".replace(",", "."), kpi_number_style),
            Paragraph(str(dados['kpis']['ranking_historico']), kpi_number_style),
            Paragraph(str(dados['kpis']['densidade_posicao']), kpi_number_style),
            Paragraph(f"{dados['kpis']['peso_estadual_pct']:.1f}%".replace(".", ","), kpi_number_style),
            Paragraph(f"{dados['kpis']['variacao_anual_pct']:+.1f}%".replace(".", ","), kpi_number_style),
        ],
        [
            Paragraph(f"FOCOS EM {dados['ano_fim']}<br/>Acumulado Atual", kpi_label_style),
            Paragraph("RANKING HISTÓRICO<br/>Posição no Estado", kpi_label_style),
            Paragraph(f"RANKING {dados['ano_fim']}<br/>Posição no Ano", kpi_label_style),
            Paragraph("PESO ESTADUAL<br/>% do Total do Pará", kpi_label_style),
            Paragraph("VARIAÇÃO ANUAL<br/>Comparado ao Ano Anterior", kpi_label_style),
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[107] * 5)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF5F5")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2B2B2")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F0D2D2")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 4))

    elements.append(Paragraph("Comparativo Estadual e Tendência Histórica", section_title))
    c1, c2 = generate_p1_charts(
        dados["top5_estado"]["municipios"],
        dados["top5_estado"]["focos"],
        dados["historico_municipio"]["anos"],
        dados["historico_municipio"]["focos"],
        dados["municipio"],
    )
    charts_table = Table([[c1, c2]], colWidths=[267, 267])
    charts_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(charts_table)
    elements.append(Spacer(1, 4))

    elements.append(Paragraph(f"Top 5 Municípios no Ranking Geral do Estado ({dados['ano_fim']})", section_title))
    t1_data = [["Posição", "Município", "Região de Integração", f"Focos ({dados['ano_fim']})", "Acumulado Histórico"]]
    for row in dados["tabela_ranking_estado"]:
        t1_data.append([
            str(row["posicao"]),
            row["municipio"],
            row["regiao"],
            f"{row['focos_atual']:,}".replace(",", "."),
            f"{row['acumulado']:,}".replace(",", ".")
        ])

    t1_table = Table(t1_data, colWidths=[55, 130, 150, 90, 110])
    styles_t1 = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (4, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, row in enumerate(dados["tabela_ranking_estado"], start=1):
        if row["municipio"].lower() == dados["municipio"].lower():
            styles_t1.extend([
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFE8E8")),
                ("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#b52b27")),
            ])
    t1_table.setStyle(TableStyle(styles_t1))
    elements.append(t1_table)
    elements.append(Spacer(1, 5))

    elements.append(Paragraph(f"Comparativo na {dados['regiao']} ({dados['ano_fim']})", section_title))
    t2_data = [["Posição Região", "Município", f"Focos ({dados['ano_fim']})", "Acumulado Histórico", "% da Região"]]
    for row in dados["tabela_ranking_regional"]:
        t2_data.append([
            str(row["posicao"]),
            row["municipio"],
            f"{row['focos_atual']:,}".replace(",", "."),
            f"{row['acumulado']:,}".replace(",", "."),
            f"{row['pct_regiao']:.1f}%".replace(".", ",")
        ])

    t2_table = Table(t2_data, colWidths=[80, 150, 95, 110, 100])
    styles_t2 = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B4C7E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, row in enumerate(dados["tabela_ranking_regional"], start=1):
        if row["municipio"].lower() == dados["municipio"].lower():
            styles_t2.extend([
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFE8E8")),
                ("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#b52b27")),
            ])
    t2_table.setStyle(TableStyle(styles_t2))
    elements.append(t2_table)

    # ==================================================================
    # PÁGINA 2: 3 MAPAS EMPILHADOS + TABELA DE SÍNTESE ESPACIAL
    # ==================================================================
    elements.append(PageBreak())

    elements.append(Paragraph(f"MAPEAMENTO ESPACIAL E RECORRÊNCIA TEMPORAL — {dados['municipio'].upper()}", meth_title_style))
    elements.append(Spacer(1, 2))

    map1, map2, map3 = generate_p2_maps(
        dados["coords_ano_atual"],
        dados["coords_historico_ano"],
        dados["municipio"],
        dados["ano_fim"],
        dados["ano_inicio"],
        dados["kml_polygons"]
    )

    elements.append(build_centered_table(map1))
    elements.append(Spacer(1, 2))
    elements.append(build_centered_table(map2))
    elements.append(Spacer(1, 2))
    elements.append(build_centered_table(map3))
    elements.append(Spacer(1, 4))

    # Tabela com Fonte Reduzida e Compacta
    spatial_summary = [
        [
            Paragraph("PARÂMETRO ESPACIAL", tbl_header_style),
            Paragraph("DIAGNÓSTICO TÉCNICO E OPERACIONAL", tbl_header_style),
        ],
        [
            Paragraph("Ocorrências Ano Atual", tbl_cell_style),
            Paragraph(f"{len(dados['coords_ano_atual']):,} focos mapeados em {dados['ano_fim']}".replace(",", "."), tbl_cell_style),
        ],
        [
            Paragraph("Acumulado Histórico Mapeado", tbl_cell_style),
            Paragraph(f"{len(dados['coords_historico_ano']):,} focos ({dados['ano_inicio']}-{dados['ano_fim']})".replace(",", "."), tbl_cell_style),
        ],
        [
            Paragraph("Base Vetorial Territorial", tbl_cell_style),
            Paragraph(f"Vetor KML oficial do município ({PATH_KML_DIR})", tbl_cell_style),
        ],
        [
            Paragraph("Resolução de Recorrência", tbl_cell_style),
            Paragraph("Células quadradas de ~0.02° (~2.2km) para medição da reincidência anual.", tbl_cell_style),
        ],
        [
            Paragraph("Aplicação Defesa Civil", tbl_cell_style),
            Paragraph("Direcionamento de sobrevoos, patrulhas e instalação de bases de combate.", tbl_cell_style),
        ]
    ]

    spatial_table = Table(spatial_summary, colWidths=[150, 370])
    spatial_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A365D")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(spatial_table)

    # ==================================================================
    # PÁGINA 3: METODOLOGIA E CANAIS DE SUPORTE
    # ==================================================================
    elements.append(PageBreak())

    elements.append(Paragraph("METODOLOGIA E FONTE DOS DADOS", meth_title_style))
    elements.append(Paragraph("Este documento descreve os critérios técnicos, métodos de processamento e canais oficiais para suporte dos dados apresentados.", meth_text_style))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph("1. Fonte de Dados e Processamento Espacial", meth_sub_style))
    elements.append(Paragraph(
        "Os dados brutos são provenientes do banco BDQueimadas do Instituto Nacional de Pesquisas Espaciais (INPE). "
        "<b>Para esta análise, foram utilizados exclusivamente os dados do satélite de referência Aqua-Tarde</b>, "
        "assegurando a padronização e consistência temporal para comparações entre anos. "
        f"A base processada abrange a série histórica do período de <b>{dados['ano_inicio']} a {dados['ano_fim']}</b>, armazenada em arquivos GeoJSON.",
        meth_text_style
    ))

    elements.append(Paragraph("2. Regionalização de Integração do Estado do Pará", meth_sub_style))
    elements.append(Paragraph(
        "A vinculação territorial obedece à divisão oficial do Pará em 12 Regiões de Integração. "
        "O enquadramento é executado por algoritmo que cruza a propriedade <i>'Municipio'</i> da feição espacial com o dicionário institucional, "
        "aplicando tratamento para remoção de acentos e padronização de caracteres.",
        meth_text_style
    ))

    elements.append(Paragraph("3. Métricas dos Indicadores Chave (KPIs)", meth_sub_style))
    elements.append(Paragraph(
        f"• <b>Focos em {dados['ano_fim']}:</b> Contagem absoluta dos focos detectados pelo satélite Aqua-Tarde no último ano da base.<br/>"
        "• <b>Ranking Histórico:</b> Posição do município no ranking estadual com base no acumulado total da série histórica.<br/>"
        f"• <b>Ranking {dados['ano_fim']}:</b> Posição do município no estado considerando estritamente as ocorrências do ano corrente.<br/>"
        f"• <b>Peso Estadual (%):</b> Proporção do município no total registrado pelo estado no ano de {dados['ano_fim']}:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<i>Peso Estadual = (Focos do Município no Ano / Total de Focos no Pará no Ano) × 100</i><br/>"
        "• <b>Variação Anual (%):</b> Percentual de alteração em relação ao ano imediatamente anterior:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<i>Variação = [(Focos Ano Atual - Focos Ano Anterior) / Focos Ano Anterior] × 100</i>",
        meth_text_style
    ))

    elements.append(Paragraph("4. Construção dos Gráficos, Mapeamentos e Recorrência", meth_sub_style))
    elements.append(Paragraph(
        "• <b>Mapa de Dispersão Espacial:</b> Plotagem pontual sobre a geometria extraída do vetor KML municipal.<br/>"
        "• <b>Mapa de Densidade Espacial:</b> Agrupamento espacial contínuo do histórico através de histograma hexagonal (<i>Hexbin</i>).<br/>"
        "• <b>Mapa de Recorrência Espacial:</b> Avalia a frequência multianual dividindo o território em células de ~2km. "
        "Calcula-se o número de anos distintos em que a célula registrou pelo menos um foco de calor, permitindo identificar áreas de pressão persistente.<br/>"
        "• <b>Evolução Anual Histórica:</b> Série temporal com todos os anos mapeados e linha de tendência calculada por Regressão Polinomial (NumPy <i>polyfit</i>).",
        meth_text_style
    ))

    elements.append(Paragraph("5. Agregadores das Tabelas Comparativas", meth_sub_style))
    elements.append(Paragraph(
        "• <b>Top 5 Ranking Geral do Estado:</b> Principais municípios do estado no ano atual, com indicação de sua Região de Integração.<br/>"
        "• <b>Comparativo na Região de Integração:</b> Exibição de todos os municípios pertencentes à mesma região do município auditado, "
        "com o cálculo de sua representatividade local (<i>% da Região</i>).",
        meth_text_style
    ))

    elements.append(Paragraph("6. Processamento Automatizado e Canais de Atendimento", meth_sub_style))
    elements.append(Paragraph(
        "Os dados deste relatório foram processados automaticamente por algoritmos desenvolvidos com apoio de "
        "<b>Inteligência Artificial orientada a técnicos de Defesa Civil</b>, garantindo precisão técnica e agilidade analítica.<br/><br/>"
        "Em caso de dúvidas, solicitações ou apontamentos metodológicos, entre em contato através dos canais institucionais:<br/>"
        "• <b>E-mail:</b> simdcedec@gmail.com (Com o assunto: <i>'AUTOSIMD-FOCOS: DÚVIDA'</i>)<br/>"
        "• <b>WhatsApp (Plantão Estadual de Defesa Civil):</b> (91) 98899-6323",
        meth_text_style
    ))

    doc.build(elements, canvasmaker=NumberedCanvas)


# ----------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("Carregando e processando arquivos GeoJSON e limite KML...")
    dados_reais = load_data_from_geojsons(data_dir=DATA_DIR, municipio_alvo="SANTARÉM")
    print(f"Período: {dados_reais['ano_inicio']} a {dados_reais['ano_fim']} | Região de Integração: {dados_reais['regiao']}")
    print(f"Coordenadas carregadas: {len(dados_reais['coords_ano_atual']):,} (Ano Atual) | {len(dados_reais['coords_historico_ano']):,} (Histórico)".replace(",", "."))
    print(f"Polígonos KML encontrados: {len(dados_reais['kml_polygons'])}")
    generate_full_report(dados_reais, output_filename="relatorio_completo_santarem.pdf")
    print("Relatório em PDF gerado com sucesso!")