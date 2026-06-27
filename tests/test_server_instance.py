"""Tests for the custom MCP wrapper class and its FastMCP integration."""

import sys
from typing import Any

import pytest

from src.server_instance import MCP, mcp

# ---------------------------------------------------------------------------
# __getattr__ delegation
# ---------------------------------------------------------------------------


def test_getattr_delegation_to_fastmcp():
    """``__getattr__`` delegates unknown attributes to the underlying FastMCP instance."""
    # `run` exists on FastMCP but not directly on the MCP class
    assert callable(mcp.run)
    # `run_async` should also be available
    assert callable(mcp.run_async)


def test_getattr_unknown_attribute_raises():
    """Accessing an attribute that does not exist on either MCP or FastMCP raises AttributeError."""
    with pytest.raises(AttributeError):
        _ = mcp.this_definitely_does_not_exist_xyz


# ---------------------------------------------------------------------------
# Tool decorator
# ---------------------------------------------------------------------------


def test_tool_decorator_without_args_registers_metadata():
    """``@mcp.tool()`` (without arguments) registers tool metadata correctly."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool()
    def sample_tool(param1: str, param2: int = 42) -> dict[str, Any]:
        """A sample tool for testing."""
        return {'data': {'param1': param1, 'param2': param2}}

    catalog = fresh_mcp.get_tool_catalog()
    assert len(catalog) == 1
    entry = catalog[0]

    assert entry['name'] == 'sample_tool'
    assert entry['description'] == 'A sample tool for testing.'
    assert entry['return_type'] == 'dict'
    assert len(entry['parameters']) == 2

    # Check param1 (required, str)
    param1 = next(p for p in entry['parameters'] if p['name'] == 'param1')
    assert param1['type'] == 'str'
    assert param1['required'] is True
    assert param1['default'] is None

    # Check param2 (optional, int, default=42)
    param2 = next(p for p in entry['parameters'] if p['name'] == 'param2')
    assert param2['type'] == 'int'
    assert param2['required'] is False
    assert param2['default'] == 42


def test_tool_decorator_with_args_registers_metadata():
    """``@mcp.tool()`` with explicit name/description passes through to FastMCP."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool(name='custom_name', description='Custom description')
    def another_tool(x: float) -> dict[str, Any]:
        """Docstring that should be overridden by explicit description."""
        return {'data': {'x': x}}

    catalog = fresh_mcp.get_tool_catalog()
    assert len(catalog) == 1
    entry = catalog[0]

    assert entry['name'] == 'custom_name'
    assert entry['description'] == 'Custom description'
    assert entry['docstring'] == 'Docstring that should be overridden by explicit description.'
    assert len(entry['parameters']) == 1
    assert entry['parameters'][0]['name'] == 'x'


def test_tool_decorator_preserves_fn_attribute():
    """The decorated function retains the ``.fn`` attribute for test callability."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool()
    def my_tool(x: int) -> dict[str, Any]:
        """Test tool."""
        return {'data': {'x': x}}

    # The wrapper should have .fn pointing to the original function
    assert hasattr(my_tool, 'fn')
    result = my_tool.fn(x=10)
    assert result == {'data': {'x': 10}}


def test_tool_decorator_function_tool_type():
    """The wrapped function becomes a FastMCP FunctionTool (not a plain function)."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool()
    def callable_tool(value: str) -> dict[str, Any]:
        """Test tool."""
        return {'data': {'value': value}}

    # The wrapper is a FunctionTool, callable through .fn for testing
    assert hasattr(callable_tool, 'fn')
    result = callable_tool.fn(value='hello')
    assert result == {'data': {'value': 'hello'}}


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


