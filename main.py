import os
import psycopg2
from pymongo import MongoClient
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

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
        
        # Проверка: простой SQL запрос
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"✅ Postgres Success! Version: {version}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Postgres Failed: {e}")

if __name__ == "__main__":
    check_mongo()
    check_postgres()