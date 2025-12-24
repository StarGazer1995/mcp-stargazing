import os
from src.server_instance import mcp
from src.qweather_interaction import qweather_get_weather_by_name, qweather_get_weather_by_position

from src.response import format_response

@mcp.tool()
def get_weather_by_name(place_name: str):
    """
    Fetches weather data for a specified location by its name using the QWeather API.

    Args:
        place_name (str): The name of the location (e.g., city, region) for which weather data is requested.

    Returns:
        Dict with keys "data", "_meta". "data" contains the weather data.

    Raises:
        ValueError: If the `QWEATHER_API_KEY` environment variable is not set, preventing API access.
    """
    QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", None)
    if QWEATHER_API_KEY is None:
        raise ValueError("QWEATHER_API_KEY environment variable not set.")
    result = qweather_get_weather_by_name(place_name, QWEATHER_API_KEY)
    return format_response(result)

@mcp.tool()
def get_weather_by_position(lat: float, lon: float):
    """
    Fetches weather data for a specified location by its geographic coordinates (latitude and longitude) using the QWeather API.

    Args:
        lat (float): The latitude of the location for which weather data is requested.
        lon (float): The longitude of the location for which weather data is requested.

    Returns:
        Dict with keys "data", "_meta". "data" contains the weather data.

    Raises:
        ValueError: If the `QWEATHER_API_KEY` environment variable is not set, preventing API access.
    """
    QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", None)
    if QWEATHER_API_KEY is None:
        raise ValueError("QWEATHER_API_KEY environment variable not set.")
    result = qweather_get_weather_by_position(lat, lon, QWEATHER_API_KEY)
    return format_response(result)
