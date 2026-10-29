# -*- coding: utf-8 -*-
"""PDF do diagnóstico — município, UC ou TI (docs/10 §4).

A4 retrato, Helvetica, cabeçalho com logos, faixa vermelha CBMPA e rodapé "Página X de Y"
(mesmo padrão visual do AutoSIMD-DESASTRE).

Seções:
1. cabeçalho e resumo executivo;
2. cenário atual — nowcast (município);
3. gráficos (top do estado no município, evolução anual, sazonalidade);
4. mapas 1 a 4;
5. estatísticas de focos ativos no modelo INPE;
6. rankings (estado, região, UCs/TIs no estado e no Brasil), UCs/TIs no município e nota metodológica.
"""

import io
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.config import (
    APP_NOME, APP_VERSAO, DESENVOLVEDOR_NOME, EMAIL_SALA_MONITORAMENTO, LOGO_APP, LOGO_CBM_CEDEC, TELEFONE_PLANTAO,
)
from core.config import TIPO_TI, TIPO_UC
from core.diagnostico import DiagnosticoMunicipio
from core.estatisticas import (
    MESES_CURTOS, EstatisticasMunicipio, extremos_por_coluna, notas, tabela_diaria_exibicao, tabela_mensal_exibicao,
)
from core.anomalias import TEXTO_METODOLOGIA
from core.grade import grade_do_territorio, nota_grade
from core.kernel import DESVIO_KERNEL_KM
from core.territorios import area_km2
from core.texto import fmt_densidade, fmt_inteiro, fmt_numero, fmt_percentual, fmt_posicao

VERMELHO = colors.HexColor("#B71C1C")
CINZA_TEXTO = colors.HexColor("#444444")
CINZA_CABECALHO = colors.HexColor("#E0E0E0")
CINZA_FUNDO = colors.HexColor("#F5F5F5")
CINZA_GRADE = colors.HexColor("#CCCCCC")

# Destaques das tabelas de estatísticas (mesmas cores do site do INPE)
AMARELO_MINIMO = colors.HexColor("#FFD54F")
VERMELHO_MAXIMO = colors.HexColor("#E53935")
FUNDO_RESUMO = {"Mínimo": colors.HexColor("#FBC02D"), "Média": colors.HexColor("#FB8C00"),
                "Máximo": colors.HexColor("#E53935")}

MARGEM = 30
LARGURA_UTIL = A4[0] - 2 * MARGEM          # 535 pt
LARGURA_MAPA = 480
DPI_FIGURAS = 150


# ---------------------------------------------------------------------- Canvas

class CanvasNumerado(canvas.Canvas):
    """Rodapé com faixa vermelha e "Página X de Y"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estados = []

    def showPage(self):
        self._estados.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._estados)
        for estado in self._estados:
            self.__dict__.update(estado)
            self._rodape(total)
            super().showPage()
        super().save()

    def _rodape(self, total):
        self.saveState()
        self.setStrokeColor(VERMELHO)
        self.setLineWidth(1)
        self.line(MARGEM, 32, A4[0] - MARGEM, 32)
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(CINZA_TEXTO)
        self.drawString(MARGEM, 20, f"{APP_NOME} | CBMPA - Coordenadoria Estadual de Proteção e Defesa Civil (DGR) "
                                    "| Fonte: BDQueimadas/INPE")
        self.drawRightString(A4[0] - MARGEM, 20, f"Página {self._pageNumber} de {total}")
        self.restoreState()


# ---------------------------------------------------------------------- Estilos

def estilos_pdf() -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("Titulo", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=12,
                                 leading=14, textColor=colors.HexColor("#111111"), alignment=1, spaceAfter=0),
        "subtitulo": ParagraphStyle("Subtitulo", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10,
                                    leading=12, textColor=colors.HexColor("#E53935"), alignment=1),
        "destaque": ParagraphStyle("Destaque", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=12,
                                   leading=14, textColor=colors.HexColor("#1E88E5"), alignment=1),
        "centro": ParagraphStyle("Centro", parent=base["Normal"], fontSize=8.5, alignment=1),
        "secao": ParagraphStyle("Secao", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11,
                                leading=14, textColor=VERMELHO, spaceBefore=8, spaceAfter=6),
        "celula": ParagraphStyle("Celula", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10,
                                 alignment=1),
        "celula_cab": ParagraphStyle("CelulaCab", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8,
                                     leading=10, alignment=1),
        "nota": ParagraphStyle("Nota", parent=base["Normal"], fontSize=8, leading=11,
                               textColor=colors.HexColor("#333333"), alignment=TA_JUSTIFY),
    }


def imagem_arquivo(caminho, largura: float):
    """Imagem de arquivo (logos) com a altura pela proporção real; reduzida para não inchar o PDF."""
    if not caminho.exists():
        return ""
    with PILImage.open(caminho) as img:
        w, h = img.size
        copia = img.convert("RGBA")
        copia.thumbnail((int(largura * 4), int(largura * 4 * h / w)))   # ~290 dpi na largura impressa
    buffer = io.BytesIO()
    copia.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return Image(buffer, width=largura, height=largura * h / w)


def imagem_figura(fig, largura: float):
    """Figura do matplotlib como imagem do PDF, mantendo a proporção."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=DPI_FIGURAS)
    buffer.seek(0)
    with PILImage.open(buffer) as img:
        w, h = img.size
    buffer.seek(0)
    return Image(buffer, width=largura, height=largura * h / w)


