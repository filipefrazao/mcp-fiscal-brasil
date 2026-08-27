"""Ferramentas MCP para analise de arquivos SPED."""

from datetime import date

from .._core import get_logger
from .schemas import InfoAberturaSPED, ResumoPeriodoSPED, SPEDAnaliseResponse

logger = get_logger(__name__)

# Identificação do tipo de SPED pelo registro 0000 campo tipo_escrituracao
TIPOS_SPED: dict[str, str] = {
    "0": "EFD-ICMS-IPI",
    "1": "EFD-Contribuicoes",
    "2": "ECD",
    "3": "ECF",
}

# Posições dos campos com valores monetários por registro (layout pipe-delimitado).
# Os índices referem-se à lista campos[1:] retornada por listar_registros_sped
# (ou seja, após remover o campo REG que ocupa a posição 0 da linha completa).
#
# Fontes:
#   EFD-Contribuicoes: Guia Prático EFD Contribuições, Ato COTEPE/ICMS 65/2013
#     M210 campo 7 (índice 6) = VL_CONT_PER (contribuicao PIS apurada no período)
#     M610 campo 7 (índice 6) = VL_CONT_PER (contribuicao COFINS apurada no período)
#     0110 campo 1 (índice 0) = COD_INC_TRIB (1=cumulativo, 2=nao-cumulativo)
#   EFD ICMS/IPI: Guia Prático EFD ICMS/IPI, Ato COTEPE/ICMS 44/2018 (versao 018)
#     E110 layout completo (campos 01 a 15):
#       campo 02 (índice  0) = VL_TOT_DEBITOS       - total de débitos BRUTOS de saídas/prestações
#       campo 03 (índice  1) = VL_AJ_DEBITOS        - ajustes a débito por doc. fiscal
#       campo 04 (índice  2) = VL_TOT_AJ_DEBITOS    - total de ajustes a débito
#       campo 05 (índice  3) = VL_ESTORNOS_CRED     - estornos de créditos
#       campo 06 (índice  4) = VL_TOT_CREDITOS      - total de créditos por entradas
#       campo 07 (índice  5) = VL_AJ_CREDITOS       - ajustes a crédito por doc. fiscal
#       campo 08 (índice  6) = VL_TOT_AJ_CREDITOS   - total de ajustes a crédito
#       campo 09 (índice  7) = VL_ESTORNOS_DEB      - estornos de débitos
#       campo 10 (índice  8) = VL_SLD_CREDOR_ANT    - saldo credor do período anterior
#       campo 11 (índice  9) = VL_SLD_APURADO       - saldo devedor apurado (= débitos - créditos)
#       campo 12 (índice 10) = VL_TOT_DED           - total de deduções
#       campo 13 (índice 11) = VL_ICMS_RECOLHER     - ICMS a recolher (= VL_SLD_APURADO - VL_TOT_DED)
#       campo 14 (índice 12) = VL_SLD_CREDOR_TRANSPORTAR
#       campo 15 (índice 13) = DEB_ESP              - valores extra-apuração
# Constantes de layout expostas como nomes públicos para que módulos consumidores
# (ex.: agentic/sped.py) possam importá-las sem acoplamento a nomes privados (_).
# O typechecker verifica esses imports normalmente pois os nomes são públicos.

CAMPO_VALOR: dict[str, int] = {
    "M210": 6,  # VL_CONT_PER - PIS (campo 7 do registro, índice 6 em campos[1:])
    "M610": 6,  # VL_CONT_PER - COFINS (campo 7 do registro, índice 6 em campos[1:])
}

# Para o registro E110 são extraídos dois campos com semânticas distintas.
# Usar CAMPO_E110_* em vez de CAMPO_VALOR para o processamento especializado do ICMS.
CAMPO_E110_TOT_DEBITOS: int = 0  # campo 02 - VL_TOT_DEBITOS: débitos BRUTOS (informativo)
CAMPO_E110_RECOLHER: int = 11  # campo 13 - VL_ICMS_RECOLHER: valor LÍQUIDO a recolher

