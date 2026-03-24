import asyncio
import time
from typing import Optional
from app.config.settings import Settings
from app.execution.http_client import HttpClientFactory

# --- Mocks ---
class MockProxyManager:
    def get_next_proxy(self) -> Optional[str]:
        return None

# Настраиваем лимит = 3 для скорости теста
# Jitter минимальный, чтобы не смазывать замеры очереди
test_settings = Settings(MAX_CONCURRENT_CHUNKS=3, JITTER_MIN=0.1, JITTER_MAX=0.2)
factory = HttpClientFactory(test_settings, MockProxyManager())

async def worker(idx, results):
    t_start = time.time()
    
    # Попытка захвата ресурса
    async with factory.client() as _:
        t_entry = time.time()
        wait_time = t_entry - t_start
        results.append((idx, wait_time))
        
        # Удержание ресурса (имитация работы)
        await asyncio.sleep(0.5)

async def main():
    print("--- Logic Test: Semaphore Latency ---")
    results = []
    # Запускаем 6 воркеров при лимите 3.
    # Ожидание: 
    # 3 войдут быстро (< 0.4s с учетом джиттера)
    # 3 будут ждать освобождения (> 0.5s, так как первые сидят 0.5s)
    tasks = [worker(i, results) for i in range(6)]
    await asyncio.gather(*tasks)
    
    # Анализ
    fast_entries = [t for i, t in results if t < 0.4]
    slow_entries = [t for i, t in results if t >= 0.5]
    
    print(f"Fast entries (immediate): {len(fast_entries)}")
    print(f"Slow entries (queued): {len(slow_entries)}")
    
    if len(fast_entries) == 3 and len(slow_entries) == 3:
        print("SUCCESS: Queueing works correctly.")
    else:
        print(f"FAILED: Unexpected distribution. Results: {results}")

if __name__ == "__main__":
    asyncio.run(main())