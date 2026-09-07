"""Shared geocoding helpers for weather tools.

Cascading geocoding strategy (zero-cost by default):

1. CJK queries  → offline China gazetteer   (province/city/district)
2. All queries  → Photon                     (international + CJK fallback)
3. Final safety → Nominatim                  (OSM fallback via geopy)

Photon is called via its public REST API (no API key required).
Nominatim requires no key but enforces strict rate limits (~1 req/s).
Neither provider is contacted when the offline gazetteer can answer a CJK
administrative query, so everyday Chinese place-name lookups are free,
offline, and deterministic.

Amap Geocoding remains supported as an **opt-in** paid-quality tier. It is
never contacted unless ``GEOCODER_PROVIDERS`` lists ``amap`` *and*
``AMAP_KEY`` is set. The old behaviour of auto-using Amap whenever
``AMAP_KEY`` was present has been removed.

The Amap tier uses the **Geocoding API** (``v3/geocode/geo``), not the POI
Search API (``v3/place/text``). The geocoding API returns administrative
divisions with ``level`` (province/city/district/township) and ``adcode``,
which is the correct tool for resolving place names like "浙江安吉".
"""

from __future__ import annotations

import os
import re

import requests
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from src.functions.weather.gazetteer import resolve_gazetteer
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

# Amap Geocoding endpoint — resolves administrative divisions (province/city/district).
# This is the correct API for place-name resolution.  The POI Search API
# (v3/place/text) matches businesses and landmarks, not administrative regions,
# and produced incorrect results like "浙江万吉(杭州市)" for "浙江安吉".
_AMAP_GEOCODE_API = 'https://restapi.amap.com/v3/geocode/geo'

# Nominatim geocoder — lazily initialised (geopy validates the user_agent
# eagerly, and we don't need it until the fallback is actually hit).
_nominatim: Nominatim | None = None

# Provider order control. ``GEOCODER_PROVIDERS`` may override the defaults;
# supported names: gazetteer, photon, nominatim, amap.
_DEFAULT_PROVIDERS_CJK = ('gazetteer', 'photon', 'nominatim')
_DEFAULT_PROVIDERS_OTHER = ('photon', 'nominatim')
_SUPPORTED_PROVIDERS = frozenset({'gazetteer', 'photon', 'nominatim', 'amap'})


def _geocode_provider_order(place_name: str) -> tuple[str, ...]:
    """Return the ordered geocoder names enabled for *place_name*.

    Amap participates only when it is explicitly listed in
    ``GEOCODER_PROVIDERS`` *and* an ``AMAP_KEY`` is configured. By default it
    is excluded so no paid Amap call is made.
    """

    configured = os.getenv('GEOCODER_PROVIDERS')
    if configured and configured.strip():
        order = tuple(
            name.strip().lower()
            for name in configured.split(',')
            if name.strip() in _SUPPORTED_PROVIDERS
        )
    elif _contains_cjk(place_name):
        order = _DEFAULT_PROVIDERS_CJK
    else:
        order = _DEFAULT_PROVIDERS_OTHER

    if not order:
        # Every configured name was unknown; fall back instead of failing.
        order = _DEFAULT_PROVIDERS_CJK if _contains_cjk(place_name) else _DEFAULT_PROVIDERS_OTHER
    return tuple(name for name in order if name != 'amap' or os.getenv('AMAP_KEY'))


def _geocode(place_name: str) -> tuple[str, float, float, str] | None:
    """Resolve *place_name* → (display_name, lat, lon, source).

    Walks the configured provider chain, stopping at the first successful
    result. Default chain: gazetteer → Photon → Nominatim (CJK) or
    Photon → Nominatim (non-CJK); Amap is opt-in.
    """

    for provider in _geocode_provider_order(place_name):
        result = _run_provider(provider, place_name)
        if result is not None:
            return result
        logger.debug('%s geocoder failed for %r, trying next', provider, place_name)
    return None


def _contains_cjk(text: str) -> bool:
    """Return True when *text* contains any CJK character."""
    return bool(re.search(r'[一-鿿㐀-䶿豈-﫿가-힯]', text))


# ── provider helpers ─────────────────────────────────────────────


def _geocode_gazetteer(place_name: str) -> tuple[str, float, float, str] | None:
    """Resolve Chinese province/city/district names from the offline dataset."""

    return resolve_gazetteer(place_name)


def _geocode_amap_with_env(place_name: str) -> tuple[str, float, float, str] | None:
    """Amap helper adapter that reads ``AMAP_KEY`` from the environment."""

    amap_key = os.getenv('AMAP_KEY')
    if not amap_key:
        return None
    return _geocode_amap(place_name, amap_key)


def _geocode_amap(place_name: str, amap_key: str) -> tuple[str, float, float, str] | None:
    """Query Amap Geocoding API.  Returns (name, lat, lon, "amap_geo") or None.

    The Amap Geocoding API (``v3/geocode/geo``) resolves structured addresses
    (省+市+区县+街道+门牌号) to coordinates.  We pass the raw *place_name* as
    the ``address`` parameter and let Amap handle parsing — its built-in
    address parser is more robust than our own regex-based disambiguation.
    """
    params: dict[str, str] = {'key': amap_key, 'address': place_name}

    try:
        resp = requests.get(_AMAP_GEOCODE_API, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.debug('Amap geocode request failed for %r: %s', place_name, exc)
        return None

    if data.get('status') != '1':
        logger.debug('Amap geocode non-success for %r: %s', place_name, data.get('info', 'unknown'))
        return None

    geocodes: list[dict] = data.get('geocodes', [])
    if not geocodes:
        return None

    # Amap typically returns one result for well-formed queries; pick the
    # first if there are multiple (they're ordered by relevance).
    best = geocodes[0]

    location = best.get('location', '')
    try:
        lon_str, lat_str = location.split(',')
        lon, lat = float(lon_str), float(lat_str)
    except (ValueError, AttributeError):
        return None

    display_name = best.get('formatted_address') or best.get('name') or place_name
    return (display_name, lat, lon, 'amap_geo')


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


def _run_provider(provider: str, place_name: str) -> tuple[str, float, float, str] | None:
    """Dispatch to a provider helper at call time (keeps module mocks working)."""

    if provider == 'amap':
        return _geocode_amap_with_env(place_name)
    return globals()[f'_geocode_{provider}'](place_name)
