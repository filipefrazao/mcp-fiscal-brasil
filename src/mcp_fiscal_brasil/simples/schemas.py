from datetime import date

from pydantic import BaseModel, Field, model_validator


class SimplesStatus(BaseModel):
    """Situação de um CNPJ no Simples Nacional e no SIMEI (MEI).

    ``simples_nacional`` e ``mei`` são tri-estado: ``True``/``False`` quando alguma
    fonte pública confirmou o regime e ``None`` quando nenhuma fonte trouxe a
    informação. Nesse caso ``verificado`` fica ``False`` e o consumidor NÃO deve
    tratar o resultado como "não optante".
    """

    cnpj: str
    simples_nacional: bool | None = Field(
        default=None,
        description="True/False quando verificado; None quando nenhuma fonte informou.",
    )
    data_opcao: date | None = None
    data_exclusao: date | None = None
    mei: bool | None = Field(
        default=None,
        description="True/False quando verificado; None quando nenhuma fonte informou.",
    )
    data_opcao_mei: date | None = None
    data_exclusao_mei: date | None = None
    fonte: str | None = Field(
        default=None, description="Fonte que confirmou o regime (BrasilAPI ou ReceitaWS)."
    )
    verificado: bool = Field(
        default=False,
        description="True quando alguma fonte confirmou o regime; False = desconhecido.",
    )

    @model_validator(mode="after")
    def _marca_verificado(self) -> "SimplesStatus":
        if self.simples_nacional is not None or self.mei is not None:
            self.verificado = True
        return self
