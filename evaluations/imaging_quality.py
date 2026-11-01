"""Frozen policy cases, independent of live providers and actual weather skill."""

from datetime import UTC, datetime, timedelta

from src.schemas import AgentPlanningRequest, NightWindow
from src.services.planning import PlanningDependencies, PlanningService

CASES = {
    'clear-continuous': True,
    'opaque-high-layer': False,
    'cloudy-74-percent': False,
    'wind-22-kph': False,
    'rain-25-percent': False,
    'single-clear-hour': False,
    'dawn-only-clearing': False,
    'forecast-gap': False,
    'missing-rain': False,
    'missing-wind': False,
    'no-astronomical-darkness': False,
}


def build_case(name, timing_sink=None):
    """Return a complete application service fixture and an evening request."""
    if name not in CASES:
        raise ValueError(f'Unknown case: {name}')
    start = datetime.fromisoformat('2026-11-08T18:00:00+08:00')
    hours = []
    for index in range(13):
        dt = start + timedelta(hours=index)
        item = {
            'time': dt.isoformat(),
            'cloud_cover_percent': 5.0,
            'precipitation_probability': 0.0,
            'wind_speed_kph': 6.0,
        }
        if name == 'opaque-high-layer':
            item['cloud_cover_high_percent'] = 90.0
        if name == 'cloudy-74-percent':
            item['cloud_cover_percent'] = 74.0
        if name == 'wind-22-kph':
            item['wind_speed_kph'] = 22.0
        if name == 'rain-25-percent':
            item['precipitation_probability'] = 0.25
        if name == 'single-clear-hour' and dt.hour != 2:
            item['cloud_cover_percent'] = 90.0
        if name == 'dawn-only-clearing' and dt.hour not in (5, 6):
            item['cloud_cover_percent'] = 90.0
        if name == 'forecast-gap' and dt.hour not in (0, 2):
            continue
        if name == 'missing-rain':
            item.pop('precipitation_probability')
        if name == 'missing-wind':
            item.pop('wind_speed_kph')
        hours.append(item)

    async def places(**_kwargs):
        return {'items': [{'name': 'Frozen Ridge', 'lat': 30.5, 'lon': 119.5, 'score': 70}]}

    async def weather(**_kwargs):
        return {'summary': {'hourly': hours}}

    async def forecast(**_kwargs):
        return {'moon_phase': {'illumination': 0.05}, 'deep_sky': [{'name': 'M31'}]}

    async def civil(_lat, _lon, reference):
        if reference.hour < 12:
            reference -= timedelta(days=1)
        date = reference.date().isoformat()
        next_date = (reference + timedelta(days=1)).date().isoformat()
        return NightWindow(
            local_date=date,
            civil_dusk=f'{date}T17:30:00+08:00',
            civil_dawn=f'{next_date}T06:30:00+08:00',
            duration_hours=13,
            time_zone='Asia/Shanghai',
        )

    async def darkness(_lat, _lon, reference):
        if name == 'no-astronomical-darkness':
            raise ValueError('No astronomical darkness')
        return (reference.replace(hour=19), (reference + timedelta(days=1)).replace(hour=5))

    service = PlanningService(
        PlanningDependencies(
            search_places=places,
            fetch_weather=weather,
            fetch_forecast=forecast,
            fetch_night_window=civil,
            fetch_imaging_bounds=darkness,
            now=lambda: datetime(2026, 11, 1, tzinfo=UTC),
            timing_sink=timing_sink,
        )
    )
    request = AgentPlanningRequest.model_validate(
        {
            'location': {'center': {'lat': 30.5, 'lon': 119.5}},
            'start_date': '2026-11-08',
            'nights': 1,
            'observation_style': 'deep_sky',
        }
    )
    return service, request
