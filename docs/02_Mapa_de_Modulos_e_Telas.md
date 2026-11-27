# Documento Técnico 02 — Mapa de Módulos e Telas

## Hierarquia principal (implementada em `app.py`)

Barra lateral (v0.15: botão 📺 dashboard / 📄 legado no Panorama e no Diagnóstico; no dashboard o painel recolhe para uma coluna de ícones — `docs/10` §10 e §11; downloads do diagnóstico em três botões — resumido, completo e pacote). Até a v0.14: navegação; parâmetros da análise (Diagnóstico) ou, no Panorama, **Relatório do cenário (PDF)** e **Focos de calor em GeoJSON**; no Diagnóstico processado, o **Pacote completo**; e, preso no rodapé, o bloco **"⋯ Base de focos (INPE) e sobre o sistema"** — recolhido; abre sozinho quando a base está sendo atualizada ("⏳ Atualizando…"), mostra "✅ Base de focos atualizada" e recolhe 5 s depois.

Panorama em abas: Cenário atual (mapa, boletim, indicadores, semana, municípios/UCs/focos) · Municípios acima da máxima · Anomalias do mês · Ano de <ano> · Estatísticas (modelo INPE). Diagnóstico em abas: Resumo (com localização) · Cenário atual · Gráficos e rankings · Mapas · Anomalias · Áreas protegidas · Estatísticas (modelo INPE) · Metodologia.

O programa abre direto com a base local. A busca de focos novos no INPE roda em segundo plano (`docs/03` §5); o painel **🛰️ Base de focos (INPE)** da barra lateral mostra dados até que dia, o andamento da busca, a próxima busca e o toggle **Nowcast (busca a cada 4 h)**.

```text
🏠 Panorama do Estado          ← página inicial (docs/07 §10)
   ├── Filtros: estado (padrão Pará) · região (Integração no PA, Geográfica Imediata nos demais; "Todas") · período
   ├── 🛰️ Cenário atual — últimas 24 h e última semana (docs/07 §11; independe do período)
   │   ├── 6 indicadores: últimas 24 h e semana (com a média), municípios com focos, focos em UCs/TIs,
   │   │   no ano até o dia, últimos 30 dias
   │   ├── 🗺️ Mapa interativo (docs/10 §3): focos da semana, quadrícula de recorrência do mês, limites
   │   │   municipais — clique num município = abre o diagnóstico dele · gráfico interativo de focos por semana no
   │   │   último trimestre (13 semanas, faixas dos meses)
   │   ├── Abas: Municípios · UCs e TIs · Focos do dia da passagem
   │   ├── 📄 Gerar relatório do cenário (PDF) → ⬇️ Baixar (docs/10 §8; estatísticas do período no fim)
   │   └── 🗺️ Focos em GeoJSON: data inicial e final → ⬇️ Baixar pontos de focos de calor → ⬇️ Baixar (P29)
   ├── 6 indicadores: focos no ano final até a data dos dados (× ano anterior), mesmo período do ano anterior,
   │   média do mesmo período, últimos 7 e 30 dias, municípios com focos
   ├── Mapa de kernel do ano final (estado ou região) · focos por ano (interativo) · sazonalidade
   │   ├── 📝 Cenário atual: texto automático (passagem, semana, ano, municípios acima da máxima, UCs/TIs)
   │   ├── 🔺 Municípios acima da máxima histórica no mês (tabela + sazonalidade do escolhido)
   │   ├── 🌡️ Anomalias do mês (abas Quantidade · Localização · Combinada; grade de 10 km)
   │   └── 📄 Gerar relatório e pacote do cenário → ⬇️ PDF · 📦 pacote completo (.zip)
   ├── Focos por região (estado inteiro) · 15 municípios com mais focos (expansor com todos) — células acima da máxima histórica
   │   das mesmas datas em vermelho (ano até a data, último mês, última semana; docs/07 §10)
   └── 📊 Estatísticas no modelo INPE (as mesmas do diagnóstico)
🔥 Diagnóstico
   Barra lateral
   ├── Nível de análise: Estado / Município · Unidade de Conservação (UC) · Terra Indígena (TI)
   ├── Município: Estado (UF; padrão Pará) + Município (os que têm focos na base)
   │   UC/TI: área protegida (as que têm focos na base, rótulo "NOME (CÓDIGO)")
   ├── Intervalo de anos (padrão: todos os anos da base)
   ├── "Baixar automaticamente o pacote completo" (padrão: ligado)
   └── 🚀 Processar Diagnóstico Completo
   Antes de processar: 🗺️ mapa interativo do estado escolhido (padrão Pará) — clique num município = diagnóstico
   Município
   ├── Resumo executivo: 6 indicadores (docs/07 §2), cada um com explicação (help)
   ├── 🧭 Localização: Brasil com o estado destacado e o estado com o território apontado (docs/10 §3)
   ├── 🛰️ Cenário atual (nowcast diário, docs/07 §9) — seção que se atualiza sozinha
   │   ├── 5 indicadores (último dia, dia anterior, 7 dias, 30 dias, no ano) com a diferença para a média
   │   ├── Gráfico interativo dos últimos 30 dias × máximo e média do mesmo dia e média ±3 dias
   │   └── Mapa sobre satélite e lista dos focos dos últimos 1/3/7/15/30 dias (o mapa interativo fica só na
   │       abertura da página Diagnóstico)
   ├── Gráficos: top 5 do estado (acumulado), evolução anual com tendência, sazonalidade (média, p10–p90, ano)
   ├── Tabelas: "Top 5 <ano> - Estado" · comparativo na Região de Integração (PA) ou Geográfica Imediata
   ├── Mapas: 1 kernel do ano final (+ tabela de UCs/TIs no município), 2 kernel acumulado, 3 recorrência, 4 trimestral
   ├── 🌡️ Anomalias (mapas 5–7 em abas, as mesmas do PDF)
   ├── Rankings de UCs e TIs no estado e no Brasil (4 abas)
   ├── 📊 Estatísticas de focos ativos no município (modelo INPE, docs/07 §8) — seção que se atualiza sozinha
   │   ├── Controles: ano de referência, mês do dia a dia, faixa de percentis, janela do mais/menos intenso,
   │   │   linhas dos comparativos, uma linha por ano no acumulado
   │   ├── Abas: Mês a mês · Dia a dia · Comparativo mensal · semanal · 1º semestre · 2º semestre · Acumulado
   │   │   (tabelas com destaque do INPE; gráficos interativos Altair: dica, zoom, legenda clicável)
   │   └── "Usar estes parâmetros no relatório (PDF e pacote)" quando os controles mudam
   ├── Síntese espacial e nota metodológica
   └── Central de exportação: download automático (opcional) + botão do pacote .zip
   UC / TI
   ├── Resumo: focos no ano final, total e média anual, posição entre as do estado e do Brasil, densidade
   ├── Gráficos: evolução anual, sazonalidade mensal
   ├── Mapas 1 a 4 (sem sobreposição de áreas protegidas)
   ├── Rankings de UCs e TIs no estado e no Brasil
   ├── 📊 Estatísticas no modelo INPE (as mesmas do município)
   └── Central de exportação: download automático (opcional) + botão do pacote .zip (com PDF e Excel)
🗂️ Bases de dados
   ├── Situação dos 4 arquivos (existe, tamanho, data de modificação)
   ├── Conteúdo da base de focos: total, anos, foco mais recente, estados com limites, focos por ano
   ├── Atualização automática: dias provisórios e histórico das buscas no INPE
   └── Como atualizar as bases
```

