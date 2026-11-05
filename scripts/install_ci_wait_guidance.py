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
# Exact accepted pre-attended block from protected d107f25c (not arbitrary marker trust).
PREVIOUS_GUIDANCE_SHA256 = frozenset({
    'f723c1107590214f61750d00afb9efa35c1f2fc982bff69b2bcc249baaf63298',
})
TARGETS = {
    'guard': '.claude/hooks/mastermind_fabric_routing_guard.py',
    'context': '.claude/hooks/mastermind_fabric_context.py',
    'codex': '.codex/AGENTS.md',
    'claude': '.claude/CLAUDE.md',
}
POLL_IDENTITY_START = '# BEGIN source-owned CI poll identity'
POLL_IDENTITY_END = '# END source-owned CI poll identity'
PR_MUTATION_UPDATE = '''    for key in ci_pr_poll_mutation_keys(clean, str(payload.get("cwd") or ""), state):
        changed = state.pop(key, None) is not None or changed
'''


def render_poll_identity(source: str) -> str:
    """Embed the bounded PR classifier without changing cooldown or watch policy."""
    helper = (ROOT / 'scripts/ci_poll_identity.py').read_text().strip()
    helper = helper.replace('from __future__ import annotations\n', '')
    embedded = POLL_IDENTITY_START + '\n' + helper + '\n' + POLL_IDENTITY_END
    original = '''def _poll_key(clean):
    m = PR_CHECK_RE.search(clean)
    if m:
        return f"pr-checks:{m.group('id')}"
    m = PR_VIEW_RE.search(clean)
    if m and PR_VIEW_STATUS_FIELDS_RE.search(m.group("tail") or ""):
        return f"pr-view:{m.group('id')}"
    m = RUN_VIEW_RE.search(clean)'''
    replacement = '''def _poll_key(clean, cwd=""):
    pr_key = ci_pr_poll_identity(clean, cwd)
    if pr_key is not None:
        return pr_key
    m = RUN_VIEW_RE.search(clean)'''
    if POLL_IDENTITY_START in source or POLL_IDENTITY_END in source:
        if (source.count(embedded) != 1 or source.count(POLL_IDENTITY_START) != 1
                or source.count(POLL_IDENTITY_END) != 1
                or source.count(replacement) != 1 or original in source):
            raise ValueError('installed CI poll classifier differs; reconcile before applying')
    else:
        source = replace_once(source, original, embedded + '\n\n\n' + replacement)
    source = replace_once(source, 'key = _poll_key(clean)',
                          'key = _poll_key(clean, str(payload.get("cwd") or ""))')
    if PR_MUTATION_UPDATE not in source:
        source = replace_once(source, '    for match in RUN_MUTATION_RE.finditer(clean):',
                              PR_MUTATION_UPDATE + '    for match in RUN_MUTATION_RE.finditer(clean):')
    elif source.count(PR_MUTATION_UPDATE) != 1:
        raise ValueError('installed PR mutation invalidation differs; reconcile before applying')
    return source


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guidance() -> str:
    source = (ROOT / 'docs/sol_skills/ACTIVE_EXECUTION.md').read_text()
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError('canonical guidance markers missing or ambiguous')
    begin, end = source.index(START), source.index(END)
    if end < begin:
        raise ValueError('canonical guidance markers are reversed')
    return source[begin:end + len(END)]


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
        if kind == 'guard':
            source = render_poll_identity(source)
        ast.parse(source)  # Refuse broken hook source before any file is written.
        return source
    block = guidance()
    if START in source or END in source:
        if source.count(START) != 1 or source.count(END) != 1:
            raise ValueError('installed liveness guidance differs; reconcile before applying')
        begin, end = source.index(START), source.index(END)
        if end < begin:
            raise ValueError('installed liveness guidance markers are reversed')
        end += len(END)
        installed = source[begin:end]
        if installed == block:
            return source
        # Upgrade only an exact protected predecessor. Unknown edits, including
        # whitespace drift, are not permission to overwrite account instructions.
        if digest(installed.encode('utf-8')) not in PREVIOUS_GUIDANCE_SHA256:
            raise ValueError('installed liveness guidance differs; reconcile before applying')
        return source[:begin] + block + source[end:]
    if source.count(ANCHOR) != 1:
        raise ValueError('assigned execution anchor missing or ambiguous')
    return source.replace(ANCHOR, ANCHOR + '\n\n' + block, 1)


def prepare(home: Path, targets: list[str] | None = None) -> list[dict]:
    plan = []
    for kind in dict.fromkeys(targets or TARGETS):
        if kind not in TARGETS:
            raise ValueError(f'unknown installed guidance target: {kind}')
        relative = TARGETS[kind]
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
    parser.add_argument('--target', action='append', choices=tuple(TARGETS),
                        help='limit this operation to named targets; default is all four')
    parser.add_argument('--evidence', type=Path, help='new backup/receipt directory required for apply')
    args = parser.parse_args()
    if args.apply and args.evidence is None:
        parser.error('--apply requires --evidence (new directory)')
    plan = prepare(args.home, args.target)
    report = apply(plan, args.evidence) if args.apply else dict(status='DRY_RUN', files=summary(plan))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
