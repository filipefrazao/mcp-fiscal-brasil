import pytest

from mcp_fiscal_brasil.esocial.tools import validar_evento_esocial

_XML_S1000 = (
    '<eSocial xmlns="http://www.esocial.gov.br/schema/evt/evtInfoEmpregador/v_S_01_03_00">'
    '<evtInfoEmpregador Id="ID1330001670001012026082710000000001">'
    "<ideEvento><tpAmb>2</tpAmb><procEmi>1</procEmi><verProc>1.0</verProc></ideEvento>"
    "</evtInfoEmpregador></eSocial>"
)


@pytest.mark.asyncio
async def test_validar_evento_resolve_codigo_pelo_elemento() -> None:
    resultado = await validar_evento_esocial(_XML_S1000)
    assert resultado.evento == "S-1000"
    assert resultado.elemento == "evtInfoEmpregador"
    assert resultado.válido is True
    assert resultado.avisos == []
    assert resultado.versão == "v_S_01_03_00"


@pytest.mark.asyncio
async def test_validar_evento_elemento_desconhecido_gera_aviso() -> None:
    xml = (
        '<eSocial xmlns="http://www.esocial.gov.br/schema/evt/evtFoo/v_S_01_03_00">'
        '<evtFoo Id="ID1"/></eSocial>'
    )
    resultado = await validar_evento_esocial(xml)
    assert resultado.evento == "evtFoo"
    assert resultado.elemento == "evtFoo"
    assert any("não corresponde" in aviso for aviso in resultado.avisos)
