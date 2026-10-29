# Documento Técnico 10 — Produtos

Identidade visual: logos em `referencia/logos/` (`AUTOSIMD-FOCOS.png`, `CBM-CEDEC.png`, `AutoSIMD-FOCOS.ico`).

## 1. Pacote .zip (`core/produto.py`)

Mesmo conteúdo para município, UC e TI (P7), montado em memória e baixado pelo navegador (automaticamente, se a opção estiver ligada, e pelo botão). `<alvo>` = nome sem acento (`SAO_FELIX_DO_XINGU`), `<p>` = `<ano_inicio>_<ano_fim>`.

| Arquivo | Município | UC / TI |
|---|---|---|
| Nome do pacote | `Diagnostico_MUN_<alvo>_<p>.zip` | `Diagnostico_UC_<alvo>_<p>.zip` / `Diagnostico_TI_…` |
| `relatorio_diagnostico_<alvo>_<p>.pdf` | ✔ (§4) | ✔ (§4) |
| `estatisticas_<alvo>_<p>.xlsx` | ✔ | ✔ (sem as abas do nowcast) |
| `grade_10x10km_<alvo>.geojson` (sempre) + `grade_<L>x<L>km_<alvo>.geojson` (proporcional, L = 5, 2.5 ou 1.25; P31, `docs/07` §4) | ✔ | ✔ |
| `dados_<MUN|UC|TI>_<alvo>.csv` | ✔ focos do município | ✔ focos da área |
| `ranking_municipios.csv`, `ranking_ucs.csv`, `ranking_tis.csv` | ✔ do estado no período | ✔ dentro da área |
| `metadados.json` | ✔ com UF, tipo de região, região, data do nowcast | ✔ com a UF predominante |
| `imagens/grafico_top5_estado_<alvo>.png` | ✔ | — |
| `imagens/grafico_evolucao_historica_…`, `grafico_sazonalidade_…` | ✔ | ✔ |
| `imagens/mapa_0_localizacao_<alvo>.png` | ✔ | ✔ |
| `imagens/mapa_5_anomalia_quantidade_…`, `mapa_6_anomalia_localizacao_…`, `mapa_7_anomalia_combinada_<alvo>.png` (≥ 3 anos de referência) | ✔ | ✔ |
| `imagens/mapa_1_densidade_ano_final_…`, `mapa_2_densidade_acumulada_…`, `mapa_3_recorrencia_…`, `mapa_4_sazonalidade_trimestral_<alvo>.png` | ✔ | ✔ |
| `imagens/estatisticas_comparativo_mensal_…`, `_semanal_…`, `_1o_semestre_…`, `_2o_semestre_…`, `estatisticas_acumulado_mensal_<alvo>.png` | ✔ (§5) | ✔ |
| `estatisticas/01_Focos_Mes_a_Mes.csv` … `07_Acumulado_Mensal.csv` | ✔ (§5) | ✔ |
| `imagens/cenario_atual_ultimos_30_dias_…`, `cenario_atual_mapa_focos_recentes_<alvo>.png` | ✔ (§6) | ✔ |
| `nowcast/Nowcast_Ultimos_30_Dias.csv`, `Nowcast_Focos_Recentes.csv`, `Nowcast_Indicadores.csv` | ✔ (§6) | ✔ |
| `risco_de_recorrencia/risco_1_baixo_<alvo>.kml`, `risco_2_moderado_…`, `risco_3_alto_…`, `risco_4_muito_alto_<alvo>.kml` e `risco_recorrencia_classes_<alvo>.geojson` | ✔ (`docs/07` §4) | ✔ |

Campos de cada arquivo em `docs/06` §4. PNGs a 180 dpi. Com a base completa (2002–2026), o pacote de São Félix do Xingu tem ~3,3 MB e o PDF 13 páginas.

## 2. Gráficos

| Gráfico | Conteúdo |
|---|---|
| Top 5 do estado (município) | Barras horizontais, acumulado do período; o município analisado em vermelho |
| Evolução anual | Linha dos focos por ano + reta de tendência (mínimos quadrados) |
| Sazonalidade mensal | **Média** de cada mês nos anos do período sem o de referência (barras com o valor), faixa **p10–p90** (barras de erro) e a **linha do ano de referência** (padrão: o ano final); os percentis seguem os parâmetros das estatísticas |

