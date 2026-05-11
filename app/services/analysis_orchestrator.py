import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import settings
from app.models.parsed_resume import (
    CoreParsedResume,
    core_parsed_resume_from_legacy_result,
    core_parsed_resume_from_parser_service_response,
)
from app.services.legacy_parser_compat_service import (
    check_freshness_with_legacy_validator,
    get_legacy_adapter,
    parse_urls_with_legacy_adapter,
    preview_with_legacy_adapter,
)
from app.services.parser_runtime_service import (
    check_freshness_with_parser_service,
    parse_resume_with_parser_service,
)


async def check_resume_freshness_for_analysis(
    *,
    payload,
    url: str,
    created_at: str | None = None,
) -> bool:
    if settings.USE_PARSER_SERVICE_FRESHNESS:
        freshness = await check_freshness_with_parser_service(
            source=payload.source,
            url=url,
        )
        return bool(freshness.get("is_fresh"))
    return await check_freshness_with_legacy_validator(url, created_at)

from app.config.settings import settings
from app.models.search import SearchPayload
from app.models.task_status import task_status_payload
from app.services.analyzer import ResumeAnalyzer
from app.services.llm_client import real_llm_chat
from app.services.report_generator import ReportGenerator
from app.storage.redis_client import redis_client
from app.storage.repository import get_repository
from app.storage.vector_cache import VectorCache, resume_to_searchable_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Role: Ти — об'єктивний та аналітичний ШІ-оцінювач резюме
в архітектурі Cloud-Native. Твоя задача — порівняти профіль
кандидата із вимогами та винести вердикт.

