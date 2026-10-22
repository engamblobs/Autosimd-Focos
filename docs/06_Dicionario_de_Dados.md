# Documento Técnico 06 — Dicionário de Dados

Baseado nas bases reais de `BASES_GEOJSON/` (21/10/2026).

## 1. Base de focos — `bdqueimadas_consolidado.parquet`

| Coluna | Tipo | Regra |
|---|---|---|
| `lon`, `lat` | float | Coordenadas WGS 84 do foco |
| `ano` | int | 2002–2025; não numérico → 0 (ignorado) |
| `mes` | int | 1–12; fora disso o foco não entra no mapa trimestral |
| `data` | texto `AAAA-MM-DD` | Só usado na página Bases de dados (foco mais recente) |
| `NM_MUN` | texto | Município, MAIÚSCULAS com acento (`SÃO FÉLIX DO XINGU`); `NONE` em 157 focos sem município |
| `NM_UF` | texto | Estado por extenso, MAIÚSCULAS (`PARÁ`) |
| `SIGLA_UF` | texto | `PA`; `NONE` nos focos sem município |
| `UC` | texto | `NOME (CÓDIGO)` da UC (CNUC `NOME_UC1`/`ID_UC0`) ou `NONE` |
| `TI` | texto | `NOME (CÓDIGO)` da TI (FUNAI `terrai_nom`/`terrai_cod`), MAIÚSCULAS, ou `NONE` |

O estado é escolhido pelo nome do arquivo de limites (`NM_UF_Pará.geojson` → `PARÁ`) e casado com `NM_UF` ou `SIGLA_UF`.

### 1.0 Nowcast — `nowcast.json`

`{"ligado": true|false}` — gravado pelo toggle da barra lateral; ausente = desligado.

### 1.1 Controle da atualização — `atualizacao_inpe.json`

| Campo | Conteúdo |
|---|---|
| `ultimo_dia` | Último dia (ISO) com arquivo do INPE incorporado |
| `provisorios` | Dias (ISO) a baixar de novo: baixados antes de fechar ou que falharam |
| `dias_diarios` | Dias (ISO) que vieram de arquivos diários e ainda serão trocados pelo mensal consolidado (P17) |
| `ultima_busca` | Data/hora (UTC) da última consulta ao servidor — decide a busca automática do dia |
| `historico` | Até 50 registros: `em`, `arquivos`, `dias`, `de`, `ate`, `focos_novos`, `total` |

## 2. Limites

| Base | Campos usados |
|---|---|
| `NM_UF_<Estado>.geojson` (IBGE) | `NM_MUN` (caixa mista, ex.: `São Félix do Xingu`); geometria |
| `UC-BR.geojson` (CNUC) | `NOME_UC1`, `ID_UC0`; geometria |
| `TI-BR.geojson` (FUNAI) | `terrai_nom`, `terrai_cod`; geometria |

O campo `AREA_KM2` do IBGE não é usado: a área é calculada no elipsoide WGS 84 (`territorios.area_km2`); em São Félix do Xingu dá 84.213 km² × 84.212,9 km² do IBGE.

## 3. Referência — `referencia/municipios_br.csv` (P4)

UTF-8, `;`: `cd_mun; nm_mun; nm_uf; sigla_uf; cd_rgi; regiao_imediata; cd_rgint; regiao_intermediaria; regiao_integracao` — 5.573 linhas (5.570 municípios + Boa Esperança do Norte-MT + as duas lagoas do RS, que não têm região). Nomes como nos limites do IBGE (a grafia de `NM_MUN`); regiões do IBGE 2017 (`referencia/fontes/regioes_geograficas_composicao_por_municipios_2017_20180911.xls`), ligadas pelo código; `regiao_integracao` só no Pará. Gerada por `ferramentas/gerar_municipios_br.py`.

## 3.1 Referência — `referencia/municipios_pa.csv`

UTF-8, `;`: `ibge; nome_oficial; variacoes; regiao_integracao; regiao_geografica_intermediaria` — 144 municípios, 12 Regiões de Integração. `variacoes` = outras grafias aceitas, separadas por `|` (hoje vazia). Mesma tabela do AutoSIMD-DESASTRE; substitui o antigo `core/dicionario_municipios-regioes.py` (conteúdo idêntico, conferido nos 144 municípios).

## 4. Arquivos do pacote

| Arquivo | Colunas / campos |
|---|---|
| `dados_<MUN|UC|TI>_<alvo>.csv` | As 10 colunas da base, só os focos do território no período (UTF-8, `,`) |
| `ranking_municipios.csv`, `ranking_ucs.csv`, `ranking_tis.csv` | `NM_MUN`/`UC`/`TI`; `Focos de Calor` — município: focos do **estado** no período; UC/TI: focos **da área** |
| `estatisticas_<…>.xlsx` | Aba `Evolucao_Historica` (`Ano`, `Focos`); aba `Sazonalidade_Mensal` (`Mês`, `Média`, `pXX`, `pYY`, `<ano de referência>`) |
| `grade_10x10km_<alvo>.geojson` | Polígonos das células com foco: `cell_id`, `focos_acumulados`, `recorrencia_anos` (WGS 84) |
| `estatisticas_<…>.xlsx`, abas das estatísticas | `Focos_Mes_a_Mes` (Ano × Janeiro…Dezembro, Total; linhas Mínimo/Média/Máximo; menor valor da coluna em amarelo, maior em vermelho), `Focos_Dia_a_Dia` (Mês/Ano × 1…31, Total), `Comparativo_Mensal`/`_Semanal`/`_1o_Semestre`/`_2o_Semestre` (mês, semana ou dia dd/mm; ano de referência; Mínimo; Média; Máximo), `Acumulado_Mensal` (Ano × Jan…Dez; linhas pXX, pYY, Média), `Notas_Estatisticas`; no município, `Nowcast_Ultimos_30_Dias` (Data, Focos, Média e Máximo do dia, Média ±3 dias), `Nowcast_Focos_Recentes` (Data, Dias antes do último, Idade, Latitude, Longitude, UC, TI), `Nowcast_Indicadores` |
| `nowcast/*.csv` | As três abas do nowcast, uma por arquivo |
| `estatisticas/01_…07_*.csv` | As mesmas 7 tabelas, uma por arquivo (UTF-8, `,`; vazio = sem cobertura da base) |
| `metadados.json` | `nome_alvo`, `tipo_analise`, `ano_inicio`, `ano_fim`, `total_focos`, `gerado_por`; município: `uf`, `tipo_regiao`, `regiao`, `nowcast_ate`; UC/TI: `uf_predominante` |
| `grade_10x10km_<alvo>.geojson` (`descricao`) | Observação do ajuste da grade à latitude (P8) |
| `risco_de_recorrencia/risco_<n>_<classe>_<alvo>.kml` | 4 arquivos (1 baixo, 2 moderado, 3 alto, 4 muito alto). Mais `risco_recorrencia_classes_<alvo>.geojson`: as classes com células numa FeatureCollection (`ordem`, `classe`, `rotulo`, `cor_hex`, `anos_min`, `anos_max`, `celulas`, `area_km2`, `q1`, `q2`, `q3`). Cada KML: `Document` com nome, descrição (território, período, nº de células, recorrência em anos, área, quartis Q1–Q3, nota da grade), estilo na cor da classe e **um** `Placemark` com a `MultiGeometry` das células da classe dissolvidas (nenhum se a classe ficou vazia). WGS 84 |
