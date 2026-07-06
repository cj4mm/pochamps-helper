import re
from typing import List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from app.models import PokemonMeta, PokemonSummary, RateEntry, StatAllocation

BASE_URL = "https://op.gg/ko/pokemon-champions/pokedex/{slug}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

SECTION_HEADINGS = [
    "기술",
    "지닌 도구",
    "특성",
    "스탯 조정",
    "노력치",
    "파트너 포켓몬",
    "승리 상대",
    "승리 기술",
    "패배 상대",
    "패배 기술",
    "메가 사용률",
]

STOP_WORDS = set(SECTION_HEADINGS) | {
    "스탯", "타입 상성", "약점", "저항", "면역", "랭크 배틀", "싱글 배틀", "더블 배틀",
    "배틀 데이터기술팀 & 빌드승리 상대패배 상대같은 타입같은 특성",
    "전체기술지닌 도구특성스탯 조정노력치파트너 포켓몬승리 상대승리 기술패배 상대패배 기술메가 사용률",
    "광고", "같은 타입", "같은 특성", "팀 & 빌드",
}

POKEMON_TYPE_WORDS = {
    "노말", "불꽃", "물", "전기", "풀", "얼음", "격투", "독", "땅", "비행", "에스퍼", "벌레", "바위", "고스트", "드래곤", "악", "강철", "페어리"
}


def _clean_lines(html: str) -> Tuple[BeautifulSoup, List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [re.sub(r"\s+", " ", line) for line in lines]
    return soup, lines


def _extract_updated_at(lines: List[str]) -> Optional[str]:
    for line in lines:
        if line.startswith("업데이트"):
            return line.replace("업데이트", "", 1).strip()
    return None


def _extract_ko_name(soup: BeautifulSoup, lines: List[str], slug: str) -> str:
    if soup.title and soup.title.string:
        m = re.match(r"(.+?)\s*-\s*Pokemon Champions", soup.title.string.strip())
        if m:
            title_name = m.group(1).strip()
            if title_name and title_name != "포켓몬 챔피언스":
                return title_name

    for i, line in enumerate(lines[:160]):
        m = re.match(r"#\s*#?\d+\s+(.+)$", line)
        if m:
            name = m.group(1).strip()
            if name and name not in {"포켓몬 챔피언스"}:
                return name
        if re.fullmatch(r"#\s*#?\d+", line) and i + 1 < len(lines):
            cand = lines[i + 1].strip()
            cand = cand.replace("Image:", "").strip()
            if cand and cand not in STOP_WORDS and cand != "포켓몬 챔피언스":
                return cand
    return slug


def _parse_rank_rate(line: str) -> Optional[Tuple[int, float]]:
    m = re.fullmatch(r"(\d+)\s+([0-9]+(?:\.[0-9]+)?)%", line)
    if m:
        return int(m.group(1)), float(m.group(2))
    return None


def _parse_rate(line: str) -> Optional[float]:
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)%", line)
    if m:
        return float(m.group(1))
    return None


def _normalize_entry_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^Image:\s*", "", text).strip()
    return text


def _is_section_heading(line: str) -> bool:
    if line in STOP_WORDS:
        return True
    # OP.GG가 탭 제목들을 한 줄로 붙여주는 경우
    if any(h in line for h in ["전체기술지닌 도구", "배틀 데이터기술"]):
        return True
    return False


def _is_junk_entry(line: str) -> bool:
    if not line or line in STOP_WORDS:
        return True
    if line.startswith("#"):
        return True
    if line in {"싱글", "더블", "전체", "KO", "로그인", "홈", "포켓덱스"}:
        return True
    if line.startswith("Image:") and len(line.split()) == 1:
        return True
    return False


def _split_name_desc(text: str) -> Tuple[str, Optional[str]]:
    text = _normalize_entry_text(text)
    if not text:
        return text, None

    if "+" in text or text.startswith("HP "):
        return text, None

    # 링크 텍스트가 "지진 지진의 충격으로... 물리"처럼 오는 경우가 많다.
    parts = text.split(" ", 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0].strip(), parts[1].strip() or None


