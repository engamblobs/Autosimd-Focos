# Documento Técnico 07 — Regras de Negócio

## 1. Território e período — metodologia única (P3, P13)

- **Período:** anos `ano_inicio` a `ano_fim`, inclusive. "Ano final" = `ano_fim`.
- **De que território é cada foco:** pelo **cruzamento do ponto do foco com o polígono** oficial — município (IBGE), UC (CNUC/MMA), TI (FUNAI). Vale para tudo: indicadores, rankings, estatísticas e nowcast.
  - Na divisa entre municípios (ponto nos dois limites), vence o primeiro na ordem dos arquivos `NM_UF_*.geojson`; fora de todos = `NONE` (159 focos, no mar ou fora do país).
  - UCs/TIs sobrepostas: vence a de menor área; mesma área (ex.: APA Miracema e RVS da Ventania, RJ, com o mesmo limite), a que vem depois no arquivo.
- **Como o programa aplica:** o cruzamento é feito **uma vez**, quando o foco entra na base (`core/atualizacao.py`), e gravado nas colunas `NM_MUN`, `NM_UF`, `SIGLA_UF`, `UC` e `TI`. O diagnóstico filtra por essas colunas (rápido). `ferramentas/verificar_base.py` refaz o cruzamento da base inteira e compara: em 21/10/2026, **5.293.068 focos, nenhuma diferença** (≈7 min). Os testes conferem o mesmo na amostra.
- **Município:** focos com `NM_MUN` = município **e** UF = estado escolhido (homônimos de outros estados não entram). Escopo estadual = focos do estado no período, sem os de município vazio.

## 2. Indicadores do município (`diagnostico.diagnosticar_municipio`)

| Indicador | Regra |
|---|---|
| Focos no ano final | Focos do município em `ano_fim` |
| Posição no país | Entre todos os pares (UF, município) com focos em `ano_fim` na base inteira — homônimos contados separadamente; focos sem município/UF fora (P3) |
| Posição no estado | Entre os municípios do estado com focos em `ano_fim` |
| Participação no estado | Focos do município em `ano_fim` ÷ focos do estado em `ano_fim` × 100 |
| Variação anual | (`ano_fim` − `ano_fim`−1) ÷ `ano_fim`−1 × 100. "—" quando `ano_fim`−1 está fora do período ou teve zero focos |
| Densidade média anual | (focos do município no período ÷ nº de anos do período) ÷ área geodésica do limite (km²). "—" sem limite |

Município sem focos no ano final: posição "Sem focos".

## 3. Rankings

- Ordem (`diagnostico.ranking`, todos os rankings): mais focos primeiro; **empate**: mais focos no **último mês** dos dados (do dia 1 ao último dia com dados até 31/12 do ano final) e, se ainda empatar, na **última semana** (os 7 dias até esse dia) (P2). Empate nos três = mesma posição (1º, 2º, 2º, 4º); na listagem, ordem alfabética. Ex. real (PA 2024): Mojuí dos Campos e Senador José Porfírio com 401 focos; Mojuí fica na frente com 53 × 36 em dezembro.
- "Top 5 <ano final> - Estado" (tabela): 5 primeiros em `ano_fim`, com o acumulado do período. Gráfico "Top 5": 5 primeiros no **acumulado do período** (P9).
- Comparativo regional: municípios da mesma região com focos em `ano_fim`, posição refeita dentro da região, % de cada um no total da região. Pará: **Região de Integração**; demais estados: **Região Geográfica Imediata** do IBGE (2017), `referencia/municipios_br.csv` (P4).
- UCs e TIs: rankings no **estado** (no município, o estado dele; na UC/TI, a UF com mais focos da área) e no **Brasil**, no período, com participação no total de focos em áreas do mesmo tipo (P6).

## 4. Grade proporcional ao território e densidade de kernel

