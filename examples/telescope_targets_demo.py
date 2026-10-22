import asyncio

from _bootstrap import ensure_project_root

ensure_project_root()

from src.functions.telescope.impl import get_telescope_targets


async def main() -> None:
    """Print ranked targets for a RedCat51 + ASI2600-style setup."""
    result = await get_telescope_targets.fn(
        focal_length_mm=250,
        aperture_mm=51,
        sensor_width_mm=23.5,
        sensor_height_mm=15.7,
        sensor_pixel_size_um=3.76,
        lon=116.4074,
        lat=39.9042,
        time='2026-01-15T22:00:00',
        time_zone='Asia/Shanghai',
        limit=10,
    )

    if result['_meta']['status'] == 'error':
        print(f'Error: {result["error"]["message"]}')
        return

    data = result['data']
    print(f'Targets: {data["total"]}')
    for index, target in enumerate(data['targets'], start=1):
        print(
            f'{index:>2}. {target["name"]:<18} '
            f'score={target["suitability_score"]:>5.1f} '
            f'alt={target.get("altitude", 0):>5.1f}°'
        )


if __name__ == '__main__':
    asyncio.run(main())
