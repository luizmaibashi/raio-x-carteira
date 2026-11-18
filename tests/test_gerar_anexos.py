"""Gate do gerador (P18): JSON completo e coerente com o texto oficial."""
import copy
import json
from decimal import Decimal as D

import pytest

from raio_x.das import ARQUIVO_ANEXOS, carregar_anexos
from scripts.gerar_anexos import GateError, PERIODOS, gate


def test_json_tem_fonte_e_estrutura_completa():
    d = carregar_anexos()
    assert set(d["anexos"]) == {"III", "V"}
    for a in d["anexos"].values():
        assert len(a["fonte"]["sha256"]) == 64 and a["fonte"]["url"].startswith("https://")
        assert set(a["partilha"]) == set(PERIODOS)
        assert all(len(t) == 6 for t in a["partilha"].values())
        assert set(a["aliquotas"]) == {"2027-2028", "2029+"}


def test_p14_primeira_faixa_anexo_iii_2027():
    l = carregar_anexos()["anexos"]["III"]["partilha"]["2027-2028"][0]
    assert {k: D(str(v)) for k, v in l.items() if k != "faixa"} == {
        "IRPJ": D("4"), "CSLL": D("3.5"), "CBS": D("15.43"), "CPP": D("43.4"), "ISS": D("33.5"), "IBS": D("0.17")}


def _json_strs():
    d = json.loads(ARQUIVO_ANEXOS.read_text(encoding="utf-8"))["anexos"]["III"]
    return d["aliquotas"], d["partilha"]


def test_gate_falha_com_faixa_faltando():
    aliq, part = _json_strs()
    part = copy.deepcopy(part); part["2030"].pop()
    with pytest.raises(GateError):
        gate("III", aliq, part)


def test_gate_falha_com_soma_errada():
    aliq, part = _json_strs()
    part = copy.deepcopy(part); part["2031"][0]["CBS"] = "16.00"
    with pytest.raises(GateError):
        gate("III", aliq, part)


def test_gate_aceita_so_excecao_conhecida():
    aliq, part = _json_strs()
    assert len(gate("III", aliq, part)) == 2
    part = copy.deepcopy(part); part["2029"][0]["CBS"] = "15.61"
    with pytest.raises(GateError):
        gate("III", aliq, part)


def test_tetos_do_iss_so_no_anexo_iii_ate_2032():
    d = carregar_anexos()["anexos"]
    assert set(d["III"]["teto_iss_5a_faixa"]) == set(PERIODOS[:-1])
    assert d["V"]["teto_iss_5a_faixa"] == {}
