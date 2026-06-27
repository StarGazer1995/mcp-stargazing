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

- 构造参数（`geotiff_path`、`min_height_difference`、`road_search_radius_km`、`db_config_path`）在首次调用 `analyze_area()` 时生效
- 仅当 `min_height_diff` 或 `road_radius_km` 变更时才重建底层 analyzer，避免重复打开 GeoTIFF 文件和重建数据库连接池
- `analyze_area()` 返回 `list[dict[str, Any]]`，每个元素是下层 `StargazingLocation` 对象的字典表示

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
- 通过 `src/models/places.py` 定义自己的 Pydantic 模型（`StargazingLocation.from_spf_location()` 做转换）
- 在工具层（`src/functions/places/impl.py`）做缓存、分页、响应包装
- 不直接 import 下层的任何模型类

## 导入边界与 `models` 命名冲突

### 问题根因

- `mcp-stargazing` 有 `src/models/` 包（Pydantic 模型）
- `stargazing-place-finder` 依赖链中也有 `models` 包
- 两个 `models` 包在同一 Python 进程中会互相遮蔽

### 当前解法（`src/paths.py`）

`paths.py` 提供以下工具函数，由 `placefinder.py` 在加载下层模块前调用：

| 函数 | 职责 |
|------|------|
| `find_module_origin()` | 安全查找模块的来源路径 |
| `is_repo_models_origin()` | 判断一个模块来源是否属于本 repo 的 `src/models/` |
| `discard_shadowing_module()` | 从 `sys.modules` 中移除被本 repo `models` 遮蔽的缓存模块 |
| `prioritize_sys_path()` | 将下层 repo 的 source root 提升到 `sys.path` 最前面 |
| `resolve_package_source_root()` | 解析任意包的 source root 路径 |

加载流程：

1. `resolve_package_source_root('stargazingplacefinder')` 确定下层 repo 的根路径
2. `find_module_origin('models')` 检查当前 `models` 模块的来源
3. 如果 `models` 来自本 repo，则 `discard_shadowing_module` 清理缓存
4. `prioritize_sys_path` 将下层根路径排到最前
5. `importlib.import_module('stargazingplacefinder')` 加载下层

### 长期方向

当前方案已将运行时补丁严格隔离在 `paths.py` 中，并通过 `test_paths.py` 覆盖。长期来看，更彻底的解法包括：

- 将 `mcp-stargazing/src/models/` 重命名为 `src/schemas/` 或 `src/dtos/` 避免与下层 `models` 冲突
- 或将下层 `models` 包重命名
- 或通过 namespace package 隔离两个 repo

无论选择哪种长期方案，当前 `paths.py` 的抽象已足够支撑现有功能，且运行时修补逻辑不扩散到 `paths.py` 之外。

## 调用链总览

### `analysis_area` 完整调用链

```
MCP Agent
  → tools/call (analysis_area)
    → src/functions/places/impl.py      # 缓存、分页、响应包装
      → src/placefinder.py              # Bridge: StargazingPlaceFinder.analyze_area()
        → src/paths.py                  # 导入边界修复
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
        → src/paths.py                  # 导入边界修复
        → stargazingplacefinder         # 下层 public API
          → light_pollution             # GeoTIFF 查询
```

## 测试覆盖

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_paths.py` | 路径解析、模块来源检测、shadow 清理、sys.path 重排 |
| `tests/test_placefinder.py` | Bridge 的构造、参数变更重建、analyze_area 转发、get_light_pollution_grid 转发 |

## 变更规则

- 新增下层能力的 bridge 转发时，优先保持函数签名与下层一致，不做额外语义转换
- Bridge 层不引入新的业务模型，只做轻量参数适配
- 任何对 `paths.py` 的修改必须同步更新 `tests/test_paths.py`
- 如果下层 public API 发生 breaking change，需要同时更新 bridge 接口和本文件
