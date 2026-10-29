# Documento Técnico 08 — Roadmap e Incrementos

Cada incremento é um pedido separado ao Claude. Só avançar quando o anterior estiver testado.

## Reorganização (v0.10 → v0.11, mesmo comportamento)

| # | Incremento | Entrega verificável | Situação |
|---|---|---|---|
| 0 | Estrutura do projeto | Árvore de `docs/04`, `.gitignore`, `requirements.txt`, git, pytest rodando | ✔ 2026-10-21 |
| 1 | Referência e amostras | `referencia/municipios_pa.csv` (no lugar do dicionário em .py), logos, `amostras/bases` gerada por `ferramentas/gerar_amostras.py` | ✔ 2026-10-21 |
| 2 | Leitura das bases | `focos.py`, `territorios.py`, `regioes.py`; base ausente/incompleta com mensagem | ✔ 2026-10-21 |
| 3 | Cálculos | `diagnostico.py`; indicadores iguais ao v0.10 na base completa (`docs/01` §7) | ✔ 2026-10-21 |
| 4 | Grade, gráficos e mapas | `grade.py` (uma implementação no lugar de quatro), `graficos.py`, `mapas.py` | ✔ 2026-10-21 |
| 5 | PDF e pacote | `relatorio_pdf.py`, `produto.py`; mesmos arquivos do v0.10 no .zip | ✔ 2026-10-21 |
| 6 | Interface | `app.py` só com telas; página Bases de dados; testes com `AppTest` | ✔ 2026-10-21 |
| 7 | Empacotamento Windows | Pacote v0.11 (323 MB) montado e testado no Wine (diagnóstico com a base completa e subida do servidor) | ✔ 2026-10-21 (61 testes) |

## Novas funções

| # | Incremento | Entrega verificável | Situação |
|---|---|---|---|
| 9 | Base sempre atualizada + nowcast | Busca automática no INPE (diário; mensal quando falta mais do que o diário guarda), dias provisórios, conversão idêntica à base; seção "Cenário atual" no município; jan–21/out/2026 incorporados (`docs/03` §5, `docs/07` §9) | ✔ 2026-10-21 (99 testes) |
| 8 | Estatísticas do município no modelo INPE | Tabelas mês a mês e dia a dia, comparativos mensal/semanal/quinzenal, acumulado com p10–p90, média e anos mais/menos intensos; gráficos interativos com parâmetros; no PDF, no Excel, em CSV e PNG (`docs/07` §8, `docs/10` §5) | ✔ 2026-10-21 (78 testes) |

| 10 | Respostas P1–P20 e pedidos da rodada 4 | Desempate, Regiões Imediatas, rankings UC/TI no estado e no Brasil, UC/TI com PDF/Excel/estatísticas, grade ajustada, semestres, busca ao abrir, consolidação mensal, nowcast no PDF, janela de 7 dias, sazonalidade com média/p10/p90, mapas de kernel, satélite no cenário atual, título do ranking regional; base inteira conferida contra os polígonos | ✔ 2026-10-21 |

| 11 | Abertura rápida, nowcast em segundo plano, Panorama do Estado, KML de risco | Abre com a base local; thread de atualização (abertura + toggle Nowcast a cada 4 h, modelo HIDRO); página inicial com o estado e filtro por região; cruzes discretas; pasta `risco_de_recorrencia` com 4 KML dissolvidos por quartil | ✔ 2026-10-22 |
| 12 | Rodadas 4–5 respondidas e publicação | Kernel configurável, Sentinel-2 cloudless (licença aberta), nowcast em UC/TI, GeoJSON de risco; v0.11 publicada no GitHub com Release | ✔ 2026-10-22 |

| 13 | Cenário atual no Panorama do Estado | Últimas 24 h (última passagem) e última semana do estado ou da região, com mapa, gráfico, municípios, UCs/TIs e o PDF do cenário (`docs/07` §11, `docs/10` §8) | ✔ 2026-10-26 (134 testes) |
| 14 | Ajustes para a v0.12 | Atalho com a versão; legenda do acumulado com a janela do mais/menos intenso (nota abaixo do gráfico removida); zero sem destaque na tabela mês a mês; grade proporcional ao território (10/5/2,5/1,25 km); kernel em UC/TI pequena (APA Pedregulho) sem erro; comparativos semestrais em semanas; rodapé no modelo do HIDRO | ✔ 2026-10-28 (137 testes) |
| 15 | Rodada 6 respondida e PDF do cenário completo | Gráfico de 52 semanas (diagnóstico e cenário); PDF do cenário com gráficos dos focos, recorrência do mês × focos atuais e estatísticas no fim; GeoJSON dos focos por intervalo de datas (P29); grade de 10 km + proporcional no pacote (P31); notas justificadas e mapa centralizado | ✔ 2026-10-28 |
| 16 | Mapas interativos e de localização | Mapa interativo (zoom, quadrícula do mês, limites municipais, clique = diagnóstico) no Panorama, no cenário atual do diagnóstico (município, UC, TI) e na abertura do Diagnóstico; mapa de localização na tela e nos PDFs; protótipo dos mapas de desvio para aprovação (P32) | ✔ 2026-10-29 |
| 17 | Anomalias e ajustes da rodada 7 | Anomalias de quantidade, localização e combinada com significância (Benjamini–Hochberg) nos PDFs; semanas do último trimestre com faixas dos meses (Panorama no lugar do gráfico de 30 dias); recordes nas tabelas do Panorama; mapa interativo só na abertura do Diagnóstico; cabeçalho com versão e SIMD (também no DESASTRE, DESASTRE 2 e HIDRO) | ✔ 2026-10-29 |
| 18 | Rodada 8 | Grupos de células significativas contornados, pontos com a cor da célula e bordas verdes; grade de 10 km nas anomalias do cenário; anomalias na tela; recorde do ano de referência na tabela mês a mês; tabela com todos os municípios; municípios acima da máxima no mês, texto do cenário, sazonalidades e pacote completo do cenário | ✔ 2026-10-29 |

## Próximos incrementos (propostos — dependem de `docs/09`)

| # | Incremento | Depende de |
|---|---|---|
| 19 | (a definir com o usuário) | — |

## Modelo de pedido ao Claude

> Implemente o **incremento N** do `docs/08`. Siga o `CLAUDE.md`. Ao terminar, responda no formato padrão e atualize os documentos afetados.
