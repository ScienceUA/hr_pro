import random
import logging
import re
import asyncio
import httpx
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
from typing import Dict, Any, List, Tuple

from parser_service.execution.executor import RequestExecutor
from parser_service.parsing.base import BaseParser
from parser_service.parsing.serp import SerpParser
from parser_service.parsing.resume_parsers import WorkUaResumeParser
from parser_service.parsing.models import PageType, DataQuality, ParsingResult
from parser_service.storage.repository import BaseRepository

logger = logging.getLogger(__name__)


class WorkUaAdapter:
    """
    Адаптер для джерела Work.ua.
    Інкапсулює логіку побудови URL, пагінації та парсингу HTML.
    """

    # Системні константи для Anti-bot Jitter (в секундах)
    JITTER_MIN = 1.5
    JITTER_MAX = 2.5

    BASE_URL = "https://www.work.ua"
    CITY_SLUGS = {
        "киев": "kyiv",
        "київ": "kyiv",
        "kyiv": "kyiv",
        "kiev": "kyiv",
        "харьков": "kharkiv",
        "харків": "kharkiv",
        "kharkiv": "kharkiv",
        "одесса": "odesa",
        "одеса": "odesa",
        "odesa": "odesa",
        "odessa": "odesa",
        "днепр": "dnipro",
        "дніпро": "dnipro",
        "dnipro": "dnipro",
        "львов": "lviv",
        "львів": "lviv",
        "lviv": "lviv",
        "запорожье": "zaporizhzhia",
        "запоріжжя": "zaporizhzhia",
        "вся украина": "",
        "украина": "",
        "ukraine": "",
    }

    def __init__(self, executor: RequestExecutor, repository: BaseRepository):
        self.name = "workua"
        self.executor = executor
        self.repository = repository

    async def _fetch_html(self, url: str) -> str:
        """Асинхронна обгортка для безпечного виклику RequestExecutor з Resilience-політиками"""  # noqa: E501

        async def _do_fetch():
            # httpx.AsyncClient створюється локально для запиту
            async with httpx.AsyncClient() as client:
                response = await self.executor.execute(
                    lambda: client.get(
                        url, timeout=15.0, follow_redirects=True
                    )
                )
                return response.text

        try:
            return await _do_fetch()
        except Exception as e:
            logger.error(f"[{self.name}] Мережева або Resilience помилка: {e}")
            return ""

    async def preview(self, search_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 1: Проходить по сторінках SERP, рахує total_found та збирає URL.
        """
        query = str(search_payload.get("query") or "").strip()
        city = str(search_payload.get("city") or "").strip()
        params = search_payload.get("params") or {}
        max_pages = search_payload.get("pages", 5)
        direct_url = search_payload.get("direct_url")

        if not query and not direct_url:
            return {"total_found": 0, "urls": []}

        urls: List[str] = []
        seen: set[str] = set()
        real_total = None

        for page_num in range(1, int(max_pages) + 1):
            current_params = dict(params)
            if page_num > 1:
                current_params["page"] = page_num

            # --- ДОДАНО ОБРОБКУ МОВ ---
            languages = search_payload.get("languages", [])
            if languages:
                mapped_langs = self._map_language_levels(languages)
                if mapped_langs:
                    current_params["language_level"] = mapped_langs
            # --------------------------

            try:
                if direct_url:
                    current_url = self._append_page_to_url(
                        direct_url, page_num
                    )
                else:
                    current_url = self._build_url(query, city, current_params)
            except Exception as e:
                raise RuntimeError(f"Помилка генерації URL: {e}")

            logger.info(
                f"[{self.name}] 📎 Preview SERP page {page_num}: {current_url}"
            )

            try:
                html_content = await self._fetch_html(current_url)
                if not html_content:
                    raise RuntimeError(
                        f"Порожня відповідь від сервера на сторінці {page_num}"
                    )
            except Exception as e:
                raise RuntimeError(f"Мережева помилка: {e}")

            base_parser = BaseParser(html_content, current_url)
            self._check_page_safety(
                base_parser.page_type, context="SERP_PREVIEW"
            )

            if base_parser.page_type != PageType.SERP:
                logger.warning(
                    f"[{self.name}] Неочікуваний тип сторінки. Зупинка."
                )
                break

            serp_parser = SerpParser(html_content, current_url)
            serp_result = serp_parser.parse()

            if serp_result.quality == DataQuality.ERROR:
                logger.error(
                    f"[{self.name}] Помилка парсингу SERP: {serp_result.error_message}"  # noqa: E501
                )
                break

            if page_num == 1:
                try:
                    real_total = getattr(serp_result, "total_found", None)
                except Exception:
                    pass

            previews = serp_result.payload or []
            if not previews:
                break

            new_urls_found = False
            for p in previews:
                u = getattr(p, "url", None)
                if isinstance(u, str) and u and u not in seen:
                    seen.add(u)
                    urls.append(u)
                    new_urls_found = True

            if not new_urls_found:
                break

            if page_num < int(max_pages):
                await asyncio.sleep(
                    random.uniform(self.JITTER_MIN, self.JITTER_MAX)
                )

        total_to_return = (
            int(real_total)
            if isinstance(real_total, int) and real_total > 0
            else len(urls)
        )
        return {"total_found": total_to_return, "urls": urls}

    async def run_from_urls(self, urls: List[str]) -> Tuple[Dict[str, Any], List[ParsingResult]]:
        """
        Phase 2: Завантажує сторінки та парсить їх.
        Повертає (статистику, список_результатів).
        """
        stats = {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None}
        results = []

        if not urls:
            return stats, results

        for url in urls:
            await asyncio.sleep(
                random.uniform(self.JITTER_MIN, self.JITTER_MAX)
            )

            try:
                html_content = await self._fetch_html(url)
                if not html_content:
                    logger.warning(f"[{self.name}] Порожній контент: {url}")
                    stats["errors"] += 1
                    continue
            except Exception as e:
                logger.error(f"[{self.name}] Помилка завантаження {url}: {e}")
                stats["errors"] += 1
                continue

            base_parser = BaseParser(html_content, url)

            if base_parser.page_type == PageType.NOT_FOUND:
                logger.warning(
                    f"[{self.name}] Резюме не знайдено (404): {url}"
                )
                stats["errors"] += 1
                continue

            # 2. Гібридний Fail Fast: ловимо RuntimeError з _check_page_safety
            try:
                self._check_page_safety(
                    base_parser.page_type, context="DETAIL"
                )
            except RuntimeError as e:
                logger.critical(f"[{self.name}] Збір перервано: {e}")
                stats["critical_error"] = str(e)
                break  # Зупиняємо збір, але повертаємо те, що вже зібрали

            resume_parser = WorkUaResumeParser(html_content, url)
            result = resume_parser.parse()

            if result.quality == DataQuality.ERROR:
                logger.warning(
                    f"[{self.name}] Помилка парсингу {url}: {result.error_message}"  # noqa: E501
                )
                stats["errors"] += 1
                continue

            try:
                # self.repository.save_result(result)  # Removed as orchestrator will do it
                stats["saved"] += 1
                results.append(result)
                # Логування збереженого резюме (без поля name)
                candidate_title = (
                    getattr(result.payload, "title", "Без посади")
                    if result.payload
                    else "Unknown Title"
                )
                logger.info(
                    f"[{self.name}] ✅ Спарсено: Кандидат ({candidate_title})"
                )
            except Exception as e:
                logger.error(f"[{self.name}] Помилка обробки {url}: {e}")
                stats["errors"] += 1

        logger.info(
            f"[{self.name}] 🏁 Збір завершено. Спарсено: {len(results)}, Помилок: {stats['errors']}, Пропущено: {stats['skipped']}"  # noqa: E501
        )
        return stats, results

    def _check_page_safety(self, page_type: PageType, context: str) -> None:
        """Перевіряє наявність блокувань. Викидає Exception для Fail Fast в Оркестраторі."""  # noqa: E501
        if page_type in [PageType.BAN, PageType.CAPTCHA, PageType.LOGIN]:
            msg = f"Блокування доступу ({page_type.value.upper()}) на етапі {context}"
            logger.critical(f"[{self.name}] 🛑 {msg}")
            raise RuntimeError(msg)

    def _append_page_to_url(self, base_url: str, page_num: int) -> str:
        if page_num <= 1:
            return base_url
        parsed = urlparse(base_url)
        qs = parse_qs(parsed.query)
        qs["page"] = [str(page_num)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _build_url(
        self, query: str, city: str = "", params: Dict[str, Any] = None
    ) -> str:
        if not query:
            raise ValueError("Query cannot be empty")

        city_slug = self._get_city_slug(city)
        query_slug = self._slugify(query)

        parts = ["resumes"]
        if city_slug:
            parts.append(city_slug)
        parts.append(query_slug)

        path = "/".join(["", "-".join(parts), ""])  # /resumes-city-query/

        query_string = ""
        if params:
            query_string = self._encode_params(params)

        url = f"{self.BASE_URL}{path}"
        if query_string:
            url += f"?{query_string}"

        return url

    def _slugify(self, text: str) -> str:
        text = text.lower().strip()
        # Замінюємо пробіли на плюси для Work.ua
        text = text.replace(" ", "+")
        # Кодуємо кирилицю у правильний URL-формат
        return quote(text, safe="+")

    def _get_city_slug(self, city: str) -> str:
        if not city:
            return ""
        key = city.lower().strip()

        if key in self.CITY_SLUGS:
            return self.CITY_SLUGS[key]

        slug = self._slugify(key)
        slug = slug.replace("+", "-")
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug

    def _encode_params(self, params: Dict[str, Any]) -> str:
        parts = []
        for key in sorted(params.keys()):
            val = params[key]
            if val is None:
                continue

            val_str = ""
            if isinstance(val, list):
                str_vals = []
                for item in val:
                    if isinstance(item, tuple) or isinstance(item, list):
                        str_vals.append(f"{item[0]}-{item[1]}")
                    else:
                        str_vals.append(str(item))
                str_vals.sort()
                val_str = "+".join(str_vals)
            else:
                val_str = str(val)

            if val_str:
                parts.append(f"{key}={val_str}")

        return "&".join(parts)

    def _map_language_levels(self, levels: List[str]) -> List[int]:
        # Каскадний мапінг рівнів англійської для Work.ua
        level_cascade = {
            "beginner": [1, 2, 3, 4, 5, 6, 7],
            "elementary": [2, 3, 4, 5, 6, 7],
            "pre_intermediate": [3, 4, 5, 6, 7],
            "intermediate": [4, 5, 6, 7],
            "upper_intermediate": [5, 6, 7],
            "advanced": [6, 7],
            "fluent": [7],
        }

        target_ids = set()
        for lvl in levels:
            lvl_lower = lvl.lower()
            if lvl_lower in level_cascade:
                target_ids.update(level_cascade[lvl_lower])
        return list(target_ids)
