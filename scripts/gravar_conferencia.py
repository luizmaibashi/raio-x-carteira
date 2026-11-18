"""Grava a conferência do módulo DAS no motor oficial da Receita (calculadora do Simples, local).

Na nuvem o motor não roda; a tela mostra esta conferência gravada, com data, em vez de um botão que falha.
Os valores do motor são a resposta da calculadora da Receita; nenhum número é digitado (regra 1).

Uso: python scripts/gravar_conferencia.py [SAIDA.json]   (motor do Simples no ar na porta 8082)
"""
import datetime as dt
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from raio_x.das import calcular  # noqa: E402
from raio_x.painel import ANOS  # noqa: E402
from raio_x.receita import URL_SIMPLES, ClienteReceita  # noqa: E402

BASE = "10000.00"   # nota de R$ 10 mil, a mesma do botão da tela
# Carteira de exemplo (RBT12 300 mil) nos dois anexos, em todos os anos, e os casos do teste de integração.
CASOS = ([(300_000, 90_000, ano) for ano in ANOS] + [(300_000, 0, ano) for ano in ANOS]
         + [(120_000, 40_000, 2027), (300_000, 30_000, 2027), (1_000_000, 300_000, 2027),
            (2_000_000, 600_000, 2027), (3_600_000, 1_200_000, 2027)])


def main() -> int:
    saida = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dados" / "conferencia_receita.json"
    cli = ClienteReceita(timeout=10)
    casos = []
    for rbt12, folha, ano in CASOS:
        das = calcular(rbt12, folha, ano)
        conf = cli.conferir_das(das, f"{ano}-03-10", BASE)
        casos.append({
            "rbt12": rbt12, "folha12": folha, "ano": ano, "anexo": das.anexo, "faixa": das.faixa,
            "p_cbs_sn": str(conf.motor.p_cbs_sn), "p_ibs_sn": str(conf.motor.p_ibs_sn),
            "base": str(conf.motor.base),
            "motor_v_cbs_sn": str(conf.motor.v_cbs_sn), "motor_v_ibs_sn": str(conf.motor.v_ibs_sn),
            "proprio_v_cbs_sn": str(conf.esperado_cbs), "proprio_v_ibs_sn": str(conf.esperado_ibs),
            "confere": conf.ok, "divergencias": list(conf.divergencias),
        })
    doc = {
        "fonte": "calculadora-rtc-simples-nacional da Receita Federal (github.com/ReceitaFederal), rodando localmente",
        "endpoint": "POST /api/calculadora/observabilidade/simples-nacional",
        "url_usada": URL_SIMPLES,
        "gravado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "casos": casos,
    }
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = sum(c["confere"] for c in casos)
    print(f"{ok}/{len(casos)} casos conferem -> {saida}")
    return 0 if ok == len(casos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
