"""Validate the published SPF dependency actually embedded by MCP."""

import re
import tomllib
from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient
from packaging.requirements import Requirement
from packaging.version import Version

from src.paths import PROJECT_ROOT


def test_spf_requirement_and_installed_version_include_search_fix():
    project = tomllib.loads((PROJECT_ROOT / 'pyproject.toml').read_text())['project']
    requirement = next(
        Requirement(item)
        for item in project['dependencies']
        if item.startswith('stargazing-place-finder')
    )
    assert Version('0.9.4') not in requirement.specifier
    assert Version('0.9.5') in requirement.specifier
    assert Version(version('stargazing-place-finder')) in requirement.specifier


@pytest.mark.parametrize('query, canonical', [('M42', 'M 42'), ('NGC7000', 'NGC 7000')])
def test_bundled_spf_resolves_catalog_ids_without_remote_lookup(monkeypatch, query, canonical):
    from server.main import app
    from server.routes import name_resolution

    def reject_remote(**kwargs):
        raise AssertionError('Known catalog IDs must not query a remote resolver')

    monkeypatch.setattr(name_resolution.httpx, 'AsyncClient', reject_remote)
    response = TestClient(app).get('/api/telescope/resolve', params={'name': query})
    assert response.status_code == 200
    target = response.json()
    assert target['name'] == canonical
    assert target['source'] == 'local_catalog'
    assert 0 <= target['ra'] < 360
    assert -90 <= target['dec'] <= 90


def test_bundled_spf_serves_single_search_field_and_built_assets():
    from server.main import app

    client = TestClient(app)
    page = client.get('/')
    assert page.status_code == 200
    assert page.text.count('id="search-input"') == 1
    assert 'aladin-search-input' not in page.text
    assets = re.findall(r'(?:src|href)="(/assets/[^"?]+\.(?:js|css))"', page.text)
    assert any(asset.endswith('.js') for asset in assets)
    assert any(asset.endswith('.css') for asset in assets)
    for asset in assets:
        assert client.get(asset).status_code == 200
