from typing import Any

from src.response import format_response
from src.server_instance import mcp


@mcp.tool()
def get_tool_catalog() -> dict[str, Any]:
    """Get metadata for all registered MCP tools.

    Returns:
        Dict with keys "data", "_meta". "data" contains a list of tool metadata objects.
    """
    tool_catalog = mcp.get_tool_catalog()
    return format_response({'tools': tool_catalog})
