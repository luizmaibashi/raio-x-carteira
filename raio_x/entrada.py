"""Entrada da carteira por CSV (decisão do problema 8: CSV agora, XML de NFS-e depois).

Formato (cabeçalho obrigatório, separador "," ou ";", UTF-8):

    cliente;valor_12m;tomador
    Cliente A;200.000,00;regular
    Cliente B;100000.00;pf

- cliente: rótulo livre. CPF/CNPJ (11 ou 14 dígitos) é recusado: o repositório só
  aceita dado sintético e o protótipo não precisa do documento (regra 5).
- valor_12m: faturado ao cliente nos 12 meses (formato BR "1.234,56" ou "1234.56").
- tomador: regime do cliente, que define se ele toma crédito de IBS/CBS (cred):
    regular   -> cred 1 (P05: não cumulatividade para todo o regime regular)
    simples_h -> cred 1 (P02/P17: optante que recolhe IBS/CBS por fora)
    simples   -> cred 0 (MODELO_ECONOMICO: Simples puro não credita)
    pf        -> cred 0 (pessoa física, consumidor final)
    isento    -> cred 0 (imune/isento, sem débito para abater)

Qualquer linha inválida gera ErroEntrada com o número da linha; nada é ignorado em silêncio.
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from raio_x.modelo import Cliente

TOMADORES_CREDITO = {"regular": True, "simples_h": True, "simples": False, "pf": False, "isento": False}
COLUNAS = ("cliente", "valor_12m", "tomador")
_RE_DOCUMENTO = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")


class ErroEntrada(ValueError):
    pass


def valor_br(texto: str) -> Decimal:
    s = texto.strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")  # "200.000" sem centavos
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise ErroEntrada(f"valor inválido: {texto!r}") from None
    if not v.is_finite():
        raise ErroEntrada(f"valor inválido: {texto!r}")
    return v


def ler_carteira_csv(origem: str | Path | io.TextIOBase) -> list[Cliente]:
    texto = Path(origem).read_text(encoding="utf-8-sig") if isinstance(origem, (str, Path)) else origem.read()
    linhas = [l for l in texto.splitlines() if l.strip()]
    if not linhas:
        raise ErroEntrada("arquivo vazio")
    sep = ";" if linhas[0].count(";") >= linhas[0].count(",") and ";" in linhas[0] else ","
    leitor = csv.DictReader(io.StringIO("\n".join(linhas)), delimiter=sep)
    cab = [c.strip().lower() for c in (leitor.fieldnames or [])]
    if sorted(cab) != sorted(COLUNAS):
        raise ErroEntrada(f"cabeçalho deve ter exatamente {', '.join(COLUNAS)}; veio {', '.join(cab)}")
    leitor.fieldnames = cab

    clientes, nomes = [], set()
    for n, row in enumerate(leitor, start=2):
        if None in row or any(v is None for v in row.values()):
            raise ErroEntrada(f"linha {n}: número de colunas diferente do cabeçalho")
        nome, tomador = row["cliente"].strip(), row["tomador"].strip().lower()
        if not nome:
            raise ErroEntrada(f"linha {n}: cliente vazio")
        if _RE_DOCUMENTO.search(nome):
            raise ErroEntrada(f"linha {n}: rótulo parece CPF/CNPJ; use um nome sem documento")
        if nome in nomes:
            raise ErroEntrada(f"linha {n}: cliente repetido {nome!r}")
        if tomador not in TOMADORES_CREDITO:
            raise ErroEntrada(f"linha {n}: tomador {tomador!r}; use {', '.join(TOMADORES_CREDITO)}")
        try:
            valor = valor_br(row["valor_12m"])
        except ErroEntrada as e:
            raise ErroEntrada(f"linha {n}: {e}") from None
        if valor <= 0:
            raise ErroEntrada(f"linha {n}: valor precisa ser positivo")
        nomes.add(nome)
        clientes.append(Cliente(nome, valor, TOMADORES_CREDITO[tomador]))
    if not clientes:
        raise ErroEntrada("nenhum cliente no arquivo")
    return clientes
