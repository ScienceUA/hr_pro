from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import ValidationError

from app.models.agent import AnalysisResult


class ResumeAnalyzerError(RuntimeError):
    pass


class LLMResponseFormatError(ResumeAnalyzerError):
    pass


class ResumeAnalyzer:
    """
    6.3 Semantic analysis orchestrator:
      CriteriaBundle (dict) + resume_json (dict from Local MVP JSONL) -> AnalysisResult via LLM.

    Security + cost controls:
      - optimize resume into compact text (no HTML, no service fields)
      - sanitize input
      - isolate resume in <resume_content> XML tag
      - strict JSON output validated by Pydantic
    """

    def __init__(
        self,
        llm_chat: Callable[[Sequence[Dict[str, str]]], str],
        system_prompt: str,
    ) -> None:
        self._llm_chat = llm_chat
        self._system_prompt = system_prompt.strip()

    # -----------------
    # Public API
    # -----------------

    def analyze(self, resume_json: Dict[str, Any], criteria_bundle: Dict[str, Any]) -> AnalysisResult:
        messages = self.prepare_prompt(resume_json=resume_json, criteria_bundle=criteria_bundle)
        raw = self.call_llm(messages)
        return self.parse_response(raw)

    # -----------------
    # Step 1: Prompt
    # -----------------

    def prepare_prompt(self, resume_json: Dict[str, Any], criteria_bundle: Dict[str, Any]) -> List[Dict[str, str]]:
        resume_text = self._optimize_resume_data(resume_json)
        resume_text = self._sanitize_text(resume_text)

        # IMPORTANT: criteria_bundle may contain internal fields; we pass it as-is,
        # but we do NOT embed any HTML or raw resume objects.
        criteria_payload = criteria_bundle

        user_content = (
            "You will evaluate the candidate resume against the criteria_bundle.\n"
            "Return ONLY one JSON object matching the AnalysisResult schema.\n\n"
            "criteria_bundle (data):\n"
            f"{json.dumps(criteria_payload, ensure_ascii=False, indent=2)}\n\n"
            "resume_content (data, isolated):\n"
            "<resume_content>\n"
            f"{resume_text}\n"
            "</resume_content>\n"
        )

        return [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

    # -----------------
    # Step 2: LLM call
    # -----------------

    def call_llm(self, messages: Sequence[Dict[str, str]]) -> str:
        try:
            return self._llm_chat(messages)
        except Exception as e:
            raise ResumeAnalyzerError(f"LLM call failed: {e}") from e

    # -----------------
    # Step 3: Parse response
    # -----------------

    def parse_response(self, raw_text: str) -> AnalysisResult:
        obj = self._extract_first_json_object(raw_text)
        if obj is None:
            raise LLMResponseFormatError(
                "LLM did not return a valid JSON object. Expected a single JSON object for AnalysisResult."
            )

        try:
            return AnalysisResult.model_validate(obj)
        except ValidationError as ve:
            raise LLMResponseFormatError(
                f"LLM returned JSON but it does not match AnalysisResult schema: {ve}"
            ) from ve

    # =================
    # Pre-processing
    # =================

    def _optimize_resume_data(self, resume_json: Dict[str, Any]) -> str:
        """
        Token economy:
          Build compact Markdown from significant fields only:
          - Title (position/candidate_title/title)
          - Skills
          - Experience
          - Education

        Hard rules:
          - DO NOT send raw HTML
          - DO NOT send service fields (cookies, headers, raw responses, etc.)
        """
        title = self._pick_first_str(resume_json, ["title", "position", "candidate_title"])
        skills = self._pick_skills(resume_json)
        experience = self._pick_experience(resume_json)
        education = self._pick_education(resume_json)

        parts: List[str] = []
        if title:
            parts.append("# Title\n" + title.strip())

        if skills:
            parts.append("# Skills\n" + "\n".join(f"- {s}" for s in skills))

        if experience:
            parts.append("# Experience\n" + "\n\n".join(experience))

        if education:
            parts.append("# Education\n" + "\n\n".join(education))

        # If nothing extracted, we still return a minimal marker so model can't hallucinate.
        if not parts:
            return "# Resume\n(no extractable content)"

        return "\n\n".join(parts)

    def _sanitize_text(self, text: str) -> str:
        """
        Input sanitization (basic):
          - remove control characters
          - strip very suspicious instruction-like fragments
          - keep user content readable
        """
        if not text:
            return text

        # Remove ASCII control chars except \n and \t
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        # Collapse excessive whitespace (but keep newlines for structure)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Basic prompt-injection hardening: neutralize common role markers if present in resume
        # (resume must be treated as data, not instructions)
        text = text.replace("<system>", "&lt;system&gt;").replace("</system>", "&lt;/system&gt;")
        text = text.replace("<assistant>", "&lt;assistant&gt;").replace("</assistant>", "&lt;/assistant&gt;")
        text = text.replace("<user>", "&lt;user&gt;").replace("</user>", "&lt;/user&gt;")

        return text.strip()

    # =================
    # Field extractors
    # =================

    def _pick_first_str(self, obj: Dict[str, Any], keys: List[str]) -> str:
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return ""

    def _pick_skills(self, resume_json: Dict[str, Any]) -> List[str]:
        v = resume_json.get("skills")
        if isinstance(v, list):
            out = [self._to_clean_str(x) for x in v if self._to_clean_str(x)]
            return out[:60]  # token safety
        if isinstance(v, str) and v.strip():
            # split by common delimiters
            chunks = re.split(r"[,;•\n]+", v)
            out = [c.strip() for c in chunks if c.strip()]
            return out[:60]
        return []

    def _pick_experience(self, resume_json: Dict[str, Any]) -> List[str]:
        v = resume_json.get("experience")
        if not isinstance(v, list):
            return []

        blocks: List[str] = []
        for i, item in enumerate(v[:12]):  # limit
            if not isinstance(item, dict):
                continue
            role = self._to_clean_str(item.get("position") or item.get("title") or item.get("role"))
            company = self._to_clean_str(item.get("company"))
            period = self._to_clean_str(item.get("period") or item.get("dates"))
            desc = self._to_clean_str(item.get("description") or item.get("details"))

            header_parts = [p for p in [role, company, period] if p]
            header = " — ".join(header_parts) if header_parts else f"Experience #{i+1}"
            body = desc if desc else "(no description)"

            blocks.append(f"## {header}\n{body}")

        return blocks

    def _pick_education(self, resume_json: Dict[str, Any]) -> List[str]:
        v = resume_json.get("education")
        if not isinstance(v, list):
            return []

        blocks: List[str] = []
        for i, item in enumerate(v[:8]):  # limit
            if not isinstance(item, dict):
                continue
            degree = self._to_clean_str(item.get("degree") or item.get("title"))
            school = self._to_clean_str(item.get("institution") or item.get("school"))
            period = self._to_clean_str(item.get("period") or item.get("dates"))
            desc = self._to_clean_str(item.get("description"))

            header_parts = [p for p in [degree, school, period] if p]
            header = " — ".join(header_parts) if header_parts else f"Education #{i+1}"
            body = desc if desc else "(no details)"

            blocks.append(f"## {header}\n{body}")

        return blocks

    def _to_clean_str(self, v: Any) -> str:
        if isinstance(v, str):
            return v.strip()
        return ""

    # =================
    # JSON extraction
    # =================

    def _extract_first_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        text = (text or "").strip()
        if not text:
            return None

        # 1) whole-text JSON
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        # 2) scan for balanced {...}
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        try:
                            parsed = json.loads(candidate)
                            return parsed if isinstance(parsed, dict) else None
                        except Exception:
                            return None
        return None