## 3. Mapas (`core/mapas.py`)

Os gráficos de sazonalidade mensal trazem no título o nome do território analisado (estado, região, município, UC ou TI).

Regras em `docs/07` §4–§6. Limite do território em azul `#1E88E5`; UC em verde `#2E7D32` (contínuo), TI em marrom `#8D4E00` (tracejado). Eixos em graus, com a proporção real da latitude.

- **Kernel (mapas 1, 2, 4):** escala de amarelo-claro a vinho, em focos por 100 km²; cada foco como pequena cruz cinza quase transparente (até 2.000 focos no mapa; acima disso não são desenhadas); nota com o desvio do kernel, o tamanho da célula e se os focos estão marcados.
- **Recorrência (mapa 3):** grade proporcional ao território (10, 5, 2,5 ou 1,25 km, `docs/07` §4) ajustada à latitude, tamanho no título, escala plasma, nota sobre o ajuste.
- **Cenário atual:** imagem de satélite **Sentinel-2 cloudless 2024** da EOX (licença CC BY-NC-SA 4.0, tiles XYZ, `core/fundo_satelite.py`; fonte em `core/config.py`, P22), limite em ciano, UC verde-limão e TI laranja; focos com contorno preto, cor pela idade (último dia `#FF1744`, 1–2 dias `#FF9100`, 3–6 dias `#FFEA00`, 7–29 dias `#E0E0E0`); crédito "Imagem: Sentinel-2 cloudless 2024 (s2maps.eu) por EOX IT Services GmbH, CC BY-NC-SA 4.0 — contém dados Copernicus Sentinel modificados (2024)". Sem internet: sem imagem, com aviso.

- **Localização (mapa 0):** dois painéis — Brasil com os estados (`referencia/limites_uf.geojson`), o estado do território em laranja `#FFB74D` e um retângulo vermelho no território; e o estado com os limites municipais em cinza, o território em vermelho `#D32F2F` e uma seta com o nome. Na tela do diagnóstico, no PDF do diagnóstico (logo após o resumo), no PDF do cenário (após os indicadores) e no pacote (`imagens/mapa_0_localizacao_<alvo>.png`).
- **Mapa interativo (só na tela — Panorama e abertura da página Diagnóstico, não dentro do diagnóstico; `core/mapa_interativo.py`):** pydeck/deck.gl (vem com o Streamlit, funciona offline; só a imagem precisa de internet). Mapa base Sentinel-2 cloudless como estilo MapLibre numa URL `data:`; quadrícula de recorrência do mês com escala YlOrRd e opacidade 110/255, sem contorno; limites municipais brancos finos, clicáveis; território em ciano; focos com a cor da idade. O deck.gl desenha numa tela separada, por cima do mapa base, e não multiplica as cores com o satélite: a transparência faz o papel do "multiplicar" pedido. O mapa do PDF não mudou.

- **Anomalias (mapas 5, 6 e 7, `mapa_anomalia`):** quantidade, localização e combinada (`docs/07` §12) na grade proporcional; 7 classes de vermelho-escuro (≤ −3, mais focos) a azul-escuro (≥ 3, menos focos), comum em branco; pontos preenchidos com a cor da própria célula e borda verde nas células significativas (pequeno, borda verde-clara `#81C784` = q < 5%; grande, borda verde-escura `#1B5E20` mais grossa = q < 1%; Benjamini–Hochberg); contorno vermelho `#C62828` / azul `#1565C0` com halo branco nos grupos de células a 1% a até 20 km; nota com o total do período, a média e a anomalia do território. Na tela (abas, no diagnóstico de município/UC/TI e no Panorama), nos PDFs do diagnóstico (seção "Anomalias de Focos de Calor", depois dos mapas) e do cenário (depois da recorrência do mês; grade de 10 km), com o texto de como ler e a metodologia; no pacote, `imagens/mapa_5_anomalia_quantidade_…`, `mapa_6_anomalia_localizacao_…`, `mapa_7_anomalia_combinada_<alvo>.png`. Sem 3 anos de referência no período, não são gerados.

## 4. PDF do diagnóstico (`core/relatorio_pdf.py`)