**Tamanho da célula — proporcional ao território (pedido de 28/10/2026):** célula = 10 km ÷ 1, 2, 4 ou 8 (**10, 5, 2,5 ou 1,25 km**), a que deixa o **lado maior** do retângulo envolvente do território com o número de células mais próximo (em escala logarítmica) de **51** — o de São Félix do Xingu-PA (511 km) com 10 km, resultado considerado ideal (`GRADE_CELULAS_LADO_MAIOR`, `GRADE_DIVISORES` em `core/config.py`). Territórios maiores que a referência ficam em 10 km; o mínimo é 1,25 km (pouco acima do pixel de ~1 km do MODIS). Exemplos no Pará: São Félix do Xingu e Altamira 10 km; Marabá e Paragominas 5 km; Bragança, Belém, Maracanã, Curuçá, Marituba 1,25 km (Maracanã: 23 × 43 células; com 10 km eram 5 × 8). Vale para o mapa 3, o GeoJSON do QGIS e o risco de recorrência (mesma grade nos três). Como a recorrência depende do tamanho da célula, ela só é comparável entre territórios com a mesma célula.

**Grade (`core/grade.py`) — ajustada à latitude (P8):** célula de lado L km de verdade (L = tamanho acima): L/110,574° de latitude × L/(111,32 · cos φ)° de longitude, com φ = latitude central do território (com 10 km: 0,091° no Pará, 0,104° no RS). Propósito: no v0.10 a célula tinha 0,09° nos dois eixos, o que dava ~10 × 10 km no Equador mas ~8,7 × 10 km no Sul; com o ajuste, toda célula tem L² km² em qualquer latitude. A observação aparece no mapa 3, no PDF, na tela e no GeoJSON (`descricao`). Começa uma célula a sudoeste do retângulo envolvente do território.
- **Recorrência:** nº de anos do período em que a célula teve ao menos um foco (mapa 3 e GeoJSON).
- GeoJSON do QGIS: só as células com foco; limites do território (sem limite: extensão dos focos).

**Densidade de kernel (`core/kernel.py`, mapas 1, 2 e 4):** kernel gaussiano com desvio padrão de **5 km** (P21) sobre raster de ~1 km (maior em territórios muito grandes, até 500 células por lado), em focos por 100 km², recortado pelo limite do território; células abaixo de 2% do máximo ficam transparentes. Cada foco aparece por cima como uma pequena cruz preta. Só numpy (convolução separável), sem scipy.
- **Cruzes dos focos:** pequenas (+), cinza e quase transparentes, só para marcar a posição; com mais de 2.000 focos no mapa não são desenhadas (viram um borrão que esconde o kernel) e a nota do mapa avisa.
- **Risco de recorrência (KML):** as células da grade com pelo menos um foco no período são divididas pelos **quartis** da recorrência (Q1, Q2, Q3 dos anos com fogo dessas células): **baixo** ≤ Q1 < **moderado** ≤ Q2 < **alto** ≤ Q3 < **muito alto**. As células de cada classe são **dissolvidas** num só polígono (`grade.risco_de_recorrencia`). Com poucos valores distintos (ex.: período de 2 anos) quartis iguais deixam classes vazias; o arquivo da classe sai assim mesmo, dizendo que está vazio.
- **Trimestral:** um kernel por trimestre (Jan–Mar, Abr–Jun, Jul–Set, Out–Dez) com os focos do período inteiro.

## 5. Mapas

| Mapa | Conteúdo |
|---|---|
| 1. Densidade no ano final | Kernel dos focos do ano final + cruzes; no município, UCs/TIs sobrepostas, numeradas, com legenda e área no município |
| 2. Densidade acumulada | Kernel dos focos do período + cruzes |
| 3. Recorrência | Grade ajustada com os anos de reincidência (escala plasma) e a observação da grade |
| 4. Trimestral | 4 painéis de kernel + cruzes; não é gerado sem focos |
| Cenário atual | Focos dos últimos N dias sobre imagem de satélite (Sentinel-2 cloudless, EOX), em Web Mercator; cor pela idade (§9) |

