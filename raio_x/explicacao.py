"""Explicação em linguagem de dono, escrita por LLM, com todo número conferido contra o cálculo (regra 1).

Fluxo:
1. `montar_fatos` calcula, de forma determinística, tudo o que o texto pode citar, já formatado.
2. O LLM recebe só esses fatos (clientes anonimizados como C1, C2...) e devolve JSON.
3. `verificar` extrai cada número do texto e exige que ele exista nos fatos. Texto com número
   fora dos fatos é descartado: nunca chega à tela.

O LLM não calcula nada. Ele escolhe o que dizer e como dizer.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from raio_x.das import calcular
from raio_x.modelo import Cliente, avaliar_carteira, poder_de_preco_indiferenca
from raio_x.painel import brl, pct

# Gemini estável mais barato na lista oficial (US$ 0,25 / 1,50 por milhão de tokens; consultada em 18/11/2026).
MODELO = "gemini-3.1-flash-lite"
# P03: cancelamento da opção pelo regime regular de IBS/CBS no 1º semestre de 2027.
PRAZO_CANCELAMENTO = "20/12/2026"

ESQUEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string"},
        "clientes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "argumento": {"type": "string"}},
                "required": ["id", "argumento"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["resumo", "clientes"],
    "additionalProperties": False,
}

SISTEMA = """Você escreve para um prestador de serviço do Simples Nacional que vende para empresas, em português do Brasil, \
com frases curtas e sem jargão. Ele quer saber se fica no Simples puro ou se passa a recolher IBS/CBS por fora \
(regime regular de IBS/CBS dentro do Simples), cliente a cliente.

Regras que não se negociam:
- Use só os números que aparecem nos FATOS, copiados exatamente como estão escritos (mesmo formato, mesmas casas). \
Não arredonde, não some, não calcule porcentagens, não escreva números por extenso, não invente prazos nem alíquotas.
- Se precisar de um número que não está nos fatos, descreva sem número.
- Refira-se aos clientes só pelo id (C1, C2...); a tela troca pelo nome.
- Não prometa resultado. Termine o resumo lembrando de levar a decisão ao contador.

