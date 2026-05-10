import importlib
import inspect
import json
import sys

from app.models.parsed_resume import (
    CoreParsedResume,
    core_parsed_resume_from_legacy_result,
    core_parsed_resume_from_parser_service_response,
)
from parser_service.parsing.models import (
    DataQuality,
    PageType,
    ParsingResult,
    ResumeDetailData,
)


def _legacy_parsing_result() -> ParsingResult:
    return ParsingResult(
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


def test_legacy_parsing_result_maps_to_core_parsed_resume():
    result = core_parsed_resume_from_legacy_result(_legacy_parsing_result())

    assert result == CoreParsedResume(
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


def test_parser_service_response_maps_to_core_parsed_resume():
    response = {
        "source": "workua",
        "external_id": "123",
        "url": "https://www.work.ua/resumes/123/",
        "parsed": True,
        "data": {
            "resume_id": "123",
            "source": "workua",
            "url": "https://www.work.ua/resumes/123/",
            "title": "Python Developer",
        },
        "errors": [],
        "implemented": True,
    }

    result = core_parsed_resume_from_parser_service_response(response)

    assert result.url == "https://www.work.ua/resumes/123/"
    assert result.resume_id == "123"
    assert result.parsed is True
    assert result.source == "workua"
    assert result.payload["title"] == "Python Developer"
    assert result.error is None


def test_local_storage_accepts_core_parsed_resume_without_parser_model_import(tmp_path):
    sys.modules.pop("app.storage.repository", None)
    repository = importlib.import_module("app.storage.repository")

    assert "parser_service.parsing.models" not in inspect.getsource(repository)
    assert repository.CoreParsedResume.__module__ == "app.models.parsed_resume"

    storage = repository.LocalStorage(tmp_path / "candidates.jsonl")
    storage.save_result(core_parsed_resume_from_legacy_result(_legacy_parsing_result()))

    lines = (tmp_path / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    saved = json.loads(lines[0])
    assert saved["resume_id"] == "123"
    assert saved["payload"]["title"] == "Python Developer"
    assert storage.exists("123") is True