def _looks_like_ranked_data_starts(lines: List[str], idx: int) -> bool:
    """Return True when a heading is followed by OP.GG ranked rows.

    OP.GG text usually looks like:
      기술
      1
      99.4%
      지진
      설명...
      물리

    Earlier navigation tabs also contain the same words, e.g. 기술/지닌 도구/특성,
    so exact heading match alone is not enough.
    """
    window_end = min(len(lines), idx + 8)
    j = idx + 1
    while j + 2 < window_end:
        if lines[j].isdigit() and _parse_rate(lines[j + 1]) is not None:
            cand = lines[j + 2]
            if cand and not _is_section_heading(cand) and not _is_junk_entry(cand):
                return True
        # Some sections can be `1 99.4%` in one line.
        if _parse_rank_rate(lines[j]):
            if j + 1 < len(lines):
                cand = lines[j + 1]
                if cand and not _is_section_heading(cand) and not _is_junk_entry(cand):
                    return True
        j += 1
    return False


def _heading_indices(lines: List[str], heading: str) -> List[int]:
    indices: List[int] = []
    for i, line in enumerate(lines):
        # IMPORTANT:
        # Use exact heading matches only. OP.GG has headings like "승리 기술" and
        # "패배 기술" right before the real "기술" table. A fuzzy `heading in line`
        # match makes the parser choose "승리 기술" as the move table and then stop
        # immediately at the next section heading.
        if line == heading:
            indices.append(i)
    return indices


def _find_heading_index(lines: List[str], heading: str) -> Optional[int]:
    candidates = _heading_indices(lines, heading)
    if not candidates:
        return None

    # Prefer the occurrence that is immediately followed by ranked rows.
    for i in candidates:
        if _looks_like_ranked_data_starts(lines, i):
            return i

    # Fallback to the last occurrence. This avoids earlier navigation tabs/basic info
    # more often than returning the first occurrence.
    return candidates[-1]


def _next_entry_text(lines: List[str], idx: int) -> Optional[Tuple[str, int]]:
    j = idx
    while j < len(lines):
        line = lines[j]
        if _is_section_heading(line):
            return None
        if _is_junk_entry(line):
            j += 1
            continue
        if _parse_rank_rate(line) or line.isdigit() or _parse_rate(line) is not None:
            return None
        return _normalize_entry_text(line), j + 1
    return None


def _parse_ranked_section(lines: List[str], heading: str, limit: int = 10) -> List[RateEntry]:
    start = _find_heading_index(lines, heading)
    if start is None:
        return []

    entries: List[RateEntry] = []
    i = start + 1
    while i < len(lines) and len(entries) < limit:
        line = lines[i]
        if _is_section_heading(line) and line != heading:
            break

        rank_rate = _parse_rank_rate(line)
        if rank_rate:
            _, rate = rank_rate
            found = _next_entry_text(lines, i + 1)
            if found:
                text, next_i = found
                name, desc = _split_name_desc(text)
                if name:
                    entries.append(RateEntry(name=name, rate=rate, description=desc))
                i = next_i
                continue

        if line.isdigit() and i + 2 < len(lines):
            rate = _parse_rate(lines[i + 1])
            if rate is not None:
                found = _next_entry_text(lines, i + 2)
                if found:
                    text, next_i = found
                    name, desc = _split_name_desc(text)
                    if name:
                        entries.append(RateEntry(name=name, rate=rate, description=desc))
                    i = next_i
                    continue
        i += 1

    return entries


STAT_KEY_ALIASES = {
    "HP": "hp", "H": "hp", "체력": "hp",
    "공격": "atk", "A": "atk", "ATK": "atk",
    "방어": "defense", "B": "defense", "DEF": "defense",
    "특수공격": "spa", "특공": "spa", "C": "spa", "SPA": "spa",
    "특수방어": "spd", "특방": "spd", "D": "spd", "SPD": "spd",
    "스피드": "spe", "속도": "spe", "S": "spe", "SPE": "spe",
}
STAT_DISPLAY_ORDER = [
    ("hp", "H"), ("atk", "A"), ("defense", "B"), ("spa", "C"), ("spd", "D"), ("spe", "S"),
]
CHAMPIONS_STAT_MAX = 32


