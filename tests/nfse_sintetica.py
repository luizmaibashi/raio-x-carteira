"""Fábrica de XML sintético de NFS-e nacional para testes e exemplos.

Documentos usam dígitos verificadores inválidos de propósito: não existem (regra 5).
"""
NS = "http://www.sped.fazenda.gov.br/nfse"


def nota(id_, dh, vserv, cnpj=None, cpf=None, nif=None, nome=None, desc_incond=None):
    if cnpj:
        doc = f"<CNPJ>{cnpj}</CNPJ>"
    elif cpf:
        doc = f"<CPF>{cpf}</CPF>"
    elif nif:
        doc = f"<NIF>{nif}</NIF>"
    else:
        doc = None
    toma = "" if doc is None else f"<toma>{doc}{f'<xNome>{nome}</xNome>' if nome else ''}</toma>"
    desc = (f"<vDescCondIncond><vDescIncond>{desc_incond}</vDescIncond></vDescCondIncond>"
            if desc_incond else "")
    return (f'<NFSe xmlns="{NS}" versao="1.01"><infNFSe Id="{id_}"><DPS versao="1.01"><infDPS>'
            f"<dhEmi>{dh}</dhEmi>{toma}<valores><vServPrest><vServ>{vserv}</vServ></vServPrest>"
            f"{desc}</valores></infDPS></DPS></infNFSe></NFSe>")
