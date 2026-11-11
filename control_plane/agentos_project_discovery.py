"""Fixed selected-WS metadata compilation by the captured canonical C owner.

Called inside the installed isolated child. Inputs were captured from Git N;
the owner/parser and all helper imports remain pinned to C. This function
neither discovers projects nor authenticates a caller. It builds the actual
canonical Agent OS state record; no Plan DTO is promoted into a Work card.
"""
from datetime import datetime, timezone, date
from pathlib import Path
import re


def compile_captured_record(*, owner, record, source, code_source, data_root,
                            observed_at_ms, git):
    if (type(observed_at_ms) is not int or not 0 < observed_at_ms <= 9007199254740991
            or type(record) is not dict or record.get('key') != source['path'].split('/WS-', 1)[1][:-3]):
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    work_ref = 'WS:' + record['key']
    path = Path(data_root) / source['path']
    # Canonical build_records uses author dates, not a request clock. Capture
    # the same two facts from the exact DATA revision under the parent's
    # cumulative deadline. A re-added path is ambiguous here and is refused.
    added = git('log', '--diff-filter=A', '--max-count=2', '--format=%as',
                source['commit'], '--', source['path'], limit=256).splitlines()
    updated = git('log', '--max-count=1', '--format=%as', source['commit'],
                  '--', source['path'], limit=256).splitlines()
    if len(added) != 1 or len(updated) != 1:
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    for value in (*added, *updated):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is None:
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        date.fromisoformat(value)
    store = owner.Store(Path(data_root) / 'agentos')
    store.records['WS/' + record['key']] = record
    store.paths['WS/' + record['key']] = path
    store.counts['workstreams'] = 1
    original = owner.git_dates_batch

    def captured_dates(paths):
        if list(paths) != [path]:
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        return {path: (added[0], updated[0])}

    owner.git_dates_batch = captured_dates
    try:
        state = owner.build_state(store, now=datetime.fromtimestamp(observed_at_ms / 1000, timezone.utc),
            degraded=owner.Degraded(), builds=None, p0_status=None, worktrees={})
    finally:
        owner.git_dates_batch = original
    if (type(state) is not dict or state.get('schema') != 'agent_os_state.v1'
            or type(state.get('workstreams')) is not list or len(state['workstreams']) != 1
            or state['workstreams'][0].get('key') != record['key']):
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    return dict(schema='mastermind.project_discovery_record.v1', selection={'work_ref': work_ref},
        source=source, code_source=code_source, observed_at_ms=observed_at_ms, agent_os_state=state)


def read_from_macro_owner(*, macro_root, expected_macro_sha, work_ref, code_root,
                          code_commit, observed_at_ms, timeout=10.0, runner=None):
    from control_plane.agentos_project_plan import read_from_macro_owner as read
    return read(macro_root=macro_root, expected_macro_sha=expected_macro_sha, work_ref=work_ref,
        code_root=code_root, code_commit=code_commit, timeout=timeout, runner=runner,
        _discovery_observed_at_ms=observed_at_ms)
