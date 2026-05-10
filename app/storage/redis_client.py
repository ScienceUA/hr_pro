import json
import logging
from typing import Any, Callable, Dict, Optional

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.config.settings import settings

logger = logging.getLogger(__name__)

TASK_TTL = settings.REDIS_TASK_TTL
PAYLOAD_TTL = settings.REDIS_PAYLOAD_TTL


class RedisUnavailableError(RuntimeError):
    """Raised when Redis is unavailable and local fallback is disabled."""


class RedisClient:
    def __init__(
        self,
        *,
        url: str | None = None,
        allow_in_memory_fallback: bool | None = None,
        redis_factory: Callable[..., Any] | None = None,
    ):
        self.url = url or settings.REDIS_URL
        self.allow_in_memory_fallback = (
            settings.ALLOW_IN_MEMORY_SESSION_FALLBACK
            if allow_in_memory_fallback is None
            else allow_in_memory_fallback
        )
        self._redis_factory = redis_factory or redis.from_url
        self._redis = None
        self._fallback_store = {}  # In-memory fallback for local dev without Redis
        logger.info(
            "RedisClient initialized with URL: %s, in-memory fallback: %s",
            self.url,
            self.allow_in_memory_fallback,
        )

    @property
    def redis(self):
        if self._redis is None:
            self._redis = self._redis_factory(self.url, decode_responses=True)
        return self._redis

    async def _safe_call(self, method_name: str, *args, **kwargs):
        """
        Attempt to call a redis method. Fallback to in-memory store if connection fails.
        """
        try:
            method = getattr(self.redis, method_name)
            return await method(*args, **kwargs)
        except Exception as e:
            if not self._is_connection_error(e):
                logger.error("Redis error in %s: %s", method_name, e)
                raise

            if not self.allow_in_memory_fallback:
                logger.error(
                    "Redis unavailable and in-memory session fallback is disabled. "
                    "APP_ENV=%s REDIS_URL=%s",
                    settings.APP_ENV,
                    self.url,
                )
                raise RedisUnavailableError(
                    "Redis is unavailable and in-memory session fallback is disabled"
                ) from e

            logger.warning(
                "Redis connection failed. Using explicitly enabled in-memory "
                "session fallback. Error: %s",
                e,
            )
            key = args[0]
            if method_name == "get":
                return self._fallback_store.get(key)
            if method_name == "set":
                self._fallback_store[key] = args[1]
                return True
            raise

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        err_str = str(exc)
        return (
            isinstance(exc, RedisError)
            or "ConnectionError" in err_str
            or "Connection refused" in err_str
            or "nodename nor servname provided" in err_str
            or "Error 8 connecting to" in err_str
        )

    async def get_task_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        data = await self._safe_call("get", f"task:{session_id}")
        if data:
            return json.loads(data)
        return None

    async def set_task_status(
        self, session_id: str, status_data: Dict[str, Any], expire: int = TASK_TTL
    ):
        await self._safe_call("set", f"task:{session_id}", json.dumps(status_data), ex=expire)
        logger.debug(f"Task status set for {session_id}")

    async def save_payload(self, session_id: str, payload_dict: Dict[str, Any], expire: int = PAYLOAD_TTL):
        await self._safe_call("set", f"payload:{session_id}", json.dumps(payload_dict), ex=expire)
        logger.info(f"Payload saved for session {session_id}")

    async def get_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        data = await self._safe_call("get", f"payload:{session_id}")
        if data:
            return json.loads(data)
        return None


redis_client = RedisClient()
