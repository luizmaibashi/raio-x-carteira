"""Valida XMLs de NFS-e contra o XSD oficial do padrão nacional (leiaute 1.01).

Baixa o pacote de esquemas do portal da NFS-e, confere o SHA-256 e valida cada arquivo. Uso de desenvolvimento:
precisa de `pip install xmlschema` (fora do requirements.txt da demo).

Correção aplicada só na cópia temporária: em tiposSimples_v1.01.xsd o padrão da série da DPS é
"^0{0,4}\\d{1,5}$". Em expressão regular de XSD, ^ e $ são caracteres literais, não âncoras, então nenhuma série
real passaria. Validamos com "0{0,4}\\d{1,5}", que é a intenção evidente do esquema.

Uso: python scripts/validar_nfse_xsd.py [arquivos.xml ...]   (padrão: dados/exemplos/nfse/*.xml)
"""
import hashlib
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import xmlschema

RAIZ = Path(__file__).resolve().parent.parent
URL = ("https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/"
       "nfse-esquemas_xsd-v1-01-20260209.zip")
SHA256 = "e7935cbd9470527c6cc32984c1b2263e614183bf0139ce2733eaaed2de9a8072"   # lido em 18/11/2026
SERIE_OFICIAL, SERIE_CORRIGIDA = 'value="^0{0,4}\\d{1,5}$"', 'value="0{0,4}\\d{1,5}"'


def esquema(pasta: Path) -> xmlschema.XMLSchema:
    bruto = subprocess.run(["curl", "-sSfL", "-A", "Mozilla/5.0", URL], check=True, capture_output=True).stdout
    if hashlib.sha256(bruto).hexdigest() != SHA256:
        raise SystemExit("o pacote de esquemas mudou: confira a nova versão antes de validar")
    zipfile.ZipFile(io.BytesIO(bruto)).extractall(pasta)
    base = pasta / "Schemas" / "1.01"
    tipos = base / "tiposSimples_v1.01.xsd"
    texto = tipos.read_text(encoding="utf-8")
    if SERIE_OFICIAL not in texto:
        raise SystemExit("padrão da série mudou no XSD: revise a correção")
    tipos.write_text(texto.replace(SERIE_OFICIAL, SERIE_CORRIGIDA), encoding="utf-8")
    return xmlschema.XMLSchema(str(base / "NFSe_v1.01.xsd"))


def main(arquivos: list[str]) -> int:
    caminhos = [Path(a) for a in arquivos] or sorted((RAIZ / "dados" / "exemplos" / "nfse").glob("*.xml"))
    with tempfile.TemporaryDirectory() as tmp:
        xs = esquema(Path(tmp))
        falhas = 0
        for c in caminhos:
            erros = list(xs.iter_errors(str(c)))
            falhas += bool(erros)
            print(f"{c.name}: " + ("válido" if not erros else f"INVÁLIDO — {erros[0].reason} em {erros[0].path}"))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
