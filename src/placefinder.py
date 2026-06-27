import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from src.paths import (
    MODELS_DIR,
    discard_shadowing_module,
    find_module_origin,
    is_repo_models_origin,
    prioritize_sys_path,
    resolve_package_source_root,
)

SPF_PACKAGE_NAME = 'stargazingplacefinder'
MODELS_MODULE_NAME = 'models'


def _prepare_spf_import_path() -> Path | None:
    """Ensure `stargazingplacefinder` resolves its own top-level modules first."""
    source_root = resolve_package_source_root(SPF_PACKAGE_NAME)
    if source_root is None:
        return None

    if is_repo_models_origin(find_module_origin(MODELS_MODULE_NAME)):
        discard_shadowing_module(MODELS_MODULE_NAME, MODELS_DIR)
    elif is_repo_models_origin(getattr(sys.modules.get(MODELS_MODULE_NAME), '__file__', None)):
        discard_shadowing_module(MODELS_MODULE_NAME, MODELS_DIR)

    prioritize_sys_path(source_root)
    return source_root


def _load_spf() -> ModuleType:
    """Import `stargazingplacefinder` after preparing its dependency source root."""
    _prepare_spf_import_path()
    try:
        return importlib.import_module(SPF_PACKAGE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == SPF_PACKAGE_NAME:
            raise ModuleNotFoundError(
                'stargazingplacefinder is required for place analysis features'
            ) from exc
        raise


class StargazingPlaceFinder:
    """Bridge wrapper around the `stargazingplacefinder` public API."""

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
        self._spf = _load_spf()
        self.stargazing_analyzer = self._init_analyzer()

    def _init_analyzer(self) -> Any:
        """Initialize the dependency analyzer using the bridge's current parameters."""
        return self._spf.init_stargazing_analyzer(
            geotiff_path=self.geotiff_path,
            min_height_difference=self.min_height_difference,
            road_search_radius_km=self.road_search_radius_km,
            db_config_path=self.db_config_path,
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
            self.stargazing_analyzer = self._init_analyzer()
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
    """Proxy the light pollution grid helper from `stargazingplacefinder`."""
    spf_module = _load_spf()
    return spf_module.get_light_pollution_grid(
        north=north,
        south=south,
        east=east,
        west=west,
        zoom=zoom,
    )
