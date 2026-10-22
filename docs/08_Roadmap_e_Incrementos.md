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

## Próximos incrementos (propostos — dependem de `docs/09`)

| # | Incremento | Depende de |
|---|---|---|
| 13 | (a definir com o usuário) | — |

## Modelo de pedido ao Claude

> Implemente o **incremento N** do `docs/08`. Siga o `CLAUDE.md`. Ao terminar, responda no formato padrão e atualize os documentos afetados.
