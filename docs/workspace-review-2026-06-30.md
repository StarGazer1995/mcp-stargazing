# Workspace 项目锐评 — 任务清单与排期

> 基于 2026-06-30 双项目全面代码审查生成。每个任务包含：问题位置、具体修复步骤、预估工时、依赖关系。

---

## 优先级定义

| 等级 | 含义 | 响应时间 |
|------|------|----------|
| 🔴 P0 | Bug / 静默数据错误 / 测试红灯 | 24h 内 |
| 🟠 P1 | 高风险技术债，随时可能炸 | 本周内 |
| 🟡 P2 | 代码质量 / 可维护性 | 本月内 |
| 🟢 P3 | 优化 / 锦上添花 | 下季度 |

---

## 一、stargazing-place-finder（SPF）

### 🔴 P0-1: 修复 3 个评分测试失败

**位置**：`src/stargazing_analyzer/test/test_analyzer_scoring.py`

**问题**：提交 `f1a021f` 将离散桶评分改为连续 sigmoid 函数后，3 个测试的期望值未更新：

| 测试名 | 旧期望 | 新实际 | 根因 |
|--------|--------|--------|------|
| `test_score_road_accessibility` | 20 | 17.6 | 100m 距离 sigmoid: `20/(1+(0.1/0.2)²)` |
| `test_score_road_accessibility_beyond_threshold` | 10 | 2.8 | 500m 距离 sigmoid: `20/(1+(0.5/0.2)²)` |
| `test_score_town_isolation_very_close` | 0 | 5.59 | 2km 对数评分替代了离散桶 |

**修复步骤**：
1. 确认新的评分公式是否是**预期行为**（与产品逻辑对齐）
2. 如果是预期行为：更新测试期望值，并补充注释说明公式来源
3. 如果不是预期行为：调整评分函数参数，使结果落在合理范围内
4. 提交前运行 `uv run pytest src/stargazing_analyzer/test/test_analyzer_scoring.py -v` 确认全部通过

**预估工时**：1h
**依赖**：无
**排期**：Day 1

---

### 🔴 P0-2: 修复 TOML 解析异常的死 catch 块

**位置**：`src/gis_service/config.py` 第 77 行

**问题**：
```python
# 当前：这个 catch 永远不会触发，因为 tomllib 抛的是 TOMLDecodeError(ValueError)，不是 ConfigError
except ConfigError as e:
    raise RuntimeError(f"Failed to parse TOML config: {e}")
```

**修复步骤**：
```python
# 改为：
except tomllib.TOMLDecodeError as e:
    raise RuntimeError(f"Failed to parse TOML config: {e}") from e
```
如果同时要兜底 `ConfigError`（来自自定义模型层），可以保留但用两个 except 分支，并加测试覆盖两种异常路径。

**预估工时**：0.5h
**依赖**：无
**排期**：Day 1

---

### 🔴 P0-3: 修复 OverpassBackend 的死 catch 块

**位置**：`src/gis_service/backends/overpass_backend.py` 第 209 行

**问题**：`except NetworkError as e:` 在对应 try 块中永远不会被抛出。

**修复步骤**：
1. 检查 try 块内实际可能抛出的异常类型（`requests.exceptions.Timeout`、`requests.exceptions.ConnectionError` 等）
2. 将 `NetworkError` 替换为实际的异常类型，或者直接删除这个死分支
3. 如果 `NetworkError` 是自定义异常类，需要在请求层封装时抛出（而非直接透传 requests 异常）

**预估工时**：0.5h
**依赖**：无
**排期**：Day 1

---

### 🟠 P1-1: 修复两个 `except (XError, Exception)` 反模式

**位置**：
- `src/stargazing_analyzer/stargazing_location_analyzer.py` 第 252 行
- `src/road_connectivity/road_connectivity_checker.py` 第 343 行

**问题**：`except (SpecificError, Exception)` 等价于 `except Exception`，会静默吞掉 TypeError、AttributeError 等编程错误。

**修复步骤**：
1. 列出该 try 块内实际可能抛出的业务异常类型
2. 仅捕获这些具体类型
3. 如果确实需要兜底，在最外层单独 `except Exception` 并**至少打 error 日志 + 记录 details**，而不是 pass
4. 写完跑该模块的测试确认没有引入回归