def tabela_pdf(linhas: list[list], larguras: list[float]) -> Table:
    tabela = Table(linhas, colWidths=larguras, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CINZA_CABECALHO),
        ("GRID", (0, 0), (-1, -1), 0.5, CINZA_GRADE),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabela


# -------------------------------------------------------------------- Blocos

def cabecalho_pdf(titulo: str, destaque: str, est: dict) -> list:
    textos = [
        Paragraph("<b>CORPO DE BOMBEIROS MILITAR DO PARÁ</b>", est["titulo"]),
        Paragraph("Coordenadoria Estadual de Proteção e Defesa Civil — DGR", est["centro"]),
        Paragraph(f"<b>{escape(titulo)}</b>", est["subtitulo"]),
        Paragraph(f"<b>{escape(destaque)}</b>", est["destaque"]),
    ]
    tabela = Table([[imagem_arquivo(LOGO_APP, 110), textos, imagem_arquivo(LOGO_CBM_CEDEC, 65)]],
                   colWidths=[118, 347, 70])
    tabela.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return [tabela, Spacer(1, 6), HRFlowable(width="100%", thickness=1.5, color=VERMELHO, spaceAfter=8)]


def _tabela_indicadores(pares: list[tuple[str, str]], est: dict) -> Table:
    """Indicadores em linhas de 3: rótulo em cima (fundo cinza), valor embaixo."""
    linhas, fundos = [], []
    for i in range(0, len(pares), 3):
        grupo = pares[i:i + 3] + [("", "")] * (3 - len(pares[i:i + 3]))
        fundos.append(len(linhas))
        linhas.append([Paragraph(f"<b>{escape(r)}</b>", est["celula_cab"]) for r, _ in grupo])
        linhas.append([Paragraph(escape(v), est["celula"]) for _, v in grupo])
    tabela = Table(linhas, colWidths=[178] * 3)
    tabela.setStyle(TableStyle([("BACKGROUND", (0, f), (-1, f), CINZA_FUNDO) for f in fundos] + [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, CINZA_GRADE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabela


def resumo_executivo(diag, est: dict) -> list:
    ano = diag.ano_fim
    if isinstance(diag, DiagnosticoMunicipio):
        r = diag.resumo
        pares = [
            (f"Focos em {ano}", fmt_inteiro(r.focos_ano_fim)),
            (f"Posição no país — {ano}", fmt_posicao(r.posicao_pais, r.total_pais)),
            (f"Posição no estado — {ano}", fmt_posicao(r.posicao_estado, r.total_estado)),
            (f"Participação no total do estado ({ano})", fmt_percentual(r.participacao_estado_pct)),
            (f"Variação {ano} vs. {ano - 1}", fmt_percentual(r.variacao_pct, sinal=True)),
            ("Densidade média anual (focos/km²/ano)", fmt_densidade(r.densidade)),
        ]
    else:
        campo = diag.campo
        area = area_km2(diag.poligono)
        no_estado, no_brasil = diag.rankings_areas[f"{campo}_estado"], diag.rankings_areas[f"{campo}_brasil"]
        rotulo = TIPO_UC if campo == "UC" else TIPO_TI

        def pos(tabela):
            linha = tabela[tabela[rotulo] == diag.nome]
            return fmt_posicao(int(linha["Posição"].iloc[0]), len(tabela)) if len(linha) else "Sem focos"
        pares = [
            (f"Focos em {ano}", fmt_inteiro(diag.focos_ano_fim)),
            (f"Total no período ({diag.ano_inicio}–{ano})", fmt_inteiro(diag.focos_periodo)),
            ("Média anual", fmt_inteiro(round(diag.media_anual))),
            (f"Posição entre as {campo}s do estado ({diag.sigla_uf or '—'}) no período", pos(no_estado)),
            (f"Posição entre as {campo}s do Brasil no período", pos(no_brasil)),
            ("Densidade média anual (focos/km²/ano)", fmt_densidade(diag.media_anual / area if area else None)),
        ]
    return [Paragraph("Resumo Executivo — Indicadores Chave", est["secao"]), _tabela_indicadores(pares, est),
            Spacer(1, 10)]


def nowcast_pdf(nowcast, figuras: dict, est: dict) -> list:
    """Cenário atual (P18): indicadores, gráfico dos últimos 30 dias e mapa dos focos recentes."""
    i, dia = nowcast.indicadores, nowcast.ultimo_dia

    def com_media(valor, media):
        return fmt_inteiro(valor) + ("" if media != media else f" (média {fmt_inteiro(round(media))})")
    pares = [
        (f"Focos em {dia:%d/%m/%Y}" + (" (dia parcial)" if nowcast.provisorio else ""),
         com_media(i["ultimo_dia"], i["media_ultimo_dia"])),
        ("Dia anterior", fmt_inteiro(i["dia_anterior"])),
        ("Últimos 7 dias", com_media(i["ultimos_7"], i["media_7"])),
        ("Últimos 30 dias", com_media(i["ultimos_30"], i["media_30"])),
        (f"No ano até {dia:%d/%m}", f"{fmt_inteiro(i['acumulado_ano'])} "
                                    f"({fmt_percentual(i['variacao_acumulado_pct'], sinal=True)} vs. média)"),
        ("Posição do ano até esta data", f"{i['posicao_acumulado']}º de {i['anos_ranking']} anos"),
    ]
    elementos = [Paragraph(f"Cenário Atual — Nowcast Diário (dados até {dia:%d/%m/%Y})", est["secao"]),
                 _tabela_indicadores(pares, est), Spacer(1, 6)]
    if figuras.get("nowcast_diario") is not None:
        elementos += [imagem_figura(figuras["nowcast_diario"], LARGURA_UTIL), Spacer(1, 4)]
    if figuras.get("nowcast_semanal") is not None:
        elementos += [imagem_figura(figuras["nowcast_semanal"], LARGURA_UTIL), Spacer(1, 4)]
    if figuras.get("nowcast_mapa") is not None:
        elementos += [imagem_figura(figuras["nowcast_mapa"], 430)]
    elementos += [Paragraph("Médias = mesmo dia (e janela de ±3 dias) nos anos anteriores que a base cobre por "
                            "inteiro. O último dia pode estar incompleto: o INPE publica os focos ao longo do dia.",
                            est["nota"]), PageBreak()]
    return elementos


def graficos_pdf(figuras: dict, est: dict) -> list:
    elementos = [Paragraph("Diagnóstico Geral e Análise de Sazonalidade", est["secao"])]
    if figuras.get("top_estado") is not None:
        lado_a_lado = Table([[imagem_figura(figuras["top_estado"], 255), imagem_figura(figuras["evolucao"], 255)]],
                            colWidths=[265, 265])
        lado_a_lado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                         ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        elementos.append(lado_a_lado)
    else:
        elementos.append(imagem_figura(figuras["evolucao"], 300))
    elementos += [Spacer(1, 6), imagem_figura(figuras["sazonalidade"], 520), Spacer(1, 10), PageBreak()]
    return elementos


def mapas_pdf(figuras: dict, est: dict) -> list:
    elementos = [Paragraph("Mapeamento Espacial de Focos de Calor", est["secao"])]
    for chave in ("mapa_dispersao", "mapa_densidade", "mapa_recorrencia", "mapa_trimestral"):
        if figuras.get(chave) is not None:
            elementos += [imagem_figura(figuras[chave], LARGURA_MAPA), Spacer(1, 8)]
    return elementos


def anomalias_pdf(figuras: dict, est: dict) -> list:
    """Os três mapas de anomalia (docs/07 §12) com a nota de como ler e a metodologia."""
    chaves = [c for c in ("anomalia_quantidade", "anomalia_localizacao", "anomalia_combinada") if figuras.get(c)]
    if not chaves:
        return []
    elementos = [PageBreak(), Paragraph("Anomalias de Focos de Calor em relação à recorrência comum", est["secao"]),
                 Paragraph(TEXTO_METODOLOGIA, est["nota"]), Spacer(1, 6)]
    for chave in chaves:
        elementos += [imagem_figura(figuras[chave], 430), Spacer(1, 6)]
    return elementos


def _valor(v) -> str:
    return "-" if v is None or v != v else fmt_numero(v)


def tabela_estatistica_pdf(tabela, larguras: list[float], linhas_destaque: list[str], fonte: float = 6.5,
                           recorde: str | None = None) -> Table:
    """Tabela com o menor valor de cada coluna em amarelo e o maior em vermelho (só entre ``linhas_destaque``);
    linhas Mínimo/Média/Máximo com fundo colorido."""
    cabecalho = [tabela.index.name or ""] + [str(c) for c in tabela.columns]
    linhas = [cabecalho] + [[str(i)] + [_valor(v) for v in linha] for i, linha in zip(tabela.index, tabela.values)]
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), CINZA_CABECALHO),
        ("GRID", (0, 0), (-1, -1), 0.4, CINZA_GRADE),
        ("FONTSIZE", (0, 0), (-1, -1), fonte),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]
    indice = {nome: i + 1 for i, nome in enumerate(tabela.index)}
    for j, (minimos, maximos) in enumerate(extremos_por_coluna(tabela, linhas_destaque, recorde).values(), start=1):
        for nome in minimos:
            estilo += [("BACKGROUND", (j, indice[nome]), (j, indice[nome]), AMARELO_MINIMO),
                       ("FONTNAME", (j, indice[nome]), (j, indice[nome]), "Helvetica-Bold")]
        for nome in maximos:
            estilo += [("BACKGROUND", (j, indice[nome]), (j, indice[nome]), VERMELHO_MAXIMO),
                       ("TEXTCOLOR", (j, indice[nome]), (j, indice[nome]), colors.white),
                       ("FONTNAME", (j, indice[nome]), (j, indice[nome]), "Helvetica-Bold")]
    for nome, cor in FUNDO_RESUMO.items():
        if nome in indice:
            estilo += [("BACKGROUND", (0, indice[nome]), (-1, indice[nome]), cor),
                       ("FONTNAME", (0, indice[nome]), (-1, indice[nome]), "Helvetica-Bold")]
    tabela_pdf_ = Table(linhas, colWidths=larguras, repeatRows=1)
    tabela_pdf_.setStyle(TableStyle(estilo))
    return tabela_pdf_