Context: Тобі надається JSON-об'єкт кандидата та два масиви вимог:
internal_mandatory (обов'язкові) та desirable (бажані). Результати
твого аналізу зберігаються у централізованому Redis-сховищі та Data Lake.

Алгоритм оцінки (Тріо-Модель):
1. Крок 1 (Обов'язкові вимоги):
   - Перевір, чи відповідає кандидат УСІМ вимогам з internal_mandatory.
   - Використовуй глибокий семантичний аналіз (розуміння синонімів, контексту досвіду).
   - Якщо бракує хоча б ОДНІЄЇ обов'язкової вимоги -> статус RED (🔴).

2. Крок 2 (Бажані навички):
   - Якщо всі обов'язкові вимоги виконано, перевір desirable.
   - Якщо бракує хоча б однієї бажаної навички -> статус YELLOW (🟡).

3. Крок 3 (Ідеальний збіг):
   - Виконано всі обов'язкові ТА всі бажані вимоги -> статус GREEN (🟢).

Правила аргументації (reasoning):
- Коментар має бути лаконічним (2-3 речення).
- RED: Чітко вкажи тільки ті обов'язкові вимоги, яких не знайдено.
- YELLOW: Підтвердь виконання обов'язкових та вкажи, яких саме бажаних навичок бракує.
- GREEN: Підтвердь повну відповідність за всіма пунктами.

Output Format (JSON ONLY):
{
  "candidate_url": "URL з вхідного JSON",
  "candidate_role": "Title з вхідного JSON",
  "status": "RED | YELLOW | GREEN",
  "reasoning": "Лаконічний текст українською мовою"
}
""".strip()

_vector_cache: Optional[VectorCache] = None


def get_vector_cache() -> VectorCache:
    global _vector_cache
    if _vector_cache is None:
        logger.info("Initializing global VectorCache...")
        _vector_cache = VectorCache()
    return _vector_cache


def get_adapter(source: str):
    return get_legacy_adapter(source)


def extract_resume_id(url: str) -> Optional[str]:
    matches = re.findall(r"\d+", url or "")
    if matches:
        return matches[-1]
    return None


def should_skip(url: str, resume_id: Optional[str] = None) -> bool:
    repo = get_repository()
    dedup_key = resume_id or extract_resume_id(url) or f"url:{url}"
    return repo.exists(dedup_key)


def _filter_new_urls(urls: List[str]) -> Tuple[List[str], int]:
    filtered = []
    skipped = 0
    for url in urls:
        resume_id = extract_resume_id(url)
        if should_skip(url, resume_id):
            skipped += 1
            logger.debug("Skipping duplicate resume before adapter run: %s", url)
            continue
        filtered.append(url)
    return filtered, skipped


async def parse_resumes_with_parser_service(
    payload: SearchPayload,
    urls: List[str],
) -> Tuple[Dict[str, Any], List[CoreParsedResume]]:
    stats = {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None}
    results: List[CoreParsedResume] = []

    for url in urls:
        response = await parse_resume_with_parser_service(
            source=payload.source,
            url=url,
        )
        if not response.get("parsed"):
            stats["errors"] += 1
            logger.warning(
                "Parser Service did not parse %s. Errors: %s",
                url,
                response.get("errors", []),
            )
            continue

        try:
            result = core_parsed_resume_from_parser_service_response(response)
        except Exception as e:
            stats["errors"] += 1
            logger.error(
                "Parser Service returned incompatible parse data for %s: %s",
                url,
                e,
            )
            continue

        stats["saved"] += 1
        results.append(result)

    return stats, results


async def run_analysis_task(session_id: str, payload: SearchPayload):
    logger.info("Starting analysis task for session: %s", session_id)
    await redis_client.set_task_status(
        session_id,
        task_status_payload(
            session_id,
            "running",
            step="semantic_pre_search",
        ),
    )

    try:
        v_cache = get_vector_cache()
        criteria_text = build_criteria_text(payload)
        cached_items = v_cache.get_cached_by_criteria(
            criteria_text=criteria_text,
            role=payload.query,
            limit=payload.pages * 20,
        )

        await redis_client.set_task_status(
            session_id,
            task_status_payload(
                session_id,
                "running",
                step="freshness_validation",
                cached_found=len(cached_items),
            ),
        )

        fresh_items = []
        for item in cached_items:
            url = item.get("url", "")
            created_at = item.get("created_at")
            is_fresh = await check_resume_freshness_for_analysis(
                payload=payload,
                url=url,
                created_at=created_at,
            )
            if is_fresh:
                fresh_items.append(item)
            else:
                logger.info("Removing stale cache entry: %s", url)
                v_cache.delete_analysis(item["id"])

        target_count = payload.pages * 20
        delta = max(0, target_count - len(fresh_items))
        newly_parsed_resumes: List[Any] = []
        skipped_duplicates = 0
        repo = get_repository()

        if delta > 0:
            await redis_client.set_task_status(
                session_id,
                task_status_payload(
                    session_id,
                    "running",
                    step="crawling",
                    cache_hits=len(fresh_items),
                    delta_to_fetch=delta,
                ),
            )

            preview_data = await preview_with_legacy_adapter(payload)
            urls, skipped_duplicates = _filter_new_urls(
                preview_data.get("urls", [])[:delta]
            )

            if urls:
                if settings.USE_PARSER_SERVICE_PARSE:
                    stats, newly_parsed_resumes = (
                        await parse_resumes_with_parser_service(payload, urls)
                    )
                else:
                    stats, newly_parsed_resumes = await parse_urls_with_legacy_adapter(
                        payload,
                        urls,
                    )
                logger.info(
                    "Parsed %s new resumes. Stats: %s",
                    len(newly_parsed_resumes),
                    stats,
                )

                for result in newly_parsed_resumes:
                    try:
                        repo.save_result(_to_core_parsed_resume(result))
                    except Exception as e:
                        logger.error("Failed to save raw result: %s", e)

        cached_analyses = [
            ({"url": item["url"]}, item["analysis_result"]) for item in fresh_items
        ]

        analyzer = ResumeAnalyzer(llm_chat=real_llm_chat, system_prompt=SYSTEM_PROMPT)
        new_analyses = []

        await redis_client.set_task_status(
            session_id,
            task_status_payload(
                session_id,
                "running",
                step="analysis",
                total=len(newly_parsed_resumes),
            ),
        )

        for idx, result in enumerate(newly_parsed_resumes):
            await redis_client.set_task_status(
                session_id,
                task_status_payload(
                    session_id,
                    "running",
                    step="analysis",
                    progress=f"{idx + 1}/{len(newly_parsed_resumes)}",
                ),
            )
            try:
                resume_json = _as_resume_dict(result)
                analysis = analyzer.analyze(
                    resume_json=resume_json,
                    criteria_bundle=payload.criteria_bundle,
                )
                if analysis:
                    analysis_dict = (
                        analysis if isinstance(analysis, dict) else analysis.model_dump()
                    )
                    new_analyses.append((resume_json, analysis_dict))

                    try:
                        repo.save_analysis(analysis_dict)
                    except Exception as e:
                        logger.error("Failed to save analysis: %s", e)

                    resume_text = resume_to_searchable_text(resume_json)
                    logger.debug(
                        "Saving analysis for %s to vector cache. Text chars: %s",
                        result.url,
                        len(resume_text),
                    )
                    v_cache.save_analysis(
                        resume_text=resume_text,
                        role=payload.query,
                        analysis_result=analysis_dict,
                        url=result.url,
                    )
            except Exception as e:
                logger.error("Analysis failed for resume %s: %s", result.url, e)

        final_report = generate_report(payload.query, cached_analyses + new_analyses)

        await redis_client.set_task_status(
            session_id,
            task_status_payload(
                session_id,
                "completed",
                message="Analysis finished successfully.",
                report=final_report,
                cache_hits=len(fresh_items),
                newly_parsed=len(newly_parsed_resumes),
                skipped_duplicates=skipped_duplicates,
            ),
        )

    except Exception as e:
        logger.error("Analysis task failed for %s: %s", session_id, e)
        await redis_client.set_task_status(
            session_id,
            task_status_payload(
                session_id,
                "failed",
                error=str(e),
            ),
        )


def build_criteria_text(payload: SearchPayload) -> str:
    bundle = payload.criteria_bundle
    parts = [payload.query]
    if bundle.get("internal_mandatory"):
        parts.append("Обов'язкові вимоги: " + ", ".join(bundle["internal_mandatory"]))
    if bundle.get("desirable"):
        parts.append("Бажані вимоги: " + ", ".join(bundle["desirable"]))
    return ". ".join(part for part in parts if part)


def generate_report(query: str, analyses: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> str:
    reporter = ReportGenerator()
    report_analyses = [
        (resume_json, analysis)
        for resume_json, analysis in analyses
        if _analysis_status(analysis) != "RED"
    ]
    report_analyses.sort(key=lambda item: _verdict_priority(item[1]))

    md_lines = [f"# Analysis Report for {query}\n"]
    if not report_analyses:
        md_lines.append("Жодного кандидата не знайдено (всі відхилені або порожні).\n")
    else:
        for resume_json, analysis in report_analyses:
            md_lines.append(reporter.generate(resume_json, analysis))
            md_lines.append("\n---\n")
    return "\n".join(md_lines)


def _analysis_status(analysis: Dict[str, Any]) -> str:
    return analysis.get("status", "RED") if isinstance(analysis, dict) else "RED"


def _verdict_priority(analysis: Dict[str, Any]) -> int:
    status = _analysis_status(analysis)
    if status == "GREEN":
        return 1
    if status == "YELLOW":
        return 2
    return 3


def _as_resume_dict(result: Any) -> Dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    raise TypeError(f"Unsupported parsing result type: {type(result)}")


def _to_core_parsed_resume(result: Any) -> CoreParsedResume:
    if isinstance(result, CoreParsedResume):
        return result
    return core_parsed_resume_from_legacy_result(result)
