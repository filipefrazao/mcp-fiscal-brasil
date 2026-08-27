from unittest.mock import patch

import pytest

from mcp_fiscal_brasil._core.errors import FiscalHTTPError, FiscalNotFoundError
from mcp_fiscal_brasil.mei.client import MEIClient


@pytest.fixture
def client():
    return MEIClient()


@pytest.mark.asyncio
async def test_get_mei_status_success(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = {"simples": {"optante": True}, "simei": {"optante": True}}
        result = await client.get_mei_status("123")
        assert result.mei is True
        assert result.simples_nacional is True


@pytest.mark.asyncio
async def test_get_mei_status_fallback_format(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = {"mei": False, "simples_nacional": False}
        result = await client.get_mei_status("123")
        assert result.mei is False
        assert result.simples_nacional is False


@pytest.mark.asyncio
async def test_get_mei_status_not_found(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = FiscalHTTPError("Not found", 404, "http://test")
        with pytest.raises(FiscalNotFoundError):
            await client.get_mei_status("123")


@pytest.mark.asyncio
async def test_get_mei_status_delegates_to_simples_client():
    from mcp_fiscal_brasil.simples.schemas import SimplesStatus

    with patch("mcp_fiscal_brasil.simples.client.SimplesClient.get_simples_status") as mock_s:
        mock_s.return_value = SimplesStatus(
            cnpj="12345678000195", simples_nacional=True, mei=True, fonte="BrasilAPI"
        )
        result = await MEIClient().get_mei_status("12.345.678/0001-95")
        assert result.mei is True
        assert result.simples_nacional is True
        assert result.verificado is True
        assert result.fonte == "BrasilAPI"


@pytest.mark.asyncio
async def test_get_mei_status_nao_verificado_quando_fontes_nao_informam(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = [
            {"opcao_pelo_simples": None, "opcao_pelo_mei": None},
            FiscalHTTPError("Too many requests", 429, "http://test"),
        ]
        result = await client.get_mei_status("123")
        assert result.mei is None
        assert result.verificado is False
