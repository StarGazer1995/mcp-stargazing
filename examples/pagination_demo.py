import http.client
import json
import time
from typing import Dict, Any, Tuple

def initialize_session(host: str = "127.0.0.1", port: int = 3001, path: str = "/shttp") -> str:
    """Initialize MCP streamable HTTP session and return session ID."""
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "examples-pagination", "version": "1.0"},
            "capabilities": {},
            "protocolVersion": "2024-11-"
        }
    })
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    session_id = resp.getheader("mcp-session-id") or ""
    
    # Drain the SSE response until 'data:' line to ensure initialization
    # (Simplified for demo)
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8").strip()
        if decoded.startswith("data: "):
            break
            
    conn.close()
    if not session_id:
        raise RuntimeError("Failed to get session ID")
    print(f"Session initialized: {session_id}")
    return session_id

def call_tool(
    name: str,
    arguments: Dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 3001,
    path: str = "/shttp",
    session_id: str = ""
) -> Dict[str, Any]:
    """Call an MCP tool and return the parsed JSON result object."""
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": f"call-{int(time.time()*1000)}",
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
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    
    result = {}
    while True:
        line = resp.readline()
        if not line:
            break
        decoded = line.decode("utf-8").strip()
        if decoded.startswith("data: "):
            payload = decoded[6:] # Strip "data: "
            try:
                parsed = json.loads(payload)
                if "result" in parsed or "error" in parsed:
                    result = parsed
                    break
            except:
                pass
    conn.close()
    return result

def run_pagination_demo():
    """
    Demonstrate how to fetch a large result set in chunks using pagination.
    This pattern is crucial for LLM contexts where we cannot fit 
    thousands of items in a single message.
    """
    HOST = "127.0.0.1"
    PORT = 3001
    PATH = "/shttp"
    
    print("=== Starting Pagination Demo ===")
    
    # 1. Initialize
    try:
        session_id = initialize_session(HOST, PORT, PATH)
    except Exception as e:
        print(f"Error connecting to server: {e}")
        print("Ensure the server is running with: python -m src.main --mode shttp --port 3001 --proxy http://127.0.0.1:7890")
        return

    # 2. Define search parameters
    # A wide area to ensure we get enough results
    search_params = {
        "south": 39.5, "west": 115.5, 
        "north": 40.5, "east": 116.5,
        "max_locations": 10,          # Reduced from 50 for faster demo
        "min_height_diff": 50.0,
        "road_radius_km": 10.0,
        "network_type": "drive"
    }
    
    # 3. Fetch Page 1 (Page Size = 5)
    print("\n[Step 1] Fetching Page 1 (5 items)...")
    resp_p1 = call_tool(
        "analysis_area",
        {**search_params, "page": 1, "page_size": 5},
        HOST, PORT, PATH, session_id
    )
    
    # Extract data from the tool's text content result
    content_p1 = resp_p1.get("result", {}).get("content", [])
    if not content_p1:
        print("No content in response:", resp_p1)
        return

    data_resp_p1 = json.loads(content_p1[0]["text"])
    data_p1 = data_resp_p1.get("data", {})
    
    total_items = data_p1.get("total", 0)
    items_p1 = data_p1.get("items", [])
    resource_id = data_p1.get("resource_id")
    
    print(f"  -> Total items found: {total_items}")
    print(f"  -> Returned items: {len(items_p1)}")
    print(f"  -> Resource ID (Cache Key): {resource_id}")
    
    if items_p1:
        print(f"  -> First item: {items_p1[0].get('name', 'Unknown')}")

    # 4. Fetch Page 2 (Page Size = 5)
    # The server uses the same search params to hit the cache (resource_id is implicitly derived from params)
    if total_items > 5:
        print("\n[Step 2] Fetching Page 2 (5 items)...")
        resp_p2 = call_tool(
            "analysis_area",
            {**search_params, "page": 2, "page_size": 5},
            HOST, PORT, PATH, session_id
        )
        
        content_p2 = resp_p2.get("result", {}).get("content", [])
        data_resp_p2 = json.loads(content_p2[0]["text"])
        data_p2 = data_resp_p2.get("data", {})
        items_p2 = data_p2.get("items", [])
        
        print(f"  -> Returned items: {len(items_p2)}")
        if items_p2:
            print(f"  -> First item of Page 2: {items_p2[0].get('name', 'Unknown')}")
            
        # Verify that we got different items
        if items_p1 and items_p2 and items_p1[0]['name'] == items_p2[0]['name']:
            print("  [WARNING] Page 1 and Page 2 start with the same item!")
        else:
            print("  [SUCCESS] Pagination seems to work correctly (different items returned).")
            
    else:
        print("Not enough items to demonstrate pagination.")

    print("\n=== Demo Complete ===")

if __name__ == "__main__":
    run_pagination_demo()
