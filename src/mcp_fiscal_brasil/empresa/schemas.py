from pydantic import BaseModel, Field

from mcp_fiscal_brasil.cnpj.schemas import AtividadeCNAE
from mcp_fiscal_brasil.shared.schemas import Endereco


class EmpresaInfo(BaseModel):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    situacao: str
    porte: str | None = None
    natureza_juridica: str | None = None
    simples_nacional: bool | None = Field(
        default=None,
        description=(
            "True/False quando alguma fonte confirmou o regime; None quando não verificado "
            "(ver regime_verificado). Não tratar None como 'não optante'."
        ),
    )
    mei: bool | None = Field(
        default=None,
        description="True/False quando verificado; None quando não verificado.",
    )
    regime_fonte: str | None = Field(
        default=None, description="Fonte que confirmou Simples/MEI (BrasilAPI ou ReceitaWS)."
    )
    regime_verificado: bool = Field(
        default=False, description="True quando Simples/MEI foram confirmados por alguma fonte."
    )
    atividade_principal: AtividadeCNAE | None = None
    atividades_secundarias: list[AtividadeCNAE] = []
    endereco: Endereco | None = None