A4 retrato, Helvetica, cabeçalho com logos, faixa vermelha `#B71C1C`, rodapé "AutoSIMD-FOCOS | CBMPA … | Fonte: BDQueimadas/INPE — Página X de Y" (mesmo padrão do AutoSIMD-DESASTRE). Título: "DIAGNÓSTICO MUNICIPAL", "DIAGNÓSTICO DE UNIDADE DE CONSERVAÇÃO" ou "DIAGNÓSTICO DE TERRA INDÍGENA".

1. **Resumo executivo** (6 indicadores). Município: focos no ano final, posição no país e no estado, participação no estado, variação, densidade. UC/TI: focos no ano final, total e média anual do período, posição entre as UCs/TIs do estado e do Brasil, densidade.
2. **Cenário atual** (município, P18): indicadores do nowcast, gráfico dos últimos 30 dias, mapa dos últimos 7 dias sobre satélite.
3. **Gráficos:** top 5 + evolução (município) ou evolução (UC/TI); sazonalidade.
4. **Mapas** 1 a 4 (480 pt de largura).
5. **Estatísticas (modelo INPE, §5):** notas, tabela mês a mês com destaques, dia a dia (dias 1–16 e 17–31 + total), comparativos mensal, semanal, 1º e 2º semestre, acumulado mensal.
6. **Tabelas e notas:** "Top 5 <ano final> - Estado (<estado>)" e "Ranking na Região de Integração (<nome>)" — fora do Pará, "Ranking na Região Geográfica Imediata (<nome>)" — (município); UCs/TIs no município; 10 primeiras UCs e TIs no estado e no Brasil; nota metodológica (fonte, cruzamento com os polígonos, kernel, grade ajustada, desempate dos rankings, processamento com IA, versão, desenvolvedor, canais de atendimento).

## 5. Estatísticas de focos ativos (modelo Programa Queimadas/INPE) — município, UC e TI

Regras em `docs/07` §8. Os mesmos dados aparecem em 4 formas: tela (tabelas + gráficos Altair interativos), PDF, Excel/CSV e PNG. O PDF/pacote usa os parâmetros aplicados na tela ("Usar estes parâmetros no relatório"); sem isso, os padrões.

| Item | Tela | PDF / PNG |
|---|---|---|
| Mês a mês (ano × mês, mínimo, média, máximo) | Tabela com destaques | Tabela com destaques (amarelo `#FFD54F` = menor diferente de 0, vermelho `#E53935` = maior; zero não é destacado; linhas de resumo `#FBC02D`/`#FB8C00`/`#E53935`) |
| Dia a dia (mês escolhido, ano de referência e anterior) | Tabela | Tabela em duas partes |
| Comparativo mensal, semanal, 1º semestre, 2º semestre | Barras do ano de referência (azul) + linhas máximo (vermelho), média (laranja), mínimo (verde); dica, zoom horizontal, legenda clicável; tabela em "Ver tabela" | Mesmo gráfico (matplotlib) |
| Acumulado mensal | Linhas cinza de cada ano, faixa cinza dos percentis, média (laranja), ano de referência (azul), anterior (roxo), mais intenso (vermelho tracejado), menos intenso (verde tracejado) | Mesmo gráfico |

Parâmetros ajustáveis na tela: ano de referência, mês do dia a dia, faixa de percentis (também da sazonalidade), janela do mais/menos intenso, linhas dos comparativos e linhas de cada ano no acumulado.

## 6. Cenário atual (nowcast) — município, UC e TI (P23)

Regras em `docs/07` §9. Na tela: 5 indicadores (vermelho quando acima da média, verde quando abaixo), gráfico interativo dos últimos 30 dias (barras = ano corrente; linhas = máximo e média do mesmo dia e média ±3 dias nos anos anteriores), mapa dos focos dos últimos 1/3/7/15/30 dias sobre satélite e a lista dos focos. No PDF e no pacote (P18): os indicadores, o gráfico, o mapa dos últimos 7 dias, e as tabelas no Excel e em `nowcast/*.csv`.

## 7. Defeitos do v0.10 que esta versão corrige

