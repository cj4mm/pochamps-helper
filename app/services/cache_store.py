import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_PATH = DATA_DIR / "pokemon_meta.json"


def load_cache() -> Dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(cache: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sanitize_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep runtime responses compact for GPT Actions.

    Old development caches may contain summary.raw.debug, which can be very large.
    Remove it when reading/saving.
    """
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary")
    if isinstance(summary, dict):
        raw = summary.get("raw")
        if isinstance(raw, dict) and "debug" in raw:
            raw = dict(raw)
            raw.pop("debug", None)
            summary = dict(summary)
            summary["raw"] = raw
            payload = dict(payload)
            payload["summary"] = summary
    return payload


def get_cached_meta(slug: str) -> Optional[Dict[str, Any]]:
    payload = load_cache().get(slug)
    if payload is None:
        return None
    return sanitize_meta(payload)


def upsert_cached_meta(slug: str, meta: Any) -> Dict[str, Any]:
    """Save a live parsed Pydantic model or dict into the JSON cache."""
    if hasattr(meta, "model_dump"):
        payload = meta.model_dump(mode="json")
    else:
        payload = dict(meta)

    payload = sanitize_meta(payload)
    payload["cache_saved_at"] = datetime.now(timezone.utc).isoformat()
    cache = load_cache()
    cache[slug] = payload
    save_cache(cache)
    return payload


def list_cached_slugs() -> list[str]:
    return sorted(load_cache().keys())
