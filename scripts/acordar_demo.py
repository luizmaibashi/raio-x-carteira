"""Abre a demo pública num navegador sem tela e a acorda se o Streamlit Community Cloud a pôs para dormir.

O Community Cloud hiberna apps sem tráfego por 12 horas; quem acorda é um visitante clicando no botão da página
de hibernação. O workflow `.github/workflows/manter_demo.yml` roda este script a cada 6 horas até o fim do Hack.
Não faz commit nem altera o repositório.

Uso: python scripts/acordar_demo.py [URL]   (requer `pip install playwright` e `playwright install chromium`)
"""
import re
import sys

from playwright.sync_api import TimeoutError as Esgotou
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://raio-x-carteira.streamlit.app"
MARCA = "Sua empresa"   # texto da barra lateral do app (innerText sai com a caixa da tela, então nada de título)


def _app_carregou(pagina, espera_ms: int) -> bool:
    """O app roda num iframe de outro endereço (/~/+/); procura a marca em todos os frames, a cada 5 s."""
    for _ in range(espera_ms // 5000):
        for frame in pagina.frames:
            try:
                if MARCA in frame.locator("body").inner_text(timeout=2000):
                    return True
            except Exception:   # frame ainda carregando ou já descartado
                pass
        pagina.wait_for_timeout(5000)
    return False


def main() -> int:
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pagina = nav.new_page()
        pagina.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        botao = pagina.get_by_role("button", name=re.compile("get this app back up", re.I))
        try:
            botao.wait_for(timeout=20_000)
            botao.click()
            print("estava dormindo: botão de acordar clicado", flush=True)
        except Esgotou:
            print("não estava dormindo", flush=True)
        ok = _app_carregou(pagina, 300_000)
        nav.close()
    print("app no ar" if ok else "app não carregou em 5 minutos")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
