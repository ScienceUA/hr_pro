import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def get_data_dir() -> Path:
    """
    Standardized data directory resolution for Cloud-Native architecture.
    Prioritizes:
    1. DATA_DIR environment variable.
    2. /app/out if running in Docker/Cloud Run.
    3. Local 'out' directory for development.
    4. Fallback to /tmp/hr_pro if all else fails or is read-only.
    """
    # 1. Check ENV
    env_data_dir = os.environ.get("DATA_DIR")
    if env_data_dir:
        path = Path(env_data_dir)
        if _is_writable(path):
            return path

    # 2. Check for Cloud Run / Docker environment
    # K_SERVICE is set by Cloud Run
    if os.environ.get("K_SERVICE") or os.environ.get("DOCKER_CONTAINER"):
        cloud_path = Path("/app/out")
        if _is_writable(cloud_path):
            return cloud_path

    # 3. Local Development
    local_path = Path(__file__).resolve().parents[2] / "out"
    if _is_writable(local_path):
        return local_path

    # 4. Final Fallback
    fallback_path = Path("/tmp/hr_pro")
    fallback_path.mkdir(parents=True, exist_ok=True)
    return fallback_path

def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test"
        test_file.touch()
        test_file.unlink()
        return True
    except Exception:
        logger.warning(f"Directory {path} is not writable or cannot be created.")
        return False
