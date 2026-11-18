"""Regrava os XMLs sintéticos de exemplo (dados/exemplos/nfse) no leiaute nacional 1.01 completo.

Dados fictícios (regra 5): CNPJ e CPF com dígito verificador inválido de propósito.
Conferir contra o XSD oficial: python scripts/validar_nfse_xsd.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests.nfse_sintetica import nota_completa  # noqa: E402

PASTA = RAIZ / "dados" / "exemplos" / "nfse"
NOTAS = [
    dict(dh="2026-02-10T09:00:00-03:00", vserv="10000.00", cnpj="11111111000100", nome="Indústria Alfa (sintético)"),
    dict(dh="2026-05-10T09:00:00-03:00", vserv="10000.00", cnpj="11111111000100", nome="Indústria Alfa (sintético)"),
    dict(dh="2026-06-15T09:00:00-03:00", vserv="6000.00", cnpj="22222222000100", nome="Comércio Beta (sintético)",
         desc_incond="500.00"),
    dict(dh="2026-07-01T09:00:00-03:00", vserv="1500.00", cpf="12345678900", nome="Pessoa física (sintético)"),
    dict(dh="2026-08-01T09:00:00-03:00", vserv="1200.00", cpf="98765432111", nome="Pessoa física (sintético)"),
]

if __name__ == "__main__":
    for i, n in enumerate(NOTAS, 1):
        (PASTA / f"nfse_{i:03d}.xml").write_text(nota_completa(i, **n), encoding="utf-8")
    print(f"{len(NOTAS)} notas gravadas em {PASTA.relative_to(RAIZ)}")
