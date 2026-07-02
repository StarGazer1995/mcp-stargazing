"""Tests for the cascading geocoding module."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

from src.functions.weather import geocoding as _gc
from src.functions.weather.geocoding import (
    _contains_cjk,
    _geocode,
    _geocode_amap,
    _geocode_nominatim,
    _geocode_photon,
    resolve_place_name,
)
from src.response import MCPError


@pytest.fixture(autouse=True)
def _reset_nominatim_singleton():
    """Reset the Nominatim singleton so tests don't leak state."""
    _gc._nominatim = None


# ── CJK detection ────────────────────────────────────────────────


@pytest.mark.parametrize(
    'text, expected',
    [
        ('北京', True),
        ('上海', True),
        ('Tokyo 東京', True),
        ('서울', True),
        ('Tokyo', False),
        ('New York', False),
        ('London', False),
        ('', False),
    ],
)
def test_contains_cjk(text, expected):
    assert _contains_cjk(text) is expected


# ── empty input ──────────────────────────────────────────────────


def test_resolve_place_name_empty():
    with pytest.raises(MCPError, match='不能为空'):
        resolve_place_name('  ')


# ── Amap Geocoding ────────────────────────────────────────────────


def test_geocode_amap_success():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'status': '1',
            'geocodes': [
                {
                    'formatted_address': '北京市',
                    'location': '116.4074,39.9042',
                    'level': 'city',
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = _geocode_amap('北京', 'test_key')

    assert result == ('北京市', 39.9042, 116.4074, 'amap_geo')


def test_geocode_amap_empty_geocodes():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'status': '1', 'geocodes': []}
        mock_get.return_value = mock_resp

        result = _geocode_amap('nonexistent', 'test_key')

    assert result is None


def test_geocode_amap_http_error():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_get.side_effect = requests.ConnectionError('unreachable')

        result = _geocode_amap('北京', 'test_key')

    assert result is None


def test_geocode_amap_malformed_location():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'status': '1',
            'geocodes': [{'formatted_address': 'Bad', 'location': 'invalid', 'level': 'city'}],
        }
        mock_get.return_value = mock_resp

        result = _geocode_amap('test', 'test_key')

    assert result is None


def test_geocode_amap_non_success_status():
    """Amap returns a non-1 status code → treated as failure."""
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'status': '0', 'info': 'INVALID_KEY'}
        mock_get.return_value = mock_resp

        result = _geocode_amap('北京', 'bad_key')

    assert result is None


