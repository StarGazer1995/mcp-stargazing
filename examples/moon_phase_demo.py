import sys
import os
from datetime import datetime, timedelta
import pytz

# Add project root to python path so we can import src
# Assuming this script is run from the project root or examples/ directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.celestial import calculate_moon_info

def main():
    print("Moon Phase Demo")
    print("===============")
    
    # Use current time in UTC
    start_date = datetime.now(pytz.UTC)
    
    print(f"Calculating moon phases for the next 30 days starting from {start_date.date()}...\n")
    print(f"{'Date':<12} | {'Phase':<16} | {'Illum %':<8} | {'Age (days)':<10}")
    print("-" * 55)
    
    for i in range(0, 30): 
        date = start_date + timedelta(days=i)
        info = calculate_moon_info(date)
        
        phase = info['phase_name']
        illum = info['illumination'] * 100
        age = info['age_days']
        
        print(f"{date.strftime('%Y-%m-%d'):<12} | {phase:<16} | {illum:8.1f} | {age:10.1f}")

if __name__ == "__main__":
    main()
