# -*- coding: utf-8 -*-
"""Capturas de tela do app em alta resolução para o README e as notas de versão do GitHub (pedido de 27/11/2026).

Usa o Firefox em modo headless controlado pelo WebDriver BiDi (vem no próprio Firefox; não precisa de
Selenium nem de outro navegador). O app tem de estar rodando (``streamlit run app.py``).

    # 1) Firefox headless com o BiDi (perfil temporário, não mexe no Firefox do usuário)
    MOZ_HEADLESS_WIDTH=1920 MOZ_HEADLESS_HEIGHT=1080 firefox --headless --new-instance \
        --profile /tmp/perfil_capturas --remote-debugging-port 9333 about:blank &
    # 2) roteiro da prévia do README (docs/imagens/previa/)
    python ferramentas/capturar_telas.py --app http://127.0.0.1:8566 --saida docs/imagens/previa
    # 3) o "antes" das notas de versão, com a versão anterior rodando noutra porta (git worktree da tag)
    python ferramentas/capturar_telas.py --roteiro antes --app http://127.0.0.1:8567 --saida /tmp/antes

Cada captura é um PNG da janela inteira (1920×1080) ou de um elemento (``elemento=`` seletor CSS).
"""

import argparse
import asyncio
import base64
import json
from pathlib import Path

import websockets


class NavegadorBidi:
    """Cliente mínimo do WebDriver BiDi: navegar, rodar JavaScript, esperar e capturar a tela."""

    def __init__(self, endereco: str = "ws://127.0.0.1:9333/session"):
        self.endereco, self._id, self.ws, self.contexto = endereco, 0, None, None

    async def __aenter__(self):
        self.ws = await websockets.connect(self.endereco, max_size=64 * 2 ** 20)
        await self.comando("session.new", {"capabilities": {}})
        arvore = await self.comando("browsingContext.getTree", {})
        self.contexto = arvore["contexts"][0]["context"]
        await self.comando("browsingContext.setViewport", {"context": self.contexto,
                                                           "viewport": {"width": 1920, "height": 1080}})
        return self

    async def __aexit__(self, *erro):
        try:
            await self.comando("session.end", {})
        finally:
            await self.ws.close()

    async def comando(self, metodo: str, parametros: dict) -> dict:
        self._id += 1
        await self.ws.send(json.dumps({"id": self._id, "method": metodo, "params": parametros}))
        while True:
            resposta = json.loads(await self.ws.recv())
            if resposta.get("id") == self._id:
                if resposta.get("type") == "error":
                    raise RuntimeError(f"{metodo}: {resposta.get('error')} — {resposta.get('message')}")
                return resposta["result"]

    async def abrir(self, url: str):
        await self.comando("browsingContext.navigate", {"context": self.contexto, "url": url, "wait": "complete"})

    async def js(self, expressao: str):
        """Valor (JSON) da expressão; promessas são aguardadas."""
        r = await self.comando("script.evaluate", {"expression": expressao, "awaitPromise": True,
                                                   "target": {"context": self.contexto},
                                                   "resultOwnership": "none"})
        if r.get("type") == "exception":
            raise RuntimeError(r["exceptionDetails"].get("text"))
        return r["result"].get("value")

    async def esperar_app(self, maximo_s: float = 180):
        """Até o Streamlit parar de rodar (sem o indicador "Running" e sem spinners)."""
        await self.js(f"""new Promise(ok => {{
            const fim = Date.now() + {int(maximo_s * 1000)}; let quietos = 0;
            const t = setInterval(() => {{
                const rodando = document.querySelector('[data-testid="stStatusWidget"]')
                    || document.querySelector('[data-testid="stSpinner"]');
                quietos = rodando ? 0 : quietos + 1;
                if (quietos >= 6 || Date.now() > fim) {{ clearInterval(t); ok(true); }}
            }}, 500);
        }})""")

    async def clicar(self, seletor: str = None, texto: str = None):
        """Clica no primeiro botão com o seletor CSS ou com o texto."""
        alvo = (f"document.querySelector({json.dumps(seletor)})" if seletor else
                f"[...document.querySelectorAll('button, [role=tab], label')].find(b => "
                f"b.innerText.trim().includes({json.dumps(texto)}))")
        ok = await self.js(f"(() => {{ const b = {alvo}; if (!b) return false; b.click(); return true; }})()")
        if not ok:
            raise RuntimeError(f"Não achei para clicar: {seletor or texto}")

    async def digitar(self, seletor: str, texto: str, enter: bool = True):
        """Teclado de verdade (as caixas de seleção do Streamlit não aceitam valor posto por JavaScript)."""
        await self.js(f"(() => {{ const e = document.querySelector({json.dumps(seletor)}); e.focus(); e.click();"
                      " return true; })()")
        teclas = [a for c in texto for a in ({"type": "keyDown", "value": c}, {"type": "keyUp", "value": c})]
        if enter:
            teclas += [{"type": "pause", "duration": 600}, {"type": "keyDown", "value": "\uE007"},
                       {"type": "keyUp", "value": "\uE007"}]
        await self.comando("input.performActions", {"context": self.contexto, "actions": [
            {"type": "key", "id": "teclado", "actions": teclas}]})

    async def capturar(self, arquivo: Path, elemento: str = None):
        # sem a barra "Deploy ⋮" do Streamlit, que não faz parte do programa
        await self.js("(() => { if (!document.getElementById('sem-barra')) { const s = document.createElement('style');"
                      "s.id = 'sem-barra'; s.textContent = '[data-testid=stToolbar]{display:none !important}';"
                      "document.head.appendChild(s); } return true; })()")
        parametros = {"context": self.contexto, "origin": "viewport"}
        if elemento:
            caixa = json.loads(await self.js(f"(() => {{ const e = document.querySelector({json.dumps(elemento)});"
                                             "const r = e.getBoundingClientRect();"
                                             "return JSON.stringify([r.x, r.y, r.width, r.height]); })()"))
            parametros["clip"] = {"type": "box", "x": caixa[0], "y": caixa[1], "width": caixa[2], "height": caixa[3]}
        r = await self.comando("browsingContext.captureScreenshot", parametros)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(base64.b64decode(r["data"]))
        print("capturado:", arquivo)


