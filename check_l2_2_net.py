import asyncio
from app.config.settings import settings
from app.execution.http_client import HttpClientFactory

# --- Mocks for DI ---
class ForceDirectManager:
    def get_next_proxy(self): return None

class ForceProxyManager:
    def __init__(self, proxy_str): self.proxy = proxy_str
    def get_next_proxy(self): return self.proxy

async def get_ip(factory, label):
    """Делает запрос к ipify и возвращает IP"""
    url = "https://api.ipify.org?format=json"
    try:
        async with factory.client() as client:
            resp = await client.get(url)
            ip = resp.json().get("ip")
            print(f"[{label}] IP: {ip}")
            return ip
    except Exception as e:
        print(f"[{label}] FAILED: {e}")
        return None

async def main():
    print("--- Network Smoke Test (DI-based) ---")
    
    # 1. Test Direct Mode
    # Мы подставляем ForceDirectManager, чтобы гарантировать отсутствие прокси
    print("\n1. Testing FORCE DIRECT:")
    direct_factory = HttpClientFactory(settings, ForceDirectManager())
    ip_direct = await get_ip(direct_factory, "DIRECT")
    
    # 2. Test Proxy Mode (только если прокси заданы в .env)
    proxies = settings.get_proxy_list
    if proxies:
        print(f"\n2. Testing FORCE PROXY ({proxies[0]}):")
        # Мы берем первый прокси из конфига и принудительно скармливаем его фабрике
        proxy_factory = HttpClientFactory(settings, ForceProxyManager(proxies[0]))
        ip_proxy = await get_ip(proxy_factory, "PROXY")
        
        # Сравнение
        if ip_direct and ip_proxy:
            if ip_direct != ip_proxy:
                print("SUCCESS: IPs are different (Proxy works).")
            else:
                print("WARNING: IPs match. (Transparent proxy or Direct used?)")
    else:
        print("\n2. Proxy check SKIPPED (No proxies in .env)")

if __name__ == "__main__":
    asyncio.run(main())