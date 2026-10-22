# Documento Técnico 04 — Arquitetura e Organização de Arquivos

## 1. Árvore do projeto

```text
Autosimd-Focos 2/                  # pasta de trabalho; o projeto continua se chamando AutoSIMD-FOCOS
├── CLAUDE.md                      # regras para o desenvolvimento com IA
├── README.md
├── app.py                         # interface Streamlit (somente telas)
├── run_app.py                     # inicia o Streamlit sem console (1ª porta livre entre 8521 e 8570) + abre o navegador
├── requirements.txt, pytest.ini
├── .gitignore                     # ignora BASES_GEOJSON/, dist/, python/, backup/
│
├── core/                          # regras e processamento (sem Streamlit)
│   ├── config.py                  # caminhos, constantes, versão do app, desenvolvedor
│   ├── texto.py                   # nomes sem acento, nome de arquivo, números no padrão brasileiro
│   ├── regioes.py                 # Região de Integração (Pará) ou Geográfica Imediata (demais) do município
│   ├── focos.py                   # leitura da base Parquet e filtros (UF, período, listas)
│   ├── atualizacao.py             # busca no INPE (diário/mensal), conversão, gravação e a thread de segundo plano
│   ├── nowcast.py                 # cenário atual do município (últimos 30 dias)
│   ├── panorama.py                # página inicial: panorama do estado/região
│   ├── territorios.py             # limites de município/UC/TI, sobreposição, área geodésica
│   ├── diagnostico.py             # indicadores, rankings, séries (DiagnosticoMunicipio, DiagnosticoArea)
│   ├── estatisticas.py            # estatísticas do município no modelo INPE (mês, dia, semana, quinzena, acumulado)
│   ├── graficos_estatisticas.py   # comparativos e acumulado: matplotlib (PDF/PNG) e Altair (tela, interativo)
│   ├── grade.py                   # grade de 10 km ajustada à latitude: contagem, recorrência, GeoJSON do QGIS
│   ├── kernel.py                  # densidade de kernel gaussiano (numpy)
│   ├── fundo_satelite.py          # tiles do Google Satélite para o mapa do cenário atual
│   ├── graficos.py                # top do estado, evolução, sazonalidade
│   ├── mapas.py                   # mapas 1 a 4
│   ├── relatorio_pdf.py           # PDF do diagnóstico municipal
│   └── produto.py                 # figuras + Excel + metadados + pacote .zip
│
├── referencia/                    # tabelas fixas versionadas no git
│   ├── municipios_pa.csv          # IBGE, nome, Região de Integração (a mesma do AutoSIMD-DESASTRE)
│   ├── municipios_br.csv          # 5.573 municípios com Região Geográfica Imediata/Intermediária (IBGE 2017)
│   ├── fontes/                    # planilha do IBGE das Regiões Geográficas (origem do municipios_br.csv)
│   └── logos/                     # AUTOSIMD-FOCOS.png, AutoSIMD-FOCOS.ico, CBM-CEDEC.png
│
├── BASES_GEOJSON/                 # bases reais (fora do git, vão no pacote) — docs/03
├── amostras/bases/                # recorte real pequeno, mesma estrutura, usado nos testes (versionado)
├── amostras/inpe/                 # recortes reais dos CSV do INPE, datas trocadas (testes da atualização)
├── testes/                        # pytest (conftest.py aponta as bases para a amostra)
├── ferramentas/
│   ├── atualizar_area_protegida_focos.py   # refaz a coluna UC ou TI da base de focos
│   ├── atualizar_base_inpe.py              # mesma atualização do programa, pela linha de comando (aceita pasta local)
│   ├── verificar_base.py                   # confere se NM_MUN/UF/UC/TI da base = cruzamento com os polígonos
│   ├── gerar_municipios_br.py              # gera referencia/municipios_br.csv (Regiões Imediatas)
│   └── gerar_amostras.py                   # gera amostras/bases a partir de BASES_GEOJSON
├── empacotamento/                 # pasta portátil Windows (padrão AutoSIMD-DESASTRE)
│   ├── empacotar_windows.py       # monta dist/AutoSIMD-FOCOS_v<versão>/ e o .zip
│   ├── iniciar.py                 # sobe o Streamlit (porta 8521–8570), atalho na Área de Trabalho
│   ├── Iniciar_AutoSIMD-FOCOS.bat, LEIA-ME.txt, config.toml, requirements-windows.txt
│   └── static/autosimd_focos.txt  # identificação do próprio servidor
├── python/                        # cache do Python portátil do Windows (fora do git)
├── dist/                          # pacotes gerados (fora do git)
└── docs/                          # esta documentação
```

## 2. Fluxo

```
barra lateral (território, período)
   → focos.carregar_focos (uma vez)        → territorios: limite + UCs/TIs sobrepostas
   → diagnostico.diagnosticar_municipio / diagnosticar_area
   → estatisticas.estatisticas_municipio (focos dentro do polígono; parâmetros da tela)
   → produto.figuras_municipio / figuras_area (graficos.py, mapas.py, grade.py) + graficos_estatisticas
   → tela (app.py) e produto.pacote_municipio / pacote_area (relatorio_pdf.py, Excel, GeoJSON, CSV, PNG)
   → download do .zip no navegador
```

## 3. Princípios

- `app.py` só chama funções de `core/`; toda regra fica em `core/` e é testável sem abrir a interface.
- `app.py` lê os caminhos de `core.config` no momento do uso (os testes trocam a pasta das bases).
- O PDF, os PNGs e a tela usam **as mesmas** figuras e tabelas (nunca recalculam).
- Caminhos sempre relativos à pasta do programa (`core.config.RAIZ`): o mesmo código roda no Linux e no pacote Windows.
- Internet só para a busca de focos novos no INPE (`core/atualizacao.py`) e para a imagem de satélite do mapa do cenário atual; sem ela, tudo funciona com a base que existe (o mapa sai sem a imagem).

## 4. Correspondência com o v0.10 (app.py de arquivo único)

| v0.10 (`app.py`) | v0.11 |
|---|---|
| `carregar_focos_consolidados` | `focos.carregar_focos` |
| `get_regiao_municipio` + `core/dicionario_municipios-regioes.py` | `regioes.regiao_do_municipio` + `referencia/municipios_pa.csv` |
| `carregar_geometria_alvo`, `obter_mapa_estados`, `rotulo_area_protegida`, `carregar_areas_protegidas`, `areas_protegidas_no_territorio`, `calcular_area_km2`, `contar_focos_na_area` | `territorios.*` |
| Cálculos soltos no bloco `if btn_processar:` | `diagnostico.diagnosticar_municipio` / `diagnosticar_area` |
| `render_rankings_areas_protegidas`, `criar_dataframe_ranking` | `diagnostico.ranking_areas_protegidas` + `app.rankings_areas_protegidas` |
| `np.histogram2d` repetido em 4 lugares, `generate_qgis_grid_geojson` | `grade.*` |
| `generate_p1_charts_figures`, `generate_seasonality_chart` | `graficos.*` |
| `generate_map_figures`, `generate_trimester_recurrence_map`, `plot_polygon_ibge` | `mapas.*` |
| `generate_pdf_report`, `_build_pdf_*`, `NumberedCanvas` | `relatorio_pdf.*` |
| Montagem do zip no `app.py`, `exportar_pacote_analise` | `produto.pacote_municipio` / `pacote_area` |
| Código sem uso (KML, `extrair_dados_ti/uc`, `gerar_pacote_completo`, `carregar_geojson_ti/uc`) | removido |
