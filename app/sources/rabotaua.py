import logging
from typing import Dict, Any, List, Optional # Додано Optional
from app.transport.fetcher import SmartFetcher
from app.storage.repository import JsonlRepository
from app.config.settings import settings

logger = logging.getLogger(__name__)

class RabotaUaAdapter:
    SEARCH_API_URL = "https://employer-api.robota.ua/cvdb/resumes"
    RESUME_BASE_URL = "https://robota.ua/candidates/"

    def __init__(self, fetcher: SmartFetcher, repository: JsonlRepository):
        self.name = "rabotaua"
        self.fetcher = fetcher
        self.repository = repository
        # Завантажуємо маппінг
        self.config = settings.load_filters_map("rabotaua")

    def preview(self, search_payload: Dict[str, Any]) -> Dict[str, Any]:
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
            "ukrainian": True,
            "showCvWithoutSalary": True,
            "searchContext": "Main",
            "experienceIds": self._map_experience(search_payload.get("experience_label")),
            "rubrics": self._map_rubrics(search_payload.get("category")),
            "scheduleIds": self._map_employment(search_payload.get("employment")), # Новий фільтр
            "educationIds": self._map_education(search_payload.get("education")),   # Новий фільтр
            "gender": search_payload.get("gender", ""), 
            "age": {"from": search_payload.get("age_from"), "to": search_payload.get("age_to")},
            "salary": {"from": search_payload.get("salary_min"), "to": search_payload.get("salary_max")},
            "hasPhoto": bool(search_payload.get("with_photo", False)),
            "hasFile": bool(search_payload.get("with_file", False)),
            "onlyDisabled": bool(search_payload.get("only_disabled", False)),
            "onlyStudents": bool(search_payload.get("only_students", False))
        }

        logger.info(f"[{self.name}] 📡 API Request: '{query}' (City ID: {payload['cityId']}, Period: {payload['period']})")
        
        try:
            response_json = self.fetcher.post_json(self.SEARCH_API_URL, json=payload)
            total = response_json.get("total", 0)
            documents = response_json.get("documents") or []
            
            # Формуємо URL для подальшого збору
            urls = [f"{self.RESUME_BASE_URL}{doc.get('resumeId')}" for doc in documents if doc.get("resumeId")]
            return {"total_found": total, "urls": urls}
        except Exception as e:
            logger.error(f"[{self.name}] Preview failed: {e}")
            raise RuntimeError(f"Rabota.ua API Error: {e}")

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
            return "ThreeMonths"
        
        # (Дні, назва для API)
        buckets = [
            (1, "Today"),
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
        """Шукає ID досвіду (0-5) у списку 'experience'."""
        if not exp_label: return []
        exp_list = self.config.get("experience", []) # Змінено з candidate_filters
        for item in exp_list:
            if item.get("id") == exp_label or exp_label in item.get("name_ua", "").lower():
                return [str(item.get("id"))]
        return []

    def _map_rubrics(self, category_label: Optional[str]) -> List[str]:
        """Шукає parent_id рубрики (1, 3 тощо) у списку 'categories'."""
        if not category_label: return []
        categories = self.config.get("categories", [])
        for cat in categories:
            # Шукаємо збіг у назві категорії (напр. "IT" містить "it")
            if category_label.lower() in cat.get("name_ua", "").lower():
                return [str(cat.get("parent_id"))]
        return []

    def _map_employment(self, label: Optional[str]) -> List[str]:
        """Маппінг типу зайнятості (scheduleIds: 1, 4, 6 тощо)."""
        if not label: return []
        emp_list = self.config.get("employment", [])
        for item in emp_list:
            if item.get("slug") == label or label in item.get("name_ua", "").lower():
                return [str(item.get("id"))]
        return []

    def _map_education(self, label: Optional[str]) -> List[str]:
        """Маппінг рівня освіти (educationIds: 1, 2, 3 тощо)."""
        if not label: return []
        edu_list = self.config.get("education", [])
        for item in edu_list:
            if label in item.get("name_ua", "").lower():
                return [str(item.get("id"))]
        return []
        
    def run_from_urls(self, urls: List[str]) -> Dict[str, Any]:
        # Це Phase 2 (Crawl), буде реалізовано в наступному кроці
        return {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None}