# Campo do regime PIS/COFINS no registro 0110
CAMPO_0110_REGIME: int = 0  # COD_INC_TRIB: "1"=cumulativo, "2"=nao-cumulativo
REGIME_0110: dict[str, str] = {
    "1": "cumulativo",
    "2": "nao-cumulativo",
}

# Aliases com underscore mantidos para compatibilidade com código legado.
# Novos módulos devem importar os nomes sem underscore acima.
_CAMPO_VALOR = CAMPO_VALOR
_CAMPO_E110_TOT_DEBITOS = CAMPO_E110_TOT_DEBITOS
_CAMPO_E110_RECOLHER = CAMPO_E110_RECOLHER
_CAMPO_0110_REGIME = CAMPO_0110_REGIME
_REGIME_0110 = REGIME_0110


def _to_float(valor: str | None) -> float:
    """Converte valor monetário SPED (vírgula decimal) para float.

    O layout oficial do SPED (EFD-Contribuições, EFD ICMS/IPI, ECD, ECF)
    define a VÍRGULA como único separador decimal. O ponto, quando presente,
    é separador de milhar (formato brasileiro), conforme Guia Prático EFD
    Contribuições (Ato COTEPE/ICMS 65/2013) e EFD ICMS/IPI (Ato COTEPE/ICMS
    44/2018). Valores no padrão en-US (ponto decimal sem vírgula) não são
    esperados no SPED e, se ocorrerem, serão interpretados como inteiro
    (ponto removido como milhar), o que é seguro para os casos reais.

    Premissa: vírgula é SEMPRE o separador decimal neste contexto.
    Estratégia: remover todos os pontos (milhar) e trocar a vírgula por ponto.

    Exemplos de entradas suportadas:
      "3.708.500,27" -> 3708500.27  (milhar + decimal)
      "1.500,00"     -> 1500.0      (milhar + decimal)
      "3708500,27"   -> 3708500.27  (sem milhar, apenas decimal)
      "100,00"       -> 100.0
      "-500,50"      -> -500.5      (negativo)
      "0"            -> 0.0
      ""             -> 0.0
      None           -> 0.0

    Args:
        valor: String monetária SPED ou None/vazia.

    Returns:
        Valor como float. Retorna 0.0 para entradas vazias, None ou inválidas.
    """
    if not valor or not valor.strip():
        return 0.0
    try:
        # Remove pontos de milhar e converte vírgula decimal para ponto
        normalizado = valor.strip().replace(".", "").replace(",", ".")
        return float(normalizado)
    except ValueError:
        return 0.0


def _parse_linha_sped(linha: str) -> list[str]:
    """Analisa uma linha SPED (delimitada por '|') e remove os pipes externos."""
    if linha.startswith("|"):
        linha = linha[1:]
    if linha.endswith("|"):
        linha = linha[:-1]
    return linha.split("|")


def _to_date(valor: str) -> date | None:
    """Converte data SPED (DDMMAAAA) em objeto date."""
    valor = valor.strip()
    if len(valor) == 8 and valor.isdigit():
        try:
            return date(int(valor[4:]), int(valor[2:4]), int(valor[:2]))
        except ValueError:
            return None
    return None


