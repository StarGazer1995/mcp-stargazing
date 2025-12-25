import sys
import os
from datetime import datetime
import pytz

# Add project root to python path so we can import src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.celestial import get_visible_planets
from src.utils import create_earth_location

def main():
    print("Visible Planets Demo")
    print("====================")
    
    # Example Location: New York City
    lat = 40.7128
    lon = -74.0060
    city = "New York City"
    
    # Current Time (UTC)
    now = datetime.now(pytz.UTC)
    
    print(f"Location: {city} (Lat: {lat}, Lon: {lon})")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("-" * 50)
    
    loc = create_earth_location(lat, lon)
    planets = get_visible_planets(loc, now)
    
    if not planets:
        print("No planets are currently above the horizon.")
    else:
        print(f"{'Planet':<10} | {'Altitude':<10} | {'Azimuth':<10}")
        print("-" * 50)
        for p in planets:
            print(f"{p['name']:<10} | {p['altitude']:<10.1f} | {p['azimuth']:<10.1f}")
            
if __name__ == "__main__":
    main()
