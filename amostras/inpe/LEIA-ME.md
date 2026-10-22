# Amostras dos arquivos de focos do INPE (testes da atualização da base)

Recortes reais de `focos_mensal_br_202512.csv` e `focos_diario_br_20261019.csv`/`20261020.csv`
(https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/), com focos de todos os satélites
perto dos municípios de `amostras/bases` e alguns longe deles. **As datas foram trocadas** para
janeiro e fevereiro de 2025 (logo depois do fim de `amostras/bases`), para simular o servidor:

| Arquivo | Simula |
|---|---|
| `focos_mensal_br_202501.csv` | mês completo, fora da janela dos arquivos diários |
| `focos_diario_br_20250201.csv`, `…20250202.csv` | dias fechados |
| `focos_diario_br_20250203.csv` | dia baixado ainda parcial (10 linhas) |
| `focos_diario_br_20250203_completo.csv` | o mesmo dia depois de fechado (servido no lugar do parcial na 2ª busca) |
| `focos_diario_br_20250204.csv` | dia novo da 2ª busca |
