import json
from functools import lru_cache
from pathlib import Path
from typing import Any, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class ParserSettings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = BASE_DIR / "app" / "config"
    WORKUA_FILTERS_PATH: Path = CONFIG_DIR / "workua_filters_map.json"
    ROBOTAUA_FILTERS_PATH: Path = CONFIG_DIR / "robotaua_filters_map.json"

    PROXY_LIST_STR: str = ""
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_MIN_WAIT: float = 1.0
    RETRY_MAX_WAIT: float = 10.0
    RETRY_HTTP_CODES: List[int] = [429, 500, 502, 503, 504]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def get_proxy_list(self) -> List[str]:
        if not self.PROXY_LIST_STR:
            return []
        return [p.strip() for p in self.PROXY_LIST_STR.split(",") if p.strip()]

    def load_filters_map(self, source: str = "workua") -> dict[str, Any]:
        path = (
            self.WORKUA_FILTERS_PATH
            if source == "workua"
            else self.ROBOTAUA_FILTERS_PATH
        )
        if not path.exists():
            raise FileNotFoundError(f"Filters map for {source} not found at {path}")
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)


@lru_cache
def get_settings() -> ParserSettings:
    return ParserSettings()


settings = get_settings()
