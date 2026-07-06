from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.models import PokemonMeta
from app.services.cache_store import get_cached_meta, list_cached_slugs, upsert_cached_meta
from app.services.name_resolver import normalize_name
from app.services.opgg_scraper import fetch_opgg_meta, fetch_opgg_debug

app = FastAPI(
    title="Pokemon Champions Helper API",
    version="0.7.0",
    description="Pokemon Champions meta/sample lookup API for Custom GPT Actions.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _entry_names(entries: List[Dict[str, Any]], limit: int = 4) -> List[str]:
    return [e.get("name") for e in entries[:limit] if e.get("name")]


def _first_name(entries: List[Dict[str, Any]]) -> Optional[str]:
    for e in entries:
        if e.get("name"):
            return e["name"]
    return None


def _rate_label(entries: List[Dict[str, Any]], limit: int = 4) -> List[str]:
    labels = []
    for e in entries[:limit]:
        name = e.get("name")
        if not name:
            continue
        rate = e.get("rate")
        if isinstance(rate, (int, float)):
            labels.append(f"{name} {rate:g}%")
        else:
            labels.append(name)
    return labels


def _infer_role(summary: Dict[str, Any]) -> str:
    moves = _entry_names(summary.get("common_moves", []), 10)
    items = _entry_names(summary.get("common_items", []), 10)

    if any("나이트" in item for item in items):
        base = "메가 에이스"
    elif "기합의띠" in items:
        base = "기합의띠 기반 전개/공격 요원"
    elif "구애스카프" in items:
        base = "스카프 고속 어태커"
    else:
        base = "대표 물리/범용 어태커"

    if any(move in moves for move in ["스텔스록", "압정뿌리기", "독압정"]):
        return f"{base} + 장판 전개"
    if any(move in moves for move in ["칼춤", "용의춤", "나쁜음모"]):
        return f"{base} + 랭크업 스위퍼"
    return base


def _build_representative_set(meta: Dict[str, Any]) -> Dict[str, Any]:
    summary = meta.get("summary", {})
    role = summary.get("role") or _infer_role(summary)
    moves = _entry_names(summary.get("common_moves", []), 4)

    return {
        "label": role,
        "nature": _first_name(summary.get("common_natures", [])),
        "ability": _first_name(summary.get("common_abilities", [])),
        "item": _first_name(summary.get("common_items", [])),
        "moves": moves,
        "evidence": {
            "moves": _rate_label(summary.get("common_moves", []), 6),
            "items": _rate_label(summary.get("common_items", []), 5),
            "abilities": _rate_label(summary.get("common_abilities", []), 3),
            "natures": _rate_label(summary.get("common_natures", []), 5),
        },
    }


def _build_threat_notes(meta: Dict[str, Any]) -> List[str]:
    summary = meta.get("summary", {})
    notes: List[str] = []
    moves = summary.get("common_moves", [])
    items = summary.get("common_items", [])
    abilities = summary.get("common_abilities", [])
    natures = summary.get("common_natures", [])

    for e in moves[:4]:
        name, rate = e.get("name"), e.get("rate")
        if name and isinstance(rate, (int, float)) and rate >= 50:
            notes.append(f"{name} 채용률이 {rate:g}%로 높아서 우선 의식해야 함")

    for e in items[:3]:
        name, rate = e.get("name"), e.get("rate")
        if not name:
            continue
        if name == "기합의띠":
            notes.append(f"기합의띠 가능성({rate:g}%): 첫 타에 쓰러뜨린다고 단정하면 위험")
        elif name == "구애스카프":
            notes.append(f"구애스카프 가능성({rate:g}%): 예상보다 먼저 움직일 수 있음")
        elif "나이트" in name:
            notes.append(f"{name} 사용률이 높아 메가 형태를 기본값으로 보는 게 안전")

    for e in abilities[:2]:
        name, rate = e.get("name"), e.get("rate")
        if name == "까칠한피부":
            notes.append(f"까칠한피부({rate:g}%): 접촉기로 때리면 반동 손해를 봄")
        elif name == "클리어바디":
            notes.append(f"클리어바디({rate:g}%): 위협/능력 하락으로 막는 플랜이 잘 안 통함")

    if natures:
        top = natures[0]
        if top.get("name") and isinstance(top.get("rate"), (int, float)):
            notes.append(f"성격은 {top['name']}({top['rate']:g}%)이 가장 많아 해당 스피드/화력 기준으로 계산 필요")

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for note in notes:
        if note not in seen:
            seen.add(note)
            deduped.append(note)
    return deduped[:8]


def _build_counterplay(meta: Dict[str, Any]) -> List[str]:
    name = meta.get("pokemon") or meta.get("ko_name") or meta.get("slug")
    summary = meta.get("summary", {})
    moves = _entry_names(summary.get("common_moves", []), 10)
    items = _entry_names(summary.get("common_items", []), 10)
    abilities = _entry_names(summary.get("common_abilities", []), 5)

    tips = [
        f"{name}의 상위 채용 기술을 기준으로 교체 받이와 선공 여부를 먼저 확인",
        "대미지 계산 전에는 확정 1타/2타를 단정하지 말고 사용률 높은 도구부터 가정",
    ]

    if "기합의띠" in items:
        tips.append("기합의띠를 깨기 위해 장판/날씨/연속기/선공기 마무리 플랜을 고려")
    if "구애스카프" in items:
        tips.append("스카프 가능성이 있으면 내 포켓몬의 최속/준속 추월 여부를 먼저 확인")
    if any("나이트" in item for item in items):
        tips.append("메가진화 후 종족값/특성 기준으로 다시 계산")
    if "까칠한피부" in abilities:
        tips.append("비접촉기나 특수기로 처리하면 까칠한피부 반동을 피할 수 있음")
    if "클리어바디" in abilities:
        tips.append("위협보다 타입상성, 화상, 고화력 약점 타점으로 압박하는 쪽이 안정적")
    if "스텔스록" in moves or "압정뿌리기" in moves:
        tips.append("초반 전개형일 수 있으니 도발/빠른 압박/고속 제거 플랜을 준비")

    return tips[:8]


def build_advice(meta: Dict[str, Any]) -> Dict[str, Any]:
    summary = meta.get("summary", {})
    return {
        "pokemon": meta.get("pokemon"),
        "ko_name": meta.get("ko_name"),
        "slug": meta.get("slug"),
        "source": meta.get("source"),
        "updated_at": meta.get("updated_at"),
        "battle_format": meta.get("battle_format"),
        "data_quality": meta.get("data_quality"),
        "representative_set": _build_representative_set(meta),
        "threat_notes": _build_threat_notes(meta),
        "counterplay": _build_counterplay(meta),
        "related": {
            "partners": _entry_names(summary.get("partners", []), 6),
            "winning_matchups": _entry_names(summary.get("winning_matchups", []), 6),
            "losing_matchups": _entry_names(summary.get("losing_matchups", []), 6),
        },
        "notes": "사용률 데이터 조합 기반의 대표 추정 샘플임. 실제 공개 샘플이 아니라면 확정 세트로 단정하지 말 것.",
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/debug/opgg/{name}", operation_id="debugOpggText", include_in_schema=False)
def debug_opgg_text(name: str):
    slug = normalize_name(name)
    return fetch_opgg_debug(slug)


@app.get("/pokemon/{name}", response_model=PokemonMeta, operation_id="getPokemonMeta")
def get_pokemon_meta(
    name: str,
    refresh: bool = Query(False, description="true면 OP.GG 실시간 조회를 먼저 시도하고 성공 시 캐시에 저장한다."),
    battle_format: str = Query("single", description="single 또는 double. 현재 MVP는 single 중심."),
):
    slug = normalize_name(name)

    if refresh:
        try:
            live = fetch_opgg_meta(slug=slug, battle_format=battle_format)
            upsert_cached_meta(slug, live)
            return live
        except Exception as e:
            cached = get_cached_meta(slug)
            if cached:
                cached["notes"] = f"실시간 OP.GG 조회 실패로 캐시 응답. error={type(e).__name__}: {e}"
                return cached
            raise HTTPException(status_code=502, detail=f"OP.GG fetch failed and no cache found: {e}")

    cached = get_cached_meta(slug)
    if cached:
        return cached

    try:
        live = fetch_opgg_meta(slug=slug, battle_format=battle_format)
        upsert_cached_meta(slug, live)
        return live
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Pokemon not found or fetch failed: {e}")


@app.get("/pokemon/{name}/advice", operation_id="getPokemonAdvice")
def get_pokemon_advice(
    name: str,
    refresh: bool = Query(False, description="true면 OP.GG 실시간 조회를 먼저 시도하고 성공 시 캐시에 저장한다."),
    battle_format: str = Query("single", description="single 또는 double. 현재 MVP는 single 중심."),
):
    meta = get_pokemon_meta(name=name, refresh=refresh, battle_format=battle_format)
    if hasattr(meta, "model_dump"):
        payload = meta.model_dump(mode="json")
    else:
        payload = dict(meta)
    return build_advice(payload)


@app.post("/cache/refresh", operation_id="refreshPokemonCache")
def refresh_pokemon_cache(
    names: str = Query(..., description="쉼표로 구분된 포켓몬 이름/slug. 예: 한카리아스,메타그로스,garchomp"),
    battle_format: str = Query("single", description="single 또는 double. 현재 MVP는 single 중심."),
):
    results = []
    for raw_name in [n.strip() for n in names.split(",") if n.strip()]:
        slug = normalize_name(raw_name)
        try:
            live = fetch_opgg_meta(slug=slug, battle_format=battle_format)
            saved = upsert_cached_meta(slug, live)
            results.append({"name": raw_name, "slug": slug, "ok": True, "pokemon": saved.get("pokemon")})
        except Exception as e:
            results.append({"name": raw_name, "slug": slug, "ok": False, "error": f"{type(e).__name__}: {e}"})
    return {"results": results}


@app.get("/cache/slugs", operation_id="listCachedPokemon")
def get_cached_slugs():
    return {"slugs": list_cached_slugs()}
