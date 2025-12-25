import sys
import os
from datetime import datetime
import pytz

# Add project root to python path so we can import src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.celestial import get_constellation_center
from src.utils import create_earth_location

def main():
    print("Constellation Finder Demo")
    print("=========================")
    
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
    
    targets = ["Orion", "Ursa Major", "Cassiopeia", "Southern Cross", "Polaris"]
    
    print(f"{'Constellation':<15} | {'Altitude':<10} | {'Azimuth':<10} | {'Status'}")
    print("-" * 65)
    
    for target in targets:
        try:
            info = get_constellation_center(target, loc, now)
            alt = info["altitude"]
            az = info["azimuth"]
            status = "Visible" if alt > 0 else "Below Horizon"
            print(f"{target:<15} | {alt:<10.1f} | {az:<10.1f} | {status}")
        except Exception as e:
            print(f"{target:<15} | {'Error: ' + str(e)}")

if __name__ == "__main__":
    main()
