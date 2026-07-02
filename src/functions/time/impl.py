import datetime
from typing import Any

from tzlocal import get_localzone

from src.logging_config import set_request_id
from src.response import format_response
from src.server_instance import mcp


@mcp.tool()
def get_local_datetime_info() -> dict[str, Any]:
    """
    Retrieve the current datetime and timezone.

    Returns:
        Dict with keys "data", "_meta". "data" contains "current_time" (ISO string).
    """
    set_request_id()
    tz = get_localzone()
    current_time = datetime.datetime.now(tz)
    # Include timezone information explicitly so the tool matches its docstring
    tz_name = getattr(tz, 'zone', None) or str(tz)
    return format_response({'current_time': current_time.isoformat(), 'time_zone': tz_name})