async def roteiro_previa(app: str, saida: Path, municipio: str = "SÃO FÉLIX DO XINGU"):
    """Telas da seção "Prévia" do README (Panorama e diagnóstico, no legado e no dashboard) e os recortes das
    notas de versão (caixa de downloads do dashboard, painel esquerdo do legado)."""
    async with NavegadorBidi() as nav:
        await nav.abrir(app)
        await nav.esperar_app()
        await asyncio.sleep(4)                       # tiles do satélite no mapa
        await nav.capturar(saida / "01_panorama.png")
        await nav.clicar(texto="Visualização dashboard")
        await nav.esperar_app(300)
        await asyncio.sleep(5)
        await nav.capturar(saida / "04_panorama_dashboard.png")
        await nav.clicar(seletor=".st-key-icone_pagina_1 button")          # 🔥 Diagnóstico, no painel recolhido
        await nav.esperar_app()
        await nav.digitar(".st-key-diag_municipio input", municipio.title())
        await nav.esperar_app(300)
        await asyncio.sleep(8)                       # busca ao vivo em segundo plano e tiles
        await nav.esperar_app(300)
        await asyncio.sleep(4)
        await nav.esperar_app(300)
        await nav.capturar(saida / "03_dashboard.png")
        await nav.js("document.querySelector('.st-key-dash_downloads').scrollIntoView({block: 'center'})")
        await asyncio.sleep(1)
        await nav.capturar(saida / "recortes" / "caixa_downloads.png", elemento=".st-key-dash_downloads")
        await nav.capturar(saida / "recortes" / "dashboard_rolado.png")
        await nav.clicar(texto="☰")
        await nav.esperar_app()
        await nav.clicar(texto="Visualização legado")
        await nav.esperar_app(300)
        await asyncio.sleep(3)
        await nav.capturar(saida / "02_diagnostico.png")
        await nav.js("(() => { const c = document.querySelector('[data-testid=stSidebarContent]');"
                     "c.scrollTo(0, c.scrollHeight); return true; })()")
        await asyncio.sleep(1)
        await nav.capturar(saida / "recortes" / "painel_esquerdo.png", elemento='[data-testid="stSidebar"]')


async def roteiro_antes(app: str, saida: Path, municipio: str = "SÃO FÉLIX DO XINGU"):
    """O "antes" das notas de versão, numa versão anterior rodando à parte: painel esquerdo do diagnóstico
    processado (legado)."""
    async with NavegadorBidi() as nav:
        await nav.abrir(app)
        await nav.esperar_app()
        await nav.clicar(texto="Diagnóstico")
        await nav.esperar_app()
        await nav.digitar('[data-testid="stSidebar"] input[aria-label*="Município"]', municipio)
        await nav.esperar_app()
        await nav.clicar(texto="Baixar automaticamente")             # sem disparar o download
        await nav.esperar_app()
        await nav.clicar(texto="Processar Diagnóstico Completo")
        await nav.esperar_app(400)
        await asyncio.sleep(3)
        await nav.esperar_app(400)
        await nav.capturar(saida / "antes_diagnostico.png")
        await nav.js("(() => { const c = document.querySelector('[data-testid=stSidebarContent]');"
                     "c.scrollTo(0, c.scrollHeight); return true; })()")
        await asyncio.sleep(1)
        await nav.capturar(saida / "antes_painel_esquerdo.png", elemento='[data-testid="stSidebar"]')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", default="http://127.0.0.1:8566")
    parser.add_argument("--saida", type=Path, default=Path("docs/imagens/previa"))
    parser.add_argument("--municipio", default="SÃO FÉLIX DO XINGU")
    parser.add_argument("--roteiro", choices=["previa", "antes"], default="previa")
    args = parser.parse_args()
    roteiro = roteiro_previa if args.roteiro == "previa" else roteiro_antes
    asyncio.run(roteiro(args.app, args.saida, args.municipio))


if __name__ == "__main__":
    main()
