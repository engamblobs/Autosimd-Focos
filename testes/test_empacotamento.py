# -*- coding: utf-8 -*-
"""Pacote Windows (sem baixar nada: monta a aplicação e as bases da amostra, sem o Python portátil)."""

import importlib.metadata
import importlib.util
import re

import pytest

from core import config
from core.config import AMOSTRAS_BASES, RAIZ

EMPACOTAMENTO = RAIZ / "empacotamento"


def carregar(nome):
    spec = importlib.util.spec_from_file_location(nome, EMPACOTAMENTO / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def empacotar():
    return carregar("empacotar_windows")


@pytest.fixture(scope="module")
def pacote(empacotar, tmp_path_factory):
    destino = tmp_path_factory.mktemp("pacote") / "AutoSIMD-FOCOS_v0"
    empacotar.montar_app(destino, *empacotar.ler_versao())
    empacotar.montar_bases(destino, AMOSTRAS_BASES)
    return destino


def test_versao_vem_do_config(empacotar):
    assert empacotar.ler_versao() == (config.APP_VERSAO, config.APP_VERSAO_DATA)


def test_conteudo_do_pacote(pacote):
    for relativo in [
        "app.py", "iniciar.py", "Iniciar_AutoSIMD-FOCOS.bat", "LEIA-ME.txt",
        ".streamlit/config.toml", "static/autosimd_focos.txt",
        "core/config.py", "core/diagnostico.py", "core/mapas.py", "core/relatorio_pdf.py", "core/produto.py",
        "core/kernel.py", "core/fundo_satelite.py", "core/estatisticas.py", "core/atualizacao.py",
        "referencia/municipios_pa.csv", "referencia/municipios_br.csv", "referencia/logos/AutoSIMD-FOCOS.ico",
        "referencia/logos/AUTOSIMD-FOCOS.png", "referencia/logos/CBM-CEDEC.png",
        "BASES_GEOJSON/bdqueimadas_consolidado.parquet", "BASES_GEOJSON/mun-brGEOJSON/NM_UF_Pará.geojson",
        "BASES_GEOJSON/ucGEOJSON/UC-BR.geojson", "BASES_GEOJSON/tiGEOJSON/TI-BR.geojson",
    ]:
        assert (pacote / relativo).is_file(), relativo
    # o que não deve ir para o pacote
    assert not list(pacote.rglob("__pycache__"))
    for pasta in ("testes", "amostras", "docs", "ferramentas"):
        assert not (pacote / pasta).exists(), pasta


def test_bases_ausentes_interrompem(empacotar, tmp_path):
    with pytest.raises(SystemExit, match="base não encontrada"):
        empacotar.montar_bases(tmp_path / "pacote", tmp_path / "sem_bases")


def test_bat_e_leia_me_em_crlf(pacote):
    for nome in ("Iniciar_AutoSIMD-FOCOS.bat", "LEIA-ME.txt"):
        bruto = (pacote / nome).read_bytes()
        assert b"\r\n" in bruto and b"\n" not in bruto.replace(b"\r\n", b""), nome
    leia_me = (pacote / "LEIA-ME.txt").read_text(encoding="utf-8")
    assert leia_me.startswith(f"AutoSIMD-FOCOS v{config.APP_VERSAO} ({config.APP_VERSAO_DATA})")


def test_bat_confere_os_arquivos_que_existem_no_pacote(pacote):
    bat = (pacote / "Iniciar_AutoSIMD-FOCOS.bat").read_text(encoding="utf-8")
    verificados = re.findall(r'if not exist "%~dp0([^"]+)"', bat)
    assert "python\\python.exe" in verificados
    for relativo in verificados:
        if relativo.startswith("python\\"):
            continue                    # o Python portátil não é montado neste teste (exige download)
        assert (pacote / relativo.replace("\\", "/")).exists(), relativo


def test_identificacao_do_servidor(pacote):
    iniciar = carregar("iniciar")
    assert (pacote / "static" / "autosimd_focos.txt").read_text(encoding="utf-8").strip() == iniciar.NOME
    assert "enableStaticServing = true" in (pacote / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert (iniciar.PORTA_PADRAO, iniciar.PORTA_PADRAO + iniciar.QTD_PORTAS - 1) == (
        config.PORTA_INICIAL, config.PORTA_FINAL)
    assert iniciar.ICONE.replace("\\", "/").endswith("referencia/logos/AutoSIMD-FOCOS.ico")


def test_versoes_do_windows_iguais_as_do_desenvolvimento():
    """Os wheels do pacote têm as mesmas versões testadas no ambiente de desenvolvimento."""
    linhas = (EMPACOTAMENTO / "requirements-windows.txt").read_text(encoding="utf-8").splitlines()
    fixadas = dict(l.split("==") for l in linhas if "==" in l and not l.startswith("#"))
    assert {"streamlit", "altair", "pandas", "pyarrow", "matplotlib", "reportlab", "shapely", "pyproj", "openpyxl"} <= set(fixadas)
    for pacote_py, versao in fixadas.items():
        assert importlib.metadata.version(pacote_py) == versao, pacote_py


def test_controle_da_atualizacao_vai_no_pacote_se_existir(empacotar, tmp_path):
    import shutil
    origem = tmp_path / "bases"
    shutil.copytree(AMOSTRAS_BASES, origem)
    (origem / "atualizacao_inpe.json").write_text("{}", encoding="utf-8")
    (origem / "bdqueimadas_consolidado.anterior.parquet").write_bytes(b"x")     # cópia de segurança: não vai
    empacotar.montar_bases(tmp_path / "pacote", origem)
    assert (tmp_path / "pacote" / "BASES_GEOJSON" / "atualizacao_inpe.json").exists()
    assert not (tmp_path / "pacote" / "BASES_GEOJSON" / "bdqueimadas_consolidado.anterior.parquet").exists()
