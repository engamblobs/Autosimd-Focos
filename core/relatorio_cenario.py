# -*- coding: utf-8 -*-
"""PDF do cenário atual do estado ou de uma região (Panorama do Estado, docs/10 §8).

Mesmo padrão visual do relatório do diagnóstico (cabeçalho com logos, faixa vermelha, rodapé
"Página X de Y"): indicadores das últimas 24 h e da última semana, mapa dos focos da semana sobre
imagem de satélite, focos por dia nos últimos 30 dias e por semana no último ano, gráficos dos focos
analisados (por dia e área protegida, por região, por município), a recorrência do mês × focos atuais,
municípios, áreas protegidas e, no fim, as estatísticas de focos ativos (modelo INPE) do período.
"""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from core.cenario import DIAS_SEMANA, CenarioAtual, recorrencia_do_mes
from core.config import APP_NOME, APP_VERSAO, EMAIL_SALA_MONITORAMENTO, TELEFONE_PLANTAO
from core.estatisticas import EstatisticasMunicipio
from core.graficos import grafico_dias_areas_cenario, grafico_municipios_cenario, grafico_regioes_cenario
from core.graficos_estatisticas import figuras_estatisticas, grafico_nowcast, grafico_nowcast_semanal
from core.mapas import MESES_NOME, mapa_recentes, mapa_recorrencia_mes
from core.produto import fechar_figuras
from core.relatorio_pdf import (
    LARGURA_UTIL, MARGEM, CanvasNumerado, _tabela_indicadores, cabecalho_pdf, estatisticas_pdf, estilos_pdf,
    imagem_figura, tabela_pdf,
)
from core.texto import fmt_inteiro, fmt_percentual, nome_arquivo

MAX_MUNICIPIOS = 40
MAX_AREAS = 20


def limites_do_cenario(cen: CenarioAtual, limite):
    if limite is not None:
        return limite.bounds
    pontos = cen.historico_mes if cen.historico_mes is not None and len(cen.historico_mes) else cen.focos_semana
    return (pontos["lon"].min(), pontos["lat"].min(), pontos["lon"].max(), pontos["lat"].max())


def figuras_cenario(cen: CenarioAtual, limite, rec=None) -> dict:
    """Mapa da semana (sobre satélite), focos por dia (30 dias) e por semana (52), gráficos dos focos da semana e
    o mapa da recorrência do mês × focos atuais (``rec``, de ``recorrencia_do_mes``)."""
    figuras = {
        "mapa": mapa_recentes(cen.nowcast.recentes(DIAS_SEMANA), limite, cen.nome, cen.dia, DIAS_SEMANA),
        "diario": grafico_nowcast(cen.nowcast),
        "semanal": grafico_nowcast_semanal(cen.nowcast),
        "dias_areas": grafico_dias_areas_cenario(cen.focos_semana, cen.inicio_semana, DIAS_SEMANA),
        "regioes": (grafico_regioes_cenario(cen.focos_semana, cen.dia, cen.tipo_regiao)
                    if cen.regiao is None and len(cen.focos_semana) else None),
        "municipios": grafico_municipios_cenario(cen.municipios) if len(cen.municipios) else None,
    }
    if rec is not None:
        figuras["recorrencia_mes"] = mapa_recorrencia_mes(rec, limite, cen.nome, cen.dia)
    return figuras


def texto_recorrencia(rec) -> str:
    """Leitura do cruzamento da recorrência do mês com os focos da semana."""
    mes = MESES_NOME[rec.mes - 1]
    if not len(rec.atuais):
        return f"Nenhum foco na última semana para cruzar com a recorrência de {mes}."
    if not rec.anos:
        return "Sem anos anteriores completos na base para calcular a recorrência do mês."
    return (f"{fmt_percentual(rec.em_celulas_com_historico)} dos {fmt_inteiro(len(rec.atuais))} focos da última "
            f"semana caíram em células com foco em {mes} em algum ano de {rec.anos[0]} a {rec.anos[-1]}, e "
            f"{fmt_percentual(rec.em_celulas_frequentes)} em células com foco em {mes} em pelo menos metade desses "
            f"{len(rec.anos)} anos. Células = nº de anos com pelo menos um foco no mês; pontos = focos da última "
            "semana. Focos fora das células coloridas ocorrem onde o fogo não é habitual nesse mês.")


