# Documento Técnico 03 — Fontes de Dados e Atualização das Bases

## 1. Como os dados chegam

As bases ficam em `BASES_GEOJSON/` (fora do git — são grandes) e vão dentro do pacote Windows. A base de focos é **atualizada sozinha** com os arquivos do INPE (§5); as demais só mudam substituindo o arquivo **com o mesmo nome**. A pasta pode ser trocada pela variável de ambiente `AUTOSIMD_FOCOS_BASES` (os testes usam `amostras/bases`).

| Arquivo | Fonte | Abrangência | Uso |
|---|---|---|---|
| `bdqueimadas_consolidado.parquet` | BDQueimadas/INPE, satélite de referência AQUA_M-T | Brasil, 04/07/2002 até o último dia buscado (5.293.068 focos até 21/10/2026) | Todos os cálculos |
| `atualizacao_inpe.json` | gerado pelo programa | — | Último dia, dias provisórios, última busca, histórico (§5) |
| `nowcast.json` | gerado pelo programa | — | Nowcast ligado/desligado (§5); não vai no pacote Windows (começa desligado) |
| `mun-brGEOJSON/NM_UF_<Estado>.geojson` | IBGE (malha municipal) | Um arquivo por UF (27) | Lista de estados, limite do município, área (densidade) |
| `ucGEOJSON/UC-BR.geojson` | CNUC/MMA | 1.805 UCs | Limite da UC analisada; UCs sobrepostas ao município |
| `tiGEOJSON/TI-BR.geojson` | FUNAI | 637 TIs | Limite da TI analisada; TIs sobrepostas ao município |

## 2. Base de focos

- Até 31/12/2025, gerada fora do programa pelo script `AUTO.py`, que converte em Parquet um GeoJSON do BDQueimadas já cruzado com os limites (`/home/lobs/SIG/FOCOS DE CALOR/bdqueimadas_consolidado.geojson`). O script não está mais na pasta antiga, mas continua no **histórico do repositório GitHub** (commit `5399b96`, v0.07: `git show 5399b96:AUTO.py`). A base agora é mantida pela atualização automática (§5), que segue as mesmas regras.
- Se a base for refeita do zero por outro meio, rode a ferramenta do item 3 para TI e para UC.
- Colunas obrigatórias (`docs/05`): faltando qualquer uma, a leitura é recusada com mensagem.

## 3. Colunas `UC` e `TI` (área protegida de cada foco)

`ferramentas/atualizar_area_protegida_focos.py` cruza cada foco (lon/lat) com os polígonos e grava o rótulo da área:

```bash
python ferramentas/atualizar_area_protegida_focos.py TI BASES_GEOJSON/tiGEOJSON/TI-BR.geojson --campo-nome terrai_nom --campo-codigo terrai_cod
python ferramentas/atualizar_area_protegida_focos.py UC BASES_GEOJSON/ucGEOJSON/UC-BR.geojson --campo-nome NOME_UC1 --campo-codigo ID_UC0
```

- Rótulo `NOME (CÓDIGO)` em maiúsculas; fora de qualquer área = `NONE`; áreas sobrepostas = a de menor área.
- A base anterior é copiada para `backup/bases/` antes de sobrescrever.
- `core.territorios.rotulo_area_protegida` monta o mesmo rótulo para achar o polígono da área escolhida. **Se os campos das bases mudarem, alterar os dois lugares.**

## 4. Amostras para os testes

`ferramentas/gerar_amostras.py` gera `amostras/bases/` (≈16 MB, versionado), com a mesma estrutura de `BASES_GEOJSON/`:

- focos de PA e AP em 2023 e 2024 (102.371 focos, inclusive 24 sem município/UF);
- limites de São Félix do Xingu, Altamira, Novo Progresso (PA) e Oiapoque (AP);
- 22 UCs e 19 TIs que tocam esses municípios;
- as 243 localidades do IBGE desses municípios e o território quilombola que os toca (`localidades/`).

`gerar_amostras.py --so-localidades` refaz só o recorte das localidades (sem mexer nos focos). `amostras/kml_localidades/PA/` tem dois KML reais do IBGE (Novo Progresso e Melgaço, que tem território quilombola) para o teste da conversão.

Depois de trocar a base completa, as amostras podem ser regeneradas; os números esperados nos testes mudam se a base mudar nesses anos.

## 5. Atualização automática pelo INPE (`core/atualizacao.py`)

| Fonte | Endereço | O que tem |
|---|---|---|
| Diário | https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/ | `focos_diario_br_AAAAMMDD.csv`, só os **últimos ~32 dias** (em 21/10/2026: 20/09 a 21/10) |
| Mensal | https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/ | `focos_mensal_br_AAAAMM.csv`, todos os meses (o mês corrente é parcial) |

