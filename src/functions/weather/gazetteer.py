"""Offline gazetteer for Chinese administrative divisions.

This module resolves Chinese province/city/district place names (e.g.
"浙江安吉", "湖州安吉县", "杭州市西湖区") against a bundled static dataset.
It is the first, free tier of the weather geocoding cascade and never makes a
network request.

Dataset notes
-------------
- Rows: province / prefecture-level city / district entries (3237 total).
- Coordinates are GCJ-02 administrative-centre points, the same datum Amap
  returned historically, so behaviour for downstream weather grids is
  unchanged. See ``src/data/china_divisions.json`` for the exact values.
- The dataset is derived from DataV GeoAtlas (via the GeoMapData_CN V3
  location.json export) and is provided for convenience; see
  ``src/data/README.md`` for provenance and coordinate-system details.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parents[2] / 'data' / 'china_divisions.json'

SOURCE = 'gazetteer'

# Matches Han characters (and CJK extensions used in Chinese place names).
_CJK_RE = re.compile(r'[\u3400-\u9fff\uf900-\ufaff]')

_NAME_SUFFIXES = (
    '维吾尔自治区',
    '回族自治区',
    '壮族自治区',
    '特别行政区',
    '自治县',
    '自治旗',
    '地区',
    '林区',
    '新区',
    '矿区',
    '自治州',
    '省',
    '市',
    '县',
    '区',
    '盟',
    '旗',
)

# Leading characters of ethnic descriptors inside autonomous-prefecture names.
# e.g. "海西蒙古族藏族自治州" -> "海西"; "延边朝鲜族自治州" -> "延边".
_ETHNIC_MARKER_RE = re.compile(r'[藏蒙回朝壮苗侗傣彝布柯土羌满黎]')

_NORMALIZE_TABLE = str.maketrans({' ': '', '\u3000': '', '·': '', '・': ''})


@dataclass(frozen=True, slots=True)
class Division:
    """One administrative division from the bundled gazetteer."""

    adcode: int
    name: str
    level: str
    province: str
    city: str
    lon: float
    lat: float


def resolve_gazetteer(place_name: str) -> tuple[str, float, float, str] | None:
    """Resolve a CJK administrative place name from the offline gazetteer.

    Returns ``(display_name, lat, lon, SOURCE)`` or ``None`` when the gazetteer
    cannot uniquely answer the query (ambiguous names fall through to online
    providers instead of guessing).
    """

    normalized = _normalize(place_name)
    if not normalized or not _CJK_RE.search(normalized):
        return None

    try:
        matches = _alias_index().get(normalized)
    except (OSError, ValueError):
        return None
    if not matches:
        return None

    # Prefer the deepest administrative level matched by the exact alias.
    best_rank = min(_level_rank(m) for m in matches)
    narrowed = [m for m in matches if _level_rank(m) == best_rank]
    if len(narrowed) != 1:
        # Ambiguous without a province/city scope (e.g. bare "朝阳区"):
        # let the online tiers try to disambiguate.
        return None

    entry = narrowed[0]
    return (_display_name(entry), entry.lat, entry.lon, SOURCE)


# ── index construction ──────────────────────────────────────────


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, tuple[Division, ...]]:
    """Return an exact-match alias index over all gazetteer rows."""

    index: dict[str, list[Division]] = {}
    for row in _load_rows():
        for alias in _aliases(row):
            index.setdefault(alias, []).append(row)
    return {alias: tuple(rows) for alias, rows in index.items()}


@lru_cache(maxsize=1)
def _load_rows() -> tuple[Division, ...]:
    raw = json.loads(_DATA_FILE.read_text(encoding='utf-8'))
    return tuple(
        Division(
            adcode=int(row['adcode']),
            name=row['name'],
            level=row['level'],
            province=row.get('province') or '',
            city=row.get('city') or '',
            lon=float(row['lon']),
            lat=float(row['lat']),
        )
        for row in raw
    )


def _aliases(row: Division) -> set[str]:
    """Generate practical lookup aliases for one administrative row."""

    name = row.name
    base = _base_name(name, row.level)
    aliases = {name, base}
    if row.level == 'province':
        return aliases

    province = row.province
    province_base = _base_name(province, 'province')

    if row.level == 'city':
        for p_form in {province, province_base}:
            for n_form in {name, base}:
                aliases.add(p_form + n_form)
        return aliases

    # district rows
    city = row.city or province
    city_base = _base_name(city, 'city')
    district_forms = {name, base}
    city_forms = {city, city_base}
    province_forms = {province, province_base}

    for p_form in province_forms:
        for d_form in district_forms:
            aliases.add(p_form + d_form)
    for c_form in city_forms:
        for d_form in district_forms:
            aliases.add(c_form + d_form)
    for p_form in province_forms:
        for c_form in city_forms:
            for d_form in district_forms:
                aliases.add(p_form + c_form + d_form)
    return {a for a in aliases if a}


def _base_name(name: str, level: str) -> str:
    """Return the practical short form of an administrative name."""

    if not name:
        return ''
    if level == 'city' and name.endswith('自治州'):
        marker = _ETHNIC_MARKER_RE.search(name)
        if marker:
            return name[: marker.start()]
        return name[: -len('自治州')]
    for suffix in _NAME_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def _display_name(row: Division) -> str:
    if row.level == 'district':
        prefix = (
            f'{row.province}{row.city}' if row.city and row.city != row.province else row.province
        )
        return f'{prefix}{row.name}'
    if row.level == 'city' and row.province:
        return f'{row.province}{row.name}'
    return row.name


def _level_rank(row: Division) -> int:
    return {'district': 0, 'city': 1, 'province': 2}[row.level]


def _normalize(text: str) -> str:
    return text.translate(_NORMALIZE_TABLE).strip()
