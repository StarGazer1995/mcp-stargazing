from conftest import _list_tools

EXPECTED_TOOLS = {
    'analysis_area',
    'get_celestial_pos',
    'get_celestial_rise_set',
    'get_best_stargazing_plan',
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


def test_mcp_startup_lists_expected_tools(running_mcp_server):
    """Verify the started MCP server advertises the expected tool names via ``tools/list``."""
    host, port, path, session_id = running_mcp_server
    listed_tools = _list_tools(host, port, path, session_id)
    assert listed_tools == EXPECTED_TOOLS, (
        f'Expected tools/list to match exactly. expected={sorted(EXPECTED_TOOLS)} '
        f'actual={sorted(listed_tools)}'
    )
