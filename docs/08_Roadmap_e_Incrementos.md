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
| 19 | Interface nova (v0.14) | Tema próprio (cores e fontes Fira, offline), Panorama e Diagnóstico em abas, boletim do cenário, legenda do mapa com as cores reais, relatório/GeoJSON/pacote no painel esquerdo, bloco "⋯" da base INPE no rodapé (abre na atualização e recolhe), sem círculo de significância dentro dos grupos | ✔ 2026-11-23 |

| 26 | Dashboard do Panorama e downloads em três botões (v0.15) | Panorama do Estado em painel único (§11 de `docs/10`); PDF resumido (4 mapas numa página) e completo (com o boletim da vulnerabilidade anexado); caixa de downloads no dashboard; boletim sem a tabela dos eventos | ✔ 2026-11-27 |
| 25 | Boletim da vulnerabilidade, título com caixas de seleção e painel recolhido refeito | PDF e pacote só da vulnerabilidade (P47, `docs/10` §9.1); PM2,5 pelo IQAR da CONAMA 491/2018 (P45); colunas Motivo e Perfil (P46); painel recolhido = coluna de botões-ícone; título do dashboard = caixas de seleção de estado e município; seção Prévia no README com capturas (`ferramentas/capturar_telas.py`) | ✔ 2026-11-27 |
| 24 | Calibração do protótipo de vulnerabilidade (P43–P46) | Distâncias e cones mantidos (P43, P44), PM2,5 pela CONAMA (P45), escala mantida com descrições novas (P46) | ✔ 2026-11-27 |
| 23 | Visualização dashboard (TV) do diagnóstico de município | Botão dashboard/legado; painel esquerdo recolhido só com ícones; layout do modelo do usuário (localização + título, sazonalidade, estatísticas interativas, comparativo; resumo, cartões de mapa com ⇄, vulnerabilidade, localidades); busca ao vivo automática em segundo plano com porcentagem sobre o mapa; logo no rodapé leva à página inicial | ✔ 2026-11-27 |
| 22 | Desempenho e leitura da vulnerabilidade | Diagnóstico em etapas por aba com cache na sessão (abas em ~6 s; antes, até ~60 s quando o servidor de satélite demorava), satélite desiste rápido; busca ao vivo em paralelo (8,7 s → 3 s), frente de fogo de 24 h como origem dos cones e ponto do vento, PM2,5 por célula de 0,1°; casinhas para as localidades, focos de calor no mapa, setas de vento agrupadas, cones dissolvidos por sobreposição + GeoJSON, camadas com liga/desliga e opacidade, dois cliques na tabela centralizam o mapa; botão "Baixar pontos de focos de calor" | ✔ 2026-11-25 |
| 21 | Vento, Sentinel-2 SWIR e vulnerabilidade (protótipo) | Chave Vento acima do Nowcast (Open-Meteo, 0,25° só onde houve foco na semana, estado em análise); camada Sentinel-2 SWIR do Painel do Fogo nos mapas interativos; aba "Vulnerabilidade (protótipo)" no diagnóstico de município: proximidade, eventos de fogo do Painel do Fogo com cones de fogo (elipse de Anderson) e fumaça, PM2,5 do CAMS, vulnerabilidade da localidade e risco | ✔ 2026-11-25 |
| 20 | Tabelas e localidades | Dois cliques no nome de um município em qualquer tabela abrem o diagnóstico; um clique na tabela "acima da máxima" troca a sazonalidade; localidades do IBGE 2022 e territórios quilombolas em Parquet (`ferramentas/importar_localidades.py`, `core/localidades.py`) | ✔ 2026-11-25 |

## Próximos incrementos (propostos — dependem de `docs/09`)

| # | Incremento | Depende de |
|---|---|---|
| 27 | Dashboard otimizado para televisões | leitura a distância, tudo numa tela sem rolagem, atualização automática (pedido de 27/11/2026, roadmap do README) |
| 28 | Dashboard de UC e TI | mesmo painel único do município |
| 29 | Interface para celular (modo mobile) | layout responsivo para uso em campo |
| 30 | Hospedagem do site | acesso pelo navegador sem instalar; decidir servidor e acesso |
| 31 | Publicação científica | método, validação e resultados |
| 32 | Integração com o MapBiomas Fogo via API | áreas queimadas ao lado dos focos; ver termos e chave da API |

## Modelo de pedido ao Claude

> Implemente o **incremento N** do `docs/08`. Siga o `CLAUDE.md`. Ao terminar, responda no formato padrão e atualize os documentos afetados.
