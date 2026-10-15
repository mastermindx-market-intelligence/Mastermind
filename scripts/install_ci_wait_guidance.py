#!/usr/bin/env python3
"""Install bounded CI guidance and Codex hook-input compatibility corrections.

Default is a read-only plan. Explicit --apply backs up each changed target and
records partial progress on failure. No scheduler, credential, hook binding or
cooldown state is changed. Existing loaded conversations are not updated by this.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- mastermind-ci-observation-liveness-v1 -->'
END = '<!-- /mastermind-ci-observation-liveness-v1 -->'
ANCHOR = '<!-- /mastermind-assigned-execution-v1 -->'
TARGETS = {
    'guard': '.claude/hooks/mastermind_fabric_routing_guard.py',
    'context': '.claude/hooks/mastermind_fabric_context.py',
    'codex': '.codex/AGENTS.md',
    'claude': '.claude/CLAUDE.md',
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guidance() -> str:
    source = (ROOT / 'docs/sol_skills/ACTIVE_EXECUTION.md').read_text()
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError('canonical guidance markers missing or ambiguous')
    return source[source.index(START):source.index(END) + len(END)]


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(new) == 1 and old not in source:
        return source
    if source.count(old) != 1 or new in source:
        raise ValueError('unexpected installed guidance; reconcile drift before applying')
    return source.replace(old, new, 1)


def render(kind: str, source: str) -> str:
    if kind in ('guard', 'context'):
        patches = json.loads((ROOT / 'scripts/ci_wait_guidance_replacements.json').read_text())
        for patch in patches[kind]:
            source = replace_once(source, patch['old'], patch['new'])
        ast.parse(source)  # Refuse broken hook source before any file is written.
        return source
    block = guidance()
    if START in source or END in source:
        if source.count(START) != 1 or source.count(END) != 1 or block not in source:
            raise ValueError('installed liveness guidance differs; reconcile before applying')
        return source
    if source.count(ANCHOR) != 1:
        raise ValueError('assigned execution anchor missing or ambiguous')
    return source.replace(ANCHOR, ANCHOR + '\n\n' + block, 1)


def prepare(home: Path) -> list[dict]:
    plan = []
    for kind, relative in TARGETS.items():
        path = home / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'refusing missing or symlink target: {path}')
        before = path.read_bytes()
        after = render(kind, before.decode('utf-8')).encode('utf-8')
        plan.append(dict(kind=kind, path=path, before=before, after=after,
                         mode=stat.S_IMODE(path.stat().st_mode)))
    return plan


def summary(plan: list[dict]) -> list[dict]:
    return [dict(kind=p['kind'], path=str(p['path']), before_sha256=digest(p['before']),
                 after_sha256=digest(p['after']), changed=p['before'] != p['after']) for p in plan]


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def assert_unchanged(p: dict) -> None:
    path = p['path']
    if (path.is_symlink() or path.read_bytes() != p['before'] or
            stat.S_IMODE(path.stat().st_mode) != p['mode']):
        raise ValueError(f'target changed since preflight: {path}')


def apply(plan: list[dict], evidence: Path) -> dict:
    # Preflight every target before making backups or touching any installed file.
    for p in plan:
        assert_unchanged(p)
    evidence.mkdir(parents=True, exist_ok=False)
    report = dict(status='PREPARED', files=summary(plan), written=[], runtime_verified=False)
    receipt = evidence / 'install.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    try:
        for p in plan:
            if p['before'] == p['after']:
                continue
            backup = evidence / (p['kind'] + '.before')
            with backup.open('xb') as handle:
                handle.write(p['before'])
            backup.chmod(0o600)
        for p in plan:
            assert_unchanged(p)
            if p['before'] == p['after']:
                continue
            atomic_write(p['path'], p['after'], p['mode'])
            report['written'].append(str(p['path']))
            receipt.write_text(json.dumps(report, indent=2) + '\n')
        report['status'] = 'INSTALLED'
    except Exception as exc:
        # Do not roll back over a concurrent owner's edit. Preserve exact progress.
        report.update(status='PARTIAL_FAILURE', error=str(exc))
        raise
    finally:
        receipt.write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--evidence', type=Path, help='new backup/receipt directory required for apply')
    args = parser.parse_args()
    if args.apply and args.evidence is None:
        parser.error('--apply requires --evidence (new directory)')
    plan = prepare(args.home)
    report = apply(plan, args.evidence) if args.apply else dict(status='DRY_RUN', files=summary(plan))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
