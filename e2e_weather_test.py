"""E2E smoke test for weather providers — real API calls."""

import os
import sys

# Load .env before any imports
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key, value = key.strip(), value.strip()
            if key not in os.environ:
                os.environ[key] = value
    print(f'✅ Loaded .env ({env_path})')
else:
    print(f'⚠️  No .env found at {env_path}')

sys.path.insert(0, os.path.dirname(__file__))

from src.functions.weather.service import (  # noqa: E402
    get_aggregated_weather_by_name,
    get_aggregated_weather_by_position,
)
from src.response import MCPError  # noqa: E402

PASS = 0
FAIL = 0


def test(name: str, fn, *args, expect_error: bool = False, **kwargs):
    global PASS, FAIL
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, dict) and 'error' in result:
            _record(name, False, f'error response: {result["error"]}', expect_error)
            return
        # Quick sanity checks
        loc = result.location
        summary = result.summary
        providers = result.providers
        success = [k for k, v in providers.items() if v.__class__.__name__ == 'ProviderSuccess']
        failed = [k for k, v in providers.items() if v.__class__.__name__ == 'ProviderError']

        print(f'✅ {name}')
        print(f'   位置: {loc.name} ({loc.lat:.4f}, {loc.lon:.4f}) tz={loc.timezone}')
        if summary.current:
            print(
                f'   当前: {summary.current.get("temperature_c")}°C, '
                f'湿度={summary.current.get("humidity")}%, '
                f'天气={summary.current.get("weather_text")}'
            )
        print(f'   日预报: {len(summary.daily)} 天, 小时预报: {len(summary.hourly)} 个')
        print(f'   成功 providers: {success}, 失败: {failed}')
        _record(name, True, None, expect_error)
    except MCPError as exc:
        _record(name, False, f'MCPError [{exc.code}] {exc.message}', expect_error)
    except Exception as exc:
        _record(name, False, f'{type(exc).__name__}: {exc}', expect_error)


def _record(name: str, ok: bool, detail: str | None, expect_error: bool):
    global PASS, FAIL
    if expect_error:
        if ok:
            print(f'❌ {name}: 预期失败但成功了')
            FAIL += 1
        else:
            print(f'✅ {name}: 预期错误 — {detail}')
            PASS += 1
    else:
        if ok:
            PASS += 1
        else:
            print(f'❌ {name}: {detail}')
            FAIL += 1


print('=' * 60)
print('E2E Weather Test — 真实 API 调用')
print('=' * 60)

# ── by_name ──
print('\n── get_weather_by_name ──')
test('北京 (open-meteo only)', get_aggregated_weather_by_name, '北京', provider='open-meteo')
test('成都 (wttr only)', get_aggregated_weather_by_name, '成都', provider='wttr')
test('上海 (qweather only)', get_aggregated_weather_by_name, '上海', provider='qweather')
test('Chengdu (all providers)', get_aggregated_weather_by_name, 'Chengdu', provider='all')
test('大理 (all providers)', get_aggregated_weather_by_name, '大理', provider='all')

# ── by_position ──
print('\n── get_weather_by_position ──')
test('成都坐标 (all)', get_aggregated_weather_by_position, 30.57, 104.06, provider='all')
test(
    '北京坐标 (open-meteo)',
    get_aggregated_weather_by_position,
    39.90,
    116.40,
    provider='open-meteo',
)
test('大理坐标 (wttr)', get_aggregated_weather_by_position, 25.60, 100.27, provider='wttr')

# ── edge cases ──
print('\n── 边界情况 ──')
test(
    '不存在的地名',
    get_aggregated_weather_by_name,
    'XyzzyNonexistentCity12345',
    provider='open-meteo',
    expect_error=True,
)
test('英文 Tokyo', get_aggregated_weather_by_name, 'Tokyo', provider='all')

print('\n' + '=' * 60)
print(f'结果: {PASS} 通过, {FAIL} 失败, 共 {PASS + FAIL} 个测试')
print('=' * 60)

sys.exit(0 if FAIL == 0 else 1)
