from typing import Any, Dict
from src.server_instance import mcp
from src.response import format_response

@mcp.tool()
def get_tool_catalog() -> Dict[str, Any]:
    """Get metadata for all registered MCP tools.

    Returns:
        Dict with keys "data", "_meta". "data" contains a list of tool metadata objects.
    """
    tool_catalog = mcp.get_tool_catalog()
    return format_response({"tools": tool_catalog})
