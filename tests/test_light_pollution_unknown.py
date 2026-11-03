"""Explicit source defaults must not become measured light-pollution values."""

from copy import deepcopy
from unittest.mock import MagicMock

import numpy as np
import pytest
import rasterio
import stargazingplacefinder as spf
from fastmcp import Client
from rasterio.transform import from_bounds

import src.main  # noqa: F401
from src.functions.places import impl
from src.placefinder import get_light_pollution_grid
from src.schemas.places import LightPollutionGridPoint
from src.server_instance import mcp

VALUES = ('brightness', 'bortle', 'sqm', 'intensity', 'radiance', 'rgb', 'hex')


def raw_point(**changes):
    return {
        'lat': 0.5,
        'lng': 0.5,
        'name': 'Fixture point',
        'overlay_name': '默认数据',
        'brightness': 128,
        'bortle': 5,
        'sqm': '20.0',
        'intensity': 0.5,
        'radiance': None,
        'rgb': [128, 128, 128],
        'hex': '#808080',
        **changes,
    }


@pytest.mark.parametrize('radiance', [None, 0, 100])
def test_explicit_default_marker_preserves_location_but_no_values(radiance):
    raw = raw_point(radiance=radiance)
    original = deepcopy(raw)
    point = LightPollutionGridPoint.from_spf_point(raw)
    assert (point.lat, point.lon, point.name, point.overlay_name) == (
        0.5,
        0.5,
        'Fixture point',
        '默认数据',
    )
    assert all(getattr(point, key) is None for key in VALUES)
    assert raw == original


@pytest.mark.parametrize('overlay', [None, 'VIIRS-DNB-2025', 'Other source', '默认数据附近'])
def test_bortle_five_and_missing_radiance_alone_do_not_imply_placeholder(overlay):
    point = LightPollutionGridPoint.from_spf_point(raw_point(overlay_name=overlay))
    assert point.bortle == 5 and point.sqm == 20.0
    assert point.brightness == 128 and point.rgb == [128, 128, 128]
    assert point.radiance is None


def test_placeholder_alternative_longitude_and_missing_values_are_supported():
    point = LightPollutionGridPoint.from_spf_point(
        {'lat': 12, 'lon': 34, 'overlay_name': '默认数据'}
    )
    assert (point.lat, point.lon) == (12, 34)
    assert all(getattr(point, key) is None for key in VALUES)


@pytest.fixture
def real_raster(tmp_path):
    path = tmp_path / 'synthetic.tif'
    with rasterio.open(
        path,
        'w',
        driver='GTiff',
        width=32,
        height=32,
        count=1,
        dtype='float32',
        crs='EPSG:4326',
        transform=from_bounds(0, 0, 1, 1, 32, 32),
    ) as file:
        file.write(np.full((32, 32), 5, dtype='float32'), 1)
    analyzer = spf.init_light_pollution_analyzer(geotiff_path=path)
    try:
        yield analyzer
    finally:
        analyzer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['outside', 'closed', 'mixed', 'inside'])
async def test_real_spf_grid_and_sdk_preserve_unknown_vs_source_backed_five(real_raster, case):
    bounds = {'south': 0.25, 'north': 0.75, 'west': 0.25, 'east': 0.75}
    if case == 'outside':
        bounds = {'south': 2.01, 'north': 2.02, 'west': 2.01, 'east': 2.02}
    elif case == 'closed':
        real_raster.close()
    elif case == 'mixed':
        bounds.update(west=-0.5, east=0.5)
    args = {**bounds, 'zoom': 8}
    raw = get_light_pollution_grid(**args)
    async with Client(mcp._mcp) as client:
        response = (await client.call_tool('light_pollution_map', args)).structured_content
    assert response['_meta']['status'] == 'success'
    assert response['data']['bounds'] == bounds
    grid = response['data']['grid']
    assert len(grid) == len(raw['data'])
    missing = 0
    for point, source in zip(grid, raw['data'], strict=True):
        assert (point['lat'], point['lon']) == (source['lat'], source['lng'])
        assert point['overlay_name'] == source['overlay_name']
        if source['overlay_name'] == '默认数据':
            missing += 1
            assert all(point[key] is None for key in VALUES)
        else:
            assert point['bortle'] == source['bortle'] == 5
            assert point['sqm'] == float(source['sqm']) == 19.5
            assert point['radiance'] == source['radiance'] == pytest.approx(7)
            assert point['rgb'] == list(source['rgb'])
    if missing:
        assert f'{missing} grid point(s)' in response['_meta']['warnings'][0]
    else:
        assert 'warnings' not in response['_meta']
    if case == 'mixed':
        assert 0 < missing < len(grid)
    elif case in {'outside', 'closed'}:
        assert missing == len(grid)
    else:
        assert missing == 0


@pytest.mark.asyncio
async def test_empty_grid_keeps_existing_response_without_inventing_points(monkeypatch):
    monkeypatch.setattr(impl, 'get_light_pollution_grid', MagicMock(return_value={'data': []}))
    response = await impl.light_pollution_map.fn(south=0, west=0, north=1, east=1)
    assert response['data']['grid'] == []
    assert 'warnings' not in response['_meta']
