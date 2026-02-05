from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, ConfigDict


class Verdict(str, Enum):
    MATCH = "MATCH"
    CONDITIONAL = "CONDITIONAL"
    REJECT = "REJECT"


class EvidenceItem(BaseModel):
    """
    Evidence must be a verbatim quote from resume_content (no paraphrasing).
    """
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(..., min_length=1, description="Verbatim quote copied from resume_content.")
    supports: str = Field(..., min_length=1, description="Which criterion this quote supports.")
    location: str = Field(..., min_length=1, description="Section name: Title|Skills|Experience|Education.")


class AnalysisResult(BaseModel):
    """
    No scores. Only categorical verdict + reasoning + evidence + missing criteria + interview questions.
    """
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    reasoning: str = Field(..., min_length=1, description="Short factual explanation (no speculation).")
    evidence: List[EvidenceItem] = Field(default_factory=list)
    missing_criteria: List[str] = Field(default_factory=list, description="Criteria not explicitly found in text.")
    interview_questions: List[str] = Field(
        default_factory=list,
        description="3-5 questions to validate weak points or confirm experience."
    )