def indicadores_cenario(cen: CenarioAtual) -> list[tuple[str, str]]:
    """(rótulo, valor) dos indicadores — os mesmos na tela e no PDF."""
    i = cen.nowcast.indicadores

    def com_media(valor, media):
        return fmt_inteiro(valor) + ("" if media != media else f" (média {fmt_inteiro(round(media))})")

    variacao = i["variacao_acumulado_pct"]
    return [
        (f"Últimas 24 h — passagem de {cen.dia:%d/%m/%Y}" + (" (parcial)" if cen.provisorio else ""),
         com_media(i["ultimo_dia"], i["media_ultimo_dia"])),
        (f"Última semana ({cen.inicio_semana:%d/%m} a {cen.dia:%d/%m})", com_media(i["ultimos_7"], i["media_7"])),
        ("Municípios com focos (24 h / semana)",
         f"{fmt_inteiro(cen.focos_24h['NM_MUN'].nunique())} / {fmt_inteiro(cen.focos_semana['NM_MUN'].nunique())}"),
        ("Focos em UCs / TIs na semana",
         f"{fmt_inteiro((cen.focos_semana['UC'] != 'NONE').sum())} / "
         f"{fmt_inteiro((cen.focos_semana['TI'] != 'NONE').sum())}"),
        (f"No ano até {cen.dia:%d/%m}", fmt_inteiro(i["acumulado_ano"])
         + ("" if variacao is None else f" ({fmt_percentual(variacao, sinal=True)} vs. média)")),
        ("Últimos 30 dias", com_media(i["ultimos_30"], i["media_30"])),
    ]


