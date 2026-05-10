import argparse
import logging
import os
from pathlib import Path
from typing import Optional

from google.cloud import storage
import redis

from app.storage.repository import get_repository

logger = logging.getLogger(__name__)


def cleanup_project(session_id: str = None, dry_run: bool = False):
    """
    Cleans up temporary session files and optionally clears Redis/GCS state.
    Uses the Repository Strategy pattern for storage cleanup.
    """
    repo = get_repository()
    
    # 1. Storage Cleanup (Local or GCS)
    deleted_count = repo.cleanup(session_id=session_id, dry_run=dry_run)
    logger.info(f"Storage cleanup finished. Total items {'marked for deletion' if dry_run else 'deleted'}: {deleted_count}")

    # 2. Redis Cleanup (Optional - clearing old task statuses)
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    if redis_url and not dry_run:
        try:
            r = redis.from_url(redis_url, decode_responses=True)
            # We look for task keys. In a real system, we'd only delete expired ones,
            # but task_status already has a TTL (e.g. 24h).
            keys = r.keys("task:*")
            if keys:
                logger.info(f"Redis has {len(keys)} task keys. They will expire based on TTL.")
                # If we really wanted to force clear:
                # r.delete(*keys)
        except Exception as e:
            logger.error(f"Redis check failed: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="HR-Pro project cleanup utility")
    parser.add_argument(
        "--role",
        type=str,
        default=None,
        help="Filter by role slug (e.g. 'sales-director')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    cleanup_project(args.role, dry_run=args.dry_run)
