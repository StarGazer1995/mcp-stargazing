import os
import argparse
from src.server_instance import mcp

# Import modules to register tools
import src.functions.celestial.impl
import src.functions.weather.impl
import src.functions.places.impl
import src.functions.time.impl

def arg_parse():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="MCP Server")
    parser.add_argument("--mode", type=str, default='local', help="Mode of operation (dev local or server)")
    parser.add_argument("--port", type=int, default=3001, help="Port to run the server on")
    parser.add_argument("--path", type=str, default="/shttp")
    parser.add_argument("--proxy", type=str, help="Proxy URL (e.g., http://127.0.0.1:7890)")
    return parser.parse_args()

def main():
    """Run the MCP server."""
    arg = arg_parse()
    
    # Configure proxy if provided
    if arg.proxy:
        os.environ["HTTP_PROXY"] = arg.proxy
        os.environ["HTTPS_PROXY"] = arg.proxy
        os.environ["http_proxy"] = arg.proxy
        os.environ["https_proxy"] = arg.proxy
        print(f"Proxy set to {arg.proxy}")
        
    if arg.mode == 'dev':
        mcp.run_dev()
    elif arg.mode == 'local':
        mcp.run()
    elif arg.mode == 'shttp':
        mcp.run(transport="streamable-http", host="127.0.0.1", port=arg.port, path=arg.path, log_level="debug")
    elif arg.mode == 'sse':
        mcp.run(transport="sse", host="127.0.0.1", port=arg.port, path=arg.path, log_level="debug")
    else:
        raise ValueError("Invalid mode")

if __name__ == "__main__":
    main()
