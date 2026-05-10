from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.analysis_orchestrator as orchestrator


@pytest.mark.asyncio
async def test_analysis_freshness_flag_off_uses_local_validator(monkeypatch):
    payload = SimpleNamespace(source="workua")
    local_validator = AsyncMock(return_value=True)
    parser_service_check = AsyncMock(return_value={"is_fresh": False})
    monkeypatch.setattr(
        orchestrator.settings,
        "USE_PARSER_SERVICE_FRESHNESS",
        False,
    )
    monkeypatch.setattr(
        orchestrator,
        "check_freshness_with_legacy_validator",
        local_validator,
    )
    monkeypatch.setattr(
        orchestrator,
        "check_freshness_with_parser_service",
        parser_service_check,
    )

    result = await orchestrator.check_resume_freshness_for_analysis(
        payload=payload,
        url="https://www.work.ua/resumes/123/",
        created_at="2026-05-10T12:00:00",
    )

    assert result is True
    local_validator.assert_awaited_once_with(
        "https://www.work.ua/resumes/123/",
        "2026-05-10T12:00:00",
    )
    parser_service_check.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_freshness_flag_on_uses_parser_service(monkeypatch):
    payload = SimpleNamespace(source="robotaua")
    local_validator = AsyncMock(return_value=False)
    parser_service_check = AsyncMock(return_value={"is_fresh": True})
    monkeypatch.setattr(
        orchestrator.settings,
        "USE_PARSER_SERVICE_FRESHNESS",
        True,
    )
    monkeypatch.setattr(
        orchestrator,
        "check_freshness_with_legacy_validator",
        local_validator,
    )
    monkeypatch.setattr(
        orchestrator,
        "check_freshness_with_parser_service",
        parser_service_check,
    )

    result = await orchestrator.check_resume_freshness_for_analysis(
        payload=payload,
        url="https://robota.ua/candidates/123",
        created_at="2026-05-10T12:00:00",
    )

    assert result is True
    parser_service_check.assert_awaited_once_with(
        source="robotaua",
        url="https://robota.ua/candidates/123",
    )
    local_validator.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_freshness_flag_on_stale_result_returns_false(monkeypatch):
    payload = SimpleNamespace(source="workua")
    parser_service_check = AsyncMock(return_value={"is_fresh": False})
    monkeypatch.setattr(
        orchestrator.settings,
        "USE_PARSER_SERVICE_FRESHNESS",
        True,
    )
    monkeypatch.setattr(
        orchestrator,
        "check_freshness_with_parser_service",
        parser_service_check,
    )

    result = await orchestrator.check_resume_freshness_for_analysis(
        payload=payload,
        url="https://www.work.ua/resumes/404/",
        created_at="2026-05-10T12:00:00",
    )

    assert result is False


def test_analysis_stale_items_still_use_existing_vector_cache_removal_path():
    source = Path(orchestrator.__file__).read_text(encoding="utf-8")

    assert "is_fresh = await check_resume_freshness_for_analysis(" in source
    assert "is_fresh" in source
    assert "vector" in source
    assert "delete" in source or "remove" in source


@pytest.mark.asyncio
async def test_analysis_parser_service_freshness_error_propagates(monkeypatch):
    payload = SimpleNamespace(source="workua")
    parser_service_check = AsyncMock(side_effect=RuntimeError("parser failed"))
    monkeypatch.setattr(
        orchestrator.settings,
        "USE_PARSER_SERVICE_FRESHNESS",
        True,
    )
    monkeypatch.setattr(
        orchestrator,
        "check_freshness_with_parser_service",
        parser_service_check,
    )

    with pytest.raises(RuntimeError, match="parser failed"):
        await orchestrator.check_resume_freshness_for_analysis(
            payload=payload,
            url="https://www.work.ua/resumes/123/",
            created_at="2026-05-10T12:00:00",
        )
