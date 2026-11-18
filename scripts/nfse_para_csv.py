"""Converte uma pasta de XMLs de NFS-e (padrão nacional) no CSV da carteira.

Uso: python scripts/nfse_para_csv.py PASTA SAIDA.csv [--inicio AAAA-MM-DD] [--fim AAAA-MM-DD]
Depois, preencha a coluna `tomador` das linhas em branco (regular, simples, simples_h, isento).
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raio_x.nfse import ler_pasta, para_csv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--inicio", type=dt.date.fromisoformat)
    ap.add_argument("--fim", type=dt.date.fromisoformat)
    a = ap.parse_args()
    r = ler_pasta(a.pasta, inicio=a.inicio, fim=a.fim)
    a.saida.write_text(para_csv(r), encoding="utf-8")
    print(f"{r.notas_lidas} notas, {len(r.tomadores)} tomadores, {r.fora_do_periodo} fora do período, "
          f"{r.duplicadas} duplicadas -> {a.saida}")
    for av in r.avisos:
        print("aviso:", av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
