"""Gera dados/anexos_simples.json a partir do texto oficial dos Anexos III e V.

Fonte: Anexos XX e XXII da LC 214/2025 (redação nova dos Anexos III e V da LC 123),
cópia do Senado. Extração por regex, sem LLM (regra 3 do AGENTS.md).
Premissas: P14 (Anexo III 2027-28), P16 (teto do ISS), P18 (6 tabelas x 6 faixas, soma 100%).

Uso: python scripts/gerar_anexos.py [--html-dir DIR]
  Sem --html-dir, baixa os HTMLs com curl (-A "Mozilla/5.0").
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

FONTES = {
    "III": "https://legis.senado.leg.br/norma/40180341/publicacao/40181117",
    "V": "https://legis.senado.leg.br/norma/40180341/publicacao/40181129",
}
PERIODOS = ["2027-2028", "2029", "2030", "2031", "2032", "2033"]
VIGENCIAS_ALIQ = ["2027-2028", "2029+"]
TOL = Decimal("0.01")
# Exceções aceitas no gate: arredondamento do próprio texto (P18).
EXCECOES_CONHECIDAS = {("III", "2027-2028", 3), ("III", "2027-2028", 4)}
# 6ª faixa: o texto traz só 4 valores; ISS e IBS saem do DAS acima de R$ 3,6 mi (P18).
COLUNAS_6A_FAIXA = ["IRPJ", "CSLL", "CBS", "CPP"]
# Nota (*) do teto do ISS: existe só no Anexo III, de 2027-28 a 2032 (P16). Lista fechada:
# tabela ausente ou a mais falha o gate.
TETOS_ESPERADOS = {"III": set(PERIODOS[:-1]), "V": set()}

SAIDA = Path(__file__).resolve().parent.parent / "dados" / "anexos_simples.json"


class GateError(Exception):
    pass


def baixar(url: str) -> bytes:
    return subprocess.run(
        ["curl", "-sSfL", "-A", "Mozilla/5.0", url], check=True, capture_output=True
    ).stdout


def texto_limpo(bruto: bytes) -> str:
    t = bruto.decode("utf-8", errors="replace")
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(\d) a Faixa", r"\1ª Faixa", t)  # "3 a Faixa" -> "3ª Faixa"
    t = re.sub(r"(\d) a faixa", r"\1ª faixa", t)
    return t


def dec(s: str) -> Decimal:
    return Decimal(s.replace(".", "").replace(",", "."))


def periodo_antes(texto: str, pos: int) -> str:
    """Período declarado mais próximo antes de `pos` ("Para o ano-calendário 2029" etc.)."""
    achados = list(re.finditer(r"anos?-calendário (\d{4})(?: e (\d{4}))?", texto[:pos]))
    if not achados:
        raise GateError(f"período não encontrado antes da posição {pos}")
    m = achados[-1]
    return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)


RE_FAIXA_ALIQ = re.compile(
    r"(\d)ª Faixa (?:Até|De [\d.]+,\d{2} a) ([\d.]+,\d{2}) (\d+,\d+)% (?:[–-]|([\d.]+,\d{2}))"
)
RE_CAB_ALIQ = re.compile(r"Receita Bruta em 12 Meses \(em R\$\) Alíquota Valor a Deduzir \(em R\$\)")
RE_CAB_PART = re.compile(r"Faixas Percentual de Repartição dos Tributos ((?:[A-Z]{3,4} (?:\(\*\) )?)+)")
RE_LINHA_PART = re.compile(r"(\d)ª Faixa ((?:\d+,\d+% (?:\(\*\) )?)+)")
RE_TETO = re.compile(
    r"quando a alíquota efetiva for superior a (\d+,\d+)%.*?com alíquota efetiva superior a [\d,]+% "
    r"((?:(?:\(Alíquota efetiva - 5%\) x \d+,\d+%|Percentual de ISS fixo em \d+,?\d*%) ?)+)"
)


def extrair_aliquotas(texto: str) -> dict:
    tabelas = {}
    for cab in RE_CAB_ALIQ.finditer(texto):
        periodo = periodo_antes(texto, cab.start())
        chave = "2027-2028" if periodo == "2027-2028" else "2029+"
        trecho = texto[cab.end(): cab.end() + 800]
        faixas = []
        for m in RE_FAIXA_ALIQ.finditer(trecho):
            n = int(m.group(1))
            if n != len(faixas) + 1:
                break
            faixas.append({
                "faixa": n,
                "rbt12_max": str(dec(m.group(2))),
                "aliquota_nominal": str(dec(m.group(3))),
                "parcela_deduzir": str(dec(m.group(4))) if m.group(4) else "0",
            })
            if n == 6:
                break
        tabelas[chave] = faixas
    return tabelas


def extrair_partilhas(texto: str) -> dict:
    tabelas = {}
    for cab in RE_CAB_PART.finditer(texto):
        periodo = periodo_antes(texto, cab.start())
        colunas = re.findall(r"[A-Z]{3,4}", cab.group(1))
        linhas = []
        pos = cab.end()
        for esperado in range(1, 7):
            m = RE_LINHA_PART.match(texto, pos) or RE_LINHA_PART.match(texto, pos + 1)
            if not m or int(m.group(1)) != esperado:
                break
            valores = [dec(v) for v in re.findall(r"(\d+,\d+)%", m.group(2))]
            cols = colunas if len(valores) == len(colunas) else (
                COLUNAS_6A_FAIXA if esperado == 6 and len(valores) == 4 else None)
            if cols is None:
                raise GateError(f"{periodo} faixa {esperado}: {len(valores)} valores para {colunas}")
            linhas.append({"faixa": esperado, **{c: str(v) for c, v in zip(cols, valores)}})
            pos = m.end()
        tabelas[periodo] = linhas
    return tabelas


def extrair_tetos(texto: str) -> dict:
    """Repartição da 5ª faixa com ISS no teto de 5% (nota (*), P16)."""
    tetos = {}
    for m in RE_TETO.finditer(texto):
        periodo = periodo_antes(texto, m.start())
        itens = re.findall(r"\(Alíquota efetiva - 5%\) x (\d+,\d+)%|Percentual de ISS fixo em (\d+,?\d*)%", m.group(2))
        tetos[periodo] = {"limiar_aliquota_efetiva": str(dec(m.group(1))), "itens": [
            {"tipo": "proporcional", "percentual": str(dec(p))} if p else
            {"tipo": "fixo", "aliquota": str(dec(f))} for p, f in itens]}
    return tetos


def montar_teto(anexo: str, periodo: str, teto: dict, colunas: list[str]) -> dict:
    """Associa cada item da tabela do teto à coluna do cabeçalho (IRPJ CSLL CBS CPP ISS IBS)."""
    if len(teto["itens"]) != len(colunas):
        raise GateError(f"{anexo} {periodo}: teto com {len(teto['itens'])} itens, esperado {len(colunas)}")
    prop, fixo = {}, {}
    for col, item in zip(colunas, teto["itens"]):
        if item["tipo"] == "proporcional":
            prop[col] = item["percentual"]
        else:
            fixo[col] = item["aliquota"]
    soma = sum(Decimal(v) for v in prop.values())
    if abs(soma - 100) > TOL:
        raise GateError(f"{anexo} {periodo}: teto proporcional soma {soma}")
    if sum(Decimal(v) for v in fixo.values()) != 5:
        raise GateError(f"{anexo} {periodo}: parcelas fixas do teto não somam 5%")
    return {"limiar_aliquota_efetiva": teto["limiar_aliquota_efetiva"], "proporcional": prop, "fixo": fixo}


def gate(anexo: str, aliq: dict, part: dict) -> list[str]:
    avisos = []
    for v in VIGENCIAS_ALIQ:
        faixas = aliq.get(v)
        if not faixas or [f["faixa"] for f in faixas] != list(range(1, 7)):
            raise GateError(f"Anexo {anexo}: tabela de alíquotas {v} incompleta")
    for p in PERIODOS:
        linhas = part.get(p)
        if not linhas or [l["faixa"] for l in linhas] != list(range(1, 7)):
            raise GateError(f"Anexo {anexo}: partilha {p} incompleta")
        for l in linhas:
            soma = sum(Decimal(x) for k, x in l.items() if k != "faixa")
            if abs(soma - 100) > TOL:
                raise GateError(f"Anexo {anexo} {p} faixa {l['faixa']}: soma {soma}")
            if soma != 100:
                if (anexo, p, l["faixa"]) not in EXCECOES_CONHECIDAS:
                    raise GateError(f"Anexo {anexo} {p} faixa {l['faixa']}: soma {soma} fora das exceções conhecidas")
                avisos.append(f"Anexo {anexo} {p} faixa {l['faixa']}: soma {soma} (arredondamento do texto)")
    extras = set(part) - set(PERIODOS)
    if extras:
        raise GateError(f"Anexo {anexo}: períodos inesperados {extras}")
    return avisos


def gerar(html_dir: Path | None) -> dict:
    hoje = dt.date.today().isoformat()
    saida = {"gerado_por": "scripts/gerar_anexos.py", "premissas": ["P14", "P16", "P18"],
             "unidade": "percentual (6.00 = 6%)", "anexos": {}}
    for anexo, url in FONTES.items():
        bruto = (html_dir / f"{anexo}.html").read_bytes() if html_dir else baixar(url)
        texto = texto_limpo(bruto)
        aliq, part, tetos = extrair_aliquotas(texto), extrair_partilhas(texto), extrair_tetos(texto)
        avisos = gate(anexo, aliq, part)
        if set(tetos) != TETOS_ESPERADOS[anexo]:
            raise GateError(f"Anexo {anexo}: tabelas de teto do ISS {sorted(tetos)}, "
                            f"esperado {sorted(TETOS_ESPERADOS[anexo])}")
        cab = RE_CAB_PART.search(texto)
        colunas = re.findall(r"[A-Z]{3,4}", cab.group(1))
        saida["anexos"][anexo] = {
            "fonte": {"url": url, "lido_em": hoje, "sha256": hashlib.sha256(bruto).hexdigest()},
            "aliquotas": aliq,
            "partilha": part,
            "teto_iss_5a_faixa": {p: montar_teto(anexo, p, t, colunas) for p, t in tetos.items()},
            "avisos": avisos,
        }
    if set(saida["anexos"]) != {"III", "V"}:
        raise GateError("anexo faltando")
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-dir", type=Path)
    args = ap.parse_args()
    dados = gerar(args.html_dir)
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for a in dados["anexos"].values():
        for av in a["avisos"]:
            print("aviso:", av)
    print("ok:", SAIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
