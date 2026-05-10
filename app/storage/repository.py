import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Set, Union

from google.cloud import storage

from app.models.parsed_resume import CoreParsedResume

logger = logging.getLogger(__name__)


class BaseRepository(ABC):
    @abstractmethod
    def exists(self, resume_id: str) -> bool:
        pass

    @abstractmethod
    def save_result(self, result: CoreParsedResume):
        pass

    @abstractmethod
    def save_analysis(self, analysis: dict):
        pass

    @abstractmethod
    def cleanup(self, session_id: str = None, dry_run: bool = False) -> int:
        """
        Cleans up storage. If session_id is provided, only cleans up that session.
        Returns the count of deleted items.
        """
        pass


class LocalStorage(BaseRepository):
    """
    Файловый репозиторий на базе JSONL (New-line Delimited JSON).
    """

    def __init__(self, file_path: Union[str, Path]):
        self.path = Path(file_path)
        self._seen_ids: Set[str] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load_processed_ids()

    def _load_processed_ids(self):
        if not self.path.exists():
            return
        valid_count, corrupted_count = 0, 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    resume_id = data.get("resume_id") or (
                        data.get("payload") or {}
                    ).get("resume_id")
                    if resume_id:
                        self._seen_ids.add(str(resume_id))
                    else:
                        self._seen_ids.add("url:" + str(data.get("url", "")))
                    valid_count += 1
                except json.JSONDecodeError:
                    logger.warning(f"Corrupted JSON at line {line_num} in {self.path}. Skipping.")
                    corrupted_count += 1
        logger.info(f"LocalStorage loaded: {valid_count} candidates. (Corrupted: {corrupted_count})")

    def exists(self, resume_id: str) -> bool:
        return str(resume_id) in self._seen_ids

    def save_result(self, result: CoreParsedResume):
        dedup_key = (
            str(result.resume_id) if result.resume_id else "url:" + str(result.url or "")
        )
        if dedup_key in self._seen_ids:
            return

        json_str = result.model_dump_json()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json_str + "\n")
            f.flush()
            os.fsync(f.fileno())

        self._seen_ids.add(dedup_key)
    def save_analysis(self, analysis: dict):
        analysis_path = self.path.parent / "analyses.jsonl"
        with open(analysis_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(analysis, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def cleanup(self, session_id: str = None, dry_run: bool = False) -> int:
        out_dir = self.path.parent
        if not out_dir.exists():
            return 0

        patterns = [
            "result_*.jsonl",
            "result_llm_*.json",
            "result_llm_*.md",
            "candidates_*.jsonl",
        ]
        
        if session_id:
            patterns = [p.replace("*", f"*{session_id}*") for p in patterns]

        deleted_count = 0
        for pattern in patterns:
            for filepath in out_dir.glob(pattern):
                try:
                    if not dry_run:
                        filepath.unlink()
                    logger.info(f"{'Would delete' if dry_run else 'Deleted'}: {filepath.name}")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {filepath.name}: {e}")
        return deleted_count


class GCSStorage(BaseRepository):
    """
    Хранилище на базе Google Cloud Storage.
    Каждый результат парсинга сохраняется в отдельный JSON-файл в указанном bucket.
    """

    def __init__(self, bucket_name: str, prefix: str = "candidates/"):
        self.bucket_name = bucket_name
        self.prefix = prefix
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)

    def _get_blob_name(self, dedup_key: str) -> str:
        safe_key = dedup_key.replace("/", "_").replace(":", "_")
        return f"{self.prefix}{safe_key}.json"

    def exists(self, resume_id: str) -> bool:
        blob_name = self._get_blob_name(str(resume_id))
        blob = self.bucket.blob(blob_name)
        return blob.exists()

    def save_result(self, result: CoreParsedResume):
        dedup_key = (
            str(result.resume_id) if result.resume_id else "url:" + str(result.url or "")
        )
        blob_name = self._get_blob_name(dedup_key)
        blob = self.bucket.blob(blob_name)

        if blob.exists():
            return

        json_str = result.model_dump_json()
        blob.upload_from_string(json_str, content_type="application/json")
    def save_analysis(self, analysis: dict):
        url = analysis.get("candidate_url", "unknown")
        safe_key = str(url).replace("/", "_").replace(":", "_")
        blob_name = f"analyses/{safe_key}.json"
        blob = self.bucket.blob(blob_name)
        
        if blob.exists():
            return

        json_str = json.dumps(analysis, ensure_ascii=False)
        blob.upload_from_string(json_str, content_type="application/json")

    def cleanup(self, session_id: str = None, dry_run: bool = False) -> int:
        # For GCS, we might want to cleanup a specific session prefix or the entire prefix
        # If session_id is provided, we look for blobs containing it in their name or prefix
        # Standard GCS session storage usually has its own prefix.
        
        search_prefix = self.prefix
        if session_id:
            # This is a bit simplified, usually you'd have a directory structure
            search_prefix = f"sessions/{session_id}/"
        
        blobs = self.bucket.list_blobs(prefix=search_prefix)
        deleted_count = 0
        for blob in blobs:
            if not dry_run:
                blob.delete()
            logger.info(f"{'Would delete' if dry_run else 'Deleted'} blob: {blob.name}")
            deleted_count += 1
        return deleted_count


from app.config.paths import get_data_dir

def get_repository() -> BaseRepository:
    """
    Фабрика репозитория. Возвращает LocalStorage или GCSStorage
    в зависимости от переменной окружения USE_GCS.
    """
    use_gcs = os.environ.get("USE_GCS", "false").lower() == "true"

    if use_gcs:
        bucket_name = os.environ.get("GCS_BUCKET_NAME", "hr-pro-data-lake")
        return GCSStorage(bucket_name=bucket_name)
    else:
        local_path = get_data_dir() / "candidates.jsonl"
        return LocalStorage(file_path=local_path)
