from typing import Dict, Any
import datetime
from tzlocal import get_localzone
from src.server_instance import mcp
from src.response import format_response

@mcp.tool()
def get_local_datetime_info() -> Dict[str, Any]:
    """
    Retrieve the current datetime and timezone.

    Returns:
        Dict with keys "data", "_meta". "data" contains "current_time" (ISO string).
    """
    tz = get_localzone()
    current_time = datetime.datetime.now(tz)
    return format_response({
        "current_time": current_time.isoformat()
    })