**预估工时**：1h
**依赖**：无
**排期**：Day 2

---

### 🟠 P1-2: 缓存竞态条件——pickle 文件 TOCTOU

**位置**：
- `src/gis_service/caching.py` 第 57–81 行
- `src/road_connectivity/road_connectivity_checker.py` 第 50–98 行

**问题**：读缓存 → 改内存 → 写回文件，三步之间无锁。并发请求互相覆盖，静默丢数据。

**修复步骤**：
1. 引入 `threading.Lock()` 或 `multiprocessing.Lock()` 保护写路径（取决于使用时是多线程还是多进程）
2. 写入时使用**原子写入模式**：先写临时文件 `.tmp`，再 `os.replace()` 原子重命名
3. 内存 dict 读写也加锁（或改用 `collections.ChainMap` + copy-on-write）
4. 写一个并发测试（至少 2 线程同时读写），验证无数据丢失

**预估工时**：3h
**依赖**：无
**排期**：Day 2–3

---

### 🟡 P2-1: 重复的 Haversine 公式

**位置**：
- `src/light_pollution/light_pollution_api.py` 第 287–308 行
- `src/gis_service/parsers.py` 第 123–148 行

**修复步骤**：
1. 在 `parsers.py` 中新增一个接受 `(float, float, float, float)` 的重载或包装函数
2. 将 `light_pollution_api.py` 的实现改为调用 `parsers.py` 的版本（构造临时 GeoCoordinate 或直接用 float 版本）
3. 跑两个模块的测试确认行为一致

**预估工时**：0.5h
**依赖**：无
**排期**：Day 3

---

### 🟡 P2-2: TOML import fallback 重复

**位置**：
- `src/config/__init__.py` 第 40–44 行
- `src/gis_service/config.py` 第 70–73 行

**修复步骤**：
1. 在 `src/config/` 下新增 `_toml_loader.py`（或被已有模块复用）：
   ```python
   try:
       import tomllib
   except ImportError:
       import tomli as tomllib
   ```
2. 两处调用方改为 `from config._toml_loader import tomllib`
3. 跑 lint 确认无 unused import 警告

**预估工时**：0.5h
**依赖**：无
**排期**：Day 3

---

### 🟡 P2-3: OverpassBackend 静默失败——失败返回 `[]` 无法区分「无数据」

**位置**：`src/gis_service/backends/overpass_backend.py`

**问题**：所有失败路径（超时、网络错误、全部 URL 不可用）都返回 `[]`，调用方无法区分「区域真的空」和「API 炸了」。

**修复步骤**：
1. 定义一个新的异常类如 `OverpassQueryFailed(reason: str)` 或复用现有的 `NetworkError`
2. 在 `_request` 方法中，当所有 URL 都失败时 `raise OverpassQueryFailed(...)` 而非 `return []`
3. 在调用方（`GisQueryService`）中 catch 这个异常，转换为 fallback 逻辑或返回带有 `_meta.warnings` 的空结果
4. 更新相关测试

**预估工时**：2h
**依赖**：P0-3（死 catch 块先修）
**排期**：Day 4

---

### 🟢 P3-1: `logging.basicConfig` 模块级副作用

**位置**：`src/road_connectivity/road_connectivity_checker.py` 第 29 行

**修复步骤**：
1. 删除 `logging.basicConfig(level=logging.INFO)`
2. 改为 `logger = logging.getLogger(__name__)`，由调用方（CLI / Flask）统一配置日志级别

**预估工时**：0.25h
**依赖**：无
**排期**：Day 5

---

### 🟢 P3-2: `mock_finder.get_towns_from_overpass` 在 conftest 中是僵尸引用

**位置**：`src/conftest.py` 第 89 行

**修复步骤**：
1. 确认 `get_towns_from_overpass` 已被彻底删除
2. 删除 conftest 中对应的 mock 属性
3. 跑全部测试确认无引用

**预估工时**：0.25h
**依赖**：无
**排期**：Day 5

---

## 二、mcp-stargazing（MCP）

