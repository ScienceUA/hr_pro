import logging
import httpx
from typing import Callable, Awaitable, Any, List
from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from app.core.exceptions import (
    TransportError,
    TransientError,
    PermanentTransportError,
    ProxyBanError,
    DomainError,
    AuthError
)

logger = logging.getLogger(__name__)

def _classify_httpx_error(e: Exception, retry_codes: List[int]) -> Exception:
    """
    Классификатор ошибок. Определяет стратегию Retry vs Fail Fast.
    """
    # 1. Ошибки статуса (ответ получен)
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        
        # 403 -> Сигнал "Смени прокси/IP" (Permanent)
        if status == 403:
            return ProxyBanError(f"HTTP 403 Forbidden: {e}")

        # 401 -> Auth Error (Domain)
        if status == 401:
            return AuthError(status, str(e))
        
        # 400 -> Bad Request (Domain, например кривой url/headers)
        if status == 400:
            return DomainError(status, f"Bad Request: {e}")

        # Transient Codes (429, 5xx) -> Retry
        if status in retry_codes:
            return TransientError(f"HTTP {status} - Transient")
            
        # 404, 410, etc -> Domain Error
        return DomainError(status, str(e))

    # 2. Ошибки таймаута -> Retry (Transient)
    # ReadTimeout может случиться и на живом прокси.
    if isinstance(e, httpx.TimeoutException):
        return TransientError(f"Timeout: {e}")

    # 3. Ошибки подключения (ConnectError, ProxyError) -> Permanent
    # Поскольку Executor работает с фиксированным клиентом (и фиксированным прокси),
    # ретраить ConnectError бесполезно - прокси не оживет мгновенно.
    # Мы падаем, чтобы Service Layer взял новый прокси.
    if isinstance(e, (httpx.ConnectError, httpx.ProxyError)):
        return PermanentTransportError(f"Connection Failed: {e}")

    # 4. Прочие сетевые ошибки (ProtocolError, etc) -> Попробуем ретрай (Transient)
    # Иногда бывают случайные сбросы соединения.
    if isinstance(e, httpx.RequestError):
        return TransientError(f"Network Glitch: {e}")
    
    return TransportError(f"Unknown: {e}")


class RequestExecutor:
    def __init__(self, settings: Any):
        self.settings = settings

    async def execute(self, request_func: Callable[[], Awaitable[httpx.Response]]) -> httpx.Response:
        """
        Выполняет запрос с политикой Resilience.
        """
        retrier = AsyncRetrying(
            retry=retry_if_exception_type(TransientError),
            stop=stop_after_attempt(self.settings.RETRY_MAX_ATTEMPTS),
            wait=wait_random_exponential(
                multiplier=self.settings.RETRY_MIN_WAIT, 
                max=self.settings.RETRY_MAX_WAIT
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )

        try:
            async for attempt in retrier:
                with attempt:
                    try:
                        response = await request_func()
                        response.raise_for_status()
                        return response
                    except Exception as e:
                        # Классификация
                        raise _classify_httpx_error(e, self.settings.RETRY_HTTP_CODES)
                        
        except Exception as e:
            # Исключение уходит в Service Layer
            raise e