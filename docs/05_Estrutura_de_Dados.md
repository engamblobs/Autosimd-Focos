# Documento Técnico 05 — Estrutura de Dados

O AutoSIMD-FOCOS **não tem banco de dados próprio**: lê as bases de `BASES_GEOJSON/` (`docs/03`) e monta tudo em memória a cada diagnóstico. O que ele grava: a base de focos atualizada pelo INPE, o controle `atualizacao_inpe.json` e a cópia `bdqueimadas_consolidado.anterior.parquet` (`docs/03` §5). O pacote .zip vai direto para o download do navegador.

## 1. Bases lidas

| Base | Formato | Leitura | Guardada em memória |
|---|---|---|---|
| Focos de calor | Parquet (10 colunas, `docs/06` §1) | `focos.carregar_focos` | DataFrame único, compartilhado entre as sessões (`st.cache_resource`) |
| Municípios | GeoJSON por UF (`NM_MUN`) | `territorios.municipios_do_estado` | Dicionário nome → geometria, por arquivo (até 4 estados) |
| UCs e TIs | GeoJSON nacional | `territorios.carregar_areas_protegidas` | Lista `{tipo, nome, geom}`, sem feições repetidas |
| Regiões de Integração | CSV (`referencia/municipios_pa.csv`) | `regioes.carregar_regioes` | Dicionário nome → região |

## 2. Estruturas em memória (`core/diagnostico.py`)

| Estrutura | Conteúdo |
|---|---|
| `ResumoMunicipio` | Os indicadores do resumo executivo (`docs/07` §2) |
| `DiagnosticoMunicipio` | Território (estado, UF, município, região, polígono), focos do município e do estado no período, `ResumoMunicipio`, séries anual e mensal, top acumulado, rankings do estado e da região, UCs/TIs sobrepostas e sua tabela |
| `DiagnosticoArea` | Tipo (UC/TI), rótulo, polígono, focos da área no período, séries anual e mensal |
| `produto.Pacote` | Nome do .zip, bytes do .zip e do PDF |
| `estatisticas.EstatisticasMunicipio` | Tabelas e séries no modelo INPE (`docs/07` §8) |
| `nowcast.Nowcast` | Últimos 30 dias do município, comparação com o mesmo dia dos anos anteriores, focos recentes; `semanal` = últimas 52 semanas (`inicio`, `fim`, `focos`, `media`, `maximo`) (`docs/07` §9) |
| `cenario.CenarioAtual` | Cenário do estado/região: dia da passagem, focos das 24 h e da semana, municípios, UCs/TIs, nowcast; `historico_mes` = focos (`lon`, `lat`, `ano`) do mês da passagem nos anos comparados (`docs/07` §11) |
| `cenario.RecorrenciaDoMes` | Grade proporcional, nº de anos com foco no mês por célula e os focos da semana com a recorrência da célula onde caíram (`docs/07` §11) |
| `atualizacao.ResultadoAtualizacao` | Situação da busca no INPE, focos novos, dias, provisórios |

## 3. Regras

- Textos da base de focos são normalizados na leitura (sem espaços nas pontas, MAIÚSCULAS); comparações de nome de município ignoram acentos (`texto.chave_nome`).
- Valores vazios: `""`, `NONE`, `NULL`, `NAN`, `N/A` (`config.VALORES_VAZIOS`) — nunca entram em listas nem rankings.
- Mudança de coluna ou de campo das bases exige atualizar este documento e o `docs/06` no mesmo incremento.
