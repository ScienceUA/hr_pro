from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.models.agent import AnalysisResult, Verdict


class ReportGeneratorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportGenerator:
    """
    6.4 Report generator (Markdown).

    Privacy rule:
      - DO NOT output full name, phone, email, or any contact fields.
      - Title must be only position title from resume.
      - Link: Work.ua URL.
    """

    def generate(self, resume_json: Dict[str, Any], analysis: AnalysisResult) -> str:
        title = self._extract_position_title(resume_json) or "Unknown Position"
        url = self._extract_url(resume_json) or ""

        verdict_emoji = self._verdict_to_emoji(analysis.verdict)

        evidence_lines = self._format_evidence(analysis)
        missing_lines = self._format_missing(analysis)
        questions_lines = self._format_questions(analysis)

        # IMPORTANT: We intentionally do NOT include any name/contact fields from resume_json.
        md = []
        md.append(f"## {title}")
        md.append("")
        md.append(f"[Ссылка на резюме]({url})" if url else "[Ссылка на резюме](#)")
        md.append("")
        md.append(f"**Вердикт:** {verdict_emoji}")
        md.append("")
        md.append("**Почему подходит:**")
        md.append(evidence_lines)
        md.append("")
        md.append("**Риски / Чего нет:**")
        md.append(missing_lines)
        md.append("")
        md.append("**Вопросы для собеседования:**")
        md.append(questions_lines)
        md.append("")

        return "\n".join(md)

    def generate_from_files(self, resume_json_path: str, analysis_json_path: str) -> str:
        resume = self._load_json(resume_json_path)
        analysis_obj = self._load_json(analysis_json_path)
        analysis = AnalysisResult.model_validate(analysis_obj)
        return self.generate(resume_json=resume, analysis=analysis)

    # --------------------
    # Helpers: formatting
    # --------------------

    def _verdict_to_emoji(self, verdict: Verdict) -> str:
        if verdict == Verdict.MATCH:
            return "🟢"
        if verdict == Verdict.CONDITIONAL:
            return "🟡"
        return "🔴"

    def _format_evidence(self, analysis: AnalysisResult) -> str:
        if not analysis.evidence:
            return "- (нет явных подтверждений в тексте)"
        lines = []
        for e in analysis.evidence:
            # Only quote + what it supports (no private info)
            lines.append(f"- «{e.quote}» — {e.supports} ({e.location})")
        return "\n".join(lines)

    def _format_missing(self, analysis: AnalysisResult) -> str:
        if not analysis.missing_criteria:
            return "- (ничего критичного не отсутствует по текущим критериям)"
        return "\n".join(f"- {m}" for m in analysis.missing_criteria)

    def _format_questions(self, analysis: AnalysisResult) -> str:
        if not analysis.interview_questions:
            return "- (вопросы не сгенерированы)"
        return "\n".join(f"- {q}" for q in analysis.interview_questions)

    # --------------------
    # Helpers: privacy-safe extraction
    # --------------------

    def _extract_position_title(self, resume_json: Dict[str, Any]) -> str:
        for k in ["title", "position", "candidate_title"]:
            v = resume_json.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def _extract_url(self, resume_json: Dict[str, Any]) -> str:
        v = resume_json.get("url")
        return v.strip() if isinstance(v, str) and v.strip() else ""

    def _load_json(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ReportGeneratorError(f"JSON must be an object: {path}")
            return data
        except Exception as e:
            raise ReportGeneratorError(f"Failed to load JSON: {path}. Error: {e}") from e