def test_geocode_amap_province_level_ok():
    """Short province query (e.g. '浙江') → returns province-level result ok."""
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'status': '1',
            'geocodes': [
                {
                    'formatted_address': '浙江省',
                    'location': '120.15,30.28',
                    'level': 'province',
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = _geocode_amap('浙江', 'test_key')

    assert result == ('浙江省', 30.28, 120.15, 'amap_geo')


def test_geocode_amap_structured_address():
    """Structured address like '浙江安吉' → resolved by Amap's own parser."""
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'status': '1',
            'geocodes': [
                {
                    'formatted_address': '浙江省湖州市安吉县',
                    'location': '119.68,30.64',
                    'level': 'district',
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = _geocode_amap('浙江安吉', 'test_key')

    assert result == ('浙江省湖州市安吉县', 30.64, 119.68, 'amap_geo')


# ── Photon ───────────────────────────────────────────────────────


def test_geocode_photon_success():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'features': [
                {
                    'properties': {'name': 'Tokyo', 'country': 'Japan'},
                    'geometry': {'coordinates': [139.7649, 35.6762]},
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = _geocode_photon('Tokyo')

    assert result == ('Tokyo, Japan', 35.6762, 139.7649, 'photon')


def test_geocode_photon_display_name_construction():
    """Display name includes all available properties."""
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'features': [
                {
                    'properties': {
                        'name': '黄山风景区',
                        'city': '黄山市',
                        'state': '安徽省',
                        'country': '中国',
                    },
                    'geometry': {'coordinates': [118.1617, 30.1344]},
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = _geocode_photon('黄山')

    assert result[0] == '黄山风景区, 黄山市, 安徽省, 中国'


def test_geocode_photon_empty_features():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'features': []}
        mock_get.return_value = mock_resp

        result = _geocode_photon('nonexistent')

    assert result is None


def test_geocode_photon_missing_coordinates():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'features': [
                {
                    'properties': {'name': 'Nowhere'},
                    'geometry': {'coordinates': []},
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = _geocode_photon('Nowhere')

    assert result is None


def test_geocode_photon_http_error():
    with patch('src.functions.weather.geocoding.requests.get') as mock_get:
        mock_get.side_effect = requests.ConnectionError('unreachable')

        result = _geocode_photon('Tokyo')

    assert result is None


# ── Nominatim (geopy) ────────────────────────────────────────────


def test_geocode_nominatim_success():
    with patch('src.functions.weather.geocoding.Nominatim') as mock_nominatim_cls:
        mock_geocoder = MagicMock()
        mock_result = MagicMock()
        mock_result.latitude = 51.5074
        mock_result.longitude = -0.1278
        mock_result.address = 'London, England, UK'
        mock_geocoder.geocode.return_value = mock_result
        mock_nominatim_cls.return_value = mock_geocoder

        result = _geocode_nominatim('London')

    assert result == ('London, England, UK', 51.5074, -0.1278, 'nominatim')


def test_geocode_nominatim_not_found():
    with patch('src.functions.weather.geocoding.Nominatim') as mock_nominatim_cls:
        mock_geocoder = MagicMock()
        mock_geocoder.geocode.return_value = None
        mock_nominatim_cls.return_value = mock_geocoder

        result = _geocode_nominatim('nonexistent')

    assert result is None


def test_geocode_nominatim_timeout():
    with patch('src.functions.weather.geocoding.Nominatim') as mock_nominatim_cls:
        mock_geocoder = MagicMock()
        mock_geocoder.geocode.side_effect = GeocoderTimedOut('timeout')
        mock_nominatim_cls.return_value = mock_geocoder

        result = _geocode_nominatim('Beijing')

    assert result is None


def test_geocode_nominatim_service_error():
    with patch('src.functions.weather.geocoding.Nominatim') as mock_nominatim_cls:
        mock_geocoder = MagicMock()
        mock_geocoder.geocode.side_effect = GeocoderServiceError('down')
        mock_nominatim_cls.return_value = mock_geocoder

        result = _geocode_nominatim('Beijing')

    assert result is None


def test_geocode_nominatim_no_address_attr():
    """Fallback to place_name when result has no address attribute."""
    with patch('src.functions.weather.geocoding.Nominatim') as mock_nominatim_cls:
        mock_geocoder = MagicMock()
        mock_result = MagicMock(spec=['latitude', 'longitude'])
        mock_result.latitude = 40.0
        mock_result.longitude = 116.0
        # No 'address' attribute
        mock_geocoder.geocode.return_value = mock_result
        mock_nominatim_cls.return_value = mock_geocoder

        result = _geocode_nominatim('SomePlace')

    assert result[0] == 'SomePlace'


# ── cascading fallback ───────────────────────────────────────────


def test_geocode_cjk_uses_amap_first():
    """CJK query with Amap key → hits Amap, skips Photon/Nominatim."""
    with (
        patch('src.functions.weather.geocoding._geocode_amap') as mock_amap,
        patch('src.functions.weather.geocoding._geocode_photon') as mock_photon,
        patch('src.functions.weather.geocoding._geocode_nominatim') as mock_nominatim,
        patch.dict(os.environ, {'AMAP_KEY': 'test_key'}),
    ):
        mock_amap.return_value = ('北京市', 39.9, 116.4, 'amap_geo')

        result = _geocode('北京')

    assert result == ('北京市', 39.9, 116.4, 'amap_geo')
    mock_amap.assert_called_once()
    mock_photon.assert_not_called()
    mock_nominatim.assert_not_called()


def test_geocode_cjk_no_amap_key_falls_to_photon():
    """CJK query without Amap key → skips to Photon."""
    with (
        patch('src.functions.weather.geocoding._geocode_amap') as mock_amap,
        patch('src.functions.weather.geocoding._geocode_photon') as mock_photon,
        patch('src.functions.weather.geocoding._geocode_nominatim') as mock_nominatim,
        patch.dict(os.environ, {}, clear=True),
    ):
        mock_photon.return_value = ('北京市, 中国', 39.9, 116.4, 'photon')

        result = _geocode('北京')

    assert result == ('北京市, 中国', 39.9, 116.4, 'photon')
    mock_amap.assert_not_called()
    mock_photon.assert_called_once()
    mock_nominatim.assert_not_called()


def test_geocode_non_cjk_skips_amap():
    """Non-CJK query → goes straight to Photon."""
    with (
        patch('src.functions.weather.geocoding._geocode_amap') as mock_amap,
        patch('src.functions.weather.geocoding._geocode_photon') as mock_photon,
        patch.dict(os.environ, {'AMAP_KEY': 'test_key'}),
    ):
        mock_photon.return_value = ('Tokyo, Japan', 35.7, 139.8, 'photon')

        result = _geocode('Tokyo')

    assert result == ('Tokyo, Japan', 35.7, 139.8, 'photon')
    mock_amap.assert_not_called()


def test_geocode_amap_fails_falls_to_photon():
    """Amap returns None → Photon is tried next."""
    with (
        patch('src.functions.weather.geocoding._geocode_amap') as mock_amap,
        patch('src.functions.weather.geocoding._geocode_photon') as mock_photon,
        patch('src.functions.weather.geocoding._geocode_nominatim') as mock_nominatim,
        patch.dict(os.environ, {'AMAP_KEY': 'test_key'}),
    ):
        mock_amap.return_value = None
        mock_photon.return_value = ('北京市, 中国', 39.9, 116.4, 'photon')

        result = _geocode('北京')

    assert result[3] == 'photon'
    mock_amap.assert_called_once()
    mock_photon.assert_called_once()
    mock_nominatim.assert_not_called()


def test_geocode_photon_fails_falls_to_nominatim():
    """Photon returns None → Nominatim is tried as last resort."""
    with (
        patch('src.functions.weather.geocoding._geocode_amap') as mock_amap,
        patch('src.functions.weather.geocoding._geocode_photon') as mock_photon,
        patch('src.functions.weather.geocoding._geocode_nominatim') as mock_nominatim,
        patch.dict(os.environ, {'AMAP_KEY': 'test_key'}),
    ):
        mock_amap.return_value = None
        mock_photon.return_value = None
        mock_nominatim.return_value = ('London, UK', 51.5, -0.13, 'nominatim')

        result = _geocode('London')

    assert result[3] == 'nominatim'
    mock_amap.assert_not_called()  # non-CJK
    mock_photon.assert_called_once()
    mock_nominatim.assert_called_once()


def test_geocode_cjk_all_tiers_fail():
    """All providers return None → _geocode returns None."""
    with (
        patch('src.functions.weather.geocoding._geocode_amap') as mock_amap,
        patch('src.functions.weather.geocoding._geocode_photon') as mock_photon,
        patch('src.functions.weather.geocoding._geocode_nominatim') as mock_nominatim,
        patch.dict(os.environ, {'AMAP_KEY': 'test_key'}),
    ):
        mock_amap.return_value = None
        mock_photon.return_value = None
        mock_nominatim.return_value = None

        result = _geocode('北京')

    assert result is None


# ── public API (resolve_place_name) ──────────────────────────────


def test_resolve_place_name_all_fail_raises_mcperror():
    """When all providers fail, resolve_place_name raises MCPError."""
    with patch('src.functions.weather.geocoding._geocode') as mock_geocode:
        mock_geocode.return_value = None

        with pytest.raises(MCPError, match='未找到地点'):
            resolve_place_name('北京')


def test_resolve_place_name_success():
    """resolve_place_name returns a LocationInfo."""
    with patch('src.functions.weather.geocoding._geocode') as mock_geocode:
        mock_geocode.return_value = ('北京市', 39.9, 116.4, 'amap_geo')

        loc = resolve_place_name('北京')

    assert loc.name == '北京市'
    assert loc.lat == 39.9
    assert loc.lon == 116.4
    assert loc.timezone is None
