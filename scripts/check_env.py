import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
import psycopg2
from pymongo import MongoClient
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv
from config.load_config import load_app_config

# 1. Загружаем пароли из .env
load_dotenv()

def check_mongo():
    print("--- CHECKING MONGO ---")
    try:
        # Формируем строку подключения
        user = os.getenv("MONGO_INITDB_ROOT_USERNAME")
        password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        port = os.getenv("MONGO_PORT", 27017)
        
        uri = f"mongodb://{user}:{password}@localhost:{port}"
        client = MongoClient(uri)
        
        # Проверка: Пишем и читаем
        db = client["test_db"]
        collection = db["smoke_test"]
        collection.insert_one({"status": "working", "system": "HR Pro"})
        
        doc = collection.find_one({"status": "working"})
        print(f"✅ MongoDB Success! Found doc: {doc['_id']}")
        
        # Чистим за собой
        collection.drop()
        client.close()
    except Exception as e:
        print(f"❌ MongoDB Failed: {e}")

def check_postgres():
    print("\n--- CHECKING POSTGRES ---")
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host="localhost",
            port=os.getenv("POSTGRES_PORT", 5432)
        )
        cur = conn.cursor()
        
        # Включаем поддержку векторов (это критически важно для RAG)
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        conn.commit()
        
        # Smoke-test pgvector: создаём таблицу с колонкой vector(3),
        # вставляем вектор длины 3 и читаем его обратно.
        cur.execute("DROP TABLE IF EXISTS vector_smoke_test;")
        cur.execute("""
            CREATE TABLE vector_smoke_test (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                embedding vector(3) NOT NULL
            );
        """)
        conn.commit()

        # ВАЖНО: vector(3) = ровно 3 числа в векторе
        cur.execute(
            "INSERT INTO vector_smoke_test (name, embedding) VALUES (%s, %s) RETURNING id;",
            ("test", [0.1, 0.2, 0.3])
        )
        inserted_id = cur.fetchone()[0]
        conn.commit()

        cur.execute(
            "SELECT id, name, embedding FROM vector_smoke_test WHERE id = %s;",
            (inserted_id,)
        )
        row = cur.fetchone()
        print(f"✅ pgvector Smoke-test OK! Row: id={row[0]}, name={row[1]}, embedding={row[2]}")

        # Чистим за собой
        cur.execute("DROP TABLE IF EXISTS vector_smoke_test;")
        conn.commit()

        # Проверка: простой SQL запрос
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"✅ Postgres Success! Version: {version}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Postgres Failed: {e}")

if __name__ == "__main__":
    cfg = load_app_config()
    print(f"--- APP CONFIG LOADED --- soft={cfg['limits']['search_soft_limit']} hard={cfg['limits']['search_hard_limit']}")
    check_mongo()
    check_postgres()
