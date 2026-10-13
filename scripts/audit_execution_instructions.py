#!/usr/bin/env python3
"""Read-only instruction-discovery audit for explicitly selected local paths.

Shows the static Codex file chain plus metadata for other chosen Markdown files.
It does not execute hooks, edit settings, admit work, load secrets, contact a
provider, or claim that an existing model session consumed the files. This is an
on-demand diagnostic, not a startup requirement, watcher, or policy authority.

Discovery reference: OpenAI's 'Unrolling the Codex agent loop' and AGENTS.md guide.
Global instructions precede project instructions. Project bytes share one cap;
more specific files appear later. The CLI reads provider-home configuration only;
repository/profile/managed overrides require separate observation. Only Markdown
fallback files are supported by this audit. Runtime overrides and injected
instructions are deliberately not invented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tomllib

SCAN_BYTES = 64 * 1024
LEGACY_SIGNALS = {
    'blanket_one_shot_ban': 'No one-shot strategic builds',
    'blanket_no_coding_role': 'Your primary job is not to code',
    'mandatory_program_stages': '## Required sequence for major programs',
    'old_checkpoint_boundary': 'CHECKPOINTED_CONTINUATION requires a justified boundary',
}


def inspect_markdown(path: Path) -> dict:
    path = Path(path).expanduser().absolute()
    if path.suffix.lower() != '.md' or not path.is_file():
        raise ValueError('Choose an existing Markdown file explicitly')
    size = path.stat().st_size
    with path.open('rb') as handle:
        prefix = handle.read(SCAN_BYTES)
    complete = size == len(prefix)
    text = prefix.decode('utf-8', errors='replace')
    return {
        'path': str(path), 'bytes': size, 'is_symlink': path.is_symlink(),
        'sha256': hashlib.sha256(prefix).hexdigest() if complete else None,
        'scanned_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
        'content_scan_truncated': not complete,
        'line_count': len(text.splitlines()) if complete else None,
        'assigned_execution_marker': '<!-- mastermind-assigned-execution-v1 -->' in text,
        'legacy_signals': [name for name, literal in LEGACY_SIGNALS.items() if literal in text],
        'signal_interpretation': 'Literal presence requires contextual review; not an execution verdict.',
    }


def _selected(directory: Path, names: list[str]) -> Path | None:
    for name in names:
        path = directory / name
        if path.is_file() and path.stat().st_size:
            return path
    return None


def codex_chain(
    codex_home: Path, repo_root: Path, cwd: Path, *,
    fallback_names: list[str] | None = None, project_max_bytes: int = 32 * 1024,
) -> dict:
    home, root, work = (Path(p).expanduser().resolve() for p in (codex_home, repo_root, cwd))
    if not all(p.is_dir() for p in (home, root, work)):
        raise ValueError('Provider home, repository root and working directory must exist')
    if not work.is_relative_to(root):
        raise ValueError('Working directory must be inside the explicitly selected repository')
    if isinstance(project_max_bytes, bool) or not isinstance(project_max_bytes, int) or project_max_bytes < 0:
        raise ValueError('Project instruction byte budget must be a nonnegative integer')
    fallbacks = list(fallback_names or [])
    for name in fallbacks:
        if not isinstance(name, str) or not name or Path(name).name != name or name in {'.', '..'}:
            raise ValueError('Fallback names must be simple filenames, never paths')
    names = list(dict.fromkeys(['AGENTS.override.md', 'AGENTS.md', *fallbacks]))
    chain = []
    global_path = _selected(home, ['AGENTS.override.md', 'AGENTS.md'])
    if global_path:
        item = inspect_markdown(global_path)
        item.update(scope='global', eligible_bytes=item['bytes'], truncated_by_project_budget=False)
        chain.append(item)
    directories = [root]
    for part in work.relative_to(root).parts:
        directories.append(directories[-1] / part)
    remaining = project_max_bytes
    for directory in directories:
        path = _selected(directory, names)
        if path is None:
            continue
        item = inspect_markdown(path)
        eligible = min(remaining, item['bytes'])
        remaining -= eligible
        item.update(scope='project', eligible_bytes=eligible,
                    truncated_by_project_budget=eligible < item['bytes'])
        chain.append(item)
    return {
        'effect': 'READ_ONLY', 'runtime_verified': False,
        'method': 'Static file discovery; no provider session was launched or inspected.',
        'codex_home': str(home), 'repo_root': str(root), 'cwd': str(work),
        'project_max_bytes': project_max_bytes, 'project_remaining_bytes': remaining,
        'chain': chain,
        'not_observed': ['injected project instructions', 'active-session context',
                         'managed provider policy', 'plugin selection', 'hook execution',
                         'remote accounts and other hosts'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--additional-markdown', type=Path, action='append', default=[])
    args = parser.parse_args()
    config_path = args.codex_home.expanduser() / 'config.toml'
    try:
        config = {}
        if config_path.is_file():
            if config_path.stat().st_size > SCAN_BYTES:
                raise ValueError('Selected config exceeds bounded audit size; choose explicit function arguments')
            config = tomllib.loads(config_path.read_text())
        report = codex_chain(
            args.codex_home, args.repo_root, args.cwd or args.repo_root,
            fallback_names=config.get('project_doc_fallback_filenames', []),
            project_max_bytes=config.get('project_doc_max_bytes', 32 * 1024),
        )
        report['additional_markdown'] = [inspect_markdown(p) for p in args.additional_markdown]
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
