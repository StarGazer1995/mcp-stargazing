# Workspace 全面评估 — 2026-06-28

> 基于实际代码状态逐文件验证，非文档二手信息。
> 覆盖 `mcp-stargazing`（v0.5.1）和 `stargazing-place-finder`（v0.6.6）。

---

## 一、🐛 应该修的 Bug

### 严重（数据正确性 / 并发安全）

| # | 项目 | 位置 | 问题 | 状态 |
|---|------|------|------|------|
| 1 | SPF | `road_connectivity_checker.py:544,549` | **双重 PostGIS 查询** — `_try_postgis_info` 对同一个点连续调用 `query_road_connectivity` 两次 | ✅ 已修复 (2026-06-30) |
| 2 | SPF | `stargazing_location_analyzer.py:286` + `road_connectivity_checker.py:421` | **NetworkX 图并发读** — `_shared_graph` 被 4 个 ThreadPoolExecutor worker 同时读取，NetworkX `MultiDiGraph` 非线程安全 | ✅ 已修复 (2026-06-30) |
| 3 | SPF | `light_pollution_api.py:230-231` | **瓦片缓存整体清空** — 超 500 条时 `_tile_cache.clear()` 丢弃全部缓存，无 LRU、无 TTL | ✅ 已修复 (2026-06-30) |
| 4 | MCP-SG | `celestial.py:395-404` | **月相惩罚检查了错误对象的高度** — 应检查月亮高度但检查了目标天体高度。月亮在地平线以下时不应加光害惩罚 | ✅ 已修复 (2026-06-30) |
| 5 | MCP-SG | `placefinder.py:13,68` | **`_last_params` 无锁读写** — 模块级全局变量在 `_init_analyzer()` 中无锁比较和写入，并发请求会竞态 | ✅ 已修复 (2026-06-30) |

### 中等（错误处理 / 静默失败）

| # | 项目 | 位置 | 问题 | 状态 |
|---|------|------|------|------|
| 6 | SPF | `overpass_backend.py:218` | **Overpass 失败返回 `[]`** — 和"成功但无结果"无法区分 | |
| 7 | SPF | `overpass_backend.py:137-218` | **无总超时** — 单请求 60s × 最多 6 次重试 = 最长 375 秒。无 deadline | ✅ 已修复 (2026-06-30) |
| 8 | MCP-SG | `functions/places/impl.py` | **SPF 异常零捕获** — SPF 异常直接穿透到 FastMCP 层，变成无上下文泛化错误 | ✅ 已修复 (2026-06-30) |
| 9 | MCP-SG | `planning/impl.py:86-134 vs 175-204` | **降水惩罚系数不一致** — 窗口排序 `* 20.0`，最终推荐 `* 10.0`，差 2 倍 | ✅ 已修复 (2026-06-30) |
| 10 | MCP-SG | `celestial.py:445-458` | **4 处 `print()` 调试语句** — `_resolve_simbad_object` 每次查询往 stdout 输出 `[DEBUG]` | ✅ 已修复 (2026-06-30) |

### 低（代码卫生）

| # | 项目 | 位置 | 问题 |
|---|------|------|------|
| 11 | SPF | `road_connectivity_checker.py:27` | **`logging.basicConfig` 模块级副作用** — import 时强制覆盖全局日志配置 |
| 12 | SPF | `elevation_backend.py:141` | **`time.sleep(0.1)` 硬编码** — 批量高程查询节流延迟无文档无配置 |
| 13 | MCP-SG | `celestial.py:286` | **裸 `print()` 替代 `logging.warning()`** |
| 14 | SPF | `light_pollution_api.py:440-483` | **`/api/light_pollution_images` 死端点** — 永远返回 "GeoTIFF backend does not support image extraction" |

---

## 二、🏗️ 架构改进

### 两个项目共同缺失：可观测性

- **结构化日志**：SPF 无，MCP-SG 仅 `geocoding.py` 一处用了 `logging.getLogger`，其余全用 `print()` 和裸 `logging.info(%s)`
- **指标**：无 Prometheus/statsd/OpenTelemetry
- **健康检查**：SPF `/api/health` 仅返回 bool，MCP-SG 无健康检查端点
- **请求追踪**：无 correlation ID，跨服务调用链无法追溯

**建议**：加 `structlog` + request_id 贯穿 MCP-SG → SPF 调用链。

### SPF 特定

1. **评分系统完全硬编码** — 35/20/20/15/10 权重、每个 Bortle 级的分数、道路距离硬阈值（200m 满分，200.1m 减半），全部写死。`StargazingConfig` 无评分权重字段。
   - **建议**：评分权重和阈值加入 `StargazingConfig`；硬阈值改成平滑函数（sigmoid/线性插值）。

2. **瓦片下载无并行** — `preload_network_for_bbox` 中 tiles 是 for 循环逐个下载。大 bbox 切 20 个 tile = 20 次串行 HTTP。
   - **建议**：`ThreadPoolExecutor` 或 `asyncio.gather` 并行下载。

### MCP-SG 特定

