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

from core.cenario import MESES_EXTENSO, DIAS_SEMANA, CenarioAtual, recorrencia_do_mes, texto_do_cenario
from core.config import APP_NOME, APP_VERSAO, EMAIL_SALA_MONITORAMENTO, TELEFONE_PLANTAO
from core.estatisticas import EstatisticasMunicipio
from core.graficos import grafico_dias_areas_cenario, grafico_municipios_cenario, grafico_regioes_cenario
from core.graficos_estatisticas import (
    figuras_estatisticas, grafico_nowcast, grafico_nowcast_semanal, grafico_sazonalidade,
)
from core.mapas import MESES_NOME, mapa_anomalia, mapa_localizacao, mapa_recentes, mapa_recorrencia_mes
from core.anomalias import PERIODO_RELATORIO, TAMANHO_GRADE_ANOMALIA_ESTADO, calcular_anomalias
from core.grade import grade_do_territorio
from core.produto import fechar_figuras, figuras_anomalias, png
from core.territorios import caminho_do_estado, geometria_municipio, municipios_simplificados
from core.relatorio_pdf import (
    LARGURA_UTIL, MARGEM, CanvasNumerado, _tabela_indicadores, anomalias_pdf, cabecalho_pdf, estatisticas_pdf,
    estilos_pdf, imagem_figura, tabela_pdf,
)
from core.texto import fmt_inteiro, fmt_numero, fmt_percentual, nome_arquivo

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
    caminho_estado = caminho_do_estado(cen.sigla_uf)
    figuras = {
        "localizacao": mapa_localizacao(cen.sigla_uf, limite, cen.nome,
                                        municipios_simplificados(caminho_estado) if caminho_estado else ()),
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


def anomalias_do_cenario(cen: CenarioAtual, limite, focos_territorio):
    """Anomalias do mês no estado/região (grade fixa de 10 km, ``docs/07`` §12); None sem dados suficientes."""
    if focos_territorio is None or len(cen.nowcast.anos_comparados) < 3:
        return None
    limites = limites_do_cenario(cen, limite)
    return calcular_anomalias(focos_territorio, limites, cen.dia, PERIODO_RELATORIO, cen.nowcast.anos_comparados,
                              grade_do_territorio(limites, TAMANHO_GRADE_ANOMALIA_ESTADO))


def tabela_acima_no_mes(cen: CenarioAtual, acima, anos_recorde, estilos) -> list:
    """Municípios com mais focos no mês (até o dia) do que em qualquer ano anterior nas mesmas datas."""
    mes = MESES_EXTENSO[cen.dia.month - 1]
    elementos = [Paragraph(f"Municípios acima da máxima histórica em {mes} (1º a {cen.dia:%d/%m}, "
                           f"× {anos_recorde[0]}–{anos_recorde[1]})", estilos["secao"])]
    if acima.empty:
        return elementos + [Paragraph("Nenhum município ultrapassou a máxima histórica das mesmas datas.",
                                      estilos["centro"]), Spacer(1, 8)]
    linhas = [["Município", cen.tipo_regiao, "Focos no mês", "Máxima anterior", "Ano", "× máxima"]]
    linhas += [[r["Município"], Paragraph(escape(r["Região"]), estilos["celula"]), fmt_inteiro(r["Focos no mês"]),
                fmt_inteiro(r["Máxima anterior"]), "—" if r["Ano da máxima"] != r["Ano da máxima"] else
                str(int(r["Ano da máxima"])), "—" if r["Vezes a máxima"] != r["Vezes a máxima"] else
                fmt_numero(r["Vezes a máxima"], 1)] for _, r in acima.iterrows()]
    return elementos + [tabela_pdf(linhas, [130, 150, 70, 75, 45, 60]), Spacer(1, 8)]


def anomalias_do_municipio(cen: CenarioAtual, municipio: str, focos_territorio, caminho_estado):
    """(anomalias do mês, limite) de um município do estado/região, na grade proporcional dele; None sem dados."""
    if focos_territorio is None or caminho_estado is None or len(cen.nowcast.anos_comparados) < 3:
        return None
    poligono = geometria_municipio(caminho_estado, municipio)
    if poligono is None:
        return None
    focos = focos_territorio[focos_territorio["NM_MUN"] == municipio.upper()]
    return calcular_anomalias(focos, poligono.bounds, cen.dia, PERIODO_RELATORIO, cen.nowcast.anos_comparados), poligono


def sazonalidades_pdf(cen: CenarioAtual, figuras: dict, municipios: list[str], estilos) -> list:
    """Uma linha por município acima da máxima: sazonalidade (média mensal, p10–p90 e o ano atual) e, ao lado,
    o mapa da anomalia combinada do mês."""
    from reportlab.platypus import PageBreak, Table, TableStyle

    elementos = [PageBreak(), Paragraph(f"Sazonalidade e anomalia dos municípios acima da máxima histórica em "
                                        f"{MESES_EXTENSO[cen.dia.month - 1]}", estilos["secao"]),
                 Paragraph("À esquerda, média mensal dos anos do período (barras), faixa p10–p90 e o ano atual (linha), "
                           "como no diagnóstico do município; à direita, a anomalia combinada (quantidade e "
                           "localização) do mês no município, na grade proporcional dele — leitura na seção de "
                           "anomalias.", estilos["nota"]), Spacer(1, 4)]
    largura_mapa = 175
    linhas = []
    for m in municipios:
        mapa = figuras.get(f"anomalia_{m}")
        linhas.append([imagem_figura(figuras[f"sazonalidade_{m}"], LARGURA_UTIL - largura_mapa - 12),
                       imagem_figura(mapa, largura_mapa) if mapa is not None else ""])
    tabela = Table(linhas, colWidths=[LARGURA_UTIL - largura_mapa - 6, largura_mapa + 6])
    tabela.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.3, "#DDDDDD")]))
    return elementos + [tabela]