Entregue:
- "resumo": 3 a 5 frases explicando o veredito e por que ele acontece nesta carteira (crédito dos clientes e \
quanto do preço o prestador consegue manter).
- "clientes": para cada cliente, 1 ou 2 frases de argumento para conversar com ele sobre preço caso o prestador \
passe a recolher por fora. Para quem aproveita o crédito, mostre que o custo dele quase não muda; para quem não \
aproveita, seja honesto sobre o aumento ou sobre a margem que o prestador perde."""


class ErroExplicacao(RuntimeError):
    pass


@dataclass(frozen=True)
class Fatos:
    dados: dict            # o que vai para o LLM (sem nomes de clientes)
    nomes: dict[str, str]  # id -> nome exibido na tela (fica fora do pedido)

    @property
    def chave(self) -> str:
        """Identifica o cenário: explicação gravada só vale para os mesmos fatos."""
        return hashlib.sha256(json.dumps(self.dados, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def montar_fatos(clientes: list[Cliente], folha12, ano: int, t, r, k=0, reducao_30: bool = False) -> Fatos:
    res = avaliar_carteira(clientes, folha12, ano, t, r, k)
    das = calcular(sum(c.valor for c in clientes), folha12, ano)
    r_virada = poder_de_preco_indiferenca(clientes, folha12, ano, t, k)
    ganho = res.prestador_h - res.prestador_s
    s = res.indiferenca_peso_com_credito
    ordem = sorted(clientes, key=lambda c: c.valor, reverse=True)
    nomes = {f"C{i}": c.nome for i, c in enumerate(ordem, 1)}
    por_cliente = []
    for i, c in enumerate(ordem, 1):
        x = res.clientes[c.nome]
        por_cliente.append({
            "id": f"C{i}", "faturado_12_meses": brl(c.valor), "aproveita_credito": "sim" if c.cred else "não",
            "diferenca_para_voce_por_fora": brl(x.ganho_prestador),
            "preco_por_fora_sem_imposto": brl(x.preco_h),
            "custo_do_cliente_muda_em": brl(x.variacao_custo_cliente),
        })
    dados = {
        "ano": str(ano),
        "melhor_regime": "IBS/CBS por fora" if ganho > 0 else ("Simples puro" if ganho < 0 else "empate"),
        "diferenca_anual_por_fora_menos_simples": brl(ganho),
        "fica_com_voce_no_simples_puro": brl(res.prestador_s),
        "fica_com_voce_recolhendo_por_fora": brl(res.prestador_h),
        "parte_do_preco_que_voce_mantem": pct(r, 0),
        "receita_de_clientes_com_credito": pct(1 - res.peso_sem_credito, 1),
        "receita_com_credito_minima_para_compensar": pct(s, 1) if s is not None else "não se aplica",
        "parte_do_preco_a_manter_para_compensar": pct(r_virada, 0) if r_virada is not None else "não se aplica",
        "aliquota_ibs_cbs_por_fora": pct(t) + (" (com redução de 30%)" if reducao_30 else ""),
        "aliquota_efetiva_do_das": pct(res.a),
        "ibs_cbs_dentro_do_das": pct(res.c, 3),
        "anexo_do_simples": das.anexo,
        "numero_de_clientes": str(len(clientes)),
        "prazo_para_cancelar_a_opcao": PRAZO_CANCELAMENTO,
        "clientes": por_cliente,
    }
    return Fatos(dados, nomes)


# Número no texto: "R$ 5.450,83", "98,9%", "2027", "20/12/2026" (vira 20, 12, 2026), "C3" (vira 3).
_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


def _normaliza(tok: str) -> Decimal | None:
    s = tok
    if "," in s:                      # formato brasileiro: ponto de milhar, vírgula decimal
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s.replace(".", "")        # "5.450" é milhar, não decimal
    try:
        return Decimal(s).normalize()
    except InvalidOperation:
        return None


def numeros(texto: str) -> set[Decimal]:
    return {n for n in (_normaliza(t) for t in _NUMERO.findall(texto)) if n is not None}


def permitidos(fatos: Fatos) -> set[Decimal]:
    ok = numeros(json.dumps(fatos.dados, ensure_ascii=False))
    # Ids dos clientes e o "1º semestre" do prazo (P03).
    ok |= {Decimal(i).normalize() for i in range(1, len(fatos.nomes) + 1)}
    return ok


def verificar(texto: str, fatos: Fatos) -> list[str]:
    """Números do texto que não existem nos fatos. Lista vazia = texto aprovado."""
    ok = permitidos(fatos)
    return sorted({t for t in _NUMERO.findall(texto) if _normaliza(t) not in ok})


def _texto_completo(saida: dict) -> str:
    return saida["resumo"] + "\n" + "\n".join(c["argumento"] for c in saida["clientes"])


def _pedir(cliente, fatos: Fatos, correcao: str | None) -> dict:
    """Uma chamada ao Gemini (`google.genai.Client`) com saída JSON presa ao ESQUEMA."""
    from google.genai import types

    pedido = "FATOS (calculados pelo protótipo; são os únicos números que você pode citar):\n" + \
        json.dumps(fatos.dados, ensure_ascii=False, indent=2)
    partes = [types.Part(text=pedido)] + ([types.Part(text=correcao)] if correcao else [])
    resp = cliente.models.generate_content(
        model=MODELO, contents=[types.Content(role="user", parts=partes)],
        config=types.GenerateContentConfig(
            system_instruction=SISTEMA, max_output_tokens=16000,
            response_mime_type="application/json", response_json_schema=ESQUEMA,
        ),
    )
    bloqueio = getattr(resp.prompt_feedback, "block_reason", None)
    if bloqueio:
        raise ErroExplicacao(f"o modelo recusou o pedido ({bloqueio})")
    if not resp.candidates:
        raise ErroExplicacao("resposta sem texto")
    fim = resp.candidates[0].finish_reason
    if fim == "MAX_TOKENS":
        raise ErroExplicacao("resposta cortada pelo limite de tokens")
    if fim not in ("STOP", None):   # SAFETY, RECITATION, PROHIBITED_CONTENT...
        raise ErroExplicacao(f"o modelo recusou o pedido ({fim})")
    partes_resp = resp.candidates[0].content.parts if resp.candidates[0].content else None
    texto = "".join(pt.text for pt in partes_resp or [] if pt.text and not getattr(pt, "thought", False))
    if not texto:
        raise ErroExplicacao("resposta sem texto")
    try:
        saida = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErroExplicacao(f"resposta não é JSON válido: {e}") from e
    ids = {c["id"] for c in saida["clientes"]}
    if ids != set(fatos.nomes):
        raise ErroExplicacao(f"clientes na resposta ({sorted(ids)}) diferem da carteira ({sorted(fatos.nomes)})")
    return saida


def gerar(cliente, fatos: Fatos, tentativas: int = 2) -> dict:
    """Pede a explicação e só devolve se todo número citado existir nos fatos.

    Na falha, tenta de novo apontando os números inventados; depois disso, erro (nada vai à tela).
    """
    correcao = None
    for _ in range(tentativas):
        saida = _pedir(cliente, fatos, correcao)
        fora = verificar(_texto_completo(saida), fatos)
        if not fora:
            return saida
        correcao = ("Sua resposta anterior citou números que não estão nos FATOS: " + ", ".join(fora) +
                    ". Reescreva usando só números copiados dos FATOS, ou sem número.")
    raise ErroExplicacao("a explicação citou números que não existem no cálculo: " + ", ".join(fora))
