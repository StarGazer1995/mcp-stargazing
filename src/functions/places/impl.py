from typing import Dict, Any, List
import asyncio
from pathlib import Path
from src.server_instance import mcp
from src.placefinder import StargazingPlaceFinder, get_light_pollution_grid
from src.cache import ANALYSIS_CACHE, generate_cache_key

from src.response import format_response

@mcp.tool()
async def light_pollution_map(
    south: float, west: float, north: float, east: float,
    zoom: int = 10
) -> Dict[str, Any]:
    """Get light pollution data for a specific area.
    
    Returns a grid of light pollution data points including brightness, Bortle class, and SQM.
    
    Args:
        south, west, north, east: Bounding box coordinates.
        zoom: Zoom level for the grid resolution (default: 10). Higher zoom means more detailed grid.
    """
    def _compute():
        return get_light_pollution_grid(north=north, south=south, east=east, west=west, zoom=zoom)

    result = await asyncio.to_thread(_compute)
    return format_response(result)

@mcp.tool()
async def analysis_area(
    south: float, west: float, north: float, east: float,
    max_locations: int = 30,
    min_height_diff: float = 100.0,
    road_radius_km: float = 10.0,
    network_type: str = 'drive',
    db_config_path: str = None,
    page: int = 1,
    page_size: int = 10
) -> Dict[str, Any]:
    """Analyze a geographic area for suitable stargazing locations.
    
    This tool searches for dark, accessible locations with good viewing conditions.
    Results are cached based on search parameters.
    
    Args:
        south, west, north, east: Bounding box coordinates.
        max_locations: Maximum number of candidate locations to find (before pagination).
        min_height_diff: Minimum elevation difference for prominence.
        road_radius_km: Search radius for road access.
        network_type: Type of road network ('drive', 'walk', etc.).
        db_config_path: Optional path to database config.
        page: Page number (1-based).
        page_size: Number of results per page.
        
    Returns:
        Dict with keys "data", "_meta". "data" contains:
        - items: List of location results for the current page.
        - total: Total number of locations found.
        - page: Current page number.
        - page_size: Current page size.
        - resource_id: Cache key for these search parameters.
    """
    # 1. Generate Cache Key based on calculation parameters (excluding pagination)
    calc_params = {
        "south": south, "west": west, "north": north, "east": east,
        "max_locations": max_locations,
        "min_height_diff": min_height_diff,
        "road_radius_km": road_radius_km,
        "network_type": network_type,
        "db_config_path": db_config_path
    }
    resource_id = generate_cache_key(**calc_params)
    
    # 2. Check Cache
    all_results = ANALYSIS_CACHE.get(resource_id)
    
    # 3. If miss, compute (in thread)
    if all_results is None:
        def _compute():
            db_config_p = Path(db_config_path) if db_config_path else None
            stargazing_place_finder = StargazingPlaceFinder(db_config_path=db_config_p)
            results = stargazing_place_finder.analyze_area(
                south=south,
                west=west,
                north=north,
                east=east,
                min_height_diff=min_height_diff,
                road_radius_km=road_radius_km,
                max_locations=max_locations,
                network_type=network_type,
            )
            
            # Ensure results are serializable
            serialized = []
            for item in results:
                if isinstance(item, dict):
                    serialized.append(item)
                elif hasattr(item, "to_dict") and callable(item.to_dict):
                    serialized.append(item.to_dict())
                elif hasattr(item, "__dict__"):
                    serialized.append(vars(item))
                else:
                    serialized.append(str(item))
            return serialized

        all_results = await asyncio.to_thread(_compute)
        ANALYSIS_CACHE.set(resource_id, all_results)
        
    # 4. Pagination
    total = len(all_results)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Slice results (safe even if indices are out of bounds)
    page_items = all_results[start_idx:end_idx]
    
    return format_response({
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        "resource_id": resource_id
    })
