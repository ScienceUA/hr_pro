from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.common import ErrorDetail

class LanguageLevelPair(BaseModel):
    language_id: int
    level_id: int

class SearchQuery(BaseModel):
    """Параметры поиска резюме (Входные данные)"""
    city_slug: str = Field(..., description="Slug города (kyiv, lviv) или 'remote'")
    role_text: Optional[str] = Field(None, description="Текст поискового запроса")
    category_ids: Optional[List[int]] = None
    
    # Демография
    gender_ids: Optional[List[int]] = None
    age_from: Optional[int] = Field(None, ge=14, le=100)
    age_to: Optional[int] = Field(None, ge=14, le=100)
    
    # Квалификация
    education_ids: Optional[List[int]] = None
    experience_ids: Optional[List[int]] = None
    language_ids: Optional[List[int]] = None
    language_level_pairs: Optional[List[LanguageLevelPair]] = None
    
    # Флаги
    student_only: Optional[bool] = None
    disability_only: Optional[bool] = None
    photo_only: Optional[bool] = None
    period_days: Optional[int] = Field(None, description="За сколько дней искать (7, 30)")
    
    page: int = Field(1, ge=1)

class SearchResponse(BaseModel):
    """Результат поиска (Выходные данные)"""
    total_found: int
    resume_urls: List[str] = Field(default_factory=list)
    
    # Поля для частичного успеха
    errors: List[ErrorDetail] = Field(default_factory=list, description="Ошибки при обработке (если partial)")
    metadata: Optional[dict] = Field(default_factory=dict, description="Доп. инфо (время выполнения, кол-во страниц)")