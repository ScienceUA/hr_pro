from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# Повертаємо стандартизовану структуру для мов
class LanguageRequirement(BaseModel):
    language: str = Field(..., description="Стандартизована назва мови")
    level: Optional[str] = Field(None, description="Рівень (якщо вказано)")


class SearchMandatory(BaseModel):
    """Нормалізовані критерії для мапінгу в скриптах"""

    role: str = Field(
        ..., description="Посада або ключові слова (КРИТИЧНО ОБОВ'ЯЗКОВО)"
    )
    city: Optional[str] = Field(None, description="Назва міста ('Київ', 'remote')")
    experience_years: Optional[int] = Field(
        None, description="Мінімальний досвід у роках (число)"
    )
    employment: Optional[str] = Field(
        None, description="Тип зайнятості ('full', 'part', 'remote')"
    )
    education_level: Optional[str] = Field(
        None, description="Рівень освіти ('higher', 'student', 'none')"
    )
    languages: Optional[List[LanguageRequirement]] = Field(
        default_factory=list, description="Обов'язкові мови"
    )
    period_days: Optional[int] = Field(None, description="За скільки днів шукати")


class SearchQuery(BaseModel):
    """Канонічна схема запиту"""

    search_mandatory: SearchMandatory = Field(
        description="Параметри, які скрипти конвертують у фільтри сайтів",
    )
    internal_mandatory: List[str] = Field(
        default_factory=list,
        description="Усі жорсткі вимоги текстом для фінального AI-аналізу",
    )
    desirable: List[str] = Field(
        default_factory=list,
        description="Бажані вимоги (виділені ДО формування пошукових критеріїв)",
    )

    page: int = Field(1, ge=1)
    allowed_sources: List[str] = Field(
        default_factory=lambda: ["workua", "robotaua", "linkedin"]
    )


class SearchResponse(BaseModel):
    total_found: int
    resume_urls: List[str]


class SearchPayload(BaseModel):
    """
    Public DTO for /preview and persisted HITL payloads.

    The DTO accepts the current flat API contract while also carrying the
    canonical Trio-model fields. Adapter-specific dicts must be produced only
    through to_adapter_payload().
    """

    query: str = ""
    city: str = ""
    source: str = "workua"
    pages: int = Field(1, ge=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    criteria_bundle: Dict[str, Any] = Field(default_factory=dict)

    search_mandatory: Optional[SearchMandatory] = None
    internal_mandatory: List[str] = Field(default_factory=list)
    desirable: List[str] = Field(default_factory=list)
    allowed_sources: List[str] = Field(
        default_factory=lambda: ["workua", "robotaua", "linkedin"]
    )

    @model_validator(mode="after")
    def normalize_trio_model(self) -> "SearchPayload":
        if self.search_mandatory:
            mandatory = self.search_mandatory
            if not self.query:
                self.query = mandatory.role
            if not self.city and mandatory.city:
                self.city = mandatory.city
            self.params = {
                **self.params,
                **self._search_mandatory_to_params(mandatory),
            }

        if not self.criteria_bundle:
            self.criteria_bundle = {
                "internal_mandatory": list(self.internal_mandatory),
                "desirable": list(self.desirable),
            }

        return self

    def to_adapter_payload(self) -> Dict[str, Any]:
        payload = {
            "query": self.query,
            "city": self.city,
            "source": self.source,
            "pages": self.pages,
            "params": dict(self.params),
            "criteria_bundle": dict(self.criteria_bundle),
        }

        if self.search_mandatory:
            payload.update(self._search_mandatory_to_adapter_fields())

        return payload

    @staticmethod
    def _search_mandatory_to_params(mandatory: SearchMandatory) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if mandatory.employment:
            params["employment"] = mandatory.employment
        if mandatory.education_level:
            params["education"] = mandatory.education_level
        if mandatory.period_days:
            params["days"] = mandatory.period_days
        if mandatory.languages:
            params["languages"] = [
                item.level or item.language for item in mandatory.languages
            ]
        if mandatory.experience_years is not None:
            params["experience_years"] = mandatory.experience_years
        return params

    def _search_mandatory_to_adapter_fields(self) -> Dict[str, Any]:
        mandatory = self.search_mandatory
        if not mandatory:
            return {}

        fields: Dict[str, Any] = {}
        if mandatory.period_days:
            fields["days"] = mandatory.period_days
        if mandatory.employment:
            fields["employment"] = mandatory.employment
        if mandatory.education_level:
            fields["education"] = mandatory.education_level
        if mandatory.languages:
            fields["languages"] = [
                item.level or item.language for item in mandatory.languages
            ]
        if mandatory.experience_years is not None:
            fields["experience_years"] = mandatory.experience_years
        return fields
