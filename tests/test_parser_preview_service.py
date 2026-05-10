from unittest.mock import AsyncMock

import pytest

from app.models.search import LanguageRequirement, SearchMandatory, SearchPayload
from app.services.parser_preview_service import (
    MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT,
    apply_preview_refinement_rule,
    build_parser_preview_request,
    preview_with_parser_service,
)


def test_build_parser_preview_request_maps_flat_search_payload():
    payload = SearchPayload(
        source="workua",
        query="python",
        city="kyiv",
        pages=2,
        params={"experience_years": 3, "employment": "full"},
    )

    assert build_parser_preview_request(payload) == {
        "source": "workua",
        "query": "python",
        "location": "kyiv",
        "filters": {"experience_years": 3, "employment": "full"},
        "limit": MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT,
    }


def test_build_parser_preview_request_reuses_normalized_trio_payload():
    payload = SearchPayload(
        source="robotaua",
        pages=1,
        search_mandatory=SearchMandatory(
            role="backend engineer",
            city="remote",
            experience_years=5,
            employment="remote",
            languages=[LanguageRequirement(language="English", level="B2")],
        ),
    )

    assert build_parser_preview_request(payload) == {
        "source": "robotaua",
        "query": "backend engineer",
        "location": "remote",
        "filters": {
            "experience_years": 5,
            "employment": "remote",
            "languages": ["B2"],
        },
        "limit": MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT,
    }


def test_build_parser_preview_request_does_not_expand_pages_into_fetch_limit():
    payload = SearchPayload(
        source="workua",
        query="python",
        city="kyiv",
        pages=10,
    )

    request = build_parser_preview_request(payload)

    assert request["limit"] == MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT
    assert request["limit"] <= 50


def test_apply_preview_refinement_rule_marks_small_result_set_as_ready():
    response = apply_preview_refinement_rule(
        {
            "total_found": 50,
            "urls": ["https://www.work.ua/resumes/1/"],
        }
    )

    assert response == {
        "total_found": 50,
        "urls": ["https://www.work.ua/resumes/1/"],
        "requires_refinement": False,
        "message": None,
    }


def test_apply_preview_refinement_rule_requires_refinement_above_threshold():
    response = apply_preview_refinement_rule(
        {
            "total_found": 51,
            "urls": ["https://www.work.ua/resumes/1/"],
        }
    )

    assert response["total_found"] == 51
    assert response["urls"] == ["https://www.work.ua/resumes/1/"]
    assert response["requires_refinement"] is True
    assert "51" in response["message"]
    assert "refine" in response["message"].lower()


@pytest.mark.asyncio
async def test_preview_with_parser_service_invokes_parser_client_preview():
    payload = SearchPayload(
        source="workua",
        query="python",
        city="kyiv",
        pages=3,
        params={"days": 7},
    )
    parser_client = AsyncMock()
    parser_client.preview.return_value = {
        "items": [
            {
                "source": "workua",
                "external_id": "1",
                "url": "https://www.work.ua/resumes/1/",
                "title": "Python Developer",
            }
        ],
        "total_found": 12,
        "returned_count": 1,
        "errors": [],
        "implemented": True,
    }

    response = await preview_with_parser_service(
        payload,
        parser_client=parser_client,
    )

    assert response == {
        "total_found": 12,
        "urls": ["https://www.work.ua/resumes/1/"],
    }
    parser_client.preview.assert_awaited_once_with(
        source="workua",
        query="python",
        location="kyiv",
        filters={"days": 7},
        limit=MAX_PREVIEW_RESULTS_BEFORE_REFINEMENT,
    )


@pytest.mark.asyncio
async def test_preview_with_parser_service_does_not_use_returned_count_as_total():
    payload = SearchPayload(source="workua", query="python", city="kyiv")
    parser_client = AsyncMock()
    parser_client.preview.return_value = {
        "items": [
            {
                "source": "workua",
                "external_id": "1",
                "url": "https://www.work.ua/resumes/1/",
                "title": "Python Developer",
            }
        ],
        "total_found": 73,
        "returned_count": 1,
        "errors": [],
        "implemented": True,
    }

    response = await preview_with_parser_service(
        payload,
        parser_client=parser_client,
    )

    assert response == {
        "total_found": 73,
        "urls": ["https://www.work.ua/resumes/1/"],
    }


def test_parser_preview_service_does_not_import_parser_internals():
    import app.services.parser_preview_service as service

    assert service.ParserClient.__module__ == "app.services.parser_client"
