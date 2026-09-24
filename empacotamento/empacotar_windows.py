"""
Monta o pacote Windows portátil do AutoSIMD-FOCOS em dist/AutoSIMD-FOCOS_v<versão>/
e o compacta em dist/AutoSIMD-FOCOS_v<versão>.zip.

Uso (no Linux, com o env do projeto):
    /home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 empacotamento/empacotar_windows.py [--sem-zip]
"""

import argparse
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PASTA_EMPACOTAMENTO = Path(__file__).resolve().parent
PROJETO = PASTA_EMPACOTAMENTO.parent
PYTHON_EMBED_VERSAO = "3.13.15"
PYTHON_EMBED = PROJETO / "python" / f"python-{PYTHON_EMBED_VERSAO}-embed-amd64"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_EMBED_VERSAO}/"
    f"python-{PYTHON_EMBED_VERSAO}-embed-amd64.zip"
)
BASES_ORIGEM = PROJETO / "BASES_GEOJSON"
DIST = PROJETO / "dist"

# Somente as bases que o app.py usa
BASES_USADAS = [
    "bdqueimadas_consolidado.parquet",
    "mun-brGEOJSON/NM_UF_*.geojson",
    "tiGEOJSON/TI-BR.geojson",
    "ucGEOJSON/UC-BR.geojson",
]


def ler_versao():
    codigo = (PROJETO / "app.py").read_text(encoding="utf-8")
    versao = re.search(r'^APP_VERSAO = "([^"]+)"', codigo, re.M).group(1)
    data = re.search(r'^APP_VERSAO_DATA = "([^"]+)"', codigo, re.M).group(1)
    return versao, data


def versao_python_embed():
    dll = next(PYTHON_EMBED.glob("python3??.dll"))
    digitos = dll.stem.removeprefix("python")
    return f"{digitos[0]}.{digitos[1:]}"


def copiar(origem, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)


def escrever_crlf(texto, destino):
    destino.write_bytes(texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))


def baixar_python_embed():
    """Baixa o Python portátil oficial do Windows para python/ (cache local, fora do git)."""
    if PYTHON_EMBED.exists():
        return
    print(f"→ Baixando Python portátil {PYTHON_EMBED_VERSAO} de python.org")
    arquivo_zip = PYTHON_EMBED.with_name(PYTHON_EMBED.name + ".zip")
    arquivo_zip.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(PYTHON_EMBED_URL, arquivo_zip)
    with zipfile.ZipFile(arquivo_zip) as zf:
        zf.extractall(PYTHON_EMBED)
    arquivo_zip.unlink()


def montar_python(destino):
    baixar_python_embed()
    print("→ Python portátil")
    shutil.copytree(PYTHON_EMBED, destino)
    pth = next(destino.glob("python3*._pth"))
    linhas = [
        "import site" if l.strip() == "#import site" else l
        for l in pth.read_text().splitlines()
        if l.strip()
    ]
    if "Lib\\site-packages" not in linhas:
        linhas.insert(linhas.index(".") + 1, "Lib\\site-packages")
    pth.write_text("\r\n".join(linhas) + "\r\n")

    print("→ Pacotes Python para Windows (download de wheels win_amd64)")
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install",
            "--only-binary=:all:",
            "--platform", "win_amd64",
            "--python-version", versao_python_embed(),
            "--implementation", "cp",
            "--target", str(destino / "Lib" / "site-packages"),
            "--no-compile",
            "--disable-pip-version-check",
            "-r", str(PASTA_EMPACOTAMENTO / "requirements-windows.txt"),
        ],
        check=True,
    )
    enxugar_site_packages(destino / "Lib" / "site-packages")


# Itens das bibliotecas que o app não usa em execução (testes, headers para
# compilar extensões, extensões Jupyter, scripts de linha de comando e os
# módulos Flight/Substrait do pyarrow, que só servem para acesso remoto)
PASTAS_REMOVIVEIS = ["bin", "etc", "share", "pyarrow/include", "pyarrow/src", "streamlit/.agents"]
ARQUIVOS_REMOVIVEIS = [
    "pyarrow/arrow_flight.dll", "pyarrow/arrow_python_flight.dll",
    "pyarrow/_flight.cp3*-win_amd64.pyd", "pyarrow/flight.py",
    "pyarrow/arrow_substrait.dll", "pyarrow/_substrait.cp3*-win_amd64.pyd",
    "pyarrow/substrait.py",
]
EXTENSOES_REMOVIVEIS = {".lib", ".pyx", ".pxd", ".pxi", ".h", ".hpp", ".c", ".cc", ".cpp", ".pyi"}


