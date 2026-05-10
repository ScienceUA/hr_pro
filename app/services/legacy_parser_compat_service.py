from typing import Any

from app.config.settings import settings
from app.models.search import SearchPayload
from app.storage.repository import get_repository
from parser_service.execution.executor import RequestExecutor
from parser_service.freshness_validator import FreshnessValidator
from parser_service.sources.robotaua import RobotaUaAdapter
from parser_service.sources.workua import WorkUaAdapter


def get_legacy_adapter(source: str) -> Any:
    executor = RequestExecutor(settings=settings)
    repo = get_repository()

    if source == "workua":
        return WorkUaAdapter(executor, repo)
    if source == "robotaua":
        return RobotaUaAdapter(executor, repo)
    raise ValueError(f"Unknown source: {source}")


async def preview_with_legacy_adapter(payload: SearchPayload) -> dict[str, Any]:
    adapter = get_legacy_adapter(payload.source)
    return await adapter.preview(payload.to_adapter_payload())


async def parse_urls_with_legacy_adapter(
    payload: SearchPayload,
    urls: list[str],
) -> tuple[dict[str, Any], list[Any]]:
    adapter = get_legacy_adapter(payload.source)
    return await adapter.run_from_urls(urls)


async def check_freshness_with_legacy_validator(
    url: str,
    created_at: str | None = None,
) -> bool:
    return await FreshnessValidator.is_fresh(url, created_at)
