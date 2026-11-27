# CLAUDE.md — AutoSIMD-FOCOS

Este arquivo é lido automaticamente pelo Claude Code ao abrir o projeto. Ele é o "prompt oficial" do sistema: define o papel, as regras obrigatórias e o formato de resposta. Os detalhes ficam em `docs/`.

## Papel

Você atua como desenvolvedor(a) sênior do **AutoSIMD-FOCOS**: o usuário escolhe um território (município de qualquer UF, Unidade de Conservação ou Terra Indígena) e um intervalo de anos, e o programa gera o **diagnóstico territorial de focos de calor** (BDQueimadas/INPE) — indicadores, gráficos, mapas, rankings, PDF, Excel, grade 10 km para o QGIS e um .zip com tudo — para a Defesa Civil do Pará (CEDEC/PA – SIMD). Antes de alterar código, leia este arquivo e os documentos em `docs/` relacionados ao pedido.

## Orientações do usuário — `docs/ORIENTAÇÕES.txt`

Quando o usuário mandar "ler as orientações" (ou equivalente), leia **só o topo** do arquivo, até a linha `################ HISTÓRICO`:

```bash
sed '/^################ HISTÓRICO/q' "docs/ORIENTAÇÕES.txt"
```

Trate esse texto como se o usuário o tivesse escrito no chat. Ao terminar, mova o texto atendido para logo abaixo da linha divisória (a entrada mais recente fica em cima), com `=== DD/MM/AAAA HH:MM — título`, o pedido e o que foi feito ou o que ficou pendente. O topo fica vazio para as próximas orientações. Não leia o histórico inteiro: só consulte trechos dele com `grep` se precisar.

**Perguntas ao usuário** (pedido de 25/11/2026): continuam em `docs/09` (com a coluna de resposta, que o usuário também preenche lá), **e vão também** na entrada do histórico do `ORIENTAÇÕES.txt`, numeradas como em `docs/09` (P43, P44…), para ele responder sem abrir o Obsidian. A resposta pode chegar por qualquer um dos dois: confira a coluna "Resposta" de `docs/09` antes de editar a tabela (o Obsidian realinha as colunas — edite por regex, sem supor espaçamento).

**Ordem da entrada do histórico** (pedido de 27/11/2026): as PERGUNTAS ficam **no início**, logo abaixo da linha `=== DD/MM/AAAA HH:MM — título` e antes do PEDIDO; depois vêm PEDIDO e FEITO.

## Leitura obrigatória por tipo de tarefa

| Tarefa | Ler antes |
|---|---|
| Qualquer tarefa | `docs/01_Definicao_Conceitual.md`, `docs/09_Pendencias_e_Decisoes.md` |
| Bases de dados, atualização pelo INPE, colunas UC/TI | `docs/03_Fontes_de_Dados_e_Importacao.md` (§5 = atualização), `docs/06_Dicionario_de_Dados.md` |
| Nowcast (cenário atual) | `docs/07_Regras_de_Negocio.md` §9, `docs/10_Produtos.md` §6 |
| Cenário atual do estado (24 h / semana, PDF do cenário) | `docs/07_Regras_de_Negocio.md` §11, `docs/10_Produtos.md` §8 |
| Anomalias de focos (quantidade, localização, combinada, significância) | `docs/07_Regras_de_Negocio.md` §12, `docs/10_Produtos.md` §3 |
| Vulnerabilidade de localidades, eventos do Painel do Fogo, vento, PM2,5, Sentinel-2 SWIR | `docs/07_Regras_de_Negocio.md` §13, `docs/03_Fontes_de_Dados_e_Importacao.md` §7–§8, `docs/10_Produtos.md` §9 |
| Rankings, regiões, mapas de kernel, grade | `docs/07_Regras_de_Negocio.md` §3–§5 |
| Colunas, campos, estruturas em memória | `docs/05_Estrutura_de_Dados.md`, `docs/06_Dicionario_de_Dados.md` |
| Indicadores, rankings, grade, áreas protegidas, Regiões de Integração | `docs/07_Regras_de_Negocio.md` |
| PDF, mapas, gráficos, pacote .zip | `docs/10_Produtos.md` |
| Estatísticas do município no modelo INPE | `docs/07_Regras_de_Negocio.md` §8, `docs/10_Produtos.md` §5 |
| Telas | `docs/02_Mapa_de_Modulos_e_Telas.md` |
| Estrutura de pastas e código | `docs/04_Arquitetura_e_Organizacao_de_Arquivos.md` |
| Planejar próximo passo | `docs/08_Roadmap_e_Incrementos.md` |

## Stack e convenções (mesmas do AutoSIMD-DESASTRE e AutoSIMD-ESTIAGEM)

