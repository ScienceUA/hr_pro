import asyncio
import httpx
from unittest.mock import AsyncMock
from dataclasses import dataclass, field
from typing import List

from app.execution.executor import RequestExecutor
from app.core.exceptions import (
    ProxyBanError, 
    TransientError, 
    PermanentTransportError,
    DomainError
)

# --- Mocks ---
@dataclass
class MockSettings:
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_MIN_WAIT: float = 0.01 
    RETRY_MAX_WAIT: float = 0.05
    RETRY_HTTP_CODES: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])

# Helper для создания response, совместимого с raise_for_status
def make_response(status_code: int):
    req = httpx.Request("GET", "https://example.com")
    return httpx.Response(status_code, request=req)

async def test_transient_retry_flow():
    print("\n--- Test 1: Transient Error (500) -> Retry ---")
    settings = MockSettings()
    executor = RequestExecutor(settings)
    
    mock_func = AsyncMock()
    # 500 (Retry) -> 500 (Retry) -> 200 (Success)
    mock_func.side_effect = [
        make_response(500),
        make_response(500),
        make_response(200)
    ]
    
    resp = await executor.execute(mock_func)
    
    # Проверка: Должно быть ровно 3 вызова (attempts)
    print(f"Call count: {mock_func.call_count}")
    
    if mock_func.call_count == 3 and resp.status_code == 200:
        print("SUCCESS: 3 attempts made, eventually succeeded.")
    else:
        print(f"FAILED: Expected 3 calls, got {mock_func.call_count}")

async def test_proxy_ban_fail_fast():
    print("\n--- Test 2: Proxy Ban (403) -> Fail Fast (Permanent) ---")
    settings = MockSettings()
    executor = RequestExecutor(settings)
    
    mock_func = AsyncMock()
    # 403 должно вызвать ProxyBanError
    mock_func.return_value = make_response(403)
    
    try:
        await executor.execute(mock_func)
        print("FAILED: Should have raised ProxyBanError")
    except ProxyBanError:
        print(f"SUCCESS: Caught ProxyBanError. Call count: {mock_func.call_count}")
        if mock_func.call_count == 1:
            print("Verified: Strictly 1 attempt (No retry on 403).")
        else:
            print(f"FAILED: Executed {mock_func.call_count} times! Should be 1.")

async def test_dead_proxy_fail_fast():
    print("\n--- Test 3: Dead Proxy (ConnectError) -> Fail Fast ---")
    settings = MockSettings()
    executor = RequestExecutor(settings)
    
    mock_func = AsyncMock()
    # ConnectError -> PermanentTransportError
    mock_func.side_effect = httpx.ConnectError("Proxy unreachable", request=httpx.Request("GET", "x"))
    
    try:
        await executor.execute(mock_func)
        print("FAILED: Should have raised PermanentTransportError")
    except PermanentTransportError:
        print(f"SUCCESS: Caught PermanentTransportError. Call count: {mock_func.call_count}")
        if mock_func.call_count == 1:
            print("Verified: Strictly 1 attempt (No retry on dead proxy).")
        else:
            print(f"FAILED: Retried on dead proxy!")

async def test_network_glitch_retry():
    print("\n--- Test 4: Network Glitch (RequestError) -> Retry ---")
    settings = MockSettings()
    executor = RequestExecutor(settings)
    
    mock_func = AsyncMock()
    # Обычная сетевая ошибка (не ConnectError/ProxyError) -> Retry
    # Сценарий: Glitch -> Glitch -> Success
    mock_func.side_effect = [
        httpx.RequestError("DNS glitch", request=httpx.Request("GET", "x")),
        httpx.RequestError("Connection reset", request=httpx.Request("GET", "x")),
        make_response(200)
    ]
    
    resp = await executor.execute(mock_func)
    
    print(f"Call count: {mock_func.call_count}")
    if mock_func.call_count == 3 and resp.status_code == 200:
        print("SUCCESS: Network glitch retried 3 times.")
    else:
        print(f"FAILED: Expected 3 calls, got {mock_func.call_count}")

async def main():
    await test_transient_retry_flow()
    await test_proxy_ban_fail_fast()
    await test_dead_proxy_fail_fast()
    await test_network_glitch_retry()

if __name__ == "__main__":
    asyncio.run(main())