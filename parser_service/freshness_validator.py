from datetime import datetime, timedelta
import httpx
import logging
import os

logger = logging.getLogger(__name__)


class FreshnessValidator:
    """
    Validator to check if a parsed resume URL is still active/fresh.
    This prevents the system from re-evaluating or providing broken links.
    """

    @staticmethod
    async def is_fresh(url: str, created_at: str = None) -> bool:
        """
        Перевіряє, чи активне резюме.
        Повертає False, якщо отримано 404, редірект на сторінку помилки,
        або якщо запис у кеші застарів за часом.
        """
        # 1. Time-based validation (TTL)
        if created_at:
            try:
                # Expecting ISO format: 2026-05-01T12:00:00.000000
                created_dt = datetime.fromisoformat(created_at)
                # Default expiration: 30 days
                expiration_days = int(os.getenv("CACHE_EXPIRATION_DAYS", "30"))
                if datetime.utcnow() - created_dt > timedelta(days=expiration_days):
                    logger.info(f"Cache entry is too old ({created_at}): {url}")
                    return False
            except ValueError:
                logger.warning(f"Invalid created_at format: {created_at}. Skipping TTL check.")

        # 2. HTTP-based validation
        if not url:
            return False

        try:
            # Використовуємо GET, оскільки деякі сайти можуть блокувати HEAD або повертати інший статус
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }
            async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
                response = await client.get(url, timeout=10.0)

                if response.status_code != 200:
                    logger.info(f"URL is not fresh (status {response.status_code}): {url}")
                    return False

                # Можна додати специфічні перевірки для Work.ua / Robota.ua
                if "404" in str(response.url) or "not-found" in str(response.url):
                    logger.info(f"URL is not fresh (redirected to 404): {url}")
                    return False

                return True

        except httpx.RequestError as e:
            logger.warning(f"Error checking freshness for {url}: {e}")
            return False
