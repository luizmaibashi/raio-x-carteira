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
    assert any("class=\"rx-topo" in md.value and "R$" in md.value for md in at.markdown)
    assert "Preço a manter" in [m.label for m in at.metric]
    assert any("precisaria manter pelo menos" in md.value for md in at.markdown)


def test_tela_com_exemplo_csv_mostra_resultado():
    at = _app().run()
    _botao(at, "Recarregar").click().run()
    assert not at.exception, at.exception
    rotulos = [m.label for m in at.metric]
    assert "Preço a manter" in rotulos
    assert any("só compensa" in md.value for md in at.markdown)


def test_tela_com_xml_exige_regime_dos_pj():
    at = _app().run()
    _botao(at, "Notas (XML)").click().run()
    assert not at.exception
    assert any("Informe o regime" in w.value for w in at.warning)
    # C12: regime ainda não informado aparece como célula vazia na tabela, não escrito "None".
    editor = at.dataframe[0].proto
    assert editor.HasField("placeholder") and editor.placeholder == ""


def test_campos_em_reais_sem_casas_decimais():
    """C13: folha e créditos aparecem como "90000", não "90000.00" (o Streamlit não formata em pt-BR)."""
    at = _app().run()
    formatos = {n.label.split(",")[0]: n.proto.format for n in at.number_input}
    assert formatos["Folha + pró-labore + encargos"] == "%.0f"
    assert formatos["Créditos de IBS/CBS das suas compras se recolher por fora"] == "%.0f"


def test_csv_invalido_nao_deixa_o_resultado_anterior_na_tela():
    """C11: arquivo recusado para a tela; o veredito do arquivo anterior não pode continuar como se fosse dele."""
    at = _app().run()
    at.radio[0].set_value("CSV").run()
    valido = (Path(APP).parent / "dados" / "exemplos" / "perfis" / "contador.csv").read_bytes()
    at.file_uploader[0].set_value(("valido.csv", valido, "text/csv")).run()
    assert "Preço a manter" in [m.label for m in at.metric]
    at.file_uploader[0].set_value(("ruim.csv", b"cliente;valor_12m;tomador\nA;abc;regular\n", "text/csv")).run()
    assert not at.exception, at.exception
    assert any("linha 2" in e.value and "ruim.csv" in e.value for e in at.error)
    assert not at.metric
    assert not any("valido.csv carregado" in md.value for md in at.markdown)


def test_tela_muda_parametros_sem_erro():
    at = _app().run()
    _botao(at, "Recarregar").click().run()
    next(s for s in at.slider if s.label.startswith("Quanto do seu preço")).set_value(50).run()
    at.number_input[0].set_value(0.0).run()   # folha 0 -> Anexo V, ainda dentro do escopo
    assert not at.exception


def test_conferencia_gravada_bate_com_o_modulo_das_atual():
    """Se a tabela do Simples ou o DAS mudar, a conferência gravada fica velha: regrave com o motor no ar."""
    from decimal import ROUND_HALF_UP
    from raio_x.das import calcular
    from raio_x.painel import caso_conferido, ler_conferencia
    doc = ler_conferencia(Path(APP).parent / "dados" / "conferencia_receita.json")
    assert doc and doc["casos"] and all(c["confere"] for c in doc["casos"])
    q = D("0.0001")
    for c in doc["casos"]:
        das = calcular(c["rbt12"], c["folha12"], c["ano"])
        assert (das.p_cbs_sn.quantize(q, ROUND_HALF_UP), das.p_ibs_sn.quantize(q, ROUND_HALF_UP)) == \
            (D(c["p_cbs_sn"]), D(c["p_ibs_sn"]))
        assert caso_conferido(doc, das) is not None
    assert ler_conferencia(Path("/nao/existe.json")) is None and caso_conferido(None, das) is None


def test_aviso_de_prazo_em_2027():
    import datetime as dt
    at = _app().run()
    avisos = [w.value for w in at.warning]
    if dt.date.today() <= dt.date(2026, 12, 20):
        assert any("20/12/2026" in w for w in avisos)
    else:
        assert not any("20/12/2026" in w for w in avisos)


@pytest.mark.parametrize("perfil,melhor", [("Designer", "S"), ("Consultora de TI", "H"), ("Contador", "S")])
def test_perfis_de_exemplo_dao_respostas_diferentes(perfil, melhor):
    at = _app().run()
    at.selectbox(key="perfil").set_value(perfil).run()
    assert not at.exception, at.exception
    topo = next(md.value for md in at.markdown if "class=\"rx-topo" in md.value)
    assert perfil in topo
    assert ("Recolher IBS/CBS por fora rende" in topo) == (melhor == "H")
    if perfil == "Contador":   # apertado: com redução de 30%, mantendo pouco do preço já vira
        assert at.checkbox(key="reducao").value is True
        assert any(m.label == "Preço a manter" and m.value == "8%" for m in at.metric)


def test_app_recarrega_modulo_antigo_que_ficou_na_memoria():
    """Simula o Streamlit Cloud com app.py novo e raio_x.lacunas antigo na memória (18/11/2026).

    Roda em outro processo: o recarregamento troca as classes do pacote e atrapalharia os demais testes.
    """
    import subprocess
    import sys
    raiz = Path(__file__).resolve().parent.parent
    roteiro = f"""
import sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file({str(raiz / "app.py")!r}, default_timeout=30).run()
lac = sys.modules["raio_x.lacunas"]
lac.avaliar = lambda clientes, folha12, ano, t, r, k=0, prazo_dias=0: []   # assinatura velha
lac._mtime_raiox = 0                                                       # arquivo mudou desde a carga
at.run()
assert not at.exception, at.exception
assert any("Pontos de atenção" in m.value for m in at.markdown), "seção sumiu"
print("ok")
"""
    r = subprocess.run([sys.executable, "-c", roteiro], cwd=raiz, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-2000:]
