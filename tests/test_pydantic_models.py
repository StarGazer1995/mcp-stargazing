"""Tests for Pydantic model validation behavior."""

import pytest
from pydantic import ValidationError

from src.models import (
    AggregatedWeatherResponse,
    AnalysisAreaResult,
    BestStargazingPlan,
    CelestialPosition,
    CurrentWeather,
    DeepSkyObject,
    GeoBounds,
    GeoPoint,
    LightPollutionGridPoint,
    LocationInfo,
    MoonInfo,
    NightlyForecast,
    NormalizedWeatherData,
    ObservationWindow,
    PlannedLocationCandidate,
    PlanningQuery,
    PlanningSummary,
    PlanningTarget,
    ProviderError,
    ProviderSuccess,
    StargazingLocation,
    VisiblePlanet,
    WeatherPlanningSummary,
)

# ── Base Models ─────────────────────────────────────────────────────────────


class TestGeoPoint:
    def test_valid_coordinates(self):
        point = GeoPoint(lat=45.5, lon=-73.5)
        assert point.lat == 45.5
        assert point.lon == -73.5

    def test_invalid_latitude(self):
        with pytest.raises(ValidationError):
            GeoPoint(lat=100, lon=0)

    def test_invalid_longitude(self):
        with pytest.raises(ValidationError):
            GeoPoint(lat=0, lon=-200)


class TestGeoBounds:
    def test_valid_bounds(self):
        bounds = GeoBounds(south=-10, west=-20, north=10, east=20)
        assert bounds.south == -10

    def test_invalid_bounds_south_greater_than_north(self):
        with pytest.raises(ValidationError):
            GeoBounds(south=10, west=0, north=5, east=20)

    def test_invalid_bounds_west_greater_than_east(self):
        with pytest.raises(ValidationError):
            GeoBounds(south=0, west=20, north=10, east=10)


# ── Celestial Models ────────────────────────────────────────────────────────


class TestCelestialPosition:
    def test_valid_position(self):
        pos = CelestialPosition(altitude=45.0, azimuth=180.0)
        assert pos.altitude == 45.0
        assert pos.azimuth == 180.0

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            CelestialPosition(altitude=45.0)  # missing azimuth


class TestMoonInfo:
    def test_valid_moon_info(self):
        info = MoonInfo(
            illumination=0.5,
            phase_name='First Quarter',
            age_days=7.4,
            elongation=90.0,
            earth_distance=384400.0,
        )
        assert info.phase_name == 'First Quarter'

    def test_invalid_illumination_coerced(self):
        # Pydantic will accept int and coerce to float
        info = MoonInfo(
            illumination=1,
            phase_name='Full Moon',
            age_days=14.8,
            elongation=180.0,
            earth_distance=384400.0,
        )
        assert isinstance(info.illumination, float)


class TestNightlyForecast:
    def test_valid_forecast(self):
        forecast = NightlyForecast(
            moon_phase=MoonInfo(
                illumination=0.5,
                phase_name='First Quarter',
                age_days=7.4,
                elongation=90.0,
                earth_distance=384400.0,
            ),
            planets=[VisiblePlanet(name='Mars', altitude=30.0, azimuth=90.0)],
            deep_sky=[
                DeepSkyObject(
                    name='M42',
                    type='Nebula',
                    magnitude=4.0,
                    altitude=45.0,
                    azimuth=120.0,
                    catalog='Messier',
                    score=2.5,
                )
            ],
        )
        assert len(forecast.planets) == 1
        assert forecast.planets[0].name == 'Mars'
        assert len(forecast.deep_sky) == 1
        assert forecast.deep_sky[0].name == 'M42'

    def test_empty_forecast(self):
        forecast = NightlyForecast(
            moon_phase=MoonInfo(
                illumination=0.0,
                phase_name='New Moon',
                age_days=0.0,
                elongation=0.0,
                earth_distance=384400.0,
            ),
        )
        assert forecast.planets == []
        assert forecast.deep_sky == []


