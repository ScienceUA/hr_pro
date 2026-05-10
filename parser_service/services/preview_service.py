import logging
import re
from typing import Any

from parser_service.config.settings import settings
from parser_service.api.dto import (
    ParserError,
    ParserPreviewItem,
    ParserPreviewRequest,
    ParserPreviewResponse,
    ParserSource,
)
from parser_service.execution.executor import RequestExecutor
from parser_service.parsing.models import ParsingResult
from parser_service.sources.robotaua import RobotaUaAdapter
from parser_service.sources.workua import WorkUaAdapter
from parser_service.storage.repository import BaseRepository

logger = logging.getLogger(__name__)

NOT_IMPLEMENTED_ERROR = ParserError(
    code="not_implemented",
    message="Parser adapter execution is not implemented for this source yet.",
)


class PreviewOnlyRepository(BaseRepository):
    """Repository stub for adapter preview paths that do not persist data."""

    def exists(self, resume_id: str) -> bool:
        return False

    def save_result(self, result: ParsingResult):
        raise NotImplementedError("Parser preview must not persist parse results.")

    def save_analysis(self, analysis: dict):
        raise NotImplementedError("Parser preview must not persist analyses.")

    def cleanup(self, session_id: str = None, dry_run: bool = False) -> int:
        return 0


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


async def build_parser_preview_response(
    request: ParserPreviewRequest,
) -> ParserPreviewResponse:
    if request.source == ParserSource.WORKUA:
        return await preview_workua(request)
    if request.source == ParserSource.ROBOTAUA:
        return await preview_robotaua(request)
    return ParserPreviewResponse(
        items=[],
        total_found=0,
        returned_count=0,
        errors=[NOT_IMPLEMENTED_ERROR],
        implemented=False,
    )


async def preview_workua(
    request: ParserPreviewRequest,
    *,
    adapter: WorkUaAdapter | None = None,
) -> ParserPreviewResponse:
    workua_adapter = adapter or build_workua_adapter()
    search_payload = _to_workua_search_payload(request)

    try:
        adapter_response = await workua_adapter.preview(search_payload)
    except Exception as exc:
        logger.exception("Work.ua preview failed")
        return ParserPreviewResponse(
            items=[],
            total_found=0,
            returned_count=0,
            errors=[
                ParserError(
                    code="preview_failed",
                    message=str(exc),
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    urls = adapter_response.get("urls") or []
    items = [
        _workua_item_from_url(url)
        for url in urls[: request.limit]
        if isinstance(url, str) and url
    ]
    total_found = adapter_response.get("total_found")
    if not isinstance(total_found, int):
        total_found = len(urls)

    return ParserPreviewResponse(
        items=items,
        total_found=total_found,
        returned_count=len(items),
        errors=[],
        implemented=True,
    )


async def preview_robotaua(
    request: ParserPreviewRequest,
    *,
    adapter: RobotaUaAdapter | None = None,
) -> ParserPreviewResponse:
    robotaua_adapter = adapter or build_robotaua_adapter()
    search_payload = _to_robotaua_search_payload(request)

    try:
        adapter_response = await robotaua_adapter.preview(search_payload)
    except Exception as exc:
        logger.exception("Robota.ua preview failed")
        return ParserPreviewResponse(
            items=[],
            total_found=0,
            returned_count=0,
            errors=[
                ParserError(
                    code="preview_failed",
                    message=str(exc),
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    urls = adapter_response.get("urls") or []
    items = [
        _robotaua_item_from_url(url)
        for url in urls[: request.limit]
        if isinstance(url, str) and url
    ]
    total_found = adapter_response.get("total_found")
    if not isinstance(total_found, int):
        total_found = len(urls)

    return ParserPreviewResponse(
        items=items,
        total_found=total_found,
        returned_count=len(items),
        errors=[],
        implemented=True,
    )


def _to_workua_search_payload(request: ParserPreviewRequest) -> dict[str, Any]:
    filters = dict(request.filters)
    return {
        "query": request.query,
        "city": request.location,
        "source": request.source.value,
        "pages": 1,
        "params": filters,
        **filters,
    }


def _to_robotaua_search_payload(request: ParserPreviewRequest) -> dict[str, Any]:
    filters = dict(request.filters)
    return {
        "query": request.query,
        "city": request.location,
        "source": request.source.value,
        "pages": 1,
        "params": filters,
        **filters,
    }


def _workua_item_from_url(url: str) -> ParserPreviewItem:
    external_id = _extract_workua_resume_id(url) or url.rstrip("/").rsplit("/", 1)[-1]
    return ParserPreviewItem(
        source=ParserSource.WORKUA,
        external_id=external_id,
        url=url,
        title="",
        candidate_name=None,
        updated_at=None,
    )


def _robotaua_item_from_url(url: str) -> ParserPreviewItem:
    external_id = _extract_robotaua_resume_id(url) or _last_url_path_segment(url)
    return ParserPreviewItem(
        source=ParserSource.ROBOTAUA,
        external_id=external_id,
        url=url,
        title="",
        candidate_name=None,
        updated_at=None,
    )


def _extract_workua_resume_id(url: str) -> str | None:
    match = re.search(r"/resumes/([^/?#]+)/?", url)
    return match.group(1) if match else None


def _extract_robotaua_resume_id(url: str) -> str | None:
    match = re.search(r"/candidates/([^/?#]+)/?", url)
    return match.group(1) if match else None


def _last_url_path_segment(url: str) -> str:
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1]
