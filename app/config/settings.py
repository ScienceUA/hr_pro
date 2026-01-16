import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Basic Info ---
    APP_NAME: str = "HR-Agent Pro Execution"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    GOOGLE_CLOUD_PROJECT: str = "local-project"
    
    # --- Paths ---
    # Было: BASE_DIR: Path = Path(__file__).resolve().parent.parent
    # Стало (3 раза parent):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = BASE_DIR / "config"
    WORKUA_FILTERS_PATH: Path = CONFIG_DIR / "workua_filters_map.json"

    # --- Proxy Configuration ---
    PROXY_LIST_STR: str = ""

    # --- HTTP Client Configuration ---
    MAX_CONCURRENT_CHUNKS: int = 5
    HTTP_TIMEOUT_CONNECT: float = 10.0
    HTTP_TIMEOUT_READ: float = 30.0
    HTTP_TIMEOUT_WRITE: float = 10.0
    HTTP_TIMEOUT_POOL: float = 5.0
    
    JITTER_MIN: float = 0.5
    JITTER_MAX: float = 1.5

    # --- Retry Policy Configuration ---
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_MIN_WAIT: float = 1.0
    RETRY_MAX_WAIT: float = 10.0
    
    # HTTP коды для ретрая. 
    # 408 убрали (это TimeoutException).
    # 400/401/403 сюда НЕ входят (это Domain/Permanent).
    RETRY_HTTP_CODES: List[int] = [429, 500, 502, 503, 504]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def load_filters_map(self) -> Dict[str, Any]:
        if not self.WORKUA_FILTERS_PATH.exists():
            raise FileNotFoundError(f"Filters map not found at {self.WORKUA_FILTERS_PATH}")
        with open(self.WORKUA_FILTERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def get_proxy_list(self) -> List[str]:
        if not self.PROXY_LIST_STR:
            return []
        return [p.strip() for p in self.PROXY_LIST_STR.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()