- Python + Streamlit; bases em Parquet e GeoJSON (sem banco próprio); distribuição como pasta portátil para Windows (sem instalação), empacotada a partir do Linux.
- A base de focos se atualiza com os CSV do INPE (`core/atualizacao.py`) **em segundo plano** (thread `AtualizadorFocos`, modelo do AutoSIMD-HIDRO): ao abrir e, com o toggle Nowcast, a cada 4 h. Nunca bloquear a abertura do programa com download. Linha de comando: `python ferramentas/atualizar_base_inpe.py [--pasta PASTA] [--sem-internet]`. Testes nunca acessam a internet (`AUTOSIMD_FOCOS_ATUALIZAR=0` no `conftest.py`; servidor simulado com `amostras/inpe`).
- Interpretador de desenvolvimento: `/home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14`.
- Rodar: `python run_app.py` (porta 8521–8570) ou `python -m streamlit run app.py`. Testes: `python -m pytest` (inclui a interface via `streamlit.testing.v1.AppTest`).
- `app.py` só tem telas e lê os caminhos de `core.config` no momento do uso. Pasta das bases trocável por `AUTOSIMD_FOCOS_BASES`; `testes/conftest.py` aponta para `amostras/bases`.
- Código, nomes, textos de tela e comentários em **português do Brasil**.
- Desenvolvedor: **Bruno Lobão da Silva** (dados em `core/config.py` → `DESENVOLVEDOR_*`, mesmos do AutoSIMD-DESASTRE/HIDRO).
- Git: branch `main`, commits como `engamblobs <engamb.lobs@gmail.com>`. **Só fazer commit quando o usuário pedir.** Repositório do projeto: https://github.com/engamblobs/Autosimd-Focos (esta pasta ainda não tem remoto — ver P1 em `docs/09`). Cada versão publicada recebe a tag `v<APP_VERSAO>` e uma Release com o `.zip` do Windows (`gh release create`).
- **Notas de versão no GitHub** (padrão pedido em 27/11/2026): cada novidade visual da Release vem com imagem. Mudança em algo que já existia = print do **antes e do depois** lado a lado; se ajudar, desenhe setas, caixas e textos sobre a imagem. Capture as telas em 1920×1080 com `ferramentas/capturar_telas.py` (Firefox headless pelo WebDriver BiDi) **antes** de mudar a tela (o "antes") e depois; guarde em `docs/imagens/novidades/<versão>/` (enquanto não há número, `proxima/`) e use no texto da Release pelo endereço `https://raw.githubusercontent.com/engamblobs/Autosimd-Focos/v<versão>/docs/imagens/...` (a tag garante que a imagem não muda). A seção **Prévia** do README (`docs/imagens/previa/`) é refeita quando a tela muda.
- Escopo: Brasil inteiro para municípios, UCs e TIs; **Regiões de Integração só no Pará**.
- Bases reais em `BASES_GEOJSON/` (fora do git). Testes usam o recorte real `amostras/bases/` (gerado por `ferramentas/gerar_amostras.py`); não invente formatos.
- Versão em `core/config.py` (`APP_VERSAO`, `APP_VERSAO_DATA`): aparece no título, no "Sobre", no PDF, nos metadados e no nome do pacote.

## Pacote Windows (destino de uso)

Pasta portátil, sem instalação e offline. Montar a partir do Linux:

```bash
/home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 empacotamento/empacotar_windows.py [--sem-zip]
```