class TestBestStargazingPlan:
    def test_valid_plan(self):
        plan = BestStargazingPlan(
            query=PlanningQuery(
                south=30.0,
                west=100.0,
                north=31.0,
                east=101.0,
                time='2024-06-15 20:00:00',
                time_zone='UTC',
                candidate_limit=2,
                target_limit=3,
                weather_provider='all',
                max_locations=10,
                min_height_diff=100.0,
                road_radius_km=10.0,
                network_type='drive',
                analysis_resource_id='analysis-123',
            ),
            summary=PlanningSummary(
                generated_at='2026-06-27T12:00:00+00:00',
                requested_time='2024-06-15 20:00:00',
                time_zone='UTC',
                total_candidates=1,
                recommended_location_name='Alpha Ridge',
                warnings=['天气摘要降级处理：EXTERNAL_API_ERROR'],
            ),
            candidates=[
                PlannedLocationCandidate(
                    rank=1,
                    recommendation_score=88.5,
                    recommendation_reasons=['波特尔等级约为 2，暗空条件较清晰。'],
                    location=StargazingLocation(name='Alpha Ridge', lat=35.0, lon=-120.0),
                    weather_summary=WeatherPlanningSummary(
                        weather_text='Clear',
                        cloud_cover_percent=10.0,
                        visibility_km=20.0,
                        wind_speed_kph=8.0,
                    ),
                    best_observation_window=ObservationWindow(
                        start_time='2024-06-15T21:00:00+00:00',
                        cloud_cover_percent=8.0,
                        precipitation_probability=0.0,
                        wind_speed_kph=6.0,
                        weather_text='Clear',
                    ),
                    moon_phase='New Moon',
                    moon_illumination=0.05,
                    top_targets=[PlanningTarget(name='M31', category='galaxy', score=91.0)],
                    notes=[],
                )
            ],
        )
        assert plan.query.analysis_resource_id == 'analysis-123'
        assert plan.summary.recommended_location_name == 'Alpha Ridge'
        assert plan.candidates[0].top_targets[0].name == 'M31'

    def test_candidate_limit_must_be_positive(self):
        with pytest.raises(ValidationError):
            PlanningQuery(
                south=30.0,
                west=100.0,
                north=31.0,
                east=101.0,
                time='2024-06-15 20:00:00',
                time_zone='UTC',
                candidate_limit=0,
                target_limit=3,
                weather_provider='all',
                max_locations=10,
                min_height_diff=100.0,
                road_radius_km=10.0,
                network_type='drive',
            )


# ── Places Models ───────────────────────────────────────────────────────────


class TestLightPollutionGridPoint:
    def test_valid_grid_point(self):
        point = LightPollutionGridPoint(lat=35.0, lon=-120.0, bortle=4, sqm=21.5)
        assert point.bortle == 4
        assert point.sqm == 21.5

    def test_minimal_grid_point(self):
        point = LightPollutionGridPoint(lat=0.0, lon=0.0)
        assert point.brightness is None


class TestStargazingLocation:
    def test_valid_location(self):
        loc = StargazingLocation(
            name='Test Site',
            lat=35.0,
            lon=-120.0,
            elevation_m=1500.0,
            bortle_class=2,
        )
        assert loc.name == 'Test Site'
        assert loc.bortle_class == 2

    def test_minimal_location(self):
        loc = StargazingLocation(lat=0.0, lon=0.0)
        assert loc.name is None

    def test_from_spf_location_uses_model_dump(self):
        class SPFLocationWithModelDump:
            def model_dump(self, exclude_none=True):
                assert exclude_none is True
                return {
                    'name': 'Model Dump Site',
                    'latitude': 35.0,
                    'longitude': -120.0,
                    'elevation': 1500.0,
                    'light_pollution_level': 'dark',
                    'light_pollution_bortle': 2,
                    'distance_to_road_km': 3.5,
                    'stargazing_score': 95.0,
                }

        loc = StargazingLocation.from_spf_location(SPFLocationWithModelDump())

        assert loc.name == 'Model Dump Site'
        assert loc.lat == 35.0
        assert loc.lon == -120.0
        assert loc.bortle_class == 2
        assert loc.score == 95.0

    def test_from_spf_location_uses_dict_method(self):
        class SPFLocationWithDict:
            def dict(self, exclude_none=True):
                assert exclude_none is True
                return {
                    'name': 'Dict Site',
                    'lat': 36.0,
                    'lon': -121.0,
                    'elevation': 1200.0,
                    'light_pollution_level': 'rural',
                    'light_pollution_bortle': 3,
                    'distance_to_road_km': 2.0,
                    'stargazing_score': 88.0,
                }

        loc = StargazingLocation.from_spf_location(SPFLocationWithDict())

        assert loc.name == 'Dict Site'
        assert loc.lat == 36.0
        assert loc.lon == -121.0
        assert loc.road_distance_km == 2.0
        assert loc.score == 88.0

    def test_from_spf_location_falls_back_to_dict_conversion(self):
        class DictLikeLocation(dict):
            pass

        loc = StargazingLocation.from_spf_location(
            DictLikeLocation(
                {
                    'name': 'Dict Fallback Site',
                    'latitude': 37.0,
                    'longitude': -122.0,
                    'elevation': 900.0,
                    'light_pollution_level': 'suburban',
                    'light_pollution_bortle': 4,
                    'distance_to_road_km': 1.2,
                    'stargazing_score': 72.0,
                }
            )
        )

        assert loc.name == 'Dict Fallback Site'
        assert loc.lat == 37.0
        assert loc.lon == -122.0
        assert loc.bortle_class == 4
        assert loc.score == 72.0


