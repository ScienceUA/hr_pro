import logging
from datetime import datetime, timezone

from parser_service.api.dto import (
    ParserError,
    ParserFreshnessRequest,
    ParserFreshnessResponse,
)
from parser_service.freshness_validator import FreshnessValidator

logger = logging.getLogger(__name__)

URL_REQUIRED_ERROR = ParserError(
    code="freshness_url_required",
    message="Freshness check requires a URL.",
)


async def build_parser_freshness_response(
    request: ParserFreshnessRequest,
) -> ParserFreshnessResponse:
    checked_at = _utc_now_iso()

    if request.url is None:
        return ParserFreshnessResponse(
            source=request.source,
            external_id=request.external_id,
            is_fresh=False,
            updated_at=None,
            checked_at=checked_at,
            errors=[URL_REQUIRED_ERROR],
            implemented=True,
        )

    try:
        is_fresh = await FreshnessValidator.is_fresh(str(request.url))
    except Exception as exc:
        logger.exception("Freshness check failed")
        return ParserFreshnessResponse(
            source=request.source,
            external_id=request.external_id,
            is_fresh=False,
            updated_at=None,
            checked_at=checked_at,
            errors=[
                ParserError(
                    code="freshness_check_failed",
                    message=str(exc),
                    details={"source": request.source},
                )
            ],
            implemented=True,
        )

    return ParserFreshnessResponse(
        source=request.source,
        external_id=request.external_id,
        is_fresh=is_fresh,
        updated_at=None,
        checked_at=checked_at,
        errors=[],
        implemented=True,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
