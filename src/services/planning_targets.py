"""Selected-window checks using the public core scheduler, without new sky requests."""

from datetime import UTC
from typing import Any

from stargazing_core import generate_shooting_schedule

from src.schemas.planning import ObservationWindow
from src.services.planning_weather import finite_number
from src.utils import parse_observation_time


def assess_target_windows(
    targets: list[dict[str, Any]], moon: Any, window: ObservationWindow, time_zone: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Retain unknown references; reject only targets with a complete negative check.

    Check each target independently so competition in a joint schedule does not
    imply infeasibility. This is a model schedule, never an exposure promise.
    """
    start = parse_observation_time(window.start_time, time_zone).astimezone(UTC)
    end = parse_observation_time(window.end_time, time_zone).astimezone(UTC)
    # Core 0.2.1 relabels aware bounds as UTC. Naive UTC works with both it
    # and the corrected core implementation, preserving the actual instants.
    bounds = [value.replace(tzinfo=None).isoformat() for value in (start, end)]
    moon_known = isinstance(moon, dict) and (
        (illumination := finite_number(moon.get('illumination'))) is not None
        and 0 <= illumination <= 1
        and isinstance(moon.get('always_down'), bool)
        and isinstance(moon.get('always_up'), bool)
        and not (moon['always_down'] and moon['always_up'])
        and (
            illumination <= 0.3
            or moon['always_down']
            or moon['always_up']
            or finite_number(moon.get('moonset')) is not None
        )
    )
    scheduler_moon = {**moon, 'phase': moon.get('phase', 'Unknown')} if moon_known else {}
    retained = []
    assessments = []
    for target in targets:
        assessment = {'name': target['name'], 'status': 'unknown', 'slots': []}
        curve = target.get('altitude_curve')
        try:
            valid = isinstance(curve, list) and len(curve) >= 2
            previous = float('-inf')
            for point in curve if valid else []:
                stamp = finite_number(point.get('time'))
                altitude = finite_number(point.get('alt'))
                if stamp is None or altitude is None or not -90 <= altitude <= 90:
                    valid = False
                    break
                if stamp <= previous:
                    valid = False
                    break
                previous = stamp
            if not valid:
                assessment['reason'] = 'missing_or_invalid_altitude_curve'
            elif curve[0]['time'] > start.timestamp() or curve[-1]['time'] < end.timestamp():
                assessment['reason'] = 'incomplete_window_coverage'
            else:
                schedule = generate_shooting_schedule(
                    [{**target, 'type': target.get('type', 'deep_sky')}],
                    scheduler_moon,
                    *bounds,
                    min_alt=25.0,
                    min_duration_min=30,
                )
                assessment.update(
                    status=(
                        (
                            'scheduler_window_available'
                            if moon_known
                            else 'altitude_window_available'
                        )
                        if schedule.slots
                        else ('no_scheduler_window' if moon_known else 'no_altitude_window')
                    ),
                    slots=[
                        {
                            'start_time': slot.start_time,
                            'end_time': slot.end_time,
                            'duration_min': slot.duration_min,
                        }
                        for slot in schedule.slots
                    ],
                    warnings=schedule.warnings,
                )
        except (TypeError, ValueError, AttributeError, OverflowError) as exc:
            assessment['reason'] = f'invalid_scheduler_input: {type(exc).__name__}'
        if not assessment['status'].startswith('no_'):
            retained.append(target)
        assessments.append(assessment)
    return retained, {
        'window_start': window.start_time,
        'window_end': window.end_time,
        'minimum_altitude_degrees': 25.0,
        'minimum_duration_minutes': 30,
        'moon_status': 'scheduler_policy' if moon_known else 'unknown_altitude_only',
        'assessment_scope': 'each_shortlisted_target_independently',
        'limitations': [
            'Linear sampled-altitude interpolation with minute resolution; no field validation.',
            'No per-slot Moon separation, terrain, tracking, meridian-flip or exposure guarantee.',
            'Independent slots may overlap; this is not a joint shooting plan.',
            'Empty shortlist does not prove no other catalog targets are available.',
        ],
        'targets': assessments,
    }
