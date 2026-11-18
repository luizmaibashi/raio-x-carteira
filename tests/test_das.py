"""Testes mínimos do DESENHO_MODULO_DAS.md. Casos de referência calculados à mão
a partir das tabelas dos Anexos III e V (LC 214/2025, Anexos XX e XXII; P14, P16, P18)."""
from decimal import Decimal as D

import pytest

from raio_x.das import ForaDoEscopo, calcular, carregar_anexos, comparar_pgdas


def q(x, casas=6):
    return x.quantize(D(1).scaleb(-casas))


def test_fator_r_exatamente_28_vai_ao_anexo_iii():
    assert calcular(100_000, 28_000, 2027).anexo == "III"
    assert calcular(100_000, D("27999.99"), 2027).anexo == "V"


def test_primeira_faixa_efetiva_igual_nominal():
    r = calcular(120_000, 40_000, 2027)
    assert r.faixa == 1 and r.aliquota_efetiva == r.aliquota_nominal == D("6.00")


def test_fronteira_180_mil():
    assert calcular(D("180000.00"), 60_000, 2027).faixa == 1
    r = calcular(D("180000.01"), 60_000, 2027)
    assert r.faixa == 2
    # continuidade: na fronteira a efetiva da 2ª faixa ≈ 6%
    assert abs(r.aliquota_efetiva - D("6.00")) < D("0.0001")


@pytest.mark.parametrize("ano", [2027, 2029, 2030, 2031, 2032])
def test_teto_iss_soma_da_partilha_e_a_efetiva(ano):
    r = calcular(3_600_000, 1_200_000, ano)
    assert r.teto_iss_aplicado
    assert r.partilha["ISS"] + (r.partilha["IBS"] if ano > 2028 else 0) <= D(5)
    assert abs(sum(r.partilha.values()) - r.aliquota_efetiva) < D("0.001")


def test_linha_do_tempo_ibs_sobe_iss_cai():
    dados = carregar_anexos()
    for anexo in ("III", "V"):
        part = dados["anexos"][anexo]["partilha"]
        for faixa in range(1, 6):
            serie = [next(l for l in part[p] if l["faixa"] == faixa)
                     for p in ("2029", "2030", "2031", "2032", "2033")]
            ibs = [D(l["IBS"]) for l in serie]
            iss = [D(l.get("ISS", 0)) for l in serie]
            assert ibs == sorted(ibs) and len(set(ibs)) == 5
            assert iss == sorted(iss, reverse=True) and iss[-1] == 0


def test_fora_do_escopo_explicito():
    with pytest.raises(ForaDoEscopo):
        calcular(D("3600000.01"), 2_000_000, 2027)
    with pytest.raises(ForaDoEscopo):
        calcular(100_000, 30_000, 2026)
    with pytest.raises(ForaDoEscopo):
        calcular(0, 0, 2027)


# (rbt12, folha12, ano, anexo, faixa, a, {tributo: esperado})
CASOS = [
    (120_000, 40_000, 2027, "III", 1, "6", {"CBS": "0.9258", "IBS": "0.0102"}),
    (300_000, 90_000, 2027, "III", 2, "8.08", {"CBS": "1.366328", "IBS": "0.015352"}),
    (300_000, 30_000, 2027, "V", 2, "16.5", {"CBS": "2.7984", "IBS": "0.03135"}),
    (3_600_000, 1_200_000, 2027, "III", 5, "17.51", {"ISS": "5", "IBS": "0.032526", "CBS": "2.90232"}),
    (3_600_000, 1_200_000, 2029, "III", 5, "17.51", {"ISS": "4.5", "IBS": "0.5", "CBS": "2.934846"}),
    (3_600_000, 1_200_000, 2033, "III", 5, "17.51", {"IBS": "5.86585"}),
    (2_000_000, 600_000, 2027, "III", 5, "14.718", {"ISS": "4.93053"}),
    (500_000, 0, 2033, "V", 3, "17.52", {"IBS": "3.3288"}),
    (1_000_000, 300_000, 2027, "III", 4, "12.436", {"CBS": "2.0419912"}),
    (1_000_000, 100_000, 2030, "V", 4, "18.79", {"IBS": "0.78918", "ISS": "3.15672"}),
]


@pytest.mark.parametrize("rbt12,folha,ano,anexo,faixa,a,partes", CASOS)
def test_casos_de_referencia(rbt12, folha, ano, anexo, faixa, a, partes):
    r = calcular(rbt12, folha, ano)
    assert (r.anexo, r.faixa) == (anexo, faixa)
    assert q(r.aliquota_efetiva) == q(D(a))
    for t, v in partes.items():
        assert q(r.partilha[t], 7) == q(D(v), 7), t


def test_pcbssn_pibssn():
    r = calcular(300_000, 90_000, 2027)
    assert r.c == r.p_cbs_sn + r.p_ibs_sn == r.partilha["CBS"] + r.partilha["IBS"]


def test_comparar_pgdas():
    r = calcular(300_000, 90_000, 2027)
    assert comparar_pgdas(r, "8.08") is None
    assert "difere" in comparar_pgdas(r, "8.20")
