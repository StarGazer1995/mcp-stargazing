"""
FastMCP 服务实例。

说明：
- 运行服务时依赖 `fastmcp`。
- 为了让纯单元测试在缺少 `fastmcp` 依赖时也能运行，这里提供一个极简的降级实现：
  仅满足 `@mcp.tool()` 装饰器与 `.fn` 调用方式（测试用）。
"""

import inspect
from typing import Any, Dict

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


class MCP:
    def __init__(self, name: str):
        self._mcp = FastMCP(name)
        self._tool_metadata: Dict[str, Dict[str, Any]] = {}
        self._tool_manager = getattr(self._mcp, '_tool_manager', None)

    def tool(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return self._decorate_tool(args[0])

        decorator = self._mcp.tool(*args, **kwargs)

        def wrapper(fn):
            wrapped = decorator(fn)
            self._register_tool_metadata(fn)
            return wrapped

        return wrapper

    def _decorate_tool(self, fn):
        wrapped = self._mcp.tool()(fn)
        self._register_tool_metadata(fn)
        return wrapped

    def _register_tool_metadata(self, fn):
        if fn.__name__ in self._tool_metadata:
            return

        signature = inspect.signature(fn)
        parameters = []
        for name, param in signature.parameters.items():
            annotation = param.annotation
            annotation_name = 'Any'
            if annotation is not inspect._empty:
                try:
                    annotation_name = annotation.__name__
                except AttributeError:
                    annotation_name = str(annotation)

            default = None
            required = param.default is inspect._empty
            if not required:
                default = param.default

            parameters.append({
                'name': name,
                'type': annotation_name,
                'required': required,
                'default': default,
            })

        doc = inspect.getdoc(fn) or ''
        description = doc.splitlines()[0] if doc else ''

        return_type = 'Any'
        if signature.return_annotation is not inspect._empty:
            try:
                return_type = signature.return_annotation.__name__
            except AttributeError:
                return_type = str(signature.return_annotation)

        self._tool_metadata[fn.__name__] = {
            'name': fn.__name__,
            'description': description,
            'docstring': doc,
            'parameters': parameters,
            'return_type': return_type,
        }

    def get_tool_catalog(self):
        return list(self._tool_metadata.values())

    def __getattr__(self, item):
        return getattr(self._mcp, item)


# Initialize MCP instance
mcp = MCP("mcp-stargazing")
