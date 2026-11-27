# -*- coding: utf-8 -*-
"""Boletim em PDF das localidades sob risco de fogo e fumaça (docs/10 §9.1; P47 aprovada em 27/11/2026).

A4 retrato, mesmo cabeçalho e rodapé dos outros PDFs:

1. **situação** — fontes e horário dos dados, 4 fichas, mapa estático (satélite, localidades pela classe, eventos,
   frentes, cones e setas de vento) e um parágrafo automático com as localidades mais expostas;
2. **lista de prioridade** — só risco moderado ou maior, com o motivo, horas para chegar, PM2,5 (faixa da CONAMA
   491/2018), distância da sede e coordenadas, para o despacho das equipes;
3. **eventos e tempo** — tabela dos eventos, severidade ao longo das passagens do satélite, vento hora a hora no
   maior evento ativo e PM2,5 hora a hora nas localidades mais expostas, com as faixas da CONAMA;
4. **método e limites** — o texto de ``METODOLOGIA_VULNERABILIDADE`` (docs/07 §13), fontes e créditos.

``pacote_vulnerabilidade`` junta o PDF, os GeoJSON (localidades com a classe, eventos e cones) e a planilha.
Quem chama fecha as figuras (``plt.close``) — aqui elas são fechadas depois de entrar no PDF.
"""

import io
import json
import re
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from matplotlib.dates import DateFormatter  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle  # noqa: E402

from core.config import APP_NOME, CREDITO_OPEN_METEO, CREDITO_SATELITE  # noqa: E402
from core.fundo_satelite import lonlat_para_mercator, mercator_para_lat, mercator_para_lon, mosaico  # noqa: E402
from core.relatorio_pdf import (  # noqa: E402
    LARGURA_UTIL, MARGEM, CanvasNumerado, _tabela_indicadores, cabecalho_pdf, estilos_pdf,
    imagem_figura, tabela_pdf,
)
from core.territorios import poligonos_de  # noqa: E402
from core.texto import fmt_inteiro, fmt_numero, nome_arquivo, nome_proprio  # noqa: E402
from core.vulnerabilidade import (  # noqa: E402
    CORES_CLASSE, FAIXAS_IQAR_PM25, METODOLOGIA_VULNERABILIDADE, AnaliseVulnerabilidade, dissolver_cones,
    geojson_dos_cones, resumo_por_classe,
)

CLASSES_PRIORIDADE = ("Muito alto", "Alto", "Moderado")
MAX_LINHAS_PRIORIDADE = 80
ALTURA_MAPA_PT = 470            # o mapa cabe na página 1 com as fichas e o parágrafo
FORMATO_HORA = DateFormatter("%d/%m %Hh")
CORES_IQAR = {"Boa": "#C8E6C9", "Moderada": "#FFF59D", "Ruim": "#FFCC80", "Muito ruim": "#EF9A9A",
              "Péssima": "#CE93D8"}
CREDITO_PAINEL_DO_FOGO = "Eventos e frentes de fogo: Painel do Fogo — CENSIPAM (WFS público)"
CREDITO_LOCALIDADES = "Localidades: IBGE, Censo Demográfico 2022 (base de localidades)"


# ---------------------------------------------------------------------- textos

def _hora(momento) -> str:
    """Horário de Belém (os dados ao vivo vêm em UTC)."""
    t = pd.Timestamp(momento)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert("America/Belem").strftime("%d/%m/%Y %H:%M")


def _horas(valor) -> str:
    return "" if pd.isna(valor) else f"~{fmt_numero(float(valor), 0)} h"


def _km(valor) -> str:
    return "" if pd.isna(valor) or not np.isfinite(float(valor)) else fmt_numero(float(valor), 1)


def _tipo(linha) -> str:
    if linha.indigena:
        return "Indígena"
    if linha.quilombola:
        return "Quilombola"
    return str(linha.categoria)