Os dois têm o mesmo formato (UTF-8, `,`, todos os satélites): `id, lat, lon, data_hora_gmt, satelite, municipio, estado, pais, municipio_id, estado_id, pais_id, numero_dias_sem_chuva, precipitacao, risco_fogo, bioma, frp`. Um arquivo de agosto ou setembro tem ~100 MB; um diário, 1–3 MB.

**Quando (em segundo plano, modelo do AutoSIMD-HIDRO):** o programa **abre com a base local**, sem esperar o INPE. Uma thread (`AtualizadorFocos`, uma por processo) faz:
- uma busca quando o programa abre (P16);
- com o **Nowcast** ligado (toggle na barra lateral, salvo em `nowcast.json`): uma busca na hora em que é ligado e depois a cada **4 horas**;
- se a busca falhar (sem internet, servidor fora do ar): nova tentativa em 30 minutos.

O painel da barra lateral (`app.painel_atualizacao`, refeito a cada 5 s) mostra o andamento ("⏳ … pode continuar usando o programa"), o resultado e a próxima busca. Quando a base muda, os dados em memória são descartados: o Panorama e a página Bases de dados recarregam sozinhos; no Diagnóstico aparece só um aviso, para não apagar a análise aberta. Não há mais botão "Buscar focos novos". Sem internet, tudo funciona com a base que existe.

**Quais dias:** do dia seguinte ao último da base até hoje (UTC), mais os dias **provisórios**. Para cada dia: arquivo diário se o servidor ainda o tiver; senão, o mensal do mês (quando faltam mais dias do que o diário guarda). Arquivos já baixados numa pasta local (`ferramentas/atualizar_base_inpe.py --pasta`) têm preferência.

**Dia provisório:** baixado antes de 30 h depois da meia-noite UTC do dia (o INPE publica os focos ao longo do dia; a passagem do AQUA à tarde entra horas depois). É baixado de novo na próxima busca, e os focos daquele dia são **substituídos** (nunca somados). Dias que não puderam ser baixados também ficam pendentes.

**Consolidação mensal (P17):** os dias que vieram de arquivos **diários** ficam registrados (`dias_diarios`). Quando o mês termina (30 h depois da meia-noite UTC do último dia) e o arquivo mensal dele aparece no servidor (ou na pasta local), o mês inteiro é baixado do mensal e esses dias são trocados pela versão consolidada (≈100 MB em agosto/setembro, uma vez por mês).

**Conversão para a base** (reproduz a base consolidada sem nenhuma diferença — conferido com dezembro de 2025, 10.669 focos):
- só `satelite = AQUA_M-T` (o satélite de referência; a base bate com a tabela do INPE: Pará 2025 = 18.366 × 18.367 no site, out/2026 = 7.415 nos dois);
- `data` = 10 primeiros caracteres de `data_hora_gmt`; `ano`, `mes` dela; `lon`/`lat` com a precisão do arquivo (a base antiga tem 3 casas);
- `NM_MUN`, `NM_UF`, `SIGLA_UF`: ponto-no-polígono com os limites do IBGE (`mun-brGEOJSON`), em maiúsculas; na divisa vence o primeiro município na ordem dos arquivos; fora de todos = `NONE`. **Não** se usa o `municipio` do INPE (grafias diferentes, ex.: ASSÚ × AÇU, e 0,6% dos focos fora do município indicado);
- `UC`, `TI`: ponto-no-polígono com as bases de UC/TI, rótulo `NOME (CÓDIGO)` em maiúsculas, áreas sobrepostas = a de menor área; mesma área = a que vem depois no arquivo (mesma regra do §3).
- **Conferência:** `ferramentas/verificar_base.py` refaz o cruzamento da base inteira e compara com as colunas (5.293.068 focos em 21/10/2026: nenhuma diferença; ≈7 min; `--anos` para só alguns anos).

**Gravação:** lê a base, tira os focos dos dias baixados, acrescenta os novos, grava num arquivo temporário e troca (a versão anterior fica em `bdqueimadas_consolidado.anterior.parquet`). Uma trava (`.atualizando.lock`) impede duas atualizações ao mesmo tempo (vencida depois de 1 h). Arquivo do INPE em formato inesperado = atualização recusada, base intacta.

**Desempenho:** ~1 s por arquivo diário; o cruzamento com os 5.573 municípios lê ~600 MB de limites (~15 s, uma vez por execução do programa; dia sem focos do AQUA pula essa etapa). Importação de jan–set/2026 (9 mensais): 27 s.

Importação inicial (21/10/2026): jan–set/2026 da pasta `~/Downloads/FOCOS 2026` (70.350 focos) e 01–21/10 pelos diários (20.445 focos).

## 7. Localidades do IBGE e territórios quilombolas (`core/localidades.py`)

