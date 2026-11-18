"""Cliente HTTP das calculadoras da Receita (rodam como serviços separados, regra 6).

- Regime regular (porta 8080): POST /api/calculadora/regime-geral
- Simples Nacional (porta 8082): POST /api/calculadora/observabilidade/simples-nacional
Endereços configuráveis por RECEITA_REGULAR_URL e RECEITA_SIMPLES_URL.

Só biblioteca padrão. Os números vêm do motor da Receita; aqui só montamos o pedido,
lemos a resposta e conferimos contra o cálculo próprio (passo 7 do DESENHO_MODULO_DAS).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from raio_x.das import ResultadoDAS

URL_REGULAR = os.environ.get("RECEITA_REGULAR_URL", "http://localhost:8080/api")
URL_SIMPLES = os.environ.get("RECEITA_SIMPLES_URL", "http://localhost:8082/api")
CENTAVO = Decimal("0.01")
CASAS_PERCENTUAL_SN = Decimal("0.0001")  # o motor do Simples lê pCBSSN/pIBSSN com 4 casas

# P13: 2027 = CBS de referência 11,3% − 0,1 p.p. + IBS de teste 0,05% UF + 0,05% município.
ALIQUOTAS_NOMINAIS_2027 = {"cbs": Decimal("11.2"), "ibsEstadual": Decimal("0.05"),
                           "ibsMunicipal": Decimal("0.05")}
# P11: consultoria em gestão financeira; CST 200 / cClassTrib 200052 = redução de 30%.
NBS_CONSULTORIA = "114011200"
CLASS_INTEGRAL = ("000", "000001")
CLASS_REDUCAO_30 = ("200", "200052")
# P12: atividade 09 do Simples (sujeita ao Fator R); documento 91 = NFS-e.
ATIVIDADE_SN, TPDOC_NFSE, CRT_SIMPLES = "09", "91", "1"


class ErroReceita(RuntimeError):
    def __init__(self, msg: str, status: int | None = None, erros: list | None = None):
        super().__init__(msg)
        self.status, self.erros = status, erros or []


def _post(url: str, corpo: dict, timeout: float) -> dict:
    dados = json.dumps(corpo, default=str).encode()
    req = urllib.request.Request(url, data=dados, method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(), parse_float=Decimal)
    except urllib.error.HTTPError as e:
        try:
            det = json.loads(e.read())
        except ValueError:
            det = {}
        erros = det.get("errors", [])
        resumo = "; ".join(f"{x.get('code', '')} {x.get('detail', '')}".strip() for x in erros) or det.get("detail", "")
        raise ErroReceita(f"API respondeu {e.code}: {det.get('title', '')} {resumo}".strip(), e.code, erros) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ErroReceita(f"API da Receita indisponível em {url}: {e}") from None


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class CalculoSimples:
    base: Decimal
    p_cbs_sn: Decimal
    p_ibs_sn: Decimal
    v_cbs_sn: Decimal
    v_ibs_sn: Decimal


@dataclass(frozen=True)
class CalculoRegular:
    base: Decimal
    v_cbs: Decimal
    v_ibs: Decimal

    @property
    def aliquota_total(self) -> Decimal:   # t efetiva devolvida pelo motor, em fração
        return (self.v_cbs + self.v_ibs) / self.base


@dataclass(frozen=True)
class Conferencia:
    ok: bool
    motor: CalculoSimples
    esperado_cbs: Decimal
    esperado_ibs: Decimal
    divergencias: tuple[str, ...]


def no_ar(url: str = URL_SIMPLES, timeout: float = 1) -> bool:
    """O motor responde? Qualquer resposta HTTP conta (a raiz devolve 404)."""
    try:
        urllib.request.urlopen(url.rstrip("/") + "/", timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


class ClienteReceita:
    def __init__(self, url_regular: str = URL_REGULAR, url_simples: str = URL_SIMPLES, timeout: float = 10):
        self.url_regular, self.url_simples, self.timeout = url_regular.rstrip("/"), url_simples.rstrip("/"), timeout

    # ---- Simples Nacional -------------------------------------------------
    def calcular_simples(self, data: str, base, p_cbs_sn, p_ibs_sn) -> CalculoSimples:
        base = _d(base).quantize(CENTAVO)
        pc = _d(p_cbs_sn).quantize(CASAS_PERCENTUAL_SN, ROUND_HALF_UP)
        pi = _d(p_ibs_sn).quantize(CASAS_PERCENTUAL_SN, ROUND_HALF_UP)
        corpo = {"id": "raio-x", "versao": "1.0.0", "data": data, "tpDoc": TPDOC_NFSE, "CRT": CRT_SIMPLES,
                 "itens": [{"numero": 1, "cAtivSN": ATIVIDADE_SN, "cClassTrib": CLASS_INTEGRAL[1],
                            "baseCalculo": str(base), "valorImpostoSeletivo": "0.00",
                            "pIBSSN": str(pi), "pCBSSN": str(pc)}]}
        resp = _post(f"{self.url_simples}/calculadora/observabilidade/simples-nacional", corpo, self.timeout)
        try:
            item = resp["objetos"][0]
            if item.get("estadoItem") != "CALCULADO":
                raise ErroReceita(f"item não calculado: {item.get('estadoItem')}")
            t = item["tribCalc"]
            return CalculoSimples(_d(t["vBC"]), _d(t["pCBSSN"]), _d(t["pIBSSN"]), _d(t["vCBSSN"]), _d(t["vIBSSN"]))
        except (KeyError, IndexError, TypeError) as e:
            raise ErroReceita(f"resposta do Simples fora do formato esperado ({e})") from None

    def conferir_das(self, das: ResultadoDAS, data: str, base) -> Conferencia:
        """Passo 7 do desenho: o motor tem de chegar ao mesmo valor de CBS/IBS que o cálculo próprio."""
        motor = self.calcular_simples(data, base, das.p_cbs_sn, das.p_ibs_sn)
        pc = das.p_cbs_sn.quantize(CASAS_PERCENTUAL_SN, ROUND_HALF_UP)
        pi = das.p_ibs_sn.quantize(CASAS_PERCENTUAL_SN, ROUND_HALF_UP)
        esp_c = (motor.base * pc / 100).quantize(CENTAVO, ROUND_HALF_UP)
        esp_i = (motor.base * pi / 100).quantize(CENTAVO, ROUND_HALF_UP)
        div = []
        if motor.v_cbs_sn != esp_c:
            div.append(f"CBS: motor {motor.v_cbs_sn}, cálculo próprio {esp_c}")
        if motor.v_ibs_sn != esp_i:
            div.append(f"IBS: motor {motor.v_ibs_sn}, cálculo próprio {esp_i}")
        if (motor.p_cbs_sn, motor.p_ibs_sn) != (pc, pi):
            div.append(f"percentuais devolvidos ({motor.p_cbs_sn}, {motor.p_ibs_sn}) diferem dos enviados ({pc}, {pi})")
        return Conferencia(not div, motor, esp_c, esp_i, tuple(div))

    # ---- Regime regular ---------------------------------------------------
    def calcular_regular(self, data_hora: str, base, municipio: int, uf: str, reducao_30: bool = False,
                         aliquotas: dict | None = None, nbs: str = NBS_CONSULTORIA) -> CalculoRegular:
        aliq = aliquotas or ALIQUOTAS_NOMINAIS_2027
        cst, ccl = CLASS_REDUCAO_30 if reducao_30 else CLASS_INTEGRAL
        corpo = {"id": "raio-x", "versao": "1.0.0", "dhFatoGerador": data_hora, "municipio": municipio, "uf": uf,
                 "itens": [{"numero": 1, "nbs": nbs, "cst": cst, "cClassTrib": ccl,
                            "baseCalculo": _d(base).quantize(CENTAVO),
                            "aliquotasNominais": {k: _d(v) for k, v in aliq.items()}}]}
        resp = _post(f"{self.url_regular}/calculadora/regime-geral", corpo, self.timeout)
        try:
            tot = resp["total"]["tribCalc"]["IBSCBSTot"]
            return CalculoRegular(_d(tot["vBCIBSCBS"]), _d(tot["gCBS"]["vCBS"]), _d(tot["gIBS"]["vIBS"]))
        except (KeyError, TypeError) as e:
            raise ErroReceita(f"resposta do regime regular fora do formato esperado ({e})") from None
