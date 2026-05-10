import logging
from typing import Any

from pydantic import HttpUrl

from parser_service.api.dto import (
    ParserError,
    ParserParseRequest,
    ParserParseResponse,
    ParserSource,
)
from parser_service.config.settings import settings
from parser_service.execution.executor import RequestExecutor
from parser_service.parsing.models import ParsingResult
from parser_service.services.preview_service import PreviewOnlyRepository
from parser_service.sources.robotaua import RobotaUaAdapter
from parser_service.sources.workua import WorkUaAdapter

logger = logging.getLogger(__name__)

NOT_IMPLEMENTED_ERROR = ParserError(
    code="not_implemented",
    message="Parser adapter execution is not implemented in this HTTP contract yet.",
)

NO_RESULTS_ERROR = ParserError(
    code="parse_no_results",
    message="Parser adapter returned no parsed results.",
)


def build_workua_adapter() -> WorkUaAdapter:
    return WorkUaAdapter(
        executor=RequestExecutor(settings=settings),
        repository=PreviewOnlyRepository(),
    )


def build_robotaua_adapter() -> RobotaUaAdapter:
    return RobotaUaAdapter(
        executor=RequestExecutor(settings=settings),
        repository=PreviewOnlyRepository(),
    )


async def build_parser_parse_response(
    request: ParserParseRequest,
) -> ParserParseResponse:
    if request.source == ParserSource.WORKUA:
        return await parse_workua(request)
    if request.source == ParserSource.ROBOTAUA:
        return await parse_robotaua(request)
    return _not_implemented_response(request)


async def parse_workua(
    request: ParserParseRequest,
    *,
    adapter: WorkUaAdapter | None = None,
) -> ParserParseResponse:
    if request.url is None:
        return ParserParseResponse(
            source=request.source,
            external_id=request.external_id,
            url=request.url,
            parsed=False,
            data={},
            errors=[
                ParserError(
                    code="parse_url_required",
                    message="Work.ua parse requires a URL.",
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    workua_adapter = adapter or build_workua_adapter()
    url = str(request.url)

    try:
        _stats, results = await workua_adapter.run_from_urls([url])
    except Exception as exc:
        logger.exception("Work.ua parse failed")
        return ParserParseResponse(
            source=request.source,
            external_id=request.external_id,
            url=request.url,
            parsed=False,
            data={},
            errors=[
                ParserError(
                    code="parse_failed",
                    message=str(exc),
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    if not results:
        return ParserParseResponse(
            source=request.source,
            external_id=request.external_id,
            url=request.url,
            parsed=False,
            data={},
            errors=[NO_RESULTS_ERROR],
            implemented=True,
        )

    result = results[0]
    data = _parsing_result_to_dict(result)
    external_id = request.external_id or _external_id_from_result(result)

    return ParserParseResponse(
        source=request.source,
        external_id=external_id,
        url=_url_from_result(result, request.url),
        parsed=True,
        data=data,
        errors=[],
        implemented=True,
    )


async def parse_robotaua(
    request: ParserParseRequest,
    *,
    adapter: RobotaUaAdapter | None = None,
) -> ParserParseResponse:
    if request.url is None:
        return ParserParseResponse(
            source=request.source,
            external_id=request.external_id,
            url=request.url,
            parsed=False,
            data={},
            errors=[
                ParserError(
                    code="parse_url_required",
                    message="Robota.ua parse requires a URL.",
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    robotaua_adapter = adapter or build_robotaua_adapter()
    url = str(request.url)

    try:
        _stats, results = await robotaua_adapter.run_from_urls([url])
    except Exception as exc:
        logger.exception("Robota.ua parse failed")
        return ParserParseResponse(
            source=request.source,
            external_id=request.external_id,
            url=request.url,
            parsed=False,
            data={},
            errors=[
                ParserError(
                    code="parse_failed",
                    message=str(exc),
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    if not results:
        return ParserParseResponse(
            source=request.source,
            external_id=request.external_id,
            url=request.url,
            parsed=False,
            data={},
            errors=[NO_RESULTS_ERROR],
            implemented=True,
        )

    result = results[0]
    data = _parsing_result_to_dict(result)
    external_id = request.external_id or _external_id_from_result(result)

    return ParserParseResponse(
        source=request.source,
        external_id=external_id,
        url=_url_from_result(result, request.url),
        parsed=True,
        data=data,
        errors=[],
        implemented=True,
    )


def _not_implemented_response(request: ParserParseRequest) -> ParserParseResponse:
    return ParserParseResponse(
        source=request.source,
        external_id=request.external_id,
        url=request.url,
        parsed=False,
        data={},
        errors=[NOT_IMPLEMENTED_ERROR],
        implemented=False,
    )


def _parsing_result_to_dict(result: ParsingResult) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json", by_alias=True)
    return dict(result)


def _external_id_from_result(result: ParsingResult) -> str | None:
    payload = getattr(result, "payload", None)
    resume_id = getattr(payload, "resume_id", None)
    if isinstance(resume_id, str) and resume_id:
        return resume_id
    return None


def _url_from_result(result: ParsingResult, fallback: HttpUrl) -> str:
    result_url = getattr(result, "url", None)
    if isinstance(result_url, str) and result_url:
        return result_url
    return str(fallback)