def texto_da_situacao(analise: AnaliseVulnerabilidade, n: int = 6) -> str:
    """Parágrafo automático: quantas e quais localidades estão em risco alto ou muito alto, e por quê."""
    loc = analise.localidades
    altas = loc[loc["classe"].isin(("Muito alto", "Alto"))]
    moderadas = int((loc["classe"] == "Moderado").sum())
    if altas.empty:
        texto = "Nenhuma localidade em risco alto ou muito alto agora."
        if moderadas:
            texto += f" {fmt_inteiro(moderadas)} em risco moderado (lista na página 2)."
        return texto
    itens = [f"{nome_proprio(r.nome)} ({_tipo(r).lower()}) — {r.motivo}" for r in altas.head(n).itertuples()]
    texto = (f"{fmt_inteiro(len(altas))} localidade{'s' if len(altas) > 1 else ''} em risco alto ou muito alto: "
             + "; ".join(itens))
    if len(altas) > n:
        texto += f"; e mais {fmt_inteiro(len(altas) - n)}"
    texto += "."
    if moderadas:
        texto += f" Outras {fmt_inteiro(moderadas)} em risco moderado."
    return texto


# ---------------------------------------------------------------------- figuras

def _em_mercator(geom):
    return shapely.transform(geom, lambda xy: np.column_stack(lonlat_para_mercator(xy[:, 0], xy[:, 1])))


def _preencher(ax, geom, **estilo):
    from matplotlib.patches import Polygon as PoligonoMpl
    for parte in poligonos_de(geom):
        ax.add_patch(PoligonoMpl(np.asarray(parte.exterior.coords), closed=True, **estilo))


