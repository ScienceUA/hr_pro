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
        title = self._extract_position_title(resume_json) or "Невідома посада"
        url = self._extract_url(resume_json) or ""

        verdict_emoji = self._verdict_to_emoji(analysis.verdict)

        evidence_lines = self._format_evidence(analysis)
        missing_lines = self._format_missing(analysis)
        questions_lines = self._format_questions(analysis)

        # IMPORTANT: We intentionally do NOT include any name/contact fields from resume_json.
        md: list[str] = []

        # -------- Detect "data unavailable" resumes (Work.ua restricted/undecoded) --------
        payload = resume_json.get("payload")
        src = payload if isinstance(payload, dict) else resume_json

        page_type = resume_json.get("page_type") or src.get("page_type")

        has_uploaded_file = bool(src.get("has_uploaded_file", False))

        about_raw = src.get("about_raw")
        skills = src.get("skills")
        experience = src.get("experience")
        education = src.get("education")

        has_structured = (
            (isinstance(skills, (list, dict)) and bool(skills))
            or (isinstance(experience, (list, dict)) and bool(experience))
            or (isinstance(education, (list, dict)) and bool(education))
        )

        has_full_text = isinstance(about_raw, str) and bool(about_raw.strip())

        # 🟡 Есть прикрепленный файл, но текст недоступен
        yellow_unavailable = (
            page_type == "resume"
            and has_uploaded_file
            and not has_structured
            and not has_full_text
        )

        # 🔴 Страница полностью пустая
        red_empty_page = (
            page_type == "resume"
            and not has_uploaded_file
            and not has_structured
            and not has_full_text
        )


        if yellow_unavailable:
            verdict_emoji = "🟡"
            evidence_lines = "- (дані резюме недоступні для аналізу)"
            missing_lines = (
                "- Дані недоступні: Work.ua не надав текст резюме без доступу роботодавця.\n"
                "- Щоб отримати дані, зареєструйтеся на Work.ua як роботодавець і придбайте послугу "
                "«Доступ до бази кандидатів» або відповідний пакет послуг."
            )

        elif red_empty_page:
            verdict_emoji = "🔴"
            evidence_lines = "- (сторінка резюме не містить доступних даних)"
            missing_lines = "- Дані відсутні на сторінці."

        # -------- Standard report rendering --------
        if red_empty_page:
            md.append(f"## {title} (сторінка порожня)")
            md.append("")
            md.append(f"[Посилання на резюме]({url})" if url else "[Посилання на резюме](#)")
            md.append("")
            md.append("**Вердикт:** 🔴")
            md.append("")
            md.append("- Дані відсутні на сторінці.")
            md.append("")
            return "\n".join(md)

        # Not empty-page: render normal full report
        if yellow_unavailable:
            md.append(f"## {title} (дані недоступні)")
        else:
            md.append(f"## {title}")

        md.append("")
        md.append(f"[Посилання на резюме]({url})" if url else "[Посилання на резюме](#)")
        md.append("")
        md.append(f"**Вердикт:** {verdict_emoji}")
        md.append("")
        md.append("**Чому підходить:**")
        md.append(evidence_lines)
        md.append("")
        md.append("**Ризики / Чого бракує:**")
        md.append(missing_lines)
        md.append("")

        # For "data unavailable" resumes, hide the interview section entirely
        if (
            not yellow_unavailable
            and not red_empty_page
            and analysis.verdict != Verdict.REJECT
        ):
            md.append("**Питання для співбесіди:**")
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
            return "- (немає явних підтверджень у тексті)"
        lines = []
        for e in analysis.evidence:
            # Only quote + what it supports (no private info)
            lines.append(f"- «{e.quote}» — {e.supports} ({e.location})")
        return "\n".join(lines)

    def _format_missing(self, analysis: AnalysisResult) -> str:
        if not analysis.missing_criteria:
            return "- (нічого критичного не бракує за поточними критеріями)"
        return "\n".join(f"- {m}" for m in analysis.missing_criteria)

    def _format_questions(self, analysis: AnalysisResult) -> str:
        if not analysis.interview_questions:
            return "- (питання не згенеровані)"
        return "\n".join(f"- {q}" for q in analysis.interview_questions)

    # --------------------
    # Helpers: privacy-safe extraction
    # --------------------

    def _extract_position_title(self, resume_json: Dict[str, Any]) -> str:
        payload = resume_json.get("payload")
        if isinstance(payload, dict):
            resume_json = payload

        for k in ["title", "position", "candidate_title"]:
            v = resume_json.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

        return ""


    def _extract_url(self, resume_json: Dict[str, Any]) -> str:
        payload = resume_json.get("payload")
        if isinstance(payload, dict):
            v = payload.get("url")
            if isinstance(v, str) and v.strip():
                return v.strip()

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
