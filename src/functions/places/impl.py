import asyncio
from pathlib import Path
from typing import Any

from src.cache import ANALYSIS_CACHE, generate_cache_key
from src.logging_config import get_logger, get_request_id, set_request_id
from src.placefinder import StargazingPlaceFinder, get_light_pollution_grid
from src.response import MCPError, format_error, format_response
from src.schemas.places import (
    AnalysisAreaResult,
    LightPollutionGrid,
    LightPollutionGridPoint,
    StargazingLocation,
)
from src.server_instance import mcp

logger = get_logger(__name__)

# Lazy-loaded SPF exception classes (populated on first use)
_spf_exc_classes: dict[str, type] | None = None


def _load_spf_exceptions() -> dict[str, type] | None:
    """Try to import SPF exception classes for isinstance-based matching.

    Returns None if SPF is not installed; in that case the caller should
    fall back to string-based name matching.
    """
    global _spf_exc_classes
    if _spf_exc_classes is not None:
        return _spf_exc_classes

    try:
        import stargazingplacefinder as spf

        _spf_exc_classes = {}
        for name in (
            'StargazingError',
            'DataError',
            'NoDataError',
            'ValidationError',
            'NetworkError',
            'CacheError',
            'ConfigError',
            'GeoError',
        ):
            cls = getattr(spf, name, None)
            if cls is not None:
                _spf_exc_classes[name] = cls
    except ImportError:
        _spf_exc_classes = {}  # Sentinel: tried and failed

    return _spf_exc_classes or None


def _translate_spf_error(exc: Exception) -> MCPError:
    """Translate SPF exceptions into MCPError for clean agent-facing messages.

    Uses isinstance checks against SPF's exception hierarchy when available;
    falls back to string-based type-name matching when SPF is not installed.
    """
    spf_exc = _load_spf_exceptions()
    if spf_exc:
        # Robust isinstance-based matching (handles inheritance)
        if isinstance(exc, spf_exc.get('ValidationError', ())):
            return MCPError(MCPError.CONFIGURATION_ERROR, f'SPF validation error: {exc}')
        if isinstance(exc, spf_exc.get('ConfigError', ())):
            return MCPError(MCPError.CONFIGURATION_ERROR, f'SPF configuration error: {exc}')
        if isinstance(exc, spf_exc.get('GeoError', ())):
            return MCPError(MCPError.INVALID_COORDINATES, f'SPF coordinate error: {exc}')
        if isinstance(exc, spf_exc.get('NetworkError', ())):
            return MCPError(MCPError.NETWORK_ERROR, f'SPF network error: {exc}')
        if isinstance(exc, spf_exc.get('NoDataError', ())):
            return MCPError(MCPError.EXTERNAL_API_ERROR, f'No data available: {exc}')
        if isinstance(exc, spf_exc.get('DataError', ())):
            return MCPError(MCPError.EXTERNAL_API_ERROR, f'SPF data error: {exc}')
        if isinstance(exc, spf_exc.get('CacheError', ())):
            return MCPError(MCPError.EXTERNAL_API_ERROR, f'SPF cache error: {exc}')
        if isinstance(exc, spf_exc.get('StargazingError', ())):
            return MCPError(MCPError.EXTERNAL_API_ERROR, f'SPF internal error: {exc}')
        # Unknown exception type — log so we can discover new SPF exception classes
        logger.warning(
            'Unrecognized SPF exception type %s (request_id=%s)',
            type(exc).__name__,
            get_request_id() or 'unknown',
        )
        return MCPError(MCPError.EXTERNAL_API_ERROR, f'SPF error: {exc}')

    # Fallback: SPF not installed — use fragile string-based matching
    exc_name = type(exc).__name__
    error_map = {
        'ValidationError': (MCPError.CONFIGURATION_ERROR, 'SPF validation error'),
        'ConfigError': (MCPError.CONFIGURATION_ERROR, 'SPF configuration error'),
        'GeoError': (MCPError.INVALID_COORDINATES, 'SPF coordinate error'),
        'NetworkError': (MCPError.NETWORK_ERROR, 'SPF network error'),
        'DataError': (MCPError.EXTERNAL_API_ERROR, 'SPF data error'),
        'NoDataError': (MCPError.EXTERNAL_API_ERROR, 'No data available'),
        'CacheError': (MCPError.EXTERNAL_API_ERROR, 'SPF cache error'),
        'StargazingError': (MCPError.EXTERNAL_API_ERROR, 'SPF internal error'),
    }
    code, prefix = error_map.get(exc_name, (MCPError.EXTERNAL_API_ERROR, 'SPF error'))
    return MCPError(code, f'{prefix}: {exc}')


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
    set_request_id()

    def _compute():
        try:
            return get_light_pollution_grid(
                north=north, south=south, east=east, west=west, zoom=zoom
            )
        except ModuleNotFoundError:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'stargazing-place-finder is not installed — '
                'place analysis features are unavailable',
            )
        except Exception as exc:
            raise _translate_spf_error(exc) from exc

    try:
        raw = await asyncio.to_thread(_compute)
    except MCPError:
        raise
    except Exception as exc:
        raise _translate_spf_error(exc) from exc
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
    set_request_id()
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
            try:
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
            except ModuleNotFoundError:
                raise MCPError(
                    MCPError.CONFIGURATION_ERROR,
                    'stargazing-place-finder is not installed — '
                    'place analysis features are unavailable',
                )
            except Exception as exc:
                raise _translate_spf_error(exc) from exc

        try:
            cached = await asyncio.to_thread(_compute)
        except MCPError:
            raise
        except Exception as exc:
            raise _translate_spf_error(exc) from exc
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
