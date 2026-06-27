import asyncio
from pathlib import Path
from typing import Any

from src.cache import ANALYSIS_CACHE, generate_cache_key
from src.placefinder import StargazingPlaceFinder, get_light_pollution_grid
from src.response import MCPError, format_error, format_response
from src.schemas.places import (
    AnalysisAreaResult,
    LightPollutionGrid,
    LightPollutionGridPoint,
    StargazingLocation,
)
from src.server_instance import mcp


@mcp.tool()
async def light_pollution_map(
    south: float, west: float, north: float, east: float, zoom: int = 10
) -> dict[str, Any]:
    """Get light pollution data for a specific area.

    Returns a grid of light pollution data points including brightness, Bortle class, and SQM.

    Args:
        south, west, north, east: Bounding box coordinates.
        zoom: Grid resolution zoom level (default: 10). Higher = more detailed.
    """

    def _compute():
        return get_light_pollution_grid(north=north, south=south, east=east, west=west, zoom=zoom)

    raw = await asyncio.to_thread(_compute)
    grid = LightPollutionGrid(
        grid=[LightPollutionGridPoint.from_spf_point(p) for p in raw.get('data', [])],
        bounds={'south': south, 'west': west, 'north': north, 'east': east},
        zoom=zoom,
    )
    return format_response(grid.model_dump())


@mcp.tool()
async def analysis_area(
    south: float,
    west: float,
    north: float,
    east: float,
    max_locations: int = 30,
    min_height_diff: float = 100.0,
    road_radius_km: float = 10.0,
    network_type: str = 'drive',
    db_config_path: str = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
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
        - resource_id: Cache key for the non-pagination search parameters.
    """
    if page < 1:
        return format_error(
            MCPError.CONFIGURATION_ERROR,
            'page must be greater than or equal to 1.',
            {'page': page},
        )
    if page_size < 1:
        return format_error(
            MCPError.CONFIGURATION_ERROR,
            'page_size must be greater than or equal to 1.',
            {'page_size': page_size},
        )

    # 1. Generate Cache Key based on calculation parameters (excluding pagination)
    calc_params = {
        'south': south,
        'west': west,
        'north': north,
        'east': east,
        'max_locations': max_locations,
        'min_height_diff': min_height_diff,
        'road_radius_km': road_radius_km,
        'network_type': network_type,
        'db_config_path': db_config_path,
    }
    resource_id = generate_cache_key(**calc_params)

    # 2. Check Cache
    cached = ANALYSIS_CACHE.get(resource_id)

    # 3. If miss, compute (in thread)
    if cached is None:

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
            # Convert spf StargazingLocation objects to our models
            return [StargazingLocation.from_spf_location(item) for item in results]

        cached = await asyncio.to_thread(_compute)
        ANALYSIS_CACHE.set(resource_id, cached)

    # 4. Pagination
    total = len(cached)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    # Slice results (safe even if indices are out of bounds)
    page_items = cached[start_idx:end_idx]

    result = AnalysisAreaResult(
        items=page_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        resource_id=resource_id,
    )
    return format_response(result.model_dump())
