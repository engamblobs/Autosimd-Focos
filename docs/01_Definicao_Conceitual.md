# Documento Técnico 01 — Definição Conceitual

## 1. Identificação

| Item | Definição |
|---|---|
| Sistema | AutoSIMD-FOCOS |
| Órgão usuário | Defesa Civil do Pará — CEDEC/PA, Sala de Informações e Monitoramento (SIMD) |
| Fonte principal | BDQueimadas / INPE — focos de calor por satélite (satélite de referência Aqua-Tarde) |
| Fontes de limites | IBGE (municípios), CNUC/MMA (Unidades de Conservação), FUNAI (Terras Indígenas) |
| Escopo geográfico | Todo o Brasil (qualquer município, UC ou TI); Regiões de Integração só no Pará |
| Ano | 2026 |
| Desenvolvimento | Bruno Lobão da Silva — Técnico de Defesa Civil, CEDEC/PA (DGR/SIMD) · Soldado do CBMPA · Eng. Ambiental e Energias Renováveis (UFRA) · Mestrando em Gestão de Riscos e Desastres Naturais na Amazônia (UFPA) |
| Contato | engamb.lobs@gmail.com · Sala de Monitoramento: simdcedec@gmail.com · [Lattes](http://lattes.cnpq.br/9038468130657451) |
| Repositório | https://github.com/engamblobs/Autosimd-Focos |
| Família | AutoSIMD (FOCOS, ESTIAGEM, AR, DESASTRE) |

## 2. Propósito

Gerar, em poucos segundos, um diagnóstico territorial de focos de calor pronto para apoiar o planejamento de prevenção e combate a incêndios florestais: o usuário escolhe o território e o período, e o programa produz indicadores, gráficos, mapas, rankings, relatório PDF, planilha Excel e a grade para o QGIS.

## 3. Escopo funcional

1. Três níveis de análise: **município** (qualquer UF), **Unidade de Conservação** e **Terra Indígena**.
2. Período em anos (intervalo contínuo, inclusive nas pontas).
3. Indicadores do município: focos no ano final, posição no país e no estado, participação no estado, variação anual e densidade média anual (focos/km²/ano).
4. Gráficos: top do estado, evolução anual com tendência, sazonalidade mensal.
5. Mapas: dispersão no ano final (com UCs/TIs sobrepostas), densidade em grade de 10 km, recorrência e migração trimestral.
6. Tabelas: ranking estadual, comparativo na Região de Integração (Pará), UCs/TIs no município, rankings nacionais de UC e TI.
7. Pacote .zip: PDF (município), Excel (município), GeoJSON da grade, CSVs e PNGs.

## 4. Fora do escopo

- Baixar ou atualizar automaticamente a base do BDQueimadas (é substituída pelo usuário, `docs/03`).
- Monitoramento diário/alertas em tempo real.
- Gravar histórico de análises (o pacote é montado em memória e baixado pelo navegador).

## 5. Princípios de produto e qualidade

- Funciona offline; distribuição portátil para Windows, sem instalação.
- Mesmo território e período ⇒ mesmos números, sempre (rankings sem ordem arbitrária em empates).
- A regra fica em `core/`, testável sem abrir a interface; a interface só mostra.
- Base ausente ou com coluna faltando ⇒ mensagem clara, nunca resultado pela metade.

## 6. Decisões técnicas

Python + Streamlit, pandas/pyarrow (Parquet), shapely + pyproj (geometria e área geodésica), matplotlib (figuras), reportlab (PDF), openpyxl (Excel). Mesma organização do AutoSIMD-DESASTRE (`core/`, `referencia/`, `amostras/`, `testes/`, `docs/`, `empacotamento/`).

## 7. Critério de aceite desta reorganização (v0.11)

Com a base completa, os indicadores do município são iguais aos do v0.10 (`app.py` de arquivo único), exceto as diferenças registradas em `docs/09` (focos sem município fora do ranking nacional, empate = mesma posição, Região de Integração só no Pará). Conferido em 21/10/2026 com São Félix do Xingu (2002–2025), Altamira (2020–2024), Bonito-BA (2010–2025) e Oiapoque-AP (2024).
