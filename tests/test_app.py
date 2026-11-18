"""Fumaça da tela com o AppTest do Streamlit e testes das funções do painel."""
from decimal import Decimal as D
from pathlib import Path

import pytest

from raio_x.painel import brl, pct, t_por_ano

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_t_por_ano():
    ts = t_por_ano("0.27", False)
    assert ts[2027] == D("0.113") and ts[2033] == D("0.27")
    assert ts[2029] == D("0.113") + D("0.1") * (D("0.27") - D("0.113"))
    assert t_por_ano("0.27", True)[2027] == D("0.0791")


def test_formatos():
    assert brl(1234.5) == "R$ 1.234,50" and brl(-5450.83) == "-R$ 5.450,83" and brl(-0.001) == "R$ 0,00" and pct(D("0.0808")) == "8,08%"


def _botao(at, rotulo):
    return next(b for b in at.button if b.label == rotulo)


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(APP, default_timeout=30)


def test_tela_abre_com_exemplo_e_veredito():
    at = _app().run()
    assert not at.exception, at.exception
    assert any("rx-veredito" in md.value and "R$" in md.value for md in at.markdown)
    assert "Melhor regime para você" in [m.label for m in at.metric]


def test_tela_com_exemplo_csv_mostra_resultado():
    at = _app().run()
    _botao(at, "Carteira (CSV)").click().run()
    assert not at.exception, at.exception
    rotulos = [m.label for m in at.metric]
    assert "Melhor regime para você" in rotulos
    assert any("H só compensa" in md.value for md in at.markdown)


def test_tela_com_xml_exige_regime_dos_pj():
    at = _app().run()
    _botao(at, "Notas (XML)").click().run()
    assert not at.exception
    assert any("Informe o regime" in w.value for w in at.warning)


def test_tela_muda_parametros_sem_erro():
    at = _app().run()
    _botao(at, "Carteira (CSV)").click().run()
    at.slider[0].set_value(0.5).run()
    at.number_input[0].set_value(0.0).run()   # folha 0 -> Anexo V, ainda dentro do escopo
    assert not at.exception
