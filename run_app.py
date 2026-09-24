import os
import sys
import subprocess
import webbrowser
import time

def main():
    # Identifica o caminho do script app.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(base_dir, "app.py")
    
    # Executa o Streamlit em segundo plano sem janela de terminal
    cmd = [
        sys.executable, "-m", "streamlit", "run", app_path,
        "--server.headless=true",
        "--server.port=8501",
        "--global.developmentMode=false"
    ]
    
    process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    time.sleep(2)
    
    # Abre o navegador automaticamente na interface
    webbrowser.open("http://localhost:8501")
    process.wait()

if __name__ == "__main__":
    main()