CHAVES_ESTATISTICAS = ("comparativo_mensal", "comparativo_semanal", "comparativo_semestre1", "comparativo_semestre2",
                       "acumulado_mensal")


def estatisticas_pdf(est: EstatisticasMunicipio, figuras: dict, estilos: dict) -> list:
    """Seção "Estatísticas de focos ativos" (modelo do Programa Queimadas/INPE)."""
    p = est.parametros
    elementos = [PageBreak(), Paragraph("Estatísticas de Focos Ativos (modelo Programa Queimadas/INPE)",
                                        estilos["secao"])]
    elementos += [Paragraph(escape(n), estilos["nota"]) for n in notas(est)] + [Spacer(1, 6)]

    mensal = tabela_mensal_exibicao(est)
    mensal.columns = MESES_CURTOS + ["Total"]
    anos = [str(a) for a in est.anos_estatistica]   # o ano de referência não é destacado
    elementos += [
        Paragraph(f"<b>Total de focos detectados em cada mês ({est.ano_inicio}–{est.ano_fim})</b>",
                  estilos["celula_cab"]), Spacer(1, 3),
        tabela_estatistica_pdf(mensal, [38] + [37] * 12 + [53], anos, recorde=str(est.ano_referencia)), Spacer(1, 8),
    ]
    diario = tabela_diaria_exibicao(est)
    if not diario.empty:
        elementos += [Paragraph(f"<b>Total de focos detectados dia a dia — mês {p.mes_diario:02d}</b>",
                                estilos["celula_cab"]), Spacer(1, 3)]
        for colunas in (diario.columns[:16], diario.columns[16:]):
            parte = diario[list(colunas)]
            elementos += [tabela_estatistica_pdf(parte, [50] + [29] * len(colunas), [], fonte=6), Spacer(1, 4)]
    for chave in CHAVES_ESTATISTICAS:
        if figuras.get(chave) is not None:
            elementos += [Spacer(1, 6), imagem_figura(figuras[chave], LARGURA_UTIL)]
    return elementos


