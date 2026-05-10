import asyncio
import logging
import httpx
import random
from typing import Dict, Any, List, Optional, Tuple

from parser_service.config.settings import settings
from parser_service.execution.executor import RequestExecutor
from parser_service.storage.repository import BaseRepository

# --- ІМПОРТИ ПАРСЕРА ---
from parser_service.parsing.resume_parsers import RobotaUaResumeParser
from parser_service.parsing.models import DataQuality, ParsingResult

logger = logging.getLogger(__name__)


class RobotaUaAdapter:
    # Системні константи для Anti-bot Jitter (в секундах)
    JITTER_MIN = 1.5
    JITTER_MAX = 2.5
    SEARCH_API_URL = "https://employer-api.robota.ua/cvdb/resumes"
    RESUME_BASE_URL = "https://robota.ua/candidates/"

    # --- GRAPHQL ЗАПИТ ДЛЯ ОТРИМАННЯ РЕЗЮМЕ ---
    GRAPHQL_QUERY = """query getCvDbResume($id: ID!) {
  employerResume(id: $id) {
    ...CvDbResume
    __typename
  }
}

fragment CvDbResume on EmployerResume {
  id title addedAt updatedAt diiaCertificate skills isAnonymous isUserOnline isActivelySearchingForNewJob isDislikedByCurrentCompany isSelectedByCurrentCompany  # noqa: E501
  owner { id __typename }
  city { id name __typename }
  districts { id name __typename }
  schedules { id __typename }
  salary { amount currency __typename }
  filling { type { id __typename } __typename }
  educations { id importSource institutionTitle level location speciality yearOfGraduation __typename }  # noqa: E501
  additionalEducations { id city { id name __typename } description location title yearOfGraduation __typename }  # noqa: E501
  experiences { id description branch { id name __typename } companyName position startWork endWork __typename }  # noqa: E501
  languageSkills { certificate isCanPassInterview language { id name __typename } level { id name __typename } __typename }  # noqa: E501
  additionals { id description name __typename }
  subrubrics { id name rubric { id name __typename } __typename }
  relocationCities { id name __typename }
  chat { id unreadMessagesCount __typename }
  personal { firstName fatherName surName birthDate age gender photoUrl __typename }  # noqa: E501
  contacts { ...CvDbResumeContactsOpened ...CvDbResumeContactsClosed __typename }  # noqa: E501
  notes { id description createdAt author { id fullName __typename } __typename }  # noqa: E501
  file { ...CvDbResumeFileOpened ...CvDbResumeFileClosed __typename }
  __typename
}

fragment CvDbResumeContactsOpened on EmployerResumeContactsOpened {
  openedAt openedBy { ... on Employee { id fullName __typename } ... on EmployerResumeContactsOpenedBySystem { isSystem __typename } __typename }  # noqa: E501
  contacts { email phone { value isConfirmed __typename } phones { value __typename } portfolios socials { value type __typename } isPhoneHidden __typename }  # noqa: E501
  __typename
}

fragment CvDbResumeContactsClosed on EmployerResumeContactsClosed {
  hasPhone isConfirmed isPhoneHidden __typename
}

fragment CvDbResumeFileOpened on EmployerResumeFileOpened {
  summary data __typename
}

fragment CvDbResumeFileClosed on EmployerResumeFileClosed {
  summary data mode __typename
}"""

    def __init__(self, executor: RequestExecutor, repository: BaseRepository):
        self.name = "robotaua"
        self.executor = executor
        self.repository = repository
        # Завантажуємо маппінг
        self.config = settings.load_filters_map("robotaua")

    async def _post_json(self, url: str, json_data: dict) -> dict:
        """Асинхронна обгортка для безпечного виконання POST-запитів із заголовками"""  # noqa: E501
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",  # noqa: E501
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-requested-with": "XMLHttpRequest",
            "Referer": "https://robota.ua/",
        }

        async def _do_fetch():
            async with httpx.AsyncClient(headers=headers) as client:
                response = await self.executor.execute(
                    lambda: client.post(url, json=json_data, timeout=30.0)
                )
                # Якщо сервер поверне помилку, ми побачимо її текст у консолі
                if response.status_code != 200:
                    logger.error(
                        f"[{self.name}] Server response body: {response.text}"
                    )
                return response.json()

        try:
            return await _do_fetch()
        except Exception as e:
            logger.error(f"[{self.name}] Мережева або Resilience помилка: {e}")
            raise RuntimeError(f"Не вдалося отримати дані з API: {e}")

    async def _fetch_html(self, url: str) -> str:
        """Асинхронна обгортка для виконання GET-запитів із заголовками"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # noqa: E501
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",  # noqa: E501
            "Accept-Language": "uk,en-US;q=0.9,en;q=0.8",
        }

        async def _do_fetch():
            async with httpx.AsyncClient(headers=headers) as client:
                response = await self.executor.execute(
                    lambda: client.get(
                        url, timeout=15.0, follow_redirects=True
                    )
                )
                return response.text

        try:
            return await _do_fetch()
        except Exception as e:
            logger.error(f"[{self.name}] Мережева помилка GET: {e}")
            return ""

    async def preview(self, search_payload: Dict[str, Any]) -> Dict[str, Any]:
        query = search_payload.get("query", "")
        city_slug = search_payload.get("city", "ukraine")

        # Формуємо базовий Payload за структурою вашого cURL
        payload = {
            "page": 0,
            "period": self._map_period(search_payload.get("days")),
            "sort": "UpdateDate",
            "searchType": "default",
            "keyWords": query,
            "cityId": self._map_city(city_slug),
            "ukrainian": False,
            "showCvWithoutSalary": True,
            "searchContext": "Main",
            "experienceIds": self._map_experience(
                search_payload.get("experience_label")
            ),
            "rubrics": self._map_rubrics(search_payload.get("category")),
            "scheduleIds": self._map_employment(
                search_payload.get("employment")
            ),  # Новий фільтр
            "educationIds": self._map_education(
                search_payload.get("education")
            ),  # Новий фільтр
            "languageIds": self._map_language_levels(
                search_payload.get("languages", [])
            ),  # <--- ДОДАНО МОВИ
            "gender": search_payload.get("gender", ""),
            "age": {
                "from": search_payload.get("age_from"),
                "to": search_payload.get("age_to"),
            },
            "salary": {
                "from": search_payload.get("salary_min"),
                "to": search_payload.get("salary_max"),
            },
            "withPhoto": bool(search_payload.get("with_photo", False)),
            "hasFile": bool(search_payload.get("with_file", False)),
            "onlyDisabled": bool(search_payload.get("only_disabled", False)),
            "onlyStudents": bool(search_payload.get("only_students", False)),
        }

        logger.debug("[%s] API payload: %s", self.name, payload)

        logger.info(
            f"[{self.name}] 📡 API Request: '{query}' (City ID: {payload['cityId']}, Period: {payload['period']})"  # noqa: E501
        )

        try:
            response_json = await self._post_json(
                self.SEARCH_API_URL, json_data=payload
            )
            total = response_json.get("total", 0)
            documents = response_json.get("documents") or []

            # Формуємо URL для подальшого збору
            urls = [
                f"{self.RESUME_BASE_URL}{doc.get('resumeId')}"
                for doc in documents
                if doc.get("resumeId")
            ]
            return {"total_found": total, "urls": urls}
        except Exception as e:
            logger.error(f"[{self.name}] Preview failed: {e}")
            raise RuntimeError(f"Robota.ua API Error: {e}")

    def _map_city(self, slug: str) -> int:
        """Шукає ID міста у списку 'cities'."""
        cities = self.config.get("cities", [])
        for city in cities:
            if city.get("slug") == slug:
                return int(city.get("id", 0))
        return 0

    def _map_period(self, days: Optional[int]) -> str:
        """Маппінг до найближчого доступного періоду на сайті"""
        if not days:
            return "All"

        # (Дні, назва для API)
        buckets = [
            (1, "Day"),
            (3, "ThreeDays"),
            (7, "Week"),
            (30, "Month"),
            (90, "ThreeMonths"),
            (365, "Year"),
        ]
        if days > 365:
            return "All"
        # Знаходимо найближчий bucket (ваше правило про 6 днів -> Week)
        return min(buckets, key=lambda x: abs(x[0] - days))[1]

    def _map_experience(self, exp_label: Optional[str]) -> List[str]:
        if not exp_label:
            return []
        exp_list = self.config.get("candidate_filters", {}).get(
            "experience", []
        )
        cascade_map = {
            "no_experience": ["0", "1", "2", "3", "4", "5"],
            "under_1_year": ["1", "2", "3", "4", "5"],
            "1-2_years": ["2", "3", "4", "5"],
            "2-5_years": ["3", "4", "5"],
            "5-10_years": ["4", "5"],
            "more_10_years": ["5"],
        }

        target_ids = cascade_map.get(exp_label, [])
        result = []
        for item in exp_list:
            if str(item.get("id")) in target_ids:
                result.append(str(item.get("id")))
        return result

    def _map_rubrics(self, category_label: Optional[str]) -> List[str]:
        """Шукає parent_id рубрики (1, 3 тощо) у списку 'categories'."""
        if not category_label:
            return []
        categories = self.config.get("categories", [])
        for cat in categories:
            # Шукаємо збіг у назві категорії (напр. "IT" містить "it")
            if category_label.lower() in cat.get("name_ua", "").lower():
                return [str(cat.get("parent_id"))]
        return []

    def _map_employment(self, label: Optional[str]) -> List[str]:
        if not label:
            return []
        emp_list = self.config.get("candidate_filters", {}).get(
            "employment", []
        )
        canonical_map = {
            "full_time": "повна зайнятість",
            "part_time": "неповна зайнятість",
            "remote": "віддалена робота",
            "project": "проектна робота",
            "shift": "позмінна робота",
            "internship": "стажування / практика",
            "seasonal": "сезонна / тимчасова робота",
        }
        label_ua = canonical_map.get(label, label).lower()
        for item in emp_list:
            if label_ua == item.get("name_ua", "").lower():
                return [str(item.get("id"))]
        return []

    def _map_education(self, label: Optional[str]) -> List[str]:
        if not label:
            return []
        edu_list = self.config.get("candidate_filters", {}).get(
            "education", []
        )

        # Каскадний мапінг: якщо вимога "середня", то підходять і всі рівні
        # вище
        cascade_map = {
            "secondary": [
                "середня",
                "середньо-спеціальна",
                "незакінчена вища",
                "вища",
            ],
            "secondary_special": [
                "середньо-спеціальна",
                "незакінчена вища",
                "вища",
            ],
            "incomplete_higher": ["незакінчена вища", "вища"],
            "higher": ["вища"],
        }

        target_names = cascade_map.get(label, [label.lower()])
        result = []
        for item in edu_list:
            if item.get("name_ua", "").lower() in target_names:
                result.append(str(item.get("id")))
        return result

    def _map_language_levels(self, levels: List[str]) -> List[str]:
        # Каскадний мапінг рівнів мови для Robota.ua (рядкові ID)
        level_cascade = {
            "beginner": ["1", "2", "3", "4", "5", "6", "7"],
            "elementary": ["2", "3", "4", "5", "6", "7"],
            "pre_intermediate": ["3", "4", "5", "6", "7"],
            "intermediate": ["4", "5", "6", "7"],
            "upper_intermediate": ["5", "6", "7"],
            "advanced": ["6", "7"],
            "fluent": ["7"],
        }

        target_ids = set()
        for lvl in levels:
            lvl_lower = lvl.lower()
            if lvl_lower in level_cascade:
                target_ids.update(level_cascade[lvl_lower])
        return list(target_ids)

    async def _fetch_graphql(self, resume_id: str) -> dict:
        """Виконує POST запит до GraphQL API Robota.ua для отримання конкретного резюме"""  # noqa: E501
        url = "https://dracula.robota.ua/?q=getCvDbResume"
        payload = {
            "operationName": "getCvDbResume",
            "variables": {"id": resume_id},
            "query": self.GRAPHQL_QUERY,
        }
        # Використовуємо вже існуючий у вас метод _post_json
        return await self._post_json(url, json_data=payload)

    async def run_from_urls(self, urls: List[str]) -> Tuple[Dict[str, Any], List[ParsingResult]]:
        """Phase 2: Завантаження резюме через GraphQL та парсинг"""
        stats = {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None}
        results = []
        if not urls:
            return stats, results

        for url in urls:
            resume_id = [p for p in url.split("/") if p.isdigit()]
            if not resume_id:
                continue
            res_id = resume_id[-1]

            # Затримка для імітації поведінки людини (Jitter)
            await asyncio.sleep(
                random.uniform(self.JITTER_MIN, self.JITTER_MAX)
            )

            try:
                # Звертаємося до GraphQL API
                json_data = await self._fetch_graphql(res_id)
                if not json_data or "data" not in json_data:
                    logger.warning(
                        f"[{self.name}] Порожня або помилкова відповідь API: {url}"  # noqa: E501
                    )
                    stats["errors"] += 1
                    continue
            except Exception as e:
                logger.error(
                    f"[{self.name}] Помилка GraphQL API для {url}: {e}"
                )
                stats["errors"] += 1
                continue

            # Викликаємо наш новий парсер
            resume_parser = RobotaUaResumeParser(json_data, url)
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
                candidate_title = (
                    getattr(result.payload, "title", "Без посади")
                    if result.payload
                    else "Unknown"
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