def mapa_estatico(analise: AnaliseVulnerabilidade, municipio_geom, nome: str, fundo: bool = True,
                  rotulos: int = 8):
    """Mapa da página 1: satélite (Sentinel-2 cloudless), cones dissolvidos, eventos e frentes, setas do vento
    para onde sopra e as localidades pela classe de risco (as ``rotulos`` mais altas com o nome)."""
    fig, ax = plt.subplots(figsize=(9, 7.4), dpi=150)
    geom = _em_mercator(municipio_geom)
    x0, y0, x1, y1 = geom.bounds
    mx, my = (x1 - x0) * 0.06, (y1 - y0) * 0.06
    ax.set_xlim(x0 - mx, x1 + mx)
    ax.set_ylim(y0 - my, y1 + my)
    imagem = None
    if fundo:
        imagem = mosaico((float(mercator_para_lon(x0 - mx)), float(mercator_para_lat(y0 - my)),
                          float(mercator_para_lon(x1 + mx)), float(mercator_para_lat(y1 + my))))
    if imagem is not None:
        ax.imshow(imagem[0], extent=imagem[1], origin="upper", zorder=0, interpolation="bilinear")
    else:
        ax.set_facecolor("#F1F3EE")
    for parte in poligonos_de(geom):
        ax.plot(*parte.exterior.xy, color="#00E5FF" if imagem is not None else "#1E88E5", linewidth=1.8, zorder=5)
    legenda = []
    for cone in dissolver_cones(analise.cones):
        fogo = cone["tipo"] == "fogo"
        _preencher(ax, _em_mercator(cone["poligono"]), facecolor="#FF5722" if fogo else "#B0BEC5",
                   edgecolor="#BF360C" if fogo else "#607D8B", linewidth=0.6, alpha=0.18 + 0.12 * cone["sobreposicao"],
                   zorder=2)
    if analise.cones:
        legenda += [Patch(facecolor="#FF5722", alpha=0.4, label="Avanço do fogo em 24 h"),
                    Patch(facecolor="#B0BEC5", alpha=0.6, label="Fumaça em 6 h")]
    ev = analise.eventos
    for linha in ev.itertuples():
        _preencher(ax, _em_mercator(linha.geometria), facecolor="none", edgecolor="#D50000", linewidth=1.1, zorder=3)
        if linha.frente is not None:
            _preencher(ax, _em_mercator(linha.frente), facecolor="#FFAB00", edgecolor="#FF6D00", linewidth=0.6,
                       alpha=0.9, zorder=3)
        if not pd.isna(linha.vento_para_graus) and not pd.isna(linha.vento_kmh):
            cx, cy = lonlat_para_mercator(np.array([linha.lon]), np.array([linha.lat]))
            comprimento = (x1 - x0) * 0.07
            angulo = np.radians(float(linha.vento_para_graus))
            ax.annotate("", xy=(cx[0] + comprimento * np.sin(angulo), cy[0] + comprimento * np.cos(angulo)),
                        xytext=(cx[0], cy[0]), zorder=7,
                        arrowprops=dict(arrowstyle="-|>", color="white", lw=2.2, mutation_scale=14))
    if len(ev):
        legenda += [Patch(facecolor="none", edgecolor="#D50000", label="Evento de fogo (Painel do Fogo)"),
                    Patch(facecolor="#FFAB00", edgecolor="#FF6D00", label="Frente de fogo (24 h)"),
                    Line2D([], [], color="white", marker=">", markeredgecolor="#555", label="Vento (para onde sopra)",
                           markerfacecolor="white", linewidth=1.5)]
    loc = analise.localidades
    px, py = lonlat_para_mercator(loc["lon"].to_numpy(), loc["lat"].to_numpy())
    for classe, tamanho in (("Sem exposição", 8), ("Baixo", 14), ("Moderado", 26), ("Alto", 40), ("Muito alto", 56)):
        sel = (loc["classe"] == classe).to_numpy()
        if sel.any():
            ax.scatter(px[sel], py[sel], s=tamanho, c=CORES_CLASSE[classe], edgecolors="black", linewidths=0.5,
                       zorder=6, marker="s" if classe != "Sem exposição" else "o")
            legenda.append(Line2D([], [], marker="s", linestyle="", markerfacecolor=CORES_CLASSE[classe],
                                  markeredgecolor="black", markersize=7, label=f"{classe} ({fmt_inteiro(sel.sum())})"))
    for i, r in enumerate(loc[loc["classe"].isin(CLASSES_PRIORIDADE)].head(rotulos).itertuples()):
        x, y = lonlat_para_mercator(np.array([r.lon]), np.array([r.lat]))
        ax.annotate(nome_proprio(r.nome), (x[0], y[0]), xytext=(5, 4), textcoords="offset points", fontsize=7,
                    fontweight="bold", color="white" if imagem is not None else "#222", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.15", fc="#00000088" if imagem is not None else "#FFFFFFCC",
                              ec="none"))
    ax.set_aspect("equal")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{mercator_para_lon(v):.1f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{mercator_para_lat(v):.1f}"))
    ax.tick_params(labelsize=7)
    ax.set_title(f"Localidades sob risco de fogo e fumaça — {nome}", fontsize=11, fontweight="bold")
    ax.legend(handles=legenda, loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=3, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.text(0.5, 0.01, CREDITO_SATELITE if imagem is not None else
             "Imagem de satélite indisponível (sem conexão com a internet).", ha="center", fontsize=6, color="#555")
    return fig


def grafico_severidade(passagens: pd.DataFrame | None, eventos: pd.DataFrame, n: int = 6):
    """Indicador de severidade (Painel do Fogo) a cada passagem do satélite, nos ``n`` eventos mais severos."""
    if passagens is None or passagens.empty or eventos.empty:
        return None
    ordem = eventos.assign(ativo=eventos["status"] == "Ativo")
    top = ordem.sort_values(["ativo", "severidade"], ascending=False).head(n)["id_evento"]
    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=150)
    for id_evento in top:
        serie = passagens[passagens["id_evento"] == id_evento]
        if len(serie):
            hora = serie["dt_passagem"].dt.tz_convert("America/Belem").dt.tz_localize(None)
            ax.plot(hora, serie["peso_global_passagem"], marker="o", markersize=3, linewidth=1.4,
                    label=f"Evento {id_evento}" + (" (ativo)" if id_evento in set(
                        eventos.loc[eventos["status"] == "Ativo", "id_evento"]) else ""))
    ax.set_ylabel("Indicador de severidade", fontsize=8)
    ax.set_title("Severidade a cada passagem do satélite — ativos primeiro (Painel do Fogo)", fontsize=10,
                 fontweight="bold")
    ax.xaxis.set_major_formatter(DateFormatter("%d/%m"))
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, ncol=3, frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def grafico_vento(vento: pd.DataFrame | None, eventos: pd.DataFrame, agora):
    """Vento previsto nas próximas 24 h no maior evento ativo: velocidade (linha) e direção (setas)."""
    if vento is None or vento.empty or eventos.empty:
        return None
    ativos = eventos.reset_index(drop=True)
    ativos = ativos[ativos["status"] == "Ativo"]
    if ativos.empty:
        return None
    k = int(ativos["area_ha"].idxmax())
    serie = vento[vento["ponto"] == k]
    inicio = pd.Timestamp(agora)
    serie = serie[(serie["hora"] >= inicio) & (serie["hora"] < inicio + pd.Timedelta(hours=24))]
    if serie.empty:
        return None
    hora = (serie["hora"] - pd.Timedelta(hours=3)).to_numpy()        # UTC → horário de Belém
    v = serie["velocidade_kmh"].to_numpy(dtype=float)
    para = np.radians((serie["direcao_graus"].to_numpy(dtype=float) + 180) % 360)
    fig, ax = plt.subplots(figsize=(10, 2.8), dpi=150)
    ax.plot(hora, v, color="#1565C0", linewidth=1.6)
    ax.quiver(hora, v, np.sin(para), np.cos(para), color="#455A64", scale=28, width=0.003, zorder=3)
    ax.set_ylim(0, max(v.max() * 1.35, 10))
    ax.set_ylabel("km/h (10 m)", fontsize=8)
    ax.xaxis.set_major_formatter(FORMATO_HORA)
    ax.set_title(f"Vento previsto nas próximas 24 h — evento {ativos.loc[k, 'id_evento']} (maior ativo); "
                 "setas = para onde sopra", fontsize=10, fontweight="bold")
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=7)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def grafico_pm25(pm25: pd.DataFrame | None, analise: AnaliseVulnerabilidade, agora, n: int = 5):
    """PM2,5 hora a hora nas ``n`` localidades com o maior máximo, sobre as faixas do IQAR (CONAMA 491/2018)."""
    loc = analise.localidades.dropna(subset=["pm25_max"])
    if pm25 is None or pm25.empty or loc.empty:
        return None
    top = loc.sort_values("pm25_max", ascending=False).drop_duplicates("pm25_max").head(n)
    inicio = pd.Timestamp(agora)
    janela = pm25[(pm25["hora"] >= inicio) & (pm25["hora"] < inicio + pd.Timedelta(hours=24))]
    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=150)
    teto = max(float(top["pm25_max"].max()) * 1.15, 60)
    limites = sorted({lim for lim, _ in FAIXAS_IQAR_PM25} | {teto})
    for baixo, alto in zip(limites[:-1], limites[1:]):
        if baixo >= teto:
            break
        nome = next(nm for lim, nm in FAIXAS_IQAR_PM25 if baixo >= lim)
        ax.axhspan(baixo, min(alto, teto), color=CORES_IQAR[nome], alpha=0.55, zorder=0)
        ax.text(1.003, (baixo + min(alto, teto)) / 2, nome, transform=ax.get_yaxis_transform(), fontsize=6.5,
                va="center", color="#444")
    for r in top.itertuples():
        serie = janela[janela["ponto"] == r.ponto]
        if len(serie):
            ax.plot(serie["hora"] - pd.Timedelta(hours=3), serie["pm25"], linewidth=1.5, label=nome_proprio(r.nome))
    ax.set_ylim(0, teto)
    ax.set_ylabel("PM2,5 (µg/m³)", fontsize=8)
    ax.xaxis.set_major_formatter(FORMATO_HORA)
    ax.set_title("PM2,5 previsto nas próximas 24 h — localidades mais expostas (faixas do IQAR, CONAMA 491/2018)",
                 fontsize=10, fontweight="bold")
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, ncol=3, frameon=False, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------- tabelas

