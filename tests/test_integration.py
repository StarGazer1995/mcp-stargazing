import pytest
from src.server_instance import mcp
# Import implementation modules to trigger registration
import src.functions.celestial.impl
import src.functions.weather.impl
import src.functions.places.impl
import src.functions.time.impl

def test_tools_registered():
    """Verify that all expected tools are registered with the MCP server instance."""
    
    # FastMCP stores tools in _tool_manager
    # We can inspect the internal dictionary if public API is not available
    # Based on debug output, mcp has _tool_manager
    
    # Try to get tools from _tool_manager if possible, or fall back to listing what we can find
    if hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
        registered_tools = list(mcp._tool_manager._tools.keys())
    else:
        # Fallback: maybe list_tools is available on mcp directly in some versions?
        # But we saw _list_tools in dir(mcp)
        # Let's try to assume _tool_manager._tools exists based on FastMCP source patterns
        registered_tools = list(mcp._tool_manager._tools.keys())

    expected_tools = [
        "get_celestial_pos",
        "get_celestial_rise_set",
        "get_weather_by_name",
        "get_weather_by_position",
        "analysis_area",
        "get_local_datetime_info"
    ]
    
    for tool_name in expected_tools:
        assert tool_name in registered_tools, f"Tool '{tool_name}' not found in registered tools: {registered_tools}"