### 🔴 P0-1: 全局缓存无锁——并发踩踏

**位置**：
- `src/celestial.py` 第 270–271 行（`OBJECTS_CACHE` / `CONSTELLATIONS_CACHE`）
- `src/cache.py` 第 44 行（`ANALYSIS_CACHE` 全局单例）

**问题**：
- `_load_objects()` 和 `_load_constellations()` 用 `is not None` 做惰性初始化，多协程同时读到 None 会重复加载
- `AnalysisCache` 使用 `dict` + `OrderedDict` 无锁，cache stampede 场景下同时 evict + insert

**修复步骤**：
1. 引入 `asyncio.Lock` 保护 `_load_objects()` / `_load_constellations()` 的初始化路径
2. 使用 double-checked locking 模式：
   ```python
   if OBJECTS_CACHE is None:
       async with _objects_lock:
           if OBJECTS_CACHE is None:
               OBJECTS_CACHE = _load_objects()
   ```
3. `AnalysisCache` 的 `get`/`put`/`evict` 方法加 `threading.Lock`（因为可能在 `asyncio.to_thread` 中调用）
4. 写一个并发测试：10 个 asyncio task 同时首次调用，验证只加载一次

**预估工时**：3h
**依赖**：无
**排期**：Day 1–2

---

### 🔴 P0-2: `@lru_cache` 在网络 I/O 函数上缓存异常（毒缓存）

**位置**：`src/celestial.py` 第 448 行 `_resolve_simbad_object`

**问题**：`functools.lru_cache` 会缓存所有返回值**包括异常**。SIMBAD 查询抛一次网络异常 → 该天体名字永久返回错误。

**修复步骤**：
1. 去掉 `@lru_cache` 装饰器
2. 手写一个带 TTL 的缓存（复用 `cache.py` 中的模式），只缓存成功结果，不缓存异常
3. 或在 wrapper 中 catch 异常后不 raise，而是跳过缓存直接 propagate：
   ```python
   @lru_cache(maxsize=512)
   def _resolve_simbad_object_cached(name: str):
       try:
           return _do_resolve(name)
       except Exception:
           _resolve_simbad_object_cached.cache_clear()  # 清除本条
           raise
   ```
   （注意：`lru_cache` 没有「清除单条」的 API，`cache_clear()` 会清空全部。建议手写。）

**预估工时**：1.5h
**依赖**：无
**排期**：Day 1

---

### 🔴 P0-3: Placefinder bridge 忽略 `geotiff_path` / `db_config_path` 变更

**位置**：`src/placefinder.py` 第 129–135 行

**问题**：`_init_analyzer` 比较 `_last_params` 判断是否需要重新初始化，但只比较 `min_height_diff` 和 `road_radius_km`，不比较 `geotiff_path` 和 `db_config_path`。传了新配置文件路径 → 分析器不重建 → 用旧配置跑出结果。

**修复步骤**：
1. 在 `_last_params` 中加入 `geotiff_path` 和 `db_config_path`（如果传入了）
2. 或者改为：每次调用时比较完整的参数字典（`**kwargs` 的 hash），任一参数变化就重建
3. 加一个测试：两次调用传不同 `db_config_path`，验证分析器被重建

**预估工时**：1h
**依赖**：无
**排期**：Day 1

---

### 🟠 P1-1: 桥接层异常类型用字符串匹配而非 `isinstance`

**位置**：`src/functions/places/impl.py` 第 20–37 行 `_translate_spf_error`

**问题**：
```python
exc_name = type(exc).__name__
if exc_name == "NoDataError":       # 名字一改就挂
    ...
```

**修复步骤**：
1. 从 SPF 公共 API 导入异常类（要求 SPF 在 `__all__` 中暴露异常类型）
2. 改为 `isinstance` 检查：
   ```python
   from stargazingplacefinder import NoDataError, ConfigError, ...
   if isinstance(exc, NoDataError):
       ...
   ```
3. 如果 SPF 尚未暴露异常类，先在 SPF 侧加 `src/stargazingplacefinder/__init__.py` 的 re-export
4. 保留一个 `else` 兜底用 `exc_name` 打 warning 日志（便于发现新增异常类型）

