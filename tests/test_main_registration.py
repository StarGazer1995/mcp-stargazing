import http.client
import json
import socket
import subprocess
import time
from collections.abc import Generator

import pytest

EXPECTED_TOOLS = {
    'analysis_area',
    'get_celestial_pos',
    'get_celestial_rise_set',
    'get_constellation',
    'get_local_datetime_info',
    'get_moon_info',
    'get_nightly_forecast',
    'get_tool_catalog',
    'get_weather_by_name',
    'get_weather_by_position',
    'light_pollution_map',
    'list_visible_planets',
}


def _get_free_port() -> int:
    """Return an available local TCP port for the temporary MCP server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _read_jsonrpc_response(response: http.client.HTTPResponse) -> dict:
    """Read a JSON-RPC response from either JSON or SSE streamable HTTP payloads."""
    content_type = response.getheader('Content-Type', '')
    body = response.read().decode('utf-8', errors='replace')

    if 'text/event-stream' not in content_type:
        return json.loads(body)

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith('data: '):
            continue
        payload = json.loads(line[6:])
        if 'result' in payload or 'error' in payload:
            return payload

    raise AssertionError(f'No JSON-RPC payload found in SSE body: {body}')


def _initialize_session(host: str, port: int, path: str) -> str:
    """Open a streamable HTTP MCP session and return the issued session id."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps(
        {
            'jsonrpc': '2.0',
            'id': 'init',
            'method': 'initialize',
            'params': {
                'clientInfo': {'name': 'pytest-startup-test', 'version': '1.0'},
                'capabilities': {},
                'protocolVersion': '2024-11-05',
            },
        }
    )
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    }
    conn.request('POST', path, body=body, headers=headers)
    response = conn.getresponse()
    payload = _read_jsonrpc_response(response)
    session_id = response.getheader('mcp-session-id') or ''
    conn.close()

    assert 'result' in payload, payload
    assert session_id, 'Missing mcp-session-id in initialize response'
    return session_id


def _list_tools(host: str, port: int, path: str, session_id: str) -> set[str]:
    """Call MCP `tools/list` and return the advertised tool names."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps({'jsonrpc': '2.0', 'id': 'tools-list', 'method': 'tools/list'})
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'mcp-session-id': session_id,
    }
    conn.request('POST', path, body=body, headers=headers)
    response = conn.getresponse()
    payload = _read_jsonrpc_response(response)
    conn.close()

    assert 'result' in payload, payload
    tools = payload['result'].get('tools', [])
    return {tool['name'] for tool in tools if 'name' in tool}


def _wait_for_server(host: str, port: int, path: str, timeout_seconds: float) -> str:
    """Poll the spawned MCP server until initialization succeeds or timeout is reached."""
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            return _initialize_session(host, port, path)
        except Exception as exc:  # pragma: no cover - timing dependent branch
            last_error = exc
            time.sleep(0.2)

    raise AssertionError(f'MCP server failed to start within timeout: {last_error}')


@pytest.fixture
def running_mcp_server() -> Generator[tuple[str, int, str, str]]:
    """Start the real MCP SHTTP server process and yield connection info for tests."""
    host = '127.0.0.1'
    port = _get_free_port()
    path = '/shttp'
    process = subprocess.Popen(
        ['python', '-m', 'src.main', '--mode', 'shttp', '--port', str(port), '--path', path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        session_id = _wait_for_server(host, port, path, timeout_seconds=20.0)
        yield host, port, path, session_id
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup fallback
            process.kill()
            process.wait(timeout=5)


def test_mcp_startup_lists_expected_tools(running_mcp_server: tuple[str, int, str, str]):
    """Verify the started MCP server advertises the expected tool names via `tools/list`."""
    host, port, path, session_id = running_mcp_server
    listed_tools = _list_tools(host, port, path, session_id)
    print(listed_tools)
    missing_tools = EXPECTED_TOOLS - listed_tools

    assert not missing_tools, (
        f'Started MCP server missed tools in tools/list: {sorted(missing_tools)}; '
        f'listed tools: {sorted(listed_tools)}'
    )
