#!/usr/bin/env python3
"""Project an explicitly selected execution brief into existing Markdown instructions.

This is an on-demand text maintenance utility, not a hook, permission manager,
policy engine, registry, scheduler or memory service. It changes no settings,
runtime permissions, provider defaults, active tasks or source leases.
Default mode is preview. Applying requires the exact target preimage and backup.
The caller must exclude concurrent writers. Preimage checks plus atomic rename
are not a filesystem compare-and-swap transaction or an execution-lease grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MARKER = 'mastermind-assigned-execution-v1'
MEMORY_MARKER = 'mastermind-execution-memory-advisory-v1'
LEGACY_BLOCKS = (
    'mastermind-ceo-forward-execution',
    'mastermind-ghost-owner-recovery-v1',
    'mastermind-autonomous-blocker-self-remedy-v1',
)
CODEX_SECTIONS = {
    'Act under the assignment', 'Minimum process that changes the next decision',
    'Use working delegation now', 'Repair real failures; scope real barriers',
    'Finish and report economically',
}
MEMORY_NOTICE = '''## Execution preference update — October 11, 2026

These records are historical evidence, not live authority, current permissions,
active source leases, available capacity or an always-on Web Meta-CEO. The current
assignment and protected procedure govern. Archived Web chats are not receivers;
a new session needs real creation and assignment. Preserve actual active writers,
exact-session proof obligations and unresolved effects on their original carrier.

Prefer verified end-to-end delivery, the shallowest useful admitted delegation,
one proportionate review and reuse of unchanged relevant evidence. Checkpoints
are saves followed by the next safe ready phase, not automatic stops. Do not
reconstruct the whole history, repeat routine approvals or tests, or wait for a
historical named owner when current assigned work can proceed safely. Old model
names, worker caps and routing prescriptions must be checked against current
policy and actual runtime, not copied from memory into a new grant.

Real permission/safety refusals, human-only authentication/consent, storage and
resource controls, budgets and release protections remain in force. A permissive
local setting never proves that a real approval prompt can be bypassed.
'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def remove_block(text: str, name: str) -> str:
    start, end = f'<!-- {name} -->', f'<!-- /{name} -->'
    if text.count(start) != text.count(end) or text.count(start) > 1:
        raise ValueError(f'Unbalanced or duplicate managed block: {name}')
    if start not in text:
        return text
    a, b = text.index(start), text.index(end)
    if b < a:
        raise ValueError(f'Reversed managed block: {name}')
    return text[:a] + text[b + len(end):]


def project(text: str, brief: str, profile: str) -> str:
    if profile not in {'codex', 'claude', 'memory'}:
        raise ValueError('Unknown Markdown profile')
    marker = MEMORY_MARKER if profile == 'memory' else MARKER
    text = remove_block(text, marker)
    if profile != 'memory':
        for legacy in LEGACY_BLOCKS:
            text = remove_block(text, legacy)
    if profile == 'codex':
        heading = '# Execution-first defaults for assigned work'
        if text.count(heading) > 1:
            raise ValueError('Duplicate legacy execution heading')
        if heading in text:
            before, rest = text.split(heading, 1)
            # Only named sections are retired. Preserve modal consent, actual
            # transport instructions, native restrictions and unknown user text.
            parts = re.split(r'(?m)^(?=##? )', rest)
            # Unclassified preamble text is user content, not a named retired
            # section. Preserve it even when the legacy heading has no children.
            retained = [parts[0]]
            for section in parts[1:]:
                first = section.splitlines()[0]
                if first.startswith('## ') and first[3:] in CODEX_SECTIONS:
                    continue
                retained.append(section)
            text = before.rstrip() + '\n\n' + ''.join(retained)
    body = MEMORY_NOTICE if profile == 'memory' else brief.strip()
    block = f'<!-- {marker} -->\n{body.rstrip()}\n<!-- /{marker} -->\n'
    # Codex memory v2 uses this explicit first-line version header.
    prefix = ''
    if profile == 'memory' and text.startswith('v1\n'):
        prefix, text = 'v1\n\n', text[3:]
    return prefix + block + '\n' + text.strip() + '\n'


def apply(path: Path, new_text: str, expected_sha256: str, backup_dir: Path) -> dict:
    path = path.expanduser()
    if path.suffix.lower() != '.md' or path.is_symlink() or not path.is_file():
        raise ValueError('Target must be an existing regular Markdown file, not a symlink')
    current = path.read_bytes()
    before = digest(current)
    if before != expected_sha256:
        raise ValueError('Target changed: exact preimage does not match; no write performed')
    new = new_text.encode('utf-8')
    if current == new:
        return {'path': str(path), 'changed': False, 'before_sha256': before, 'after_sha256': before}
    backup_dir = backup_dir.expanduser()
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = digest(str(path.absolute()).encode())[:16]
    backup = backup_dir / f'{identity}-{before}.md'
    try:
        with backup.open('xb') as handle:
            handle.write(current)
        backup.chmod(0o600)
    except FileExistsError:
        if backup.read_bytes() != current:
            raise ValueError('Existing backup disagrees; no target write performed')
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, name = tempfile.mkstemp(prefix='.execution-brief-', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(new)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(mode)
        if path.is_symlink() or digest(path.read_bytes()) != before:
            raise ValueError('Target changed during preparation; no target write performed')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    after = digest(path.read_bytes())
    if after != digest(new):
        raise RuntimeError('Post-write readback differs; reconcile target before further edits')
    return {'path': str(path), 'changed': True, 'before_sha256': before,
            'after_sha256': after, 'before_bytes': len(current), 'after_bytes': len(new),
            'backup': str(backup)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path, required=True)
    parser.add_argument('--profile', choices=['codex', 'claude', 'memory'], required=True)
    parser.add_argument('--brief', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    if args.path.suffix.lower() != '.md' or args.path.is_symlink():
        parser.error('Only explicit non-symlink Markdown targets are supported')
    original = args.path.read_bytes()
    text = project(original.decode('utf-8'), args.brief.read_text(), args.profile)
    if args.apply:
        if not args.expected_sha256 or args.backup_dir is None:
            parser.error('--apply requires --expected-sha256 and --backup-dir')
        result = apply(args.path, text, args.expected_sha256, args.backup_dir)
    else:
        result = {'path': str(args.path), 'preview_only': True,
                  'before_sha256': digest(original), 'after_sha256': digest(text.encode()),
                  'before_bytes': len(original), 'after_bytes': len(text.encode()),
                  'changed': original != text.encode()}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
