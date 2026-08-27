from datetime import date

from pydantic import BaseModel, Field, model_validator


class MEIStatus(BaseModel):
    """Situação de um CNPJ no SIMEI (MEI), com o Simples Nacional como contexto.

    ``mei`` e ``simples_nacional`` são tri-estado (``None`` = nenhuma fonte informou;
    ver ``verificado``).
    """

    cnpj: str
    mei: bool | None = Field(
        default=None,
        description="True/False quando verificado; None quando nenhuma fonte informou.",
    )
    data_opcao_mei: date | None = None
    data_exclusao_mei: date | None = None
    simples_nacional: bool | None = Field(
        default=None,
        description="True/False quando verificado; None quando nenhuma fonte informou.",
    )
    fonte: str | None = Field(
        default=None, description="Fonte que confirmou o regime (BrasilAPI ou ReceitaWS)."
    )
    verificado: bool = Field(
        default=False,
        description="True quando alguma fonte confirmou o regime; False = desconhecido.",
    )

    @model_validator(mode="after")
    def _marca_verificado(self) -> "MEIStatus":
        if self.simples_nacional is not None or self.mei is not None:
            self.verificado = True
        return self
