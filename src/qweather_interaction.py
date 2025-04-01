import requests
import gzip
import json

def fetch_gzipped_json(api_url: str, api_token: str) -> dict:
    """
    Fetches and decompresses a gzip-compressed JSON response from an API.
    Args:
        api_url (str): The API endpoint URL.
        api_token (str): The authentication token.

    Returns:
        dict: The decompressed JSON data if successful.
        None: If the request or decompression fails (prints error details).
    """
    headers = {
        "X-QW-Api-Key": api_token,
        "Accept-Encoding": "gzip"
    }

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()

        # Check if the response is gzip-compressed
        if response.headers.get("Content-Encoding") == "gzip":
            return json.loads(response.content.decode("utf-8"))
        else:
            return response.json()  # Fallback to regular JSON if not compressed

    except (requests.exceptions.RequestException, gzip.BadGzipFile, json.JSONDecodeError) as e:
        print(f"Error processing API response: {e}")
        return None
    
def qweather_get_poi(position: str, api_token: str) -> dict:
    """
    Fetches Points of Interest (POI) data from QWeather API for a given location.
    Args:
        position (str): The location name (e.g., city or district).
        api_token (str): The QWeather API authentication token.

    Returns:
        dict: POI data in JSON format if successful, None otherwise.
    """
    api = "https://geoapi.qweather.com/v2/poi/lookup?type=scenic&location={}".format(position)
    return fetch_gzipped_json(api, api_token)

def qweather_get_weather_by_coord_real_time(lon: float, lat: float, api_token: str) -> dict:
    """
    Fetches real-time weather data from QWeather API for given coordinates.
    Args:
        lon (float): Longitude of the location.
        lat (float): Latitude of the location.
        api_token (str): The QWeather API authentication token.

    Returns:
        dict: Real-time weather data in JSON format if successful, None otherwise.
    """
    api = "https://api.qweather.com/v7/weather/now?location={},{}".format(lon, lat)
    return fetch_gzipped_json(api, api_token)

def qweather_get_weather_by_coord_in_ten_days(lon: float, lat: float, api_token: str) -> dict:
    """
    Fetches 10-day weather forecast data from QWeather API for given coordinates.
    Args:
        lon (float): Longitude of the location.
        lat (float): Latitude of the location.
        api_token (str): The QWeather API authentication token.

    Returns:
        dict: 10-day weather forecast data in JSON format if successful, None otherwise.
    """
    api = "https://api.qweather.com/v7/weather/10d?location={},{}".format(lon, lat)
    return fetch_gzipped_json(api, api_token)

def qweather_get_weather_by_name(city: str, api_token: str) -> dict:
    """
    Fetches both real-time and 10-day forecast weather data for a given city name.
    Args:
        city (str): The city name (e.g., "上海市闵行区").
        api_token (str): The QWeather API authentication token.

    Returns:
        dict: A dictionary containing:
            - "real_time": Real-time weather data.
            - "ten_days_forcasts": 10-day weather forecast data.
        Returns None if any API call fails.
    """
    res = qweather_get_poi(city, api_token)
    if not res:
        return None
    
    lat, lon = res['poi'][0]['lat'], res['poi'][0]['lon']
    
    real_time_data = qweather_get_weather_by_coord_real_time(lon, lat, api_token)
    ten_days_forcasts = qweather_get_weather_by_coord_in_ten_days(lon, lat, api_token)
    
    return {
        "real_time": real_time_data,
        "ten_days_forcasts": ten_days_forcasts
    }

def qweather_get_weather_by_position(lat, lon, api_token):
    """Get weather data by position.
    Args:
        lat (float): Latitude.
        lon (float): Longitude.
        api_token (str): The QWeather API authentication token.
    Returns:
       dict: A dictionary containing the following keys:
        "real_time": Real-time weather data.
        "ten_days_forcasts": 10-day weather forecast data."
        """
    real_time_data = qweather_get_weather_by_coord_real_time(lon, lat, api_token)
    ten_days_forcasts = qweather_get_weather_by_coord_in_ten_days(lon, lat, api_token)

    return {
        "real_time": real_time_data,
        "ten_days_forcasts": ten_days_forcasts
    }