## Padrões de tela

- Os resultados aparecem ao clicar em **Processar** e continuam na tela até mudar o território ou o período na barra lateral (o diagnóstico fica em memória e não é recalculado a cada clique).
- **Visualização dashboard** (pedido de 27/11/2026, modelo `REFERENCIA PARA MODO DASHBOARD.jpg`): botão **📺 Visualização dashboard / 📄 Visualização legado** no alto do painel esquerdo da página Diagnóstico; vale só para o diagnóstico de **município** (UC/TI e as outras páginas continuam como antes). Detalhes em `docs/10` §10.
  - Painel esquerdo **recolhido** (84 px, só ícones: ☰, navegação, 📄/📺, 🚀 processar, ⬇️ pacote, ⋯); **☰** abre o painel inteiro e **« Recolher o painel** volta. Os botões funcionam recolhidos.
- **Rodapé** (todas as páginas): logo do AutoSIMD-FOCOS; clicar nele leva à página inicial (Panorama) sem recarregar.
- **Vulnerabilidade:** os dados ao vivo são buscados sozinhos, em segundo plano, quando a página carrega; a porcentagem aparece no canto do mapa e some ao terminar (o mapa se atualiza). O botão passou a ser "🔄 Buscar de novo agora".
- **Diagnóstico em etapas** (pedido de 25/11/2026): as abas aparecem logo e cada uma gera só as suas figuras, na ordem das abas (Resumo → Cenário → Gráficos → Mapas → Anomalias → … → Vulnerabilidade); o que já ficou pronto aparece enquanto o resto é gerado, e o pacote PDF/.zip é montado por último. Figuras, imagens e pacote ficam guardados na sessão: mexer em qualquer controle da página não refaz nada (só trocar território, período, base ou parâmetros do relatório). O mapa sobre o satélite desiste em até 8 s se o servidor de imagens não responder e, por 5 min, sai sem imagem sem esperar a rede de novo.
- A seção de estatísticas é um `st.fragment`: mexer nos controles dela refaz só essa seção. O PDF e o pacote só mudam ao clicar em "Usar estes parâmetros no relatório" (refaz a página inteira, sem novo download automático).
- **Diagnóstico de município → aba "Vulnerabilidade (protótipo)"** (P42, `docs/10` §9): localidades do IBGE do município pelo risco de fogo e fumaça; botão para buscar eventos do Painel do Fogo, vento e PM2,5 (internet).
- **Painel ⋯ (rodapé da barra lateral):** chave **Vento (Open-Meteo)** logo acima da chave **Nowcast** (P40); mapas interativos com a chave **Sentinel-2 em realce de fogo (SWIR — Painel do Fogo)** (P41).
- **Dois cliques no nome de um município** em qualquer tabela com a coluna "Município" (rankings do diagnóstico, municípios do cenário, focos do dia, acima da máxima, ranking do Panorama) abrem o diagnóstico dele, como o clique no mapa. Na tabela dos municípios acima da máxima, **um clique** num município troca o gráfico de sazonalidade abaixo (a lista de escolha continua). Sem legenda na tela (pedido de 25/11/2026). Implementação: `tabela(df, chave=, estado=)` em `app.py`; um componente (`st.components.v2`) escuta o duplo clique e lê o texto da célula selecionada.
- Os botões de download não recarregam a página (`on_click="ignore"`), então os resultados continuam na tela depois de baixar.
- A base de focos e as geometrias são lidas uma vez por execução do programa (cache em memória).
- Números no padrão brasileiro (`1.234`, `4,5%`).
