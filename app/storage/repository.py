import json
import logging
from pathlib import Path
from typing import Set, Union
import os

from app.parsing.models import ParsingResult

logger = logging.getLogger(__name__)

class JsonlRepository:
    """
    Файловый репозиторий на базе JSONL (New-line Delimited JSON).
    Обеспечивает:
    - Потоковую запись (Append-only).
    - Дедупликацию в памяти (In-memory Set).
    - Устойчивость к сбоям (Flush, Recovery).
    """

    def __init__(self, file_path: Union[str, Path]):
        self.path = Path(file_path)
        self._seen_ids: Set[str] = set()
        
        # Гарантируем, что папка существует
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # При старте загружаем уже обработанные ID
        self._load_processed_ids()

    def _load_processed_ids(self):
        """
        Читает файл построчно, извлекает resume_id и заполняет кэш.
        Игнорирует битые строки.
        """
        if not self.path.exists():
            return

        valid_count = 0
        corrupted_count = 0

        with open(self.path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # Нам не нужно парсить весь объект через Pydantic при старте,
                    # достаточно быстро достать ID из dict.
                    data = json.loads(line)
                    resume_id = (data.get("payload") or {}).get("resume_id")
                    if resume_id:
                        self._seen_ids.add(str(resume_id))
                        valid_count += 1
                    else:
                        url = data.get("url", "")
                        self._seen_ids.add("url:" + str(url))
                        valid_count += 1

                except json.JSONDecodeError:
                    # Это нормально при внезапном выключении питания на прошлой записи
                    logger.warning(f"Corrupted JSON at line {line_num} in {self.path}. Skipping.")
                    corrupted_count += 1
                except Exception as e:
                    logger.warning(f"Error reading line {line_num}: {e}")

        logger.info(f"Repository loaded: {valid_count} candidates ready. (Corrupted lines: {corrupted_count})")

    def exists(self, resume_id: str) -> bool:
        """Быстрая проверка наличия кандидата (O(1))."""
        return str(resume_id) in self._seen_ids

    def save_result(self, result: ParsingResult):
        """
        Атомарно дописывает результат парсинга в файл и обновляет кэш дедупликации.
        Дедуп-ключ:
        - если есть payload.resume_id -> используем его
        - иначе используем "url:" + result.url
        """
        # 1) Определяем ключ дедупликации
        dedup_key = None
        if result.payload is not None and hasattr(result.payload, "resume_id") and result.payload.resume_id:
            dedup_key = str(result.payload.resume_id)
        else:
            dedup_key = "url:" + str(result.url or "")

        # 2) Дедуп
        if dedup_key in self._seen_ids:
            return

        # 3) Сериализация и запись (пишем именно ParsingResult)
        json_str = result.model_dump_json()

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json_str + "\n")
            f.flush()
            os.fsync(f.fileno())

        # 4) Обновляем кэш
        self._seen_ids.add(dedup_key)
