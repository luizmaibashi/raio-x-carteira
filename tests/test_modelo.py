"""Testes exigidos pelo MODELO_ECONOMICO.md e casos calculados à mão."""
from decimal import Decimal as D

import pytest

from raio_x.das import ForaDoEscopo
from raio_x.modelo import (Cliente, aliquota_t, avaliar_carteira, linha_do_tempo,
                           peso_indiferenca, preco_equilibrio, resultado_cliente)

A, C, T = D("0.0808"), D("0.013817"), D("0.113")


def test_t_2027_e_reducao_30():
    assert aliquota_t(2027) == D("0.113")
    assert aliquota_t(2027, reducao_30=True) == D("0.0791")
    with pytest.raises(ForaDoEscopo):
        aliquota_t(2030)
    assert aliquota_t(2030, cenario="0.20") == D("0.20")


def test_carteira_com_credito_h_ganha_ja_com_r0():
    res = resultado_cliente(1000, True, A, C, T, 0)
    assert res.ganho_prestador >= 0
    assert res.variacao_custo_cliente == 0  # r = 0: cliente indiferente
    # P(1−a) + P·c(a−c)
    assert res.prestador_h == 1000 * (1 - A) + 1000 * C * (A - C)


def test_carteira_sem_credito_h_perde_com_r0():
    res = resultado_cliente(1000, False, A, C, T, 0)
    assert res.ganho_prestador < 0
    assert abs(res.variacao_custo_cliente) < D("1e-20")


def test_sem_credito_r1_custo_do_cliente_sobe_t():
    res = resultado_cliente(1000, False, A, C, T, 1)
    assert res.preco_h == 1000
    assert res.cliente_h == res.cliente_s * (1 + T)


def test_c_zero_cliente_nao_credita_em_s():
    res = resultado_cliente(1000, True, A, 0, T, 0)
    assert res.cliente_s == 1000


def test_conservacao_tributo_igual_credito():
    res = resultado_cliente(1000, True, A, C, T, D("0.4"))
    assert res.tributo_por_fora == res.credito_cliente_h == T * res.preco_h


def test_equilibrio_sem_credito_2027():
    # P/(1+t) = 1000/1,113 = 898,4726…: cerca de 10% da receita (MODELO_ECONOMICO.md)
    assert round(preco_equilibrio(1000, False, C, T), 4) == D("898.4726")


def test_r_fora_do_intervalo():
    with pytest.raises(ForaDoEscopo):
        resultado_cliente(1000, True, A, C, T, D("1.1"))


CARTEIRA = [Cliente("cliente-a", D(200_000), True), Cliente("cliente-b", D(100_000), False)]


def test_carteira_usa_modulo_das():
    # RBT12 300 mil, Fator R 30%: Anexo III 2ª faixa, a = 8,08% (caso de referência do DAS)
    r = avaliar_carteira(CARTEIRA, 90_000, 2027, T, 0)
    assert r.a == D("0.0808")
    assert r.peso_sem_credito == D(1) / 3
    assert r.prestador_s == 300_000 * (1 - r.a)
    assert r.prestador_h == sum(x.prestador_h for x in r.clientes.values())


def test_peso_de_indiferenca_zera_ganho():
    s = peso_indiferenca(A, C, T, 0)
    assert s is not None and 0 < s < 1
    ganho = s * resultado_cliente(1, True, A, C, T, 0).ganho_prestador + \
        (1 - s) * resultado_cliente(1, False, A, C, T, 0).ganho_prestador
    assert abs(ganho) < D("1e-20")


def test_com_r1_h_vale_em_qualquer_carteira():
    # r = 1: Q = P; H rende P(1−a+c) > P(1−a)
    assert peso_indiferenca(A, C, T, 1) is None
    assert avaliar_carteira(CARTEIRA, 90_000, 2027, T, 1).melhor == "H"


def test_linha_do_tempo_vira_quando_t_sobe():
    # Carteira 90% com crédito; com r = 0 cada real sem crédito custa ~t/(1+t)
    cart = [Cliente("x", D(270_000), True), Cliente("y", D(30_000), False)]
    res, virada = linha_do_tempo(cart, 90_000, {2027: "0.001", 2033: "0.28"}, 0)
    assert [x.melhor for x in res] == ["H", "S"] and virada == 2033