def tabela_prioridade(analise: AnaliseVulnerabilidade) -> pd.DataFrame:
    """Localidades em risco moderado ou maior, na ordem de prioridade (também vai para a planilha)."""
    loc = analise.localidades
    loc = loc[loc["classe"].isin(CLASSES_PRIORIDADE)]
    return pd.DataFrame({
        "Localidade": [nome_proprio(n) for n in loc["nome"]],
        "Tipo": [_tipo(r) for r in loc.itertuples()],
        "Risco": loc["classe"], "Motivo": loc["motivo"], "Perfil": loc["perfil"],
        "Fogo chega": [_horas(v) for v in loc["eta_fogo_h"]],
        "Fumaça chega": [_horas(v) for v in loc["eta_fumaca_h"]],
        "PM2,5 máx. 24 h": [("" if pd.isna(v) else f"{v:.0f}") for v in loc["pm25_max"]],
        "Qualidade do ar": loc["qualidade_ar"],
        "Dist. sede (km)": [_km(v) for v in loc["dist_sede_km"]],
        "Latitude": loc["lat"].round(5), "Longitude": loc["lon"].round(5),
    })


def _imagem_limitada(fig, largura: float, altura_max: float):
    """Figura com a largura pedida, ou menor se a altura passar de ``altura_max`` (municípios compridos)."""
    imagem = imagem_figura(fig, largura)
    if imagem.drawHeight > altura_max:
        escala = altura_max / imagem.drawHeight
        imagem.drawWidth, imagem.drawHeight = imagem.drawWidth * escala, altura_max
    return imagem


