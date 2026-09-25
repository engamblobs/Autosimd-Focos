# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AutoSIMD-FOCOS: a Streamlit app that produces territorial diagnostics of heat spots / fire foci (INPE BDQueimadas data) for the Defesa Civil do Pará (CEDEC/PA – SIMD). The user picks a target (State/Municipality, Conservation Unit – UC, or Indigenous Land – TI) and a year range, and the app generates charts, maps, rankings, a PDF report, an Excel sheet, a 10x10 km QGIS grid (.geojson) and a ZIP bundle of everything. All code, identifiers, UI text and comments are in Brazilian Portuguese; keep that convention.

Git repo: https://github.com/engamblobs/Autosimd-Focos (branch `main`, commits as engamblobs <engamb.lobs@gmail.com>; `gh` is authenticated). Each released version gets a tag `v<APP_VERSAO>` and a GitHub Release with the Windows `.zip` attached (`gh release create`). `.gitignore` excludes `BASES_GEOJSON/`, `dist/` and `python/`. No test suite or linter exists.

## Running

Always use the project venv interpreter: `/home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14`.

```bash
/home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 -m streamlit run app.py   # dev (Linux)
/home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 run_app.py                # headless on :8501 + opens browser
```

## Windows package (the deployment target)

The app is distributed as a portable Windows folder (no install, offline). Build it from Linux:

```bash
/home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 empacotamento/empacotar_windows.py [--sem-zip]
```

This creates `dist/AutoSIMD-FOCOS_v<APP_VERSAO>/` (+ `.zip`): the embeddable Windows Python from `python/python-3.13.15-embed-amd64/` with `Lib\site-packages` added to its `._pth`, win_amd64 wheels pinned in `empacotamento/requirements-windows.txt` (keep them in sync with the dev venv versions), `app.py`, logos + region dictionary from `core/`, only the bases the app reads (see `BASES_USADAS`), `empacotamento/iniciar.py` (finds a free port from 8501, starts Streamlit, opens the browser when `/_stcore/health` answers; reuses an instance already on 8501), the `.bat` launcher and `LEIA-ME.txt` (both written with CRLF), and `empacotamento/config.toml` as `.streamlit/config.toml`. `enxugar_site_packages` strips tests, headers/sources, Jupyter `share/`/`etc/`, `bin/` and pyarrow Flight/Substrait (~100 MB) — if a new dependency breaks on Windows, check this list first. On first run `iniciar.py` creates a Desktop shortcut (`AutoSIMD-FOCOS.lnk`, icon `core/logos/AutoSIMD-FOCOS.ico`) via PowerShell/WScript.Shell and records the package path in `.atalho_criado`; Wine's PowerShell is a stub, so the shortcut can only be verified on real Windows. It can be smoke-tested under Wine: `WINEDEBUG=-all wine dist/<pkg>/python/python.exe ...`.

All paths in `app.py` are relative to its own folder (`BASE_DIR`): data in `BASES_GEOJSON/` (foci Parquet, `mun-brGEOJSON/NM_UF_<Estado>.geojson`, `tiGEOJSON/TI-BR.geojson`, `ucGEOJSON/UC-BR.geojson`), logos and region dictionary in `core/`. Never reintroduce absolute paths — the same file runs in dev and in the Windows package.

## Versioning and legacy copies

The version lives in `APP_VERSAO` / `APP_VERSAO_DATA` in `app.py` (shown in the page title, the About menu and the sidebar "Sobre o Sistema & Desenvolvedor" expander, and used to name the Windows package). When saving a new version, bump both constants first, then copy `app.py` to `historico/app_<APP_VERSAO>_<YYYYMMDD>.py`. `historico/` files are frozen snapshots — don't edit them; `app` (no extension) is an older standalone copy. Root `app.py` is the only live version (the old `AutoSIMD-v2/` and `data/` folders were deleted; the v2 app survives as `historico/app_AutoSIMD-v2_20260913.py`).

## Architecture of `app.py`

Single-file Streamlit script (~2000 lines), top-to-bottom execution:

1. **Config/paths + region lookup** — `core/dicionario_municipios-regioes.py` is loaded dynamically via `importlib` (hyphenated filename, can't be imported normally) to get `MAPA_MUNICIPIO_REGIAO` (Pará "Regiões de Integração"). Lookups are accent-insensitive via `remover_acentos`.
2. **Data loading** — `carregar_focos_consolidados` (`@st.cache_data`) reads `bdqueimadas_consolidado.parquet` with columns `lon, lat, ano, mes, data, NM_MUN, NM_UF, SIGLA_UF, UC, TI`; text columns are normalized to stripped UPPERCASE, so filter values must be uppercased too. Target geometries come from GeoJSON (`carregar_geometria_alvo`, matched across several possible property keys). The KML helpers (`find_and_parse_kml`, `draw_kml_boundary`) are dead code — KMLs are not shipped. Municipal GeoJSONs are per-state files `NM_UF_<Estado>.geojson`.
3. **Figure generators** (matplotlib) — `generate_p1_charts_figures`, `generate_seasonality_chart`, `generate_map_figures`, `generate_trimester_recurrence_map`, plus `generate_qgis_grid_geojson`.
4. **PDF report** (reportlab platypus) — `generate_pdf_report` composes the `_build_pdf_*` helpers; `NumberedCanvas` adds page numbering.
5. **Export** — `gerar_pacote_completo` / `exportar_pacote_analise` build the ZIP; `disparar_download_automatico` triggers a browser download via injected HTML/JS.
6. **Sidebar UI + processing** — sidebar sets `tipo_analise`, target, year range; on the "Processar" button there are two branches: UC/TI analysis (`btn_processar and tipo_analise != "Estado / Município"`) and the municipal analysis (`if btn_processar:`).

## Supporting scripts

- `ferramentas/atualizar_area_protegida_focos.py` — rewrites the `TI` or `UC` column of the foci Parquet by point-in-polygon against a GeoJSON (label `NOME (CÓDIGO)` uppercased, `NONE` when outside, smallest polygon wins on overlaps; backs up the Parquet to `BASES_GEOJSON/backup/` first). TI was rebuilt from FUNAI's `tiGEOJSON/TI-BR.geojson` (`terrai_nom`/`terrai_cod`, all Brazil) and UC from CNUC's `ucGEOJSON/UC-BR.geojson` (`NOME_UC1`/`ID_UC0`, all Brazil). `rotulo_area_protegida` in `app.py` rebuilds the same `NOME (CÓDIGO)` label to find a polygon — keep both in sync if the source fields change.
- `AUTO.py` — one-off streaming converter (ijson → pyarrow) from the huge consolidated BDQueimadas GeoJSON to the Parquet the app reads. Defines the Parquet schema; keep it in sync with the columns `app.py` expects. Re-running it would revert the TI/UC columns to the old source data — rerun the `ferramentas/` script afterwards.
- `core/baixarregioes.py` — generates the municipality→region dictionary from the region lists (source text also in `regioesdeintegracao`).
- `core/analytics.py`, `core/viz.py` — standalone analytics/Plotly modules, **not imported by `app.py`**. `core/loader.py` and `core/exporter.py` are empty placeholders. `core/teste-santarem.py`, `core/testes_pdf.py` are experiments.
- `PAINELFOGO/main.py` — standalone experiment querying the SIPAM "Painel do Fogo" API.
- `config.py` — project metadata constants; not used by `app.py`.
