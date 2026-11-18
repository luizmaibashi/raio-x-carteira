"""Funções da tela (sem Streamlit), testáveis: cenários de t, tabelas e sensibilidade.

Nenhum número aqui é oficial além de t(2027) (P13): de 2028 em diante t é cenário
informado pelo usuário, e a tela diz isso.
"""
from __future__ import annotations

from decimal import Decimal

from raio_x.modelo import Cliente, ResultadoCarteira, aliquota_t, avaliar_carteira

# P01: IBS em 10/20/30/40% em 2029–2032 e integral em 2033; 2027–28 com IBS de teste (P13).
FRACAO_IBS = {2027: Decimal(0), 2028: Decimal(0), 2029: Decimal("0.1"), 2030: Decimal("0.2"),
              2031: Decimal("0.3"), 2032: Decimal("0.4"), 2033: Decimal(1)}
ANOS = tuple(FRACAO_IBS)


def t_por_ano(t_2033, reducao_30: bool) -> dict[int, Decimal]:
    """2027 oficial (P13). Demais anos: cenário t(ano) = t2027 + fração do IBS × (t2033 − t2027).

    Supõe CBS constante na referência de 2027 e o IBS crescendo pela fração da transição (P01).
    """
    base = aliquota_t(2027)
    t33 = Decimal(str(t_2033))
    cen = {ano: base + f * (t33 - base) for ano, f in FRACAO_IBS.items()}
    return {ano: (aliquota_t(2027, reducao_30) if ano == 2027 else aliquota_t(ano, reducao_30, cen[ano]))
            for ano in ANOS}


def tabela_clientes(res: ResultadoCarteira, cred: dict[str, bool]) -> list[dict]:
    linhas = []
    for nome, x in res.clientes.items():
        linhas.append({
            "Cliente": nome,
            "Toma crédito": "sim" if cred[nome] else "não",
            "Preço hoje (S)": float(x.preco_s),
            "Preço-base em H": float(x.preco_h),
            "Você fica com (S)": float(x.prestador_s),
            "Você fica com (H)": float(x.prestador_h),
            "H − S para você": float(x.ganho_prestador),
            "Custo do cliente: H − S": float(x.variacao_custo_cliente),
        })
    return sorted(linhas, key=lambda l: l["H − S para você"])


def sensibilidade_r(clientes: list[Cliente], folha12, ano: int, t, k=0, passos: int = 10) -> list[dict]:
    out = []
    for i in range(passos + 1):
        r = Decimal(i) / passos
        res = avaliar_carteira(clientes, folha12, ano, t, r, k)
        out.append({"r": float(r), "H − S para você": float(res.prestador_h - res.prestador_s)})
    return out


def brl(v) -> str:
    """Formato brasileiro; negativo começa com "-" (o Streamlit usa isso para a cor do delta)."""
    x = float(v)
    s = f"{abs(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if x < 0 and s != "0,00" else f"R$ {s}"


def pct(v, casas: int = 2) -> str:
    return f"{float(v) * 100:.{casas}f}%".replace(".", ",")
