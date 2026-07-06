from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from app.services.name_resolver import normalize_name

# Minimal, code-owned battle knowledge. OP.GG still supplies usage/meta data.
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0, "flying": 2, "dragon": 0.5},
    "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5, "bug": 0.5, "rock": 2, "dragon": 0.5, "steel": 0.5},
    "ice": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0, "dark": 2, "steel": 2, "fairy": 0.5},
    "poison": {"grass": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground": {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying": {"electric": 0.5, "grass": 2, "fighting": 2, "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "dark": 0, "steel": 0.5},
    "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2, "ghost": 0.5, "dark": 2, "steel": 0.5, "fairy": 0.5},
    "rock": {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2, "steel": 0.5},
    "ghost": {"normal": 0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon": {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark": {"fighting": 0.5, "psychic": 2, "ghost": 2, "dark": 0.5, "fairy": 0.5},
    "steel": {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2, "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy": {"fire": 0.5, "fighting": 2, "poison": 0.5, "dragon": 2, "dark": 2, "steel": 0.5},
}

TYPE_KO = {
    "노말": "normal", "불꽃": "fire", "물": "water", "전기": "electric", "풀": "grass", "얼음": "ice", "격투": "fighting", "독": "poison", "땅": "ground", "비행": "flying", "에스퍼": "psychic", "벌레": "bug", "바위": "rock", "고스트": "ghost", "드래곤": "dragon", "악": "dark", "강철": "steel", "페어리": "fairy",
}

# Common Champions/Pokemon slugs used by current OP.GG meta. Unknowns still work, but type scoring becomes weaker.
POKEMON_TYPES: Dict[str, List[str]] = {
    "garchomp": ["dragon", "ground"],
    "metagross": ["steel", "psychic"],
    "lucario": ["fighting", "steel"],
    "dragonite": ["dragon", "flying"],
    "gyarados": ["water", "flying"],
    "charizard": ["fire", "flying"],
    "gengar": ["ghost", "poison"],
    "tyranitar": ["rock", "dark"],
    "gardevoir": ["psychic", "fairy"],
    "scizor": ["bug", "steel"],
    "mimikyu": ["ghost", "fairy"],
    "meowscarada": ["grass", "dark"],
    "primarina": ["water", "fairy"],
    "archaludon": ["steel", "dragon"],
    "ninetales-alola": ["ice", "fairy"],
    "raichu": ["electric"],
    "blaziken": ["fire", "fighting"],
    "corviknight": ["flying", "steel"],
    "hydreigon": ["dark", "dragon"],
    "hippowdon": ["ground"],
    "glimmora": ["rock", "poison"],
    "staraptor": ["normal", "flying"],
    "kilowattrel": ["electric", "flying"],
    "talonflame": ["fire", "flying"],
    "rotom-wash": ["electric", "water"],
    "salamence": ["dragon", "flying"],
    "greninja": ["water", "dark"],
    "azumarill": ["water", "fairy"],
    "ferrothorn": ["grass", "steel"],
}

MOVE_TYPES: Dict[str, str] = {
    # Korean moves from OP.GG examples/current meta
    "지진": "ground", "대지의힘": "ground", "10만마력": "ground", "땅고르기": "ground",
    "스텔스록": "rock", "암석봉인": "rock", "스톤샤워": "rock", "스톤에지": "rock", "파워젬": "rock",
    "역린": "dragon", "스케일샷": "dragon", "드래곤테일": "dragon", "용성군": "dragon", "드래곤클로": "dragon",
    "독찌르기": "poison", "오물폭탄": "poison", "클리어스모그": "poison",
    "사이코팽": "psychic", "사념의박치기": "psychic", "사이코키네시스": "psychic",
    "불릿펀치": "steel", "아이언헤드": "steel", "코멧펀치": "steel", "러스터캐논": "steel", "골드러시": "steel",
    "냉동펀치": "ice", "냉동빔": "ice", "눈보라": "ice", "고드름침": "ice",
    "번개펀치": "electric", "10만볼트": "electric", "번개": "electric", "볼트체인지": "electric",
    "인파이트": "fighting", "깨트리기": "fighting", "암해머": "fighting", "파동탄": "fighting", "무릎차기": "fighting",
    "화염방사": "fire", "불대문자": "fire", "플레어드라이브": "fire", "열풍": "fire", "블라스트번": "fire",
    "물의파동": "water", "하이드로펌프": "water", "아쿠아제트": "water", "웨이브태클": "water", "문포스": "fairy",
    "치근거리기": "fairy", "드레인키스": "fairy", "섀도크루": "ghost", "섀도볼": "ghost", "야습": "ghost",
    "탁쳐서떨구기": "dark", "기습": "dark", "악의파동": "dark", "물고버티기": "dark",
    "씨기관총": "grass", "트릭플라워": "grass", "에너지볼": "grass", "파워휩": "grass",
    "브레이브버드": "flying", "애크러뱃": "flying", "폭풍": "flying", "에어슬래시": "flying",
    "유턴": "bug", "시저크로스": "bug", "벌레의야단법석": "bug",
    "신속": "normal", "몸통박치기": "normal", "파괴광선": "normal", "이판사판태클": "normal",
    # English fallbacks
    "earthquake": "ground", "stealth rock": "rock", "outrage": "dragon", "bullet punch": "steel",
    "ice punch": "ice", "thunder punch": "electric", "close combat": "fighting", "protect": "normal",
}

PRIORITY_MOVES = {"불릿펀치", "신속", "야습", "기습", "아쿠아제트", "마하펀치", "얼음뭉치", "Bullet Punch", "Extreme Speed"}
HAZARD_MOVES = {"스텔스록", "압정뿌리기", "독압정", "끈적끈적네트", "Stealth Rock", "Spikes", "Toxic Spikes"}
SETUP_MOVES = {"칼춤", "용의춤", "나쁜음모", "명상", "벌크업", "껍질깨기", "Swords Dance", "Dragon Dance", "Nasty Plot"}
SUPPORT_MOVES = {"도발", "전기자석파", "오로라베일", "리플렉터", "빛의장막", "순풍", "트릭룸", "앵콜", "막말내뱉기"}
SPECIAL_HINT_MOVES = {"화염방사", "불대문자", "하이드로펌프", "냉동빔", "10만볼트", "번개", "문포스", "섀도볼", "러스터캐논", "용성군", "에너지볼", "사이코키네시스", "파동탄", "악의파동"}
PHYSICAL_HINT_MOVES = {"지진", "역린", "스케일샷", "사이코팽", "불릿펀치", "냉동펀치", "번개펀치", "아이언헤드", "코멧펀치", "인파이트", "치근거리기", "유턴", "브레이브버드", "플레어드라이브"}

DEFAULT_BUILD_CANDIDATES = [
    "garchomp", "metagross", "mimikyu", "meowscarada", "primarina", "charizard", "archaludon", "ninetales-alola",
    "raichu", "blaziken", "corviknight", "hydreigon", "hippowdon", "gengar", "gyarados", "lucario", "tyranitar", "scizor", "gardevoir", "dragonite", "glimmora"
]


def type_multiplier(attack_type: str, defender_types: List[str]) -> float:
    mult = 1.0
    chart = TYPE_CHART.get(attack_type, {})
    for t in defender_types:
        mult *= chart.get(t, 1.0)
    return mult


def defensive_profile(types: List[str]) -> Dict[str, List[str]]:
    weak, resist, immune = [], [], []
    for atk in TYPE_CHART:
        m = type_multiplier(atk, types)
        if m == 0:
            immune.append(atk)
        elif m > 1:
            weak.append(atk)
        elif m < 1:
            resist.append(atk)
    return {"weak_to": weak, "resists": resist, "immune_to": immune}


def entry_names(entries: List[Dict[str, Any]], limit: int = 10) -> List[str]:
    return [e.get("name") for e in entries[:limit] if e.get("name")]


def common_move_types(summary: Dict[str, Any], limit: int = 8) -> List[str]:
    types: List[str] = []
    for mv in entry_names(summary.get("common_moves", []), limit):
        t = MOVE_TYPES.get(mv) or MOVE_TYPES.get(mv.lower())
        if t and t not in types:
            types.append(t)
    return types


def infer_role_tags(meta: Dict[str, Any]) -> List[str]:
    summary = meta.get("summary", {})
    moves = entry_names(summary.get("common_moves", []), 12)
    items = entry_names(summary.get("common_items", []), 8)
    abilities = entry_names(summary.get("common_abilities", []), 4)
    slug = meta.get("slug") or ""
    types = POKEMON_TYPES.get(slug, [])
    tags = set()

    if any("나이트" in item for item in items): tags.add("mega_ace")
    if "기합의띠" in items: tags.add("focus_sash")
    if "구애스카프" in items: tags.add("speed_control")
    if "자뭉열매" in items or "먹다남은음식" in items: tags.add("bulky")
    if any(m in HAZARD_MOVES for m in moves): tags.add("hazard_setter")
    if any(m in PRIORITY_MOVES for m in moves): tags.add("priority_user")
    if any(m in SETUP_MOVES for m in moves): tags.add("setup_sweeper")
    if any(m in SUPPORT_MOVES for m in moves): tags.add("support")
    if any(m in SPECIAL_HINT_MOVES for m in moves): tags.add("special_attacker")
    if any(m in PHYSICAL_HINT_MOVES for m in moves): tags.add("physical_attacker")
    if "ground" in types: tags.add("electric_immunity")
    if "steel" in types: tags.add("steel_type")
    if "fairy" in types: tags.add("dragon_check")
    if "water" in types: tags.add("fire_check")
    if "fire" in types: tags.add("steel_check")
    if "클리어바디" in abilities: tags.add("intimidate_resist")
    if not tags: tags.add("generalist")
    return sorted(tags)


def summarize_profile(meta: Dict[str, Any]) -> Dict[str, Any]:
    slug = meta.get("slug") or normalize_name(meta.get("pokemon") or "")
    types = POKEMON_TYPES.get(slug, [])
    profile = defensive_profile(types) if types else {"weak_to": [], "resists": [], "immune_to": []}
    summary = meta.get("summary", {})
    return {
        "pokemon": meta.get("pokemon"),
        "ko_name": meta.get("ko_name"),
        "slug": slug,
        "types": types,
        "role_tags": infer_role_tags(meta),
        "common_move_types": common_move_types(summary),
        **profile,
    }


def matchup_score(my_meta: Dict[str, Any], opp_meta: Dict[str, Any]) -> Tuple[float, List[str]]:
    my = summarize_profile(my_meta)
    opp = summarize_profile(opp_meta)
    reasons: List[str] = []
    score = 0.0

    # Offensive coverage from my top move types into opponent typing.
    best_mult = 1.0
    best_type: Optional[str] = None
    if opp["types"]:
        for mt in my["common_move_types"]:
            mult = type_multiplier(mt, opp["types"])
            if mult > best_mult:
                best_mult, best_type = mult, mt
        if best_mult >= 4:
            score += 18; reasons.append(f"{my['pokemon']}이 {best_type} 타점으로 {opp['pokemon']}에게 4배 이상 압박 가능")
        elif best_mult >= 2:
            score += 10; reasons.append(f"{my['pokemon']}이 {best_type} 타점으로 {opp['pokemon']} 약점 압박 가능")
        elif best_mult == 0:
            score -= 8

    # Defensive switching: can my mon take opponent's common move types?
    opp_move_types = opp["common_move_types"]
    if my["types"] and opp_move_types:
        danger = 0
        safe = 0
        for ot in opp_move_types[:5]:
            mult = type_multiplier(ot, my["types"])
            if mult > 1: danger += 1
            if mult < 1: safe += 1
        score += safe * 3 - danger * 4
        if safe >= 2:
            reasons.append(f"{my['pokemon']}이 {opp['pokemon']}의 주요 타점을 일부 받아낼 수 있음")
        if danger >= 2:
            reasons.append(f"{my['pokemon']}은 {opp['pokemon']}의 주요 타점에 약점이 겹칠 수 있음")

    # Useful role tags.
    tags = set(my["role_tags"])
    if "priority_user" in tags: score += 4
    if "focus_sash" in tags: score += 3
    if "mega_ace" in tags: score += 6
    if "speed_control" in tags: score += 4
    if "dragon_check" in tags and "dragon" in opp["types"]: score += 5
    if "fire_check" in tags and ("fire" in opp["types"] or "steel" in opp["types"]): score += 4
    return score, reasons[:3]


def team_role_balance(selected_profiles: List[Dict[str, Any]]) -> Tuple[float, List[str], List[str]]:
    all_tags = {tag for p in selected_profiles for tag in p.get("role_tags", [])}
    score = 0.0
    reasons, risks = [], []
    desired = {
        "main_damage": {"mega_ace", "setup_sweeper", "physical_attacker", "special_attacker"},
        "priority": {"priority_user"},
        "speed": {"speed_control"},
        "safety": {"focus_sash", "bulky"},
    }
    if all_tags & desired["main_damage"]: score += 8; reasons.append("에이스/딜러 역할 확보")
    if all_tags & desired["priority"]: score += 4; reasons.append("선공기 마무리 플랜 있음")
    if all_tags & desired["speed"]: score += 4; reasons.append("스카프/스피드 보정 가능성으로 속도전 대응 가능")
    if all_tags & desired["safety"]: score += 3; reasons.append("기합의띠/내구 도구 기반 안정성이 있음")
    if not (all_tags & {"special_attacker"}): risks.append("특수 딜러 비중이 낮을 수 있음")
    if not (all_tags & {"priority_user", "speed_control"}): risks.append("상대 고속 에이스 마무리 수단이 부족할 수 있음")
    return score, reasons, risks


def weakness_stack(profiles: List[Dict[str, Any]]) -> Dict[str, int]:
    c = Counter()
    for p in profiles:
        for w in p.get("weak_to", []):
            c[w] += 1
    return dict(c.most_common())


def selection_recommendations(my_metas: List[Dict[str, Any]], opp_metas: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    results = []
    meta_by_slug = {m.get("slug"): m for m in my_metas}
    for combo in combinations(my_metas, 3):
        profiles = [summarize_profile(m) for m in combo]
        total = 50.0
        reasons: List[str] = []
        risks: List[str] = []

        # Matchup coverage: each opponent should have at least one decent answer.
        uncovered = []
        for opp in opp_metas:
            best = -999.0; best_reasons: List[str] = []; best_name = None
            for mine in combo:
                s, rs = matchup_score(mine, opp)
                if s > best:
                    best, best_reasons, best_name = s, rs, mine.get("pokemon")
            total += max(min(best, 18), -10)
            if best < 4:
                uncovered.append(opp.get("pokemon") or opp.get("slug"))
            else:
                reasons.extend(best_reasons[:1])
        if uncovered:
            risks.append("처리가 애매한 상대: " + ", ".join(uncovered[:3]))

        rb_score, rb_reasons, rb_risks = team_role_balance(profiles)
        total += rb_score
        reasons.extend(rb_reasons)
        risks.extend(rb_risks)

        # Penalize stacked weaknesses among selected 3.
        stacks = weakness_stack(profiles)
        bad_stacks = [t for t, n in stacks.items() if n >= 2]
        total -= len(bad_stacks) * 3
        if bad_stacks:
            risks.append("선출 3마리 약점 겹침: " + ", ".join(bad_stacks[:4]))

        # Lead heuristic: pick mega/sash/hazard/highest role mon.
        lead = combo[0]
        def lead_value(m: Dict[str, Any]) -> int:
            tags = set(summarize_profile(m)["role_tags"])
            return ("hazard_setter" in tags) * 4 + ("focus_sash" in tags) * 3 + ("mega_ace" in tags) * 2 + ("speed_control" in tags) * 1
        lead = sorted(combo, key=lead_value, reverse=True)[0]

        names = [m.get("pokemon") or m.get("ko_name") or m.get("slug") for m in combo]
        results.append({
            "selection": names,
            "lead": lead.get("pokemon") or lead.get("ko_name") or lead.get("slug"),
            "score": round(max(0, min(100, total)), 1),
            "reason": list(dict.fromkeys(reasons))[:6],
            "risks": list(dict.fromkeys(risks))[:5],
            "profiles": profiles,
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    for idx, r in enumerate(results[:top_n], 1):
        r["rank"] = idx
    return results[:top_n]


def analyze_team(metas: List[Dict[str, Any]]) -> Dict[str, Any]:
    profiles = [summarize_profile(m) for m in metas]
    tags = Counter(tag for p in profiles for tag in p.get("role_tags", []))
    weak = weakness_stack(profiles)
    warnings = []
    for t, n in weak.items():
        if n >= 3:
            warnings.append(f"{t} 약점이 {n}마리로 많이 겹침")
    if tags.get("special_attacker", 0) == 0:
        warnings.append("특수 공격 역할이 부족할 수 있음")
    if tags.get("priority_user", 0) == 0 and tags.get("speed_control", 0) == 0:
        warnings.append("선공기/스피드 컨트롤 수단이 부족할 수 있음")
    if tags.get("mega_ace", 0) == 0 and tags.get("setup_sweeper", 0) == 0:
        warnings.append("명확한 에이스 플랜이 약할 수 있음")
    strengths = []
    if tags.get("mega_ace", 0): strengths.append("메가 에이스 축이 있음")
    if tags.get("priority_user", 0): strengths.append("선공기 마무리 수단이 있음")
    if tags.get("hazard_setter", 0): strengths.append("장판 전개 플랜이 있음")
    if tags.get("dragon_check", 0): strengths.append("드래곤 견제 축이 있음")
    return {
        "team": [m.get("pokemon") or m.get("ko_name") or m.get("slug") for m in metas],
        "profiles": profiles,
        "role_counts": dict(tags.most_common()),
        "weakness_stack": weak,
        "strengths": strengths,
        "warnings": warnings,
        "notes": "역할/약점 분석은 OP.GG 대표 사용률과 내장 타입 상성표 기반의 휴리스틱 결과임. 대미지 확정 계산은 별도 확인 필요.",
    }


def build_party(core_metas: List[Dict[str, Any]], candidate_metas: List[Dict[str, Any]], party_size: int = 6) -> Dict[str, Any]:
    chosen = list(core_metas)
    chosen_slugs = {m.get("slug") for m in chosen}

    # Candidate score = partner relation + weakness cover + role diversity.
    while len(chosen) < party_size:
        current_profiles = [summarize_profile(m) for m in chosen]
        current_weak = weakness_stack(current_profiles)
        current_tags = {tag for p in current_profiles for tag in p.get("role_tags", [])}
        best = None; best_score = -999; best_reasons: List[str] = []
        for cand in candidate_metas:
            if cand.get("slug") in chosen_slugs:
                continue
            cp = summarize_profile(cand)
            score = 0.0; reasons = []
            # Cover stacked weaknesses by resisting/immune.
            for w, n in current_weak.items():
                if n >= 2 and (w in cp.get("resists", []) or w in cp.get("immune_to", [])):
                    score += 8 + n; reasons.append(f"{w} 약점 보완")
            # Add missing roles.
            tags = set(cp.get("role_tags", []))
            if "special_attacker" not in current_tags and "special_attacker" in tags:
                score += 8; reasons.append("특수 딜러 보강")
            if "priority_user" not in current_tags and "priority_user" in tags:
                score += 6; reasons.append("선공기 마무리 보강")
            if "speed_control" not in current_tags and "speed_control" in tags:
                score += 5; reasons.append("스피드 플랜 보강")
            if "dragon_check" not in current_tags and "dragon_check" in tags:
                score += 5; reasons.append("드래곤 견제 보강")
            if "fire_check" not in current_tags and "fire_check" in tags:
                score += 4; reasons.append("불꽃/강철 대응 보강")
            # OP.GG partner relation from core/current.
            cand_name = cand.get("pokemon") or cand.get("ko_name") or ""
            for m in chosen:
                partners = entry_names(m.get("summary", {}).get("partners", []), 10)
                if cand_name in partners:
                    score += 6; reasons.append(f"{m.get('pokemon')}의 OP.GG 파트너 후보")
            if score > best_score:
                best, best_score, best_reasons = cand, score, reasons
        if not best:
            break
        chosen.append(best); chosen_slugs.add(best.get("slug"))
    analysis = analyze_team(chosen)
    return {
        "recommended_party": [m.get("pokemon") or m.get("ko_name") or m.get("slug") for m in chosen],
        "core": [m.get("pokemon") or m.get("ko_name") or m.get("slug") for m in core_metas],
        "analysis": analysis,
        "notes": "추천 파티는 OP.GG 파트너 데이터, 내장 타입 상성표, 역할 태그 자동 추정으로 만든 초안임. 실제 환경에서는 선호 포켓몬/금지 룰/대미지 계산으로 보정 필요.",
    }