def _celula(texto, estilo):
    return Paragraph(escape(str(texto)), estilo)


def _bloco_prioridade(analise, est) -> list:
    tab = tabela_prioridade(analise)
    blocos = [Paragraph("Lista de prioridade — risco moderado ou maior", est["secao"])]
    if tab.empty:
        return blocos + [Paragraph("Nenhuma localidade em risco moderado ou maior agora.", est["centro"])]
    celula = est["celula"].clone("CelulaPequena", fontSize=6.5, leading=8)
    linhas = [["#", "Localidade", "Risco", "Motivo principal", "Chega em", "PM2,5 (CONAMA)", "Sede (km)",
               "Lat / Lon"]]
    cores = []
    for i, (_, r) in enumerate(tab.head(MAX_LINHAS_PRIORIDADE).iterrows(), start=1):
        chega = " / ".join(x for x in (f"fogo {r['Fogo chega']}" if r["Fogo chega"] else "",
                                       f"fumaça {r['Fumaça chega']}" if r["Fumaça chega"] else "") if x)
        pm = f"{r['PM2,5 máx. 24 h']} ({r['Qualidade do ar'].lower()})" if r["PM2,5 máx. 24 h"] else ""
        linhas.append([str(i), _celula(f"{r['Localidade']} — {r['Tipo']}", celula), r["Risco"],
                       _celula(r["Motivo"], celula), _celula(chega, celula), _celula(pm, celula),
                       r["Dist. sede (km)"], Paragraph(f"{r['Latitude']:.4f}<br/>{r['Longitude']:.4f}", celula)])
        cores.append(("BACKGROUND", (2, i), (2, i), colors.HexColor(CORES_CLASSE[r["Risco"]])))
        if r["Risco"] in ("Muito alto", "Alto"):
            cores.append(("TEXTCOLOR", (2, i), (2, i), colors.white))
    tabela = tabela_pdf(linhas, [18, 118, 46, 140, 62, 62, 36, 53])
    tabela.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 6.5), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2), *cores]))
    blocos.append(tabela)
    if len(tab) > MAX_LINHAS_PRIORIDADE:
        blocos.append(Paragraph(f"… e mais {fmt_inteiro(len(tab) - MAX_LINHAS_PRIORIDADE)} localidades (lista "
                                "completa na planilha do pacote).", est["nota"]))
    blocos.append(Spacer(1, 4))
    blocos.append(Paragraph(
        "Motivo = o critério que deu a nota de exposição. Chega em = hora prevista para o avanço do fogo (24 h) ou a "
        "fumaça do evento (6 h) alcançarem a localidade. PM2,5 = máximo previsto nas próximas 24 h e a faixa do "
        "índice de qualidade do ar da Resolução CONAMA 491/2018.", est["nota"]))
    return blocos


