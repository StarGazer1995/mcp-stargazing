# `analysis_area` 响应语义说明

## 概述

`analysis_area` 是 `mcp-stargazing` 中复杂度最高的 MCP 工具。它搜索指定地理区域内的观星候选地点，并支持分页获取结果。本文档明确其分页、缓存和 `resource_id` 的语义约定，作为 agent 集成和测试的基线。

## 请求参数

### 搜索参数（影响计算结果）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `south` | float | — | 南边界纬度 |
| `west` | float | — | 西边界经度 |
| `north` | float | — | 北边界纬度 |
| `east` | float | — | 东边界经度 |
| `max_locations` | int | 30 | 候选地点最大数量（分页前） |
| `min_height_diff` | float | 100.0 | 最小高程差 |
| `road_radius_km` | float | 10.0 | 道路搜索半径 |
| `network_type` | str | `"drive"` | 道路网络类型 |
| `db_config_path` | str | None | 数据库配置路径 |

### 分页参数（不影响计算结果）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（1-based） |
| `page_size` | int | 10 | 每页结果数 |

## 响应结构

```json
{
  "data": {
    "items": [
      {
        "name": "...",
        "lat": 40.0,
        "lon": 116.0,
        "score": 85.5,
        "bortle_class": 3,
        "...": "..."
      }
    ],
    "total": 25,
    "page": 1,
    "page_size": 10,
    "total_pages": 3,
    "resource_id": "a1b2c3d4..."
  },
  "_meta": {
    "version": "1.0.0",
    "status": "success"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `items` | list | 当前页的地点列表 |
| `total` | int | 本次搜索找到的总地点数 |
| `page` | int | 当前页码（1-based） |
| `page_size` | int | 每页结果数 |
| `total_pages` | int | 总页数 = `ceil(total / page_size)` |
| `resource_id` | str | 非分页搜索参数的稳定标识符 |

## `resource_id` 语义

### 定义

`resource_id` 是**非分页搜索参数**的 MD5 哈希。生成时使用的参数为：

```
south, west, north, east, max_locations, min_height_diff,
road_radius_km, network_type, db_config_path
```

**分页参数 `page` 和 `page_size` 不参与 `resource_id` 的计算**。

### 用途

`resource_id` 的作用是让 agent 能够：

1. **跨多次分页请求定位同一结果集**：同一组搜索参数 + 不同 `page` → 相同的 `resource_id`
2. **关联上层工具的输出**：例如 `get_best_stargazing_plan` 的 `query.analysis_resource_id` 引用此值，agent 可以据此回查底层搜索结果

### 稳定性

- 同一组搜索参数在同一进程中产生相同的 `resource_id`
- 跨进程、跨启动时可能不同（缓存是进程内缓存，不持久化）
- 参数顺序不影响 `resource_id`（内部排序后序列化）

### 边界情况

- 搜索参数变化（如 `max_locations` 从 30 改为 50）→ 新的 `resource_id` + 新的缓存条目
- 仅分页参数变化（如 `page=2`）→ 相同 `resource_id`，不触发重新计算

## 分页语义

### 基本规则

- `page` 从 1 开始计数
- `page_size` 最小为 1
- `page < 1` 或 `page_size < 1` → 返回 `CONFIGURATION_ERROR`
- 请求页超出范围时返回空 `items`，不报错

### 分页与缓存的关系

```
请求 analysis_area(page=1, page_size=10, south=39, west=115, north=41, east=117, ...)
  → resource_id = md5(搜索参数)
  → 缓存未命中 → 执行完整搜索 → 缓存 30 个结果
  → 返回 items[0:10]

请求 analysis_area(page=2, page_size=10, south=39, west=115, north=41, east=117, ...)
  → resource_id = md5(搜索参数)  # 相同
  → 缓存命中 → 直接使用缓存的 30 个结果
  → 返回 items[10:20]
```

## 缓存语义

### 缓存策略

- 缓存 key = `resource_id`（即搜索参数的 MD5）
- 缓存 value = 完整的地点列表（未分页）
- TTL = 3600 秒（1 小时），基于创建时间
- 缓存作用域 = 进程内存（`src/cache.py:ANALYSIS_CACHE`）

### 缓存失效

- 超过 TTL 后自动失效，下次请求触发重新计算
- 搜索参数变化 → 新的 `resource_id` → 新的缓存条目
- 进程重启 → 缓存清空
- **不会**因为时间推移或外部数据变化而主动失效

### 设计约束

- 缓存不跨进程：多个 MCP server 实例各自维护独立缓存
- 无预热机制：首次请求触发完整计算
- 无主动驱逐：不因内存压力驱逐条目（仅依赖 TTL）

## 验证行为

| 场景 | 响应 |
|------|------|
| `page < 1` | `CONFIGURATION_ERROR`："page must be greater than or equal to 1." |
| `page_size < 1` | `CONFIGURATION_ERROR`："page_size must be greater than or equal to 1." |
| 正常请求，无结果 | `items: []`, `total: 0`, `total_pages: 0` |
| 正常请求，有结果 | 标准 success 响应，分页字段完整 |

验证错误使用 `format_error()` 返回结构化 `{error, _meta}` 格式，不抛异常。

## 与其他工具的关联

### `get_best_stargazing_plan`

复合规划工具内部调用 `analysis_area.fn()` 获取候选地点，并将 `resource_id` 写入响应中的 `query.analysis_resource_id`。这使得：

- Agent 可以从规划结果直接定位到底层搜索
- Agent 可以在规划后翻阅全部底层搜索结果，无需重复搜索参数

### `light_pollution_map`

`light_pollution_map` 与 `analysis_area` 共享同一个下层 bridge（`src/placefinder.py`），但 `light_pollution_map` 不使用 `resource_id` 或分页机制。两者的下层调用路径不同：

- `analysis_area` → `StargazingPlaceFinder.analyze_area()` → 综合分析
- `light_pollution_map` → `get_light_pollution_grid()` → 光污染网格查询

## 测试约束

| 测试文件 | 覆盖 |
|---------|------|
| `tests/test_serialization.py` | 验证 JSON 响应结构、分页字段完整性 |
| `tests/test_mcp_client.py` | 协议层 `tools/call` 验证 |
| `tests/test_integration.py` | 工具注册验证 |
| `tests/test_mcp_tools.py` | 工具级单元测试 |
| `tests/test_placefinder.py` | Bridge 层调用链测试 |
