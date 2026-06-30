import importlib
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from src.logging_config import get_logger
from src.paths import prioritize_sys_path, resolve_package_source_root

logger = get_logger(__name__)

SPF_PACKAGE_NAME = 'stargazingplacefinder'

# Track last-configured analyzer parameters so we avoid re-creating the
# SPF singleton (closing/reopening GeoTIFF handles and PostGIS pools)
# when nothing has changed.
_last_params: dict[str, Any] | None = None
_last_params_lock = threading.Lock()


def _prepare_spf_import_path() -> Path | None:
    """Ensure ``stargazingplacefinder`` resolves its own top-level modules first.

    Since MCP's Pydantic schemas live under ``src/schemas/`` (not ``src/models/``),
    there is no longer a bare ``models`` package conflict.  We only need to put the
    SPF source root at the front of ``sys.path`` so that SPF's internal imports
    (e.g. ``from models import ...``) resolve correctly.

    .. note::

        This is a workaround.  The proper fix is for SPF to use package-relative
        imports (e.g. ``from stargazingplacefinder.models import ...``) so that
        sys.path manipulation is unnecessary.  Tracked as a quarterly item.
    """
    source_root = resolve_package_source_root(SPF_PACKAGE_NAME)
    if source_root is None:
        logger.warning(
            'Cannot resolve SPF package source root — place analysis will be unavailable'
        )
        return None

    logger.debug('Using sys.path workaround for SPF imports from %s', source_root)
    prioritize_sys_path(source_root)
    return source_root


def _load_spf() -> ModuleType:
    """Import ``stargazingplacefinder`` after preparing its dependency source root."""
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
    """Bridge wrapper around the ``stargazingplacefinder`` public API.

    Only calls the public API surface (``analyze_area``, ``get_light_pollution_grid``)
    — never reaches into internal SPF types like ``StargazingLocationAnalyzer``.
    """

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
        self._init_analyzer()

    def _init_analyzer(self) -> None:
        """Configure the SPF singleton analyzer — skipped when params are unchanged."""
        global _last_params

        new_params = {
            'geotiff_path': self.geotiff_path,
            'min_height_difference': self.min_height_difference,
            'road_search_radius_km': self.road_search_radius_km,
            'db_config_path': self.db_config_path,
        }

        with _last_params_lock:
            if _last_params == new_params:
                return  # nothing changed — reuse the existing singleton

        # Load SPF config from TOML file (env STARGAZING_CONFIG or default path),
        # then pass it through to RoadConnectivityChecker (tile size, etc.).
        try:
            from config import load_stargazing_config  # type: ignore[import-untyped]

            spf_config = load_stargazing_config()
        except Exception:
            spf_config = None

        self._spf.init_stargazing_analyzer(
            geotiff_path=self.geotiff_path,
            min_height_difference=self.min_height_difference,
            road_search_radius_km=self.road_search_radius_km,
            db_config_path=self.db_config_path,
            config=spf_config,
        )
        with _last_params_lock:
            _last_params = new_params

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
            self._init_analyzer()
        # Use the public API which returns already-serialized dicts,
        # avoiding SPF Pydantic model instances leaking into MCP's process
        # space where they would conflict with MCP's own StargazingLocation.
        return self._spf.analyze_area(
            bbox=(south, west, north, east),
            max_locations=max_locations,
            network_type=network_type,
            include_light_pollution=True,
            include_road_connectivity=True,
        )


def get_light_pollution_grid(
    north: float, south: float, east: float, west: float, zoom: int = 10
) -> dict[str, Any]:
    """Proxy the light pollution grid helper from ``stargazingplacefinder``."""
    spf_module = _load_spf()
    return spf_module.get_light_pollution_grid(
        north=north,
        south=south,
        east=east,
        west=west,
        zoom=zoom,
    )
