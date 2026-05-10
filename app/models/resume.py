from typing import List, Optional
from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    period: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    year_end: Optional[int] = None


class Language(BaseModel):
    name: Optional[str] = None
    level: Optional[str] = None


class Resume(BaseModel):
    """Канонічна модель профілю кандидата"""

    id: str = Field(..., description="Унікальний ідентифікатор резюме")
    source: str = Field(
        ..., description="Джерело походження ('workua', 'robotaua', тощо)"
    )
    url: str = Field(..., description="Повне посилання на профіль")
    title: str = Field(..., description="Вказана посада кандидата")
    salary: Optional[str] = Field(None, description="Очікувана зарплата")
    location: Optional[str] = Field(
        None, description="Місто проживання або готовність до релокейту/remote"
    )
    skills: List[str] = Field(
        default_factory=list, description="Ключові навички (Tags)"
    )
    summary: Optional[str] = Field(
        None, description="Розділ 'Про себе' або текст із завантаженого CV"
    )
    experience: List[Experience] = Field(
        default_factory=list, description="Досвід роботи"
    )
    education: List[Education] = Field(default_factory=list, description="Освіта")
    languages: List[Language] = Field(default_factory=list, description="Знання мов")
