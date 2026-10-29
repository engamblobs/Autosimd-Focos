"""
Monta o pacote Windows portátil do AutoSIMD-FOCOS em dist/AutoSIMD-FOCOS_v<versão>/
e o compacta em dist/AutoSIMD-FOCOS_v<versão>.zip (mesmo padrão do AutoSIMD-DESASTRE).

Uso (no Linux, com o env do projeto):
    /home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 empacotamento/empacotar_windows.py [--sem-zip]
    /home/lobs/.local/share/venvs/fortracc2-env/bin/python3.14 empacotamento/empacotar_windows.py --travar

Integridade: o zip do Python portátil é conferido pelo SHA256 publicado pelo python.org e os
wheels são instalados com --require-hashes a partir de requirements-windows.lock (versões e
SHA256 de todas as dependências, inclusive as indiretas). Mudou requirements-windows.txt?
Rode --travar para gerar a trava de novo.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PASTA_EMPACOTAMENTO = Path(__file__).resolve().parent
PROJETO = PASTA_EMPACOTAMENTO.parent
NOME = "AutoSIMD-FOCOS"
PYTHON_EMBED_VERSAO = "3.13.15"
PYTHON_EMBED_ZIP = PROJETO / "python" / f"python-{PYTHON_EMBED_VERSAO}-embed-amd64.zip"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_EMBED_VERSAO}/{PYTHON_EMBED_ZIP.name}"
# SHA256 publicado pelo python.org para esse zip; o empacotamento para se o arquivo não conferir
PYTHON_EMBED_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
REQUISITOS = PASTA_EMPACOTAMENTO / "requirements-windows.txt"
TRAVA = PASTA_EMPACOTAMENTO / "requirements-windows.lock"
PLATAFORMA = ["--only-binary=:all:", "--platform", "win_amd64",
              "--python-version", PYTHON_EMBED_VERSAO.rsplit(".", 1)[0], "--implementation", "cp"]
# Fora do resolvedor do pip (vão na versão fixada): o streamlit 1.61.1 declara pillow<13 só por
# precaução — o 1.66.1 apenas retirou o limite (streamlit#17589) — e o pillow 13.0.0 corrige falhas críticas
SEM_RESOLVER = {"pillow"}
DIST = PROJETO / "dist"
BASES_ORIGEM = PROJETO / "BASES_GEOJSON"

# O que vai para o pacote (relativo ao projeto). Não vão: testes, amostras, docs, ferramentas.
ARQUIVOS_APP = ["app.py"]
PASTAS_APP = ["core", "referencia"]
IGNORAR = shutil.ignore_patterns("__pycache__", "*.pyc", ".~lock.*#", "*~")
# Somente as bases que o programa lê (core/config.py)
BASES_USADAS = [
    "bdqueimadas_consolidado.parquet",
    "mun-brGEOJSON/NM_UF_*.geojson",
    "tiGEOJSON/TI-BR.geojson",
    "ucGEOJSON/UC-BR.geojson",
]
# Vão se existirem: controle da atualização pelo INPE (dias provisórios são baixados de novo no Windows)
BASES_OPCIONAIS = ["atualizacao_inpe.json"]


def ler_versao():
    codigo = (PROJETO / "core" / "config.py").read_text(encoding="utf-8")
    versao = re.search(r'^APP_VERSAO = "([^"]+)"', codigo, re.M).group(1)
    data = re.search(r'^APP_VERSAO_DATA = "([^"]+)"', codigo, re.M).group(1)
    return versao, data


def copiar(origem, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)


def escrever_crlf(texto, destino):
    destino.write_bytes(texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def obter_python_embed():
    """Zip oficial do Python portátil em python/ (cache local, fora do git), conferido pelo SHA256."""
    if not PYTHON_EMBED_ZIP.exists():
        print(f"→ Baixando Python portátil {PYTHON_EMBED_VERSAO} de python.org")
        PYTHON_EMBED_ZIP.parent.mkdir(parents=True, exist_ok=True)
        parcial = PYTHON_EMBED_ZIP.with_name(PYTHON_EMBED_ZIP.name + ".parcial")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, parcial)
        if sha256(parcial) != PYTHON_EMBED_SHA256:
            parcial.unlink()
            sys.exit("ERRO: o Python portátil baixado não confere com o SHA256 do python.org (corrompido ou adulterado)")
        parcial.replace(PYTHON_EMBED_ZIP)
    elif sha256(PYTHON_EMBED_ZIP) != PYTHON_EMBED_SHA256:
        sys.exit(f"ERRO: {PYTHON_EMBED_ZIP} não confere com o SHA256 do python.org; apague-o para baixar de novo")


def nome_canonico(nome):
    return re.sub(r"[-_.]+", "-", nome).lower()


def ler_fixadas(caminho):
    """{nome canônico: versão} das linhas "pacote==versão" (ignora comentários e --hash)."""
    fixadas = {}
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        if m := re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s;#]+)", linha):
            fixadas[nome_canonico(m.group(1))] = m.group(2)
    return fixadas


def conferir_trava():
    """Toda versão de requirements-windows.txt precisa estar igual na trava."""
    if not TRAVA.exists():
        sys.exit(f"ERRO: {TRAVA.name} não existe; gere com: empacotar_windows.py --travar")
    travadas = ler_fixadas(TRAVA)
    diferentes = [f"{n}=={v}" for n, v in ler_fixadas(REQUISITOS).items() if travadas.get(n) != v]
    if diferentes:
        sys.exit(f"ERRO: {TRAVA.name} desatualizado ({', '.join(diferentes)}); gere de novo com --travar")


def resolver(linhas, sem_dependencias=False):
    """{nome canônico: (nome, versão, sha256)} dos wheels win_amd64 que o pip escolheria (sem instalar)."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada, relatorio = Path(tmp) / "requisitos.txt", Path(tmp) / "relatorio.json"
        entrada.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
             "--disable-pip-version-check", *PLATAFORMA, "--target", str(Path(tmp) / "alvo"),
             *(["--no-deps"] if sem_dependencias else []), "--report", str(relatorio), "-r", str(entrada)],
            check=True,
        )
        itens = json.loads(relatorio.read_text(encoding="utf-8"))["install"]
    return {nome_canonico(i["metadata"]["name"]): (i["metadata"]["name"], i["metadata"]["version"],
                                                    i["download_info"]["archive_info"]["hashes"]["sha256"])
            for i in itens}