- Gera `dist/AutoSIMD-FOCOS_v<APP_VERSAO>/` e o `.zip`. Contém: Python portátil 3.13 (zip em `python/`, baixado de python.org se faltar e conferido pelo SHA256), wheels win_amd64 de `empacotamento/requirements-windows.txt` (**manter as versões iguais às do ambiente de desenvolvimento** — há teste para isso), `app.py`, `core/`, `referencia/`, só as bases que o programa lê (`BASES_USADAS`), `iniciar.py`, `.streamlit/config.toml`, `static/autosimd_focos.txt`, `.bat` e `LEIA-ME.txt` (ambos em CRLF). Não vão: testes, amostras, docs, ferramentas.
- **Integridade (23/10/2026):** o zip do Python portátil fica em `python/` e é conferido pelo SHA256 do python.org (`PYTHON_EMBED_SHA256`); os wheels são instalados com `--require-hashes --no-deps` a partir de `empacotamento/requirements-windows.lock` (versão e SHA256 de **todas** as dependências, inclusive as indiretas). Mudou `requirements-windows.txt`? Rode `empacotar_windows.py --travar` (o empacotamento para se a trava estiver desatualizada; há teste). `SEM_RESOLVER` = pacotes fixados fora do resolvedor do pip: o pillow 13.0.0 (falhas críticas no 12.x), porque o streamlit 1.61.1 declara `pillow<13` só por precaução (o 1.66.1 apenas retirou o limite). O build grava `<pacote>.zip.sha256`: publique o hash junto com o link; o LEIA-ME ensina a conferir com `Get-FileHash`.
- Planilhas exportadas passam por `neutralizar_formulas` (texto que começa com `=` vira texto, não fórmula).
- O `._pth` do Python portátil recebe `Lib\site-packages` e `..` (pasta do programa, para `import core` funcionar).
- `enxugar_site_packages` remove testes, headers, Jupyter `share/`/`etc/`, `bin/` e Flight/Substrait do pyarrow (~100 MB) — se uma dependência nova quebrar no Windows, olhe essa lista primeiro.
- `iniciar.py`: portas 8521–8570 (o AutoSIMD-DESASTRE usa 8571–8620; 8501 é o padrão de outros apps Streamlit), reconhece a própria instância por `static/autosimd_focos.txt` (servido com `server.enableStaticServing`; `/_stcore/health` não distingue apps). Armadilhas do Windows que o Wine não reproduz: conectar numa porta FECHADA leva ~2 s (sondagem com timeout de 0,25 s, para na primeira livre), `localhost` tenta IPv6 antes (tudo usa `127.0.0.1`), proxy corporativo intercepta `urllib` até em 127.0.0.1 (opener com `ProxyHandler({})`). Cria o atalho `AutoSIMD-FOCOS v<APP_VERSAO>.lnk` na Área de Trabalho via PowerShell (versão lida do texto de `core/config.py`) e grava `.atalho_criado` (pasta + nome do atalho: versão nova = atalho novo).
- O `.bat` confere `python\python.exe`, `iniciar.py`, `app.py`, `core\`, `referencia\` e a base Parquet, e explica as causas comuns (aberto de dentro do .zip, extração parcial, antivírus).
- Teste de fumaça no Wine (o PowerShell do Wine é um stub; atalho só se verifica no Windows real): `WINEDEBUG=-all wine dist/<pacote>/python/python.exe ...`. Ao testar o `iniciar.py`, substitua `webbrowser.open` (senão abre o navegador do Linux).
- Pacotes antigos e backups de bases vão para `backup/` (fora do git).

## Regras obrigatórias

1. Trabalhe em incrementos pequenos e verificáveis (`docs/08`); não altere módulos fora do pedido.
2. Toda regra fica em `core/` (sem Streamlit); `app.py` só mostra. O PDF, os PNGs e a tela usam as mesmas figuras e tabelas.
3. Caminhos sempre relativos à pasta do programa (`core.config`); nunca caminhos absolutos — o mesmo código roda no Linux e no pacote Windows.
4. Base ausente ou com coluna faltando = mensagem clara; nunca resultado pela metade em silêncio.
5. Valores vazios da base (`""`, `NONE`, `NULL`, `NAN`, `N/A`) nunca entram em listas nem rankings.
6. O rótulo de UC/TI (`NOME (CÓDIGO)`) é o mesmo em `core.territorios.rotulo_area_protegida` e em `ferramentas/atualizar_area_protegida_focos.py`; mudou um, mude o outro.
7. Mudança de coluna, campo ou arquivo de saída exige atualizar `docs/05`, `docs/06` e `docs/10` no mesmo incremento.
8. Toda função de leitura, cálculo ou geração de arquivo vem com teste usando `amostras/bases`.
9. Internet só para a busca de focos novos no INPE, para a imagem de satélite dos mapas e para os dados ao vivo que o usuário liga ou pede (vento — chave Vento; eventos do Painel do Fogo, vento e PM2,5 — buscados sozinhos, em segundo plano, quando a seção Vulnerabilidade abre (e no botão "Buscar de novo"); satélite também no mapa do boletim em PDF da vulnerabilidade; mosaico SWIR — chave no mapa); sem ela (ou com resposta em formato inesperado) o programa avisa, mantém a base intacta e continua funcionando. Os testes nunca acessam a internet (`AUTOSIMD_FOCOS_ATUALIZAR=0`, `AUTOSIMD_FOCOS_SATELITE=0` e `AUTOSIMD_FOCOS_AO_VIVO=0` no `conftest.py`; respostas reais gravadas em `amostras/ao_vivo/`). No pydeck, texto literal numa propriedade vai entre aspas (`radius_units="'pixels'"`): sem elas vira expressão `@@=` e o mapa inteiro fica cinza.
10. Feche as figuras do matplotlib depois de usadas (`produto.fechar_figuras`).
11. Município, UC e TI de cada foco = cruzamento do ponto com os polígonos, para tudo (P3, P13). O cruzamento é gravado nas colunas da base quando o foco entra (só AQUA_M-T); `test_atribuicao_reproduz_a_base` e `ferramentas/verificar_base.py` garantem que as colunas e o cruzamento são iguais. Não reintroduzir filtros pelo nome do município do INPE.

## Formato da resposta de desenvolvimento

Informe: **objetivo**, **arquivos alterados**, **decisões e riscos**, **como testar localmente** e **próximos passos**.

Se houver lacuna de regra de negócio que afete **o que é contado como foco de um território**, **como um indicador ou ranking é calculado** ou **a que área protegida um foco pertence**, **pare e apresente opções** antes de implementar. Registre a decisão em `docs/09_Pendencias_e_Decisoes.md`.
