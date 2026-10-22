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


START = b'<!-- mastermind-assigned-execution-v1 -->'
END = b'<!-- /mastermind-assigned-execution-v1 -->'


def managed_brief_evidence(data: bytes, *, complete: bool, expected_brief: str | None = None) -> dict:
    """Report bounded byte evidence, never authority or actual provider loading."""
    starts, ends = data.count(START), data.count(END)
    result = {'state': 'ABSENT', 'start_byte': None, 'end_byte': None,
              'body_sha256': None, 'normalization': 'outer whitespace stripped'}
    if starts == 1:
        result['start_byte'] = data.index(START)
    if not complete:
        result['state'] = 'UNKNOWN_TRUNCATED'
        return result
    if not starts and not ends:
        return result
    if starts != 1 or ends != 1 or data.index(END) < data.index(START):
        result['state'] = 'MALFORMED'
        return result
    a, b = data.index(START), data.index(END)
    body = data[a + len(START):b].strip()
    result.update(end_byte=b + len(END), body_sha256=hashlib.sha256(body).hexdigest(),
                  state='PRESENT_UNCOMPARED')
    if expected_brief is not None:
        expected = expected_brief.strip().encode('utf-8')
        if len(expected) > SCAN_BYTES:
            raise ValueError('Expected brief exceeds bounded audit size')
        result['expected_body_sha256'] = hashlib.sha256(expected).hexdigest()
        result['state'] = 'MATCH' if body == expected else 'CONTENT_MISMATCH'
    return result


def _eligibility(item: dict, count: int) -> None:
    brief = item['execution_brief']
    start, end = brief['start_byte'], brief['end_byte']
    item['assigned_execution_marker_eligible'] = start is not None and start + len(START) <= count
    item['execution_brief_fully_eligible'] = end is not None and end <= count
    item['expected_brief_eligible'] = brief['state'] == 'MATCH' and item['execution_brief_fully_eligible']


def inspect_markdown(path: Path, *, expected_brief: str | None = None) -> dict:
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
        'assigned_execution_marker': START in prefix,
        'execution_brief': managed_brief_evidence(prefix, complete=complete, expected_brief=expected_brief),
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
    expected_brief: str | None = None,
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
    shadowed = []

    def select(directory: Path, candidates: list[str]) -> Path | None:
        winner = _selected(directory, candidates)
        if winner is not None:
            for name in candidates[candidates.index(winner.name) + 1:]:
                other = directory / name
                if other.is_file() and other.stat().st_size:
                    shadowed.append({'path': str(other), 'selected_path': str(winner),
                                     'reason': 'HIGHER_PRIORITY_FILENAME'})
        return winner
    global_path = select(home, ['AGENTS.override.md', 'AGENTS.md'])
    if global_path:
        item = inspect_markdown(global_path, expected_brief=expected_brief)
        item.update(scope='global', eligible_bytes=item['bytes'], truncated_by_project_budget=False)
        _eligibility(item, item['bytes'])
        chain.append(item)
    directories = [root]
    for part in work.relative_to(root).parts:
        directories.append(directories[-1] / part)
    remaining = project_max_bytes
    for directory in directories:
        path = select(directory, names)
        if path is None:
            continue
        item = inspect_markdown(path, expected_brief=expected_brief)
        eligible = min(remaining, item['bytes'])
        remaining -= eligible
        item.update(scope='project', eligible_bytes=eligible,
                    truncated_by_project_budget=eligible < item['bytes'])
        _eligibility(item, eligible)
        chain.append(item)
    return {
        'effect': 'READ_ONLY', 'runtime_verified': False,
        'method': 'Static file discovery; no provider session was launched or inspected.',
        'codex_home': str(home), 'repo_root': str(root), 'cwd': str(work),
        'project_max_bytes': project_max_bytes, 'project_remaining_bytes': remaining,
        'chain': chain, 'shadowed_files': shadowed,
        'expected_brief_selected': any(x['expected_brief_eligible'] for x in chain),
        'selection_interpretation': 'Static eligibility only; not semantic precedence, runtime trust, or served-session proof.',
        'not_observed': ['injected project instructions', 'active-session context',
                         'managed provider policy', 'plugin selection', 'hook execution',
                         'remote accounts and other hosts'],
    }


def completeness_evidence(report: dict, *, expected_requested: bool = False) -> dict:
    """Summarize missing static evidence without deciding runtime permissions.

    The optional CLI check is a caller-selected diagnostic, never a startup hook,
    admission decision, instruction rewrite, or proof that a model loaded a file.
    """
    findings = []
    for item in report['chain']:
        if item['truncated_by_project_budget']:
            findings.append({'code': 'PROJECT_BUDGET_TRUNCATION', 'path': item['path'],
                             'omitted_bytes': item['bytes'] - item['eligible_bytes']})
        if item['eligible_bytes'] and item['content_scan_truncated']:
            findings.append({'code': 'CONTENT_SCAN_INCOMPLETE', 'path': item['path']})
        if item['eligible_bytes'] and item['execution_brief']['state'] == 'MALFORMED':
            findings.append({'code': 'MANAGED_BRIEF_MALFORMED', 'path': item['path']})
        if item['execution_brief_fully_eligible'] and item['execution_brief']['state'] == 'CONTENT_MISMATCH':
            findings.append({'code': 'EXPECTED_BRIEF_CONTENT_MISMATCH', 'path': item['path']})
    if expected_requested and not report['expected_brief_selected']:
        findings.append({'code': 'EXPECTED_BRIEF_NOT_ELIGIBLE'})
    return {'scope': 'STATIC_FILE_EVIDENCE_ONLY', 'complete': not findings, 'findings': findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Return 1 for incomplete static instruction evidence; does not gate or inspect runtime execution')
    parser.add_argument('--codex-home', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--additional-markdown', type=Path, action='append', default=[])
    parser.add_argument('--expected-brief', type=Path, help='Compare managed blocks with this explicit Markdown brief; report only, never repair')
    args = parser.parse_args()
    config_path = args.codex_home.expanduser() / 'config.toml'
    try:
        config = {}
        expected = None
        if args.expected_brief is not None:
            brief_path = args.expected_brief.expanduser()
            if brief_path.suffix.lower() != '.md' or brief_path.stat().st_size > SCAN_BYTES:
                raise ValueError('Expected brief must be a bounded Markdown file')
            expected = brief_path.read_text(encoding='utf-8')
        if config_path.is_file():
            if config_path.stat().st_size > SCAN_BYTES:
                raise ValueError('Selected config exceeds bounded audit size; choose explicit function arguments')
            config = tomllib.loads(config_path.read_text())
        report = codex_chain(
            args.codex_home, args.repo_root, args.cwd or args.repo_root,
            fallback_names=config.get('project_doc_fallback_filenames', []),
            project_max_bytes=config.get('project_doc_max_bytes', 32 * 1024),
            expected_brief=expected,
        )
        report['additional_markdown'] = [inspect_markdown(p, expected_brief=expected) for p in args.additional_markdown]
        report['completeness'] = completeness_evidence(report, expected_requested=expected is not None)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if args.check and not report['completeness']['complete'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
