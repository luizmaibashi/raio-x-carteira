"""Lacunas: pontos de atenção que o cálculo S × H não mede, disparados por regra determinística.

Lacuna é alerta em texto, não número novo: os números citados vêm da carteira ou do cálculo, e cada regra
cita a premissa que a sustenta (regra 2).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from raio_x.modelo import Cliente, avaliar_carteira
from raio_x.painel import pct

# P20: alerta quando um cliente responde por 30% ou mais da receita (escolha do protótipo, sem fonte legal).
LIMITE_CONCENTRACAO = Decimal("0.30")
# P21: acima de 30 dias de prazo, o recebimento passa da apuração mensal do imposto (art. 10 da LC 214).
PRAZO_ALERTA_DIAS = 30


@dataclass(frozen=True)
class Lacuna:
    id: str
    titulo: str
    texto: str
    premissa: str


def _diferenca(clientes: list[Cliente], folha12, ano: int, t, r, k) -> Decimal:
    res = avaliar_carteira(clientes, folha12, ano, t, r, k)
    return res.prestador_h - res.prestador_s


def concentracao(clientes: list[Cliente], folha12, ano: int, t, r, k=0) -> Lacuna | None:
    """P20. Se o maior cliente pesa ≥ 30%, diz quanto pesa e se o veredito depende do crédito dele."""
    total = sum((Decimal(c.valor) for c in clientes), Decimal(0))
    maior = max(clientes, key=lambda c: c.valor)
    fatia = Decimal(maior.valor) / total
    if fatia < LIMITE_CONCENTRACAO:
        return None
    texto = f"{maior.nome} responde por {pct(fatia, 1)} da sua receita. "
    ganho = _diferenca(clientes, folha12, ano, t, r, k)
    if maior.cred and ganho > 0:
        sem_credito = [replace(c, cred=False) if c is maior else c for c in clientes]
        if _diferenca(sem_credito, folha12, ano, t, r, k) <= 0:
            texto += ("Recolher por fora só compensa porque ele usa o crédito: se ele deixar de usar (por exemplo, "
                      "se migrar para o Simples), a conta vira a favor do Simples puro. Confirme o regime dele antes "
                      "de optar.")
            return Lacuna("concentracao", "Sua decisão depende de um cliente", texto, "P20")
    texto += ("Uma mudança nele (preço, regime ou a saída dele) mexe no resultado da carteira inteira: refaça a "
              "conta se algo mudar com esse cliente.")
    return Lacuna("concentracao", "Receita concentrada", texto, "P20")


def prazo_recebimento(prazo_dias: int) -> Lacuna | None:
    """P21 (com P07 e P08). Recolhendo por fora, o imposto nasce na prestação, não no recebimento."""
    if prazo_dias <= PRAZO_ALERTA_DIAS:
        return None
    texto = (f"Recolhendo por fora, o IBS/CBS nasce quando você presta o serviço, não quando recebe. Com {prazo_dias} "
             "dias para receber, você pode ter de pagar o imposto antes de o dinheiro entrar. O cálculo acima não "
             "mede esse efeito no caixa, e o split payment pode mudar essa conta: confira com o seu contador.")
    return Lacuna("prazo", "Imposto antes do dinheiro", texto, "P21")


def avaliar(clientes: list[Cliente], folha12, ano: int, t, r, k=0, prazo_dias: int = 0) -> list[Lacuna]:
    achadas = (concentracao(clientes, folha12, ano, t, r, k), prazo_recebimento(prazo_dias))
    return [x for x in achadas if x is not None]
