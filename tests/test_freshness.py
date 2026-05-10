import pytest
import httpx
from unittest.mock import patch, MagicMock

from parser_service.freshness_validator import FreshnessValidator

@pytest.mark.asyncio
async def test_is_fresh_valid_url():
    """Перевірка валідного URL (200 OK)."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = httpx.URL("https://work.ua/resumes/123456/")
        mock_get.return_value = mock_response

        is_fresh = await FreshnessValidator.is_fresh("https://work.ua/resumes/123456/")
        assert is_fresh is True

@pytest.mark.asyncio
async def test_is_fresh_404_url():
    """Перевірка URL, що повертає 404."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.url = httpx.URL("https://work.ua/resumes/123456/")
        mock_get.return_value = mock_response

        is_fresh = await FreshnessValidator.is_fresh("https://work.ua/resumes/123456/")
        assert is_fresh is False

@pytest.mark.asyncio
async def test_is_fresh_redirect_to_404():
    """Перевірка URL, що редіректить на сторінку 404."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = httpx.URL("https://work.ua/404-page")
        mock_get.return_value = mock_response

        is_fresh = await FreshnessValidator.is_fresh("https://work.ua/resumes/123456/")
        assert is_fresh is False

@pytest.mark.asyncio
async def test_is_fresh_network_error():
    """Перевірка обробки мережевої помилки."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("Network error")):
        is_fresh = await FreshnessValidator.is_fresh("https://work.ua/resumes/123456/")
        assert is_fresh is False

@pytest.mark.asyncio
async def test_is_fresh_empty_url():
    """Перевірка поведінки з порожнім URL."""
    is_fresh = await FreshnessValidator.is_fresh("")
    assert is_fresh is False


@pytest.mark.asyncio
async def test_is_fresh_expired_timestamp():
    """Перевірка застарілого таймстампу (більше 30 днів)."""
    from datetime import datetime, timedelta
    old_date = (datetime.utcnow() - timedelta(days=31)).isoformat()
    # HTTP could be 200, but the timestamp is too old
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = httpx.URL("https://work.ua/resumes/123")
        mock_get.return_value = mock_response

        is_fresh = await FreshnessValidator.is_fresh("https://work.ua/resumes/123", created_at=old_date)
        assert is_fresh is False


@pytest.mark.asyncio
async def test_is_fresh_valid_timestamp():
    """Перевірка свіжого таймстампу (менше 30 днів)."""
    from datetime import datetime, timedelta
    recent_date = (datetime.utcnow() - timedelta(days=1)).isoformat()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = httpx.URL("https://work.ua/resumes/123")
        mock_get.return_value = mock_response

        is_fresh = await FreshnessValidator.is_fresh("https://work.ua/resumes/123", created_at=recent_date)
        assert is_fresh is True
