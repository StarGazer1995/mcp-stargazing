import http.client
import json
from datetime import datetime
from typing import Dict, Any, Tuple

def initialize_session(host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp") -> str:
    """Initialize MCP streamable HTTP session and return session ID."""
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "examples-tools-demo", "version": "1.0"},
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
    print(f"[tools/call] POST {path} name={name} args={arguments}")
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
    """Call multiple MCP tools via SHTTP and print summarized results."""
    host = "127.0.0.1"
    port = 3001
    path = "/shttp"
    session_id = initialize_session(host=host, port=port, path=path)

    # 1) get_local_datetime_info
    sse, obj = call_tool("get_local_datetime_info", {}, host, port, path, session_id)
    print("[get_local_datetime_info] parsed keys:", list(obj.keys()))
    print("[get_local_datetime_info] result keys:", list(obj.get("result", {}).keys()))

    # Prepare common arguments
    lon = -74.0060
    lat = 40.7128
    time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    time_zone = "UTC"

    # 2) get_visible_planets
    sse2, obj2 = call_tool("get_visible_planets", {
        "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone
    }, host, port, path, session_id)
    print("[get_visible_planets] result keys:", list(obj2.get("result", {}).keys()))
    content2 = obj2.get("result", {}).get("content", [])
    if content2 and content2[0].get("type") == "text":
        try:
            planets = json.loads(content2[0].get("text", "[]"))
            print("[get_visible_planets] count:", len(planets))
            if planets:
                print("[get_visible_planets] first:", planets[0])
        except Exception:
            print("[get_visible_planets] parse failed")

    # 3) get_celestial_pos (sun)
    sse3, obj3 = call_tool("get_celestial_pos", {
        "celestial_object": "sun", "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone
    }, host, port, path, session_id)
    print("[get_celestial_pos] result keys:", list(obj3.get("result", {}).keys()))
    content3 = obj3.get("result", {}).get("content", [])
    if content3 and content3[0].get("type") == "text":
        print("[get_celestial_pos] payload:", content3[0].get("text", ""))

    # 4) get_celestial_rise_set (sun)
    sse4, obj4 = call_tool("get_celestial_rise_set", {
        "celestial_object": "sun", "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone
    }, host, port, path, session_id)
    print("[get_celestial_rise_set] result keys:", list(obj4.get("result", {}).keys()))
    content4 = obj4.get("result", {}).get("content", [])
    if content4 and content4[0].get("type") == "text":
        print("[get_celestial_rise_set] payload:", content4[0].get("text", ""))

    # 5) get_constellation (Orion) - uses local centers, no SIMBAD
    sse5, obj5 = call_tool("get_constellation", {
        "constellation_name": "Orion", "lon": lon, "lat": lat, "time": time_str, "time_zone": time_zone
    }, host, port, path, session_id)
    print("[get_constellation] result keys:", list(obj5.get("result", {}).keys()))
    content5 = obj5.get("result", {}).get("content", [])
    if content5 and content5[0].get("type") == "text":
        print("[get_constellation] payload:", content5[0].get("text", ""))

if __name__ == "__main__":
    main()
