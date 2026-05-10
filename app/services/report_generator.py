from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Імпортуємо тільки AnalysisResult (Verdict більше не існує)
from app.models.agent import AnalysisResult


class ReportGeneratorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportGenerator:
    """
    6.4 Report generator (Markdown).
    Адаптовано під нову Тріо-модель та статуси Світлофора.
    """

    def generate(
        self, resume_json: Dict[str, Any], analysis: Optional[AnalysisResult]
    ) -> str:
        title = self._extract_position_title(resume_json) or "Невідома посада"
        url = self._extract_url(resume_json) or ""

        # 1. Захист: якщо аналізатор повернув None
        if analysis is None:
            return self._generate_error_block(title, url, "Помилка аналізу LLM")

        # 2. Захист: закриті контакти / авторизація
        if (
            "обмежений" in analysis.reasoning.lower()
            or "авторизація" in analysis.reasoning.lower()
        ):
            return self._generate_protected_block(title, url)

        # 3. Перевірка на "порожню сторінку" (за новою канонічною моделлю)
        payload = resume_json.get("payload")
        src = payload if isinstance(payload, dict) else resume_json
        page_type = resume_json.get("page_type") or src.get("page_type")

        # Перевіряємо нові поля
        skills = src.get("skills")
        experience = src.get("experience")
        education = src.get("education")
        summary = src.get("summary")

        has_structured = (
            (isinstance(skills, (list, dict)) and bool(skills))
            or (isinstance(experience, (list, dict)) and bool(experience))
            or (isinstance(education, (list, dict)) and bool(education))
        )
        has_full_text = isinstance(summary, str) and bool(summary.strip())

        red_empty_page = (
            page_type == "resume" and not has_structured and not has_full_text
        )

        if red_empty_page:
            return self._generate_error_block(title, url, "Дані відсутні на сторінці.")

        # 4. Рендеринг нормального звіту за статусами "Світлофора"
        status_map = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}

        # Беремо дані з аналізу (вони пріоритетні), або фолбек на json
        cand_title = getattr(analysis, "candidate_role", title)
        cand_url = getattr(analysis, "candidate_url", url)
        status = getattr(analysis, "status", "RED")
        verdict_emoji = status_map.get(status, "🔴")

        md: list[str] = []
        md.append(f"## {cand_title}")
        md.append("")
        md.append(
            f"[Посилання на резюме]({cand_url})"
            if cand_url
            else "[Посилання на резюме](#)"
        )
        md.append("")
        md.append(f"**Вердикт:** {verdict_emoji}")

        if status == "GREEN":
            md.append("\n**Повна відповідність:**")
        elif status == "YELLOW":
            md.append("\n**Ризики / Чого бракує:**")
        elif status == "RED":
            md.append("\n**Чому не підходить:**")

        # Виводимо єдине поле reasoning замість старих evidence/missing
        md.append(getattr(analysis, "reasoning", ""))
        md.append("\n---\n")

        return "\n".join(md)

    def generate_from_files(
        self, resume_json_path: str, analysis_json_path: str
    ) -> str:
        resume = self._load_json(resume_json_path)
        analysis_obj = self._load_json(analysis_json_path)
        analysis = AnalysisResult.model_validate(analysis_obj)
        return self.generate(resume_json=resume, analysis=analysis)

    # --------------------
    # Helpers: Error handling
    # --------------------

    def _generate_error_block(self, title: str, url: str, error_msg: str) -> str:
        md: list[str] = []
        md.append(f"## {title}")
        md.append("")
        if url:
            md.append(f"[Посилання на резюме]({url})")
            md.append("")
        md.append("**Вердикт:** ⚠️")
        md.append("")
        md.append(f"- {error_msg}")
        md.append("")
        md.append("---")
        md.append("")
        return "\n".join(md)

    def _generate_protected_block(self, title: str, url: str) -> str:
        md: list[str] = []
        md.append(f"## {title}")
        md.append("")
        if url:
            md.append(f"[Посилання на резюме]({url})")
            md.append("")
        md.append("**Вердикт:** 🟡")
        md.append("")
        md.append("**Чому підходить:**")
        md.append("Немає даних")
        md.append("")
        md.append("**Ризики / Чого бракує:**")
        md.append(
            "Доступ до резюме обмежений, перейдіть за посиланням для отримання даних резюме."
        )
        md.append("")
        md.append("---")
        md.append("")
        return "\n".join(md)

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
            raise ReportGeneratorError(
                f"Failed to load JSON: {path}. Error: {e}"
            ) from e
