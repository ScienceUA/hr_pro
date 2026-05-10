import importlib
import sys
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from parser_service.main import app
from parser_service.parsing.models import (
    DataQuality,
    PageType,
    ParsingResult,
    ResumeDetailData,
)


@pytest.mark.asyncio
async def test_preview_contract_returns_workua_adapter_data():
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 73,
        "urls": [
            "https://www.work.ua/resumes/123/",
            "https://www.work.ua/resumes/456/",
        ],
    }

    with patch(
        "parser_service.services.preview_service.build_workua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/preview",
                json={
                    "source": "workua",
                    "query": "python",
                    "location": "kyiv",
                    "filters": {"experience": "2y"},
                    "limit": 10,
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "source": "workua",
                "external_id": "123",
                "url": "https://www.work.ua/resumes/123/",
                "title": "",
                "candidate_name": None,
                "updated_at": None,
            },
            {
                "source": "workua",
                "external_id": "456",
                "url": "https://www.work.ua/resumes/456/",
                "title": "",
                "candidate_name": None,
                "updated_at": None,
            },
        ],
        "total_found": 73,
        "returned_count": 2,
        "errors": [],
        "implemented": True,
    }
    adapter.preview.assert_awaited_once_with(
        {
            "query": "python",
            "city": "kyiv",
            "source": "workua",
            "pages": 1,
            "params": {"experience": "2y"},
            "experience": "2y",
        }
    )


@pytest.mark.asyncio
async def test_preview_contract_limits_returned_items_without_changing_total():
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 73,
        "urls": [
            "https://www.work.ua/resumes/123/",
            "https://www.work.ua/resumes/456/",
        ],
    }

    with patch(
        "parser_service.services.preview_service.build_workua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/preview",
                json={
                    "source": "workua",
                    "query": "python",
                    "location": "kyiv",
                    "limit": 1,
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] == 73
    assert data["returned_count"] == 1
    assert [item["external_id"] for item in data["items"]] == ["123"]


@pytest.mark.asyncio
async def test_preview_contract_returns_robotaua_adapter_data():
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 31,
        "urls": [
            "https://robota.ua/candidates/123",
            "https://robota.ua/profile/custom-slug?source=cvdb",
        ],
    }

    with patch(
        "parser_service.services.preview_service.build_robotaua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/preview",
                json={
                    "source": "robotaua",
                    "query": "python",
                    "location": "kyiv",
                    "filters": {"experience_label": "2-5_years"},
                    "limit": 10,
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "source": "robotaua",
                "external_id": "123",
                "url": "https://robota.ua/candidates/123",
                "title": "",
                "candidate_name": None,
                "updated_at": None,
            },
            {
                "source": "robotaua",
                "external_id": "custom-slug",
                "url": "https://robota.ua/profile/custom-slug?source=cvdb",
                "title": "",
                "candidate_name": None,
                "updated_at": None,
            },
        ],
        "total_found": 31,
        "returned_count": 2,
        "errors": [],
        "implemented": True,
    }
    adapter.preview.assert_awaited_once_with(
        {
            "query": "python",
            "city": "kyiv",
            "source": "robotaua",
            "pages": 1,
            "params": {"experience_label": "2-5_years"},
            "experience_label": "2-5_years",
        }
    )


