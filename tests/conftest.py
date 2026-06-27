import http.client
import json
import socket
import subprocess
import sys
import time
from collections.abc import Generator

import pytest
from astropy.utils.iers import conf

from src.paths import PROJECT_ROOT

# Prevent pytest run-time from failing because of stale IERS predictive data.
conf.auto_download = False
conf.auto_max_age = None

# ---------------------------------------------------------------------------
# Shared MCP HTTP client helpers (used by test_main_registration + test_mcp_client)
# ---------------------------------------------------------------------------


def _get_free_port() -> int:
    """Return an available local TCP port for the temporary MCP server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _read_jsonrpc_response(
    response: http.client.HTTPResponse, expected_id: str | None = None
) -> dict:
    """Read a JSON-RPC response and optionally require a matching request id."""
    content_type = response.getheader('Content-Type', '')
    body = response.read().decode('utf-8', errors='replace')

    if 'text/event-stream' not in content_type:
        payload = json.loads(body)
        if expected_id is not None:
            assert payload.get('id') == expected_id, payload
        return payload

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith('data: '):
            continue
        payload = json.loads(line[6:])
        if 'result' in payload or 'error' in payload:
            if expected_id is not None and payload.get('id') != expected_id:
                continue
            return payload

    raise AssertionError(f'No JSON-RPC payload found in SSE body for id={expected_id}: {body}')


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
    payload = _read_jsonrpc_response(response, expected_id='init')
    session_id = response.getheader('mcp-session-id') or ''
    conn.close()

    assert 'result' in payload, payload
    assert session_id, 'Missing mcp-session-id in initialize response'
    return session_id


def _list_tools(host: str, port: int, path: str, session_id: str) -> set[str]:
    """Call MCP ``tools/list`` and return the advertised tool names."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps({'jsonrpc': '2.0', 'id': 'tools-list', 'method': 'tools/list'})
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'mcp-session-id': session_id,
    }
    conn.request('POST', path, body=body, headers=headers)
    response = conn.getresponse()
    payload = _read_jsonrpc_response(response, expected_id='tools-list')
    conn.close()

    assert 'result' in payload, payload
    tools = payload['result'].get('tools', [])
    return {tool['name'] for tool in tools if 'name' in tool}


def _call_tool(
    host: str, port: int, path: str, session_id: str, tool_name: str, arguments: dict
) -> dict:
    """Call an MCP tool via ``tools/call`` and return the JSON-RPC response dict."""
    request_id = f'call-{tool_name}'
    conn = http.client.HTTPConnection(host, port, timeout=10)
    body = json.dumps(
        {
            'jsonrpc': '2.0',
            'id': request_id,
            'method': 'tools/call',
            'params': {'name': tool_name, 'arguments': arguments},
        }
    )
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'mcp-session-id': session_id,
    }
    conn.request('POST', path, body=body, headers=headers)
    response = conn.getresponse()
    payload = _read_jsonrpc_response(response, expected_id=request_id)
    conn.close()
    return payload


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
        [sys.executable, '-m', 'src.main', '--mode', 'shttp', '--port', str(port), '--path', path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(PROJECT_ROOT),
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


# ---------------------------------------------------------------------------
# Other shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_simbad_network(monkeypatch):
    """Prevent slow astroquery SIMBAD network calls during tests."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    def fake_resolve(name: str) -> SkyCoord:
        # Provide fixed coordinates for commonly used objects in tests.
        lower_name = name.lower()
        if lower_name == 'andromeda':
            return SkyCoord(ra=10.68458 * u.deg, dec=41.26917 * u.deg, frame='icrs')
        if lower_name == 'polaris':
            return SkyCoord(ra=37.95456067 * u.deg, dec=89.26410897 * u.deg, frame='icrs')
        if lower_name == 'sirius':
            return SkyCoord(ra=101.28715533 * u.deg, dec=-16.71611586 * u.deg, frame='icrs')
        if lower_name == 'betelgeuse':
            return SkyCoord(ra=88.792939 * u.deg, dec=7.407064 * u.deg, frame='icrs')
        if lower_name in {'antare', 'antares'}:
            return SkyCoord(ra=247.351915 * u.deg, dec=-26.432002 * u.deg, frame='icrs')
        raise ValueError(f"Test-only fake resolver has no data for '{name}'")

    monkeypatch.setattr('src.celestial._resolve_simbad_object', fake_resolve)
