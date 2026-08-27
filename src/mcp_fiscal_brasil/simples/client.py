"""Cliente para consulta do Simples Nacional e do SIMEI (MEI).

Fontes públicas, em ordem:

1. BrasilAPI ``/cnpj/v1/{cnpj}`` — campos ``opcao_pelo_simples`` e ``opcao_pelo_mei``
   (``true``/``false``; ``null`` quando o CNPJ não consta na base do Simples da RFB).
2. ReceitaWS ``/cnpj/{cnpj}`` — objetos ``simples`` e ``simei`` com ``optante`` explícito.

Se nenhuma fonte confirmar o regime, o status volta com ``verificado=False`` e os
campos ``simples_nacional``/``mei`` em ``None`` (desconhecido, não "não optante").

Nota: a rota ``/simples/v1/{cnpj}`` da BrasilAPI, usada até a v0.5.1, não existe
(HTTP 404 para qualquer CNPJ).
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from mcp_fiscal_brasil._core import FiscalNotFoundError, HTTPClient, get_logger, settings
from mcp_fiscal_brasil._core.errors import FiscalError, FiscalHTTPError

from .schemas import SimplesStatus

logger = get_logger(__name__)


def _parse_date(date_str: Any) -> date | None:
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None


def _bool_ou_none(valor: Any) -> bool | None:
    return valor if isinstance(valor, bool) else None


def _parse_brasilapi_cnpj(cnpj: str, data: dict[str, Any]) -> SimplesStatus:
    """Interpreta os campos de Simples/MEI da resposta ``/cnpj/v1`` da BrasilAPI.

    Aceita também o formato plano legado (``simples_nacional``/``mei``).
    """
    simples = _bool_ou_none(data.get("opcao_pelo_simples", data.get("simples_nacional")))
    mei = _bool_ou_none(data.get("opcao_pelo_mei", data.get("mei")))
    verificado = simples is not None or mei is not None
    return SimplesStatus(
        cnpj=cnpj,
        simples_nacional=simples,
        data_opcao=_parse_date(data.get("data_opcao_pelo_simples", data.get("data_opcao_simples"))),
        data_exclusao=_parse_date(
            data.get("data_exclusao_do_simples", data.get("data_exclusao_simples"))
        ),
        mei=mei,
        data_opcao_mei=_parse_date(data.get("data_opcao_pelo_mei", data.get("data_opcao_simei"))),
        data_exclusao_mei=_parse_date(
            data.get("data_exclusao_do_mei", data.get("data_exclusao_simei"))
        ),
        fonte="BrasilAPI" if verificado else None,
    )


def _parse_receitaws(cnpj: str, data: dict[str, Any]) -> SimplesStatus:
    """Interpreta os objetos ``simples``/``simei`` da resposta da ReceitaWS."""
    simples_raw = data.get("simples")
    simei_raw = data.get("simei")
    simples = simples_raw if isinstance(simples_raw, dict) else {}
    simei = simei_raw if isinstance(simei_raw, dict) else {}
    opt_simples = _bool_ou_none(simples.get("optante"))
    opt_mei = _bool_ou_none(simei.get("optante"))
    verificado = opt_simples is not None or opt_mei is not None
    return SimplesStatus(
        cnpj=cnpj,
        simples_nacional=opt_simples,
        data_opcao=_parse_date(simples.get("data_opcao")),
        data_exclusao=_parse_date(simples.get("data_exclusao")),
        mei=opt_mei,
        data_opcao_mei=_parse_date(simei.get("data_opcao")),
        data_exclusao_mei=_parse_date(simei.get("data_exclusao")),
        fonte="ReceitaWS" if verificado else None,
    )


class SimplesClient:
    """Cliente para consulta do Simples Nacional/SIMEI via BrasilAPI com fallback ReceitaWS."""

    def __init__(self) -> None:
        # Memoização por instância: evita repetir as chamadas quando o mesmo CNPJ
        # é consultado por mais de uma tool na mesma análise (ex.: compliance + MEI).
        self._memo: dict[str, SimplesStatus] = {}
        # Deduplicação de consultas em andamento: chamadas concorrentes para o
        # mesmo CNPJ (asyncio.gather) compartilham a mesma tarefa.
        self._em_andamento: dict[str, asyncio.Task[SimplesStatus]] = {}

    def _http_client(self, base_url: str) -> HTTPClient:
        return HTTPClient(
            base_url,
            timeout=settings.mcp_fiscal_http_timeout,
            max_retries=settings.mcp_fiscal_max_retries,
            cache_ttl=settings.mcp_fiscal_cache_ttl,
            rate_limit_per_second=settings.mcp_fiscal_rate_limit,
        )

    async def get_simples_status(self, cnpj: str) -> SimplesStatus:
        """Consulta o status do Simples Nacional e MEI para um CNPJ.

        Raises:
            FiscalNotFoundError: quando nenhuma fonte reconhece o CNPJ.
        """
        cnpj_clean = "".join(c for c in cnpj if c.isdigit())
        if cnpj_clean in self._memo:
            return self._memo[cnpj_clean]

        tarefa = self._em_andamento.get(cnpj_clean)
        if tarefa is None:
            tarefa = asyncio.ensure_future(self._consultar(cnpj_clean))
            self._em_andamento[cnpj_clean] = tarefa
        try:
            return await tarefa
        finally:
            self._em_andamento.pop(cnpj_clean, None)

    async def _consultar(self, cnpj_clean: str) -> SimplesStatus:
        logger.info("simples_status_started", cnpj=cnpj_clean)

        status, encontrado_brasilapi = await self._via_brasilapi(cnpj_clean)
        if status is None or not status.verificado:
            fallback = await self._via_receitaws(
                cnpj_clean, cnpj_ja_encontrado=encontrado_brasilapi
            )
            if fallback is not None and fallback.verificado:
                status = fallback

        if status is None:
            status = SimplesStatus(cnpj=cnpj_clean)
        if not status.verificado:
            logger.warning("simples_status_nao_verificado", cnpj=cnpj_clean)

        self._memo[cnpj_clean] = status
        return status

    async def _via_brasilapi(self, cnpj: str) -> tuple[SimplesStatus | None, bool]:
        """Retorna (status, cnpj_encontrado). Levanta NotFound apenas após o fallback."""
        async with self._http_client(settings.brasilapi_base_url) as client:
            try:
                data = await client.get(f"/cnpj/v1/{cnpj}")
            except FiscalHTTPError as exc:
                if exc.status_code == 404:
                    logger.info("simples_brasilapi_cnpj_not_found", cnpj=cnpj)
                    return None, False
                logger.warning("simples_brasilapi_failed", cnpj=cnpj, error=str(exc))
                return None, True
            except FiscalError as exc:
                logger.warning("simples_brasilapi_failed", cnpj=cnpj, error=str(exc))
                return None, True
        return _parse_brasilapi_cnpj(cnpj, data), True

    async def _via_receitaws(self, cnpj: str, *, cnpj_ja_encontrado: bool) -> SimplesStatus | None:
        async with self._http_client(settings.receita_base_url) as client:
            try:
                data = await client.get(f"/cnpj/{cnpj}")
            except FiscalHTTPError as exc:
                if exc.status_code == 404 and not cnpj_ja_encontrado:
                    raise FiscalNotFoundError("CNPJ não encontrado", "CNPJ", cnpj) from exc
                logger.warning("simples_receitaws_failed", cnpj=cnpj, error=str(exc))
                return None
            except FiscalError as exc:
                logger.warning("simples_receitaws_failed", cnpj=cnpj, error=str(exc))
                return None

        if data.get("status") == "ERROR":
            if not cnpj_ja_encontrado:
                raise FiscalNotFoundError(
                    str(data.get("message") or "CNPJ não encontrado"), "CNPJ", cnpj
                )
            logger.warning("simples_receitaws_error", cnpj=cnpj, message=data.get("message"))
            return None
        if not cnpj_ja_encontrado and not data:
            raise FiscalNotFoundError("CNPJ não encontrado", "CNPJ", cnpj)
        return _parse_receitaws(cnpj, data)
