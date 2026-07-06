import json
from pathlib import Path
from typing import Dict

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_name_map() -> Dict[str, str]:
    path = DATA_DIR / "pokemon_names.json"
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_name(name: str) -> str:
    name_map = load_name_map()
    raw = name.strip()
    lower = raw.lower()

    # Exact Korean / alias match first
    if raw in name_map:
        return name_map[raw]
    if lower in name_map:
        return name_map[lower]

    # Basic slug fallback
    return lower.replace(" ", "-").replace("_", "-")
