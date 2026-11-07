#!/usr/bin/env python3
"""Package immutable specialist methods; never install, grant or launch anything."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPECIALISTS = (
    'mastermind-ci-triage',
    'mastermind-product-path-proof',
    'mastermind-market-source-validation',
    'mastermind-quant-validation',
    'mastermind-telemetry-investigation',
)
PARTS = ('SKILL.md', 'agents/openai.yaml', 'references/cases.md')
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 1024 * 1024


def source_paths(include_native_routing: bool = False) -> tuple[str, ...]:
    names = SPECIALISTS + (('agent-pools',) if include_native_routing else ())
    return tuple(f'skills/{name}/{part}' for name in names for part in PARTS)


def read_commit_files(repo: Path, sha: str, include_native_routing: bool = False) -> dict[str, bytes]:
    """Read only fixed regular-file blobs from one local immutable Git commit."""
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('EXACT_COMMIT_REQUIRED')
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1')

    def git(*args: str) -> bytes:
        return subprocess.run(
            ['git', '--no-replace-objects', *args], cwd=repo, env=env,
            check=True, capture_output=True, timeout=15,
        ).stdout

    if git('cat-file', '-t', sha).strip() != b'commit':
        raise ValueError('SOURCE_IS_NOT_COMMIT')
    files: dict[str, bytes] = {}
    for path in source_paths(include_native_routing):
        row = git('ls-tree', '-z', sha, '--', path)
        parts = row.rstrip(b'\0').split(b'\t')
        if len(parts) != 2 or parts[1].decode('utf-8') != path:
            raise ValueError('SOURCE_FILE_MISSING')
        metadata = parts[0].decode('ascii').split()
        if len(metadata) != 3 or metadata[:2] != ['100644', 'blob']:
            raise ValueError('SOURCE_NOT_REGULAR_TEXT')
        size = int(git('cat-file', '-s', metadata[2]).strip())
        if size > MAX_FILE_BYTES:
            raise ValueError('SOURCE_FILE_TOO_LARGE')
        data = git('cat-file', 'blob', metadata[2])
        data.decode('utf-8')
        if len(data) != size:
            raise ValueError('SOURCE_SIZE_MISMATCH')
        files[path] = data
    if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise ValueError('PACKAGE_TOO_LARGE')
    return files


def assemble(files: dict[str, bytes], sha: str, *, include_native_routing: bool = False) -> dict[str, bytes]:
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('EXACT_COMMIT_REQUIRED')
    if set(files) != set(source_paths(include_native_routing)):
        raise ValueError('SOURCE_CENSUS_MISMATCH')
    if any(not isinstance(data, bytes) for data in files.values()):
        raise ValueError('SOURCE_BYTES_REQUIRED')
    for data in files.values():
        data.decode('utf-8')
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('SOURCE_FILE_TOO_LARGE')
    if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise ValueError('PACKAGE_TOO_LARGE')
    names = SPECIALISTS + (('agent-pools',) if include_native_routing else ())
    for name in names:
        entry = files[f'skills/{name}/SKILL.md'].decode('utf-8')
        if not entry.startswith(f'---\nname: {name}\ndescription: ') or '\n---\n' not in entry[4:]:
            raise ValueError('SKILL_IDENTITY_MISMATCH')
    manifest = {
        'name': 'mastermind-specialists',
        'version': '0.1.0',
        'description': 'Task-scoped CI, product verification, market evidence, quantitative validation and telemetry methods.',
        'author': {'name': 'Mastermind-X'},
        'skills': './skills/',
    }
    result = dict(files)
    # OpenAI requires presentation metadata; Claude must not inherit unknown keys.
    codex = {**manifest, 'interface': {
        'displayName': 'Mastermind Specialists',
        'shortDescription': 'Evidence-based engineering and market validation workflows',
        'longDescription': 'Task-scoped CI, product verification, market evidence, quantitative validation and incident methods. Skills provide methods, not new tool access.',
        'developerName': 'Mastermind-X',
        'category': 'Productivity',
        'capabilities': ['Read'],
    }}
    for directory, projected in (('.codex-plugin', codex), ('.claude-plugin', manifest)):
        result[f'{directory}/plugin.json'] = (json.dumps(projected, sort_keys=True, indent=2) + '\n').encode()
    result['BUILD.json'] = (json.dumps({
        'schema': 'mastermind.specialist_method_artifact.v1',
        'source_commit': sha,
        'state': 'PACKAGED_NOT_INSTALLED',
        'native_skill_attested': False,
        'execution_authority': False,
        'include_native_routing': include_native_routing,
        'canonical_source_files': {
            path: {'path': path, 'sha256': hashlib.sha256(data).hexdigest()}
            for path, data in sorted(files.items())
        },
    }, sort_keys=True, indent=2) + '\n').encode()
    result['README.md'] = b'''# Mastermind Specialists

These original methods extend existing Mastermind workflows. Load only the method
needed for the assigned task. BUILD.json binds the exported bytes to source; it
is not installation, runtime admission, model-use or acceptance evidence.

This package installs no MCP server, hook, browser engine, provider adapter,
credential, process, permission or service. Use supported native or Web plugin
installation only after source review and applicable release approval. Sealed
Fabric workers need their existing capability-package/profile admission.

The optional agent-pools compatibility skill is for authorized native parents,
not Web shell delegation or ambient leaf-worker spawning. Preserve an incumbent
installation and inspect duplicates before rollout. Do not auto-enable it in a
Web plugin or replace a live skill from a source candidate without its release.
'''
    return result


def zip_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or not name:
                raise ValueError('ARCHIVE_PATH_INVALID')
            info = zipfile.ZipInfo('mastermind-specialists/' + name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-native-routing', action='store_true')
    args = parser.parse_args(argv)
    try:
        source = read_commit_files(ROOT, args.source_sha, args.include_native_routing)
        data = zip_bytes(assemble(source, args.source_sha, include_native_routing=args.include_native_routing))
        with args.output.open('xb') as handle:
            handle.write(data)
        if args.output.read_bytes() != data:
            raise ValueError('PACKAGE_READBACK_FAILED')
        print(json.dumps({'state': 'PACKAGED_NOT_INSTALLED', 'source_commit': args.source_sha,
                          'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                          'native_skill_attested': False, 'execution_authority': False}, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'state': 'PACKAGE_FAILED', 'error_type': type(exc).__name__,
                          'native_skill_attested': False, 'execution_authority': False}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
