from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.search import SearchPayload
from app.services import legacy_parser_compat_service as compat

ROOT = Path(__file__).resolve().parents[1]


def test_analysis_orchestrator_has_no_direct_parser_service_imports():
    source = (ROOT / "app/services/analysis_orchestrator.py").read_text(
        encoding="utf-8"
    )

    assert "from parser_service" not in source
    assert "import parser_service" not in source


def test_legacy_compat_service_owns_legacy_parser_service_imports():
    source = (ROOT / "app/services/legacy_parser_compat_service.py").read_text(
        encoding="utf-8"
    )

    assert "from parser_service.execution.executor import RequestExecutor" in source
    assert "from parser_service.freshness_validator import FreshnessValidator" in source
    assert "from parser_service.sources.robotaua import RobotaUaAdapter" in source
    assert "from parser_service.sources.workua import WorkUaAdapter" in source


def test_only_legacy_compat_service_imports_legacy_adapter_classes():
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if (
            "from parser_service.sources.workua import WorkUaAdapter" in source
            or "from parser_service.sources.robotaua import RobotaUaAdapter" in source
            or "from parser_service.execution.executor import RequestExecutor" in source
            or "from parser_service.freshness_validator import FreshnessValidator" in source
        ):
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == ["app/services/legacy_parser_compat_service.py"]


@pytest.mark.asyncio
async def test_preview_with_legacy_adapter_delegates_to_adapter(monkeypatch):
    adapter = Mock()
    adapter.preview = AsyncMock(return_value={"total_found": 1, "urls": ["u"]})
    monkeypatch.setattr(compat, "get_legacy_adapter", Mock(return_value=adapter))
    payload = SearchPayload(query="python", city="kyiv", source="workua", pages=1)

    result = await compat.preview_with_legacy_adapter(payload)

    assert result == {"total_found": 1, "urls": ["u"]}
    compat.get_legacy_adapter.assert_called_once_with("workua")
    adapter.preview.assert_awaited_once_with(payload.to_adapter_payload())


@pytest.mark.asyncio
async def test_parse_urls_with_legacy_adapter_delegates_to_adapter(monkeypatch):
    adapter = Mock()
    adapter.run_from_urls = AsyncMock(return_value=({"saved": 1}, ["result"]))
    monkeypatch.setattr(compat, "get_legacy_adapter", Mock(return_value=adapter))
    payload = SearchPayload(query="python", city="kyiv", source="workua", pages=1)

    result = await compat.parse_urls_with_legacy_adapter(payload, ["u"])

    assert result == ({"saved": 1}, ["result"])
    compat.get_legacy_adapter.assert_called_once_with("workua")
    adapter.run_from_urls.assert_awaited_once_with(["u"])


@pytest.mark.asyncio
async def test_check_freshness_with_legacy_validator_delegates(monkeypatch):
    is_fresh = AsyncMock(return_value=True)
    monkeypatch.setattr(compat.FreshnessValidator, "is_fresh", is_fresh)

    result = await compat.check_freshness_with_legacy_validator("u", "created")

    assert result is True
    is_fresh.assert_awaited_once_with("u", "created")
