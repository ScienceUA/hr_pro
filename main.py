import argparse
import logging
import sys
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Импорты (убедитесь, что запускаете из корня проекта через poetry run python main.py)
from app.transport.fetcher import SmartFetcher
from app.storage.repository import JsonlRepository
from app.services.crawler import CrawlerService

def main():
    parser = argparse.ArgumentParser(description="HR Pro Crawler MVP")
    parser.add_argument("--query", type=str, required=True, help="Search query (e.g. 'Python')")
    parser.add_argument("--city", type=str, default="", help="City (e.g. 'Kyiv')")
    parser.add_argument("--pages", type=int, default=1, help="Max SERP pages to crawl")
    parser.add_argument("--out", type=str, default="candidates.jsonl", help="Output file path")
    
    args = parser.parse_args()

    # 1. Инициализация компонентов
    print(f"🔧 Initializing Crawler...")
    
    # Фетчер (пока без прокси)
    fetcher = SmartFetcher()
    
    # Репозиторий
    repo = JsonlRepository(args.out)
    
    # Сервис
    service = CrawlerService(fetcher, repo)

    # 2. Запуск
    print(f"🏃 Starting crawl for query: '{args.query}' in '{args.city}'")
    try:
        stats = service.run(
            query=args.query, 
            city=args.city, 
            max_pages=args.pages
        )
        
        # 3. Итоги
        print("\n" + "="*40)
        print(f"🏁 CRAWL FINISHED")
        print(f"   Reason: {stats.stop_reason or 'Completed'}")
        print(f"   Pages Processed:  {stats.pages_processed}")
        print(f"   Candidates Found: {stats.candidates_found}")
        print(f"   Candidates New:   {stats.candidates_new}")
        print(f"   Candidates Saved: {stats.candidates_saved}")
        print(f"   Errors (SERP):    {stats.errors_serp}")
        print(f"   Errors (Detail):  {stats.errors_detail}")
        print(f"📁 Data saved to: {args.out}")
        print("="*40)

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user. Data saved safely.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()