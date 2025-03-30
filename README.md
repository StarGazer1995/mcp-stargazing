# mcp-stargazing

Calculate the altitude, rise, and set times of celestial objects (Sun, Moon, planets, stars, and deep-space objects) for any location on Earth, with optional light pollution analysis.

## Features
- **Altitude/Azimuth Calculation**: Get elevation and compass direction for any celestial object.
- **Rise/Set Times**: Determine when objects appear/disappear above the horizon.
- **Light Pollution Analysis**: Load and analyze light pollution maps (GeoTIFF format).
- **Supports**:
  - Solar system objects (Sun, Moon, planets)
  - Stars (e.g., "sirius")
  - Deep-space objects (e.g., "andromeda", "orion_nebula")
- **Time Zone Aware**: Works with local or UTC times.

## Installation
```bash
pip install astropy pytz numpy astroquery rasterio geopy
```

## Usage

### Calculate Altitude/Azimuth
```python src/main.py
from src.celestial import celestial_pos
from astropy.coordinates import EarthLocation
import pytz
from datetime import datetime

# Observer location (New York)
location = EarthLocation(lat=40.7128, lon=-74.0060)

# Time (local timezone-aware)
local_time = pytz.timezone("America/New_York").localize(datetime(2023, 10, 1, 12, 0))
altitude, azimuth = celestial_pos("sun", location, local_time)
print(f"Sun Position: Altitude={altitude:.1f}°, Azimuth={azimuth:.1f}°")
```

### Calculate Rise/Set Times
```python src/main.py
from src.celestial import celestial_rise_set

rise, set_ = celestial_rise_set("andromeda", location, local_time.date())
print(f"Andromeda: Rise={rise.iso}, Set={set_.iso}")
```

### Load Light Pollution Map
```python src/light_pollution.py
from src.light_pollution import load_map

# Load a GeoTIFF light pollution map
vriis_data, bounds, crs, transform = load_map("path/to/map.tif")
print(f"Map Bounds: {bounds}")
```

## API Reference

### `celestial_pos(celestial_object, observer_location, time)` (`src/celestial.py`)
- **Inputs**:
  - `celestial_object`: Name (e.g., `"sun"`, `"andromeda"`).
  - `observer_location`: `EarthLocation` object.
  - `time`: `datetime` (timezone-aware) or Astropy `Time`.
- **Returns**: `(altitude_degrees, azimuth_degrees)`.

### `celestial_rise_set(celestial_object, observer_location, date, horizon=0.0)` (`src/celestial.py`)
- **Inputs**: 
  - `date`: Timezone-aware `datetime`.
  - `horizon`: Horizon elevation (default: 0°).
- **Returns**: `(rise_time, set_time)` as UTC `Time` objects.

### `load_map(map_path)` (`src/light_pollution.py`)
- **Inputs**:
  - `map_path`: Path to GeoTIFF file.
- **Returns**: Tuple `(vriis_data, bounds, crs, transform)` for light pollution analysis.

## Testing
Run tests with:
```bash
pytest tests/
```

### Key Test Cases (`tests/test_celestial.py`)
```python tests/test_celestial.py
def test_calculate_altitude_deepspace():
    """Test deep-space object resolution."""
    altitude, _ = celestial_pos("andromeda", NYC, Time.now())
    assert -90 <= altitude <= 90

def test_calculate_rise_set_sun():
    """Validate Sun rise/set times."""
    rise, set_ = celestial_rise_set("sun", NYC, datetime(2023, 10, 1))
    assert rise < set_
```

## Project Structure
```
.
├── src/
│   ├── celestial.py          # Core celestial calculations
│   ├── light_pollution.py    # Light pollution map utilities
│   ├── utils.py              # Time/location helpers
│   └── main.py               # CLI entry point
├── tests/
│   ├── test_celestial.py
│   └── test_utils.py
└── README.md
```

## Future Work
- Add support for comets/asteroids.
- Optimize SIMBAD queries for offline use.
- Integrate light pollution data into visibility predictions.

### Key Updates:
1. **Light Pollution**: Added `light_pollution.py` to features and API reference.
2. **Dependencies**: Added `rasterio` and `geopy` to installation instructions.
3. **Project Structure**: Clarified file roles and test coverage.
```