def _figuras(analise, municipio_geom, nome, ao_vivo, fundo) -> dict:
    ev = analise.eventos
    figuras = {"mapa": mapa_estatico(analise, municipio_geom, nome, fundo=fundo)}
    if ao_vivo:
        figuras["severidade"] = grafico_severidade(ao_vivo.get("passagens"), ev)
        figuras["vento"] = grafico_vento(ao_vivo.get("vento_eventos"), ev, analise.momento)
        figuras["pm25"] = grafico_pm25(ao_vivo.get("pm25"), analise, analise.momento)
    return figuras


def _texto_eventos(ev: pd.DataFrame) -> str:
    ativos = int((ev["status"] == "Ativo").sum())
    texto = (f"{fmt_inteiro(ativos)} eventos ativos e {fmt_inteiro(len(ev) - ativos)} em observação no município e "
             "até ~55 km dele (Painel do Fogo — CENSIPAM). A lista dos eventos, com área, expansão, severidade, vento, "
             "avanço e alcance da fumaça, está na planilha do pacote.")
    return texto


def _metodologia(est) -> list:
    blocos = [Paragraph("Método e limites", est["secao"])]
    for linha in METODOLOGIA_VULNERABILIDADE.strip().splitlines():
        texto = escape(linha.strip())
        if not texto:
            continue
        texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
        texto = re.sub(r"\*(.+?)\*", r"<i>\1</i>", texto)
        recuo = len(linha) - len(linha.lstrip())
        if texto.startswith("- "):
            texto = "• " + texto[2:]
        blocos.append(Paragraph(texto, est["nota"].clone(f"m{recuo}", leftIndent=recuo * 4)))
    blocos += [
        Spacer(1, 6),
        Paragraph("<b>Limites.</b> Protótipo em avaliação: pesos, distâncias e classes ainda podem ser calibrados "
                  "com os registros de ocorrências. A área dos eventos vem dos buffers de 400 m dos focos VIIRS e "
                  "superestima eventos pequenos. Os cones supõem o vento previsto constante e não levam em conta "
                  "relevo, vegetação nem combate. O PM2,5 do CAMS tem resolução de ~40 km: localidades vizinhas "
                  "dividem o mesmo valor. Use como apoio à decisão, junto com a verificação em campo.", est["nota"]),
        Spacer(1, 6),
        Paragraph("<b>Fontes.</b> " + "; ".join(escape(c) for c in (
            "Focos de calor: BDQueimadas/INPE (satélite de referência AQUA)", CREDITO_PAINEL_DO_FOGO,
            CREDITO_OPEN_METEO, CREDITO_LOCALIDADES, CREDITO_SATELITE)) + ".", est["nota"]),
    ]
    return blocos


# ---------------------------------------------------------------------- PDF e pacote

