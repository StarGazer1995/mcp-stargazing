"""Recovery over actual HTTP connections and fresh server processes."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from conftest import _get_free_port, _wait_for_server
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from src.paths import PROJECT_ROOT

REQUEST = {
    'bounds': {'south': 30, 'west': 119, 'north': 31, 'east': 120},
    'road_radius_km': 0,
    'max_locations': 2,
}


def local_client(url):
    def http_client(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout or httpx.Timeout(10),
            auth=auth,
            trust_env=False,
            follow_redirects=True,
        )

    return Client(StreamableHttpTransport(url, httpx_client_factory=http_client), timeout=10)


@pytest.fixture
def server(tmp_path):
    processes = []

    def stop(process):
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def start():
        port = _get_free_port()
        log = (tmp_path / f'server-{len(processes)}.log').open('w', encoding='utf-8')
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith('STARGAZING_TASK_')
        }
        env.update(STARGAZING_TASK_WORKERS='1', STARGAZING_TASK_QUEUE_CAPACITY='0')
        process = subprocess.Popen(
            [
                sys.executable,
                '-m',
                'evaluations.area_task_server',
                '--control-dir',
                str(tmp_path),
                '--port',
                str(port),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        processes.append((process, log))
        try:
            _wait_for_server('127.0.0.1', port, '/shttp', timeout_seconds=20)
        except Exception as exc:
            stop(process)
            raise AssertionError(log.name + '\n' + Path(log.name).read_text()) from exc
        return process, f'http://127.0.0.1:{port}/shttp'

    yield start, stop, tmp_path
    (tmp_path / 'release').touch()
    for process, log in reversed(processes):
        stop(process)
        log.close()


async def call(client, name, **arguments):
    result = await client.call_tool(name, arguments)
    payload = result.structured_content
    assert payload['_meta']['status'] == 'success', payload
    return payload['data']


async def wait_status(client, task_id, predicate):
    async with asyncio.timeout(10):
        while True:
            status = await call(client, 'get_area_analysis_task', task_id=task_id)
            if predicate(status):
                return status
            await asyncio.sleep(0.02)


def calls(control):
    return [json.loads(line) for line in (control / 'calls.jsonl').read_text().splitlines()]


@pytest.mark.asyncio
async def test_disconnect_reconnect_pagination_and_actual_restart(server):
    start, stop, control = server
    process, url = start()
    async with local_client(url) as client:
        submitted = await call(client, 'submit_area_analysis', request=REQUEST)
        task_id = submitted['task_id']
        await wait_status(client, task_id, lambda state: state['state'] == 'running')
    # A new connection must observe the same still-running job after disconnect.
    async with local_client(url) as client:
        running = await call(client, 'get_area_analysis_task', task_id=task_id)
        assert running['state'] == 'running'
        assert running['execution_pending'] is True
        assert running['progress'] is None
        duplicate = await call(client, 'submit_area_analysis', request=REQUEST)
        assert duplicate['task_id'] == task_id
        (control / 'release').touch()
        completed = await wait_status(client, task_id, lambda state: state['state'] == 'succeeded')
        page_one = await call(client, 'get_area_analysis_result', task_id=task_id, page_size=1)
    async with local_client(url) as client:
        page_two = await call(
            client, 'get_area_analysis_result', task_id=task_id, page=2, page_size=1
        )
        assert page_one['items'][0]['name'] == 'Recovery Ridge'
        assert page_two['items'][0]['name'] == 'Recovery Valley'
        assert page_one['resource_id'] == page_two['resource_id'] == submitted['resource_id']
        assert page_two['total'] == 2
        # Reading pages must not trigger another provider execution.
        assert len(calls(control)) == 1
    stop(process)
    (control / 'release').unlink()
    (control / 'started').unlink()
    _replacement, new_url = start()
    async with local_client(new_url) as client:
        for name in (
            'get_area_analysis_task',
            'get_area_analysis_result',
            'cancel_area_analysis_task',
        ):
            stale = await client.call_tool(name, {'task_id': task_id})
            assert stale.structured_content['error']['code'] == 'TASK_RUNTIME_CHANGED'
        retry = await call(client, 'submit_area_analysis', request=completed['request'])
        assert retry['task_id'] != task_id
        assert retry['resource_id'] == submitted['resource_id']
        # A restarted process has neither the old task registry nor its result cache.
        running = await wait_status(
            client, retry['task_id'], lambda state: state['state'] == 'running'
        )
        assert running['result_revision'] is None
        async with asyncio.timeout(5):
            while not (control / 'started').exists():
                await asyncio.sleep(0.02)
        assert len(calls(control)) == 2
        (control / 'release').touch()
        finished = await wait_status(
            client, retry['task_id'], lambda state: state['state'] == 'succeeded'
        )
        assert finished['result_revision'] != completed['result_revision']
        page = await call(client, 'get_area_analysis_result', task_id=retry['task_id'])
        assert page['total'] == 2


@pytest.mark.asyncio
async def test_cancel_after_disconnect_retains_slot_until_provider_finishes(server):
    start, _stop, control = server
    _process, url = start()
    async with local_client(url) as client:
        task = await call(client, 'submit_area_analysis', request=REQUEST)
        task_id = task['task_id']
        await wait_status(client, task_id, lambda state: state['state'] == 'running')
    async with local_client(url) as client:
        cancelled = await call(client, 'cancel_area_analysis_task', task_id=task_id)
        assert cancelled['state'] == 'cancelled'
        assert cancelled['execution_pending'] is True
        duplicate = await client.call_tool('submit_area_analysis', {'request': REQUEST})
        assert duplicate.structured_content['error']['code'] == 'TASK_CAPACITY_EXCEEDED'
        (control / 'release').touch()
        drained = await wait_status(client, task_id, lambda state: not state['execution_pending'])
        assert drained['state'] == 'cancelled'
        assert drained['result_revision'] is None
        unavailable = await client.call_tool('get_area_analysis_result', {'task_id': task_id})
        assert unavailable.structured_content['error']['code'] == 'TASK_UNAVAILABLE'
        # A retry must compute again: the cancelled execution published nothing.
        retry = await call(client, 'submit_area_analysis', request=REQUEST)
        assert retry['task_id'] != task_id
        await wait_status(client, retry['task_id'], lambda state: state['state'] == 'succeeded')
        assert len(calls(control)) == 2


@pytest.mark.asyncio
async def test_crashed_process_cannot_resume_its_inflight_task(server):
    start, _stop, control = server
    process, url = start()
    async with local_client(url) as client:
        old = await call(client, 'submit_area_analysis', request=REQUEST)
        await wait_status(client, old['task_id'], lambda state: state['state'] == 'running')
        async with asyncio.timeout(5):
            while not (control / 'started').exists():
                await asyncio.sleep(0.02)
    # Deliberately crash only the child created by this test, before publication.
    process.kill()
    process.wait(timeout=5)
    _replacement, new_url = start()
    async with local_client(new_url) as client:
        stale = await client.call_tool('get_area_analysis_task', {'task_id': old['task_id']})
        assert stale.structured_content['error']['code'] == 'TASK_RUNTIME_CHANGED'
        retry = await call(client, 'submit_area_analysis', request=old['request'])
        assert retry['task_id'] != old['task_id']
        assert retry['resource_id'] == old['resource_id']
        (control / 'release').touch()
        await wait_status(client, retry['task_id'], lambda state: state['state'] == 'succeeded')
        assert len(calls(control)) == 2