Todos os mapas em graus com a proporção real da latitude (1/cos φ); o do cenário atual em Web Mercator, com os eixos em graus.

## 6. Áreas protegidas no município (`territorios.areas_protegidas_no_territorio`)

- Interseção do polígono da UC/TI com o do município.
- Descarta "lascas" de borda: interseção < 2% da área protegida **e** < 1% do município.
- Ordem: TIs e depois UCs, cada grupo da maior para a menor interseção; número sequencial no mapa.
- Colunas da tabela: área no município (km², geodésica), % da área protegida que está no município, focos no ano final e no período — contados por **ponto dentro da interseção** (não pela coluna `UC`/`TI` da base).

## 7. Nomes

- Município: comparação sem acento e sem diferença de maiúsculas (`São Félix do Xingu` = `SÃO FÉLIX DO XINGU` = `sao felix do xingu`).
- UC/TI: rótulo exato `NOME (CÓDIGO)` em maiúsculas.
- Nomes de arquivo: ASCII, `_` no lugar de espaços e pontuação (`SAO_FELIX_DO_XINGU`).

## 8. Estatísticas de focos ativos (modelo Programa Queimadas/INPE) — município, UC e TI

Implementação: `core/estatisticas.py` (`estatisticas_territorio`). Modelo: https://data.inpe.br/queimadas/estatisticas/?tipo=estados&item=para, aplicado ao território (P14).

| Regra | Definição |
|---|---|
| Focos | Os do território no período, pelo cruzamento com o polígono (§1) |
| Cobertura | Da 1ª à última data da base, dentro do período (hoje 04/07/2002 até o último dia buscado). Mês, semana ou dia fora da cobertura = vazio ("-"), nunca zero |
| Ano de referência | Padrão = ano final; ajustável na tela. É o ano das barras e das linhas destacadas |
| Mínimo, média, máximo | Por coluna, com todos os anos do **período da análise** (P15) **menos o de referência**, ignorando vazios |
| Destaque da tabela mês a mês | Menor valor de cada coluna em amarelo e maior em vermelho, entre os mesmos anos do mínimo/máximo (o ano de referência não é destacado); empate = todos destacados. **Zero nunca é destacado**: o amarelo vai para o menor valor diferente de 0, e a coluna só com zeros fica sem destaque (vale também para o dia a dia) |
| Dia a dia | Um mês (padrão: o último com dados no ano de referência), ano de referência e o anterior, dias 1–31 e total |
| Comparativos (P12) | **Mensal**; **semanal** (blocos de 7 dias a partir de 1º de janeiro, 53 semanas, a última curta); **1º semestre** (01/01 a 30/06) e **2º semestre** (01/07 a 31/12) **em semanas**: blocos de 7 dias a partir do 1º dia do semestre, a última mais curta como a 53ª do semanal — 26 no 1º (a 26ª com 6 dias, 7 nos bissextos) e 27 no 2º (a 27ª = 30–31/12) (pedido de 28/10/2026; antes, cada dia) |
| Sazonalidade mensal | Média de cada mês nos mesmos anos do mínimo/máximo, faixa p10–p90 (os percentis escolhidos) e a linha do ano de referência |
| Acumulado mensal | Soma do ano até cada mês; uma linha por ano; faixa entre os percentis escolhidos (padrão p10–p90) e média, com os anos do mínimo/máximo |
| Mais e menos intenso | Maior e menor total anual entre os N anos **completos** imediatamente anteriores ao ano de referência (padrão N = 10). A legenda do acumulado diz a janela: "2025 (mais intenso nos últimos 10 anos)" |
| Anos parciais | Anos que a base não cobre inteiros (2002) entram nas estatísticas e são citados nas notas |

## 9. Cenário atual — nowcast diário (`core/nowcast.py`)

