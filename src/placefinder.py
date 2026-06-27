import importlib
import sys
from pathlib import Path
from typing import Any

from src.paths import MODELS_DIR, is_within_path


def _is_repo_models_origin(origin: str | None) -> bool:
    """Return whether the resolved `models` module comes from this repo's `src/models`."""
    return is_within_path(origin, MODELS_DIR)


# ---------------------------------------------------------------------------
# Defensive guard: ensure stargazingplacefinder's 'models' package is not
# shadowed by mcp-stargazing's own src/models/ directory when src/ is on
# sys.path (e.g. during development with `python -m src.main`).
# ---------------------------------------------------------------------------
_site_models = None
try:
    _site_models = importlib.util.find_spec('models')
except (ImportError, ValueError, ModuleNotFoundError):
    pass

if _site_models is not None and _site_models.origin is not None:
    if _is_repo_models_origin(_site_models.origin):
        # 'models' resolves to mcp-stargazing's own models — this will break
        # stargazingplacefinder below.  Restore site-packages priority.
        _site_pkgs = [p for p in sys.path if 'site-packages' in p]
        _rest = [p for p in sys.path if 'site-packages' not in p]
        sys.path = _site_pkgs + _rest

import stargazingplacefinder as spf  # noqa: E402


class StargazingPlaceFinder:
    def __init__(
        self,
        geotiff_path: Path | None = None,
        min_height_difference: float = 100.0,
        road_search_radius_km: float = 10.0,
        db_config_path: Path | None = None,
    ):
        self.geotiff_path = geotiff_path
        self.min_height_difference = min_height_difference
        self.road_search_radius_km = road_search_radius_km
        self.db_config_path = db_config_path
        self.stargazing_analyzer = spf.init_stargazing_analyzer(
            geotiff_path=geotiff_path,
            min_height_difference=min_height_difference,
            road_search_radius_km=road_search_radius_km,
            db_config_path=db_config_path,
        )

    def analyze_area(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        min_height_diff: float = 100.0,
        road_radius_km: float = 10.0,
        max_locations: int = 30,
        network_type: str = 'drive',
    ) -> list[dict[str, Any]]:
        # Only re-init the analyzer when spatial parameters actually change.
        # This avoids re-opening GeoTIFF files and re-creating PostGIS
        # connection pools on every call (e.g. pagination).
        if (
            min_height_diff != self.min_height_difference
            or road_radius_km != self.road_search_radius_km
        ):
            self.min_height_difference = min_height_diff
            self.road_search_radius_km = road_radius_km
            self.stargazing_analyzer = spf.init_stargazing_analyzer(
                geotiff_path=self.geotiff_path,
                min_height_difference=self.min_height_difference,
                road_search_radius_km=self.road_search_radius_km,
                db_config_path=self.db_config_path,
            )
        return self.stargazing_analyzer.analyze_area(
            bbox=(south, west, north, east),
            max_locations=max_locations,
            location_types=None,
            network_type=network_type,
            include_light_pollution=True,
            include_road_connectivity=True,
        )


def get_light_pollution_grid(
    north: float, south: float, east: float, west: float, zoom: int = 10
) -> dict[str, Any]:
    return spf.get_light_pollution_grid(north=north, south=south, east=east, west=west, zoom=zoom)
