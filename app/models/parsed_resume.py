from typing import Any

from pydantic import BaseModel, Field


class CoreParsedResume(BaseModel):
    """Core-owned parser boundary contract."""

    url: str
    resume_id: str | None = None
    parsed: bool
    source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


def core_parsed_resume_from_legacy_result(result: Any) -> CoreParsedResume:
    payload = _to_dict(getattr(result, "payload", None))
    error = getattr(result, "error_message", None)
    quality = _enum_value(getattr(result, "quality", None))

    return CoreParsedResume(
        url=str(getattr(result, "url", "")),
        resume_id=_optional_str(_first_present(payload, "resume_id", "id")),
        parsed=quality != "error" and not error,
        source=_optional_str(payload.get("source")),
        payload=payload,
        error=_optional_str(error),
    )


def core_parsed_resume_from_parser_service_response(
    response: dict[str, Any],
) -> CoreParsedResume:
    data = response.get("data")
    payload = _parser_service_payload(data)
    error = _first_parser_error(response.get("errors"))

    return CoreParsedResume(
        url=str(response.get("url") or payload.get("url") or ""),
        resume_id=_optional_str(
            response.get("external_id") or _first_present(payload, "resume_id", "id")
        ),
        parsed=bool(response.get("parsed")),
        source=_optional_str(response.get("source") or payload.get("source")),
        payload=payload,
        error=error,
    )


def _parser_service_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    nested_payload = data.get("payload")
    if isinstance(nested_payload, dict):
        return nested_payload
    return data


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", by_alias=True)
        return dumped if isinstance(dumped, dict) else {"items": dumped}
    return {}


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_parser_error(errors: Any) -> str | None:
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if isinstance(first, dict):
        return _optional_str(first.get("message") or first.get("code"))
    return _optional_str(first)
