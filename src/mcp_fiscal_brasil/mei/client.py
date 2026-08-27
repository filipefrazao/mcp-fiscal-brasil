"""Cliente para consulta do MEI (SIMEI).

A situação no SIMEI vem das mesmas fontes públicas do Simples Nacional (BrasilAPI
``/cnpj/v1`` e ReceitaWS), por isso este cliente delega ao ``SimplesClient`` e
apenas projeta o resultado no ``MEIStatus``.
"""

from __future__ import annotations

from mcp_fiscal_brasil._core import get_logger

from ..simples.client import SimplesClient
from .schemas import MEIStatus

logger = get_logger(__name__)


class MEIClient:
    """Cliente para consulta do MEI via BrasilAPI com fallback ReceitaWS."""

    def __init__(self, simples_client: SimplesClient | None = None) -> None:
        self._simples_client = simples_client or SimplesClient()

    async def get_mei_status(self, cnpj: str) -> MEIStatus:
        """Consulta o status MEI de um CNPJ."""
        logger.info("mei_status_started", cnpj=cnpj)
        status = await self._simples_client.get_simples_status(cnpj)
        return MEIStatus(
            cnpj=status.cnpj,
            mei=status.mei,
            data_opcao_mei=status.data_opcao_mei,
            data_exclusao_mei=status.data_exclusao_mei,
            simples_nacional=status.simples_nacional,
            fonte=status.fonte,
        )
