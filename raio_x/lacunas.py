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
            # Texto sem pronome de gênero: o nome do cliente pode ser masculino ou feminino.
            texto += ("Recolher por fora só compensa porque esse cliente usa o crédito: se deixar de usar (por "
                      "exemplo, se migrar para o Simples), a conta vira a favor do Simples puro. Confirme o regime "
                      "desse cliente antes de optar.")
            return Lacuna("concentracao", "Sua decisão depende de um cliente", texto, "P20")
    texto += ("Qualquer mudança nesse cliente (preço, regime ou saída) mexe no resultado da carteira inteira: "
              "refaça a conta se algo mudar.")
    return Lacuna("concentracao", "Receita concentrada", texto, "P20")


def prazo_recebimento(prazo_dias: int) -> Lacuna | None:
    """P21 (com P07 e P08). Recolhendo por fora, o imposto nasce na prestação, não no recebimento."""
    if prazo_dias <= PRAZO_ALERTA_DIAS:
        return None
    texto = (f"Recolhendo por fora, o IBS/CBS nasce quando você presta o serviço, não quando recebe. Com {prazo_dias} "
             "dias para receber, você pode ter de pagar o imposto antes de o dinheiro entrar. O cálculo acima não "
             "mede esse efeito no caixa, e o split payment pode mudar essa conta: confira com o seu contador.")
    return Lacuna("prazo", "Imposto antes do dinheiro", texto, "P21")


def repasse_em_contrato(r) -> Lacuna | None:
    """P09. Manter parte do preço supõe que o cliente aceite: contrato privado não se reajusta sozinho."""
    if Decimal(str(r)) <= 0:
        return None
    texto = (f"O resultado supõe que você mantém {pct(Decimal(str(r)), 0)} do preço, ou seja, que o cliente aceita "
             "pagar parte do imposto novo. Contrato não se reajusta sozinho com a reforma: isso depende de uma "
             "cláusula de repasse ou de negociação. Confira o que os seus contratos dizem.")
    return Lacuna("repasse", "Preço depende do contrato", texto, "P09")


def reducao_nao_marcada(clientes: list[Cliente], folha12, ano: int, t, t_com_reducao, r, k=0,
                        marcada: bool = False) -> Lacuna | None:
    """P06. Avisa só quando a redução de 30% viraria a resposta a favor de recolher por fora."""
    if marcada or t_com_reducao is None:
        return None
    if _diferenca(clientes, folha12, ano, t, r, k) > 0 or _diferenca(clientes, folha12, ano, t_com_reducao, r, k) <= 0:
        return None
    texto = ("Se a sua profissão é regulamentada (contador, economista, advogado e outras) e você tem registro no "
             "conselho, o IBS/CBS por fora pode ter redução de 30%. Com ela, recolher por fora passa a compensar "
             "nesta carteira. Marque a opção na barra lateral e confirme a elegibilidade com o seu contador.")
    return Lacuna("reducao_30", "A redução de 30% mudaria a resposta", texto, "P06")


def avaliar(clientes: list[Cliente], folha12, ano: int, t, r, k=0, prazo_dias: int = 0, t_com_reducao=None,
            reducao_marcada: bool = False) -> list[Lacuna]:
    achadas = (concentracao(clientes, folha12, ano, t, r, k), prazo_recebimento(prazo_dias), repasse_em_contrato(r),
               reducao_nao_marcada(clientes, folha12, ano, t, t_com_reducao, r, k, reducao_marcada))
    return [x for x in achadas if x is not None]
