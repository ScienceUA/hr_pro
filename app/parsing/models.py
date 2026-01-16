import re
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from urllib.parse import urlsplit, urlunsplit

# --- 1. Enums (Классификация) ---

class PageType(str, Enum):
    """
    Контекст страницы. Определяется классификатором (Signature Check).
    """
    RESUME = "resume"           # Целевая страница
    SERP = "serp"               # Список
    LOGIN = "login"             # Форма входа
    CAPTCHA = "captcha"         # Капча
    BAN = "ban"                 # WAF / 403
    NOT_FOUND = "not_found"     # 404
    UNKNOWN = "unknown"         # Не распознано

class DataQuality(str, Enum):
    """
    Качество извлеченных данных (Применимо ТОЛЬКО если PageType.RESUME/SERP).
    """
    COMPLETE = "complete"       # Все поля на месте
    PARTIAL = "partial"         # Обязательные есть, опциональных нет
    ERROR = "error"             # Критическая ошибка парсинга (смена верстки)

# --- 2. Component DTOs (Данные) ---

class SalaryDTO(BaseModel):
    amount: Optional[int] = None
    currency: Optional[str] = None
    comment: Optional[str] = None

class ExperienceEntryDTO(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    period: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None

class EducationEntryDTO(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    year: Optional[str] = None
    specialty: Optional[str] = None

# --- 3. Payload DTOs (Чистые данные) ---

class BaseResumeData(BaseModel):
    """Базовые поля данных (без метаданных страницы)."""
    resume_id: str
    url: str  # str вместо HttpUrl для сохранения каноничности

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("url")
    @classmethod
    def validate_canonical_url(cls, v: str) -> str:
        # Канонизация: отбрасываем query (?puid=...) и fragment (#...)
        # В DTO храним только стабильный canonical URL, чтобы не терять карточки SERP.
        v = v.strip()
        parts = urlsplit(v)
        canonical = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

        # Паттерн Work.ua: https://www.work.ua/resumes/<id>[/]
        # Не используем HttpUrl, чтобы избежать скрытой нормализации.
        pattern = r"^https://www\.work\.ua/resumes/[a-zA-Z0-9]+/?$"
        if not re.match(pattern, canonical):
            raise ValueError(f"URL does not match canonical pattern: {v}")
        return canonical

    @field_validator("resume_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v:
            raise ValueError("resume_id cannot be empty")
        # Разрешаем цифры и буквы (на случай изменения формата ID)
        if not v.isalnum():
            raise ValueError(f"resume_id contains invalid characters: {v}")
        return v

class ResumeDetailData(BaseResumeData):
    """
    Полезная нагрузка для детальной страницы.
    """
    # Loose fields
    name: Optional[str] = None
    title: Optional[str] = None
    age: Optional[str] = None
    city: Optional[str] = None
    salary: Optional[SalaryDTO] = None
    
    # Lists (Default empty list, NEVER None)
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntryDTO] = Field(default_factory=list)
    education: List[EducationEntryDTO] = Field(default_factory=list)
    
    about_raw: Optional[str] = None
    
    # Flags (Состояние контента)
    has_hidden_contacts: bool = False

class ResumePreviewData(BaseResumeData):
    """
    Полезная нагрузка для элемента списка (SERP).
    """
    title: Optional[str] = None
    age: Optional[str] = None
    city: Optional[str] = None
    updated_at: Optional[str] = None

# --- 4. Result Container (Единый контракт парсера) ---

# ... (Предыдущие классы BaseResumeData, ResumeDetailData, ResumePreviewData остаются без изменений)

class ParsingResult(BaseModel):
    """
    Единый контракт результата работы парсера.
    """
    url: str
    page_type: PageType
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Payload теперь полиморфный: либо Деталка, либо Список превью
    payload: Optional[Union[ResumeDetailData, List[ResumePreviewData]]] = None
    
    # Метаданные списка (только для SERP)
    next_page_url: Optional[str] = None
    
    quality: Optional[DataQuality] = None
    error_message: Optional[str] = None

    @model_validator(mode='after')
    def validate_integrity(self) -> 'ParsingResult':
        # 1. Запрет на Payload при ошибках доступа
        non_data_types = [PageType.BAN, PageType.CAPTCHA, PageType.LOGIN, PageType.NOT_FOUND]
        if self.page_type in non_data_types and self.payload is not None:
             raise ValueError(f"Payload must be None for page type {self.page_type}")

        # 2. Валидация типов Payload в зависимости от PageType
        if self.quality != DataQuality.ERROR:
            # Для RESUME ожидаем одиночный объект
            if self.page_type == PageType.RESUME:
                if not isinstance(self.payload, ResumeDetailData):
                    raise ValueError(f"For RESUME page, payload must be ResumeDetailData, got {type(self.payload)}")
            
            # Для SERP ожидаем список (может быть пустым, но список)
            elif self.page_type == PageType.SERP:
                if not isinstance(self.payload, list):
                    raise ValueError(f"For SERP page, payload must be a List, got {type(self.payload)}")
        
        return self