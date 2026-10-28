"""Public discovery must deliver actionable routing without a second metadata schema."""

import re

import pytest
from conftest import _call_tool, _list_tool_entries
from fastmcp import Client

import src.main  # noqa: F401
from src.server_instance import mcp

SECTIONS = ('Use when', 'Do not use when', 'Requires', 'Returns', 'Follow-up')

INTERPRETATION_GUIDANCE = {
    'plan_stargazing_session': (
        'relative ranking',
        'not a probability',
        '_meta.status=success',
        'decision=null',
        'null observation_window',
        'nightly_weather_unavailable',
        'no_usable_observation_window',
        'long_range_forecast',
        'summary.current',
        'summary.daily',
        'Sun below -6 degrees',
        '-18 degrees',
        'not measured noise',
        'request as a JSON object, not a JSON string',
        'not a plan locked to the center point',
        'approximate search box, not a strict circular distance filter',
        'inspect resolved_location',
        'do not compare scores across generic and equipment rankings',
        'a timeout does not establish that a background planning task exists',
    ),
    'get_best_stargazing_plan': (
        'relative ranking',
        '_meta.status=success',
        'candidate notes',
        'Missing night-hour weather is unknown',
        'null best_observation_window',
        'Sun below -6 degrees',
        '-18 degrees',
        'not a fixed-site plan',
    ),
    'get_multiday_stargazing_plan': (
        'relative ranking',
        'per-night errors',
        'dated forecast hours for each night',
        'summary.current',
        'summary.daily',
        'unknown, not clear',
        'null best_observation_window',
        '-18 degrees',
    ),
    'get_weather_by_name': (
        'summary.current',
        'summary.daily',
        'summary.hourly',
        'across local midnight',
        'Missing/null or out-of-horizon hours are unknown',
        'not observations',
    ),
    'get_weather_by_position': (
        'summary.current',
        'summary.daily',
        'summary.hourly',
        'across local midnight',
        'Missing/null or out-of-horizon hours are unknown',
        'not observations',
    ),
    'get_telescope_targets': (
        'altitude is at civil dusk, not at the requested clock time',
        'sampled peak within the civil-night window',
        'UTC Unix seconds',
        'no crossing was found inside that window',
        'not a probability',
        'Missing photometry is unknown',
        'get_celestial_pos',
    ),
    'get_shooting_plan': (
        'altitude is at civil dusk, not the requested clock time',
        'does not validate weather',
        'not an all-night imaging commitment',
        '-18 degrees',
    ),
    'get_nightly_forecast': (
        'not a weather forecast',
        'at the supplied time',
        'lower first',
        'higher first',
        'not a separately solved meridian transit',
        '-18 degrees',
        "A bare date means local midnight and can belong to the previous evening's night",
    ),
}


def assert_routing_contract(listed, catalog):
    listed_by_name = {tool['name']: tool for tool in listed}
    catalog_by_name = {tool['name']: tool for tool in catalog}
    assert set(listed_by_name) == set(catalog_by_name)
    for name, entry in catalog_by_name.items():
        description = listed_by_name[name]['description']
        # Existing catalog consumers keep their summary and full-docstring fields.
        # An explicit decorator description takes precedence over its docstring.
        assert description in (entry['description'], entry['docstring']), name
        for section in SECTIONS:
            assert re.search(rf'(?m)^{re.escape(section)}:\s*\S', description), (name, section)
        follow_up = re.search(r'(?ms)^Follow-up:\s*(.*?)(?=^[A-Z][^:\n]*:|\Z)', description).group(
            1
        )
        references = set(
            re.findall(r'\b(?:get_|list_|plan_|analysis_|submit_|cancel_|light_)\w+\b', follow_up)
        )
        assert references <= set(listed_by_name), (name, references - set(listed_by_name))
        assert set(entry) == {'name', 'description', 'docstring', 'parameters', 'return_type'}
    # Both SDK and real HTTP discovery must carry the interpretation boundaries;
    # a README-only clarification would not protect a newly connected AI caller.
    for name, phrases in INTERPRETATION_GUIDANCE.items():
        description = ' '.join(listed_by_name[name]['description'].split())
        for phrase in phrases:
            assert phrase in description, (name, phrase)


@pytest.mark.asyncio
async def test_sdk_discovery_has_routing_for_every_tool():
    async with Client(mcp._mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool('get_tool_catalog', {})
    assert_routing_contract(
        [tool.model_dump() for tool in tools], result.structured_content['data']['tools']
    )


def test_http_discovery_has_the_same_routing_contract(running_mcp_server):
    host, port, path, session_id = running_mcp_server
    listed = _list_tool_entries(host, port, path, session_id)
    response = _call_tool(host, port, path, session_id, 'get_tool_catalog', {})
    content = response['result']['structuredContent']
    assert_routing_contract(listed, content['data']['tools'])


@pytest.mark.asyncio
async def test_ambiguous_tools_explain_their_actual_scope():
    async with Client(mcp._mcp) as client:
        descriptions = {tool.name: tool.description for tool in await client.list_tools()}
    required = {
        'plan_stargazing_session': ('decision.targets', 'without a second lookup'),
        'get_constellation': ('center', 'arbitrary coordinates'),
        'get_local_datetime_info': ('server environment', 'remote observing site'),
        'get_celestial_rise_set': ('calendar_day', 'next_events'),
        'list_visible_planets': ('above', 'darkness guarantees'),
        'analysis_area': ('synchronous', 'submit_area_analysis'),
        'get_best_stargazing_plan': ('existing bbox-first', 'plan_stargazing_session'),
        'get_multiday_stargazing_plan': ('existing bbox-first', 'nonconsecutive'),
        'get_weather_by_name': ('exact coordinates', 'get_weather_by_position'),
        'get_area_analysis_result': ('publication', 'TASK_RESULT_EXPIRED'),
        'cancel_area_analysis_task': ('terminal state stays unchanged', 'execution_pending'),
    }
    for name, phrases in required.items():
        assert all(phrase in descriptions[name] for phrase in phrases), name