@pytest.mark.asyncio
async def test_preview_contract_limits_robotaua_items_without_changing_total():
    adapter = AsyncMock()
    adapter.preview.return_value = {
        "total_found": 31,
        "urls": [
            "https://robota.ua/candidates/123",
            "https://robota.ua/candidates/456",
        ],
    }

    with patch(
        "parser_service.services.preview_service.build_robotaua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/preview",
                json={
                    "source": "robotaua",
                    "query": "python",
                    "location": "kyiv",
                    "limit": 1,
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] == 31
    assert data["returned_count"] == 1
    assert data["implemented"] is True
    assert [item["url"] for item in data["items"]] == [
        "https://robota.ua/candidates/123"
    ]


@pytest.mark.asyncio
async def test_parse_contract_returns_workua_parsed_result():
    adapter = AsyncMock()
    adapter.run_from_urls.return_value = (
        {"saved": 1, "errors": 0, "skipped": 0, "critical_error": None},
        [
            ParsingResult(
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
        ],
    )

    with patch(
        "parser_service.services.parse_service.build_workua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/parse",
                json={
                    "source": "workua",
                    "url": "https://www.work.ua/resumes/123/",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "workua"
    assert data["external_id"] == "123"
    assert data["url"] == "https://www.work.ua/resumes/123/"
    assert data["parsed"] is True
    assert data["implemented"] is True
    assert data["errors"] == []
    assert data["data"]["url"] == "https://www.work.ua/resumes/123/"
    assert data["data"]["page_type"] == "resume"
    assert data["data"]["quality"] == "complete"
    assert data["data"]["payload"]["resume_id"] == "123"
    assert data["data"]["payload"]["title"] == "Python Developer"
    adapter.run_from_urls.assert_awaited_once_with(
        ["https://www.work.ua/resumes/123/"]
    )


@pytest.mark.asyncio
async def test_parse_contract_returns_stable_error_for_workua_no_results():
    adapter = AsyncMock()
    adapter.run_from_urls.return_value = (
        {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None},
        [],
    )

    with patch(
        "parser_service.services.parse_service.build_workua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/parse",
                json={
                    "source": "workua",
                    "url": "https://www.work.ua/resumes/404/",
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "source": "workua",
        "external_id": None,
        "url": "https://www.work.ua/resumes/404/",
        "parsed": False,
        "data": {},
        "errors": [
            {
                "code": "parse_no_results",
                "message": "Parser adapter returned no parsed results.",
                "details": None,
            }
        ],
        "implemented": True,
    }


@pytest.mark.asyncio
async def test_parse_contract_returns_stable_error_for_workua_exception():
    adapter = AsyncMock()
    adapter.run_from_urls.side_effect = RuntimeError("network failed")

    with patch(
        "parser_service.services.parse_service.build_workua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/parse",
                json={
                    "source": "workua",
                    "url": "https://www.work.ua/resumes/500/",
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "source": "workua",
        "external_id": None,
        "url": "https://www.work.ua/resumes/500/",
        "parsed": False,
        "data": {},
        "errors": [
            {
                "code": "parse_failed",
                "message": "network failed",
                "details": {"source": "workua"},
            }
        ],
        "implemented": True,
    }


@pytest.mark.asyncio
async def test_parse_contract_returns_robotaua_parsed_result():
    adapter = AsyncMock()
    adapter.run_from_urls.return_value = (
        {"saved": 1, "errors": 0, "skipped": 0, "critical_error": None},
        [
            ParsingResult(
                url="https://robota.ua/candidates/123",
                page_type=PageType.RESUME,
                payload=ResumeDetailData(
                    resume_id="123",
                    source="robotaua",
                    url="https://robota.ua/candidates/123",
                    title="Python Developer",
                    skills=["Python"],
                ),
                quality=DataQuality.COMPLETE,
            )
        ],
    )

    with patch(
        "parser_service.services.parse_service.build_robotaua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/parse",
                json={
                    "source": "robotaua",
                    "url": "https://robota.ua/candidates/123",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "robotaua"
    assert data["external_id"] == "123"
    assert data["url"] == "https://robota.ua/candidates/123"
    assert data["parsed"] is True
    assert data["implemented"] is True
    assert data["errors"] == []
    assert data["data"]["url"] == "https://robota.ua/candidates/123"
    assert data["data"]["page_type"] == "resume"
    assert data["data"]["quality"] == "complete"
    assert data["data"]["payload"]["resume_id"] == "123"
    assert data["data"]["payload"]["source"] == "robotaua"
    adapter.run_from_urls.assert_awaited_once_with(
        ["https://robota.ua/candidates/123"]
    )


@pytest.mark.asyncio
async def test_parse_contract_returns_stable_error_for_robotaua_no_results():
    adapter = AsyncMock()
    adapter.run_from_urls.return_value = (
        {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None},
        [],
    )

    with patch(
        "parser_service.services.parse_service.build_robotaua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/parse",
                json={
                    "source": "robotaua",
                    "url": "https://robota.ua/candidates/404",
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "source": "robotaua",
        "external_id": None,
        "url": "https://robota.ua/candidates/404",
        "parsed": False,
        "data": {},
        "errors": [
            {
                "code": "parse_no_results",
                "message": "Parser adapter returned no parsed results.",
                "details": None,
            }
        ],
        "implemented": True,
    }


@pytest.mark.asyncio
async def test_parse_contract_returns_stable_error_for_robotaua_exception():
    adapter = AsyncMock()
    adapter.run_from_urls.side_effect = RuntimeError("graphql failed")

    with patch(
        "parser_service.services.parse_service.build_robotaua_adapter",
        return_value=adapter,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/parse",
                json={
                    "source": "robotaua",
                    "url": "https://robota.ua/candidates/500",
                },
            )
    
    assert response.status_code == 200
    assert response.json() == {
        "source": "robotaua",
        "external_id": None,
        "url": "https://robota.ua/candidates/500",
        "parsed": False,
        "data": {},
        "errors": [
            {
                "code": "parse_failed",
                "message": "graphql failed",
                "details": {"source": "robotaua"},
            }
        ],
        "implemented": True,
    }


@pytest.mark.asyncio
async def test_parse_contract_requires_url_for_robotaua_parse():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/parse",
            json={
                "source": "robotaua",
                "external_id": "123",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "source": "robotaua",
        "external_id": "123",
        "url": None,
        "parsed": False,
        "data": {},
        "errors": [
            {
                "code": "parse_url_required",
                "message": "Robota.ua parse requires a URL.",
                "details": {"source": "robotaua"},
            }
        ],
        "implemented": True,
    }


@pytest.mark.asyncio
async def test_freshness_contract_returns_fresh_url_response():
    with patch(
        "parser_service.services.freshness_service.FreshnessValidator.is_fresh",
        new_callable=AsyncMock,
        return_value=True,
    ) as validator:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/freshness",
                json={
                    "source": "workua",
                    "url": "https://www.work.ua/resumes/123/",
                    "external_id": "123",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "source": "workua",
        "external_id": "123",
        "is_fresh": True,
        "updated_at": None,
        "checked_at": data["checked_at"],
        "errors": [],
        "implemented": True,
    }
    assert data["checked_at"]
    validator.assert_awaited_once_with("https://www.work.ua/resumes/123/")


@pytest.mark.asyncio
async def test_freshness_contract_returns_stale_url_response():
    with patch(
        "parser_service.services.freshness_service.FreshnessValidator.is_fresh",
        new_callable=AsyncMock,
        return_value=False,
    ) as validator:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/freshness",
                json={
                    "source": "robotaua",
                    "url": "https://robota.ua/candidates/123",
                    "external_id": "123",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "robotaua"
    assert data["external_id"] == "123"
    assert data["is_fresh"] is False
    assert data["updated_at"] is None
    assert data["checked_at"]
    assert data["errors"] == []
    assert data["implemented"] is True
    validator.assert_awaited_once_with("https://robota.ua/candidates/123")


@pytest.mark.asyncio
async def test_freshness_contract_returns_stable_error_for_validator_exception():
    with patch(
        "parser_service.services.freshness_service.FreshnessValidator.is_fresh",
        new_callable=AsyncMock,
        side_effect=RuntimeError("validator failed"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/freshness",
                json={
                    "source": "workua",
                    "url": "https://www.work.ua/resumes/500/",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "source": "workua",
        "external_id": None,
        "is_fresh": False,
        "updated_at": None,
        "checked_at": data["checked_at"],
        "errors": [
            {
                "code": "freshness_check_failed",
                "message": "validator failed",
                "details": {"source": "workua"},
            }
        ],
        "implemented": True,
    }
    assert data["checked_at"]


@pytest.mark.asyncio
async def test_freshness_contract_requires_url_for_implemented_check():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/freshness",
            json={
                "source": "workua",
                "external_id": "abc",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "source": "workua",
        "external_id": "abc",
        "is_fresh": False,
        "updated_at": None,
        "checked_at": data["checked_at"],
        "errors": [
            {
                "code": "freshness_url_required",
                "message": "Freshness check requires a URL.",
                "details": None,
            }
        ],
        "implemented": True,
    }
    assert data["checked_at"]


@pytest.mark.asyncio
async def test_preview_validation_rejects_invalid_source():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/preview",
            json={
                "source": "unknown",
                "query": "python",
                "location": "kyiv",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "enum"


@pytest.mark.asyncio
async def test_parse_validation_requires_url_or_external_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/parse", json={"source": "workua"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "value_error"


def test_contract_imports_do_not_load_core_app_modules():
    sys.modules.pop("parser_service.api.dto", None)
    sys.modules.pop("main", None)

    importlib.import_module("parser_service.api.dto")

    assert "main" not in sys.modules