def gerar_relatorio_cenario(cen: CenarioAtual, limite, est: EstatisticasMunicipio | None = None,
                            agora: datetime | None = None) -> tuple[bytes, str]:
    """(PDF, nome do arquivo) do cenário atual; ``est`` = estatísticas do período do Panorama (no fim do PDF)."""
    agora = agora or datetime.now()
    rec = recorrencia_do_mes(cen, limites_do_cenario(cen, limite)) if len(cen.focos_semana) or (
        cen.historico_mes is not None and len(cen.historico_mes)) else None
    figuras = figuras_cenario(cen, limite, rec)
    if est is not None:
        figuras.update({f"est_{k}": v for k, v in figuras_estatisticas(est).items()})
    try:
        estilos = estilos_pdf()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM,
                                bottomMargin=45, title=f"{APP_NOME} — Cenário atual {cen.nome}", author=APP_NOME)
        historia = cabecalho_pdf(f"{APP_NOME} — CENÁRIO ATUAL DE FOCOS DE CALOR",
                                 f"{cen.nome.upper()} — {cen.dia:%d/%m/%Y}", estilos)
        historia += [
            Paragraph("Indicadores — últimas 24 horas e última semana", estilos["secao"]),
            _tabela_indicadores(indicadores_cenario(cen), estilos), Spacer(1, 6),
            Paragraph(escape(
                f"Últimas 24 h = passagem mais recente do satélite de referência processada pelo INPE "
                f"({cen.dia:%d/%m/%Y}); última semana = {cen.inicio_semana:%d/%m} a {cen.dia:%d/%m}. Médias = mesmo "
                "dia (e soma da semana) nos anos anteriores que a base cobre por inteiro. Gerado em "
                f"{agora:%d/%m/%Y %H:%M}; base buscada no INPE até {cen.ultimo_dia_base:%d/%m/%Y}."), estilos["nota"]),
            Spacer(1, 6),
            imagem_figura(figuras["mapa"], 440), Spacer(1, 4),
            imagem_figura(figuras["diario"], LARGURA_UTIL), Spacer(1, 4),
        ]
        if figuras["semanal"] is not None:
            historia += [imagem_figura(figuras["semanal"], LARGURA_UTIL), Spacer(1, 8)]
        historia.append(Paragraph(f"Gráficos dos focos analisados — {escape(cen.nome)}", estilos["secao"]))
        for chave in ("dias_areas", "regioes", "municipios"):
            if figuras[chave] is not None:
                historia += [imagem_figura(figuras[chave], LARGURA_UTIL), Spacer(1, 6)]
        if rec is not None:
            historia += [KeepTogether([          # título, mapa e leitura na mesma página
                Paragraph(f"Recorrência de {MESES_NOME[rec.mes - 1]} × focos atuais", estilos["secao"]),
                imagem_figura(figuras["recorrencia_mes"], 440), Spacer(1, 4),
                Paragraph(escape(texto_recorrencia(rec)), estilos["nota"])]), Spacer(1, 8)]
        historia.append(Paragraph(f"Municípios com focos na última semana — {escape(cen.nome)}", estilos["secao"]))
        if cen.municipios.empty:
            historia.append(Paragraph("Nenhum foco na última semana.", estilos["centro"]))
        else:
            linhas = [["Município", cen.tipo_regiao, "Últimas 24 h", "Última semana"]]
            linhas += [[r["Município"], Paragraph(escape(r["Região"]), estilos["celula"]),
                        fmt_inteiro(r["Últimas 24 h"]), fmt_inteiro(r["Última semana"])]
                       for _, r in cen.municipios.head(MAX_MUNICIPIOS).iterrows()]
            historia.append(tabela_pdf(linhas, [170, 175, 90, 100]))
            if len(cen.municipios) > MAX_MUNICIPIOS:
                historia.append(Paragraph(f"… e mais {len(cen.municipios) - MAX_MUNICIPIOS} municípios "
                                          "(lista completa na tela).", estilos["nota"]))

        historia += [Spacer(1, 8), Paragraph("Unidades de Conservação e Terras Indígenas com focos na última semana",
                                             estilos["secao"])]
        if cen.areas.empty:
            historia.append(Paragraph("Nenhum foco em área protegida na última semana.", estilos["centro"]))
        else:
            linhas = [["Tipo", "Área protegida", "Últimas 24 h", "Última semana"]]
            linhas += [[r["Tipo"], Paragraph(escape(r["Área protegida"]), estilos["celula"]),
                        fmt_inteiro(r["Últimas 24 h"]), fmt_inteiro(r["Última semana"])]
                       for _, r in cen.areas.head(MAX_AREAS).iterrows()]
            historia.append(tabela_pdf(linhas, [35, 320, 80, 100]))

        historia += [Spacer(1, 10), Paragraph(
            "<b>Nota:</b> focos do satélite de referência (AQUA_M-T, BDQueimadas/INPE); município, UC e TI de cada "
            "foco pelo cruzamento com os limites oficiais (IBGE, CNUC/MMA, FUNAI). Imagem de fundo: Sentinel-2 "
            "cloudless 2024 (EOX, CC BY-NC-SA 4.0). Processamento com apoio de Inteligência Artificial orientada por "
            f"técnicos de Defesa Civil ({escape(APP_NOME)} v{APP_VERSAO}). Canais de atendimento: "
            f"{EMAIL_SALA_MONITORAMENTO} | Plantão Defesa Civil: {TELEFONE_PLANTAO}.", estilos["nota"])]
        if est is not None:
            historia += estatisticas_pdf(est, {k[4:]: v for k, v in figuras.items() if k.startswith("est_")}, estilos)
        doc.build(historia, canvasmaker=CanvasNumerado)
    finally:
        fechar_figuras(figuras)
    return buffer.getvalue(), f"Cenario_Focos_{nome_arquivo(cen.nome)}_{cen.dia:%Y%m%d}.pdf"
