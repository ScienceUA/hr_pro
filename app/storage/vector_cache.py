import json
import hashlib
import logging
from datetime import datetime
from typing import Any

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

from app.config.paths import get_data_dir

logger = logging.getLogger(__name__)

CHROMA_DB_DIR = get_data_dir() / "chromadb_data"


def resume_to_searchable_text(resume_json: dict[str, Any]) -> str:
    """
    Build a semantic-search document from the canonical resume schema.

    The parser payload does not expose a generic "text" field. ChromaDB must
    index stable candidate content: title, skills, summary and experience.
    """
    payload = resume_json.get("payload") or {}
    if not isinstance(payload, dict):
        return ""

    parts = []
    title = payload.get("title")
    if title:
        parts.append(str(title))

    skills = payload.get("skills") or []
    if isinstance(skills, list) and skills:
        parts.append("Skills: " + ", ".join(str(skill) for skill in skills if skill))

    summary = payload.get("summary")
    if summary:
        parts.append(str(summary))

    experience = payload.get("experience") or []
    if isinstance(experience, list):
        for item in experience:
            if not isinstance(item, dict):
                continue
            exp_parts = [
                item.get("position"),
                item.get("company"),
                item.get("period"),
                item.get("duration"),
                item.get("description"),
            ]
            text = " ".join(str(value) for value in exp_parts if value)
            if text:
                parts.append(text)

    return "\n".join(parts).strip()


class VectorCache:
    """
    Клас для роботи з локальною векторною базою ChromaDB.
    Дозволяє зберігати та шукати вже проаналізовані резюме за їхнім текстом та семантикою.
    """

    def __init__(self, collection_name: str = "resumes_cache"):
        CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Connecting to ChromaDB at {CHROMA_DB_DIR}")
        self.client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        logger.info("Loading SentenceTransformer model...")
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        logger.info("Model loaded. Getting collection...")
        self.collection = self.client.get_or_create_collection(
            name=collection_name, embedding_function=self.emb_fn
        )
        logger.info(f"VectorCache ready. Collection count: {self.collection.count()}")

    def _generate_id(self, resume_text: str, role: str) -> str:
        unique_string = f"{role}_{resume_text}"
        return hashlib.md5(unique_string.encode("utf-8")).hexdigest()

    def get_cached_analysis(self, resume_text: str, role: str) -> dict | None:
        """
        Шукає семантично схоже резюме у базі (дуже мала відстань, майже ідентичне).
        """
        if not resume_text or not resume_text.strip():
            return None

        results = self.collection.query(
            query_texts=[resume_text],
            n_results=1,
            where={"role": role},
        )

        if results["distances"] and results["distances"][0]:
            distance = results["distances"][0][0]
            if distance < 0.05:
                metadata = results["metadatas"][0][0]
                analysis_json = metadata.get("analysis_result")
                if analysis_json:
                    return json.loads(analysis_json)

        return None

    def get_cached_by_criteria(self, criteria_text: str, role: str, limit: int = 50) -> list[dict]:
        """
        Шукає релевантні резюме у базі за семантичним описом критеріїв.
        Повертає список словників з url, analysis_result та id.
        """
        if not criteria_text or not criteria_text.strip():
            return []

        # Якщо колекція порожня, ChromaDB може повернути помилку при query, краще перевірити
        if self.collection.count() == 0:
            return []

        # query can only return up to collection.count() results
        n_res = min(limit, self.collection.count())

        results = self.collection.query(
            query_texts=[criteria_text],
            n_results=n_res,
            where={"role": role},
        )

        cached_items = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                url = metadata.get("url")
                analysis_json = metadata.get("analysis_result")
                created_at = metadata.get("created_at")
                if url and analysis_json:
                    cached_items.append({
                        "id": doc_id,
                        "url": url,
                        "analysis_result": json.loads(analysis_json),
                        "created_at": created_at,
                        "distance": results["distances"][0][i] if results.get("distances") else None
                    })
        return cached_items

    def save_analysis(self, resume_text: str, role: str, analysis_result: dict, url: str = ""):
        """
        Зберігає текст резюме (як вектор) та його вердикт (як метадані) у базу.
        """
        if not resume_text or not resume_text.strip():
            return

        doc_id = self._generate_id(resume_text, role)

        self.collection.upsert(
            ids=[doc_id],
            documents=[resume_text],
            metadatas=[
                {
                    "role": role,
                    "url": url,
                    "analysis_result": json.dumps(analysis_result, ensure_ascii=False),
                    "created_at": datetime.utcnow().isoformat(),
                }
            ],
        )

    def delete_analysis(self, doc_id: str):
        """Видаляє запис із бази за ID."""
        self.collection.delete(ids=[doc_id])
