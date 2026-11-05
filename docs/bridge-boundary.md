# Bridge 边界说明

## 定位

`mcp-stargazing/src/placefinder.py` 是 `mcp-stargazing` 与 `stargazing-place-finder` 之间的唯一桥接层。其职责可以用一句话描述：

> **将下层 domain engine 的地点分析能力，以可控、可测试的方式暴露给上层 MCP 工具层，同时隔离跨 repo 的导入边界问题。**

## Bridge 层暴露的公开接口

| 接口 | 类型 | 用途 |
|------|------|------|
| `StargazingPlaceFinder` | class | 封装下层 analyzer 的初始化与 `analyze_area` 调用，支持参数变更时自动重建 analyzer |
| `get_light_pollution_grid()` | function | 薄代理，直接转发到 `stargazingplacefinder.get_light_pollution_grid()` |

### `StargazingPlaceFinder` 约定

- 构造时初始化或复用底层 analyzer；每次实际 `analyze_area()` 都重新核对自己的参数和公共配置加载器返回的有效模型
- 参数或有效配置变化时通过 SPF 公共初始化入口重建 analyzer；相同配置模型继续复用 GeoTIFF 文件和数据库连接池，即使配置文件的格式/身份变化
- `analyze_area()` 返回 `list[dict[str, Any]]`，每个元素是下层 `StargazingLocation` 对象的字典表示

### 配置新鲜度的边界

`stargazingplacefinder.config.load_stargazing_config()` 在每次实际计算前重新调用；bridge
不复制其默认路径发现、TOML 解析或字段规则。复用判断同时包含有效配置模型，不能仅凭
请求/文件路径相同就永久沿用旧配置。重用同一个 bridge 实例、切换 `STARGAZING_CONFIG`
或修改同一 TOML 的有效值时，下一次实际计算会重新核对；不同实例交替使用也会恢复各自
的参数。加载失败保持既有 defaults 降级，不把失败当成已确认配置最新。

这是 bridge 的实际计算配置核对；上层生产结果缓存另外观察显式 `STARGAZING_CONFIG`
路径及文件元数据，变化时失效并拒绝旧代次发布。没有身份观察器的独立缓存仍只按
自己的 TTL 复用。元数据保护不等于读取配置内容或证明地理资料更新。数据库内容、
同路径数据库连接配置、GeoTIFF 内容版本以及下层 GIS/道路缓存失效仍未统一处理，不能
据本轮修复声称来源资料已更新或 P7.6 已完成。构造时解析的 DB/GeoTIFF 路径仍是该
bridge 实例的参数，不会被后续环境变化隐式替换。

缓存的配置代次与 bridge 的有效模型比较分工不同：格式或文件身份变化可以保守地使
结果失效，但新模型值相等时仍可复用 analyzer 资源；源配置元数据不可验证时，上层
拒绝缓存复用/发布。具体边界见 `analysis-area-semantics.md`。

### 热门度评分归属

- 单独调用 `analysis_area` 时，bridge 原样传递热门度偏好，SPF 负责调整地点分与排序。
- 单晚、多晚和主规划入口均由 `PlanningService` 请求中性地点分：传入 SPF 的
  `avoid_popular_spots` 与 `prefer_quiet_at_night` 固定为 `False`，半径照常传递。
- SPF 在关闭偏好时仍生成热门度启发式字段；MCP 使用这些字段在
  `score_breakdown.popularity_adjustment` 中应用用户偏好一次。粗排和精排分别从中性分计算。
- 规划器注入的 `search_places` 依赖也必须遵守这个约定；直接调用
  `evaluate_candidate` 时，传入的地点分必须不含热门度偏好调整。
- 规划的 `analysis_resource_id` 对应中性查询，可用相同地点搜索参数、半径和两个
  `False` 偏好标志重查分页。带偏好的独立地点查询使用不同缓存条目。

### `get_light_pollution_grid()` 约定

- 每次调用都重新 `importlib.import_module` 加载下层模块
- 直接转发参数，不做缓存或转换
- 返回 `dict[str, Any]`

## 不应由 Bridge 层承担的职责

以下能力属于 `stargazing-place-finder` 内部实现，bridge 层**不应直接暴露**：

