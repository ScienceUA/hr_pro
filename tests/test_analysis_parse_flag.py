from unittest.mock import AsyncMock, Mock

import pytest

import app.services.analysis_orchestrator as orchestrator
from app.models.search import SearchPayload
from parser_service.parsing.models import (
    DataQuality,
    PageType,
    ParsingResult,
    ResumeDetailData,
)


def _payload() -> SearchPayload:
    return SearchPayload(
        query="python",
        city="kyiv",
        source="workua",
        pages=1,
        criteria_bundle={},
    )


def _parser_service_response(parsed: bool = True) -> dict:
    if not parsed:
        return {
            "source": "workua",
            "external_id": None,
            "url": "https://www.work.ua/resumes/404/",
            "parsed": False,
            "data": {},
            "errors": [{"code": "parse_no_results", "message": "No results"}],
            "implemented": True,
        }

    result = ParsingResult(
        url="https://www.work.ua/resumes/123/",
        page_type=PageType.RESUME,
        payload=ResumeDetailData(
            resume_id="123",
            source="workua",
            url="https://www.work.ua/resumes/123/",
            title="Python Developer",
            skills=["Python"],
        ),
        quality=DataQuality.COMPLETE,
    )
    return {
        "source": "workua",
        "external_id": "123",
        "url": "https://www.work.ua/resumes/123/",
        "parsed": True,
        "data": result.model_dump(mode="json", by_alias=True),
        "errors": [],
        "implemented": True,
    }


def _patch_analysis_runtime(monkeypatch, adapter):
    vector_cache = Mock()
    vector_cache.get_cached_by_criteria.return_value = []
    repo = Mock()
    repo.exists.return_value = False

    monkeypatch.setattr(
        orchestrator,
        "get_vector_cache",
        Mock(return_value=vector_cache),
    )
    monkeypatch.setattr(orchestrator, "get_repository", Mock(return_value=repo))
    monkeypatch.setattr(orchestrator, "get_adapter", Mock(return_value=adapter))
    monkeypatch.setattr(orchestrator, "generate_report", Mock(return_value="# Report"))

    redis = Mock()
    redis.set_task_status = AsyncMock()
    monkeypatch.setattr(orchestrator, "redis_client", redis)

    return repo


@pytest.mark.asyncio
async def test_analysis_parse_flag_off_uses_direct_adapter(monkeypatch):
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 1,
        "urls": ["https://www.work.ua/resumes/123/"],
    }
    adapter.run_from_urls.return_value = (
        {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None},
        [],
    )
    _patch_analysis_runtime(monkeypatch, adapter)
    parser_service_parse = AsyncMock(return_value=_parser_service_response())
    monkeypatch.setattr(orchestrator.settings, "USE_PARSER_SERVICE_PARSE", False)
    monkeypatch.setattr(
        orchestrator,
        "parse_resume_with_parser_service",
        parser_service_parse,
    )

    await orchestrator.run_analysis_task("session-1", _payload())

    adapter.run_from_urls.assert_awaited_once_with(
        ["https://www.work.ua/resumes/123/"]
    )
    parser_service_parse.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_parse_flag_on_uses_parser_service_for_deduped_urls(
    monkeypatch,
):
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 2,
        "urls": [
            "https://www.work.ua/resumes/123/",
            "https://www.work.ua/resumes/456/",
        ],
    }
    repo = _patch_analysis_runtime(monkeypatch, adapter)
    repo.exists.side_effect = [False, True]
    parser_service_parse = AsyncMock(
        return_value=_parser_service_response(parsed=False)
    )
    monkeypatch.setattr(orchestrator.settings, "USE_PARSER_SERVICE_PARSE", True)
    monkeypatch.setattr(
        orchestrator,
        "parse_resume_with_parser_service",
        parser_service_parse,
    )

    await orchestrator.run_analysis_task("session-1", _payload())

    parser_service_parse.assert_awaited_once_with(
        source="workua",
        url="https://www.work.ua/resumes/123/",
    )
    adapter.run_from_urls.assert_not_awaited()


@pytest.mark.asyncio
async def test_parser_service_parse_data_becomes_parsing_result(monkeypatch):
    parser_service_parse = AsyncMock(return_value=_parser_service_response())
    monkeypatch.setattr(
        orchestrator,
        "parse_resume_with_parser_service",
        parser_service_parse,
    )

    stats, results = await orchestrator.parse_resumes_with_parser_service(
        _payload(),
        ["https://www.work.ua/resumes/123/"],
    )

    assert stats == {"saved": 1, "errors": 0, "skipped": 0, "critical_error": None}
    assert len(results) == 1
    assert isinstance(results[0], ParsingResult)
    assert results[0].url == "https://www.work.ua/resumes/123/"
    assert results[0].payload.resume_id == "123"
    assert results[0].model_dump()["payload"]["title"] == "Python Developer"


@pytest.mark.asyncio
async def test_parser_service_parse_false_counts_error_without_result(monkeypatch):
    parser_service_parse = AsyncMock(
        return_value=_parser_service_response(parsed=False)
    )
    monkeypatch.setattr(
        orchestrator,
        "parse_resume_with_parser_service",
        parser_service_parse,
    )

    stats, results = await orchestrator.parse_resumes_with_parser_service(
        _payload(),
        ["https://www.work.ua/resumes/404/"],
    )

    assert stats == {"saved": 0, "errors": 1, "skipped": 0, "critical_error": None}
    assert results == []
