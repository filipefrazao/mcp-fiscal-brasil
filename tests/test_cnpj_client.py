"""Tests for CNPJ client response parsing edge cases."""

import pytest

from mcp_fiscal_brasil.cnpj.client import CNPJClient


def test_parse_brasil_api_handles_null_collections_and_invalid_date() -> None:
    client = CNPJClient()

    response = client._parse_brasil_api(
        {
            "razao_social": "EMPRESA TESTE LTDA",
            "descricao_situacao_cadastral": "ATIVA",
            "natureza_juridica": "206-2 - Sociedade Empresaria Limitada",
            "cnaes_secundarios": None,
            "qsa": None,
            "data_inicio_atividade": "31/01/2024",
        },
        "12345678000195",
    )

    assert response.cnpj == "12345678000195"
    assert response.atividades_secundarias == []
    assert response.qsa == []
    assert response.data_abertura is None


@pytest.mark.asyncio
async def test_parse_brasil_api_le_cnaes_secundarios_e_numero_sem_acento() -> None:
    """A BrasilAPI usa chaves sem acento; antes os CNAEs secundarios e o numero eram descartados."""
    from unittest.mock import patch

    from mcp_fiscal_brasil.cnpj.client import CNPJClient

    payload = {
        "cnpj": "33000167000101",
        "razao_social": "EMPRESA TESTE S.A.",
        "descricao_situacao_cadastral": "ATIVA",
        "natureza_juridica": "Sociedade Anônima Aberta",
        "cnae_fiscal": 600001,
        "cnae_fiscal_descricao": "Extração de petróleo e gás natural",
        "cnaes_secundarios": [
            {"codigo": 1921700, "descricao": "Fabricação de produtos do refino de petróleo"},
            {"codigo": 0, "descricao": "Não informada"},
        ],
        "logradouro": "REPUBLICA DO CHILE",
        "numero": "65",
        "bairro": "CENTRO",
        "municipio": "RIO DE JANEIRO",
        "uf": "RJ",
        "cep": "20031170",
        "qsa": [],
    }
    with patch("mcp_fiscal_brasil._core.http.HTTPClient.get") as mock_get:
        mock_get.return_value = payload
        resultado = await CNPJClient().consultar("33000167000101")

    assert [a.código for a in resultado.atividades_secundarias] == ["1921700"]
    assert resultado.endereco is not None
    assert resultado.endereco.número == "65"