**预估工时**：1.5h（含 SPF 侧配合）
**依赖**：需要 SPF 侧配合在公开 API 中暴露异常类
**排期**：Day 2–3

---

### 🟠 P1-2: 桥接层静默吞配置加载异常

**位置**：`src/placefinder.py` 第 98–103 行

**问题**：
```python
try:
    from config import load_stargazing_config
    spf_config = load_stargazing_config(config_path)
except Exception:        # <-- 裸 Exception，吞一切
    spf_config = None    # <-- 静默降级，无日志
```

**修复步骤**：
1. 至少 catch 具体的异常类型（`FileNotFoundError`、`ValueError`、tomllib 解析错误等）
2. 捕获后打 **至少 WARNING 级别** 日志：`logger.warning("Failed to load SPF config from %s: %s", config_path, e)`
3. 绝对不要 catch `KeyboardInterrupt` / `SystemExit`（用 `except Exception` 而非 `except BaseException` 勉强可以，但还是要加日志）
4. 考虑：配置加载失败是否应该是 fatal error 而非静默降级？如果 SPF 没有配置就无法正常工作，应该 raise 而非返回 None

**预估工时**：0.5h
**依赖**：无
**排期**：Day 2

---

### 🟠 P1-3: `fastmcp` 版本未锁定

**位置**：`pyproject.toml` 第 22 行

**问题**：
```toml
"fastmcp",   # 无版本约束，上游 breaking change 直接炸
```

**修复步骤**：
```toml
# 改为（以当前 lock 文件中的版本为准）：
"fastmcp>=2.0.0,<3.0.0",
```
1. 查看 `uv.lock` 中当前锁定的 fastmcp 版本
2. 设置合理的主版本上限（fastmcp 遵循 semver 的话就 `<NEXT_MAJOR>`）
3. CI 中加一个 `uv lock --check` 步骤确保 lock 文件和约束一致

**预估工时**：0.25h
**依赖**：无
**排期**：Day 2

---

### 🟠 P1-4: `astropy[all]` 过度依赖

**位置**：`pyproject.toml` 第 23 行

**问题**：项目只用了 `units`、`coordinates`、`time`、`iers` 四个子模块，但 `[all]` 拖进来了 `matplotlib`、`scipy`、`h5py`、`pyarrow` 等 15+ 个包。Docker 镜像体积无谓膨胀。

**修复步骤**：
1. 改为精确指定所需子模块：
   ```toml
   "astropy>=6.0",
   ```
   （astropy 的核心功能不需要 extras，`units`/`coordinates`/`time`/`iers` 都在基础包里）
2. 如果确实需要 `astroquery`（SIMBAD 查询），单独列：
   ```toml
   "astroquery",
   ```
3. 构建 Docker 镜像后对比体积差异
4. 跑全部测试确认无 ImportError

**预估工时**：0.5h
**依赖**：无
**排期**：Day 2

---

### 🟡 P2-1: 天气 provider 代码重复 ~60%

**位置**：
- `src/functions/weather/providers/open_meteo.py`（313行）
- `src/functions/weather/providers/qweather.py`（245行）
- `src/functions/weather/providers/wttr.py`（252行）

**问题**：三个 provider 遵循完全相同的 fetch → parse → normalize → return 模式，每个都有私有的 `_to_float` 等工具函数。

**修复步骤**：
1. 抽取抽象基类 `BaseWeatherProvider`：
   ```python
   class BaseWeatherProvider(ABC):
       @abstractmethod
       def fetch(self, ...) -> RawResponse: ...
       @abstractmethod
       def normalize(self, raw: RawResponse) -> NormalizedWeatherData: ...
       
       # 共享工具方法
       @staticmethod
       def _to_float(value, default=0.0): ...
       @staticmethod
       def _safe_index(data, index, default=None): ...
   ```
2. 三个 provider 继承基类，只实现 `fetch` 和 `normalize`
3. 更新 `service.py` 的 provider 调度逻辑（改为针对基类编程）
4. 跑全部天气相关测试

**预估工时**：4h
**依赖**：无
**排期**：Day 4–5

