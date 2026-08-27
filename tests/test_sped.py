"""Tests for SPED parsing edge cases."""

from datetime import date

import pytest

from mcp_fiscal_brasil.sped.tools import analisar_sped, listar_registros_sped


async def test_analisar_sped_ignores_blank_lines_in_total_records() -> None:
    content = (
        "|0000|015|0|N||EMPRESA TESTE LTDA|12345678000195||SP|123456789|3550308|||0|01012024|31012024|\n"
        "\n"
        "|9999|2|\n"
    )

    response = await analisar_sped(content)

    assert response.resumo is not None
    assert response.resumo.total_registros == 2
    assert response.resumo.tipos_registros == {"0000": 1, "9999": 1}
    assert response.erros == []


async def test_analisar_sped_empty_content_reports_missing_opening() -> None:
    response = await analisar_sped(" \n ")

    assert response.resumo is not None
    assert response.resumo.total_registros == 0
    assert response.resumo.tipos_registros == {}
    assert "Registro 0000" in response.erros[0]


async def test_listar_registros_sped_strips_requested_record_type() -> None:
    content = (
        "|C100|0|1|55|00|123|31012024|100.00|\n|C100|0|1|55|00|124|31012024|250.00|\n|9999|3|\n"
    )

    records = await listar_registros_sped(content, " c100 ")

    assert [record["registro"] for record in records] == ["C100", "C100"]
    assert records[0]["raw"] == "|C100|0|1|55|00|123|31012024|100.00|"


@pytest.mark.asyncio
async def test_analisar_sped_reconhece_leiaute_efd_icms_ipi() -> None:
    conteudo = (
        "|0000|017|0|01012026|31012026|EMPRESA TESTE LTDA|12345678000195||SP|123456789|3550308|"
        "|SUF1|A|1|\n|0001|0|\n|0990|2|\n|9999|4|\n"
    )
    resultado = await analisar_sped(conteudo)
    abertura = resultado.abertura
    assert resultado.tipo_sped == "EFD-ICMS-IPI"
    assert abertura is not None and abertura.layout == "EFD-ICMS-IPI"
    assert abertura.periodo_inicial == date(2026, 1, 1)
    assert abertura.periodo_final == date(2026, 1, 31)
    assert resultado.resumo.periodo_inicial == date(2026, 1, 1)
    assert abertura.nome_empresarial == "EMPRESA TESTE LTDA"
    assert abertura.cnpj == "12345678000195"
    assert abertura.uf == "SP"
    assert abertura.ie == "123456789"
    assert abertura.cod_municipio == "3550308"
    assert abertura.suframa == "SUF1"
    assert abertura.ind_perfil == "A"
    assert abertura.ind_ativ == "1"
    # Campos que nao existem no leiaute EFD-ICMS/IPI nao recebem datas por engano.
    assert abertura.indicador_situacao is None
    assert abertura.num_rec_scp is None


@pytest.mark.asyncio
async def test_analisar_sped_reconhece_leiaute_efd_contribuicoes() -> None:
    conteudo = (
        "|0000|006|0|||01012026|31012026|EMPRESA TESTE LTDA|12345678000195|SP|3550308||00|0|\n"
        "|0001|0|\n|9999|3|\n"
    )
    resultado = await analisar_sped(conteudo)
    abertura = resultado.abertura
    assert resultado.tipo_sped == "EFD-Contribuicoes"
    assert abertura is not None and abertura.layout == "EFD-Contribuicoes"
    assert abertura.periodo_inicial == date(2026, 1, 1)
    assert abertura.nome_empresarial == "EMPRESA TESTE LTDA"
    assert abertura.cnpj == "12345678000195"
    assert abertura.uf == "SP"
    assert abertura.cod_municipio == "3550308"
    assert abertura.ind_nat_pj == "00"
    assert abertura.ind_ativ == "0"


@pytest.mark.asyncio
async def test_analisar_sped_reconhece_leiaute_ecd_e_ecf() -> None:
    ecd = "|0000|LECD|01012025|31122025|EMPRESA TESTE LTDA|12345678000195|SP|123456789|3550308|||||||0|\n|9999|2|\n"
    resultado = await analisar_sped(ecd)
    assert resultado.tipo_sped == "ECD"
    assert resultado.abertura is not None
    assert resultado.abertura.periodo_final == date(2025, 12, 31)
    assert resultado.abertura.cnpj == "12345678000195"
    assert resultado.abertura.ie == "123456789"

    ecf = "|0000|LECF|0010|12345678000195|EMPRESA TESTE LTDA|0|0|||01012025|31122025|N||0||\n|9999|2|\n"
    resultado = await analisar_sped(ecf)
    assert resultado.tipo_sped == "ECF"
    assert resultado.abertura is not None
    assert resultado.abertura.codigo_versao_leiaute == "0010"
    assert resultado.abertura.cnpj == "12345678000195"
    assert resultado.abertura.nome_empresarial == "EMPRESA TESTE LTDA"
    assert resultado.abertura.periodo_inicial == date(2025, 1, 1)
    assert resultado.abertura.periodo_final == date(2025, 12, 31)


@pytest.mark.asyncio
async def test_analisar_sped_mantem_leiaute_legado(sped_abertura_sample: str) -> None:
    resultado = await analisar_sped(sped_abertura_sample)
    assert resultado.tipo_sped == "EFD-ICMS-IPI"
    assert resultado.abertura is not None
    assert resultado.abertura.layout is None
    assert resultado.abertura.cnpj == "12345678000195"
