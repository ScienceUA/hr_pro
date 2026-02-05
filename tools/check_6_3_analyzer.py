import json

from app.services.analyzer import ResumeAnalyzer


SYSTEM_PROMPT = """
You are a strict resume evaluation engine.

Rules (non-negotiable):
1) Use ONLY the provided resume text and the provided criteria_bundle. Do NOT assume or infer hidden skills.
2) If a skill/requirement is NOT explicitly present in the resume text, treat it as missing and put it into missing_criteria.
   Do NOT write "probably", "maybe", "likely", "implied", or "could know".
3) Evidence must be direct quotes copied from the resume. If you cannot quote it, you cannot claim it.
4) Return ONLY one JSON object. No markdown, no code fences, no extra keys, no explanations outside JSON.
5) Verdict policy:
   - MATCH: all must-have criteria are explicitly evidenced; no must-not violations.
   - CONDITIONAL: some must-have criteria are missing OR unclear, but overall profile could fit; include missing_criteria.
   - REJECT: must-not violation OR critical must-have missing, with clear reasoning.
6) Be concise. reasoning must be short and factual.
""".strip()


def fake_llm(messages):
    # Имитируем корректный JSON-ответ модели.
    # Важно: этот тест проверяет схему/валидацию, а не качество решения.
    return json.dumps({
        "verdict": "CONDITIONAL",
        "reasoning": "Some required skills are not explicitly mentioned.",
        "evidence": [
            {"source_field": "summary", "quote": "Project management and stakeholder communication", "supports": "project management experience"}
        ],
        "missing_criteria": ["explicit Scrum certification", "English level B2 explicitly stated"]
    }, ensure_ascii=False)


def main():
    analyzer = ResumeAnalyzer(llm_chat=fake_llm, system_prompt=SYSTEM_PROMPT)

    # Минимальное “резюме” как JSON (похоже на JSONL запись, но упрощено)
    resume_json = {
        "url": "https://work.ua/resumes/123456/",
        "title": "Project Manager",
        "summary": "Project management and stakeholder communication"
    }

    # Минимальный CriteriaBundle (структура любая — анализатор сейчас принимает dict)
    criteria_bundle = {
        "search": {"query": "Project Manager", "city": "kyiv", "params": {}},
        "must": ["project management experience"],
        "must_not": [],
        "semantic": ["communication", "leadership"]
    }

    result = analyzer.analyze(resume_json=resume_json, criteria_bundle=criteria_bundle)
    print("OK: AnalysisResult validated")
    print(result.model_dump_json(ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
