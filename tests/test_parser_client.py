import importlib
import sys

import httpx
import pytest

from app.services.parser_client import (
    ParserClient,
    ParserClientHTTPError,
    ParserClientResponseError,
    ParserClientTimeout,
    ParserClientTransportError,
)


def make_json_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_health_calls_parser_service_health_endpoint():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"status": "ok", "service": "parser", "version": "0.1.0"},
        )

    client = ParserClient(
        base_url="http://parser-service:8000/",
        transport=make_json_transport(handler),
    )

    response = await client.health()

    assert response == {"status": "ok", "service": "parser", "version": "0.1.0"}
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "http://parser-service:8000/health"


@pytest.mark.asyncio
async def test_preview_sends_contract_payload_and_parses_response():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "items": [],
                "total_found": 0,
                "returned_count": 0,
                "errors": [],
                "implemented": False,
            },
        )

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    response = await client.preview(
        source="workua",
        query="python",
        location="kyiv",
        filters={"experience": "2y"},
        limit=10,
    )

    assert response == {
        "items": [],
        "total_found": 0,
        "returned_count": 0,
        "errors": [],
        "implemented": False,
    }
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://parser-service:8000/preview"
    assert requests[0].read() == (
        b'{"source":"workua","query":"python","location":"kyiv",'
        b'"filters":{"experience":"2y"},"limit":10}'
    )


@pytest.mark.asyncio
async def test_parse_sends_source_locator_payload():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "source": "robotaua",
                "external_id": "123",
                "url": "https://example.com/resume/123",
                "parsed": False,
                "data": {},
                "errors": [],
                "implemented": False,
            },
        )

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    response = await client.parse(
        source="robotaua",
        url="https://example.com/resume/123",
        external_id="123",
    )

    assert response["source"] == "robotaua"
    assert response["parsed"] is False
    assert str(requests[0].url) == "http://parser-service:8000/parse"
    assert requests[0].read() == (
        b'{"source":"robotaua","url":"https://example.com/resume/123",'
        b'"external_id":"123"}'
    )


@pytest.mark.asyncio
async def test_freshness_sends_source_locator_payload():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "source": "workua",
                "external_id": "abc",
                "is_fresh": False,
                "updated_at": None,
                "checked_at": None,
                "errors": [],
                "implemented": False,
            },
        )

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    response = await client.freshness(source="workua", external_id="abc")

    assert response["is_fresh"] is False
    assert str(requests[0].url) == "http://parser-service:8000/freshness"
    assert requests[0].read() == b'{"source":"workua","external_id":"abc"}'


@pytest.mark.asyncio
async def test_non_2xx_response_raises_predictable_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": [{"type": "missing", "loc": ["body", "query"]}]},
        )

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    with pytest.raises(ParserClientHTTPError) as exc:
        await client.preview(source="workua", query="", location="kyiv")

    assert exc.value.status_code == 422
    assert exc.value.response_body == {
        "detail": [{"type": "missing", "loc": ["body", "query"]}]
    }


@pytest.mark.asyncio
async def test_timeout_raises_predictable_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    with pytest.raises(ParserClientTimeout):
        await client.health()


@pytest.mark.asyncio
async def test_transport_error_raises_predictable_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    with pytest.raises(ParserClientTransportError):
        await client.health()


@pytest.mark.asyncio
async def test_non_json_response_raises_predictable_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = ParserClient(
        base_url="http://parser-service:8000",
        transport=make_json_transport(handler),
    )

    with pytest.raises(ParserClientResponseError):
        await client.health()


def test_parser_client_import_does_not_import_parser_adapters():
    for module_name in [
        "app.services.parser_client",
        "parser_service.sources.workua",
        "parser_service.sources.robotaua",
    ]:
        sys.modules.pop(module_name, None)

    importlib.import_module("app.services.parser_client")

    assert "parser_service.sources.workua" not in sys.modules
    assert "parser_service.sources.robotaua" not in sys.modules
