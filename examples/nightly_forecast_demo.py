import sys
import os
from datetime import datetime
import pytz

# Add project root to python path so we can import src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.celestial import calculate_nightly_forecast
from src.utils import create_earth_location

def main():
    print("Nightly Stargazing Forecast")
    print("===========================")
    
    # Location: New York City
    lat = 40.7128
    lon = -74.0060
    city = "New York City"
    
    # Current Time (UTC)
    now = datetime.now(pytz.UTC)
    
    print(f"Location: {city} (Lat: {lat}, Lon: {lon})")
    print(f"Date: {now.strftime('%Y-%m-%d')}")
    print("-" * 60)
    
    loc = create_earth_location(lat, lon)
    
    try:
        forecast = calculate_nightly_forecast(loc, now, limit=20)
        
        # 1. Moon
        moon = forecast['moon_phase']
        print(f"Moon Phase: {moon['phase_name']} ({moon['illumination']*100:.1f}%)")
        print("-" * 60)
        
        # 2. Planets
        planets = forecast['planets']
        if planets:
            print("Visible Planets:")
            for p in planets:
                print(f"  * {p['name']:<10} Alt: {p['altitude']:.1f}°  Az: {p['azimuth']:.1f}°")
        else:
            print("No planets currently visible.")
        print("-" * 60)
        
        # 3. Deep Sky
        print(f"{'Object':<12} | {'Type':<12} | {'Mag':<5} | {'Alt':<5} | {'Score'}")
        print("-" * 60)
        
        for obj in forecast['deep_sky']:
            name = obj['name']
            otype = obj['type'][:12] # Truncate
            mag = f"{obj['magnitude']:.1f}"
            alt = f"{obj['altitude']:.0f}°"
            score = f"{obj['score']:.1f}"
            
            print(f"{name:<12} | {otype:<12} | {mag:<5} | {alt:<5} | {score}")
            
    except Exception as e:
        print(f"Error generating forecast: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
