# -*- coding: utf-8 -*-
"""Inicia o AutoSIMD-FOCOS sem console e abre o navegador.

Usa a primeira porta livre da faixa própria (core.config.PORTA_INICIAL–PORTA_FINAL),
para poder rodar junto com os outros AutoSIMD.

    python run_app.py
"""

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from core.config import PORTA_FINAL, PORTA_INICIAL  # noqa: E402


def porta_livre() -> int:
    for porta in range(PORTA_INICIAL, PORTA_FINAL + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise RuntimeError(f"Nenhuma porta livre entre {PORTA_INICIAL} e {PORTA_FINAL}.")


def main():
    porta = porta_livre()
    comando = [
        sys.executable, "-m", "streamlit", "run", str(RAIZ / "app.py"),
        "--server.headless=true", f"--server.port={porta}", "--server.address=127.0.0.1",
        "--global.developmentMode=false", "--browser.gatherUsageStats=false",
    ]
    processo = subprocess.Popen(comando, cwd=RAIZ,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{porta}")
    processo.wait()


if __name__ == "__main__":
    main()
