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

    Use when: you need the server environment's current time and local timezone.
    Do not use when: you need time at a remote observing site or already have its timezone.
    Requires: no inputs; local means the server environment, not the user's observing site.
    Follow-up: use the observing site's explicit time_zone in celestial and
        plan_stargazing_session requests; do not infer it from the server timezone.

    Returns:
        Dict with keys "data", "_meta". "data" contains "current_time" (ISO string).
    """
    set_request_id()
    tz = get_localzone()
    current_time = datetime.datetime.now(tz)
    # Include timezone information explicitly so the tool matches its docstring
    tz_name = getattr(tz, 'zone', None) or str(tz)
    return format_response({'current_time': current_time.isoformat(), 'time_zone': tz_name})
