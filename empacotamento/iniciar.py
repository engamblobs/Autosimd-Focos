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
# 8501 é a porta padrão de qualquer app Streamlit (ex.: outros sistemas da SIMD);
# o AutoSIMD-FOCOS usa uma faixa própria para não disputar com eles
PORTA_PADRAO = 8521
QTD_PORTAS = 50
# IPv4 fixo: com "localhost" o Windows tenta IPv6 antes e cada falha custa ~2 s
HOST = "127.0.0.1"
# Arquivo servido pelo próprio servidor (static/) para reconhecer que a porta é do AutoSIMD-FOCOS
URL_IDENTIFICACAO = "http://127.0.0.1:{porta}/app/static/autosimd_focos.txt"
IDENTIFICACAO = "AutoSIMD-FOCOS"
# Sem proxy: em redes corporativas o proxy do Windows interceptaria até 127.0.0.1
SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
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


def eh_autosimd(porta):
    """True se a porta tem um servidor do AutoSIMD-FOCOS (e não outro app Streamlit)."""
    try:
        with SEM_PROXY.open(URL_IDENTIFICACAO.format(porta=porta), timeout=2) as resposta:
            return resposta.read(64).decode("utf-8", "ignore").strip() == IDENTIFICACAO
    except (OSError, ValueError):
        return False


def porta_ocupada(porta):
    """True se algum programa já escuta na porta.

    No Windows, conectar numa porta FECHADA da própria máquina leva ~2 s até
    falhar; com timeout curto a resposta é imediata (porta ocupada aceita a
    conexão em menos de 1 ms, então não há risco de confundir).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((HOST, porta)) == 0


def main():
    sys.stdout.reconfigure(line_buffering=True)  # mensagens aparecem na hora na janela
    criar_atalho_area_de_trabalho()

    print("Verificando portas disponíveis...")
    portas = range(PORTA_PADRAO, PORTA_PADRAO + QTD_PORTAS)
    porta = None
    for p in portas:
        if not porta_ocupada(p):
            porta = p  # primeira livre; para aqui
            break
        if eh_autosimd(p):
            # Já aberto em outra janela: só reabre o navegador na porta dele
            print("O AutoSIMD-FOCOS já está em execução. Abrindo o navegador...")
            webbrowser.open(f"http://{HOST}:{p}")
            time.sleep(3)
            return 0
        print(f"  porta {p} em uso por outro programa")
    if porta is None:
        print(f"ERRO: nenhuma porta livre entre {portas[0]} e {portas[-1]}.")
        return 1

    url = f"http://{HOST}:{porta}"
    print(f"Iniciando o servidor local na porta {porta}, aguarde (a primeira abertura pode levar até 1 minuto)...")
    processo = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", APP,
            f"--server.port={porta}", f"--server.address={HOST}",
        ],
        cwd=PASTA,
    )

    inicio = time.time()
    while not (porta_ocupada(porta) and eh_autosimd(porta)):
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
