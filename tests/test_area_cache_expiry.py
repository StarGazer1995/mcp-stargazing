"""Real SDK paging must not renew elapsed cache lifetime or reuse expired data."""

import time
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from src.analysis_cache import AnalysisCache
from src.functions.places import impl
from src.schemas.places import StargazingLocation
from src.server_instance import mcp


@pytest.mark.asyncio
async def test_sdk_paging_recomputes_at_elapsed_ttl_even_after_wall_clock_rollback(monkeypatch):
    elapsed = [0.0]
    cache = AnalysisCache(ttl_seconds=60, clock=lambda: elapsed[0])
    first = StargazingLocation(name='First', lat=30.5, lon=119.5)
    second = StargazingLocation(name='Second', lat=30.6, lon=119.6)
    replacement = StargazingLocation(name='Refreshed', lat=30.5, lon=119.5)
    compute = MagicMock(side_effect=[[first, second], [replacement]])
    monkeypatch.setattr(impl, 'ANALYSIS_CACHE', cache)
    monkeypatch.setattr(impl, 'compute_area_locations', compute)
    parameters = dict(south=30.0, north=31.0, west=119.0, east=120.0, page_size=1)
    async with Client(mcp._mcp) as client:
        initial = (await client.call_tool('analysis_area', parameters)).structured_content['data']
        resource = initial['resource_id']
        old_revision = cache.get_versioned(resource)[1]
        assert initial['items'][0]['name'] == 'First'
        wall_time = time.time()
        monkeypatch.setattr(time, 'time', lambda: wall_time - 3600)
        elapsed[0] = 59.999
        page = (
            await client.call_tool('analysis_area', {**parameters, 'page': 2})
        ).structured_content['data']
        assert page['items'][0]['name'] == 'Second'
        assert page['resource_id'] == resource
        assert compute.call_count == 1
        assert cache.get_versioned(resource)[1] == old_revision
        elapsed[0] = 60.0
        refreshed = (await client.call_tool('analysis_area', parameters)).structured_content['data']
        assert refreshed['items'][0]['name'] == 'Refreshed'
        assert refreshed['resource_id'] == resource
        assert compute.call_count == 2
        assert cache.get_versioned(resource)[1] != old_revision
