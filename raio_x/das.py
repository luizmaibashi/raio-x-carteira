"""Alíquota efetiva do DAS e partilha de CBS/IBS (Anexos III e V, 2027-2033).

Determinístico, sem LLM. Tabelas em dados/anexos_simples.json (gerado por
scripts/gerar_anexos.py a partir do texto oficial). Unidades: percentuais em Decimal
(Decimal("6.00") = 6%). Valores monetários em reais.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

ARQUIVO_ANEXOS = Path(__file__).resolve().parent.parent / "dados" / "anexos_simples.json"

FATOR_R_MINIMO = Decimal("0.28")          # P12: atividade 09 sujeita ao Fator R; >= 28% -> Anexo III
TETO_ESCOPO_RBT12 = Decimal("3600000")    # Desenho, passo 6: 6ª faixa (sublimite) fora do protótipo
ANOS = range(2027, 2034)                  # P01/P18: tabelas de 2027 a 2033
TOLERANCIA_PGDAS = Decimal("0.01")        # Desenho, passo 8: diferença > 0,01 p.p. vira alerta
CEM = Decimal(100)


class ForaDoEscopo(ValueError):
    """Entrada fora do que o protótipo calcula. Nunca devolvemos número aproximado (regra 4)."""


@dataclass(frozen=True)
class ResultadoDAS:
    anexo: str
    fator_r: Decimal
    faixa: int
    aliquota_nominal: Decimal
    parcela_deduzir: Decimal
    aliquota_efetiva: Decimal            # a
    partilha: dict[str, Decimal]         # tributo -> alíquota efetiva sobre a receita (%)
    teto_iss_aplicado: bool
    premissas: tuple[str, ...] = field(default=())

    @property
    def p_cbs_sn(self) -> Decimal:       # pCBSSN (P15)
        return self.partilha.get("CBS", Decimal(0))

    @property
    def p_ibs_sn(self) -> Decimal:       # pIBSSN (P15)
        return self.partilha.get("IBS", Decimal(0))

    @property
    def c(self) -> Decimal:              # fatia CBS + IBS dentro de a
        return self.p_cbs_sn + self.p_ibs_sn


@lru_cache(maxsize=1)
def carregar_anexos(caminho: Path = ARQUIVO_ANEXOS) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"), parse_float=Decimal)


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def periodo_partilha(ano: int) -> str:
    """P18: 2027-28 compartilham tabela; 2029 a 2033 têm uma cada."""
    return "2027-2028" if ano in (2027, 2028) else str(ano)


def vigencia_aliquotas(ano: int) -> str:
    """P14: tabela de alíquotas 2027-28; outra a partir de 2029 (muda só a 6ª faixa)."""
    return "2027-2028" if ano in (2027, 2028) else "2029+"


def fator_r(rbt12, folha12) -> Decimal:
    rbt12, folha12 = _d(rbt12), _d(folha12)
    if rbt12 <= 0:
        raise ForaDoEscopo("RBT12 precisa ser positiva para calcular o Fator R")
    if folha12 < 0:
        raise ForaDoEscopo("folha dos 12 meses não pode ser negativa")
    return folha12 / rbt12


def anexo_por_fator_r(fr: Decimal) -> str:
    """P12: Fator R >= 28% -> Anexo III; abaixo -> Anexo V (fronteira inclusiva)."""
    return "III" if fr >= FATOR_R_MINIMO else "V"


def faixa(tabela: list[dict], rbt12: Decimal) -> dict:
    """P14: faixa pela RBT12; limite superior da faixa é inclusivo (até 180.000,00)."""
    for f in tabela:
        if rbt12 <= _d(f["rbt12_max"]):
            return f
    raise ForaDoEscopo("RBT12 acima de R$ 4,8 milhões: empresa fora do Simples")


def calcular(rbt12, folha12, ano: int, dados: dict | None = None) -> ResultadoDAS:
    rbt12 = _d(rbt12)
    if ano not in ANOS:
        raise ForaDoEscopo(f"ano {ano} fora de 2027-2033")
    fr = fator_r(rbt12, folha12)
    if rbt12 > TETO_ESCOPO_RBT12:
        raise ForaDoEscopo(
            "RBT12 acima de R$ 3,6 milhões: sublimite (ISS e IBS fora do DAS) não é coberto pelo protótipo")
    dados = dados or carregar_anexos()
    anexo = anexo_por_fator_r(fr)
    tab = dados["anexos"][anexo]
    f = faixa(tab["aliquotas"][vigencia_aliquotas(ano)], rbt12)
    nominal, pd = _d(f["aliquota_nominal"]), _d(f["parcela_deduzir"])

    # P15: a = (RBT12 x Aliq - PD) / RBT12; na 1ª faixa PD = 0 e a = nominal.
    a = (rbt12 * nominal / CEM - pd) / rbt12 * CEM

    periodo = periodo_partilha(ano)
    linha = next(l for l in tab["partilha"][periodo] if l["faixa"] == f["faixa"])
    teto = tab.get("teto_iss_5a_faixa", {}).get(periodo)
    premissas = ["P12", "P14", "P15", "P18"]
    if teto and f["faixa"] == 5 and a > _d(teto["limiar_aliquota_efetiva"]):
        # P16: ISS limitado a 5%; (a - 5%) repartido entre os demais pela tabela da nota (*).
        # A partir de 2029 o texto fixa ISS + IBS = 5% (ex.: 4,5% + 0,5% em 2029).
        partilha = {t: _d(v) for t, v in teto["fixo"].items()}
        partilha.update({t: (a - 5) * _d(p) / CEM for t, p in teto["proporcional"].items()})
        aplicado = True
        premissas.append("P16")
    else:
        partilha = {t: a * _d(p) / CEM for t, p in linha.items() if t != "faixa"}
        aplicado = False
    return ResultadoDAS(anexo, fr, f["faixa"], nominal, pd, a, partilha, aplicado, tuple(premissas))


def comparar_pgdas(resultado: ResultadoDAS, pgdas_aliquota) -> str | None:
    """Opção C do desenho: alerta se a alíquota do PGDAS diverge mais de 0,01 p.p."""
    dif = _d(pgdas_aliquota) - resultado.aliquota_efetiva
    if abs(dif) <= TOLERANCIA_PGDAS:
        return None
    return (f"Alíquota do PGDAS ({_d(pgdas_aliquota):.2f}%) difere da calculada "
            f"({resultado.aliquota_efetiva:.2f}%) em {dif:+.2f} p.p.; confira Fator R, RBT12 "
            f"e segregação de receitas.")
