from datetime import datetime, timedelta

import pytz
from _bootstrap import ensure_project_root

ensure_project_root()

from src.celestial import calculate_moon_info


def main():
    print('Moon Phase Demo')
    print('===============')

    # Use current time in UTC
    start_date = datetime.now(pytz.UTC)

    print(f'Calculating moon phases for the next 30 days starting from {start_date.date()}...\n')
    print(f'{"Date":<12} | {"Phase":<16} | {"Illum %":<8} | {"Age (days)":<10}')
    print('-' * 55)

    for i in range(0, 30):
        date = start_date + timedelta(days=i)
        info = calculate_moon_info(date)

        phase = info['phase_name']
        illum = info['illumination'] * 100
        age = info['age_days']

        print(f'{date.strftime("%Y-%m-%d"):<12} | {phase:<16} | {illum:8.1f} | {age:10.1f}')


if __name__ == '__main__':
    main()
