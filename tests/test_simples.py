import asyncio
from unittest.mock import patch

import pytest

from mcp_fiscal_brasil._core.errors import FiscalHTTPError, FiscalNotFoundError
from mcp_fiscal_brasil.simples.client import SimplesClient


@pytest.fixture
def client():
    return SimplesClient()


_BRASILAPI_OPTANTE = {
    "cnpj": "12345678000195",
    "opcao_pelo_simples": True,
    "data_opcao_pelo_simples": "2019-01-01",
    "data_exclusao_do_simples": None,
    "opcao_pelo_mei": False,
    "data_opcao_pelo_mei": None,
    "data_exclusao_do_mei": None,
}
_BRASILAPI_SEM_INFO = {"cnpj": "33000167000101", "opcao_pelo_simples": None, "opcao_pelo_mei": None}
_RECEITAWS_NAO_OPTANTE = {
    "status": "OK",
    "simples": {"optante": False, "data_opcao": None, "data_exclusao": None},
    "simei": {"optante": False, "data_opcao": None, "data_exclusao": None},
}


@pytest.mark.asyncio
async def test_brasilapi_cnpj_v1_confirma_regime(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = _BRASILAPI_OPTANTE
        result = await client.get_simples_status("12.345.678/0001-95")
        assert result.simples_nacional is True
        assert result.mei is False
        assert result.verificado is True
        assert result.fonte == "BrasilAPI"
        assert str(result.data_opcao) == "2019-01-01"
        mock_get.assert_awaited_once_with("/cnpj/v1/12345678000195")


@pytest.mark.asyncio
async def test_null_na_brasilapi_cai_para_receitaws(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = [_BRASILAPI_SEM_INFO, _RECEITAWS_NAO_OPTANTE]
        result = await client.get_simples_status("33000167000101")
        assert result.simples_nacional is False
        assert result.mei is False
        assert result.verificado is True
        assert result.fonte == "ReceitaWS"
        assert mock_get.await_count == 2
        assert mock_get.await_args_list[1].args == ("/cnpj/33000167000101",)


@pytest.mark.asyncio
async def test_nenhuma_fonte_confirma_retorna_nao_verificado(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = [
            _BRASILAPI_SEM_INFO,
            FiscalHTTPError("Too many requests", 429, "http://test"),
        ]
        result = await client.get_simples_status("33000167000101")
        assert result.simples_nacional is None
        assert result.mei is None
        assert result.verificado is False
        assert result.fonte is None


@pytest.mark.asyncio
async def test_nao_usa_rota_simples_v1_inexistente(client):
    """A rota BrasilAPI /simples/v1 nao existe (404 para todo CNPJ) e nao deve ser chamada."""
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = [_BRASILAPI_SEM_INFO, _RECEITAWS_NAO_OPTANTE]
        await client.get_simples_status("33000167000101")
        for chamada in mock_get.await_args_list:
            assert not chamada.args[0].startswith("/simples/")


@pytest.mark.asyncio
async def test_memoiza_por_cnpj(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = _BRASILAPI_OPTANTE
        primeiro = await client.get_simples_status("12345678000195")
        segundo = await client.get_simples_status("12.345.678/0001-95")
        assert primeiro is segundo
        mock_get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_simples_status_formato_plano_legado(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = {
            "simples_nacional": True,
            "mei": False,
            "data_opcao_simples": "2020-01-01",
        }
        result = await client.get_simples_status("123")
        assert result.simples_nacional is True
        assert result.mei is False
        assert result.data_opcao is not None


@pytest.mark.asyncio
async def test_get_simples_status_formato_aninhado_receitaws(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = {
            "simples": {"optante": True, "data_opcao": "2020-01-01"},
            "simei": {"optante": True, "data_opcao": "2020-01-01"},
        }
        result = await client.get_simples_status("123")
        assert result.simples_nacional is True
        assert result.mei is True
        assert result.fonte == "ReceitaWS"


@pytest.mark.asyncio
async def test_get_simples_status_not_found(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = FiscalHTTPError("Not found", 404, "http://test")
        with pytest.raises(FiscalNotFoundError):
            await client.get_simples_status("123")


@pytest.mark.asyncio
async def test_receitaws_status_error_apos_404_levanta_not_found(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = [
            FiscalHTTPError("Not found", 404, "http://test"),
            {"status": "ERROR", "message": "CNPJ rejeitado pela Receita Federal"},
        ]
        with pytest.raises(FiscalNotFoundError):
            await client.get_simples_status("123")


@pytest.mark.asyncio
async def test_chamadas_concorrentes_compartilham_a_mesma_consulta(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:

        async def lento(*_args, **_kwargs):
            await asyncio.sleep(0.01)
            return _BRASILAPI_OPTANTE

        mock_get.side_effect = lento
        a, b = await asyncio.gather(
            client.get_simples_status("12345678000195"),
            client.get_simples_status("12345678000195"),
        )
        assert a is b
        mock_get.assert_awaited_once()
