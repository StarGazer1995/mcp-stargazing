"""
FastMCP 服务实例。

说明：
- 运行服务时依赖 `fastmcp`。
- 为了让纯单元测试在缺少 `fastmcp` 依赖时也能运行，这里提供一个极简的降级实现：
  仅满足 `@mcp.tool()` 装饰器与 `.fn` 调用方式（测试用）。
"""

try:
    from fastmcp import FastMCP  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _ToolWrapper:
        """测试用工具包装器：提供 `.fn` 与可调用行为。"""

        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args, **kwargs):
            return self.fn(*args, **kwargs)

    class FastMCP:  # type: ignore
        """测试用 FastMCP 替身（仅实现 tool 装饰器）。"""

        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(fn):
                return _ToolWrapper(fn)

            return decorator


# Initialize MCP instance
mcp = FastMCP("mcp-stargazing")