def historia_vulnerabilidade(analise: AnaliseVulnerabilidade, municipio: str, estado: str, municipio_geom,
                             ao_vivo: dict | None, ultimo_dia_base=None, fundo: bool = True,
                             agora: datetime | None = None, anexo: bool = False,
                             figuras: dict | None = None) -> tuple[list, dict]:
    """(blocos do reportlab, figuras) do boletim: vira o PDF próprio ou o anexo do diagnóstico completo
    (``anexo=True`` muda o título)."""
    agora = agora or datetime.now()
    nome = nome_proprio(municipio)
    est = estilos_pdf()
    classes = resumo_por_classe(analise)
    ev = analise.eventos
    if figuras is None:              # dadas = as mesmas do boletim solto (o mapa baixa o satélite uma vez só)
        figuras = _figuras(analise, municipio_geom, nome, ao_vivo, fundo)
    historia = cabecalho_pdf(("ANEXO — " if anexo else f"{APP_NOME} — ") + "LOCALIDADES SOB RISCO DE FOGO E FUMAÇA",
                             f"{nome.upper()} ({estado.upper()}) — {_hora(analise.momento)}", est)
    fontes = [f"Focos da base INPE até {ultimo_dia_base:%d/%m/%Y}" if ultimo_dia_base else "Focos da base INPE"]
    if ao_vivo:
        fontes.append(f"Painel do Fogo, vento e PM2,5 buscados em {_hora(ao_vivo['buscado_em'])} (Belém)")
    else:
        fontes.append("sem os dados ao vivo (eventos, vento e PM2,5): só proximidade dos focos e vulnerabilidade")
    historia += [
        Paragraph("Situação agora", est["secao"]),
        _tabela_indicadores([
            ("Localidades analisadas", fmt_inteiro(len(analise.localidades))),
            ("Risco muito alto / alto", f"{classes['Muito alto']} / {classes['Alto']}"),
            ("Risco moderado", fmt_inteiro(classes["Moderado"])),
            ("Eventos ativos / em observação", f"{int((ev['status'] == 'Ativo').sum())} / "
                                               f"{int((ev['status'] == 'Em observação').sum())}" if ao_vivo else "—"),
        ], est),
        Spacer(1, 4),
        Paragraph(escape(" · ".join(fontes) + f". Gerado em {agora:%d/%m/%Y %H:%M}."), est["nota"]),
        Spacer(1, 4),
        Paragraph(escape(texto_da_situacao(analise)), est["nota"].clone("Situacao", fontSize=9, leading=12)),
        Spacer(1, 6),
        _imagem_limitada(figuras["mapa"], 470, ALTURA_MAPA_PT),
    ]
    for aviso in [*(ao_vivo or {}).get("avisos", []), *analise.avisos]:
        historia.append(Paragraph(f"⚠ {escape(aviso)}", est["nota"]))
    # sem a tabela dos eventos de fogo (pedido de 27/11/2026): ela fica na planilha do pacote
    historia += [PageBreak(), *_bloco_prioridade(analise, est), PageBreak(),
                 Paragraph("Eventos de fogo e tempo previsto", est["secao"]),
                 Paragraph(escape(_texto_eventos(ev) if ao_vivo else "Sem os dados ao vivo."), est["nota"])]
    for chave in ("severidade", "vento", "pm25"):
        if figuras.get(chave) is not None:
            historia += [Spacer(1, 8), KeepTogether([imagem_figura(figuras[chave], LARGURA_UTIL)])]
    if not ao_vivo:
        historia.append(Paragraph("Sem os dados ao vivo: busque-os na tela para incluir os eventos, o vento e a "
                                  "fumaça prevista.", est["nota"]))
    historia += [PageBreak(), *_metodologia(est)]
    return historia, figuras


