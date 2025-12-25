import http.client
import json
import time
from datetime import datetime

def initialize_session(host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp") -> str:
    """Initialize MCP streamable HTTP session and return session ID."""
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "perf-benchmark", "version": "1.0"},
            "capabilities": {},
            "protocolVersion": "2024-11-"
        }
    })
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    start = time.time()
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    session_id = resp.getheader("mcp-session-id") or ""
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if decoded.startswith("data: "):
            break
    conn.close()
    print("initialize_ms:", int((time.time() - start) * 1000))
    if not session_id:
        raise RuntimeError("Missing mcp-session-id")
    return session_id

def call_tool(name: str, arguments: dict, host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp", session_id: str = "") -> int:
    """Call an MCP tool and return elapsed milliseconds."""
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "call",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        }
    })
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "mcp-session-id": session_id,
    }
    start = time.time()
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if decoded.startswith("data: "):
            break
    conn.close()
    elapsed_ms = int((time.time() - start) * 1000)
    print(f"{name}_ms:", elapsed_ms)
    return elapsed_ms

def main():
    """Run a performance benchmark for SHTTP tools and print durations."""
    host = "127.0.0.1"
    port = 3001
    path = "/shttp"
    session_id = initialize_session(host=host, port=port, path=path)
    lon = -74.0060
    lat = 40.7128
    time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    time_zone = "UTC"

    call_tool("get_local_datetime_info", {}, host, port, path, session_id)
    call_tool("get_visible_planets", {"lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone}, host, port, path, session_id)
    call_tool("get_celestial_pos", {"celestial_object": "sun", "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone}, host, port, path, session_id)
    call_tool("get_celestial_rise_set", {"celestial_object": "sun", "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone}, host, port, path, session_id)
    call_tool("get_constellation", {"constellation_name": "Orion", "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone}, host, port, path, session_id)

if __name__ == "__main__":
    main()
