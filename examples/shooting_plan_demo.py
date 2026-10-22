import asyncio

from _bootstrap import ensure_project_root

ensure_project_root()

from src.functions.telescope.impl import get_shooting_plan


async def main() -> None:
    """Print a single-night imaging plan for a RedCat51-style setup."""
    result = await get_shooting_plan.fn(
        focal_length_mm=250,
        aperture_mm=51,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        sensor_pixel_size_um=3.76,
        lon=116.4074,
        lat=39.9042,
        time='2026-01-15T22:00:00',
        time_zone='Asia/Shanghai',
        min_altitude=25.0,
        limit=10,
    )

    if result['_meta']['status'] == 'error':
        print(f'Error: {result["error"]["message"]}')
        return

    data = result['data']
    plan = data['plan']
    print(f'Dark window: {plan["dusk"]} -> {plan["dawn"]}')
    print(f'Total dark time: {plan["total_dark_min"]} min')
    for slot in plan['slots']:
        print(
            f'{slot["start_time"]} -> {slot["end_time"]}  '
            f'{slot["target_name"]} ({slot["duration_min"]} min)'
        )


if __name__ == '__main__':
    asyncio.run(main())
