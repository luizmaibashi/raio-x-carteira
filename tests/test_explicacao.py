"""Explicação por LLM: o verificador barra qualquer número que não saiu do cálculo (regra 1)."""
import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from raio_x.explicacao import ErroExplicacao, gerar, montar_fatos, verificar
from raio_x.modelo import Cliente, aliquota_t

CARTEIRA = [Cliente("Indústria Alfa (sintético)", D(120_000), True), Cliente("Loja Gama (sintético)", D(45_000), False),
            Cliente("Pessoa física Épsilon (sintético)", D(25_000), False)]


def _fatos(r=0):
    return montar_fatos(CARTEIRA, 60_000, 2027, aliquota_t(2027), r)


class Falso:
    """Imita client.beta.messages.create devolvendo respostas prontas, em ordem."""

    def __init__(self, *saidas, stop="end_turn"):
        self.saidas, self.pedidos, self.stop = list(saidas), [], stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.pedidos.append(kw)
        texto = json.dumps(self.saidas.pop(0), ensure_ascii=False)
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=texto)])


def _saida(fatos, resumo):
    return {"resumo": resumo, "clientes": [{"id": i, "argumento": f"{i} aproveita ou não o crédito."}
                                           for i in fatos.nomes]}


def test_fatos_anonimizam_clientes_e_trazem_numeros_formatados():
    f = _fatos()
    pedido = json.dumps(f.dados, ensure_ascii=False)
    assert "Alfa" not in pedido and "Gama" not in pedido          # nomes ficam fora do pedido
    assert f.nomes == {"C1": "Indústria Alfa (sintético)", "C2": "Loja Gama (sintético)",
                       "C3": "Pessoa física Épsilon (sintético)"}
    assert f.dados["melhor_regime"] == "Simples puro"
    assert f.dados["diferenca_anual_por_fora_menos_simples"].startswith("-R$ ")
    assert f.chave == _fatos().chave and f.chave != _fatos(0.5).chave


def test_verificador_aceita_numero_copiado_e_barra_inventado():
    f = _fatos()
    perda = f.dados["diferenca_anual_por_fora_menos_simples"].lstrip("-")
    cred = f.dados["receita_de_clientes_com_credito"]
    assert verificar(f"Por fora custaria {perda} por ano; {cred} da receita tem crédito. Prazo: 20/12/2026.", f) == []
    assert verificar("Por fora custaria uns R$ 5,4 mil.", f) == ["5,4"]
    assert verificar("Isso é 42% do seu lucro.", f) == ["42"]


def test_gera_e_devolve_quando_numeros_conferem():
    f = _fatos()
    falso = Falso(_saida(f, f"O Simples puro deixa {f.dados['fica_com_voce_no_simples_puro']} com você."))
    out = gerar(falso, f)
    assert out["resumo"].startswith("O Simples puro")
    pedido = falso.pedidos[0]
    assert pedido["model"] == "claude-opus-5-5" and pedido["fallbacks"] == "default"
    assert pedido["output_config"]["format"]["type"] == "json_schema"


def test_tenta_de_novo_apontando_o_numero_inventado_e_depois_desiste():
    f = _fatos()
    falso = Falso(_saida(f, "Você perderia 37% da margem."), _saida(f, "Ainda 37%."))
    with pytest.raises(ErroExplicacao, match="37"):
        gerar(falso, f)
    assert "37" in falso.pedidos[1]["messages"][-1]["content"]


def test_segunda_tentativa_corrigida_passa():
    f = _fatos()
    falso = Falso(_saida(f, "Você perderia 37% da margem."), _saida(f, "Fique no Simples puro."))
    assert gerar(falso, f)["resumo"] == "Fique no Simples puro."


def test_recusa_e_clientes_trocados_viram_erro():
    f = _fatos()
    with pytest.raises(ErroExplicacao, match="recusou"):
        gerar(Falso(_saida(f, "x"), stop="refusal"), f)
    errado = {"resumo": "x", "clientes": [{"id": "C9", "argumento": "y"}]}
    with pytest.raises(ErroExplicacao, match="diferem"):
        gerar(Falso(errado), f)


ARQ = __import__("pathlib").Path(__file__).resolve().parent.parent / "dados" / "explicacoes_ia.json"


@pytest.mark.skipif(not ARQ.exists(), reason="explicações ainda não gravadas")
def test_explicacoes_gravadas_conferem_com_o_calculo_atual():
    """Toda explicação gravada vale para um perfil no cenário inicial e só cita números do cálculo."""
    from scripts.gerar_explicacoes import fatos_do_perfil
    perfis = json.loads((ARQ.parent / "exemplos" / "perfis.json").read_text(encoding="utf-8"))
    gravadas = json.loads(ARQ.read_text(encoding="utf-8"))
    fatos = {fatos_do_perfil(p).chave: fatos_do_perfil(p) for p in perfis}
    assert set(gravadas) == set(fatos), "regrave com scripts/gerar_explicacoes.py: o cálculo mudou"
    for chave, g in gravadas.items():
        texto = g["resumo"] + " " + " ".join(c["argumento"] for c in g["clientes"])
        assert verificar(texto, fatos[chave]) == [], g["perfil"]
        assert {c["id"] for c in g["clientes"]} == set(fatos[chave].nomes)


@pytest.mark.skipif(not ARQ.exists(), reason="explicações ainda não gravadas")
@pytest.mark.parametrize("perfil", ["Designer", "Consultora de TI", "Contador"])
def test_tela_mostra_explicacao_gravada_do_perfil(perfil, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(ARQ.parent.parent / "app.py"), default_timeout=30).run()
    at.selectbox(key="perfil").set_value(perfil).run()
    assert not at.exception, at.exception
    assert any("Texto escrito por IA" in c.value for c in at.caption)
