import datetime as dt
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from raio_x.entrada import ErroEntrada, ler_carteira_csv
from raio_x.nfse import ROTULO_PF, ErroNFSe, ler_notas, para_csv
from tests.nfse_sintetica import nota, nota_completa

RAIZ = Path(__file__).resolve().parent.parent
CNPJ_A, CNPJ_B, CPF = "11111111000100", "22222222000100", "12345678900"


def arq(*notas):
    return [(f"n{i}.xml", n.encode()) for i, n in enumerate(notas)]


def test_agrega_por_tomador_e_desconto_incondicional():
    r = ler_notas(arq(
        nota("N1", "2026-03-01T10:00:00-03:00", "1000.00", cnpj=CNPJ_A, nome="Alfa"),
        nota("N2", "2026-04-01T10:00:00-03:00", "500.00", cnpj=CNPJ_A, nome="Alfa", desc_incond="50.00"),
        nota("N3", "2026-04-02T10:00:00-03:00", "300.00", cnpj=CNPJ_B, nome="Beta"),
    ))
    assert {t.rotulo: t.valor for t in r.tomadores} == {"Alfa": D("1450.00"), "Beta": D("300.00")}
    assert r.notas_lidas == 3


def test_cpf_nao_sai_da_leitura():
    r = ler_notas(arq(
        nota("N1", "2026-03-01T10:00:00-03:00", "200.00", cpf=CPF, nome="Fulano"),
        nota("N2", "2026-03-02T10:00:00-03:00", "100.00", cpf="98765432111", nome="Beltrano"),
    ))
    assert [(t.rotulo, t.tipo, t.valor) for t in r.tomadores] == [(ROTULO_PF, "pf", D("300.00"))]
    texto = para_csv(r) + repr(r)
    assert CPF not in texto and "Fulano" not in texto


def test_csv_gerado_exige_regime_dos_pj_e_depois_alimenta_o_modelo():
    r = ler_notas(arq(
        nota("N1", "2026-03-01T10:00:00-03:00", "1000.00", cnpj=CNPJ_A, nome="Alfa"),
        nota("N2", "2026-03-01T10:00:00-03:00", "200.00", cpf=CPF),
    ))
    csv_ = para_csv(r)
    assert CNPJ_A not in csv_
    with pytest.raises(ErroEntrada, match="tomador"):
        ler_carteira_csv(__import__("io").StringIO(csv_))
    preenchido = csv_.replace("Alfa;1000.00;", "Alfa;1000.00;regular")
    cart = ler_carteira_csv(__import__("io").StringIO(preenchido))
    assert [(c.nome, c.cred) for c in cart] == [("Alfa", True), (ROTULO_PF, False)]


def test_periodo_duplicadas_e_sem_tomador():
    n1 = nota("N1", "2026-01-15T10:00:00-03:00", "100.00", cnpj=CNPJ_A, nome="Alfa")
    r = ler_notas(arq(
        n1, n1,
        nota("N2", "2025-12-31T10:00:00-03:00", "999.00", cnpj=CNPJ_A, nome="Alfa"),
        nota("N3", "2026-02-01T10:00:00-03:00", "50.00"),
    ), inicio=dt.date(2026, 1, 1), fim=dt.date(2026, 12, 31))
    assert (r.notas_lidas, r.fora_do_periodo, r.duplicadas) == (2, 1, 1)
    assert any("não identificado" in t.rotulo for t in r.tomadores) and r.avisos


def test_razao_social_repetida_vira_rotulo_unico():
    r = ler_notas(arq(
        nota("N1", "2026-03-01T10:00:00", "1", cnpj=CNPJ_A, nome="Igual"),
        nota("N2", "2026-03-01T10:00:00", "1", cnpj=CNPJ_B, nome="Igual"),
    ))
    assert sorted(t.rotulo for t in r.tomadores) == ["Igual", "Igual (2)"]


@pytest.mark.parametrize("conteudo,trecho", [
    (nota("N1", "2026-03-01T10:00:00", "1", nif="X1"), "exterior"),
    (nota("N1", "2026-03-01T10:00:00", "abc", cnpj=CNPJ_A), "vServ"),
    (nota("N1", "ontem", "1", cnpj=CNPJ_A), "dhEmi"),
    (nota("N1", "2026-03-01T10:00:00", "10", cnpj=CNPJ_A, desc_incond="20"), "negativo"),
    ("<x/>", "infNFSe"),
    ("<a>", "inválido"),
    ('<!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>', "DOCTYPE"),
])
def test_erros_explicitos(conteudo, trecho):
    with pytest.raises(ErroNFSe, match=trecho):
        ler_notas([("x.xml", conteudo.encode())])


def test_exemplos_sinteticos_e_script(tmp_path):
    saida = tmp_path / "c.csv"
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "nfse_para_csv.py"),
                        str(RAIZ / "dados" / "exemplos" / "nfse"), str(saida)],
                       capture_output=True, text=True, check=True)
    assert "5 notas" in p.stdout
    linhas = saida.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "cliente;valor_12m;tomador" and len(linhas) == 4


def test_nota_completa_do_leiaute_oficial():
    """Leiaute 1.01 inteiro (o mesmo dos exemplos validados no XSD): os campos ao redor não atrapalham."""
    r = ler_notas(arq(
        nota_completa(1, "2026-03-01T10:00:00-03:00", "1000.00", cnpj=CNPJ_A, nome="Alfa", desc_incond="100.00"),
        nota_completa(2, "2026-03-02T10:00:00-03:00", "200.00", cpf=CPF, nome="Fulano"),
    ))
    assert sorted((t.rotulo, t.valor) for t in r.tomadores) == [("Alfa", D("900.00")), (ROTULO_PF, D("200.00"))]


def test_periodo_usa_a_competencia_e_nao_a_emissao():
    # Emitida em janeiro de 2027 com competência de dezembro de 2026: entra em 2026 (P22).
    n = nota_completa(1, "2027-01-05T10:00:00-03:00", "500.00", cnpj=CNPJ_A, nome="Alfa", d_compet="2026-12-20")
    r = ler_notas(arq(n), inicio=dt.date(2026, 1, 1), fim=dt.date(2026, 12, 31))
    assert (r.notas_lidas, r.fora_do_periodo) == (1, 0)


def test_tomador_exterior_sem_nif_tambem_fica_fora():
    with pytest.raises(ErroNFSe, match="exterior"):
        ler_notas(arq(nota_completa(1, "2026-03-01T10:00:00-03:00", "1.00", nao_nif=0, nome="Exterior")))


def test_exemplos_da_demo_sao_o_leiaute_completo():
    pasta = RAIZ / "dados" / "exemplos" / "nfse"
    r = ler_notas([(p.name, p.read_bytes()) for p in sorted(pasta.glob("*.xml"))])
    assert r.notas_lidas == 5 and all(b"Signature" in p.read_bytes() for p in pasta.glob("*.xml"))
