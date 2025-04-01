import numpy as np
import rasterio
from rasterio.windows import Window

from rasterio.transform import rowcol

def get_light_pollution_around_location(
    raster_path: str,
    lat: float,
    lon: float,
    radius_km: float = 1.0
) -> np.ndarray:
    """
    Extract light pollution data within a radius (default: 1km) of a location.
    Args:
        raster_path: Path to the raster file (e.g., GeoTIFF).
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        radius_km: Radius in kilometers (default: 1km).
    Returns:
        Numpy array of light pollution values in the region.
    """
    with rasterio.open(raster_path) as src:
        # Step 1: Convert lat/lon to raster's CRS (if not already matched)
        if src.crs is None:
            raise ValueError("Raster has no CRS. Ensure it is georeferenced.")
        
        # Step 2: Calculate bounding box (1km around the point)
        # Approximate delta in degrees (1km ≈ 0.00899 degrees at equator)
        delta_deg = radius_km / 111.32  # Rough approximation
        min_lon, max_lon = lon - delta_deg, lon + delta_deg
        min_lat, max_lat = lat - delta_deg, lat + delta_deg
        print(min_lat, max_lat, min_lon, max_lon)

        # Step 3: Convert bounding box to pixel coordinates
        row_min, col_min = rowcol(src.transform, xs=[min_lon], ys=[min_lat])
        row_max, col_max = rowcol(src.transform, xs=[max_lon], ys=[max_lat])
        print(row_min, row_max, col_min, col_max)

        # Step 4: Read the windowed data
        window = Window.from_slices(
            rows=(row_max[0], row_min[0]),
            cols=(col_min[0], col_max[0])
        )
        print("window: ", window)
        data = src.read(1, window=window)
        return data

def viirs_to_bortle(radiance: float) -> int:
    """
    Convert VIIRS radiance (nW/cm²/sr) to Bortle scale class (1-9).
    Args:
        radiance: VIIRS radiance value.
    Returns:
        Bortle class (1-9).
    """
    if radiance < 0.11:
        return 1
    elif 0.11 <= radiance < 0.33:
        return 2
    elif 0.33 <= radiance < 0.60:
        return 3
    elif 0.60 <= radiance < 1.00:
        return 4
    elif 1.00 <= radiance < 2.00:
        return 5
    elif 2.00 <= radiance < 5.00:
        return 6
    elif 5.00 <= radiance < 10.0:
        return 7
    elif 10.00 <= radiance < 50.00:
        return 8
    else:
        return 9

# Vectorized version for numpy arrays
def viirs_to_bortle_array(radiance_array: np.ndarray) -> np.ndarray:
    """Convert an array of VIIRS radiance values to Bortle classes."""
    bortle_classes = np.zeros_like(radiance_array, dtype=int)
    vectorized_bortle = np.vectorize(viirs_to_bortle)
    bortle_classes = vectorized_bortle(radiance_array)
    return bortle_classes

def get_bortle_scale_light_pollution_given_location(
        lat: float,
        lon: float,
        raster_path: str = None,
        radius_km: float = 10.0,
) -> float:
    """Get the Bortle scale light pollution for a given location."""
    data = get_light_pollution_around_location(
        raster_path=raster_path,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    bortle_data = viirs_to_bortle_array(data)
    return np.nanmean(bortle_data)

if __name__ == "__main__":

    MAP_PATH ="/Users/gongzhao/Downloads/VNL_npp_2023_global_vcmslcfg_v2_c202402081600.minimum.dat.tif"
    # Usage (example: Somewhere in Shanghai)
    data = get_light_pollution_around_location(
        raster_path=MAP_PATH,
        lat=31.000,  # Latitude
        lon=121.500,  # Longitude
        radius_km=10.0,
    )
    print("Mean bortle scale: ", np.nanmean(data))