---

### 🟡 P2-2: `calculate_nightly_forecast` 134 行上帝函数

**位置**：`src/celestial.py` 第 306 行

**问题**：一个函数做五件事：时间窗口生成、月亮惩罚、行星可见性、深空天体评分、排序聚合。无法单独测试每个环节。

**修复步骤**：
1. 拆分为 5 个独立函数：
   - `_generate_time_grid(start, end, interval)` → `list[TimeInfo]`
   - `_score_moon_penalty(time, location)` → `float`
   - `_score_visible_planets(time, location)` → `list[PlanetScore]`
   - `_score_deep_sky_objects(time, location, moon_penalty)` → `list[ObjectScore]`
   - `_aggregate_forecast(scores)` → `NightlyForecast`
2. 主函数变为纯编排：
   ```python
   def calculate_nightly_forecast(...):
       grid = _generate_time_grid(...)
       scores = [_score_single_time(t, loc) for t in grid]
       return _aggregate_forecast(scores)
   ```
3. 为每个拆分出的函数写单元测试

**预估工时**：3h
**依赖**：无
**排期**：Day 5–6

---

### 🟡 P2-3: 死代码——`schemas/error.py` 中的 `ErrorCode` StrEnum 零引用

**位置**：`src/schemas/error.py`（21行）

**修复步骤**：
1. **方案 A（推荐）**：让 `MCPError` 使用 `ErrorCode`：
   ```python
   # src/response.py
   from src.schemas.error import ErrorCode
   
   class MCPError(Exception):
       def __init__(self, code: ErrorCode, message: str, details: Any = None):
           ...
   ```
   同时更新所有 `raise MCPError("VALIDATION_ERROR", ...)` 调用为 `raise MCPError(ErrorCode.VALIDATION_ERROR, ...)`

2. **方案 B**：如果觉得改量太大，直接删掉 `schemas/error.py`，别留死代码

**预估工时**：1h（方案B）/ 2h（方案A）
**依赖**：无
**排期**：Day 3

---

### 🟡 P2-4: 死 import——`calc_visible_planets` 别名未使用

**位置**：`src/functions/celestial/impl.py` 第 131 行

**问题**：
```python
from src.celestial import get_visible_planets as calc_visible_planets  # 第131行
...
# 第133行：calc_visible_planets(...) — 但这个名称实际已被第141行的赋值覆盖
get_visible_planets = list_visible_planets  # 第141行覆盖了模块级名称
```

**修复步骤**：
1. 确认 `calc_visible_planets` 在模块中再无其他引用
2. 如果不使用，删除该 import
3. 如果需要的是原始函数（未装饰版本），在 import 时重命名为 `_raw_visible_planets` 并直接使用它

**预估工时**：0.25h
**依赖**：无
**排期**：Day 3

---

### 🟡 P2-5: Planning 工具通过 `.fn` 裸调其他工具——脆弱的运行时耦合

**位置**：`src/functions/planning/impl.py` 第 5–27 行

**问题**：直接 import 其他工具的 `.fn` 属性（装饰前的原始函数），任何签名变更在运行时才暴露。

**修复步骤**：
1. 将共享逻辑抽取到一个**独立于工具层的 service 模块**中：
   ```
   src/services/
   ├── analysis.py    # 从 places/impl.py 抽出的核心逻辑
   ├── weather.py     # 从 weather/impl.py 抽出的核心逻辑
   └── forecast.py    # 从 celestial/impl.py 抽出的核心逻辑
   ```
2. Planning 工具 import service 层函数，而非其他工具的 `.fn`
3. 各工具的 `impl.py` 变成薄包装：校验参数 → 调 service → 格式化响应

**预估工时**：4h（涉及多处重构）
**依赖**：P2-2（forecast 拆分与这个有交集，可一起做）
**排期**：Day 6–7

---

### 🟢 P3-1: 清理测试中的 `print('DEBUG: ...')`

**位置**：
- `tests/test_moon.py`
- `tests/test_constellation.py`
- `tests/test_planets.py`
- `tests/test_forecast.py`

