from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ParserSource(StrEnum):
    WORKUA = "workua"
    ROBOTAUA = "robotaua"


class ParserError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ParserPreviewRequest(BaseModel):
    source: ParserSource
    query: str = Field(min_length=1)
    location: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)


class ParserPreviewItem(BaseModel):
    source: ParserSource
    external_id: str
    url: HttpUrl
    title: str
    candidate_name: str | None = None
    updated_at: str | None = None


class ParserPreviewResponse(BaseModel):
    items: list[ParserPreviewItem]
    total_found: int
    returned_count: int
    errors: list[ParserError]
    implemented: bool = False


class ParserParseRequest(BaseModel):
    source: ParserSource
    url: HttpUrl | None = None
    external_id: str | None = None

    @model_validator(mode="after")
    def require_url_or_external_id(self) -> "ParserParseRequest":
        if self.url is None and self.external_id is None:
            raise ValueError("Either url or external_id is required.")
        return self


class ParserParseResponse(BaseModel):
    source: ParserSource
    external_id: str | None
    url: HttpUrl | None
    parsed: bool
    data: dict[str, Any]
    errors: list[ParserError]
    implemented: bool = False

    model_config = ConfigDict(use_enum_values=True)


class ParserFreshnessRequest(BaseModel):
    source: ParserSource
    url: HttpUrl | None = None
    external_id: str | None = None

    @model_validator(mode="after")
    def require_url_or_external_id(self) -> "ParserFreshnessRequest":
        if self.url is None and self.external_id is None:
            raise ValueError("Either url or external_id is required.")
        return self


class ParserFreshnessResponse(BaseModel):
    source: ParserSource
    external_id: str | None
    is_fresh: bool
    updated_at: str | None
    checked_at: str | None
    errors: list[ParserError]
    implemented: bool = False

    model_config = ConfigDict(use_enum_values=True)
