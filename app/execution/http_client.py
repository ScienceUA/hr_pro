import asyncio
import random
import logging
import inspect
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.config.headers import get_headers

logger = logging.getLogger(__name__)

class HttpClientFactory:
    """
    Фабрика HTTP-клиентов с поддержкой Dependency Injection.
    Управляет жизненным циклом клиентов, лимитами concurrency и ротацией прокси.
    """

    def __init__(self, settings: Any, proxy_manager: Any):
        self.settings = settings
        self.proxy_manager = proxy_manager
        
        # Инициализация семафора.
        # ВАЖНО: Это лимит на уровне ПРОЦЕССА.
        # Глобальный Rate Limiting должен обеспечиваться инфраструктурой (Cloud Tasks).
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_CHUNKS)
        
        # Fail-Fast проверка совместимости httpx
        self._validate_library_capability()

    def _validate_library_capability(self):
        """Гарантирует, что httpx поддерживает нужный API (proxy=...)."""
        sig = inspect.signature(httpx.AsyncClient)
        if 'proxy' not in sig.parameters:
            raise RuntimeError(
                "CRITICAL: Installed httpx version does not support 'proxy' argument. "
                "Update dependencies to httpx>=0.27.0"
            )

    def _mask_proxy_url(self, url: str) -> str:
        """Безопасная маскировка пароля в URL."""
        if not url:
            return "Direct"
        try:
            parsed = urlparse(url)
            if parsed.password:
                # Реконструируем netloc безопасным способом
                safe_netloc = f"{parsed.username}:***@{parsed.hostname}"
                if parsed.port:
                    safe_netloc += f":{parsed.port}"
                parsed = parsed._replace(netloc=safe_netloc)
            return urlunparse(parsed)
        except Exception:
            return "Invalid-URL"

    async def _jitter(self):
        """Вносит случайную задержку для размытия нагрузки."""
        delay = random.uniform(self.settings.JITTER_MIN, self.settings.JITTER_MAX)
        await asyncio.sleep(delay)

    @asynccontextmanager
    async def client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """
        Создает контекст с настроенным клиентом.
        Ограничивает количество активных клиентов через семафор.
        """
        # Back-pressure: ожидание свободного слота.
        # Внимание: ожидающие корутины потребляют память, но тяжелый Client еще не создан.
        async with self._semaphore:
            
            # Jitter внутри семафора гарантирует, что мы замедляем именно активную обработку,
            # но "съедаем" часть пропускной способности ради распределения нагрузки.
            await self._jitter()
            
            # Получение конфигурации через внедренные зависимости
            proxy_url: Optional[str] = self.proxy_manager.get_next_proxy()
            headers = get_headers()
            
            timeout = httpx.Timeout(
                connect=self.settings.HTTP_TIMEOUT_CONNECT,
                read=self.settings.HTTP_TIMEOUT_READ,
                write=self.settings.HTTP_TIMEOUT_WRITE,
                pool=self.settings.HTTP_TIMEOUT_POOL,
            )
            
            limits = httpx.Limits(
                max_keepalive_connections=self.settings.MAX_CONCURRENT_CHUNKS,
                max_connections=self.settings.MAX_CONCURRENT_CHUNKS * 2
            )

            try:
                async with httpx.AsyncClient(
                    proxy=proxy_url,
                    headers=headers,
                    timeout=timeout,
                    limits=limits,
                    follow_redirects=True,
                    http2=True,
                    verify=True,
                ) as client:
                    yield client
            except Exception as e:
                # Безопасное логирование
                safe_proxy = self._mask_proxy_url(proxy_url or "")
                logger.error(f"HTTP Client Init Failed. Proxy: {safe_proxy}. Error class: {e.__class__.__name__}")
                raise