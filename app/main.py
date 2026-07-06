from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.models import PokemonMeta
from app.services.cache_store import get_cached_meta, list_cached_slugs, upsert_cached_meta
from app.services.name_resolver import normalize_name
from app.services.opgg_scraper import fetch_opgg_meta, fetch_opgg_debug
from app.services.team_logic import (
    DEFAULT_BUILD_CANDIDATES,
    analyze_team,
    build_party,
    selection_recommendations,
    summarize_profile,
)

app = FastAPI(
    title="Pokemon Champions Helper API",
    version="0.12.0",
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



def _stat_allocation_label(allocation: Dict[str, Any]) -> Optional[str]:
    if not allocation:
        return None
    label = allocation.get("label")
    rate = allocation.get("rate")
    if label and isinstance(rate, (int, float)):
        return f"{label} ({rate:g}%)"
    return label


def _top_stat_allocation(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allocations = summary.get("common_stat_allocations") or []
    return allocations[0] if allocations else None

def _build_representative_set(meta: Dict[str, Any]) -> Dict[str, Any]:
    summary = meta.get("summary", {})
    role = summary.get("role") or _infer_role(summary)
    moves = _entry_names(summary.get("common_moves", []), 4)

    top_allocation = _top_stat_allocation(summary)

    return {
        "label": role,
        "nature": _first_name(summary.get("common_natures", [])),
        "ability": _first_name(summary.get("common_abilities", [])),
        "item": _first_name(summary.get("common_items", [])),
        "moves": moves,
        "stat_allocation": top_allocation,
        "stat_allocation_label": _stat_allocation_label(top_allocation) if top_allocation else None,
        "evidence": {
            "moves": _rate_label(summary.get("common_moves", []), 6),
            "items": _rate_label(summary.get("common_items", []), 5),
            "abilities": _rate_label(summary.get("common_abilities", []), 3),
            "natures": _rate_label(summary.get("common_natures", []), 5),
            "stat_allocations": [_stat_allocation_label(x) for x in summary.get("common_stat_allocations", [])[:5] if _stat_allocation_label(x)],
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

    top_alloc = _top_stat_allocation(summary)
    alloc_label = _stat_allocation_label(top_alloc) if top_alloc else None
    if alloc_label:
        notes.append(f"대표 노력치 분배는 {alloc_label} 기준으로 확인됨. 포챔스 노력치는 각 스탯 최대 32 기준")

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
        "stat_allocations": summary.get("common_stat_allocations", []),
        "stat_allocation_notes": summary.get("stat_allocation_notes", ["포켓몬 챔피언스 노력치는 H/A/B/C/D/S 각 항목 최대 32 기준으로 해석합니다."]),
        "related": {
            "partners": _entry_names(summary.get("partners", []), 6),
            "winning_matchups": _entry_names(summary.get("winning_matchups", []), 6),
            "losing_matchups": _entry_names(summary.get("losing_matchups", []), 6),
        },
        "notes": "사용률 데이터 조합 기반의 대표 추정 샘플임. 포켓몬 챔피언스 노력치는 기존 252 방식이 아니라 각 스탯 최대 32 기준으로 표현함. 실제 공개 샘플이 아니라면 확정 세트로 단정하지 말 것.",
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/debug/opgg/{name}", operation_id="debugOpggText", include_in_schema=False)
def debug_opgg_text(name: str):
    slug = normalize_name(name)
    return fetch_opgg_debug(slug)




@app.get("/pokemon/available", operation_id="listAvailablePokemon")
def list_available_pokemon():
    # This list is a practical candidate pool used by team building. It combines cached Pokemon and curated slugs.
    slugs = sorted(set(list_cached_slugs()) | set(DEFAULT_BUILD_CANDIDATES))
    return {
        "slugs": slugs,
        "count": len(slugs),
        "notes": "Team recommendations only use Pokemon that resolve successfully from OP.GG Pokemon Champions. This list is a candidate pool, not an official full roster.",
    }


@app.get("/")
def root():
    return {"ok": True, "name": "Pokemon Champions Helper API", "version": "0.12.0"}

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



def _as_payload(meta: Any) -> Dict[str, Any]:
    if hasattr(meta, "model_dump"):
        return meta.model_dump(mode="json")
    return dict(meta)


def _load_meta_for_team(name: str, refresh: bool, battle_format: str) -> Dict[str, Any]:
    # Team endpoints use the same cache/live logic as /pokemon.
    meta = get_pokemon_meta(name=name, refresh=refresh, battle_format=battle_format)
    return _as_payload(meta)


def _meta_display_name(meta: Dict[str, Any]) -> str:
    return meta.get("pokemon") or meta.get("ko_name") or meta.get("slug") or "unknown"


def _load_meta_safe(name: str, refresh: bool, battle_format: str) -> Dict[str, Any]:
    slug = normalize_name(str(name))
    try:
        meta = _load_meta_for_team(str(name), refresh, battle_format)
        return {"ok": True, "input": str(name), "slug": meta.get("slug") or slug, "meta": meta}
    except Exception as e:
        return {
            "ok": False,
            "input": str(name),
            "slug": slug,
            "reason": f"{type(e).__name__}: {e}",
        }


def _load_many_safe(names: List[Any], refresh: bool, battle_format: str, limit: int = 6) -> Dict[str, Any]:
    metas: List[Dict[str, Any]] = []
    unavailable: List[Dict[str, Any]] = []
    seen_slugs = set()
    for raw in names[:limit]:
        res = _load_meta_safe(str(raw), refresh, battle_format)
        if res["ok"]:
            meta = res["meta"]
            slug = meta.get("slug") or res.get("slug")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            metas.append(meta)
        else:
            unavailable.append({"input": res["input"], "slug": res["slug"], "reason": res["reason"]})
    return {"metas": metas, "unavailable": unavailable}


@app.post("/team/analyze", operation_id="analyzeTeam")
def analyze_team_endpoint(body: Dict[str, Any]):
    team = body.get("team") or body.get("my_team") or []
    refresh = bool(body.get("refresh", False))
    battle_format = body.get("battle_format", "single")
    if not isinstance(team, list) or not team:
        raise HTTPException(status_code=400, detail="team must be a non-empty list of Pokemon names")
    loaded = _load_many_safe(team, refresh, battle_format, limit=6)
    metas = loaded["metas"]
    if not metas:
        raise HTTPException(status_code=404, detail={"message": "No team Pokemon could be found in OP.GG Pokemon Champions data", "unavailable_pokemon": loaded["unavailable"]})
    result = analyze_team(metas)
    result["input_team"] = [str(x) for x in team[:6]]
    result["unavailable_pokemon"] = loaded["unavailable"]
    result["candidate_policy"] = "Only Pokemon successfully resolved from OP.GG Pokemon Champions are included in analysis."
    if loaded["unavailable"]:
        result.setdefault("warnings", []).append("일부 포켓몬은 OP.GG에서 조회 실패하여 분석에서 제외됨: " + ", ".join(x["input"] for x in loaded["unavailable"]))
    return result


@app.post("/team/selection", operation_id="recommendTeamSelection")
def recommend_team_selection(body: Dict[str, Any]):
    my_team = body.get("my_team") or []
    opponent_team = body.get("opponent_team") or []
    refresh = bool(body.get("refresh", False))
    battle_format = body.get("battle_format", "single")
    top_n = int(body.get("top_n", 3))
    if not isinstance(my_team, list) or len(my_team) < 3:
        raise HTTPException(status_code=400, detail="my_team must contain at least 3 Pokemon names")
    if not isinstance(opponent_team, list) or not opponent_team:
        raise HTTPException(status_code=400, detail="opponent_team must contain at least 1 Pokemon name")

    my_loaded = _load_many_safe(my_team, refresh, battle_format, limit=6)
    opp_loaded = _load_many_safe(opponent_team, refresh, battle_format, limit=6)
    my_metas = my_loaded["metas"]
    opp_metas = opp_loaded["metas"]

    if len(my_metas) < 3:
        raise HTTPException(status_code=404, detail={
            "message": "At least 3 of my_team must be available in OP.GG Pokemon Champions data",
            "available_my_team": [_meta_display_name(m) for m in my_metas],
            "unavailable_pokemon": my_loaded["unavailable"],
        })

    recs = selection_recommendations(my_metas, opp_metas, top_n=max(1, min(top_n, 5)))
    skipped = {"my_team": my_loaded["unavailable"], "opponent_team": opp_loaded["unavailable"]}
    return {
        "input_my_team": [str(x) for x in my_team[:6]],
        "input_opponent_team": [str(x) for x in opponent_team[:6]],
        "my_team": [_meta_display_name(m) for m in my_metas],
        "opponent_team": [_meta_display_name(m) for m in opp_metas],
        "recommended_selections": recs,
        "unavailable_pokemon": skipped,
        "candidate_policy": "Selection is calculated only from Pokemon successfully resolved from OP.GG Pokemon Champions. Unavailable Pokemon are excluded and listed here.",
        "notes": "3마리 선출 추천은 OP.GG 대표 사용률, 타입/역할 휴리스틱, 6C3 조합 점수 기반임. 조회 실패 포켓몬은 제외됨. 실제 확정 대미지/스피드는 별도 계산 필요.",
    }


@app.post("/team/build", operation_id="buildRecommendedParty")
def build_recommended_party(body: Dict[str, Any]):
    core = body.get("core") or body.get("pokemon") or []
    refresh = bool(body.get("refresh", False))
    battle_format = body.get("battle_format", "single")
    party_size = int(body.get("party_size", 6))
    if isinstance(core, str):
        core = [core]
    if not isinstance(core, list) or not core:
        raise HTTPException(status_code=400, detail="core must be a non-empty list of Pokemon names")

    core_loaded = _load_many_safe(core, refresh, battle_format, limit=3)
    core_metas = core_loaded["metas"]
    if not core_metas:
        raise HTTPException(status_code=404, detail={"message": "No core Pokemon could be found in OP.GG Pokemon Champions data", "unavailable_pokemon": core_loaded["unavailable"]})

    # Candidate pool: OP.GG partners of core + optional user candidates + curated OP.GG-tested default pool.
    candidates = []
    for m in core_metas:
        candidates.extend([p.get("name") for p in m.get("summary", {}).get("partners", []) if p.get("name")])
    user_pool = body.get("candidate_pool") or []
    if isinstance(user_pool, list):
        candidates.extend([str(x) for x in user_pool])
    candidates.extend(DEFAULT_BUILD_CANDIDATES)
    # Keep order/dedupe.
    deduped = []
    for c in candidates:
        if c and c not in deduped:
            deduped.append(c)

    candidate_metas = []
    unavailable_candidates = []
    for name in deduped[:60]:
        res = _load_meta_safe(str(name), refresh=False, battle_format=battle_format)
        if res["ok"]:
            candidate_metas.append(res["meta"])
        else:
            unavailable_candidates.append({"input": res["input"], "slug": res["slug"], "reason": res["reason"]})
    # Only OP.GG-resolved candidates are allowed into final recommendations.
    result = build_party(core_metas, candidate_metas, party_size=max(len(core_metas), min(party_size, 6)))
    result["candidate_count"] = len(candidate_metas)
    result["unavailable_pokemon"] = {"core": core_loaded["unavailable"], "candidates": unavailable_candidates[:20]}
    result["candidate_policy"] = "Recommended party uses only Pokemon successfully resolved from OP.GG Pokemon Champions. Failed candidates are excluded."
    return result



@app.get("/pokemon/{name}/profile", operation_id="getPokemonProfile")
def get_pokemon_profile(name: str, refresh: bool = Query(False), battle_format: str = Query("single")):
    meta = _load_meta_for_team(name, refresh, battle_format)
    return summarize_profile(meta)
