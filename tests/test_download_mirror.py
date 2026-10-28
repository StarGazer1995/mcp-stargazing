"""Build-time catalog mirror selection uses astroquery's validated public setting."""

import pytest

from scripts.download_data import _simbad_client


def test_default_simbad_server(monkeypatch):
    monkeypatch.delenv('SIMBAD_SERVER', raising=False)
    assert _simbad_client().server == 'simbad.cds.unistra.fr'


def test_official_simbad_mirror(monkeypatch):
    monkeypatch.setenv('SIMBAD_SERVER', 'simbad.harvard.edu')
    assert _simbad_client().server == 'simbad.harvard.edu'


def test_invalid_simbad_mirror_fails(monkeypatch):
    monkeypatch.setenv('SIMBAD_SERVER', 'invalid.example')
    with pytest.raises(ValueError, match='does not correspond to a SIMBAD server'):
        _simbad_client()
