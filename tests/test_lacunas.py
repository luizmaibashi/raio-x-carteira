"""Lacunas por regra determinística (P20 concentração, P21 prazo de recebimento)."""
from decimal import Decimal as D

import pytest

from raio_x import lacunas
from raio_x.modelo import Cliente, aliquota_t

T = aliquota_t(2027)


def _c(nome, valor, cred):
    return Cliente(f"{nome} (sintético)", D(valor), cred)


def test_sem_concentracao_abaixo_de_30_por_cento():
    carteira = [_c(n, 100_000, True) for n in "ABCD"]          # 25% cada
    assert lacunas.concentracao(carteira, 120_000, 2027, T, 0) is None


def test_concentracao_no_limite_cita_a_fatia():
    carteira = [_c("A", 30_000, False), _c("B", 70_000, True)]  # maior = B, 70%
    x = lacunas.concentracao(carteira, 30_000, 2027, T, 0)
    assert x.premissa == "P20" and x.titulo == "Receita concentrada"
    assert "B (sintético) responde por 70,0% da sua receita" in x.texto
    exato = [_c("A", 30_000, True)] + [_c(n, 17_500, True) for n in "BCDE"]  # 30,0% exatos
    assert lacunas.concentracao(exato, 30_000, 2027, T, 0) is not None


def test_veredito_que_depende_do_credito_do_maior_cliente():
    # Tudo com crédito: por fora ganha. Sem o crédito do maior (≈ 43% da receita), perde.
    carteira = [_c("Banco", 180_000, True), _c("Seguradora", 150_000, True), _c("Varejo", 90_000, True)]
    x = lacunas.concentracao(carteira, 126_000, 2027, T, 0)
    assert x.titulo == "Sua decisão depende de um cliente"
    assert "se ele deixar de usar" in x.texto


@pytest.mark.parametrize("dias, alerta", [(0, False), (30, False), (31, True), (90, True)])
def test_prazo_de_recebimento(dias, alerta):
    x = lacunas.prazo_recebimento(dias)
    assert (x is not None) == alerta
    if alerta:
        assert x.premissa == "P21" and f"Com {dias} dias" in x.texto


def test_avaliar_junta_as_duas_regras():
    carteira = [_c("A", 30_000, False), _c("B", 70_000, True)]
    ids = [x.id for x in lacunas.avaliar(carteira, 30_000, 2027, T, 0, prazo_dias=60)]
    assert ids == ["concentracao", "prazo"]
    assert lacunas.avaliar([_c(n, 100_000, True) for n in "ABCD"], 120_000, 2027, T, 0, prazo_dias=30) == []


def test_tela_mostra_pontos_de_atencao_da_consultora():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=30).run()
    at.selectbox(key="perfil").set_value("Consultora de TI").run()
    assert not at.exception, at.exception
    textos = " ".join(x.value for x in at.info)
    assert "Sua decisão depende de um cliente" in textos and "Com 60 dias" in textos