def travar_dependencias():
    """Gera requirements-windows.lock: versão e SHA256 de cada wheel, inclusive das dependências indiretas."""
    linhas = [l.strip() for l in REQUISITOS.read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.lstrip().startswith("#")]
    fora = [l for l in linhas if nome_canonico(re.split(r"[=<>!~; ]", l)[0]) in SEM_RESOLVER]
    pacotes = {n: p for n, p in resolver([l for l in linhas if l not in fora]).items() if n not in SEM_RESOLVER}
    if fora:
        pacotes |= resolver(fora, sem_dependencias=True)
    TRAVA.write_text(
        "# Gerado por empacotamento/empacotar_windows.py --travar; não edite à mão.\n"
        f"# Wheels win_amd64 (CPython {PYTHON_EMBED_VERSAO.rsplit('.', 1)[0]}) de requirements-windows.txt e de todas "
        "as suas dependências, com o SHA256 de cada arquivo.\n"
        + "".join(f"{nome}=={versao} --hash=sha256:{hash_}\n"
                  for nome, versao, hash_ in sorted(pacotes.values(), key=lambda p: nome_canonico(p[0]))),
        encoding="utf-8",
    )
    print(f"✓ {TRAVA.name}: {len(pacotes)} pacotes com SHA256")


def montar_python(destino):
    obter_python_embed()
    print("→ Python portátil")
    with zipfile.ZipFile(PYTHON_EMBED_ZIP) as zf:
        zf.extractall(destino)
    pth = next(destino.glob("python3*._pth"))
    linhas = [
        "import site" if l.strip() == "#import site" else l
        for l in pth.read_text().splitlines()
        if l.strip()
    ]
    if "Lib\\site-packages" not in linhas:
        linhas.insert(linhas.index(".") + 1, "Lib\\site-packages")
    # a pasta do programa precisa estar no caminho para "import core" funcionar com o Python portátil
    if ".." not in linhas:
        linhas.insert(linhas.index(".") + 1, "..")
    pth.write_text("\r\n".join(linhas) + "\r\n")

    print(f"→ Pacotes Python para Windows (wheels win_amd64 conferidos pelo SHA256 de {TRAVA.name})")
    conferir_trava()
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", *PLATAFORMA,
            "--target", str(destino / "Lib" / "site-packages"),
            "--no-deps", "--require-hashes",
            "--no-compile",
            "--disable-pip-version-check",
            "-r", str(TRAVA),
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
    print("→ Aplicação, tabelas de referência e arquivos de inicialização")
    for nome in ARQUIVOS_APP:
        copiar(PROJETO / nome, destino / nome)
    for nome in PASTAS_APP:
        shutil.copytree(PROJETO / nome, destino / nome, ignore=IGNORAR)
    copiar(PASTA_EMPACOTAMENTO / "iniciar.py", destino / "iniciar.py")
    copiar(PASTA_EMPACOTAMENTO / "config.toml", destino / ".streamlit" / "config.toml")
    copiar(PASTA_EMPACOTAMENTO / "static" / "autosimd_focos.txt", destino / "static" / "autosimd_focos.txt")
    escrever_crlf(
        (PASTA_EMPACOTAMENTO / f"Iniciar_{NOME}.bat").read_text(encoding="utf-8"),
        destino / f"Iniciar_{NOME}.bat",
    )
    escrever_crlf(
        (PASTA_EMPACOTAMENTO / "LEIA-ME.txt").read_text(encoding="utf-8").format(versao=f"v{versao}", data=data),
        destino / "LEIA-ME.txt",
    )