# Posições dos campos do registro 0000 por leiaute (índice 0 = "0000").
_MAPA_0000: dict[str, dict[str, int]] = {
    # EFD-ICMS/IPI (Guia Prático):
    # |0000|COD_VER|COD_FIN|DT_INI|DT_FIN|NOME|CNPJ|CPF|UF|IE|COD_MUN|IM|SUFRAMA|IND_PERFIL|IND_ATIV|
    "EFD-ICMS-IPI": {
        "codigo_versao_leiaute": 1,
        "tipo_escrituracao": 2,
        "periodo_inicial": 3,
        "periodo_final": 4,
        "nome_empresarial": 5,
        "cnpj": 6,
        "cpf": 7,
        "uf": 8,
        "ie": 9,
        "cod_municipio": 10,
        "im": 11,
        "suframa": 12,
        "ind_perfil": 13,
        "ind_ativ": 14,
    },
    # EFD-Contribuições:
    # |0000|COD_VER|TIPO_ESCRIT|IND_SIT_ESP|NUM_REC_ANTERIOR|DT_INI|DT_FIN|NOME|CNPJ|UF|COD_MUN|SUFRAMA|IND_NAT_PJ|IND_ATIV|
    "EFD-Contribuicoes": {
        "codigo_versao_leiaute": 1,
        "tipo_escrituracao": 2,
        "indicador_situacao": 3,
        "num_rec_scp": 4,
        "periodo_inicial": 5,
        "periodo_final": 6,
        "nome_empresarial": 7,
        "cnpj": 8,
        "uf": 9,
        "cod_municipio": 10,
        "suframa": 11,
        "ind_nat_pj": 12,
        "ind_ativ": 13,
    },
    # ECD: |0000|LECD|DT_INI|DT_FIN|NOME|CNPJ|UF|IE|COD_MUN|IM|IND_SIT_ESP|...
    "ECD": {
        "periodo_inicial": 2,
        "periodo_final": 3,
        "nome_empresarial": 4,
        "cnpj": 5,
        "uf": 6,
        "ie": 7,
        "cod_municipio": 8,
        "im": 9,
        "indicador_situacao": 10,
    },
    # ECF: |0000|LECF|COD_VER|CNPJ|NOME|IND_SIT_INI_PER|SIT_ESPECIAL|PAT_REMAN|DT_SIT_ESP|
    #      DT_INI|DT_FIN|RETIFICADORA|NUM_REC|TIP_ECF|COD_SCP|
    "ECF": {
        "codigo_versao_leiaute": 2,
        "cnpj": 3,
        "nome_empresarial": 4,
        "indicador_situacao": 6,
        "periodo_inicial": 9,
        "periodo_final": 10,
        "num_rec_scp": 12,
    },
    # Leiaute legado deste projeto, mantido quando nenhum dos oficiais é reconhecido.
    "LEGADO": {
        "codigo_versao_leiaute": 1,
        "tipo_escrituracao": 2,
        "indicador_situacao": 3,
        "num_rec_scp": 4,
        "nome_empresarial": 5,
        "cnpj": 6,
        "cpf": 7,
        "uf": 8,
        "ie": 9,
        "cod_municipio": 10,
        "suframa": 11,
        "ind_perfil": 12,
        "ind_ativ": 13,
        "periodo_inicial": 14,
        "periodo_final": 15,
    },
}


def _detectar_layout_0000(campos: list[str]) -> str:
    """Identifica o leiaute do registro 0000 pela assinatura dos campos."""
    identificador = campos[1].strip().upper() if len(campos) > 1 else ""
    if identificador == "LECD":
        return "ECD"
    if identificador == "LECF":
        return "ECF"
    if len(campos) > 4 and _to_date(campos[3]) and _to_date(campos[4]):
        return "EFD-ICMS-IPI"
    if len(campos) > 6 and _to_date(campos[5]) and _to_date(campos[6]):
        return "EFD-Contribuicoes"
    return "LEGADO"


def _parse_abertura(campos: list[str]) -> InfoAberturaSPED:
    """Analisa o registro 0000 (abertura) do arquivo SPED conforme o leiaute detectado."""
    layout = _detectar_layout_0000(campos)
    mapa = _MAPA_0000[layout]

    def get(nome: str) -> str | None:
        indice = mapa.get(nome)
        if indice is None or indice >= len(campos):
            return None
        valor = campos[indice].strip()
        return valor or None

    return InfoAberturaSPED(
        layout=None if layout == "LEGADO" else layout,
        codigo_versao_leiaute=get("codigo_versao_leiaute"),
        tipo_escrituracao=get("tipo_escrituracao"),
        indicador_situacao=get("indicador_situacao"),
        num_rec_scp=get("num_rec_scp"),
        nome_empresarial=get("nome_empresarial"),
        cnpj=get("cnpj"),
        cpf=get("cpf"),
        uf=get("uf"),
        ie=get("ie"),
        cod_municipio=get("cod_municipio"),
        im=get("im"),
        suframa=get("suframa"),
        ind_perfil=get("ind_perfil"),
        ind_nat_pj=get("ind_nat_pj"),
        ind_ativ=get("ind_ativ"),
        periodo_inicial=_to_date(get("periodo_inicial") or ""),
        periodo_final=_to_date(get("periodo_final") or ""),
    )