**修复步骤**：
1. 删除所有 `print()` 语句
2. 如果确实需要调试输出，用 `logging.debug()` + pytest 的 `--log-cli-level=DEBUG`
3. 将 smoke test 转为真正的断言测试（mock 外部依赖，验证返回值结构）

**预估工时**：2h
**依赖**：无
**排期**：Day 4

---

### 🟢 P3-2: 补写 `test_retry.py`

**位置**：新建 `tests/test_retry.py`

**需覆盖的边界条件**：
| 场景 | 预期行为 |
|------|----------|
| 成功在第 1 次 | 不重试，返回结果 |
| 成功在第 3 次（最后一次） | 重试 2 次后成功 |
| 全部 3 次失败 | 抛出最后一次的异常 |
| `max_attempts=1` | 不重试，直接失败 |
| `backoff_factor=1`（线性） | 延迟为 1s, 2s, 3s... |
| `max_delay` 命中上限 | 延迟不超上限 |
| 异步函数装饰 | 正确 await 异步函数 |
| `retryable_errors` 过滤——不可重试异常 | 直接 raise，不重试 |

**预估工时**：2.5h
**依赖**：无
**排期**：Day 5

---

### 🟢 P3-3: CI/CD 统一使用 `uv` 替代 `pip`

**位置**：
- `.github/workflows/ci.yml` 第 81 行（`pip install diff-cover`）
- `.github/workflows/release-pypi.yml` 第 27 行（`pip install build`）
- `Dockerfile` 第 29、40、62 行（`pip install setuptools wheel`）

**修复步骤**：
```yaml
# ci.yml: pip install diff-cover  →  uv pip install diff-cover
# 或加到 dev dependencies:
# uv add --dev diff-cover
# 然后在 CI 中: uv run diff-cover ...
```
Dockerfile 同理，统一 `uv pip install` 而非裸 `pip install`。

**预估工时**：0.5h
**依赖**：无
**排期**：Day 4

---

### 🟢 P3-4: Dockerfile 去掉无意义的 `uv cache clean`

**位置**：`Dockerfile` 第 31、42、48、64、70 行

**问题**：每次 `uv sync` 后立即 `uv cache clean`，导致多阶段构建中每个阶段重新下载所有包，与缓存目的背道而驰。

**修复步骤**：
1. 删除所有 `uv cache clean` 行
2. 只在最后一个生产阶段（prod）的末尾做一次 `uv cache clean`（减小最终镜像体积）
3. 中间阶段保留缓存，利用 Docker BuildKit 的 `--mount=type=cache` 跨构建复用：
   ```dockerfile
   RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
   ```

**预估工时**：0.5h
**依赖**：无
**排期**：Day 4

---

### 🟢 P3-5: Dockerfile 加 `HEALTHCHECK`

**位置**：`Dockerfile`

