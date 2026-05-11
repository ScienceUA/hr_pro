from unittest.mock import AsyncMock, Mock

import pytest

import app.services.analysis_orchestrator as orchestrator
from app.models.parsed_resume import CoreParsedResume
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
    vector_cache.save_analysis = Mock()
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


def _patch_analyzer(monkeypatch):
    analyzer = Mock()
    analyzer.analyze.return_value = {
        "candidate_url": "https://www.work.ua/resumes/123/",
        "candidate_role": "Python Developer",
        "status": "GREEN",
        "reasoning": "Matches criteria.",
    }
    analyzer_cls = Mock(return_value=analyzer)
    monkeypatch.setattr(orchestrator, "ResumeAnalyzer", analyzer_cls)
    return analyzer


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

    adapter.preview.assert_awaited_once_with(_payload().to_adapter_payload())
    parser_service_parse.assert_awaited_once_with(
        source="workua",
        url="https://www.work.ua/resumes/123/",
    )
    adapter.run_from_urls.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_parse_flag_on_keeps_url_discovery_on_legacy_preview(
    monkeypatch,
):
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 1,
        "urls": ["https://www.work.ua/resumes/123/"],
    }
    _patch_analysis_runtime(monkeypatch, adapter)
    parser_service_parse = AsyncMock(return_value=_parser_service_response(parsed=False))
    monkeypatch.setattr(orchestrator.settings, "USE_PARSER_SERVICE_PARSE", True)
    monkeypatch.setattr(
        orchestrator,
        "parse_resume_with_parser_service",
        parser_service_parse,
    )

    await orchestrator.run_analysis_task("session-1", _payload())

    adapter.preview.assert_awaited_once_with(_payload().to_adapter_payload())
    adapter.run_from_urls.assert_not_awaited()
    parser_service_parse.assert_awaited_once_with(
        source="workua",
        url="https://www.work.ua/resumes/123/",
    )


@pytest.mark.asyncio
async def test_analysis_parse_flag_on_saves_core_resume_and_analyzes_stable_core_dict(
    monkeypatch,
):
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 1,
        "urls": ["https://www.work.ua/resumes/123/"],
    }
    repo = _patch_analysis_runtime(monkeypatch, adapter)
    analyzer = _patch_analyzer(monkeypatch)
    parser_service_parse = AsyncMock(return_value=_parser_service_response(parsed=True))
    monkeypatch.setattr(orchestrator.settings, "USE_PARSER_SERVICE_PARSE", True)
    monkeypatch.setattr(
        orchestrator,
        "parse_resume_with_parser_service",
        parser_service_parse,
    )

    await orchestrator.run_analysis_task("session-1", _payload())

    adapter.preview.assert_awaited_once_with(_payload().to_adapter_payload())
    adapter.run_from_urls.assert_not_awaited()
    parser_service_parse.assert_awaited_once_with(
        source="workua",
        url="https://www.work.ua/resumes/123/",
    )

    repo.save_result.assert_called_once()
    saved_resume = repo.save_result.call_args.args[0]
    assert isinstance(saved_resume, CoreParsedResume)
    assert saved_resume == CoreParsedResume(
        url="https://www.work.ua/resumes/123/",
        resume_id="123",
        parsed=True,
        source="workua",
        payload={
            "resume_id": "123",
            "source": "workua",
            "url": "https://www.work.ua/resumes/123/",
            "title": "Python Developer",
            "salary": None,
            "location": None,
            "skills": ["Python"],
            "summary": None,
            "experience": [],
            "education": [],
            "languages": [],
        },
        error=None,
    )

    expected_resume_dict = saved_resume.model_dump()
    analyzer.analyze.assert_called_once_with(
        resume_json=expected_resume_dict,
        criteria_bundle=_payload().criteria_bundle,
    )
    orchestrator.get_vector_cache.return_value.save_analysis.assert_called_once_with(
        resume_text="Python Developer\nSkills: Python",
        role="python",
        analysis_result={
            "candidate_url": "https://www.work.ua/resumes/123/",
            "candidate_role": "Python Developer",
            "status": "GREEN",
            "reasoning": "Matches criteria.",
        },
        url="https://www.work.ua/resumes/123/",
    )


@pytest.mark.asyncio
async def test_parser_service_parse_data_becomes_core_parsed_resume(monkeypatch):
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
    assert isinstance(results[0], CoreParsedResume)
    assert results[0].url == "https://www.work.ua/resumes/123/"
    assert results[0].resume_id == "123"
    assert results[0].payload["title"] == "Python Developer"


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