def gerar_pdf_vulnerabilidade(analise: AnaliseVulnerabilidade, municipio: str, estado: str, municipio_geom,
                              ao_vivo: dict | None, ultimo_dia_base=None, fundo: bool = True,
                              agora: datetime | None = None, figuras: dict | None = None) -> tuple[bytes, str, dict]:
    """(PDF, nome do arquivo, figuras) do boletim; ``ao_vivo`` = ``buscar_dados_ao_vivo`` (ou None)."""
    historia, figuras = historia_vulnerabilidade(analise, municipio, estado, municipio_geom, ao_vivo,
                                                 ultimo_dia_base, fundo, agora, figuras=figuras)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM,
                            bottomMargin=45, title=f"{APP_NOME} — Localidades sob risco — {nome_proprio(municipio)}",
                            author=APP_NOME)
    doc.build(historia, canvasmaker=CanvasNumerado)
    nome_pdf = f"localidades_risco_fogo_{nome_arquivo(municipio)}_{analise.momento:%Y%m%d_%H%M}.pdf"
    return buffer.getvalue(), nome_pdf, figuras


def geojson_localidades(analise: AnaliseVulnerabilidade) -> str:
    colunas = ["nome", "categoria", "classe", "risco", "exposicao", "vulnerabilidade", "motivo", "perfil",
               "foco_24h_km", "foco_7d_km", "eta_fogo_h", "eta_fumaca_h", "pm25_max", "qualidade_ar", "dist_sede_km"]
    feicoes = []
    for r in analise.localidades.itertuples():
        propriedades = {}
        for c in colunas:
            v = getattr(r, c)
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (float, np.floating)):
                v = None if not np.isfinite(v) else round(float(v), 2)
            elif v is pd.NA:
                v = None
            propriedades[c] = v if not isinstance(v, str) or c != "nome" else nome_proprio(v)
        feicoes.append({"type": "Feature", "properties": propriedades,
                        "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]}})
    return json.dumps({"type": "FeatureCollection", "features": feicoes}, ensure_ascii=False)


def geojson_eventos(analise: AnaliseVulnerabilidade) -> str:
    feicoes = []
    for r in analise.eventos.itertuples():
        propriedades = {"id_evento": int(r.id_evento), "status": r.status, "area_ha": float(r.area_ha),
                        "expansao_ha_h": float(r.expansao_ha_h),
                        "severidade": None if pd.isna(r.severidade) else float(r.severidade),
                        "inicio": str(r.inicio), "ultima_deteccao": str(r.ultima_deteccao)}
        feicoes.append({"type": "Feature", "properties": propriedades,
                        "geometry": shapely.geometry.mapping(r.geometria)})
    return json.dumps({"type": "FeatureCollection", "features": feicoes}, ensure_ascii=False)


def pacote_vulnerabilidade(pdf: bytes, nome_pdf: str, analise: AnaliseVulnerabilidade, figuras: dict) -> tuple[bytes, str]:
    """ZIP com o PDF, os GeoJSON (localidades, eventos, cones — abrem no QGIS), a planilha e os PNG."""
    from core.produto import png
    base = nome_pdf.removesuffix(".pdf")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(nome_pdf, pdf)
        z.writestr("localidades.geojson", geojson_localidades(analise))
        z.writestr("eventos_de_fogo.geojson", geojson_eventos(analise))
        z.writestr("cones_fogo_fumaca.geojson", geojson_dos_cones(dissolver_cones(analise.cones)))
        planilha = io.BytesIO()
        with pd.ExcelWriter(planilha) as escritor:
            tabela_prioridade(analise).to_excel(escritor, sheet_name="Prioridade", index=False)
            analise.localidades.drop(columns=["ponto"], errors="ignore").to_excel(
                escritor, sheet_name="Todas as localidades", index=False)
            analise.eventos.drop(columns=["geometria", "frente"]).assign(
                inicio=lambda d: d["inicio"].astype(str), ultima_deteccao=lambda d: d["ultima_deteccao"].astype(str)
            ).to_excel(escritor, sheet_name="Eventos", index=False)
        z.writestr("localidades_e_eventos.xlsx", planilha.getvalue())
        for chave, figura in figuras.items():
            if figura is not None:
                z.writestr(f"figuras/{chave}.png", png(figura, dpi=150))
    for figura in figuras.values():
        if figura is not None:
            plt.close(figura)
    return buffer.getvalue(), f"{base}.zip"
