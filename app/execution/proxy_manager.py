import random
from typing import Optional, Set
from app.config import settings

class ProxyManager:
    def __init__(self):
        # Загружаем список один раз при инициализации
        self.proxies = settings.get_proxy_list
        # Множество для временного хранения "плохих" прокси
        self._quarantined: Set[str] = set()
    
    def get_next_proxy(self) -> Optional[str]:
        """
        Возвращает URL прокси или None, если прокси не настроены 
        (режим прямой работы для локальной разработки).
        """
        if not self.proxies:
            return None  # Local/Direct mode
            
        # Фильтруем прокси, которые в карантине
        available = [p for p in self.proxies if p not in self._quarantined]
        
        if not available:
            # Если все прокси в карантине, сбрасываем его (Last Resort),
            # чтобы не останавливать работу полностью.
            self._quarantined.clear()
            available = self.proxies
            
        return random.choice(available)

    def quarantine_proxy(self, proxy_url: str):
        """Временно исключает прокси из ротации (до перезапуска процесса)"""
        if proxy_url:
            self._quarantined.add(proxy_url)

# Глобальный инстанс
proxy_manager = ProxyManager()