def _ranking_areas_pdf(tabela, rotulo: str, titulo: str, est: dict, n: int = 10) -> list:
    elementos = [Paragraph(f"<b>{escape(titulo)}</b>", est["celula_cab"]), Spacer(1, 4)]
    if tabela.empty:
        return elementos + [Paragraph("Nenhum foco no período.", est["centro"]), Spacer(1, 8)]
    linhas = [["Pos", rotulo, "Focos", "Participação"]]
    linhas += [[f"{r['Posição']}º", Paragraph(escape(r[rotulo]), est["celula"]), fmt_inteiro(r["Focos de Calor"]),
                fmt_percentual(r["Participação (%)"], 2)] for _, r in tabela.head(n).iterrows()]
    return elementos + [tabela_pdf(linhas, [35, 340, 70, 90]), Spacer(1, 8)]


def tabelas_e_notas(diag, est: dict) -> list:
    ano = diag.ano_fim
    elementos = [Paragraph("Tabelas Comparativas e Nota Metodológica", est["secao"])]

    if isinstance(diag, DiagnosticoMunicipio):
        elementos += [Paragraph(f"<b>Top {len(diag.ranking_estado)} {ano} - Estado ({escape(diag.estado)})</b>",
                                est["celula_cab"]), Spacer(1, 4)]
        linhas = [["Pos", "Município", "Região", f"Focos ({ano})", "Acumulado"]]
        linhas += [[r["Posição"], r["Município"], Paragraph(escape(r["Região"]), est["celula"]),
                    fmt_inteiro(r[f"Focos ({ano})"]), fmt_inteiro(r["Acumulado"])]
                   for _, r in diag.ranking_estado.iterrows()]
        elementos += [tabela_pdf(linhas, [40, 180, 140, 80, 80]), Spacer(1, 10)]

        elementos += [Paragraph(f"<b>Ranking na {escape(diag.tipo_regiao)} ({escape(diag.regiao)})</b>",
                                est["celula_cab"]), Spacer(1, 4)]
        if diag.ranking_regiao.empty:
            elementos.append(Paragraph("Região do município não identificada.", est["centro"]))
        else:
            linhas = [["Pos", "Município", f"Focos ({ano})", "% Região"]]
            linhas += [[r["Posição"], r["Município"], fmt_inteiro(r[f"Focos ({ano})"]), r["% Região"]]
                       for _, r in diag.ranking_regiao.iterrows()]
            elementos.append(tabela_pdf(linhas, [40, 240, 120, 120]))
        elementos.append(Spacer(1, 10))

        if not diag.tabela_areas.empty:
            elementos += [Paragraph("<b>Unidades de Conservação e Terras Indígenas no Município</b>",
                                    est["celula_cab"]), Spacer(1, 4)]
            periodo = f"{diag.ano_inicio}–{diag.ano_fim}"
            linhas = [["Nº", "Tipo", "Nome", "Área no mun. (km²)", f"Focos {ano}", f"Focos {periodo}"]]
            for _, a in diag.tabela_areas.iterrows():
                area = a["Área no município (km²)"]
                linhas.append([a["Nº"], a["Tipo"], Paragraph(escape(a["Nome"]), est["celula"]),
                               fmt_inteiro(area) if area else "—", fmt_inteiro(a[f"Focos em {ano}"]),
                               fmt_inteiro(a[f"Focos {periodo}"])])
            elementos += [tabela_pdf(linhas, [25, 30, 250, 80, 70, 80]), Spacer(1, 12)]
        estado = diag.estado
    else:
        estado = diag.sigla_uf or "—"

    periodo = f"{diag.ano_inicio}–{diag.ano_fim}"
    for campo, rotulo in (("UC", TIPO_UC), ("TI", TIPO_TI)):
        elementos += _ranking_areas_pdf(diag.rankings_areas[f"{campo}_estado"], rotulo,
                                        f"{campo}s com mais focos no estado ({estado}), {periodo}", est)
        elementos += _ranking_areas_pdf(diag.rankings_areas[f"{campo}_brasil"], rotulo,
                                        f"{campo}s com mais focos no Brasil, {periodo}", est)

    nota_da_grade = nota_grade(grade_do_territorio(diag.poligono.bounds)) if diag.poligono is not None else ""
    elementos.append(Paragraph(
        "<b>Nota Metodológica Oficial:</b><br/>"
        "• <b>Fonte dos Dados:</b> BDQueimadas / INPE (Satélite de referência Aqua-Tarde, AQUA_M-T), atualizada "
        "com os arquivos diários e mensais do Programa Queimadas.<br/>"
        "• <b>Território:</b> município, UC e TI de cada foco pelo cruzamento do ponto do foco com os limites "
        "oficiais (IBGE, CNUC/MMA, FUNAI); em áreas protegidas sobrepostas, vale a de menor área.<br/>"
        f"• <b>Mapas:</b> densidade de kernel gaussiano (desvio de {fmt_numero(DESVIO_KERNEL_KM)} km); "
        f"{escape(nota_da_grade)}<br/>"
        "• <b>Rankings:</b> mais focos primeiro; empate decidido pelos focos no último mês e, depois, na última "
        "semana dos dados; persistindo o empate, mesma posição.<br/>"
        "• <b>Processamento:</b> Os dados foram processados por algoritmos desenvolvidos com apoio de "
        "Inteligência Artificial orientada por técnicos de Defesa Civil "
        f"({escape(APP_NOME)} v{APP_VERSAO} — {escape(DESENVOLVEDOR_NOME)}).<br/>"
        f"• <b>Canais de Atendimento:</b> {EMAIL_SALA_MONITORAMENTO} | Plantão Defesa Civil: {TELEFONE_PLANTAO}.",
        est["nota"]))
    return elementos