def montar_bases(destino, origem=BASES_ORIGEM):
    print("→ Bases de dados")
    for padrao in BASES_USADAS:
        arquivos = sorted(Path(origem).glob(padrao))
        if not arquivos:
            sys.exit(f"ERRO: base não encontrada: BASES_GEOJSON/{padrao}")
        for arq in arquivos:
            copiar(arq, destino / "BASES_GEOJSON" / arq.relative_to(origem))
    for nome in BASES_OPCIONAIS:
        if (Path(origem) / nome).exists():
            copiar(Path(origem) / nome, destino / "BASES_GEOJSON" / nome)


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
    parser.add_argument("--travar", action="store_true",
                        help=f"gera {TRAVA.name} (versões e SHA256 dos wheels) e sai")
    args = parser.parse_args()
    if args.travar:
        travar_dependencias()
        return

    versao, data = ler_versao()
    destino = DIST / f"{NOME}_v{versao}"
    print(f"Empacotando {NOME} v{versao} ({data}) em {destino}")
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)

    montar_python(destino / "python")
    montar_app(destino, versao, data)
    montar_bases(destino)
    print(f"✓ Pasta pronta: {destino} ({tamanho_mb(destino):,.0f} MB)")

    if not args.sem_zip:
        arquivo_zip = compactar(destino)
        hash_zip = sha256(arquivo_zip)
        arquivo_zip.with_name(arquivo_zip.name + ".sha256").write_text(f"{hash_zip}  {arquivo_zip.name}\n",
                                                                     encoding="utf-8")
        print(f"✓ Zip pronto: {arquivo_zip} ({tamanho_mb(arquivo_zip):,.0f} MB)")
        print(f"  SHA256: {hash_zip}")
        print(f"  (também em {arquivo_zip.name}.sha256; publique junto com o link de download)")


if __name__ == "__main__":
    main()
