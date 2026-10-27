from typing import Any

from src.logging_config import set_request_id
from src.response import format_response
from src.server_instance import mcp


@mcp.tool()
def get_tool_catalog() -> dict[str, Any]:
    """Get metadata for all registered MCP tools.

    Use when: you need the wrapped catalog with full documentation and parameter summaries.
    Do not use when: your client only needs standard MCP tools/list discovery or a business result.
    Requires: no inputs; this call discovers tools and does not perform observing analysis.
    Follow-up: choose a tool from its use/do-not-use guidance; plan_stargazing_session
        is the primary entry for complete observing decisions.

    Returns:
        Dict with keys "data", "_meta". "data.tools" contains tool metadata objects.
    """
    set_request_id()
    tool_catalog = mcp.get_tool_catalog()
    return format_response({'tools': tool_catalog})