1. **Placefinder 桥接是最脆弱的环节**：
   - `sys.path` 操作在非 editable 安装的 SPF 上失效
   - SPF 异常穿透无翻译（Bug #8）
   - 并发请求不同参数时竞态（Bug #5）
   - SPF 未安装时 `ModuleNotFoundError` 导致 `places/impl.py` 整体 import 崩溃
   - **建议**：工具函数层面加 try/except 翻译成 `MCPError`；`_last_params` 加锁；长期推动 SPF 清理内部 import 结构。

2. **天气 Provider 串行调用** — `service.py` 中 `for pname in provider_names` 顺序执行，`all` 模式最长 45 秒。
   - **建议**：`asyncio.gather` 并行查询 + 总超时。

3. **缓存无界增长** — `AnalysisCache` 只有 TTL 无 maxsize。不同参数反复调会无限吃内存。
   - **建议**：加 `maxsize` + LRU 淘汰。

4. **5 个 Pydantic Schema 定义但从未使用** — `GeoPoint`、`GeoBounds`、`TimeInfo`、`ErrorCode`（StrEnum）、`PaginatedResult[T]`。
   - **建议**：用起来或删掉。

---

## 三、🚀 值得开发的功能

### 短期（高价值、低成本）

| 优先级 | 项目 | 功能 | 理由 |
|--------|------|------|------|
| P0 | 两个 | 结构化日志 + request_id | 没有日志的生产服务无法排障 |
| P0 | MCP-SG | SPF 错误翻译层 | 现在 SPF 异常直接穿透，LLM 拿到无意义错误 |
| P1 | MCP-SG | 健康检查端点 | 容器探活、负载均衡 health check |
| P1 | SPF | Dockerfile | 当前 Flask 裸跑 + 无容器化 = 无法生产部署 |
| P2 | MCP-SG | 并行天气查询 | `asyncio.gather` 三 provider 并行 + 总超时 |

### 中期（需要设计）

| 优先级 | 项目 | 功能 | 理由 |
|--------|------|------|------|
| P1 | SPF | 可配置评分权重 | 加入 `StargazingConfig`，不同地区/偏好可调参 |
| P1 | SPF | 平滑评分函数 | sigmoid/线性插值替代硬阈值，消除断崖 |
| P2 | SPF | LRU 瓦片缓存 | 替代 `_tile_cache.clear()` 暴力清空 |
| P2 | SPF | 并行道路网络下载 | tile 下载并行化 |
| P2 | MCP-SG | 缓存 size limit + LRU | `AnalysisCache` 加 maxsize |
| P3 | MCP-SG | 清理 sys.path hack | 推动 SPF 修复内部 import 结构 |

### 长期（新能力）

| 优先级 | 项目 | 功能 | 理由 |
|--------|------|------|------|
| P2 | SPF | 国际光污染数据 | 目前硬编码中国 VIIRS GeoTIFF，支持全球数据可打开国际市场 |
| P2 | MCP-SG | ISS / 卫星过境 | Skyfield / TLE 数据，`get_satellite_passes` 工具 |
| P3 | MCP-SG | 流星雨 / 日食预测 | `get_upcoming_meteor_showers`、`get_next_eclipse` |
| P3 | MCP-SG | 望远镜推荐 | `get_best_targets_for_telescope`，按口径/季节/难度 |
| P3 | MCP-SG | 用户偏好配置 | 深空摄影 vs 目视 vs 行星，不同偏好调整推荐权重 |
| P3 | SPF | 观测点历史评价 | 用户上报实际体验，反馈到推荐排序 |

---

## 四、📋 优先级行动清单

### 现在就该做的（本周）— ✅ 全部完成 (2026-06-30)

- [x] SPF: 修双重 PostGIS 查询（改 `_check_via_postgis` 返回 dict，消除第二次 `query_road_connectivity`）
- [x] SPF: 修 NetworkX 图并发读（加 `threading.Lock` 保护 `_shared_graph` 读写）
- [x] MCP-SG: 修月相惩罚检查错误对象的高度（用 `moon_altaz.alt.deg` 替代 `altaz.alt.deg`）
- [x] MCP-SG: 给 placefinder.py 加 SPF 异常翻译（`_translate_spf_error()` 映射 8 种 SPF 异常 → MCPError）
- [x] 两个: 删掉生产代码里的 `print()` 调试语句（MCP-SG 5处 → `logging`，SPF 已干净）

### 这个月该做的 — ✅ 全部完成 (2026-06-30)

