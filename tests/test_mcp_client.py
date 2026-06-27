"""MCP protocol-level tests for ``tools/call`` JSON-RPC responses."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from conftest import _call_tool, _list_tools

EXPECTED_TOOLS = {
    'analysis_area',
    'get_celestial_pos',
    'get_celestial_rise_set',
    'get_constellation',
    'get_local_datetime_info',
    'get_moon_info',
    'get_nightly_forecast',
    'get_tool_catalog',
    'get_weather_by_name',
    'get_weather_by_position',
    'light_pollution_map',
    'list_visible_planets',
}


def _assert_success_tool_payload(payload: dict, expected_id: str) -> dict:
    """Validate a successful ``tools/call`` JSON-RPC payload and return its data."""
    assert payload['jsonrpc'] == '2.0'
    assert payload['id'] == expected_id
    assert 'error' not in payload, payload
    assert 'result' in payload, payload

    result = payload['result']
    assert result['isError'] is False

    content = result['content']
    assert isinstance(content, list) and content, result
    assert content[0]['type'] == 'text'

    structured_content = result['structuredContent']
    parsed_text_payload = json.loads(content[0]['text'])
    assert parsed_text_payload == structured_content
    assert structured_content['_meta']['status'] == 'success'

    return structured_content['data']


def _assert_error_tool_payload(payload: dict, expected_id: str) -> str:
    """Validate an error ``tools/call`` JSON-RPC payload and return its text message."""
    assert payload['jsonrpc'] == '2.0'
    assert payload['id'] == expected_id
    assert 'result' in payload or 'error' in payload, payload

    if 'error' in payload:
        error = payload['error']
        assert 'message' in error
        return error['message']

    result = payload['result']
    assert result['isError'] is True

    content = result['content']
    assert isinstance(content, list) and content, result
    assert content[0]['type'] == 'text'
    assert isinstance(content[0]['text'], str) and content[0]['text']
    return content[0]['text']


@pytest.mark.parametrize(
    ('tool_name', 'arguments'),
    [
        ('get_local_datetime_info', {}),
        (
            'get_celestial_pos',
            {
                'celestial_object': 'sun',
                'lon': -74.0,
                'lat': 40.0,
                'time': '2024-06-15 12:00:00',
                'time_zone': 'America/New_York',
            },
        ),
        ('get_moon_info', {'time': '2024-06-15 12:00:00', 'time_zone': 'UTC'}),
    ],
)
def test_tools_call_success_returns_expected_payload_shape(
    running_mcp_server, tool_name: str, arguments: dict
):
    """Successful ``tools/call`` responses expose stable JSON-RPC and business payload fields."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(host, port, path, session_id, tool_name, arguments)

    data = _assert_success_tool_payload(payload, expected_id=f'call-{tool_name}')

    if tool_name == 'get_local_datetime_info':
        assert set(data) == {'current_time', 'time_zone'}
        datetime.fromisoformat(data['current_time'])
        assert isinstance(data['time_zone'], str) and data['time_zone']
    elif tool_name == 'get_celestial_pos':
        assert set(data) == {'altitude', 'azimuth'}
        assert isinstance(data['altitude'], float)
        assert isinstance(data['azimuth'], float)
        assert -90.0 <= data['altitude'] <= 90.0
        assert 0.0 <= data['azimuth'] <= 360.0
    else:
        assert set(data) == {
            'illumination',
            'phase_name',
            'age_days',
            'elongation',
            'earth_distance',
        }
        assert 0.0 <= data['illumination'] <= 1.0
        assert isinstance(data['phase_name'], str) and data['phase_name']
        assert data['age_days'] >= 0.0
        assert data['elongation'] >= 0.0
        assert data['earth_distance'] > 0.0


def test_tools_call_get_tool_catalog_returns_expected_tools(running_mcp_server):
    """``get_tool_catalog`` returns the wrapped catalog payload through ``tools/call``."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(host, port, path, session_id, 'get_tool_catalog', {})

    data = _assert_success_tool_payload(payload, expected_id='call-get_tool_catalog')

    assert set(data) == {'tools'}
    assert isinstance(data['tools'], list)
    tool_names = {tool['name'] for tool in data['tools']}
    assert tool_names == EXPECTED_TOOLS

    weather_tool = next(tool for tool in data['tools'] if tool['name'] == 'get_weather_by_name')
    assert weather_tool['description'] == '通过地点名称获取综合天气（当前 + 小时预报 + 日预报）。'
    assert any(param['name'] == 'place_name' for param in weather_tool['parameters'])
    assert any(param['name'] == 'provider' for param in weather_tool['parameters'])


@pytest.mark.parametrize(
    ('tool_name', 'arguments', 'expected_snippets'),
    [
        ('non_existent_tool', {}, ('Unknown tool: non_existent_tool',)),
        (
            'get_celestial_pos',
            {},
            ('Missing required argument', 'celestial_object', 'time_zone'),
        ),
    ],
)
def test_tools_call_error_returns_specific_failure_reason(
    running_mcp_server, tool_name: str, arguments: dict, expected_snippets: tuple[str, ...]
):
    """Error ``tools/call`` responses should expose the concrete failure reason."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(host, port, path, session_id, tool_name, arguments)

    message = _assert_error_tool_payload(payload, expected_id=f'call-{tool_name}')

    for snippet in expected_snippets:
        assert snippet in message


def test_tools_list_returns_all_expected_tools(running_mcp_server):
    """Verify ``tools/list`` includes all expected registered tools."""
    host, port, path, session_id = running_mcp_server
    tools = _list_tools(host, port, path, session_id)

    expected = {
        'analysis_area',
        'get_celestial_pos',
        'get_celestial_rise_set',
        'get_constellation',
        'get_local_datetime_info',
        'get_moon_info',
        'get_nightly_forecast',
        'get_tool_catalog',
        'get_weather_by_name',
        'get_weather_by_position',
        'light_pollution_map',
        'list_visible_planets',
    }
    assert tools == expected
