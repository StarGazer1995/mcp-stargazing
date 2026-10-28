"""Build-time catalog mirror selection uses astroquery's validated public setting."""

from unittest.mock import Mock

import pytest
from astropy.table import Table

from scripts.download_data import _query_objects, _simbad_client


def test_identifier_batches_preserve_all_names():
    client = Mock()
    client.query_objects.side_effect = lambda names, **kwargs: Table({'name': names})
    names = [f'NGC {index}' for index in range(205)]
    result = _query_objects(client, names)
    assert list(result['name']) == names
    assert [len(call.args[0]) for call in client.query_objects.call_args_list] == [100, 100, 5]


def test_missing_batch_fails_closed():
    client = Mock()
    client.query_objects.return_value = None
    with pytest.raises(RuntimeError, match='catalog is incomplete'):
        _query_objects(client, ['M 1'])


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
