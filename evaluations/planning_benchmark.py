"""Repeatable frozen policy gate or live MCP observation, with explicit evidence limits."""

import argparse
import asyncio
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from src.schemas import AgentPlanningRequest, AgentPlanningResult
from src.services.planning_quality import IMAGING_POLICY

from .imaging_quality import CASES, build_case


def summarize(samples):
    durations = sorted(sample['elapsed_seconds'] for sample in samples)
    return {
        'attempts': len(samples),
        'execution_successes': sum(s['execution_success'] for s in samples),
        'expectation_checks': sum(s['expectation_passed'] is not None for s in samples),
        'expectation_passes': sum(s['expectation_passed'] is True for s in samples),
        'p50_seconds': statistics.median(durations) if durations else None,
        'p95_seconds': durations[math.ceil(len(durations) * 0.95) - 1] if durations else None,
        'percentile_method': 'nearest rank for p95; small samples are descriptive only',
    }


async def run_case(case, *, mode, url, timeout):
    events = []
    started = perf_counter()
    sample = {
        'case': case['id'],
        'started_at': datetime.now(UTC).isoformat(),
        'execution_success': False,
        'expectation_passed': None,
        'stages': events,
    }
    try:
        if mode == 'frozen':
            service, request = build_case(case['id'], events.append)
            result = await service.build_agent_plan(request)
        else:
            from fastmcp import Client

            async with Client(url, timeout=timeout) as client:
                request = AgentPlanningRequest.model_validate(case['request'])
                reply = await client.call_tool(
                    'plan_stargazing_session', {'request': request.model_dump(mode='json')}
                )
                payload = reply.structured_content or reply.data
                if payload.get('_meta', {}).get('status') != 'success':
                    raise ValueError(str(payload.get('error')))
                result = AgentPlanningResult.model_validate(payload['data'])
        sample['execution_success'] = True
        sample['decision_present'] = result.decision is not None
        sample['uncertainty_codes'] = [u.code for u in result.uncertainties]
        if 'expected_decision' in case:
            sample['expectation_passed'] = sample['decision_present'] == case['expected_decision']
        if result.decision:
            sample['window'] = (
                result.decision.observation_window.model_dump()
                if result.decision.observation_window
                else None
            )
        # Live observations do not by themselves establish forecast accuracy or site validity.
        sample['forecast_accuracy_verified'] = False
        sample['site_access_verified'] = False
    except Exception as exc:
        sample['error'] = f'{type(exc).__name__}: {exc}'[:500]
        if 'expected_decision' in case:
            sample['expectation_passed'] = False
    sample['elapsed_seconds'] = perf_counter() - started
    return sample


async def run(args):
    if args.mode == 'frozen':
        cases = [{'id': name, 'expected_decision': expected} for name, expected in CASES.items()]
    else:
        if not args.url or not args.requests:
            raise ValueError(
                'live mode requires --url and --requests (JSON array of id/request objects)'
            )
        cases = json.loads(args.requests.read_text())
        if not isinstance(cases, list) or not cases:
            raise ValueError('--requests must contain a non-empty array')
    samples = []
    for repeat in range(args.repeats):
        for case in cases:
            sample = await run_case(case, mode=args.mode, url=args.url, timeout=args.timeout)
            sample['repeat'] = repeat + 1
            samples.append(sample)
    return {
        'recorded_at': datetime.now(UTC).isoformat(),
        'mode': args.mode,
        'scope': (
            'network-free policy fixtures; latency is not production performance'
            if args.mode == 'frozen'
            else 'live client latency; provider stage times remain in server planning_stage logs'
        ),
        'policy': IMAGING_POLICY if args.mode == 'frozen' else None,
        'target_label': args.label,
        'summary': summarize(samples),
        'samples': samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['frozen', 'live'], default='frozen')
    parser.add_argument('--url')
    parser.add_argument('--label', default='unspecified')
    parser.add_argument('--requests', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0:
        parser.error('repeats and timeout must be positive')
    report = asyncio.run(run(args))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / 'planning-benchmark.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    text = (
        '# Planning benchmark\n\n'
        + report['scope']
        + '\n\n```json\n'
        + json.dumps(report['summary'], indent=2)
        + '\n```\n'
    )
    (args.out_dir / 'planning-benchmark.md').write_text(text)
    print(json.dumps(report['summary']))
    return (
        0
        if all(
            s['execution_success'] and s['expectation_passed'] is not False
            for s in report['samples']
        )
        else 1
    )


if __name__ == '__main__':
    raise SystemExit(main())