**修复步骤**：
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3001/health')" || exit 1
```

**预估工时**：0.25h
**依赖**：需要确认 `/health` 端点存在且返回 200
**排期**：Day 4

---

### 🟢 P3-6: 天气模块中文 docstring 国际化

**位置**：
- `src/functions/weather/impl.py`
- `src/qweather_interaction.py`

**修复步骤**：
1. 将中文参数说明翻译为英文
2. 保持术语一致性（CJK 地名处理保留中文注释说明业务逻辑即可）
3. 跑 lint 确认格式

**预估工时**：1h
**依赖**：无
**排期**：Day 5

---

## 三、跨项目任务

### 🟠 P1-CROSS: 桥接层 `sys.path` 注入——最根本的技术债

**位置**：
- MCP 侧：`src/placefinder.py` 第 43 行 + `src/paths.py`
- SPF 侧：内部裸 `from models import ...` 风格的导入

**问题**：MCP 通过 `sys.path.insert(0, SPF_SRC_ROOT)` 让 SPF 的裸导入工作。这是两边的共同问题。

**修复步骤（两阶段）**：

**阶段一：SPF 侧改正导入（SPF 负责）**
1. 在 SPF 中逐步将裸导入改为包相对导入：
   ```python
   # 之前
   from models import GeoCoordinate
   # 之后
   from ..models import GeoCoordinate
   # 或使用完整包路径
   from stargazingplacefinder.models import GeoCoordinate
   ```
2. 更新 SPF 的 `pyproject.toml` 确保包正确安装后可被 `import stargazingplacefinder` 发现
3. 跑 SPF 全部测试确认无 ImportError

**阶段二：MCP 侧移除 workaround（MCP 负责）**
1. 删除 `src/paths.py`（不再需要 sys.path 操作）
2. 删除 `src/placefinder.py` 中的 `_prepare_spf_import_path()` 调用
3. 改为标准 `import stargazingplacefinder`（通过 pip 安装的包）
4. 跑 MCP 全部测试确认无 ImportError

**预估工时**：SPF 侧 2h + MCP 侧 1h = 3h
**依赖**：SPF 侧先完成
**排期**：SPF Day 5–6 → MCP Day 7

---

## 四、建议排期总表

```
Week 1（7月第一周）
┌──────────────────────────────────────────────────────────────┐
│  Mon   🔴 P0 扫雷日                                              │
│        SPF: 修3个测试 + TOML死catch + Overpass死catch            │
│        MCP: 无锁缓存 + 毒缓存 + placefinder参数漏比较             │
│                                                                  │
│  Tue   🟠 P1 高风险日                                            │
│        SPF: 两个 except(Exception)反模式                          │
│        SPF: 缓存 TOCTOU 竞态                                     │
│        MCP: 字符串异常匹配 → isinstance                           │
│        MCP: 配置静默吞异常 + fastmcp/astropy版本锁                │
│                                                                  │
│  Wed   🟡 P2 质量日（前半）                                        │
│        SPF: Haversine去重 + TOML import去重                      │
│        MCP: ErrorCode死代码 + calc_visible_planets死import       │
│                                                                  │
│  Thu   🟡 P2 质量日（后半）+ 🟢 P3 优化                             │
│        SPF: Overpass静默失败改抛异常                              │
│        MCP: 清理DEBUG print + 统一uv/pip + Dockerfile优化         │
│                                                                  │
│  Fri   🟡 P2 大活                                                 │
│        SPF: 包相对导入改造（为跨项目任务铺路）                      │
│        MCP: 补写 test_retry.py + 中文docstring英文化              │
│                                                                  │
│  Sat   🟡 P2 大活（续）                                            │
│        MCP: 天气provider去重（抽基类）                            │
│        MCP: calculate_nightly_forecast 拆分                      │
│        MCP: Planning工具解耦（service层抽取）                     │
│                                                                  │
│  Sun   🟠 跨项目收尾                                               │
│        MCP: 删除 sys.path workaround（依赖SPF完成改造）           │
│        全量测试 + lint + 收尾文档更新                              │
└──────────────────────────────────────────────────────────────┘
```

### 工时汇总

| 项目 | P0 | P1 | P2 | P3 | 小计 |
|------|----|----|----|----|------|
| SPF | 2h | 4h | 3h | 0.5h | **9.5h** |
| MCP | 5.5h | 3.75h | 12.5h | 7h | **28.75h** |
| Cross | — | 3h | — | — | **3h** |
| **总计** | **7.5h** | **10.75h** | **15.5h** | **7.5h** | **41.25h** |

> 总计约 **5 个工作日**的纯编码时间。考虑到开会、CR、修 CI 等开销，建议预留 **7–8 个工作日**。

---

## 五、后续持续改进建议

1. **pre-commit 加检查**：加一个 hook 禁止 `except Exception: pass`（至少要求 `logger.exception(...)`）
2. **CI 加 nightly build**：每周跑一次全量测试 + 依赖更新检查，避免上游 breaking change 偷袭
3. **测试覆盖率门槛提升**：当前 SPF 60% / MCP 未强制，建议 SPF → 75%、MCP → 70%
4. **SPF 公开 API 契约**：明确定义 `__all__` 包含哪些类/函数/异常，MCP 只依赖公开 API
5. **mypy 严格模式**：逐步开启 `disallow_untyped_defs`、`no_implicit_optional` 等严格检查

---

*本文档由 Claude Code 基于 2026-06-30 双项目代码审查生成。任务优先级和排期是建议，请根据实际团队带宽调整。*
