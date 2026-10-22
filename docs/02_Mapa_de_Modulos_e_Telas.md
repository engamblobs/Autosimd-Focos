# Documento Técnico 02 — Mapa de Módulos e Telas

## Hierarquia principal (implementada em `app.py`)

Barra lateral: navegação, **🛰️ Base de focos (INPE)** (dados até que dia, se o dia é parcial, andamento da busca em segundo plano, próxima busca e o toggle "Nowcast"), parâmetros da análise (só na página Diagnóstico) e "Sobre o Sistema & Desenvolvedor".

O programa abre direto com a base local. A busca de focos novos no INPE roda em segundo plano (`docs/03` §5); o painel **🛰️ Base de focos (INPE)** da barra lateral mostra dados até que dia, o andamento da busca, a próxima busca e o toggle **Nowcast (busca a cada 4 h)**.

```text
🏠 Panorama do Estado          ← página inicial (docs/07 §10)
   ├── Filtros: estado (padrão Pará) · região (Integração no PA, Geográfica Imediata nos demais; "Todas") · período
   ├── 6 indicadores: focos no ano final até a data dos dados (× ano anterior), mesmo período do ano anterior,
   │   média do mesmo período, últimos 7 e 30 dias, municípios com focos
   ├── Mapa de kernel do ano final (estado ou região) · focos por ano (interativo) · sazonalidade
   ├── Focos por região (estado inteiro) · 15 municípios com mais focos
   └── 📊 Estatísticas no modelo INPE (as mesmas do diagnóstico)
🔥 Diagnóstico
   Barra lateral
   ├── Nível de análise: Estado / Município · Unidade de Conservação (UC) · Terra Indígena (TI)
   ├── Município: Estado (UF; padrão Pará) + Município (os que têm focos na base)
   │   UC/TI: área protegida (as que têm focos na base, rótulo "NOME (CÓDIGO)")
   ├── Intervalo de anos (padrão: todos os anos da base)
   ├── "Baixar automaticamente o pacote completo" (padrão: ligado)
   └── 🚀 Processar Diagnóstico Completo
   Município
   ├── Resumo executivo: 6 indicadores (docs/07 §2), cada um com explicação (help)
   ├── 🛰️ Cenário atual (nowcast diário, docs/07 §9) — seção que se atualiza sozinha
   │   ├── 5 indicadores (último dia, dia anterior, 7 dias, 30 dias, no ano) com a diferença para a média
   │   ├── Gráfico interativo dos últimos 30 dias × máximo e média do mesmo dia e média ±3 dias
   │   └── Mapa sobre satélite (Sentinel-2 cloudless) e lista dos focos dos últimos 1/3/7/15/30 dias, cor pela idade
   ├── Gráficos: top 5 do estado (acumulado), evolução anual com tendência, sazonalidade (média, p10–p90, ano)
   ├── Tabelas: "Top 5 <ano> - Estado" · comparativo na Região de Integração (PA) ou Geográfica Imediata
   ├── Mapas: 1 kernel do ano final (+ tabela de UCs/TIs no município), 2 kernel acumulado, 3 recorrência, 4 trimestral
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
- A seção de estatísticas é um `st.fragment`: mexer nos controles dela refaz só essa seção. O PDF e o pacote só mudam ao clicar em "Usar estes parâmetros no relatório" (refaz a página inteira, sem novo download automático).
- Os botões de download não recarregam a página (`on_click="ignore"`), então os resultados continuam na tela depois de baixar.
- A base de focos e as geometrias são lidas uma vez por execução do programa (cache em memória).
- Números no padrão brasileiro (`1.234`, `4,5%`).
