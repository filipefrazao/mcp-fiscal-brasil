from unittest.mock import patch

import pytest

from mcp_fiscal_brasil._core.errors import FiscalHTTPError, FiscalNotFoundError
from mcp_fiscal_brasil.cnae.client import CNAEClient


@pytest.fixture
def client():
    return CNAEClient()


@pytest.mark.asyncio
async def test_get_activities_success(client):
    """get_activities usa get_list pois /subclasses (sem codigo) retorna lista."""
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get_list") as mock_get:
        # A API IBGE retorna 'descricao' sem acento
        mock_get.return_value = [{"id": "0111301", "descricao": "Cultivo de arroz"}]
        result = await client.get_activities()
        assert len(result) == 1
        assert result[0].código == "0111301"
        assert result[0].descrição == "Cultivo de arroz"


@pytest.mark.asyncio
async def test_get_activity_success(client):
    """get_activity usa get() pois /subclasses/{code} retorna objeto, nao lista."""
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = {
            "id": "6201501",
            "descricao": "DESENVOLVIMENTO DE PROGRAMAS DE COMPUTADOR SOB ENCOMENDA",
        }
        result = await client.get_activity("6201501")
        assert result.código == "6201501"
        assert "COMPUTADOR" in result.descrição


@pytest.mark.asyncio
async def test_get_activity_not_found(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = FiscalHTTPError("Not found", 404, "http://test")
        with pytest.raises(FiscalNotFoundError):
            await client.get_activity("9999999")


@pytest.mark.asyncio
async def test_get_classes_success(client):
    """get_classes usa get_list pois /classes (sem codigo) retorna lista."""
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get_list") as mock_get:
        mock_get.return_value = [
            {
                "id": "01113",
                "descricao": "Cultivo de cereais",
                "grupo": {"descricao": "Grupo 1", "divisao": {"descricao": "Divisao 1"}},
            }
        ]
        result = await client.get_classes()
        assert len(result) == 1
        assert result[0].código == "01113"
        assert result[0].descrição == "Cultivo de cereais"
        assert result[0].grupo == "Grupo 1"
        assert result[0].divisao == "Divisao 1"


@pytest.mark.asyncio
async def test_get_class_success(client):
    """get_class usa get() pois /classes/{code} retorna objeto, nao lista."""
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = {
            "id": "62015",
            "descricao": "DESENVOLVIMENTO DE PROGRAMAS DE COMPUTADOR SOB ENCOMENDA",
            "grupo": {
                "id": "620",
                "descricao": "ATIVIDADES DOS SERVICOS DE TI",
                "divisao": {
                    "id": "62",
                    "descricao": "ATIVIDADES DOS SERVICOS DE TI",
                },
            },
        }
        result = await client.get_class("62015")
        assert result.código == "62015"
        assert "COMPUTADOR" in result.descrição
        assert result.grupo == "ATIVIDADES DOS SERVICOS DE TI"
        assert result.divisao == "ATIVIDADES DOS SERVICOS DE TI"


@pytest.mark.asyncio
async def test_get_class_not_found(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.side_effect = FiscalHTTPError("Not found", 404, "http://test")
        with pytest.raises(FiscalNotFoundError):
            await client.get_class("99999")


_SUBCLASSES_IBGE = [
    {"id": "5611201", "descricao": "Restaurantes e similares"},
    {
        "id": "5620104",
        "descricao": (
            "Fornecimento de alimentos preparados preponderantemente para consumo domiciliar"
        ),
    },
    {"id": "8599604", "descricao": "Treinamento em desenvolvimento profissional e gerencial"},
]


@pytest.mark.asyncio
async def test_get_activities_filtra_localmente_ignorando_acento_e_caixa(client):
    """O IBGE ignora parametros de busca textual; o filtro e aplicado localmente."""
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get_list") as mock_get:
        mock_get.return_value = _SUBCLASSES_IBGE
        result = await client.get_activities("RESTAURANTÉ")
        assert [a.código for a in result] == ["5611201"]
        # Nenhum parametro de busca e enviado ao IBGE (seria ignorado).
        mock_get.assert_awaited_once_with("/subclasses")


@pytest.mark.asyncio
async def test_get_activities_exige_todos_os_termos_relevantes(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get_list") as mock_get:
        mock_get.return_value = _SUBCLASSES_IBGE
        result = await client.get_activities("treinamento em desenvolvimento profissional")
        assert [a.código for a in result] == ["8599604"]
        assert await client.get_activities("treinamento restaurante") == []


@pytest.mark.asyncio
async def test_get_activities_sem_texto_devolve_lista_completa(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get_list") as mock_get:
        mock_get.return_value = _SUBCLASSES_IBGE
        result = await client.get_activities()
        assert len(result) == len(_SUBCLASSES_IBGE)


@pytest.mark.asyncio
async def test_get_classes_filtra_localmente(client):
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get_list") as mock_get:
        mock_get.return_value = [
            {
                "id": "5611",
                "descricao": "Restaurantes e outros serviços de alimentação e bebidas",
                "grupo": {"descricao": "Alimentação", "divisao": {"descricao": "Alimentação"}},
            },
            {"id": "6201", "descricao": "Desenvolvimento de programas de computador sob encomenda"},
        ]
        result = await client.get_classes("programas de computador")
        assert [c.código for c in result] == ["6201"]
        mock_get.assert_awaited_once_with("/classes")