def _is_next_rank(lines: List[str], idx: int) -> bool:
    return idx + 1 < len(lines) and lines[idx].isdigit() and _parse_rate(lines[idx + 1]) is not None


def _collect_rank_block(lines: List[str], idx_after_rate: int, max_lines: int = 40) -> Tuple[List[str], int]:
    """Collect raw text for one ranked OP.GG row until the next ranked row/section.

    This is mainly used for Champions stat allocation rows. OP.GG often splits an
    allocation across many lines like `HP`, `32`, `공격`, `32` rather than one cell.
    """
    raw: List[str] = []
    i = idx_after_rate
    while i < len(lines) and len(raw) < max_lines:
        line = lines[i]
        if _is_section_heading(line):
            break
        if _is_next_rank(lines, i) and raw:
            break
        if not _is_junk_entry(line):
            raw.append(_normalize_entry_text(line))
        i += 1
    return raw, i


def _parse_stat_values(raw_lines: List[str]) -> dict:
    values = {}
    # First, parse adjacent `stat name` + `number` lines.
    for i, line in enumerate(raw_lines):
        key = STAT_KEY_ALIASES.get(line)
        if key and i + 1 < len(raw_lines):
            nxt = raw_lines[i + 1]
            if re.fullmatch(r"\d{1,2}", nxt):
                val = int(nxt)
                if 0 <= val <= CHAMPIONS_STAT_MAX:
                    values[key] = val

    # Also parse compact lines such as `HP 32 공격 32 스피드 32`.
    joined = " ".join(raw_lines)
    # Normalize common Korean two-word variants before regex matching.
    joined = joined.replace("특수 공격", "특수공격").replace("특수 방어", "특수방어")
    pattern = r"(HP|H|체력|공격|A|방어|B|특수공격|특공|C|특수방어|특방|D|스피드|속도|S)\s*[:=]?\s*(\d{1,2})"
    for stat, val_s in re.findall(pattern, joined, flags=re.IGNORECASE):
        key = STAT_KEY_ALIASES.get(stat) or STAT_KEY_ALIASES.get(stat.upper())
        if key:
            val = int(val_s)
            if 0 <= val <= CHAMPIONS_STAT_MAX:
                values[key] = val
    return values


def _format_stat_label(values: dict) -> str:
    parts = []
    for key, short in STAT_DISPLAY_ORDER:
        val = values.get(key)
        if val is not None:
            parts.append(f"{short}{val}")
    return " / ".join(parts)


def _parse_stat_allocations(lines: List[str], limit: int = 5) -> List[StatAllocation]:
    start = _find_heading_index(lines, "노력치")
    if start is None:
        return []

    allocations: List[StatAllocation] = []
    i = start + 1
    while i < len(lines) and len(allocations) < limit:
        line = lines[i]
        if _is_section_heading(line) and line != "노력치":
            break

        rate = None
        next_idx = None
        rank_rate = _parse_rank_rate(line)
        if rank_rate:
            _, rate = rank_rate
            next_idx = i + 1
        elif line.isdigit() and i + 1 < len(lines):
            parsed_rate = _parse_rate(lines[i + 1])
            if parsed_rate is not None:
                rate = parsed_rate
                next_idx = i + 2

        if rate is not None and next_idx is not None:
            raw, after = _collect_rank_block(lines, next_idx)
            values = _parse_stat_values(raw)
            label = _format_stat_label(values)
            if not label and raw:
                # Keep a compact raw label so the user can still inspect OP.GG text.
                label = " / ".join(raw[:8])
            allocations.append(StatAllocation(
                rate=rate,
                hp=values.get("hp"),
                atk=values.get("atk"),
                defense=values.get("defense"),
                spa=values.get("spa"),
                spd=values.get("spd"),
                spe=values.get("spe"),
                label=label,
                raw=raw[:16],
                note="포켓몬 챔피언스 노력치 기준: H/A/B/C/D/S 각 항목 최대 32",
            ))
            i = after
            continue
        i += 1
    return allocations