**Origem:** KML do IBGE "Localidades 2022" (Censo 2022), um arquivo por município, numa subpasta por UF (5.571 arquivos, ~1 GB; baixados em 25/11/2026 em `~/Downloads/LOCALIDADES_MUN_BRASIL_KML`). Cada KML tem pastas por categoria (cidade, vila, núcleo urbano, povoado, núcleo rural, lugarejo, localidade indígena, localidade quilombola, agrovila de assentamento, outras) com um ponto por localidade e a pasta "13. Referência" com o limite do município e os territórios quilombolas (polígonos).

**Importação (uma vez, ou quando o IBGE publicar outra versão):**

```bash
python ferramentas/importar_localidades.py ~/Downloads/LOCALIDADES_MUN_BRASIL_KML
```

Gera em `BASES_GEOJSON/localidades/` (9 s; **1 GB de KML → 5,3 MB**): `localidades_ibge_2022.parquet` (87.362 localidades, 2,7 MB) e `territorios_quilombolas_2022.parquet` (495 territórios, 2,6 MB). A mesma localidade aparece em duas pastas do KML quando também é indígena, quilombola ou agrovila (8.801 casos): aqui vira uma linha, com a categoria da pasta geral e as marcas `indigena`/`quilombola`/`agrovila_pa`. O território quilombola que cruza vários municípios vem em cada KML: fica um por código (união das partes). O limite municipal do KML não é importado (o programa já usa os do IBGE). Colunas: `docs/06` §9.

**Uso:** ainda nenhuma tela lê essas tabelas — são a base da análise de localidades vulneráveis a fogo e fumaça (proposta em `docs/09`, rodada 10). Por isso ainda não vão no pacote Windows (`BASES_USADAS`); entram quando a análise for implementada.

## 8. Vento, eventos de fogo e PM2,5 — dados ao vivo (P40–P42)

| Dado | Fonte | Quando | Onde fica |
|---|---|---|---|
| Vento a 10 m (velocidade, direção de onde vem, rajada), hora a hora: dia anterior + 48 h | Open-Meteo `api.open-meteo.com/v1/forecast` (gratuito, sem chave, CC BY 4.0) | Só com a chave **Vento** ligada (painel ⋯, acima do Nowcast): junto com cada busca de focos (ao abrir e, com o Nowcast, a cada 4 h) e na hora em que a chave é ligada | `BASES_GEOJSON/vento.parquet` (30 dias) e `vento.json` (chave + estado) |
| Eventos de fogo ativos e em observação + indicadores por passagem + frentes de fogo (24 h) | Painel do Fogo (CENSIPAM) — WFS `panorama.sipam.gov.br/geoserver/painel_do_fogo/wfs`, camadas `mv_evento_filtro`, `mv_indicadores_queimadas` e `mv_deteccoes_classificadas` ("Frente de Fogo (24h)") | Botão da aba Vulnerabilidade | Só na sessão |
| Vento nos eventos e PM2,5 nas localidades | Open-Meteo (`forecast` e `air-quality`, CAMS) | Botão da aba Vulnerabilidade | Só na sessão |
| Mosaico Sentinel-2 SWIR | Painel do Fogo — WMS `painel_do_fogo:sentinel_swir` | Chave no mapa interativo | Não é gravado (ladrilhos) |

**Vento (P40, resposta de 25/11/2026):** só para o **estado em análise** (o da página aberta; trocar de estado com a chave ligada passa a buscar o novo) e só nas quadrículas de **0,25°** (~28 km) com foco nos últimos 7 dias da base (no Pará, em 25/11/2026: 492 quadrículas, 2 consultas de ~2,5 s). Teto de 1.500 quadrículas por coleta (limite gratuito do Open-Meteo: 10 mil por dia). Sem internet: frase no painel, base intacta.

**Tempo da busca (25/11/2026, São Félix do Xingu):** eventos 1,5 s, frentes 1,5 s, passagens 1,5 s, vento 1,1 s, PM2,5 2,2 s; em paralelo, **≈ 3 s no total** (antes, em sequência e com o vento em todos os eventos e o PM2,5 em cada localidade: 8,7 s).

**Painel do Fogo:** a busca é pelo retângulo do município + 0,5° (o filtro por UF/município do serviço não funciona — os campos vêm como listas Java); ~1,5 s para os eventos e ~1,5 s para os indicadores (filtrados por `id_evento`). Só eventos ativos e em observação (os extintos saem do serviço).

**Testes:** `AUTOSIMD_FOCOS_AO_VIVO=0` no `conftest.py`; as respostas reais gravadas em `amostras/ao_vivo/sao_felix_do_xingu.json` (25/11/2026) são devolvidas pela consulta (endereço + parâmetros), porque a busca é paralela.
