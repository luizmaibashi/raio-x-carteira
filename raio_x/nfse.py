"""Leitor de XML de NFS-e do padrão nacional -> carteira agregada por tomador.

Decisão do problema 8 (Luiz, 18/11/2026): CSV agora, XML depois. Este leitor
transforma as notas emitidas num CSV da carteira (formato de raio_x.entrada) com a
coluna `tomador` pré-preenchida só onde o XML basta (pessoa física). O regime de
cada tomador PJ (regular, simples, simples_h, isento) não está na nota: fica em
branco e o usuário completa; o leitor de CSV recusa linha em branco (regra 4).

Campos lidos (leiaute da NFS-e nacional, por nome local, independente de namespace):
  infNFSe/DPS/infDPS/dhEmi                              data de emissão
  infNFSe/DPS/infDPS/toma/{CNPJ|CPF|NIF|xNome}          tomador
  infNFSe/DPS/infDPS/valores/vServPrest/vServ           valor do serviço
  infNFSe/DPS/infDPS/valores/vDescCondIncond/vDescIncond desconto incondicionado

Privacidade (regra 5): o CPF é lido só para saber que o tomador é pessoa física e
é descartado na hora; todas as PF viram uma linha agregada. CNPJ serve só de chave
em memória e não vai para o CSV (o rótulo é a razão social).

Limitações explícitas: nota cancelada não é detectável pelo XML da NFS-e (evento
separado): não inclua canceladas. Tomador no exterior (NIF) -> erro, fora do escopo.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROTULO_PF = "Pessoas físicas (agregado)"
ROTULO_SEM_TOMADOR = "Tomador não identificado (agregado)"


class ErroNFSe(ValueError):
    pass


@dataclass
class Tomador:
    rotulo: str
    tipo: str                 # "pj", "pf" ou "nao_identificado"
    valor: Decimal = Decimal(0)
    notas: int = 0


@dataclass
class ResultadoLeitura:
    tomadores: list[Tomador]
    notas_lidas: int
    fora_do_periodo: int
    duplicadas: int
    avisos: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _filho(el: ET.Element | None, *caminho: str) -> ET.Element | None:
    for nome in caminho:
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == nome), None)
    return el


def _texto(el, *caminho) -> str | None:
    alvo = _filho(el, *caminho)
    return alvo.text.strip() if alvo is not None and alvo.text and alvo.text.strip() else None


def _dec(s: str | None, campo: str, origem: str) -> Decimal:
    try:
        v = Decimal(s) if s is not None else None
    except InvalidOperation:
        v = None
    if v is None or not v.is_finite():
        raise ErroNFSe(f"{origem}: {campo} ausente ou inválido")
    return v


def _parse(conteudo: bytes, origem: str) -> ET.Element:
    if b"<!DOCTYPE" in conteudo or b"<!ENTITY" in conteudo:
        raise ErroNFSe(f"{origem}: XML com DOCTYPE/ENTITY recusado")
    try:
        return ET.fromstring(conteudo)
    except ET.ParseError as e:
        raise ErroNFSe(f"{origem}: XML inválido ({e})") from None


def _inf_nfse(raiz: ET.Element) -> list[ET.Element]:
    achados = [el for el in raiz.iter() if _local(el.tag) == "infNFSe"]
    if not achados:
        raise ErroNFSe("nenhum infNFSe no arquivo (é XML de NFS-e do padrão nacional?)")
    return achados


def ler_notas(arquivos: list[tuple[str, bytes]], inicio: dt.date | None = None,
              fim: dt.date | None = None) -> ResultadoLeitura:
    """Agrega notas por tomador. `arquivos` = [(nome, conteúdo)]; período inclusivo."""
    if not arquivos:
        raise ErroNFSe("nenhum arquivo")
    por_chave: dict[str, Tomador] = {}
    ids, lidas, fora, dup = set(), 0, 0, 0
    for nome, conteudo in arquivos:
        for inf in _inf_nfse(_parse(conteudo, nome)):
            origem = f"{nome} ({inf.get('Id') or 'sem Id'})"
            nid = inf.get("Id")
            if nid and nid in ids:
                dup += 1
                continue
            if nid:
                ids.add(nid)
            dps = _filho(inf, "DPS", "infDPS")
            if dps is None:
                raise ErroNFSe(f"{origem}: sem DPS/infDPS")
            data_txt = _texto(dps, "dhEmi")
            try:
                data = dt.datetime.fromisoformat(data_txt).date()
            except (TypeError, ValueError):
                raise ErroNFSe(f"{origem}: dhEmi ausente ou inválido") from None
            if (inicio and data < inicio) or (fim and data > fim):
                fora += 1
                continue
            vserv = _dec(_texto(dps, "valores", "vServPrest", "vServ"), "vServ", origem)
            desc_txt = _texto(dps, "valores", "vDescCondIncond", "vDescIncond")
            # P19: receita bruta = preço do serviço menos descontos incondicionais.
            valor = vserv - (_dec(desc_txt, "vDescIncond", origem) if desc_txt else 0)
            if valor < 0:
                raise ErroNFSe(f"{origem}: valor líquido negativo")

            toma = _filho(dps, "toma")
            if toma is not None and _texto(toma, "NIF"):
                raise ErroNFSe(f"{origem}: tomador no exterior (NIF) fora do escopo do protótipo")
            cnpj = _texto(toma, "CNPJ") if toma is not None else None
            if cnpj:
                chave = "pj:" + cnpj
                rot = _texto(toma, "xNome") or "Pessoa jurídica sem nome"
                t = por_chave.setdefault(chave, Tomador(rot, "pj"))
            elif toma is not None and _texto(toma, "CPF"):
                # CPF lido só para classificar; não é guardado (regra 5).
                t = por_chave.setdefault("pf", Tomador(ROTULO_PF, "pf"))
            else:
                t = por_chave.setdefault("sem", Tomador(ROTULO_SEM_TOMADOR, "nao_identificado"))
            t.valor += valor
            t.notas += 1
            lidas += 1

    tomadores = list(por_chave.values())
    # Rótulos únicos: duas empresas com a mesma razão social viram "Nome (2)".
    vistos: dict[str, int] = {}
    for t in tomadores:
        n = vistos.get(t.rotulo, 0) + 1
        vistos[t.rotulo] = n
        if n > 1:
            t.rotulo = f"{t.rotulo} ({n})"
    avisos = []
    if any(t.tipo == "nao_identificado" for t in tomadores):
        avisos.append("Há notas sem tomador identificado; classifique a linha agregada à mão.")
    return ResultadoLeitura(tomadores, lidas, fora, dup, avisos)


def para_csv(resultado: ResultadoLeitura) -> str:
    """CSV no formato de raio_x.entrada. PF já vem como `pf`; o resto fica em branco."""
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\n")
    w.writerow(["cliente", "valor_12m", "tomador"])
    for t in sorted(resultado.tomadores, key=lambda t: -t.valor):
        w.writerow([t.rotulo, f"{t.valor:.2f}", "pf" if t.tipo == "pf" else ""])
    return saida.getvalue()


def ler_pasta(pasta: Path, **kw) -> ResultadoLeitura:
    arquivos = sorted(pasta.glob("*.xml"))
    return ler_notas([(p.name, p.read_bytes()) for p in arquivos], **kw)