def _parse_evs(lines: List[str], limit: int = 5) -> List[str]:
    # Backward-compatible compact labels. Detailed structured data is available in
    # `common_stat_allocations` and uses Champions' 0~32-per-stat scale.
    evs: List[str] = []
    for alloc in _parse_stat_allocations(lines, limit=limit):
        prefix = f"{alloc.rate:g}%" if alloc.rate is not None else "?%"
        evs.append(f"{prefix} / {alloc.label or '원문 파싱 필요'}")
    return evs


def _clean_pokemon_name_from_link(text: str) -> str:
    text = _normalize_entry_text(text)
    parts = text.split()
    if not parts:
        return text
    cleaned: List[str] = []
    for p in parts:
        if p in POKEMON_TYPE_WORDS:
            break
        cleaned.append(p)
    return " ".join(cleaned) if cleaned else parts[0]


def _parse_pokemon_list_section(lines: List[str], heading: str, limit: int = 10) -> List[RateEntry]:
    start = _find_heading_index(lines, heading)
    if start is None:
        return []

    entries: List[RateEntry] = []
    i = start + 1
    while i < len(lines) and len(entries) < limit:
        line = lines[i]
        if _is_section_heading(line) and line != heading:
            break
        if line.isdigit():
            found = _next_entry_text(lines, i + 1)
            if found:
                text, next_i = found
                entries.append(RateEntry(name=_clean_pokemon_name_from_link(text), description=text))
                i = next_i
                continue
        i += 1
    return entries


def _debug_matches(lines: List[str]) -> dict:
    def around(keyword: str, radius: int = 8):
        for i, line in enumerate(lines):
            if keyword in line:
                start = max(0, i - radius)
                end = min(len(lines), i + radius + 1)
                return [{"idx": j, "line": lines[j]} for j in range(start, end)]
        return []

    return {
        "line_count": len(lines),
        "around_기술": around("기술"),
        "around_99": around("99"),
        "around_지진": around("지진"),
        "headings_found": {h: _find_heading_index(lines, h) for h in SECTION_HEADINGS},
    }


def fetch_opgg_debug(slug: str) -> dict:
    url = BASE_URL.format(slug=slug)
    with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    soup, lines = _clean_lines(response.text)
    return {
        "url": url,
        "status_code": response.status_code,
        "title": soup.title.string.strip() if soup.title and soup.title.string else None,
        **_debug_matches(lines),
    }


def fetch_opgg_meta(slug: str, battle_format: str = "single") -> PokemonMeta:
    url = BASE_URL.format(slug=slug)
    with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()

    soup, lines = _clean_lines(response.text)
    ko_name = _extract_ko_name(soup, lines, slug)
    updated_at = _extract_updated_at(lines)

    summary = PokemonSummary(
        common_moves=_parse_ranked_section(lines, "기술"),
        common_items=_parse_ranked_section(lines, "지닌 도구"),
        common_abilities=_parse_ranked_section(lines, "특성"),
        common_natures=_parse_ranked_section(lines, "스탯 조정"),
        common_evs=_parse_evs(lines),
        common_stat_allocations=_parse_stat_allocations(lines),
        stat_allocation_notes=["포켓몬 챔피언스 노력치는 H/A/B/C/D/S 각 항목 최대 32 기준으로 해석합니다."],
        partners=_parse_pokemon_list_section(lines, "파트너 포켓몬"),
        winning_matchups=_parse_pokemon_list_section(lines, "승리 상대"),
        losing_matchups=_parse_pokemon_list_section(lines, "패배 상대"),
        raw={"url": url, "line_count": len(lines)},
    )

    has_core_data = bool(summary.common_moves or summary.common_items or summary.common_abilities)

    return PokemonMeta(
        pokemon=ko_name,
        ko_name=ko_name,
        slug=slug,
        source="OP.GG Pokemon Champions Pokedex",
        updated_at=updated_at,
        battle_format=battle_format,
        data_quality="live_opgg_parse" if has_core_data else "live_opgg_empty",
        summary=summary,
        notes="OP.GG 페이지 텍스트 파싱 기반. 사이트 구조 변경 시 일부 항목이 누락될 수 있음.",
    )
