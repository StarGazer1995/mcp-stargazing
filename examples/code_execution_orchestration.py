import http.client
import json
from typing import Dict, Any, Tuple, List


def initialize_session(host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp") -> str:
    """
    Initialize MCP streamable HTTP session and return session ID.
    """
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "examples-code-exec", "version": "1.0"},
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
    
    # Read SSE initial response line by line
    content = ""
    while True:
        # We expect a JSONRPC response for 'initialize'
        # FastMCP SHTTP might return it as SSE data
        line = resp.readline()
        if not line:
            break
        
        line_decoded = line.decode("utf-8", errors="replace")
        content += line_decoded
        
        line_stripped = line_decoded.strip()
        if line_stripped.startswith("data: "):
            # Once we get data, we assume initialization is acknowledged 
            # (usually contains server capabilities)
            break
            
    conn.close()
    
    print("[initialize] mcp-session-id=", session_id)
    # print("[initialize] body(trunc)=", content[:200].replace("\n", " "))
    
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
    """
    Call an MCP tool via streamable HTTP and return raw SSE payload and parsed JSON.
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
    print(f"[tools/call] {name} args={arguments}")
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    
    # SSE response reading loop
    sse_text = ""
    json_obj: Dict[str, Any] = {}
    
    # Read line by line to avoid blocking on open stream
    while True:
        line = resp.readline()
        if not line:
            break
        
        line_decoded = line.decode("utf-8", errors="replace")
        sse_text += line_decoded
        
        line_stripped = line_decoded.strip()
        # print(f"DEBUG: {line_stripped}") # Debug logging
        
        if line_stripped.startswith("data: "):
            payload = line_stripped[len("data: "):]
            try:
                # In MCP SHTTP, we usually get one result per call request 
                # (though logging might produce other events). 
                # If we parse a valid JSON result, we can assume success for this simple demo.
                # However, FastMCP might keep the stream open.
                # We need to decide when to stop reading.
                # For this demo, let's stop after getting the first data message
                # which usually contains the result.
                parsed = json.loads(payload)
                # Check if it's a tool result or just a log
                # MCP tool result structure: {"jsonrpc": "2.0", "result": {...}, "id": ...}
                if "result" in parsed or "error" in parsed:
                     json_obj = parsed
                     break
            except Exception:
                pass
                
    conn.close()
    return sse_text, json_obj


def extract_text_result(obj: Dict[str, Any]) -> str:
    """
    Extract text content from MCP SSE JSON envelope.
    """
    result = obj.get("result", {})
    content = result.get("content", [])
    if content and content[0].get("type") == "text":
        return content[0].get("text", "")
    return ""


def orchestrate_workflow():
    """
    Run a programmatic workflow:
    - Compute celestial positions for multiple objects
    - Fetch local weather by position
    - Analyze stargazing area around the position
    """
    host = "127.0.0.1"
    port = 3001
    path = "/shttp"
    session_id = initialize_session(host=host, port=port, path=path)

    # 1. 获取本地时间
    print(f"\n[Orchestrator] Calling get_local_datetime_info...")
    _, dt_resp = call_tool("get_local_datetime_info", {}, host=host, port=port, path=path, session_id=session_id)
    dt_content = dt_resp.get("result", {}).get("content", [])
    current_time_str = "2025-01-01 21:00:00" # Default fallback
    if dt_content and dt_content[0].get("type") == "text":
        try:
            raw_text = dt_content[0]["text"]
            # print(f"DEBUG: dt_text={raw_text}")
            dt_resp_data = json.loads(raw_text)
            current_time_str = dt_resp_data.get("data", {}).get("current_time")
            print(f"  -> Local time: {current_time_str}")
            # Simple truncation for ISO format to "YYYY-MM-DD HH:MM:SS" if needed, 
            # but celestial tools accept ISO strings usually via astropy/dateutil
        except Exception as e:
            print(f"  -> Error parsing datetime: {e}")

    lon, lat = 116.20, 40.00
    # time_str, tz = "2025-01-01 21:00:00", "Asia/Shanghai" 
    # Use dynamic time
    time_str = current_time_str
    tz = "Asia/Shanghai" # Assuming known or extracted from time string if it contains offset

    # 2. 调用天体位置工具 (并行或批量模拟)
    #    假设我们要看三个天体
    celestial_objects = ["Moon", "Jupiter", "Sirius"]
    results = {}
    
    for obj_name in celestial_objects:
        # 在实际代码执行环境中，这里可以使用 asyncio.gather 做并行
        # 这里为了演示简单，使用顺序调用
        print(f"\n[Orchestrator] Calling get_celestial_pos for {obj_name}...")
        sse, resp = call_tool(
            "get_celestial_pos",
            {
                "celestial_object": obj_name,
                "lon": 116.20,
                "lat": 40.00,
                "time": time_str, # 使用刚才获取的时间
                "time_zone": "Asia/Shanghai"
            },
            host=host, port=port, path=path, session_id=session_id
        )
        # 结果处理：直接在代码里提取需要的数值
        res_content = resp.get("result", {}).get("content", [])
        if res_content and res_content[0].get("type") == "text":
            try:
                raw_text = res_content[0]["text"]
                # print(f"DEBUG: {obj_name} raw_text={raw_text}")
                data_obj = json.loads(raw_text)
                # The tool now returns {"data": {...}, "_meta": ...}
                inner_data = data_obj.get("data", {})
                
                alt = inner_data.get("altitude")
                az = inner_data.get("azimuth")
                results[obj_name] = {"alt": alt, "az": az}
                print(f"  -> {obj_name}: Alt={alt}, Az={az}")
            except Exception as e:
                print(f"  -> Error parsing result for {obj_name}: {e}")
                print(f"  -> Raw content: {res_content[0]['text'][:200]}")

    _, weather_obj = call_tool(
        name="get_weather_by_position",
        arguments={"lat": lat, "lon": lon},
        host=host, port=port, path=path, session_id=session_id,
    )
    weather_text = extract_text_result(weather_obj)
    print("[weather] by position ->", weather_text[:200])

    bounds = {"south": lat - 0.02, "west": lon - 0.02, "north": lat + 0.02, "east": lon + 0.02}
    print("\n[Orchestrator] Calling analysis_area (Page 1)...")
    _, area_obj = call_tool(
        name="analysis_area",
        arguments={**bounds, "max_locations": 5, "min_height_diff": 50.0, "road_radius_km": 5.0, "network_type": "drive", "page": 1, "page_size": 2},
        host=host, port=port, path=path, session_id=session_id,
    )
    
    area_content = area_obj.get("result", {}).get("content", [])
    if area_content and area_content[0].get("type") == "text":
        try:
            area_resp = json.loads(area_content[0]["text"])
            area_data = area_resp.get("data", {})
            total = area_data.get("total", 0)
            resource_id = area_data.get("resource_id", "N/A")
            items = area_data.get("items", [])
            print(f"  -> Found {total} locations. Resource ID: {resource_id}")
            print(f"  -> Page 1 has {len(items)} items.")
            
            # Demo Pagination: If there are more items, fetch page 2
            if total > 2:
                print("\n[Orchestrator] Fetching analysis_area (Page 2) using cache...")
                # Note: We pass the same calculation params to hit the cache
                _, area_p2_obj = call_tool(
                    name="analysis_area",
                    arguments={**bounds, "max_locations": 5, "min_height_diff": 50.0, "road_radius_km": 5.0, "network_type": "drive", "page": 2, "page_size": 2},
                    host=host, port=port, path=path, session_id=session_id,
                )
                p2_content = area_p2_obj.get("result", {}).get("content", [])
                if p2_content:
                    p2_resp = json.loads(p2_content[0]["text"])
                    p2_data = p2_resp.get("data", {})
                    print(f"  -> Page 2 has {len(p2_data.get('items', []))} items. Resource ID: {p2_data.get('resource_id')}")
                    
        except Exception as e:
            print(f"  -> Error parsing area analysis: {e}")
            print("  -> Raw:", area_content[0]["text"][:200])


def main():
    """
    Entry point for the code execution orchestration demo.
    """
    orchestrate_workflow()


if __name__ == "__main__":
    main()

