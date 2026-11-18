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


# Assinatura com a estrutura do xmldsig e valores fictícios: o XSD exige o bloco; nada aqui é assinado de verdade.
_ASSINATURA = (
    '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><SignedInfo>'
    '<CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
    '<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>'
    '<Reference URI="#{id}"><Transforms>'
    '<Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>'
    '<Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/></Transforms>'
    '<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
    '<DigestValue>AAAA</DigestValue></Reference></SignedInfo>'
    '<SignatureValue>AAAA</SignatureValue></Signature>')
_MUN = "3550308"
_PRESTADOR = "00000000000000"


def nota_completa(seq: int, dh: str, vserv: str, cnpj=None, cpf=None, nif=None, nao_nif=None, nome=None,
                  desc_incond=None, d_compet=None) -> str:
    """NFS-e completa no leiaute nacional 1.01, válida contra o XSD oficial (scripts/validar_nfse_xsd.py)."""
    id_nfse = f"NFS{_MUN}22{_PRESTADOR}{seq:013d}2603{1:09d}0"
    id_dps = f"DPS{_MUN}2{_PRESTADOR}{1:05d}{seq:015d}"
    doc = (f"<CNPJ>{cnpj}</CNPJ>" if cnpj else f"<CPF>{cpf}</CPF>" if cpf else f"<NIF>{nif}</NIF>" if nif
           else f"<cNaoNIF>{nao_nif}</cNaoNIF>" if nao_nif is not None else None)
    toma = "" if doc is None else f"<toma>{doc}<xNome>{nome or 'Tomador (sintético)'}</xNome></toma>"
    desc = f"<vDescCondIncond><vDescIncond>{desc_incond}</vDescIncond></vDescCondIncond>" if desc_incond else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<NFSe xmlns="{NS}" versao="1.01"><infNFSe Id="{id_nfse}">'
            "<xLocEmi>Cidade Fictícia</xLocEmi><xLocPrestacao>Cidade Fictícia</xLocPrestacao>"
            f"<nNFSe>{seq}</nNFSe><xTribNac>Consultoria (sintético)</xTribNac><verAplic>sintetico</verAplic>"
            f"<ambGer>2</ambGer><tpEmis>1</tpEmis><cStat>100</cStat><dhProc>{dh}</dhProc><nDFSe>{seq}</nDFSe>"
            f"<emit><CNPJ>{_PRESTADOR}</CNPJ><xNome>Prestador Fictício (sintético)</xNome>"
            "<enderNac><xLgr>Rua Fictícia</xLgr><nro>1</nro><xBairro>Centro</xBairro>"
            f"<cMun>{_MUN}</cMun><UF>SP</UF><CEP>01000000</CEP></enderNac></emit>"
            f"<valores><vLiq>{vserv}</vLiq></valores>"
            f'<DPS versao="1.01"><infDPS Id="{id_dps}"><tpAmb>2</tpAmb><dhEmi>{dh}</dhEmi>'
            f"<verAplic>sintetico</verAplic><serie>1</serie><nDPS>{seq}</nDPS><dCompet>{d_compet or dh[:10]}</dCompet>"
            f"<tpEmit>1</tpEmit><cLocEmi>{_MUN}</cLocEmi>"
            f"<prest><CNPJ>{_PRESTADOR}</CNPJ><regTrib><opSimpNac>3</opSimpNac><regEspTrib>0</regEspTrib></regTrib>"
            f"</prest>{toma}"
            f"<serv><locPrest><cLocPrestacao>{_MUN}</cLocPrestacao></locPrest>"
            "<cServ><cTribNac>171901</cTribNac><xDescServ>Consultoria (sintético)</xDescServ></cServ></serv>"
            f"<valores><vServPrest><vServ>{vserv}</vServ></vServPrest>{desc}"
            "<trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN></tribMun>"
            "<totTrib><indTotTrib>0</indTotTrib></totTrib></trib></valores>"
            "</infDPS></DPS></infNFSe>" + _ASSINATURA.format(id=id_nfse) + "</NFSe>\n")
