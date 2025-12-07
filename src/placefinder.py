import stargazingplacefinder as spf
from typing import Optional, List, Dict, Any
from pathlib import Path

class StargazingPlaceFinder:
    def __init__(self, kml_file_path: Optional[Path] = None,
                             images_base_path: Optional[Path] = None,
                             min_height_difference: float = 100.0,
                             road_search_radius_km: float = 10.0,
                             db_config_path: Optional[Path] = None):
        self.kml_file_path = kml_file_path
        self.images_base_path = images_base_path
        self.min_height_difference = min_height_difference
        self.road_search_radius_km = road_search_radius_km
        self.db_config_path = db_config_path
        self.stargazing_analyzer = spf.init_stargazing_analyzer(
            kml_file_path, images_base_path, min_height_difference, road_search_radius_km, db_config_path)

    def analyze_area(self, south: float, west: float, north: float, east: float,
                        min_height_diff: float = 100.0,
                        road_radius_km: float = 10.0,
                        max_locations: int = 30,
                        network_type: str = 'drive') -> List[Dict[str, Any]]:
        self.min_height_difference = min_height_diff
        self.road_search_radius_km = road_radius_km
        self.stargazing_analyzer = spf.init_stargazing_analyzer(
            self.kml_file_path, self.images_base_path, self.min_height_difference, self.road_search_radius_km, self.db_config_path)
        return self.stargazing_analyzer.analyze_area(
            bbox=(south, west, north, east),
            max_locations=max_locations,
            location_types=None,
            network_type=network_type,
            include_light_pollution=True,
            include_road_connectivity=True,
        )
