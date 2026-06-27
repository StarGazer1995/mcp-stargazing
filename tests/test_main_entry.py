"""Tests for the server entry point: argument parsing and ``main()``."""

import os
import sys
from unittest.mock import patch

import pytest


class TestArgParse:
    """Tests for ``arg_parse()``."""

    def test_defaults(self):
        """Default arguments are correct."""
        with patch.object(sys, 'argv', ['mcp-stargazing']):
            from src.main import arg_parse

            args = arg_parse()
            assert args.mode == 'local'
            assert args.port == 3001
            assert args.path == '/shttp'
            assert args.proxy is None

    def test_custom_mode_port_path(self):
        """Custom mode, port, and path are parsed correctly."""
        test_args = ['mcp-stargazing', '--mode', 'shttp', '--port', '8080', '--path', '/mcp']
        with patch.object(sys, 'argv', test_args):
            from src.main import arg_parse

            args = arg_parse()
            assert args.mode == 'shttp'
            assert args.port == 8080
            assert args.path == '/mcp'

    def test_proxy_flag(self):
        """The --proxy flag is parsed."""
        with patch.object(sys, 'argv', ['mcp-stargazing', '--proxy', 'http://proxy:7890']):
            from src.main import arg_parse

            args = arg_parse()
            assert args.proxy == 'http://proxy:7890'


class TestMain:
    """Tests for ``main()`` with mocked server run calls."""

    @pytest.fixture(autouse=True)
    def _reset_main_module(self):
        """Ensure a fresh import of src.main for each test to avoid singleton state."""
        import src.main

        # Clear any cached module-level state
        src.main.iers_conf.auto_download = False
        src.main.iers_conf.auto_max_age = None

    def test_mode_dev_raises_attribute_error(self):
        """``main()`` mode='dev' raises AttributeError — ``run_dev`` removed in FastMCP 2.13+."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'dev']),
        ):
            from src.main import main

            # FastMCP >=2.13 removed `run_dev`.  The project may need to migrate
            # to `mcp.run(transport='stdio')` or a different dev workflow.
            with pytest.raises(AttributeError, match='run_dev'):
                main()

    def test_mode_local_calls_run(self):
        """``main()`` with mode='local' calls ``mcp.run()`` with no transport."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'local']),
            patch('src.main.mcp.run') as mock_run,
        ):
            from src.main import main

            main()
            mock_run.assert_called_once()

    def test_mode_shttp_calls_run_with_transport(self):
        """``main()`` with mode='shttp' calls ``mcp.run()`` with streamable-http."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'shttp', '--port', '3001']),
            patch('src.main.mcp.run') as mock_run,
            patch.dict(os.environ, {'MCP_HOST': '127.0.0.1'}),
        ):
            from src.main import main

            main()
            mock_run.assert_called_once_with(
                transport='streamable-http',
                host='127.0.0.1',
                port=3001,
                path='/shttp',
                log_level='debug',
            )

    def test_mode_sse_calls_run_with_transport(self):
        """``main()`` with mode='sse' calls ``mcp.run()`` with SSE transport."""
        with (
            patch.object(
                sys,
                'argv',
                ['mcp-stargazing', '--mode', 'sse', '--port', '8080', '--path', '/sse'],
            ),
            patch('src.main.mcp.run') as mock_run,
            patch.dict(os.environ, {'MCP_HOST': '0.0.0.0'}),
        ):
            from src.main import main

            main()
            mock_run.assert_called_once_with(
                transport='sse',
                host='0.0.0.0',
                port=8080,
                path='/sse',
                log_level='debug',
            )

    def test_invalid_mode_raises(self):
        """An invalid mode raises ValueError."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'invalid_mode']),
        ):
            from src.main import main

            with pytest.raises(ValueError, match='Invalid mode'):
                main()

    def test_proxy_sets_env_vars(self):
        """When --proxy is provided, HTTP_PROXY and HTTPS_PROXY are set."""
        with (
            patch.object(
                sys, 'argv', ['mcp-stargazing', '--mode', 'local', '--proxy', 'http://p:7890']
            ),
            patch('src.main.mcp.run'),
            patch.dict(os.environ, {}, clear=True),
        ):
            from src.main import main

            main()
            assert os.environ['HTTP_PROXY'] == 'http://p:7890'
            assert os.environ['HTTPS_PROXY'] == 'http://p:7890'
            assert os.environ['http_proxy'] == 'http://p:7890'
            assert os.environ['https_proxy'] == 'http://p:7890'

    def test_no_proxy_leaves_env_untouched(self):
        """Without --proxy, no proxy env vars are set."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'local']),
            patch('src.main.mcp.run'),
            patch.dict(os.environ, {}, clear=True),
        ):
            from src.main import main

            main()
            assert 'HTTP_PROXY' not in os.environ

    def test_iers_auto_download_enabled(self):
        """When ASTROPY_IERS_AUTO_DOWNLOAD=1, IERS auto-download is on."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'local']),
            patch('src.main.mcp.run'),
            patch.dict(os.environ, {'ASTROPY_IERS_AUTO_DOWNLOAD': '1'}),
        ):
            import src.main
            from src.main import main

            main()
            assert src.main.iers_conf.auto_download is True

    def test_mcp_host_default(self):
        """When MCP_HOST is not set, it defaults to '0.0.0.0'."""
        with (
            patch.object(sys, 'argv', ['mcp-stargazing', '--mode', 'shttp']),
            patch('src.main.mcp.run') as mock_run,
            patch.dict(os.environ, {}, clear=True),
        ):
            from src.main import main

            main()
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs['host'] == '0.0.0.0'
