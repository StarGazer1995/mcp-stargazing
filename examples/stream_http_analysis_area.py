import http.client
import json
from typing import Dict, Any, Tuple


def initialize_session(host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp") -> str:
    """Initialize MCP streamable HTTP session and return session ID.

    Args:
        host: HTTP server host
        port: HTTP server port
        path: Stream HTTP endpoint path

    Returns:
        Session ID string extracted from response headers
    """
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "examples-cli", "version": "1.0"},
            "capabilities": {},
            "protocolVersion": "2024-11-"
        }
    })
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    print(f"POST {path} initialize ...")
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    session_id = resp.getheader("mcp-session-id") or ""
    content = resp.read().decode("utf-8", errors="replace")
    print("initialize response headers: mcp-session-id=", session_id)
    print("initialize response body (truncated):", content[:200].replace("\n", " "))
    conn.close()
    if not session_id:
        raise RuntimeError("Missing mcp-session-id in initialize response headers")
    return session_id


def call_tool(
    name: str,
    arguments: Dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 3001,
    path: str = "/shttp",
    session_id: str = ""
) -> Tuple[str, Dict[str, Any]]:
    """Call an MCP tool via streamable HTTP and return raw SSE payload and parsed JSON.

    Args:
        name: Tool name to call (e.g., "analysis_area")
        arguments: Tool arguments dict
        host: HTTP server host
        port: HTTP server port
        path: Stream HTTP endpoint path
        session_id: Session ID from initialize

    Returns:
        Tuple of (raw_sse_text, parsed_json_object)
    """
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
    print(f"POST {path} tools/call name={name} ...")
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    sse_text = resp.read().decode("utf-8", errors="replace")
    conn.close()
    print("call response SSE (truncated):", sse_text[:200].replace("\n", " "))

    json_obj: Dict[str, Any] = {}
    # Extract JSON after 'data: '
    for line in sse_text.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: "):]
            try:
                json_obj = json.loads(payload)
            except Exception:
                pass
            break
    return sse_text, json_obj


def main():
    """Run a full stream HTTP example to call analysis_area and print results."""
    host = "127.0.0.1"
    port = 3001
    path = "/shttp"
    session_id = initialize_session(host=host, port=port, path=path)
    args = {
        "south": 39.98,
        "west": 116.18,
        "north": 40.02,
        "east": 116.22,
        "max_locations": 3,
        "min_height_diff": 50.0,
        "road_radius_km": 5.0,
        "network_type": "drive",
    }
    sse, obj = call_tool(
        name="analysis_area",
        arguments=args,
        host=host,
        port=port,
        path=path,
        session_id=session_id,
    )
    print("Parsed JSON keys:", list(obj.keys()))
    result = obj.get("result", {})
    content = result.get("content", [])
    if content and content[0].get("type") == "text":
        text = content[0].get("text", "")
        try:
            items = json.loads(text)
            print("Items count:", len(items))
            if items:
                print("First item name:", items[0].get("name"))
                print("First item light_pollution_brightness:", items[0].get("light_pollution_brightness"))
        except Exception:
            print("Failed to parse content text as JSON")


if __name__ == "__main__":
    main()