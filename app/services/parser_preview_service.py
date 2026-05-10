from typing import Any

from app.models.search import SearchPayload
from app.services.parser_client import ParserClient


PREVIEW_REFINEMENT_THRESHOLD = 50
MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT = PREVIEW_REFINEMENT_THRESHOLD


def build_parser_preview_request(
    payload: SearchPayload,
    *,
    limit: int = MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT,
) -> dict[str, Any]:
    return {
        "source": payload.source,
        "query": payload.query,
        "location": payload.city,
        "filters": dict(payload.params),
        "limit": limit,
    }


async def preview_with_parser_service(
    payload: SearchPayload,
    *,
    parser_client: ParserClient | None = None,
) -> dict[str, Any]:
    client = parser_client or ParserClient()
    request = build_parser_preview_request(payload)
    response = await client.preview(**request)
    return normalize_parser_preview_response(response)


def normalize_parser_preview_response(response: dict[str, Any]) -> dict[str, Any]:
    items = response.get("items") or []
    urls = [
        str(item["url"])
        for item in items
        if isinstance(item, dict) and item.get("url")
    ]
    total_found = response.get("total_found")
    if not isinstance(total_found, int):
        total_found = len(urls)
    return {"total_found": total_found, "urls": urls}


def apply_preview_refinement_rule(
    preview_data: dict[str, Any],
    *,
    threshold: int = PREVIEW_REFINEMENT_THRESHOLD,
) -> dict[str, Any]:
    total_found = preview_data.get("total_found")
    requires_refinement = isinstance(total_found, int) and total_found > threshold

    enriched_preview = dict(preview_data)
    enriched_preview["requires_refinement"] = requires_refinement
    enriched_preview["message"] = (
        (
            f"Found {total_found} candidates. Please refine or narrow the "
            "search criteria before starting analysis."
        )
        if requires_refinement
        else None
    )
    return enriched_preview