async def analisar_sped(conteudo: str, nome_arquivo: str | None = None) -> SPEDAnaliseResponse:
    """
    Analisa um arquivo SPED e extrai informações sobre o período, empresa e tipos de registros.

    Suporta EFD-ICMS/IPI, EFD-Contribuições, ECD e ECF.

    Args:
        conteudo: Conteúdo do arquivo SPED como string (formato pipe-delimitado)
        nome_arquivo: Nome do arquivo (opcional, para informação)

    Returns:
        SPEDAnaliseResponse com resumo do arquivo, informações da empresa e contagem de registros.
    """
    logger.info("sped_analysis_started", nome_arquivo=nome_arquivo or "desconhecido")

    abertura: InfoAberturaSPED | None = None
    tipos_registros: dict[str, int] = {}
    erros: list[str] = []
    avisos: list[str] = []
    periodo_inicial: date | None = None
    periodo_final: date | None = None

    linhas = [linha for linha in conteudo.strip().splitlines() if linha.strip()]
    total = len(linhas)

    for _num_linha, linha in enumerate(linhas, 1):
        linha = linha.strip()
        campos = _parse_linha_sped(linha)
        if not campos:
            continue

        registro = campos[0]
        tipos_registros[registro] = tipos_registros.get(registro, 0) + 1

        # Registro de abertura
        if registro == "0000" and abertura is None:
            abertura = _parse_abertura(campos)
            periodo_inicial = abertura.periodo_inicial
            periodo_final = abertura.periodo_final

    tipo_sped = "Desconhecido"
    if abertura and abertura.layout:
        tipo_sped = abertura.layout
    elif abertura and abertura.tipo_escrituracao:
        tipo_sped = TIPOS_SPED.get(abertura.tipo_escrituracao, f"Tipo {abertura.tipo_escrituracao}")

    # Verifica presença de registros obrigatórios
    if "0000" not in tipos_registros:
        erros.append("Registro 0000 (abertura) não encontrado - arquivo possivelmente inválido")
    if "9999" not in tipos_registros:
        avisos.append("Registro 9999 (encerramento) não encontrado - arquivo pode estar incompleto")

    resumo = ResumoPeriodoSPED(
        periodo_inicial=periodo_inicial,
        periodo_final=periodo_final,
        total_registros=total,
        tipos_registros=tipos_registros,
        cnpj=abertura.cnpj if abertura else None,
        razao_social=abertura.nome_empresarial if abertura else None,
        uf=abertura.uf if abertura else None,
    )

    return SPEDAnaliseResponse(
        tipo_sped=tipo_sped,
        abertura=abertura,
        resumo=resumo,
        avisos=avisos,
        erros=erros,
    )


async def listar_registros_sped(
    conteudo: str, tipo_registro: str
) -> list[dict[str, str | list[str]]]:
    """
    Lista todos os registros de um determinado tipo em um arquivo SPED.

    Args:
        conteudo: Conteúdo do arquivo SPED
        tipo_registro: Código do registro a buscar (ex: 'C100', 'E110', '0140')

    Returns:
        Lista de dicionários com os campos de cada ocorrência do registro.
        Cada dicionário contém:
        - "registro": código do registro (string)
        - "campos": lista de campos (excluindo REG), indexável por posição
        - "raw": linha original intacta (string)
    """
    tipo_registro = tipo_registro.upper().strip()
    resultado: list[dict[str, str | list[str]]] = []

    for linha in conteudo.strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue
        campos = _parse_linha_sped(linha)
        if campos and campos[0] == tipo_registro:
            resultado.append(
                {
                    "registro": tipo_registro,
                    "campos": campos[1:],  # lista indexável, sem o campo REG
                    "raw": linha,
                }
            )

    return resultado
