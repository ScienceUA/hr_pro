from typing import List, Optional
from pydantic import BaseModel

class ExperienceBlock(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    period: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None

class EducationBlock(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    specialty: Optional[str] = None
    period: Optional[str] = None

class LanguageSkill(BaseModel):
    name: str
    level: Optional[str] = None

class WorkPreferences(BaseModel):
    salary_expectation: Optional[str] = None
    employment_type: List[str] = []
    schedule: List[str] = []

class ResumeJSON(BaseModel):
    """Детальная структура резюме"""
    resume_url: str
    resume_type: str = "standard"
    
    # Основная инфо
    title: str
    location_main: str
    additional_locations: List[str] = []
    age: Optional[int] = None
    updated_at: Optional[str] = None
    
    # Блоки
    experience_blocks: List[ExperienceBlock] = []
    education_blocks: List[EducationBlock] = []
    skills: List[str] = []
    languages: List[LanguageSkill] = []
    additional_courses: List[str] = []
    
    work_preferences: Optional[WorkPreferences] = None