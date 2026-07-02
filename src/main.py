import argparse
import os
from importlib.metadata import version

from astropy.utils.iers import conf as iers_conf
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import modules to register tools on process startup.
import src.functions.celestial.impl  # noqa: F401
import src.functions.metadata.impl  # noqa: F401
import src.functions.places.impl  # noqa: F401
import src.functions.planning.impl  # noqa: F401
import src.functions.time.impl  # noqa: F401
import src.functions.weather.impl  # noqa: F401
from src.logging_config import get_logger, setup_logging
from src.server_instance import mcp


@mcp.custom_route('/health', methods=['GET'])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for container probes and load balancers."""
    return JSONResponse(
        {
            'status': 'healthy',
            'version': version('mcp-stargazing'),
            'service': 'mcp-stargazing',
        }
    )


def arg_parse():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='MCP Server')
    parser.add_argument(
        '--mode', type=str, default='local', help='Mode of operation (local, shttp, or sse)'
    )
    parser.add_argument('--port', type=int, default=3001, help='Port to run the server on')
    parser.add_argument('--path', type=str, default='/shttp')
    parser.add_argument('--proxy', type=str, help='Proxy URL (e.g., http://127.0.0.1:7890)')
    return parser.parse_args()


def main():
    """Run the MCP server."""
    arg = arg_parse()
    setup_logging(dev_mode=arg.mode == 'local')
    logger = get_logger(__name__)
    host = os.getenv('MCP_HOST', '0.0.0.0')  # nosec - intentional MCP server bind
    auto_env = os.getenv('ASTROPY_IERS_AUTO_DOWNLOAD', '0')
    iers_conf.auto_download = auto_env == '1'
    iers_conf.auto_max_age = None

    # Configure proxy if provided
    if arg.proxy:
        os.environ['HTTP_PROXY'] = arg.proxy
        os.environ['HTTPS_PROXY'] = arg.proxy
        os.environ['http_proxy'] = arg.proxy
        os.environ['https_proxy'] = arg.proxy
        logger.info('Proxy configured', proxy=arg.proxy)

    if arg.mode == 'local':
        mcp.run()
    elif arg.mode == 'shttp':
        mcp.run(
            transport='streamable-http', host=host, port=arg.port, path=arg.path, log_level='debug'
        )
    elif arg.mode == 'sse':
        mcp.run(transport='sse', host=host, port=arg.port, path=arg.path, log_level='debug')
    else:
        raise ValueError('Invalid mode')


if __name__ == '__main__':
    main()
