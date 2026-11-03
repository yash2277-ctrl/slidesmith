"""Paths and runtime settings (read from the .env file in the project root)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
PROJECTS_DIR = DATA_DIR / "projects"

for d in (TEMPLATES_DIR, PROJECTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

load_dotenv(ENV_FILE)

DEMO_MODEL = "demo"


def base_url() -> str:
    return os.getenv("AI_BASE_URL", "").strip().rstrip("/")


def api_key() -> str:
    return os.getenv("AI_API_KEY", "").strip()


def model() -> str:
    """Model id to request. Empty = auto-pick the first model the endpoint lists."""
    return os.getenv("AI_MODEL", "").strip()


def max_tokens() -> int:
    try:
        return max(1024, int(os.getenv("AI_MAX_TOKENS", "12000")))
    except ValueError:
        return 12000


def temperature() -> float:
    try:
        return float(os.getenv("AI_TEMPERATURE", "0.7"))
    except ValueError:
        return 0.7


def review_enabled() -> bool:
    """Render each slide and let the AI look at it and fix it (slower, better)."""
    return os.getenv("AI_REVIEW", "1").strip().lower() not in ("0", "false", "off", "no")


def review_model() -> str:
    """Model for the visual review; empty = pick a vision model from the endpoint automatically."""
    return os.getenv("AI_REVIEW_MODEL", "").strip()


def demo_mode() -> bool:
    return not base_url() or model() == DEMO_MODEL


def save_settings(values: dict[str, str | None]) -> None:
    """Persist provided settings to .env and apply them to this process."""
    ENV_FILE.touch(exist_ok=True)
    for key in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL", "AI_MAX_TOKENS", "AI_TEMPERATURE", "AI_REVIEW", "AI_REVIEW_MODEL"):
        value = values.get(key)
        if value is None:
            continue
        value = value.strip()
        set_key(str(ENV_FILE), key, value, quote_mode="never")
        os.environ[key] = value
