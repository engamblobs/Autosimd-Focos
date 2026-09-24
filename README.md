# AutoSIMD-FOCOS

**Diagnóstico Territorial de Focos de Calor**
Sala de Informações e Monitoramento de Desastres (SIMD) — Coordenadoria Estadual de Proteção e Defesa Civil do Pará (CEDEC/PA)

O AutoSIMD-FOCOS automatiza a análise histórica de focos de calor detectados por satélite (BDQueimadas/INPE) e gera, em poucos segundos, um diagnóstico territorial pronto para apoiar o planejamento de prevenção e combate a incêndios florestais.

## O que o programa faz

Você escolhe **o território** e **o período de anos**, clica em **Processar Diagnóstico Completo** e o sistema gera:

- **Resumo executivo** — focos no ano, posição do município no ranking estadual (acumulado e no ano), participação no total do estado, variação em relação ao ano anterior e **densidade média anual de focos (focos/km²/ano)**.
- **Gráficos** — Top 5 municípios do estado, evolução anual dos focos e padrão sazonal (distribuição mensal).
- **Mapas**
  1. Dispersão espacial dos focos no último ano, com as **Unidades de Conservação e Terras Indígenas** existentes no município desenhadas e identificadas;
  2. Densidade acumulada em grade de 10 km × 10 km;
  3. Recorrência temporal (em quantos anos cada célula teve fogo);
  4. Migração sazonal dos focos por trimestre.
- **Tabelas** — ranking estadual, comparativo dentro da Região de Integração do Pará e focos por UC/TI no município.
- **Pacote para download (.zip)** com relatório **PDF** diagramado, planilha **Excel**, grade **GeoJSON** para o QGIS, rankings em CSV e todas as imagens em PNG.

Níveis de análise disponíveis:

| Nível | Exemplo |
|---|---|
| Estado / Município (qualquer município do Brasil) | São Félix do Xingu – PA |
| Unidade de Conservação (UC) | Estação Ecológica da Terra do Meio |
| Terra Indígena (TI) | TI Apyterewa |

> As bases de UC e TI incluídas nesta versão cobrem o estado do Pará.

## Instalação no Windows

Não é preciso instalar Python nem ter internet: o pacote já traz tudo.

**Requisitos:** Windows 10 ou 11 (64 bits) e cerca de 2 GB livres em disco.

1. Acesse a página **[Releases](https://github.com/engamblobs/Autosimd-Focos/releases/latest)** e baixe o arquivo `AutoSIMD-FOCOS_v<versão>.zip` (≈ 300 MB).
2. Clique com o botão direito no arquivo baixado → **Extrair tudo…** e escolha uma pasta (ex.: `C:\AutoSIMD-FOCOS`).
   **Não execute de dentro do .zip** — extraia primeiro.
3. Abra a pasta extraída e dê dois cliques em **`Iniciar_AutoSIMD-FOCOS.bat`**.
4. Se o Windows exibir *"O Windows protegeu o computador"*, clique em **Mais informações → Executar assim mesmo**.
5. Uma janela preta abre e, em alguns segundos, o sistema aparece no navegador (endereço `http://localhost:8501`).
6. Na primeira execução é criado o atalho **AutoSIMD-FOCOS** na Área de Trabalho, com o ícone da Sala — use-o nas próximas vezes.

**Para encerrar:** feche a janela preta. Fechar apenas o navegador deixa o sistema rodando; para voltar, abra o atalho novamente.

**Para atualizar as bases de dados:** substitua os arquivos dentro de `BASES_GEOJSON\` mantendo exatamente os mesmos nomes (`bdqueimadas_consolidado.parquet`, `mun-brGEOJSON\NM_UF_<Estado>.geojson`, `ucGEOJSON\UC-BR.geojson`, `tiGEOJSON\TI-BR.geojson`) e reabra o sistema.

**Para atualizar o programa:** baixe o `.zip` da nova versão, extraia em uma nova pasta e abra o `.bat` dela uma vez — o atalho da Área de Trabalho passa a apontar para a versão nova.

## Fontes de dados

- **Focos de calor:** BDQueimadas / INPE (satélite de referência).
- **Limites municipais:** IBGE.
- **Unidades de Conservação:** CNUC / MMA.
- **Terras Indígenas:** FUNAI.

## Para desenvolvedores

O programa é um app [Streamlit](https://streamlit.io) em um único arquivo (`app.py`). As bases de dados não ficam no repositório (são grandes demais); coloque-as em `BASES_GEOJSON/`, na mesma estrutura descrita acima.

```bash
# Rodar localmente (Linux)
python -m streamlit run app.py

# Gerar o pacote Windows portátil em dist/ (baixa o Python portátil e as bibliotecas para Windows)
python empacotamento/empacotar_windows.py
```

Dependências: `streamlit`, `pandas`, `pyarrow`, `numpy`, `matplotlib`, `shapely`, `pyproj`, `reportlab`, `pillow`, `openpyxl` — versões fixadas em [`empacotamento/requirements-windows.txt`](empacotamento/requirements-windows.txt).

## Autor e contato

**Bruno Lobão da Silva** — Técnico de Defesa Civil, CEDEC/PA (DGR/SIMD) · Soldado do CBMPA
📧 engamb.lobs@gmail.com · Sala de Monitoramento: simdcedec@gmail.com
