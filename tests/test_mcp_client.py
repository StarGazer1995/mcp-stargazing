"""MCP protocol-level tests — call tools via ``tools/call`` JSON-RPC on a live server."""

from conftest import _call_tool, _list_tools


def test_tools_call_get_tool_catalog(running_mcp_server):
    """Call ``get_tool_catalog`` through the MCP protocol and check the response."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(host, port, path, session_id, 'get_tool_catalog', {})

    assert 'result' in payload, f'Expected result, got: {payload}'
    result = payload['result']
    # FastMCP returns the tool result inside result.content[0].text as JSON string
    assert 'content' in result, f'Expected content in result: {result}'


def test_tools_call_local_datetime(running_mcp_server):
    """Call ``get_local_datetime_info`` through the MCP protocol."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(host, port, path, session_id, 'get_local_datetime_info', {})

    assert 'result' in payload, f'Expected result, got: {payload}'
    result = payload['result']
    assert 'content' in result


def test_tools_call_celestial_pos(running_mcp_server):
    """Call ``get_celestial_pos`` through the MCP protocol with valid parameters."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(
        host,
        port,
        path,
        session_id,
        'get_celestial_pos',
        {
            'celestial_object': 'sun',
            'lon': -74.0,
            'lat': 40.0,
            'time': '2024-06-15 12:00:00',
            'time_zone': 'America/New_York',
        },
    )

    assert 'result' in payload, f'Expected result, got: {payload}'


def test_tools_call_moon_info(running_mcp_server):
    """Call ``get_moon_info`` through the MCP protocol with valid parameters."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(
        host,
        port,
        path,
        session_id,
        'get_moon_info',
        {'time': '2024-06-15 12:00:00', 'time_zone': 'UTC'},
    )

    assert 'result' in payload, f'Expected result, got: {payload}'


def test_tools_call_invalid_tool_name(running_mcp_server):
    """Calling a non-existent tool returns a JSON-RPC error."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(host, port, path, session_id, 'non_existent_tool', {})

    # Should either contain an error at the JSON-RPC level, or the result may
    # contain an isError flag — both indicate the tool was not found.
    has_error = 'error' in payload or (
        'result' in payload
        and isinstance(payload['result'], dict)
        and payload['result'].get('isError')
    )
    assert has_error, f'Expected error for invalid tool, got: {payload}'


def test_tools_call_missing_required_params(running_mcp_server):
    """Calling ``get_celestial_pos`` without required params returns an error."""
    host, port, path, session_id = running_mcp_server
    payload = _call_tool(
        host,
        port,
        path,
        session_id,
        'get_celestial_pos',
        {},  # no arguments at all
    )

    # FastMCP should return an error about missing required parameters
    has_error = 'error' in payload or (
        'result' in payload
        and isinstance(payload['result'], dict)
        and payload['result'].get('isError')
    )
    assert has_error, f'Expected error for missing params, got: {payload}'


def test_tools_list_returns_all_expected_tools(running_mcp_server):
    """Verify ``tools/list`` includes all 12 registered tools."""
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
    missing = expected - tools
    assert not missing, f'Missing tools: {sorted(missing)}'
