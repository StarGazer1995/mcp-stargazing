#!/usr/bin/env python3
"""Validate release metadata before tags, PyPI publication, or Docker builds."""

from __future__ import annotations

import argparse
import subprocess
import tomllib
from pathlib import Path


def read_project_version(pyproject: Path) -> str:
    """Read the package version from a PEP 621 project table."""
    data = tomllib.loads(pyproject.read_text(encoding='utf-8'))
    version = data.get('project', {}).get('version')
    if not isinstance(version, str) or not version:
        raise ValueError(f'No project.version found in {pyproject}')
    return version


def validate_tag(tag: str, version: str) -> None:
    """Require the release tag to be exactly ``v<pyproject version>``."""
    expected = f'v{version}'
    if tag != expected:
        raise ValueError(f'Release tag mismatch: expected {expected}, got {tag}')


def distribution_versions(dist_dir: Path) -> dict[str, str]:
    """Return package artifact filename → embedded filename version."""
    artifacts: dict[str, str] = {}
    for path in sorted(dist_dir.iterdir()):
        if path.name.endswith('.whl'):
            parts = path.name.split('-')
            if len(parts) >= 2 and parts[0] == 'mcp_stargazing':
                artifacts[path.name] = parts[1]
        elif path.name.startswith('mcp_stargazing-') and path.name.endswith('.tar.gz'):
            artifacts[path.name] = path.name.removeprefix('mcp_stargazing-').removesuffix('.tar.gz')
    return artifacts


def validate_distribution_versions(dist_dir: Path, version: str) -> None:
    """Require built wheel and sdist filenames to carry the project version."""
    artifacts = distribution_versions(dist_dir)
    wheels = [name for name in artifacts if name.endswith('.whl')]
    sdists = [name for name in artifacts if name.endswith('.tar.gz')]
    if not wheels or not sdists:
        raise ValueError(f'Expected wheel and sdist artifacts in {dist_dir}, found {artifacts}')

    mismatches = {
        name: artifact_version
        for name, artifact_version in artifacts.items()
        if artifact_version != version
    }
    if mismatches:
        raise ValueError(f'Distribution version mismatch; expected {version}: {mismatches}')


def validate_ancestor(ancestor: str, commit: str = 'HEAD') -> None:
    """Require ``commit`` to be reachable from the named release branch."""
    result = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', commit, ancestor],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f'{commit} is not reachable from {ancestor}')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)

    version_parser = subparsers.add_parser('version')
    version_parser.add_argument('--pyproject', type=Path, default=Path('pyproject.toml'))

    tag_parser = subparsers.add_parser('validate-tag')
    tag_parser.add_argument('--tag', required=True)
    tag_parser.add_argument('--pyproject', type=Path, default=Path('pyproject.toml'))

    dist_parser = subparsers.add_parser('validate-dist')
    dist_parser.add_argument('--dist-dir', type=Path, default=Path('dist'))
    dist_parser.add_argument('--version', required=True)

    ancestor_parser = subparsers.add_parser('validate-ancestor')
    ancestor_parser.add_argument('--ancestor', required=True)
    ancestor_parser.add_argument('--commit', default='HEAD')

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == 'version':
        print(read_project_version(args.pyproject))
    elif args.command == 'validate-tag':
        validate_tag(args.tag, read_project_version(args.pyproject))
        print(f'Release tag {args.tag} matches pyproject version.')
    elif args.command == 'validate-dist':
        validate_distribution_versions(args.dist_dir, args.version)
        print(f'Distribution artifacts match version {args.version}.')
    elif args.command == 'validate-ancestor':
        validate_ancestor(args.ancestor, args.commit)
        print(f'{args.commit} is reachable from {args.ancestor}.')


if __name__ == '__main__':
    main()