class TestAnalysisAreaResult:
    def test_valid_result(self):
        result = AnalysisAreaResult(
            items=[StargazingLocation(lat=35.0, lon=-120.0)],
            total=1,
            page=1,
            page_size=10,
            total_pages=1,
            resource_id='abc123',
        )
        assert len(result.items) == 1
        assert result.total_pages == 1

    def test_page_must_be_positive(self):
        with pytest.raises(ValidationError):
            AnalysisAreaResult(
                items=[],
                total=0,
                page=0,
                page_size=10,
                total_pages=0,
                resource_id='abc',
            )

    def test_total_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            AnalysisAreaResult(
                items=[],
                total=-1,
                page=1,
                page_size=10,
                total_pages=0,
                resource_id='abc',
            )


# ── Weather Models ──────────────────────────────────────────────────────────


class TestAggregatedWeatherResponse:
    def test_providers_accepts_typed_models(self):
        """Test that providers field accepts ProviderSuccess/ProviderError directly."""
        loc = LocationInfo(name='Test', lat=0.0, lon=0.0)
        current = CurrentWeather(temperature_c=20.0)
        data = NormalizedWeatherData(location=loc, current=current)
        success = ProviderSuccess(provider='open-meteo', data=data)
        error = ProviderError(
            provider='qweather',
            error={'code': 'API_ERROR', 'message': 'Failed'},
        )

        response = AggregatedWeatherResponse(
            location=loc,
            summary={'current': {}, 'daily': [], 'hourly': []},
            providers={'open-meteo': success, 'qweather': error},
            source={
                'query_mode': 'all',
                'successful_providers': ['open-meteo'],
                'failed_providers': ['qweather'],
            },
        )
        assert isinstance(response.providers['open-meteo'], ProviderSuccess)
        assert isinstance(response.providers['qweather'], ProviderError)
        # Verify serialization works recursively
        dumped = response.model_dump()
        assert dumped['providers']['open-meteo']['status'] == 'success'
        assert dumped['providers']['qweather']['status'] == 'error'

    def test_model_dump_roundtrip(self):
        """Test that model_dump produces a JSON-serializable dict."""
        loc = LocationInfo(name='Paris', lat=48.86, lon=2.35)
        current = CurrentWeather(temperature_c=15.0)
        data = NormalizedWeatherData(location=loc, current=current)
        success = ProviderSuccess(provider='open-meteo', data=data)

        response = AggregatedWeatherResponse(
            location=loc,
            summary={'current': {'temperature_c': 15.0}, 'daily': [], 'hourly': []},
            providers={'open-meteo': success},
            source={
                'query_mode': 'all',
                'successful_providers': ['open-meteo'],
                'failed_providers': [],
            },
        )
        dumped = response.model_dump()
        import json

        # Should not raise
        json.dumps(dumped)
