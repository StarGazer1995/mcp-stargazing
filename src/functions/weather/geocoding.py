"""Shared geocoding helpers for weather tools.

Cascading geocoding strategy:

1. CJK queries  → Amap POI Search  (Chinese cities, mountains, parks)
2. All queries  → Photon           (international cities, landmarks)
3. Final safety → Nominatim         (OSM fallback via geopy)

Photon is called via its public REST API (no API key required).
Amap requires an ``AMAP_KEY`` environment variable.
Nominatim requires no key but enforces strict rate limits (~1 req/s).
"""

from __future__ import annotations

import os
import re

import requests
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from src.logging_config import get_logger
from src.response import MCPError
from src.schemas.weather import LocationInfo

logger = get_logger(__name__)

# ── public entry point ────────────────────────────────────────────


def resolve_place_name(place_name: str) -> LocationInfo:
    """将地点名称解析为标准位置对象。"""

    cleaned = place_name.strip()
    if not cleaned:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            'place_name 不能为空。',
            {'place_name': place_name},
        )

    result = _geocode(cleaned)
    if result is None:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'未找到地点: {cleaned}',
            {'place_name': cleaned},
        )

    display_name, lat, lon, source = result
    logger.debug('Resolved %r via %s → (%f, %f)', cleaned, source, lat, lon)
    return LocationInfo(name=display_name, lat=lat, lon=lon, timezone=None)


# ── core geocoding logic ─────────────────────────────────────────

# Photon public API (Komoot-hosted, no key required).
_PHOTON_API = 'https://photon.komoot.io/api'

# Amap POI Search endpoint.
_AMAP_POI_API = 'https://restapi.amap.com/v3/place/text'

# Nominatim geocoder — lazily initialised (geopy validates the user_agent
# eagerly, and we don't need it until the fallback is actually hit).
_nominatim: Nominatim | None = None


def _geocode(place_name: str) -> tuple[str, float, float, str] | None:
    """Resolve *place_name* → (display_name, lat, lon, source).

    Falls back through Amap → Photon → Nominatim, stopping at the first
    successful result.
    """

    # Tier 1: Amap for CJK queries.
    if _contains_cjk(place_name):
        amap_key = os.getenv('AMAP_KEY')
        if amap_key:
            result = _geocode_amap(place_name, amap_key)
            if result is not None:
                return result
            logger.debug('Amap failed for %r, falling back to Photon', place_name)

    # Tier 2: Photon.
    result = _geocode_photon(place_name)
    if result is not None:
        return result

    # Tier 3: Nominatim — last-resort safety net.
    logger.debug('Photon failed for %r, falling back to Nominatim', place_name)
    return _geocode_nominatim(place_name)


def _contains_cjk(text: str) -> bool:
    """Return True when *text* contains any CJK character."""
    return bool(re.search(r'[一-鿿㐀-䶿豈-﫿가-힯]', text))


# ── provider helpers ─────────────────────────────────────────────


def _geocode_amap(place_name: str, amap_key: str) -> tuple[str, float, float, str] | None:
    """Query Amap POI Search.  Returns (name, lat, lon, "amap_poi") or None."""
    params = {'key': amap_key, 'keywords': place_name, 'offset': 1}
    try:
        resp = requests.get(_AMAP_POI_API, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.debug('Amap request failed for %r: %s', place_name, exc)
        return None

    pois = data.get('pois')
    if not pois:
        return None

    location = pois[0].get('location', '')
    try:
        lon_str, lat_str = location.split(',')
        lon, lat = float(lon_str), float(lat_str)
    except (ValueError, AttributeError):
        return None

    return (pois[0].get('name', place_name), lat, lon, 'amap_poi')


def _geocode_photon(place_name: str) -> tuple[str, float, float, str] | None:
    """Query Photon forward-geocoding. Returns (name, lat, lon, "photon") or None."""
    params = {'q': place_name, 'limit': 1}
    headers = {'User-Agent': 'mcp-stargazing/1.0'}
    try:
        resp = requests.get(_PHOTON_API, params=params, timeout=5, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.debug('Photon request failed for %r: %s', place_name, exc)
        return None

    features = data.get('features')
    if not features:
        return None

    props = features[0].get('properties', {})
    geom = features[0].get('geometry', {})
    coords = geom.get('coordinates', [])

    if len(coords) < 2:
        return None

    # Build a human-readable display name from available properties.
    name_parts = [props.get(k) for k in ('name', 'city', 'state', 'country') if props.get(k)]
    display_name = ', '.join(name_parts) if name_parts else place_name

    return (display_name, coords[1], coords[0], 'photon')


def _geocode_nominatim(place_name: str) -> tuple[str, float, float, str] | None:
    """Query Nominatim via geopy. Returns (address, lat, lon, "nominatim") or None."""
    global _nominatim
    if _nominatim is None:
        _nominatim = Nominatim(user_agent='mcp-stargazing')

    try:
        result = _nominatim.geocode(place_name, exactly_one=True, addressdetails=True)
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        logger.debug('Nominatim request failed for %r: %s', place_name, exc)
        return None

    if result is None:
        return None

    display_name = getattr(result, 'address', None) or place_name
    return (display_name, result.latitude, result.longitude, 'nominatim')