TITULOS_PDF = {TIPO_UC: "DIAGNÓSTICO DE UNIDADE DE CONSERVAÇÃO", TIPO_TI: "DIAGNÓSTICO DE TERRA INDÍGENA"}


def gerar_pdf(diag, figuras: dict, est: EstatisticasMunicipio | None = None, nowcast=None) -> bytes:
    """PDF completo do diagnóstico (município, UC ou TI); ``figuras`` = ``produto.figuras_territorio``."""
    buffer = io.BytesIO()
    nome = diag.nome
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM,
                            bottomMargin=45, title=f"{APP_NOME} — Diagnóstico {nome}", author=APP_NOME)
    estilos = estilos_pdf()
    titulo = "DIAGNÓSTICO MUNICIPAL" if isinstance(diag, DiagnosticoMunicipio) else TITULOS_PDF[diag.tipo]
    historia = cabecalho_pdf(f"{APP_NOME} — {titulo}", f"{diag.municipio} ({diag.ano_inicio} - {diag.ano_fim})",
                             estilos)
    historia += resumo_executivo(diag, estilos)
    if figuras.get("localizacao") is not None:
        historia += [imagem_figura(figuras["localizacao"], 470), Spacer(1, 8)]
    if nowcast is not None:
        historia += nowcast_pdf(nowcast, figuras, estilos)
    historia += graficos_pdf(figuras, estilos)
    historia += mapas_pdf(figuras, estilos)
    historia += anomalias_pdf(figuras, estilos)
    if est is not None:
        historia += estatisticas_pdf(est, figuras, estilos) + [PageBreak()]
    historia += tabelas_e_notas(diag, estilos)
    doc.build(historia, canvasmaker=CanvasNumerado)
    return buffer.getvalue()
