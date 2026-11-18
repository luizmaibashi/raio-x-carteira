"""Cliente das APIs da Receita: unidade com servidor falso; integração se as APIs estiverem no ar."""
import json
import threading
import urllib.error
import urllib.request
from decimal import Decimal as D
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from raio_x.das import calcular
from raio_x.modelo import aliquota_t
from raio_x.receita import ClienteReceita, ErroReceita, URL_REGULAR, URL_SIMPLES


class _Falso(BaseHTTPRequestHandler):
    respostas: dict = {}
    pedidos: list = []

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).pedidos.append((self.path, corpo))
        status, resp = type(self).respostas[self.path]
        dados = json.dumps(resp).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *a):
        pass


@pytest.fixture
def falso():
    _Falso.respostas, _Falso.pedidos = {}, []
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/api"
    yield ClienteReceita(url, url, timeout=5), _Falso
    srv.shutdown()


SN = "/api/calculadora/observabilidade/simples-nacional"


def _resp_sn(vbc, pc, pi, vc, vi):
    return {"objetos": [{"estadoItem": "CALCULADO", "tribCalc": {
        "vBC": vbc, "pCBSSN": pc, "pIBSSN": pi, "vCBSSN": vc, "vIBSSN": vi}}]}


def test_monta_pedido_do_simples_com_4_casas(falso):
    cli, f = falso
    f.respostas[SN] = (200, _resp_sn("10000.00", "1.3663", "0.0154", "136.63", "1.54"))
    das = calcular(300_000, 90_000, 2027)   # pCBSSN 1,366328 -> 1,3663
    conf = cli.conferir_das(das, "2027-03-10", "10000")
    path, corpo = f.pedidos[0]
    assert corpo["itens"][0]["pCBSSN"] == "1.3663" and corpo["itens"][0]["cAtivSN"] == "09"
    assert conf.ok, conf.divergencias


def test_conferencia_acusa_divergencia(falso):
    cli, f = falso
    f.respostas[SN] = (200, _resp_sn("10000.00", "1.3663", "0.0154", "136.64", "1.54"))
    conf = cli.conferir_das(calcular(300_000, 90_000, 2027), "2027-03-10", "10000")
    assert not conf.ok and "CBS" in conf.divergencias[0]


def test_erro_422_vira_erro_receita_com_codigo(falso):
    cli, f = falso
    f.respostas[SN] = (422, {"title": "Erros", "errors": [{"code": "VSN-018", "detail": "CRT incompatível"}]})
    with pytest.raises(ErroReceita, match="VSN-018") as e:
        cli.calcular_simples("2027-03-10", 100, 1, 0)
    assert e.value.status == 422


def test_api_fora_do_ar():
    with pytest.raises(ErroReceita, match="indisponível"):
        ClienteReceita("http://127.0.0.1:9/api", "http://127.0.0.1:9/api", timeout=1).calcular_simples(
            "2027-03-10", 100, 1, 0)


# ---- integração com as calculadoras locais ---------------------------------
def _no_ar(url):
    try:
        urllib.request.urlopen(url + "/", timeout=1)
        return True
    except urllib.error.HTTPError:   # servidor respondeu (404 na raiz): está no ar
        return True
    except Exception:
        return False


integracao = pytest.mark.skipif(not (_no_ar(URL_REGULAR) and _no_ar(URL_SIMPLES)),
                                reason="APIs da Receita fora do ar (portas 8080/8082)")


@integracao
@pytest.mark.parametrize("rbt12,folha,ano", [
    (120_000, 40_000, 2027), (300_000, 90_000, 2027), (300_000, 30_000, 2027),
    (3_600_000, 1_200_000, 2027), (1_000_000, 300_000, 2027), (2_000_000, 600_000, 2027)])
def test_motor_do_simples_confere_com_modulo_das(rbt12, folha, ano):
    conf = ClienteReceita().conferir_das(calcular(rbt12, folha, ano), f"{ano}-03-10", "12345.67")
    assert conf.ok, conf.divergencias


@integracao
@pytest.mark.parametrize("reducao", [False, True])
def test_motor_regular_confere_t_2027(reducao):
    r = ClienteReceita().calcular_regular("2027-03-10T10:00:00-03:00", 10_000, 5002704, "MS", reducao_30=reducao)
    assert r.aliquota_total == aliquota_t(2027, reducao_30=reducao)
