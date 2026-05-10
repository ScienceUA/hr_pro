import pytest
from redis.exceptions import ConnectionError

from app.storage.redis_client import RedisClient, RedisUnavailableError


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, **kwargs):
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)


class UnavailableRedis:
    async def set(self, key, value, **kwargs):
        raise ConnectionError("Connection refused")

    async def get(self, key):
        raise ConnectionError("Connection refused")


@pytest.mark.asyncio
async def test_redis_client_uses_redis_when_available():
    fake = FakeRedis()
    client = RedisClient(
        url="redis://test",
        allow_in_memory_fallback=False,
        redis_factory=lambda *args, **kwargs: fake,
    )

    await client.save_payload("session-1", {"query": "python"})
    await client.set_task_status("session-1", {"status": "pending"})

    assert await client.get_payload("session-1") == {"query": "python"}
    assert await client.get_task_status("session-1") == {"status": "pending"}


@pytest.mark.asyncio
async def test_redis_client_uses_in_memory_fallback_only_when_allowed():
    client = RedisClient(
        url="redis://unavailable",
        allow_in_memory_fallback=True,
        redis_factory=lambda *args, **kwargs: UnavailableRedis(),
    )

    await client.save_payload("session-1", {"query": "python"})
    await client.set_task_status("session-1", {"status": "pending"})

    assert await client.get_payload("session-1") == {"query": "python"}
    assert await client.get_task_status("session-1") == {"status": "pending"}


@pytest.mark.asyncio
async def test_redis_client_raises_when_unavailable_and_fallback_forbidden():
    client = RedisClient(
        url="redis://unavailable",
        allow_in_memory_fallback=False,
        redis_factory=lambda *args, **kwargs: UnavailableRedis(),
    )

    with pytest.raises(RedisUnavailableError):
        await client.save_payload("session-1", {"query": "python"})
