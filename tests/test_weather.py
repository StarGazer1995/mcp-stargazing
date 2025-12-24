import pytest
from unittest.mock import patch
import os
from src.functions.weather.impl import get_weather_by_name, get_weather_by_position

def test_get_weather_by_name_no_api_key():
    with patch.dict(os.environ, clear=True):
        if "QWEATHER_API_KEY" in os.environ:
            del os.environ["QWEATHER_API_KEY"]
            
        with pytest.raises(ValueError, match="QWEATHER_API_KEY"):
            # Use .fn to call the underlying function
            get_weather_by_name.fn("Beijing")

def test_get_weather_by_name_success():
    with patch.dict(os.environ, {"QWEATHER_API_KEY": "fake_key"}), \
         patch("src.functions.weather.impl.qweather_get_weather_by_name") as mock_api:
        mock_api.return_value = {"weather": "sunny"}
        result = get_weather_by_name.fn("Beijing")
        
        assert "data" in result
        assert result["data"] == {"weather": "sunny"}
        assert result["_meta"]["status"] == "success"
        mock_api.assert_called_with("Beijing", "fake_key")

def test_get_weather_by_position_success():
    with patch.dict(os.environ, {"QWEATHER_API_KEY": "fake_key"}), \
         patch("src.functions.weather.impl.qweather_get_weather_by_position") as mock_api:
        mock_api.return_value = {"temp": 20}
        result = get_weather_by_position.fn(40.0, 116.0)
        
        assert "data" in result
        assert result["data"] == {"temp": 20}
        mock_api.assert_called_with(40.0, 116.0, "fake_key")
