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
    tools = _list_tool_entries(host, port, path, session_id)
    return {tool['name'] for tool in tools if 'name' in tool}


def _list_tool_entries(host: str, port: int, path: str, session_id: str) -> list[dict]:
    """Call MCP ``tools/list`` and return the advertised tool objects."""
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
    return payload['result'].get('tools', [])


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


def _open_sse_stream(
    host: str, port: int, path: str
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse, str]:
    """Open the SSE endpoint and return the live connection plus the message endpoint path."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request('GET', path, headers={'Accept': 'text/event-stream'})
    response = conn.getresponse()
    response.fp.raw._sock.settimeout(5.0)

    assert response.status == 200, response.status
    assert 'text/event-stream' in response.getheader('Content-Type', '')

    event_name, data = _read_sse_event(response)
    assert event_name == 'endpoint', (event_name, data)
    return conn, response, data


def _read_sse_event(
    response: http.client.HTTPResponse, timeout_seconds: float = 5.0
) -> tuple[str | None, str]:
    """Read the next complete SSE event from an open stream response."""
    deadline = time.time() + timeout_seconds
    event_name = None
    data_lines: list[str] = []

    while time.time() < deadline:
        raw_line = response.fp.readline()
        if not raw_line:
            continue

        line = raw_line.decode('utf-8', errors='replace').rstrip('\r\n')
        if not line:
            if data_lines:
                return event_name, '\n'.join(data_lines)
            event_name = None
            data_lines = []
            continue

        if line.startswith('event:'):
            event_name = line[6:].strip()
        elif line.startswith('data:'):
            data_lines.append(line[5:].strip())

    raise AssertionError('Timed out while reading SSE event from server.')


def _read_sse_jsonrpc_payload(
    response: http.client.HTTPResponse,
    expected_id: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict:
    """Read JSON-RPC payloads from an open SSE stream and optionally match on request id."""
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        _, data = _read_sse_event(response, timeout_seconds=max(0.1, deadline - time.time()))
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue

        if 'result' not in payload and 'error' not in payload:
            continue
        if expected_id is not None and payload.get('id') != expected_id:
            continue
        return payload

    raise AssertionError(f'No JSON-RPC payload found in SSE stream for id={expected_id}.')


def _post_sse_jsonrpc(host: str, port: int, message_path: str, payload: dict) -> int:
    """Post a JSON-RPC message to the SSE message endpoint and return the HTTP status."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request(
        'POST',
        message_path,
        body=json.dumps(payload),
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        },
    )
    response = conn.getresponse()
    status = response.status
    response.read()
    conn.close()
    return status


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


@pytest.fixture
def running_mcp_sse_server() -> Generator[
    tuple[str, int, str, http.client.HTTPResponse, http.client.HTTPConnection]
]:
    """Start the real MCP SSE server process and yield connection info for protocol tests."""
    host = '127.0.0.1'
    port = _get_free_port()
    path = '/sse'
    process = subprocess.Popen(
        [sys.executable, '-m', 'src.main', '--mode', 'sse', '--port', str(port), '--path', path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    stream_conn = None
    stream_response = None
    try:
        deadline = time.time() + 20.0
        last_error: Exception | None = None
        message_path = ''

        while time.time() < deadline:
            try:
                stream_conn, stream_response, message_path = _open_sse_stream(host, port, path)
                break
            except Exception as exc:  # pragma: no cover - timing dependent branch
                last_error = exc
                time.sleep(0.2)
        else:
            raise AssertionError(f'MCP SSE server failed to start within timeout: {last_error}')

        yield host, port, message_path, stream_response, stream_conn
    finally:
        if stream_conn is not None:
            stream_conn.close()
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
