"""Validate the supervisord configuration for the dual-service Docker setup.

These tests ensure the supervisor config file is well-formed, that both the
MCP server and SPF web UI programs are correctly defined, and that the
Dockerfile is consistent with the supervisor configuration.
"""

import configparser
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPERVISORD_CONF = PROJECT_ROOT / 'supervisord.conf'
DOCKERFILE = PROJECT_ROOT / 'Dockerfile'


def _parse_config() -> configparser.RawConfigParser:
    """Parse the supervisord.conf file with INI-safe handling of %(env_*) vars."""
    # supervisor uses %(ENV_VAR)s for environment variable substitution;
    # ConfigParser interprets bare % as interpolation.  Use RawConfigParser
    # and pass an empty dict so it skips key lookups entirely.
    parser = configparser.RawConfigParser()
    parser.read(SUPERVISORD_CONF, encoding='utf-8')
    return parser


# ── Config file presence ──────────────────────────────────────────────


def test_supervisord_conf_exists():
    """supervisord.conf must exist at the project root."""
    assert SUPERVISORD_CONF.is_file(), f'supervisord.conf not found at {SUPERVISORD_CONF}'


# ── Sections ──────────────────────────────────────────────────────────


def test_supervisord_section_present():
    """The [supervisord] global section must be present."""
    cfg = _parse_config()
    assert cfg.has_section('supervisord'), 'Missing [supervisord] section'


def test_nodaemon_is_true():
    """supervisord must run in foreground (nodaemon=true) for Docker."""
    cfg = _parse_config()
    assert cfg.get('supervisord', 'nodaemon') == 'true', (
        'nodaemon must be true so supervisord stays in the foreground'
    )


# ── Programs ──────────────────────────────────────────────────────────


def test_mcp_program_defined():
    """The MCP server program must be configured."""
    cfg = _parse_config()
    assert cfg.has_section('program:mcp'), 'Missing [program:mcp] section'


def test_spf_web_program_defined():
    """The SPF web UI program must be configured."""
    cfg = _parse_config()
    assert cfg.has_section('program:spf-web'), 'Missing [program:spf-web] section'


def test_mcp_program_launches_correctly():
    """MCP must launch mcp-stargazing directly (no uv run — image is pre-built)."""
    cfg = _parse_config()
    command = cfg.get('program:mcp', 'command')
    assert command.startswith('mcp-stargazing'), (
        f'MCP command should start with mcp-stargazing, got: {command}'
    )
    assert '--mode shttp' in command, f'MCP command should use streamable HTTP mode, got: {command}'


def test_spf_web_program_launches_correctly():
    """SPF web must launch uvicorn directly (no uv run — image is pre-built)."""
    cfg = _parse_config()
    command = cfg.get('program:spf-web', 'command')
    assert command.startswith('uvicorn'), f'SPF command should start with uvicorn, got: {command}'
    assert 'server.main:app' in command, (
        f'SPF command should reference server.main:app, got: {command}'
    )


# ── Ports ─────────────────────────────────────────────────────────────


def test_mcp_port_is_3001():
    """MCP should listen on port 3001."""
    cfg = _parse_config()
    command = cfg.get('program:mcp', 'command')
    assert '--port 3001' in command, f'MCP should use port 3001, got: {command}'


def test_spf_web_port_is_5001():
    """SPF web should listen on port 5001."""
    cfg = _parse_config()
    command = cfg.get('program:spf-web', 'command')
    assert '--port 5001' in command, f'SPF web should use port 5001, got: {command}'


# ── Working directory ─────────────────────────────────────────────────


def test_both_programs_share_app_directory():
    """Both programs must run from /app (Docker WORKDIR)."""
    cfg = _parse_config()
    mcp_dir = cfg.get('program:mcp', 'directory')
    spf_dir = cfg.get('program:spf-web', 'directory')
    assert mcp_dir == '/app', f'MCP directory should be /app, got: {mcp_dir}'
    assert spf_dir == '/app', f'SPF directory should be /app, got: {spf_dir}'


# ── Auto-restart ──────────────────────────────────────────────────────


def test_both_programs_have_autorestart():
    """Both programs should auto-restart on failure."""
    cfg = _parse_config()
    assert cfg.get('program:mcp', 'autorestart') == 'true'
    assert cfg.get('program:spf-web', 'autorestart') == 'true'


# ── Dockerfile ↔ supervisord.conf consistency ─────────────────────────


def test_dockerfile_exposes_both_ports():
    """Dockerfile must EXPOSE both 3001 and 5001."""
    docker_text = DOCKERFILE.read_text(encoding='utf-8')
    expose_line = ''
    for line in docker_text.splitlines():
        if line.strip().startswith('EXPOSE'):
            expose_line = line.strip()
            break
    assert expose_line, 'Missing EXPOSE line in Dockerfile'
    assert '3001' in expose_line, f'Port 3001 not exposed: {expose_line}'
    assert '5001' in expose_line, f'Port 5001 not exposed: {expose_line}'


def test_dockerfile_installs_supervisor():
    """Dockerfile must install the supervisor package."""
    docker_text = DOCKERFILE.read_text(encoding='utf-8')
    assert 'supervisor' in docker_text, (
        'Dockerfile must install supervisor (apt-get install supervisor)'
    )


def test_dockerfile_entrypoint_is_supervisord():
    """Dockerfile ENTRYPOINT must be supervisord."""
    docker_text = DOCKERFILE.read_text(encoding='utf-8')
    assert 'ENTRYPOINT ["supervisord"]' in docker_text, 'Dockerfile ENTRYPOINT must be supervisord'


def test_supervisord_conf_path_matches_dockerfile():
    """The supervisor config path in CMD must match the COPY destination in Dockerfile."""
    docker_text = DOCKERFILE.read_text(encoding='utf-8')
    # Extract COPY destination
    copy_match = re.search(r'COPY supervisord\.conf (\S+)', docker_text)
    assert copy_match, 'Dockerfile must COPY supervisord.conf'
    dest_path = copy_match.group(1)

    # Extract CMD path
    cmd_match = re.search(r'CMD \["-c", "(\S+)"\]', docker_text)
    assert cmd_match, 'Dockerfile CMD must reference the config path'
    cmd_path = cmd_match.group(1)

    assert dest_path == cmd_path, f'COPY dest ({dest_path}) must match CMD path ({cmd_path})'