def enxugar_site_packages(site_packages):
    antes = tamanho_mb(site_packages)
    for pasta in PASTAS_REMOVIVEIS:
        shutil.rmtree(site_packages / pasta, ignore_errors=True)
    for pasta_testes in list(site_packages.rglob("tests")):
        if pasta_testes.is_dir():
            shutil.rmtree(pasta_testes)
    for padrao in ARQUIVOS_REMOVIVEIS:
        for arq in site_packages.glob(padrao):
            arq.unlink()
    for arq in site_packages.rglob("*"):
        if arq.is_file() and arq.suffix in EXTENSOES_REMOVIVEIS:
            arq.unlink()
    print(f"  bibliotecas enxugadas: {antes:,.0f} MB → {tamanho_mb(site_packages):,.0f} MB")


def montar_app(destino, versao, data):
    print("→ Aplicação e arquivos de inicialização")
    copiar(PROJETO / "app.py", destino / "app.py")
    copiar(
        PROJETO / "core" / "dicionario_municipios-regioes.py",
        destino / "core" / "dicionario_municipios-regioes.py",
    )
    for logo in ("AUTOSIMD-FOCOS.png", "CBM-CEDEC.png", "AutoSIMD-FOCOS.ico"):
        copiar(PROJETO / "core" / "logos" / logo, destino / "core" / "logos" / logo)
    copiar(PASTA_EMPACOTAMENTO / "iniciar.py", destino / "iniciar.py")
    copiar(PASTA_EMPACOTAMENTO / "config.toml", destino / ".streamlit" / "config.toml")
    escrever_crlf(
        (PASTA_EMPACOTAMENTO / "Iniciar_AutoSIMD-FOCOS.bat").read_text(encoding="utf-8"),
        destino / "Iniciar_AutoSIMD-FOCOS.bat",
    )
    escrever_crlf(
        (PASTA_EMPACOTAMENTO / "LEIA-ME.txt")
        .read_text(encoding="utf-8")
        .format(versao=f"v{versao}", data=data),
        destino / "LEIA-ME.txt",
    )


def montar_bases(destino):
    print("→ Bases de dados")
    for padrao in BASES_USADAS:
        arquivos = sorted(BASES_ORIGEM.glob(padrao))
        if not arquivos:
            sys.exit(f"ERRO: base não encontrada: BASES_GEOJSON/{padrao}")
        for arq in arquivos:
            copiar(arq, destino / "BASES_GEOJSON" / arq.relative_to(BASES_ORIGEM))


def compactar(pasta):
    arquivo_zip = pasta.parent / f"{pasta.name}.zip"
    print(f"→ Compactando {arquivo_zip.name}")
    arquivo_zip.unlink(missing_ok=True)
    if shutil.which("7z"):
        subprocess.run(
            ["7z", "a", "-tzip", "-mx=5", "-bso0", "-bsp0", str(arquivo_zip), pasta.name],
            cwd=pasta.parent,
            check=True,
        )
    else:
        with zipfile.ZipFile(arquivo_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for arq in sorted(pasta.rglob("*")):
                zf.write(arq, arq.relative_to(pasta.parent))
    return arquivo_zip


def tamanho_mb(caminho):
    if caminho.is_file():
        return caminho.stat().st_size / 1e6
    return sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file()) / 1e6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sem-zip", action="store_true", help="não gera o .zip")
    args = parser.parse_args()

    versao, data = ler_versao()
    destino = DIST / f"AutoSIMD-FOCOS_v{versao}"
    print(f"Empacotando AutoSIMD-FOCOS v{versao} ({data}) em {destino}")
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)

    montar_python(destino / "python")
    montar_app(destino, versao, data)
    montar_bases(destino)
    print(f"✓ Pasta pronta: {destino} ({tamanho_mb(destino):,.0f} MB)")

    if not args.sem_zip:
        arquivo_zip = compactar(destino)
        print(f"✓ Zip pronto: {arquivo_zip} ({tamanho_mb(arquivo_zip):,.0f} MB)")


if __name__ == "__main__":
    main()
