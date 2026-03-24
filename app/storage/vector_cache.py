import json
import hashlib
from pathlib import Path
import chromadb
import chromadb.utils.embedding_functions as embedding_functions

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DB_DIR = PROJECT_ROOT / "out" / "chromadb_data"

class VectorCache:
    """
    Клас для роботи з локальною векторною базою ChromaDB.
    Дозволяє зберігати та шукати вже проаналізовані резюме за їхнім текстом.
    """
    def __init__(self, collection_name: str = "resumes_cache"):
        # Створюємо папку для БД, якщо її немає
        CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
        
        # Використовуємо локальний клієнт, який зберігає дані на диск
        self.client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        
        # Инициализируем многоязычную модель
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        # Створюємо або відкриваємо існуючу колекцію с явным указанием функции эмбеддингов
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.emb_fn
        )

    def _generate_id(self, resume_text: str, role: str) -> str:
        """Генерує унікальний ID на основі тексту та назви вакансії."""
        unique_string = f"{role}_{resume_text}"
        return hashlib.md5(unique_string.encode('utf-8')).hexdigest()

    def get_cached_analysis(self, resume_text: str, role: str) -> dict | None:
        """
        Шукає семантично схоже резюме у базі.
        Якщо знайдено збіг (дуже мала відстань) для тієї ж ролі, повертає готовий результат.
        """
        if not resume_text or not resume_text.strip():
            return None
            
        # Робимо запит до векторної бази
        results = self.collection.query(
            query_texts=[resume_text],
            n_results=1,
            where={"role": role} # Фільтруємо строго по конкретній посаді
        )
        
        if results["distances"] and results["distances"][0]:
            distance = results["distances"][0][0]
            # У ChromaDB менша відстань означає більшу схожість.
            # Відстань < 0.05 означає, що тексти практично ідентичні (понад 95% збігу).
            if distance < 0.05:
                metadata = results["metadatas"][0][0]
                analysis_json = metadata.get("analysis_result")
                if analysis_json:
                    return json.loads(analysis_json)
        
        return None

    def save_analysis(self, resume_text: str, role: str, analysis_result: dict):
        """
        Зберігає текст резюме (як вектор) та його вердикт (як метадані) у базу.
        """
        if not resume_text or not resume_text.strip():
            return
            
        doc_id = self._generate_id(resume_text, role)
        
        # Зберігаємо або оновлюємо запис (upsert)
        self.collection.upsert(
            ids=[doc_id],
            documents=[resume_text],
            metadatas=[{
                "role": role,
                "analysis_result": json.dumps(analysis_result, ensure_ascii=False)
            }]
        )