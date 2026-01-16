from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def load_app_config(path: str = "config/app.yaml") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p.resolve()}")

    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping (top-level dict).")

    return data

