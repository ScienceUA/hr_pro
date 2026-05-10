from typing import List, Optional
from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    # Core fields defined in the system prompt
    status: str = Field(..., description="RED | YELLOW | GREEN")
    reasoning: str = Field(..., description="Лаконічний текст аргументації")
    
    # Optional extended fields for deep analysis
    verdict: Optional[str] = Field(None, description="Internal verdict status (e.g., REJECT)")
    evidence: List[str] = Field(default_factory=list, description="List of evidence points")
    missing_criteria: List[str] = Field(default_factory=list, description="List of missing criteria")
