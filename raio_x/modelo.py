"""Modelo econômico S × H por cliente e por carteira (MODELO_ECONOMICO.md).

S = Simples puro (IBS/CBS dentro do DAS); H = IBS/CBS por fora (regime regular).
Determinístico. Grandezas em fração (Decimal("0.113") = 11,3%), valores em reais.

Fora do modelo (limitações registradas, sem número): efeito de caixa do split
payment e do prazo de recebimento (P07, P08); IR do sócio; mudança de faixa do
Simples causada pelo novo preço em H (a e c ficam os do RBT12 informado).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from raio_x.das import ForaDoEscopo, calcular

CEM = Decimal(100)
# P13: CBS de referência 2027 = 11,3% (TCU), com IBS de teste de 0,1% e CBS −0,1 p.p.
# Parâmetro até a resolução do Senado (prazo 15/12/2026). Outros anos: sem alíquota
# de referência publicada, o chamador informa t como cenário.
T_REFERENCIA = {2027: Decimal("0.113")}
# P06/P11: redução de 30% para profissão intelectual regulamentada (cClassTrib 200052).
REDUCAO_PROFISSAO = Decimal("0.30")


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def aliquota_t(ano: int, reducao_30: bool = False, cenario=None) -> Decimal:
    """t do ano: referência oficial (P13) ou cenário explícito; nunca valor inventado (regra 4)."""
    if cenario is not None:
        t = _d(cenario)
    elif ano in T_REFERENCIA:
        t = T_REFERENCIA[ano]
    else:
        raise ForaDoEscopo(f"sem alíquota de referência de CBS+IBS para {ano}: informe um cenário")
    if t < 0:
        raise ForaDoEscopo("t não pode ser negativa")
    return t * (1 - REDUCAO_PROFISSAO) if reducao_30 else t


def preco_equilibrio(p, cred: bool, c, t) -> Decimal:
    """Q* que deixa o cliente indiferente entre S e H."""
    p, c, t = _d(p), _d(c), _d(t)
    return p * (1 - c) if cred else p / (1 + t)


def preco_h(p, cred: bool, c, t, r) -> Decimal:
    """Q(r) = Q* + r (P − Q*); r = 0 cliente indiferente, r = 1 prestador mantém P."""
    r = _d(r)
    if not 0 <= r <= 1:
        raise ForaDoEscopo("poder de preço r deve estar entre 0 e 1")
    q = preco_equilibrio(p, cred, c, t)
    return q + r * (_d(p) - q)


@dataclass(frozen=True)
class ResultadoCliente:
    preco_s: Decimal
    preco_h: Decimal              # Q, sem o tributo destacado
    preco_equilibrio: Decimal     # Q*
    prestador_s: Decimal
    prestador_h: Decimal
    cliente_s: Decimal            # custo líquido do cliente
    cliente_h: Decimal
    tributo_por_fora: Decimal     # t·Q recolhido pelo prestador em H
    credito_cliente_h: Decimal

    @property
    def ganho_prestador(self) -> Decimal:   # H − S
        return self.prestador_h - self.prestador_s

    @property
    def variacao_custo_cliente(self) -> Decimal:  # H − S
        return self.cliente_h - self.cliente_s


def resultado_cliente(p, cred: bool, a, c, t, r, k=0) -> ResultadoCliente:
    p, a, c, t, k = _d(p), _d(a), _d(c), _d(t), _d(k)
    if p < 0:
        raise ForaDoEscopo("preço negativo")
    q = preco_h(p, cred, c, t, r)
    imposto = t * q
    credito_h = imposto if cred else Decimal(0)
    return ResultadoCliente(
        preco_s=p, preco_h=q, preco_equilibrio=preco_equilibrio(p, cred, c, t),
        prestador_s=p * (1 - a),
        # P17: em H o DAS perde a fatia c e o tributo por fora não entra na receita bruta.
        prestador_h=q * (1 - a + c) + k,
        # P04: em S o cliente com crédito aproveita só o IBS/CBS contido no DAS (c).
        cliente_s=p * (1 - (c if cred else 0)),
        # P05: cliente do regime regular credita o tributo destacado.
        cliente_h=q * (1 + t) - credito_h,
        tributo_por_fora=imposto, credito_cliente_h=credito_h,
    )


@dataclass(frozen=True)
class Cliente:
    nome: str          # rótulo sintético (regra 5)
    valor: Decimal     # faturamento anual atual (P_i)
    cred: bool


@dataclass(frozen=True)
class ResultadoCarteira:
    ano: int
    a: Decimal
    c: Decimal
    t: Decimal
    r: Decimal
    clientes: dict[str, ResultadoCliente]
    prestador_s: Decimal
    prestador_h: Decimal
    peso_sem_credito: Decimal
    indiferenca_peso_com_credito: Decimal | None  # fração mínima da receita com crédito para H ≥ S

    @property
    def melhor(self) -> str:
        return "H" if self.prestador_h > self.prestador_s else "S"


def _ganho_unitario(cred: bool, a, c, t, r) -> Decimal:
    res = resultado_cliente(1, cred, a, c, t, r)
    return res.ganho_prestador


def peso_indiferenca(a, c, t, r, k_por_real=0) -> Decimal | None:
    """Fração s da receita vinda de clientes com crédito em que H = S.

    O ganho por real é linear em s: s·g_cred + (1−s)·g_sem + k = 0. Devolve None se
    H ganha (ou perde) em qualquer composição de carteira.
    """
    g1, g0 = _ganho_unitario(True, a, c, t, r), _ganho_unitario(False, a, c, t, r)
    k = _d(k_por_real)
    if g1 == g0:
        return None
    s = -(g0 + k) / (g1 - g0)
    return s if 0 <= s <= 1 else None


def avaliar_carteira(clientes: list[Cliente], folha12, ano: int, t, r, k=0) -> ResultadoCarteira:
    """a e c vêm do módulo DAS com RBT12 = soma da carteira (P14, P15)."""
    if not clientes:
        raise ForaDoEscopo("carteira vazia")
    rbt12 = sum((_d(cl.valor) for cl in clientes), Decimal(0))
    das = calcular(rbt12, folha12, ano)
    a, c, t, r, k = das.aliquota_efetiva / CEM, das.c / CEM, _d(t), _d(r), _d(k)
    res = {}
    for cl in clientes:
        if cl.nome in res:
            raise ForaDoEscopo(f"cliente repetido: {cl.nome}")
        # K (créditos das compras do prestador em H) repartido pela receita de cada cliente.
        res[cl.nome] = resultado_cliente(cl.valor, cl.cred, a, c, t, r, k * _d(cl.valor) / rbt12)
    sem = sum((_d(cl.valor) for cl in clientes if not cl.cred), Decimal(0))
    return ResultadoCarteira(
        ano=ano, a=a, c=c, t=t, r=r, clientes=res,
        prestador_s=sum((x.prestador_s for x in res.values()), Decimal(0)),
        prestador_h=sum((x.prestador_h for x in res.values()), Decimal(0)),
        peso_sem_credito=sem / rbt12,
        indiferenca_peso_com_credito=peso_indiferenca(a, c, t, r, k / rbt12),
    )


def linha_do_tempo(clientes: list[Cliente], folha12, t_por_ano: dict[int, object], r, k=0):
    """Avalia cada ano informado; devolve resultados e o primeiro ano em que a decisão troca."""
    anos = sorted(t_por_ano)
    resultados = [avaliar_carteira(clientes, folha12, ano, t_por_ano[ano], r, k) for ano in anos]
    virada = next((b.ano for x, b in zip(resultados, resultados[1:]) if x.melhor != b.melhor), None)
    return resultados, virada
