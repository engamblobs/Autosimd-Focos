"""
Inicializador do AutoSIMD-FOCOS no Windows (Python portátil incluído no pacote).
Sobe o servidor Streamlit local e abre o navegador quando ele estiver pronto.
"""

import base64
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

PASTA = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(PASTA, "app.py")
PORTA_PADRAO = 8501
TEMPO_MAX_INICIO_S = 180
BAT = os.path.join(PASTA, "Iniciar_AutoSIMD-FOCOS.bat")
ICONE = os.path.join(PASTA, "core", "logos", "AutoSIMD-FOCOS.ico")
MARCADOR_ATALHO = os.path.join(PASTA, ".atalho_criado")


def criar_atalho_area_de_trabalho():
    """Cria o atalho com ícone na Área de Trabalho na 1ª execução ou se a pasta mudou de lugar."""
    if os.name != "nt":
        return
    try:
        with open(MARCADOR_ATALHO, encoding="utf-8") as f:
            if f.read().strip() == PASTA:
                return
    except OSError:
        pass

    def ps(texto):  # literal PowerShell entre aspas simples
        return "'" + texto.replace("'", "''") + "'"

    script = (
        "$d = [Environment]::GetFolderPath('Desktop');"
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'AutoSIMD-FOCOS.lnk'));"
        f"$s.TargetPath = {ps(BAT)};"
        f"$s.WorkingDirectory = {ps(PASTA)};"
        f"$s.IconLocation = {ps(ICONE + ',0')};"
        "$s.Description = 'AutoSIMD-FOCOS - Diagnóstico Territorial de Focos de Calor';"
        "$s.Save();"
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "Write-Output $s.FullName"
    )
    try:
        resultado = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
            ],
            capture_output=True,
            timeout=30,
        )
        caminho_atalho = resultado.stdout.decode("utf-8", "replace").strip()
        if resultado.returncode == 0 and caminho_atalho and os.path.exists(caminho_atalho):
            with open(MARCADOR_ATALHO, "w", encoding="utf-8") as f:
                f.write(PASTA)
            print("Atalho 'AutoSIMD-FOCOS' criado na Área de Trabalho.")
    except (OSError, subprocess.SubprocessError):
        pass  # o atalho é conveniência; o sistema abre normalmente sem ele


def app_ativo(porta):
    try:
        with urllib.request.urlopen(
            f"http://localhost:{porta}/_stcore/health", timeout=1
        ) as resposta:
            return resposta.status == 200
    except OSError:
        return False


def porta_livre(porta):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


def main():
    criar_atalho_area_de_trabalho()

    # Já aberto em outra janela: só reabre o navegador
    if app_ativo(PORTA_PADRAO):
        print("O AutoSIMD-FOCOS já está em execução. Abrindo o navegador...")
        webbrowser.open(f"http://localhost:{PORTA_PADRAO}")
        time.sleep(3)
        return 0

    porta = next(
        (p for p in range(PORTA_PADRAO, PORTA_PADRAO + 50) if porta_livre(p)), None
    )
    if porta is None:
        print("ERRO: nenhuma porta livre entre 8501 e 8550.")
        return 1

    url = f"http://localhost:{porta}"
    print("Iniciando o servidor local, aguarde (a primeira abertura pode levar até 1 minuto)...")
    processo = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP, f"--server.port={porta}"],
        cwd=PASTA,
    )

    inicio = time.time()
    while not app_ativo(porta):
        if processo.poll() is not None:
            print("ERRO: o servidor foi encerrado durante a inicialização.")
            return processo.returncode or 1
        if time.time() - inicio > TEMPO_MAX_INICIO_S:
            print("ERRO: o servidor não respondeu a tempo.")
            processo.terminate()
            return 1
        time.sleep(1)

    webbrowser.open(url)
    print()
    print("=" * 68)
    print(f"  AutoSIMD-FOCOS aberto no navegador: {url}")
    print("  Para ENCERRAR o sistema, feche esta janela.")
    print("=" * 68)

    try:
        return processo.wait()
    except KeyboardInterrupt:
        processo.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
