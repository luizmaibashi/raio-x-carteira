"""Gera e grava a explicação por IA dos perfis de exemplo no cenário inicial da tela (2027, 0% do preço mantido).

Assim a demo mostra a explicação sem chamar a API a cada visita. Cada texto gravado passou pelo verificador:
todo número citado existe no cálculo (regra 1); o teste tests/test_explicacao.py confere de novo.

Uso: ANTHROPIC_API_KEY=... python scripts/gerar_explicacoes.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import anthropic  # noqa: E402

from raio_x.entrada import ler_carteira_csv  # noqa: E402
from raio_x.explicacao import MODELO, gerar, montar_fatos, numeros  # noqa: E402
from raio_x.modelo import aliquota_t  # noqa: E402

EXEMPLOS = RAIZ / "dados" / "exemplos"
SAIDA = RAIZ / "dados" / "explicacoes_ia.json"


def fatos_do_perfil(p: dict):
    with open(EXEMPLOS / p["arquivo"], encoding="utf-8") as f:
        clientes = ler_carteira_csv(f)
    return montar_fatos(clientes, float(p["folha12"]), 2027, aliquota_t(2027, p["reducao_30"]), 0.0, 0.0,
                        p["reducao_30"])


def main() -> int:
    perfis = json.loads((EXEMPLOS / "perfis.json").read_text(encoding="utf-8"))
    gravadas = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {}
    cliente = anthropic.Anthropic()
    for p in perfis:
        fatos = fatos_do_perfil(p)
        saida = gerar(cliente, fatos)
        texto = saida["resumo"] + " " + " ".join(c["argumento"] for c in saida["clientes"])
        gravadas[fatos.chave] = {
            "perfil": p["nome"], "modelo": MODELO,
            "gerado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "numeros_conferidos": len(numeros(texto)), **saida,
        }
        print(f"{p['nome']}: ok ({gravadas[fatos.chave]['numeros_conferidos']} números conferidos)")
    SAIDA.write_text(json.dumps(gravadas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
