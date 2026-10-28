"""Build-time catalog mirror selection uses astroquery's validated public setting."""

from unittest.mock import Mock

import pytest
import requests
from astropy.table import Table
from pyvo.dal.exceptions import DALServiceError

from scripts import download_data
from scripts.download_data import _identifier_query, _query_objects, _simbad_client


@pytest.fixture
def mirrors(monkeypatch):
    clients = {}
    for server in download_data._SIMBAD_SERVERS:
        client = Mock(server=server)
        client.query_tap.return_value = Table({'name': ['M 1']})
        clients[server] = client
    monkeypatch.setattr(
        download_data, '_simbad_client', lambda server='simbad.cds.unistra.fr': clients[server]
    )
    monkeypatch.setattr(download_data.requests, 'get', Mock())
    monkeypatch.setattr(download_data.time, 'sleep', Mock())
    return clients


def test_identifier_batches_preserve_all_names(mirrors):
    client = mirrors['simbad.cds.unistra.fr']
    names = [f'NGC {index}' for index in range(205)]
    client.query_tap.side_effect = [
        Table({'name': names[:100]}),
        Table({'name': names[100:200]}),
        Table({'name': names[200:]}),
    ]
    result = _query_objects(client, names)
    assert list(result['name']) == names
    assert client.query_tap.call_count == 3
    assert client.query_tap.call_args_list[1].args[0] == _identifier_query(names[100:200])
    for call in client.query_tap.call_args_list:
        assert call.kwargs['async_job'] is True
        assert 'TAP_UPLOAD' not in call.args[0]
        assert 'script_infos' not in call.kwargs


def test_identifier_query_escapes_literals():
    query = _identifier_query(["Barnard's galaxy", 'NGC 1333'])
    assert "IN ('Barnard''s galaxy','NGC 1333')" in query


def test_missing_batch_fails_closed(mirrors):
    client = mirrors['simbad.cds.unistra.fr']
    client.query_tap.side_effect = None
    client.query_tap.return_value = None
    with pytest.raises(RuntimeError, match='catalog is incomplete'):
        _query_objects(client, ['M 1'])


def test_connection_failure_switches_mirror_and_keeps_working_mirror(mirrors, monkeypatch):
    primary = mirrors['simbad.cds.unistra.fr']
    backup = mirrors['simbad.harvard.edu']
    backup.query_tap.side_effect = [
        Table({'name': [str(i) for i in range(100)]}),
        Table({'name': ['100']}),
    ]

    def connect(url, **kwargs):
        assert kwargs['timeout'] == (5, 15)
        if 'cds.unistra.fr' in url:
            raise requests.ConnectTimeout('unreachable')
        return Mock()

    probe = Mock(side_effect=connect)
    monkeypatch.setattr(download_data.requests, 'get', probe)
    result = _query_objects(primary, [str(i) for i in range(101)])
    assert len(result) == 101
    primary.query_tap.assert_not_called()
    assert backup.query_tap.call_count == 2
    assert probe.call_count == 3  # primary retries once, backup is probed once


def test_transient_query_failure_retries_same_batch(mirrors):
    primary = mirrors['simbad.cds.unistra.fr']
    primary.query_tap.side_effect = [DALServiceError('504'), Table({'name': ['M 1']})]
    assert len(_query_objects(primary, ['M 1'])) == 1
    assert primary.query_tap.call_count == 2
    mirrors['simbad.harvard.edu'].query_tap.assert_not_called()


def test_query_failure_switches_mirror_without_losing_prior_batch(mirrors):
    primary = mirrors['simbad.cds.unistra.fr']
    primary.query_tap.side_effect = [
        Table({'name': [str(i) for i in range(100)]}),
        DALServiceError('504'),
        DALServiceError('504'),
    ]
    mirrors['simbad.harvard.edu'].query_tap.return_value = Table({'name': ['100']})
    result = _query_objects(primary, [str(i) for i in range(101)])
    assert list(result['name']) == [str(i) for i in range(101)]
    assert mirrors['simbad.harvard.edu'].query_tap.call_args.args[0] == _identifier_query(['100'])


def test_all_mirrors_fail_closed(mirrors):
    for client in mirrors.values():
        client.query_tap.side_effect = DALServiceError('504')
    with pytest.raises(RuntimeError, match='mirrors failed; catalog is incomplete'):
        _query_objects(mirrors['simbad.cds.unistra.fr'], ['M 1'])
    assert all(client.query_tap.call_count == 2 for client in mirrors.values())


def test_query_validation_error_is_not_retried(mirrors):
    client = mirrors['simbad.cds.unistra.fr']
    client.query_tap.side_effect = ValueError('invalid query')
    with pytest.raises(ValueError, match='invalid query'):
        _query_objects(client, ['M 1'])
    assert client.query_tap.call_count == 1


def test_messier_download_failure_does_not_publish_partial_catalog(mirrors):
    for client in mirrors.values():
        client.query_tap.side_effect = DALServiceError('504')
    with pytest.raises(RuntimeError, match='catalog is incomplete'):
        download_data.download_messier_objects()


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