| Regra | Definição |
|---|---|
| Resolução | Só diária (a base guarda a data, não a hora) |
| Focos | Todos os focos do município, UC ou TI (P23) na base (independe do período da barra lateral), pelo cruzamento com o polígono (§1), até o último dia da base |
| Último dia | O de `atualizacao_inpe.json`; se for provisório, a tela avisa que ainda é parcial |
| Comparação | Cada um dos últimos 30 dias × o mesmo dia do calendário nos anos anteriores que a base cobre desde 1º de janeiro (2003 em diante): média e máximo; e a média da **janela de 7 dias** (o dia ±3) nesses anos (P20). 29/02 sem par é ignorado |
| Semanal | Últimas 52 semanas (blocos de 7 dias até o último dia) × média e máximo da mesma semana nos anos anteriores (no PDF, no Excel e no pacote) |
| Relatório | PDF, Excel e CSV/PNG do pacote: indicadores, gráfico dos 30 dias e mapa dos últimos 7 dias (P18) |
| Indicadores | Focos no último dia, no dia anterior, nos últimos 7 e 30 dias (com a diferença para a soma das médias dos mesmos dias) e no ano até o mesmo dia/mês (% em relação à média desses anos e posição entre eles, empate = mesma posição) |
| Idade no mapa | Último dia; 1–2 dias antes; 3–6; 7–29 |

## 10. Panorama do estado — página inicial (`core/panorama.py`)

| Regra | Definição |
|---|---|
| Território | Estado inteiro ou uma região dele: Região de Integração (PA) ou Geográfica Imediata (demais), pelo município de cada foco (§1) |
| Data dos dados | Último dia com focos até 31/12 do ano final |
| Ano final "até a data" | Focos de 1º de janeiro até o dia/mês da data dos dados; comparado com o mesmo período do ano anterior e com a média do mesmo período dos anos anteriores do período (só anos cobertos desde 1º de janeiro) |
| Últimos 7 / 30 dias | Até a data dos dados |
| Regiões e municípios | Ranking do ano final com o desempate do §3 |
| Estatísticas | As do §8, com os focos do estado/região |

## 11. Cenário atual do estado — últimas 24 h e última semana (`core/cenario.py`)

| Regra | Definição |
|---|---|
| Território | Estado inteiro ou a região escolhida no filtro do Panorama (§10); independe do período |
| Últimas 24 h | O satélite de referência (AQUA_M-T) passa **uma vez por dia** e a base guarda só a data: últimas 24 h = a **passagem mais recente**, o último dia com focos na base inteira, sem passar do último dia buscado no INPE. Enquanto a passagem do dia corrente não é processada, vale a do dia anterior (P28) |
| Última semana | Os 7 dias até o dia da passagem, inclusive |
| Médias | As do nowcast (§9): soma das médias do mesmo dia nos anos anteriores cobertos desde 1º de janeiro |
| Parcial | Dia da passagem ainda provisório (`atualizacao_inpe.json`): indicador marcado "(parcial)" |
| Municípios | Focos nas 24 h e na semana; ordem: 24 h, depois semana |
| UCs e TIs | Pelo cruzamento do foco (§1); ordem: semana, depois 24 h |
| Semanas (último ano) | 52 blocos de 7 dias corridos terminando no dia da passagem; cada um × a mesma semana (mesmas datas) nos anos anteriores cobertos desde 1º de janeiro: média e máximo |
| Recorrência do mês | Grade proporcional (§4) sobre o limite do estado/região; por célula, nº de anos (os comparados do nowcast) com pelo menos um foco no mês da passagem; cada foco da semana recebe o valor da célula onde caiu. "Frequente" = foco no mês em pelo menos metade desses anos |
| Base regravada | O nowcast regrava a base em segundo plano; a página só recarrega sozinha no ciclo do painel da barra lateral, nunca no meio de um clique |
