import io
from decimal import Decimal as D
from pathlib import Path

import pytest

from raio_x.entrada import ErroEntrada, ler_carteira_csv, valor_br
from raio_x.modelo import avaliar_carteira

EXEMPLO = Path(__file__).resolve().parent.parent / "dados" / "exemplos" / "carteira_exemplo.csv"


def csv_(texto):
    return ler_carteira_csv(io.StringIO(texto))


def test_exemplo_sintetico_roda_no_modelo():
    cart = ler_carteira_csv(EXEMPLO)
    assert len(cart) == 5 and sum(c.valor for c in cart) == 300_000
    assert [c.cred for c in cart] == [True, True, False, True, False]
    r = avaliar_carteira(cart, 90_000, 2027, "0.113", 0)
    assert r.peso_sem_credito == D(70_000) / 300_000


@pytest.mark.parametrize("txt,esperado", [
    ("1.234,56", "1234.56"), ("1234.56", "1234.56"), ("200.000", "200000"), ("R$ 10,00", "10.00")])
def test_valor_br(txt, esperado):
    assert valor_br(txt) == D(esperado)


def test_separador_virgula_e_ordem_de_colunas():
    cart = csv_("tomador,cliente,valor_12m\nregular,A,1000.00\n")
    assert cart[0].valor == D("1000.00") and cart[0].cred


@pytest.mark.parametrize("texto,trecho", [
    ("", "vazio"),
    ("cliente;valor\nA;1\n", "cabeçalho"),
    ("cliente;valor_12m;tomador\n", "nenhum cliente"),
    ("cliente;valor_12m;tomador\nA;1,00;mei\n", "tomador"),
    ("cliente;valor_12m;tomador\nA;abc;pf\n", "linha 2"),
    ("cliente;valor_12m;tomador\nA;0;pf\n", "positivo"),
    ("cliente;valor_12m;tomador\nA;1;pf\nA;2;pf\n", "repetido"),
    ("cliente;valor_12m;tomador\nA;1\n", "colunas"),
    ("cliente;valor_12m;tomador\n123.456.789-00;1;pf\n", "CPF/CNPJ"),
    ("cliente;valor_12m;tomador\nEmpresa 12345678000199;1;regular\n", "CPF/CNPJ"),
])
def test_erros_explicitos(texto, trecho):
    with pytest.raises(ErroEntrada, match=trecho):
        csv_(texto)
