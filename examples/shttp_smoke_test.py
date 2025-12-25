import http.client
import json
from typing import Dict, Any, Tuple

def initialize_session(host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp") -> str:
    """Initialize MCP streamable HTTP session and return session ID."""
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "examples-smoke", "version": "1.0"},
            "capabilities": {},
            "protocolVersion": "2024-11-"
        }
    })
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    print(f"[initialize] POST {path}")
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    session_id = resp.getheader("mcp-session-id") or ""

    # Drain SSE init response to confirm handshake
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if decoded.startswith("data: "):
            print("[initialize] data received")
            break
    conn.close()
    if not session_id:
        raise RuntimeError("Missing mcp-session-id")
    print("[initialize] session_id:", session_id)
    return session_id

def call_tool(name: str, arguments: Dict[str, Any], host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp", session_id: str = "") -> Tuple[str, Dict[str, Any]]:
    """Call an MCP tool via streamable HTTP and return raw SSE payload and parsed JSON."""
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
    print(f"[tools/call] POST {path} name={name}")
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    sse_text = ""
    result_obj: Dict[str, Any] = {}
    # Read until we get a JSON payload line
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        sse_text += decoded + "\n"
        if decoded.startswith("data: "):
            payload = decoded[6:]
            try:
                parsed = json.loads(payload)
                if "result" in parsed or "error" in parsed:
                    result_obj = parsed
                    break
            except Exception:
                pass
    conn.close()
    return sse_text, result_obj

def main():
    """Run a minimal SHTTP smoke test against the running container."""
    host = "127.0.0.1"
    port = 3001
    path = "/shttp"
    session_id = initialize_session(host=host, port=port, path=path)
    # Call a simple tool that has no external dependencies
    sse, obj = call_tool(
        name="get_local_datetime_info",
        arguments={},
        host=host,
        port=port,
        path=path,
        session_id=session_id,
    )
    print("[call] SSE (trunc):", sse[:200].replace("\n", " "))
    print("[call] parsed keys:", list(obj.keys()))
    print("[call] result keys:", list(obj.get("result", {}).keys()))

if __name__ == "__main__":
    main()
