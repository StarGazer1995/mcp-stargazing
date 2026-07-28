import importlib
import os
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from src.logging_config import get_logger
from src.paths import (
    PROJECT_ROOT,
    discard_shadowing_module,
    prioritize_sys_path,
    resolve_package_source_root,
)

logger = get_logger(__name__)

SPF_PACKAGE_NAME = 'stargazingplacefinder'

# Track last-configured analyzer parameters so we avoid re-creating the
# SPF singleton (closing/reopening GeoTIFF handles and PostGIS pools)
# when nothing has changed.
_last_params: dict[str, Any] | None = None
_last_params_lock = threading.Lock()


def _prepare_legacy_spf_import_path() -> Path | None:
    """Prioritize the legacy SPF source root for older published package layouts."""
    source_root = resolve_package_source_root(SPF_PACKAGE_NAME)
    if source_root is None:
        logger.warning(
            'Cannot resolve SPF package source root — place analysis will be unavailable'
        )
        return None

    logger.debug('Falling back to legacy SPF import path from %s', source_root)
    prioritize_sys_path(source_root)
    discard_shadowing_module('cache', PROJECT_ROOT)
    return source_root


def _load_spf() -> ModuleType:
    """Import SPF, preferring the modern package layout but tolerating legacy wheels."""
    try:
        return importlib.import_module(SPF_PACKAGE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name != SPF_PACKAGE_NAME:
            _prepare_legacy_spf_import_path()
            try:
                return importlib.import_module(SPF_PACKAGE_NAME)
            except ModuleNotFoundError as retry_exc:
                if retry_exc.name == SPF_PACKAGE_NAME:
                    raise ModuleNotFoundError(
                        'stargazingplacefinder is required for place analysis features'
                    ) from retry_exc
                raise
        if exc.name == SPF_PACKAGE_NAME:
            raise ModuleNotFoundError(
                'stargazingplacefinder is required for place analysis features'
            ) from exc
        raise


def _load_spf_config():
    """Load SPF config while remaining compatible with older published packages."""
    try:
        from stargazingplacefinder.config import load_stargazing_config
    except ModuleNotFoundError as exc:
        # Older SPF wheels expose ``config`` as a top-level package instead of
        # ``stargazingplacefinder.config``. Keep this fallback so MCP can ship
        # independently while the new SPF wrapper rolls out.
        if exc.name != 'stargazingplacefinder.config':
            raise
        from config import load_stargazing_config

    return load_stargazing_config()


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
        # Auto-resolve db_config_path: explicit > STARGAZING_DB_CONFIG env > None
        if db_config_path is None:
            env_path = os.environ.get('STARGAZING_DB_CONFIG')
            if env_path:
                db_config_path = Path(env_path)
                logger.info('Using STARGAZING_DB_CONFIG env var: %s', db_config_path)
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

        # Load SPF config from the dependency package so bridge callers do not
        # need to know about SPF's internal top-level module layout.
        try:
            spf_config = _load_spf_config()
        except FileNotFoundError:
            logger.debug('No SPF config file found, using defaults')
            spf_config = None
        except Exception:
            logger.warning('Failed to load SPF config, using defaults', exc_info=True)
            spf_config = None

        self._spf.init_stargazing_analyzer(
            geotiff_path=self.geotiff_path,
            min_height_difference=self.min_height_difference,
            road_search_radius_km=self.road_search_radius_km,
            db_config_path=self.db_config_path,
            config=spf_config,
        )
        logger.info(
            'SPF analyzer initialized (db_config=%s)',
            self.db_config_path or 'env/None',
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
        #
        # Note: geotiff_path / db_config_path are constructor-only and cannot
        # change across analyze_area calls on the same instance.  Cross-instance
        # param changes are caught by __init__ → _init_analyzer() which compares
        # the full param dict including data-source paths.
        if (
            min_height_diff != self.min_height_difference
            or road_radius_km != self.road_search_radius_km
        ):
            self.min_height_difference = min_height_diff
            self.road_search_radius_km = road_radius_km
            self._init_analyzer()

        # When road_radius_km <= 0 the caller explicitly opts out of road
        # connectivity analysis.  This avoids triggering OSMnx downloads from
        # Overpass API when PostGIS is unavailable or road data isn't needed.
        include_road = road_radius_km > 0

        # Use the public API which returns already-serialized dicts,
        # avoiding SPF Pydantic model instances leaking into MCP's process
        # space where they would conflict with MCP's own StargazingLocation.
        return self._spf.analyze_area(
            bbox=(south, west, north, east),
            max_locations=max_locations,
            network_type=network_type,
            include_light_pollution=True,
            include_road_connectivity=include_road,
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
