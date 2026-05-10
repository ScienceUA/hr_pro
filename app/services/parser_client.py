from typing import Any

import httpx

from app.config.settings import settings


class ParserClientError(RuntimeError):
    """Base error for Parser Service client failures."""


class ParserClientHTTPError(ParserClientError):
    def __init__(self, status_code: int, response_body: Any):
        super().__init__(f"Parser Service returned HTTP {status_code}")
        self.status_code = status_code
        self.response_body = response_body


class ParserClientTimeout(ParserClientError):
    pass


class ParserClientTransportError(ParserClientError):
    pass


class ParserClientResponseError(ParserClientError):
    pass


class ParserClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = (base_url or settings.PARSER_SERVICE_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.PARSER_SERVICE_TIMEOUT
        self._transport = transport

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def preview(
        self,
        *,
        source: str,
        query: str,
        location: str,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": source,
            "query": query,
            "location": location,
        }
        if filters is not None:
            payload["filters"] = filters
        if limit is not None:
            payload["limit"] = limit
        return await self._request("POST", "/preview", json=payload)

    async def parse(
        self,
        *,
        source: str,
        url: str | None = None,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._source_locator_payload(
            source=source,
            url=url,
            external_id=external_id,
        )
        return await self._request("POST", "/parse", json=payload)

    async def freshness(
        self,
        *,
        source: str,
        url: str | None = None,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._source_locator_payload(
            source=source,
            url=url,
            external_id=external_id,
        )
        return await self._request("POST", "/freshness", json=payload)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise ParserClientTimeout("Parser Service request timed out") from exc
        except httpx.RequestError as exc:
            raise ParserClientTransportError(
                "Parser Service request failed before a response was received"
            ) from exc

        response_body = self._decode_json(response)
        if response.status_code < 200 or response.status_code >= 300:
            raise ParserClientHTTPError(response.status_code, response_body)
        return response_body

    @staticmethod
    def _decode_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ParserClientResponseError(
                "Parser Service returned a non-JSON response"
            ) from exc
        if not isinstance(data, dict):
            raise ParserClientResponseError(
                "Parser Service returned a JSON response that is not an object"
            )
        return data

    @staticmethod
    def _source_locator_payload(
        *,
        source: str,
        url: str | None,
        external_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"source": source}
        if url is not None:
            payload["url"] = url
        if external_id is not None:
            payload["external_id"] = external_id
        return payload