| Defeito | Correção |
|---|---|
| Emojis nos títulos do PDF saíam como quadrados pretos (■) | Títulos só com texto |
| Posição arbitrária em empates | Desempate pelo último mês e pela última semana (P2) |
| Focos sem município contados como um município no ranking nacional | Fora do ranking (P3) |
| Fora do Pará, "Comparativo na Não Identificada" com o estado inteiro | Região Geográfica Imediata do IBGE (P4) |
| Grade de 0,09° nos dois eixos (células menores no Sul) | Grade de 10 × 10 km ajustada à latitude (P8) |
| Nome do GeoJSON da grade com `_` no lugar das letras acentuadas | Nome sem acento |
| Resultados sumiam ao clicar em baixar | Botões não recarregam a página |
| GeoJSON de UC (108 MB) relido a cada clique | Lido uma vez |
| UC/TI sem PDF nem Excel | Mesmo pacote do município (P7) |

## 8. PDF do cenário atual do estado (`core/relatorio_cenario.py`)

Botão **📄 Gerar relatório do cenário (PDF)** no Panorama do Estado; depois aparece **⬇️ Baixar** (some quando muda o estado, a região ou a base). Arquivo `Cenario_Focos_<Estado ou Região>_<AAAAMMDD da passagem>.pdf`, no padrão visual do PDF do diagnóstico (cabeçalho com logos, rodapé "Página X de Y"):

1. Indicadores (os mesmos 6 da tela) e nota com as definições (`docs/07` §11, texto justificado), data de geração e último dia buscado; mapa de localização (§3);
2. Mapa dos focos da última semana sobre o Sentinel-2 cloudless, cor pela idade, centralizado, com a legenda centralizada abaixo do mapa;
3. Focos por dia nos últimos 30 dias e **por semana no último trimestre** (13 semanas, faixas dos meses) × máximo e média da mesma semana nos anos anteriores;
4. **Gráficos dos focos analisados:** focos por dia na semana (fora de áreas protegidas / em UC / em TI, empilhados), focos da semana por região (só no estado inteiro, com a parte das 24 h) e os 15 municípios com mais focos na semana;
5. **Recorrência do mês × focos atuais:** grade proporcional (`docs/07` §4) com o nº de anos em que cada célula teve foco no mês da passagem (anos comparados do nowcast) e os focos da semana por cima; leitura com a % dos focos em células com histórico no mês e em células com foco em pelo menos metade dos anos;
6. Municípios com focos na semana (até 40), UCs e TIs com focos na semana (até 20) — a lista dos focos das 24 h saiu (P29: o GeoJSON a substitui);
7. Nota de fontes e canais de atendimento;
7a. **Cenário atual** (texto automático, logo depois dos indicadores) e **Municípios acima da máxima histórica no mês** (tabela: focos no mês, máxima anterior, ano, vezes a máxima), depois das anomalias;
7b. **Sazonalidade e anomalia dos municípios acima da máxima** — uma linha por município: o gráfico de sazonalidade (com o nome do município no título) e, ao lado, o mapa compacto da **anomalia combinada** do mês no município (grade proporcional dele, `mapa_anomalia(..., compacto=True)`); antes das estatísticas;
8. **Estatísticas de focos ativos** (modelo INPE, a mesma seção do PDF do diagnóstico, §5) do estado/região no período do filtro do Panorama, com os parâmetros padrão.

O botão **📄 Gerar relatório e pacote do cenário** gera o PDF e o **pacote completo** (`Cenario_Completo_<alvo>_<AAAAMMDD>.zip`, conteúdo em `docs/06`).

Ao lado do PDF, **🗺️ Focos de calor em GeoJSON** (P29): data inicial e final (padrão = a última semana), **Preparar GeoJSON** e **Baixar**: todos os focos do estado/região no intervalo, com os campos de `docs/06`. Acima de 200.000 focos a tela pede um intervalo menor.

No PDF do diagnóstico (§4), a seção do cenário atual também tem o gráfico de focos por semana no último trimestre (13 semanas, faixas dos meses), abaixo do de 30 dias (PNG `imagens/cenario_atual_ultimas_13_semanas_<alvo>.png` e aba `Nowcast_Ultimas_13_Semanas` no Excel). No Panorama (tela), esse gráfico, interativo, substituiu o de 30 dias. Em todos os PDFs, as notas são justificadas.
