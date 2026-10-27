# 1.0 前公共 schema 基线

`tests/public_schema_baseline.json` 保存了源提交
`505a50e8c522de327447405c501ff5f8b39e538e` 的公共 schema，用于在增加长任务工具前保留
既有调用方依赖的结构。这是兼容性审查基线，不表示已经完成 1.0 契约冻结。

## 覆盖范围

- 现有 17 个工具实际对外公布的 `inputSchema` 与 `outputSchema`。
- `AgentPlanningResult`、`BestStargazingPlan`、`MultiNightStargazingPlan` 和
  `AnalysisAreaResult` 的序列化模型，包括嵌套字段、枚举、默认值和约束。
- 统一成功/失败 envelope 示例与当前公共错误码集合。
- 采集时的 SDK 版本与源提交，作为审查上下文；版本号本身不参与 schema 比较。

部分工具当前对外公布的是通用字典 `outputSchema`。这里保存其真实声明，不虚构更严格的
字段保证；上述详细模型以外的业务输出仍由既有工具与序列化测试保护。完整输出类型化
仍是独立工作；后续 1.0 冻结基线保存真实声明，范围见下文与迁移说明。

## 如何检查

```bash
uv run pytest tests/test_public_schema_baseline.py tests/test_mcp_client.py
```

应用层测试重新读取 SDK 生成的 schema 并核对详细模型。协议层测试启动真实 MCP 服务，
将客户端收到的 `tools/list` 与保存的工具 schema 逐项比较。

规则如下：

1. 既有工具不能悄悄删除或改名；已保存的工具 schema、详细结果模型和默认 envelope
   必须相同。这个初始门禁是保守的，新增可选字段等兼容变更也会要求显式审查。
2. 新工具允许独立增加，但仍需自己的注册、成功/错误、参数和协议测试；这份历史基线
   不自动替新增工具提供测试保证。
3. 错误码可以新增，已有错误码不能移除；新增码仍须同步文档与错误路径测试。
4. 顶层工具描述不属于 schema 快照，后续可补使用边界而不重写历史基线。schema 内的
   字段描述属于当前严格比较的一部分，其变化也需要审查。
5. 不通过批量刷新快照来掩盖兼容性失败。变更应解释原因、影响、兼容或弃用策略，并在
   独立审查中决定如何建立下一份基线。进入 1.0 时再保存完整的新契约。

## 重新采集用于比较

另有独立的 1.0 冻结基线 `tests/public_contract_v1.json`，补齐全部工具、公开注解、任务、
天气/天体模型和任务 envelope；它不替换历史快照，两份门禁同时运行。范围与兼容规则见
[1.0 迁移说明](v1-migration.md)。采集器 `scripts.capture_v1_contract` 使用同样参数，独占
创建 `public_contract_v1.json`；注解按真实 wire 形式省略 null 字段，测试不更新快照。

```bash
uv run python -m scripts.capture_public_contract \
  --out-dir /absolute/path/to/task/work \
  --source-revision <verified-commit-sha>
```

输出目录应为既有任务工作区。采集器不执行任何业务工具，不请求天气、地点或设备数据；
它只读取注册信息和模型。输出使用独占创建，已有文件不会被覆盖。测试本身不写快照。
