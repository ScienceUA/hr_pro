from typing import Any

from app.services.parser_client import ParserClient


async def parse_resume_with_parser_service(
    *,
    source: str,
    url: str,
    parser_client: ParserClient | None = None,
) -> dict[str, Any]:
    client = parser_client or ParserClient()
    response = await client.parse(source=source, url=url)
    return normalize_parser_parse_response(response, source=source, url=url)


async def check_freshness_with_parser_service(
    *,
    source: str,
    url: str,
    parser_client: ParserClient | None = None,
) -> dict[str, Any]:
    client = parser_client or ParserClient()
    response = await client.freshness(source=source, url=url)
    return normalize_parser_freshness_response(response, source=source)


def normalize_parser_parse_response(
    response: dict[str, Any],
    *,
    source: str,
    url: str,
) -> dict[str, Any]:
    data = response.get("data")
    errors = response.get("errors")
    return {
        "source": response.get("source") or source,
        "external_id": response.get("external_id"),
        "url": response.get("url") or url,
        "parsed": bool(response.get("parsed")),
        "data": data if isinstance(data, dict) else {},
        "errors": errors if isinstance(errors, list) else [],
        "implemented": bool(response.get("implemented")),
    }


def normalize_parser_freshness_response(
    response: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    errors = response.get("errors")
    return {
        "source": response.get("source") or source,
        "external_id": response.get("external_id"),
        "is_fresh": bool(response.get("is_fresh")),
        "updated_at": response.get("updated_at"),
        "checked_at": response.get("checked_at"),
        "errors": errors if isinstance(errors, list) else [],
        "implemented": bool(response.get("implemented")),
    }