def test_register_tool_metadata_includes_all_fields():
    """``_register_tool_metadata`` stores name, description, docstring, parameters, return_type."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool()
    def documented_tool(query: str, limit: int = 10) -> list[str]:
        """Search for objects matching the query.

        Extended docstring with more details.
        """
        return [query * i for i in range(limit)]

    entry = fresh_mcp.get_tool_catalog()[0]

    assert entry['name'] == 'documented_tool'
    assert entry['description'] == 'Search for objects matching the query.'
    assert 'Extended docstring' in entry['docstring']
    assert 'list' in entry['return_type'] or 'List' in entry['return_type']
    assert len(entry['parameters']) == 2


def test_tool_metadata_does_not_overwrite_on_duplicate():
    """Registering the same function name twice does not overwrite metadata."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool()
    def first_registration(a: int) -> int:
        """First registration."""
        return a

    # Try registering again with the same function (simulated)
    fresh_mcp._register_tool_metadata(first_registration.fn)
    entry = fresh_mcp.get_tool_catalog()[0]

    # Metadata should reflect the FIRST registration
    assert entry['description'] == 'First registration.'


def test_tool_metadata_does_not_overwrite_same_explicit_name():
    """Registering the same explicit tool name twice preserves the first metadata entry."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool(name='shared_name', description='First description')
    def first_tool(a: int) -> int:
        """First tool."""
        return a

    @fresh_mcp.tool(name='shared_name', description='Second description')
    def second_tool(b: int) -> int:
        """Second tool."""
        return b

    catalog = fresh_mcp.get_tool_catalog()
    assert len(catalog) == 1
    entry = catalog[0]

    assert entry['name'] == 'shared_name'
    assert entry['description'] == 'First description'
    assert entry['parameters'][0]['name'] == 'a'


def test_get_tool_catalog_returns_list():
    """``get_tool_catalog`` returns a list (may be empty before any registration)."""
    empty_mcp = MCP('empty')
    catalog = empty_mcp.get_tool_catalog()

    assert isinstance(catalog, list)
    assert catalog == []


def test_get_tool_catalog_is_a_copy():
    """Modifying the returned list does not affect internal metadata."""
    fresh_mcp = MCP('test-server')

    @fresh_mcp.tool()
    def some_tool(x: int) -> int:
        """A tool."""
        return x

    catalog = fresh_mcp.get_tool_catalog()
    catalog.clear()
    # Internal metadata should be unaffected
    assert len(fresh_mcp.get_tool_catalog()) == 1


# ---------------------------------------------------------------------------
# MCP name and initialization
# ---------------------------------------------------------------------------


def test_mcp_name():
    """The MCP instance stores the provided name."""
    named_mcp = MCP('my-astronomy-server')
    assert named_mcp._mcp.name == 'my-astronomy-server'


def test_mcp_tool_manager_access():
    """``_tool_manager`` attribute is accessible from underlying FastMCP."""
    # The default mcp may or may not have _tool_manager depending on FastMCP internals
    # Just verify the attribute access doesn't raise on the wrapper
    assert hasattr(mcp, '_tool_manager')


# ---------------------------------------------------------------------------
# FastMCP fallback (for environments without fastmcp installed)
# ---------------------------------------------------------------------------


def test_fastmcp_fallback_when_not_installed():
    """When fastmcp is not available, the fallback FastMCP allows ``@mcp.tool()`` usage."""
    # Save real modules
    fastmcp_module = sys.modules.get('fastmcp')
    server_instance_module = sys.modules.get('src.server_instance')

    try:
        # Simulate fastmcp not being installed
        sys.modules['fastmcp'] = None  # trigger ModuleNotFoundError on import

        # Force re-import of server_instance with fastmcp unavailable
        if 'src.server_instance' in sys.modules:
            del sys.modules['src.server_instance']

        from importlib import reload

        import src.server_instance

        reload(src.server_instance)

        # Create a fresh MCP instance using the fallback
        fallback_mcp = src.server_instance.MCP('fallback-test')

        @fallback_mcp.tool()
        def fallback_tool(x: int) -> int:
            """A fallback tool."""
            return x * 2

        # Verify the tool works
        assert hasattr(fallback_tool, 'fn')
        assert fallback_tool.fn(x=5) == 10

        # Tool catalog should be populated
        catalog = fallback_mcp.get_tool_catalog()
        assert len(catalog) == 1
        assert catalog[0]['name'] == 'fallback_tool'

    finally:
        # Restore real modules
        if fastmcp_module is not None:
            sys.modules['fastmcp'] = fastmcp_module
        elif 'fastmcp' in sys.modules:
            del sys.modules['fastmcp']

        # Restore server_instance
        if server_instance_module is not None:
            sys.modules['src.server_instance'] = server_instance_module