def pacote_cenario(cen: CenarioAtual, pdf: bytes, nome_pdf: str, pngs: dict, acima=None, geojson: dict | None = None
                   ) -> tuple[bytes, str]:
    """Pacote completo do cenário (.zip): PDF, imagens, tabelas (CSV), focos da semana (GeoJSON) e metadados."""
    import json
    import zipfile

    alvo = nome_arquivo(cen.nome)
    arquivos = {nome_pdf: pdf}
    for chave, imagem in pngs.items():
        arquivos[f"imagens/{nome_arquivo(chave)}.png"] = imagem
    tabelas = {"municipios_ultima_semana": cen.municipios, "areas_protegidas_ultima_semana": cen.areas,
               "focos_ultimas_24h": cen.focos_24h}
    if acima is not None:
        tabelas["municipios_acima_da_maxima_no_mes"] = acima
    for nome, tabela in tabelas.items():
        arquivos[f"tabelas/{nome}.csv"] = tabela.to_csv(index=False).encode("utf-8")
    if geojson is not None:
        arquivos[f"focos_ultima_semana_{alvo}.geojson"] = json.dumps(geojson, ensure_ascii=False).encode("utf-8")
    arquivos["metadados.json"] = json.dumps({
        "territorio": cen.nome, "estado": cen.estado, "passagem": cen.dia.isoformat(),
        "semana": [cen.inicio_semana.isoformat(), cen.dia.isoformat()], "focos_24h": len(cen.focos_24h),
        "focos_semana": len(cen.focos_semana), "gerado_por": f"{APP_NOME} v{APP_VERSAO}"},
        ensure_ascii=False, indent=2).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in arquivos.items():
            z.writestr(nome, conteudo)
    return buffer.getvalue(), f"Cenario_Completo_{alvo}_{cen.dia:%Y%m%d}.zip"


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
                            focos_territorio=None, agora: datetime | None = None, acima_no_mes=None,
                            anos_recorde: tuple[int, int] | None = None, sazonalidades: dict | None = None,
                            pngs: dict | None = None) -> tuple[bytes, str]:
    """(PDF, nome do arquivo) do cenário atual.

    ``est`` = estatísticas do período do Panorama (no fim); ``focos_territorio`` = todos os focos do estado/região
    (anomalias, docs/07 §12); ``acima_no_mes`` = municípios acima da máxima histórica no mês (``panorama``), com
    ``sazonalidades`` = município → ``EstatisticasMunicipio`` para o gráfico de sazonalidade de cada um; ``pngs``
    = dicionário que recebe o PNG de cada figura (pacote do cenário).
    """
    agora = agora or datetime.now()
    rec = recorrencia_do_mes(cen, limites_do_cenario(cen, limite)) if len(cen.focos_semana) or (
        cen.historico_mes is not None and len(cen.historico_mes)) else None
    figuras = figuras_cenario(cen, limite, rec)
    if est is not None:
        figuras.update({f"est_{k}": v for k, v in figuras_estatisticas(est).items()})
    figuras.update(figuras_anomalias(anomalias_do_cenario(cen, limite, focos_territorio), limite, cen.nome))
    caminho_estado = caminho_do_estado(cen.sigla_uf)
    for municipio, est_mun in (sazonalidades or {}).items():
        figuras[f"sazonalidade_{municipio}"] = grafico_sazonalidade(est_mun)
        an = anomalias_do_municipio(cen, municipio, focos_territorio, caminho_estado)
        if an is not None:
            figuras[f"anomalia_{municipio}"] = mapa_anomalia(an[0], "combinada", an[1], municipio,
                                                             compacto=True)
    if pngs is not None:
        pngs.update({chave: png(figura, dpi=150) for chave, figura in figuras.items() if figura is not None})
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
            Spacer(1, 4),
            Paragraph("Cenário atual", estilos["secao"]),
            *[Paragraph(escape(p), estilos["nota"]) for p in texto_do_cenario(cen, acima_no_mes, anos_recorde,
                                                                              no_relatorio=bool(sazonalidades))],
            Spacer(1, 6),
            imagem_figura(figuras["localizacao"], 470), Spacer(1, 6),
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
        historia += anomalias_pdf(figuras, estilos)
        if acima_no_mes is not None and anos_recorde:
            historia += tabela_acima_no_mes(cen, acima_no_mes, anos_recorde, estilos)
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
        if sazonalidades:
            historia += sazonalidades_pdf(cen, figuras, list(sazonalidades), estilos)
        if est is not None:
            historia += estatisticas_pdf(est, {k[4:]: v for k, v in figuras.items() if k.startswith("est_")}, estilos)
        doc.build(historia, canvasmaker=CanvasNumerado)
    finally:
        fechar_figuras(figuras)
    return buffer.getvalue(), f"Cenario_Focos_{nome_arquivo(cen.nome)}_{cen.dia:%Y%m%d}.pdf"
