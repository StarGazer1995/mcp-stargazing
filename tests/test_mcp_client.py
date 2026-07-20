"""MCP protocol-level tests for ``tools/call`` JSON-RPC responses."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from conftest import (
    _call_tool,
    _list_tool_entries,
    _list_tools,
    _post_sse_jsonrpc,
    _read_sse_jsonrpc_payload,
)

EXPECTED_TOOLS = {
    'analysis_area',
    'get_celestial_pos',
    'get_celestial_rise_set',
    'get_best_stargazing_plan',
    'get_constellation',
    'get_local_datetime_info',
    'get_moon_info',
    'get_nightly_forecast',
    'get_shooting_plan',
    'get_telescope_targets',
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
            'altitude',
            'azimuth',
            'moonrise',
            'moonset',
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


def test_tools_call_get_best_stargazing_plan_validation_error_stays_structured(running_mcp_server):
    """Planning validation failures should remain in the structured business payload."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(
        host,
        port,
        path,
        session_id,
        'get_best_stargazing_plan',
        {
            'south': 39.5,
            'west': 115.5,
            'north': 39.4,
            'east': 115.6,
            'time': '2024-06-15 20:00:00',
            'time_zone': 'UTC',
        },
    )

    assert payload['jsonrpc'] == '2.0'
    assert payload['id'] == 'call-get_best_stargazing_plan'
    assert 'error' not in payload, payload
    assert 'result' in payload, payload

    result = payload['result']
    assert result['isError'] is False
    structured_content = result['structuredContent']
    assert structured_content['_meta']['status'] == 'error'
    assert structured_content['error']['code'] == 'CONFIGURATION_ERROR'
    assert structured_content['error']['message'] == 'south must be less than north.'
    assert structured_content['error']['details'] == {'south': 39.5, 'north': 39.4}
    assert json.loads(result['content'][0]['text']) == structured_content


def test_tools_list_matches_get_tool_catalog_names(running_mcp_server):
    """`tools/list` and `get_tool_catalog` should expose the same registered tool names."""
    host, port, path, session_id = running_mcp_server
    listed_tools = _list_tools(host, port, path, session_id)
    payload = _call_tool(host, port, path, session_id, 'get_tool_catalog', {})

    catalog_data = _assert_success_tool_payload(payload, expected_id='call-get_tool_catalog')
    catalog_tools = catalog_data['tools']

    assert {tool['name'] for tool in catalog_tools} == listed_tools


def test_tools_list_matches_get_tool_catalog_descriptions_and_parameters(running_mcp_server):
    """`tools/list` should stay aligned with the wrapped catalog descriptions and parameters."""
    host, port, path, session_id = running_mcp_server
    listed_tools = _list_tool_entries(host, port, path, session_id)
    payload = _call_tool(host, port, path, session_id, 'get_tool_catalog', {})

    catalog_data = _assert_success_tool_payload(payload, expected_id='call-get_tool_catalog')
    catalog_by_name = {tool['name']: tool for tool in catalog_data['tools']}
    listed_by_name = {tool['name']: tool for tool in listed_tools}

    assert set(listed_by_name) == set(catalog_by_name)

    for tool_name, catalog_tool in catalog_by_name.items():
        listed_tool = listed_by_name[tool_name]
        assert listed_tool['description'].startswith(catalog_tool['description'])

        input_schema = listed_tool.get('inputSchema', {})
        properties = input_schema.get('properties', {})
        required = set(input_schema.get('required', []))
        catalog_parameter_names = {param['name'] for param in catalog_tool['parameters']}
        catalog_required_names = {
            param['name'] for param in catalog_tool['parameters'] if param['required']
        }

        assert set(properties) == catalog_parameter_names
        assert required == catalog_required_names


def test_sse_tools_call_preserves_request_id(running_mcp_sse_server):
    """SSE responses should preserve the JSON-RPC request id for initialize and tool calls."""
    host, port, message_path, stream_response, _stream_conn = running_mcp_sse_server

    initialize_status = _post_sse_jsonrpc(
        host,
        port,
        message_path,
        {
            'jsonrpc': '2.0',
            'id': 'sse-init',
            'method': 'initialize',
            'params': {
                'clientInfo': {'name': 'pytest-sse-client', 'version': '1.0'},
                'capabilities': {},
                'protocolVersion': '2024-11-05',
            },
        },
    )
    assert initialize_status == 202

    initialize_payload = _read_sse_jsonrpc_payload(stream_response, expected_id='sse-init')
    assert initialize_payload['id'] == 'sse-init'
    assert 'result' in initialize_payload

    tool_status = _post_sse_jsonrpc(
        host,
        port,
        message_path,
        {'jsonrpc': '2.0', 'id': 'sse-tools-list', 'method': 'tools/list'},
    )
    assert tool_status == 202

    tools_payload = _read_sse_jsonrpc_payload(stream_response, expected_id='sse-tools-list')
    assert tools_payload['id'] == 'sse-tools-list'
    assert 'result' in tools_payload
    assert {tool['name'] for tool in tools_payload['result'].get('tools', [])} == EXPECTED_TOOLS


def test_tools_call_business_error_returns_structured_error_payload(running_mcp_server):
    """Business validation failures should stay in structuredContent, not JSON-RPC errors."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(
        host,
        port,
        path,
        session_id,
        'get_moon_info',
        {'time': 'invalid-time-format', 'time_zone': 'UTC'},
    )

    assert payload['jsonrpc'] == '2.0'
    assert payload['id'] == 'call-get_moon_info'
    assert 'error' not in payload, payload
    assert 'result' in payload, payload

    result = payload['result']
    assert result['isError'] is False
    structured_content = result['structuredContent']
    assert structured_content['_meta']['status'] == 'error'
    assert structured_content['error']['code'] == 'INVALID_TIME_FORMAT'
    assert 'invalid-time-format' in structured_content['error']['message']
    assert json.loads(result['content'][0]['text']) == structured_content


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
        'get_best_stargazing_plan',
        'get_constellation',
        'get_local_datetime_info',
        'get_moon_info',
        'get_nightly_forecast',
        'get_shooting_plan',
        'get_telescope_targets',
        'get_tool_catalog',
        'get_weather_by_name',
        'get_weather_by_position',
        'light_pollution_map',
        'list_visible_planets',
    }
    assert tools == expected
