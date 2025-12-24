import argparse
import os
import sys
from astropy.utils import iers
from astropy.time import Time
from astroquery.simbad import Simbad
import astropy.units as u
from astropy.coordinates import SkyCoord

def download_data(proxy=None):
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        # Also set ALL_PROXY for some libs
        os.environ["ALL_PROXY"] = proxy
        print(f"Using proxy: {proxy}")
        
    # Test connectivity first
    import requests
    try:
        print("Testing connectivity to google.com...")
        resp = requests.get("https://www.google.com", timeout=5)
        print(f"Connectivity test: {resp.status_code}")
    except Exception as e:
        print(f"Connectivity test failed: {e}")

    print("Downloading IERS data (Earth rotation parameters)...")
    try:
        # Use simple download method which usually triggers caching
        # Old method: iers.IERS_A.open(...)
        # New approach: just access the table, it auto-downloads if needed
        # Or force download via utils.data
        from astropy.utils.data import download_file
        iers_a_url = iers.IERS_A_URL
        if not iers_a_url:
             iers_a_url = 'https://datacenter.iers.org/data/9/finals2000A.all'
        
        print(f"Downloading IERS_A from {iers_a_url}...")
        download_file(iers_a_url, cache=True)
        print("IERS data downloaded successfully (to cache).")
    except Exception as e:
        print(f"Error downloading IERS data: {e}")

    print("Pre-warming Simbad cache for common objects...")
    common_objects = ["Sirius", "Betelgeuse", "Rigel", "Andromeda", "Pleiades"]
    for obj in common_objects:
        try:
            print(f"Querying {obj}...")
            Simbad.query_object(obj)
        except Exception as e:
            print(f"Error querying {obj}: {e}")
            
    print("All data downloads attempted.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-download astronomy data")
    parser.add_argument("--proxy", type=str, help="Proxy URL (e.g., http://127.0.0.1:9981)")
    args = parser.parse_args()
    
    download_data(args.proxy)
