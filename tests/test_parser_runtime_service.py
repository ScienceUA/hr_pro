import importlib
import sys
from unittest.mock import AsyncMock

import pytest

from app.services.parser_client import ParserClientTransportError
from app.services.parser_runtime_service import (
    check_freshness_with_parser_service,
    parse_resume_with_parser_service,
)


@pytest.mark.asyncio
async def test_parse_resume_with_parser_service_returns_parsed_data():
    parser_client = AsyncMock()
    parser_client.parse.return_value = {
        "source": "workua",
        "external_id": "123",
        "url": "https://www.work.ua/resumes/123/",
        "parsed": True,
        "data": {"payload": {"title": "Python Developer"}},
        "errors": [],
        "implemented": True,
    }

    response = await parse_resume_with_parser_service(
        source="workua",
        url="https://www.work.ua/resumes/123/",
        parser_client=parser_client,
    )

    assert response == {
        "source": "workua",
        "external_id": "123",
        "url": "https://www.work.ua/resumes/123/",
        "parsed": True,
        "data": {"payload": {"title": "Python Developer"}},
        "errors": [],
        "implemented": True,
    }
    parser_client.parse.assert_awaited_once_with(
        source="workua",
        url="https://www.work.ua/resumes/123/",
    )


@pytest.mark.asyncio
async def test_parse_resume_with_parser_service_keeps_not_parsed_errors():
    parser_client = AsyncMock()
    parser_client.parse.return_value = {
        "source": "robotaua",
        "external_id": None,
        "url": "https://robota.ua/candidates/404",
        "parsed": False,
        "data": {},
        "errors": [{"code": "parse_no_results", "message": "No results"}],
        "implemented": True,
    }

    response = await parse_resume_with_parser_service(
        source="robotaua",
        url="https://robota.ua/candidates/404",
        parser_client=parser_client,
    )

    assert response["source"] == "robotaua"
    assert response["url"] == "https://robota.ua/candidates/404"
    assert response["parsed"] is False
    assert response["data"] == {}
    assert response["errors"] == [
        {"code": "parse_no_results", "message": "No results"}
    ]
    assert response["implemented"] is True


@pytest.mark.asyncio
async def test_check_freshness_with_parser_service_returns_true():
    parser_client = AsyncMock()
    parser_client.freshness.return_value = {
        "source": "workua",
        "external_id": "123",
        "is_fresh": True,
        "updated_at": None,
        "checked_at": "2026-05-10T12:00:00+00:00",
        "errors": [],
        "implemented": True,
    }

    response = await check_freshness_with_parser_service(
        source="workua",
        url="https://www.work.ua/resumes/123/",
        parser_client=parser_client,
    )

    assert response == {
        "source": "workua",
        "external_id": "123",
        "is_fresh": True,
        "updated_at": None,
        "checked_at": "2026-05-10T12:00:00+00:00",
        "errors": [],
        "implemented": True,
    }
    parser_client.freshness.assert_awaited_once_with(
        source="workua",
        url="https://www.work.ua/resumes/123/",
    )


@pytest.mark.asyncio
async def test_check_freshness_with_parser_service_returns_false_with_errors():
    parser_client = AsyncMock()
    parser_client.freshness.return_value = {
        "source": "robotaua",
        "external_id": None,
        "is_fresh": False,
        "updated_at": None,
        "checked_at": "2026-05-10T12:00:00+00:00",
        "errors": [{"code": "freshness_check_failed", "message": "failed"}],
        "implemented": True,
    }

    response = await check_freshness_with_parser_service(
        source="robotaua",
        url="https://robota.ua/candidates/500",
        parser_client=parser_client,
    )

    assert response["is_fresh"] is False
    assert response["errors"] == [
        {"code": "freshness_check_failed", "message": "failed"}
    ]
    assert response["implemented"] is True


@pytest.mark.asyncio
async def test_parser_runtime_service_propagates_parser_client_errors():
    parser_client = AsyncMock()
    parser_client.parse.side_effect = ParserClientTransportError(
        "Parser Service unavailable"
    )

    with pytest.raises(ParserClientTransportError):
        await parse_resume_with_parser_service(
            source="workua",
            url="https://www.work.ua/resumes/123/",
            parser_client=parser_client,
        )


def test_parser_runtime_service_does_not_import_parser_internals():
    for module_name in [
        "app.services.parser_runtime_service",
        "parser_service.sources.workua",
        "parser_service.sources.robotaua",
    ]:
        sys.modules.pop(module_name, None)

    service = importlib.import_module("app.services.parser_runtime_service")

    assert service.ParserClient.__module__ == "app.services.parser_client"
    assert "parser_service.sources.workua" not in sys.modules
    assert "parser_service.sources.robotaua" not in sys.modules