| 下层内部实现 | 原因 |
|-------------|------|
| GeoTIFF 句柄管理与资源生命周期 | 属于下层 resource management，bridge 通过 `analyzer` 间接使用 |
| PostGIS / Overpass 查询实现 | 属于下层 GIS 服务内部细节 |
| 道路网络预载与复用 | 属于下层 `road_connectivity` 模块内部优化 |
| 并行分析调度 | 属于下层 `stargazing_analyzer` 的并发策略 |
| GIS 查询 fallback 链 | 属于下层容错逻辑 |
| 下层 `models` 模块的内部数据结构 | 避免跨 repo 的模型耦合 |

上层（`mcp-stargazing`）应该：
- 通过 `src/schemas/places.py` 定义自己的 Pydantic 模型（`StargazingLocation.from_spf_location()` 做转换）
- 在工具层（`src/functions/places/impl.py`）做缓存、分页、响应包装
- 不直接 import 下层的任何模型类

## 导入边界

`mcp-stargazing` 最低支持 `stargazing-place-finder>=0.9.4`。Bridge 只导入
`stargazingplacefinder` 命名空间下的公共 API，不再修改 `sys.path`，也不兼容旧版
顶层 `config` / `models` / `cache` 布局。

这一版本同时把 MCP 自身的分析缓存模块从 `src/cache.py` 改名为
`src/analysis_cache.py`，避免源码测试环境把 MCP 的 `cache` 模块暴露为顶层包并与
SPF 的内部模块发生名称遮蔽。

依赖缺失时，bridge 会明确提示需要安装
`stargazing-place-finder>=0.9.4`。配置只从
`stargazingplacefinder.config.load_stargazing_config` 加载。

## 调用链总览

### `analysis_area` 完整调用链

```
MCP Agent
  → tools/call (analysis_area)
    → src/functions/places/impl.py      # 缓存、分页、响应包装
      → src/placefinder.py              # Bridge: StargazingPlaceFinder.analyze_area()
        → stargazingplacefinder         # 下层 public API
          → stargazing_analyzer         # 综合分析引擎
            → light_pollution           # 光污染查询
            → gis_service               # GIS 查询
            → road_connectivity         # 道路可达性
```

### `light_pollution_map` 完整调用链

```
MCP Agent
  → tools/call (light_pollution_map)
    → src/functions/places/impl.py      # 模型转换、响应包装
      → src/placefinder.py              # Bridge: get_light_pollution_grid()
        → stargazingplacefinder         # 下层 public API
          → light_pollution             # GeoTIFF 查询
```

网格适配器识别 SPF 的明确 `overlay_name="默认数据"` 标记。其 Bortle 5、SQM 20、
亮度和颜色是显示占位值，不能作为来源数据；MCP 保留坐标、点名和该标记，将这些
可空字段返回为 `null`，并在既有 `_meta.warnings` 中报告数量。不会仅凭 Bortle 5、
灰色或缺失 radiance 猜测占位点；没有该标记的既有值继续保留。网格点数、bounds、zoom、
工具参数和公共模型不变，不修改上游 Web 默认显示，也不改变独立地点/规划评分链。

## 测试覆盖

后台任务与同步区域分析复用 `compute_area_locations` 和 `build_analysis_page`。
前者只计算而不发布缓存；任务执行器在取消/超时状态检查与成功确认的同一锁范围内发布。
区域计算会串行进入 SPF 的全局 analyzer，避免后台与同步请求同时重新配置该单例。
线程执行配额与地点计算锁是不同边界，详见 `task-lifecycle.md`。

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_paths.py` | 仓库路径常量 |
| `tests/test_placefinder.py` | Bridge 的构造、配置加载、legacy fallback、analyze_area 转发、get_light_pollution_grid 转发 |
| `tests/test_bridge_config_refresh.py` | 合成 TOML 的真实公共加载、同实例/跨实例配置复用、SDK 缓存未命中与后台实际计算 |

## 变更规则

- 新增下层能力的 bridge 转发时，优先保持函数签名与下层一致，不做额外语义转换
- Bridge 层不引入新的业务模型，只做轻量参数适配
- 任何对仓库路径常量的修改必须同步更新 `tests/test_paths.py`
- 如果下层 public API 发生 breaking change，需要同时更新 bridge 接口和本文件