| # | Sprint | 项目 | 项 | 理由 | 状态 |
|---|--------|------|----|------|------|
| 1 | 🔴 S1 | MCP-SG | 加 `/health` 端点 | 容器探活必需，10 行代码，无此无法正经部署 | ✅ |
| 2 | 🔴 S1 | MCP-SG | 并行天气查询 | `ThreadPoolExecutor` 三 provider 并行，最坏延迟 45s→15s | ✅ |
| 3 | 🔴 S1 | MCP-SG | 分析缓存加 maxsize + LRU | 防内存泄漏，`AnalysisCache` 当前无界增长 | ✅ |
| 4 | 🟡 S2 | 两个 | structlog + request_id | 无日志的生产服务等于盲飞，贯穿 MCP-SG → SPF 调用链 | ✅ |
| 5 | 🟡 S2 | SPF | 瓦片缓存 LRU + TTL | Bug #3：替代 `_tile_cache.clear()` 暴力清空 | ✅ |
| 6 | 🟡 S2 | MCP-SG | `_last_params` 加锁 | Bug #5：并发安全，投入极小 | ✅ |
| 7 | 🟢 S3 | SPF | Overpass 加总超时 | Bug #7：避免用户挂死等 375s | ✅ |
| 8 | 🟢 S3 | MCP-SG | 降水惩罚系数统一 | Bug #9：统一为 `* 20.0` | ✅ |

### 这个季度该做的 — ✅ 全部完成 (2026-06-30)

- [x] SPF: 可配置评分权重 — `StargazingConfig` 新增 5 个 weight 字段 + `road_distance_decay_km`
- [x] SPF: 平滑评分函数（去硬阈值） — 道路距离 sigmoid 衰减替代 200m 硬阈值，城镇距离 log 函数替代离散桶
- [x] SPF: Dockerfile + gunicorn — 多阶段构建，gunicorn 4 workers，`.dockerignore`
- [x] SPF: 并行道路网络 tile 下载 — `preload_network_for_bbox` 用 `ThreadPoolExecutor` 并行下载
- [x] MCP-SG: 清理 sys.path hack — 添加诊断日志 + 后续行动文档；完整修复需 SPF 侧 20+ 文件将 `from models` 改为包内相对导入

---

## 五、修复记录

### 2026-06-30 — 本周关键 Bug 修复（5 项）

| 项目 | 分支 | Commit | 修复内容 |
|------|------|--------|----------|
| SPF | `fix/critical-bugs-week-26-06-30` | `1759cf0` | Bug #1 (去重PostGIS查询) + Bug #2 (graph_lock) |
| MCP-SG | `fix/critical-bugs-week-26-06-30` | `c590c50` | Bug #4 (月相bug) + Bug #8 (SPF异常翻译) + Bug #10 (print→logging) |

### 2026-06-30 — 月度 Sprint 全部完成（8 项）

#### 🔴 S1（本周优先）

| # | 项 | 变更 | 说明 |
|---|-----|------|------|
| S1-1 | `/health` 端点 | `main.py` | FastMCP `custom_route` 注册 `GET /health`，返回 `{status, version, service}` |
| S1-2 | 并行天气查询 | `service.py` | `ThreadPoolExecutor` + `as_completed` 并行三 provider，`_query_provider_safe` 异常包装，`successful_providers`/`failed_providers` 排序保证确定性 |
| S1-3 | 缓存 maxsize + LRU | `cache.py` | `OrderedDict` 实现 LRU，默认 maxsize=128，get 时 `move_to_end` 标记热度，set 时 `popitem(last=False)` 淘汰最旧 |

#### 🟡 S2（次周）

| # | 项 | 变更 | 说明 |
|---|-----|------|------|
| S2-4 | structlog + request_id | 10 个文件 | 新增 `logging_config.py`（structlog 配置 + ContextVar request_id），6 个 tool 域注入 `set_request_id()`，替换 `celestial.py`/`geocoding.py`/`places/impl.py` 的 `logging.getLogger` 和 `main.py` 的 `print()` |
| S2-5 | SPF 瓦片缓存 LRU + TTL | `light_pollution_api.py` | `dict.clear()` → `OrderedDict` + `popitem(last=False)` LRU 淘汰 + 1 小时 TTL，新增 `_set_tile_cache()` 辅助函数 |
| S2-6 | `_last_params` 加锁 | `placefinder.py` | `threading.Lock()` 保护模块级参数比较和写入 |

#### 🟢 S3（三周）

| # | 项 | 变更 | 说明 |
|---|-----|------|------|
| S3-7 | Overpass 总超时 | `overpass_backend.py` | 新增 `total_timeout` 参数（默认 90s），`_request` 每次重试前检查 `elapsed >= total_timeout` |
| S3-8 | 降水惩罚系数统一 | `planning/impl.py` | `* 10.0` → `* 20.0`，与窗口排序一致 |

#### 新增测试

| 文件 | 测试数 | 覆盖内容 |
|------|--------|----------|
| `tests/test_cache.py` | 12 | LRU 淘汰、TTL 过期、key 更新、maxsize=1、边界条件 |
| `tests/test_main_entry.py` | +1 | `/health` 端点返回结构 |
| `tests/test_weather_service.py` | +1 | Provider 抛出 MCPError 时正确转为 ProviderError |

#### CI 通过情况

| 检查项 | MCP-SG | SPF |
|--------|--------|-----|
| ruff check | ✅ | ✅ |
| ruff format | ✅ | ✅ |
| bandit | ✅ 0 issues | N/A |
| pytest | ✅ 221 passed | N/A |
| diff-cover (vs HEAD) | ✅ **100%** | N/A |
