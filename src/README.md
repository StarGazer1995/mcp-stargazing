
# mcp-stargazing

Calculate the altitude, rise, and set times of celestial objects (Sun, Moon, planets, stars, and deep-space objects) for any location on Earth.

## Features
- **Solar System Objects**: Sun, Moon, and planets.
- **Deep-Space Objects**: Stars (e.g., "sirius"), galaxies (e.g., "andromeda"), and nebulae.
- **Precise Calculations**:
  - Altitude/azimuth angles.
  - Rise/set times with custom horizon elevation.
- **Time Zone Support**: Works with local or UTC times.

## Installation
```bash
pip install astropy pytz numpy astroquery
```

## Usage

### Calculate Object Position
```python src/main.py
from src.celestial import celestial_pos
from astropy.coordinates import EarthLocation
from datetime import datetime
import pytz

# Observer location (New York)
location = EarthLocation(lat=40.7128, lon=-74.0060, height=0)

# Time (local timezone-aware)
local_time = pytz.timezone("America/New_York").localize(datetime(2023, 10, 1, 12, 0))
altitude, azimuth = celestial_pos("andromeda", location, local_time)
print(f"Andromeda: Altitude={altitude:.1f}°, Azimuth={azimuth:.1f}°")
```

### Calculate Rise/Set Times
```python src/main.py
from src.celestial import celestial_rise_set

rise, set_ = celestial_rise_set("moon", location, local_time.date(), horizon=5.0)
print(f"Moon: Rise={rise.iso}, Set={set_.iso}")
```

## API Reference (`src/celestial.py`)

### Core Functions
```python src/celestial.py
def celestial_pos(
    celestial_object: str,  # "sun", "moon", "andromeda", etc.
    observer_location: EarthLocation,
    time: Union[Time, datetime]  # Timezone-aware if datetime
) -> Tuple[float, float]:
    """Returns (altitude_degrees, azimuth_degrees)."""
```

```python src/celestial.py
def celestial_rise_set(
    celestial_object: str,
    observer_location: EarthLocation,
    date: datetime,  # Timezone-aware
    horizon: float = 0.0
) -> Tuple[Optional[Time], Optional[Time]]:
    """Returns (rise_time_utc, set_time_utc)."""
```

## Testing
Run all tests:
```bash
pytest tests/
```

### Key Test Cases
```python tests/test_celestial.py
def test_deepspace_altitude():
    """Test altitude calculation for Andromeda Galaxy."""
    altitude, _ = celestial_pos("andromeda", NYC, Time.now())
    assert -90 <= altitude <= 90

def test_polar_night():
    """Verify Sun never rises in Arctic winter."""
    polar_loc = EarthLocation(lat=90*u.deg, lon=0)
    rise, set_ = celestial_rise_set("sun", polar_loc, datetime(2023, 12, 22))
    assert rise is None and set_ is None
```

## Project Structure
```
.
├── src/
│   ├── celestial.py     # Core calculations (rise/set, altitude)
│   └── utils.py         # Timezone/location helpers
├── tests/
│   ├── test_celestial.py  # Unit tests for celestial.py
│   └── test_utils.py     # Tests for utility functions
└── README.md
```

## Future Work
- Add offline catalog for deep-space objects.
- Support for comets/asteroids.
- Web API interface.
