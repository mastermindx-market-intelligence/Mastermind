"""Canonical pure factoring and fixed artifact-bound proof; fixtures only."""
import dataclasses
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from control_plane import chairman_control_room as ccr
from control_plane import executive_inbox as inbox
from control_plane.executive_runtime import Runtime
from tests.test_workspace_programs_qualification import empty_inputs
from tests.test_executive_inbox import store, frozen_git


def artifact(tmp_path, value=None):
    p = tmp_path / ccr.AGENT_OS_STATE_RELATIVE_PATH
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(value or {'schema': ccr.AGENT_OS_STATE_SCHEMA, 'workstreams': []}))
    return p


@pytest.mark.parametrize('value', ['bad', {}, [None], [{'key': None}]])
def test_malformed_workstream_collection_is_visible(value):
    args = empty_inputs(); args['agent_os_state']['workstreams'] = value
    doc = ccr.compose_control_room(**args)
    assert any(x.startswith('agent_os_state:') for x in doc['degraded'])


@pytest.mark.parametrize('field,value', [('repositories','bad'), ('repositories',[None]),
    ('open_prs','bad'), ('open_prs',[None]), ('recently_merged','bad')])
def test_malformed_repository_collections_are_visible(field, value):
    args = empty_inputs()
    args['active_builds']['repositories'] = value if field == 'repositories' else [{field: value}]
    assert any(x.startswith('active_builds:') for x in ccr.compose_control_room(**args)['degraded'])


@pytest.mark.parametrize('budget', [0, 1, True, 2097153])
def test_installed_budget_is_closed(tmp_path, budget):
    artifact(tmp_path)
    doc, error = ccr._read_agent_os_state(str(tmp_path), installed_byte_budget=budget)
    assert doc is None and error


def test_exact_artifact_budget_and_one_extra_byte(tmp_path):
    p = artifact(tmp_path)
    bound = ccr.INSTALLED_MACRO_ARTIFACT_BYTES
    p.write_bytes(b'{"x":"' + b'a' * (bound - 8) + b'"}')
    assert p.stat().st_size == bound
    assert ccr._read_agent_os_state(str(tmp_path), installed_byte_budget=bound)[1] is None
    with p.open('ab') as f: f.write(b' ')
    assert ccr._read_agent_os_state(str(tmp_path), installed_byte_budget=bound)[0] is None


def test_physical_reads_have_size_bound(tmp_path, monkeypatch):
    artifact(tmp_path)
    real = os.fdopen; sizes = []
    class Stream:
        def __init__(self, f): self.f = f
        def __enter__(self): return self
        def __exit__(self, *args): return self.f.__exit__(*args)
        def fileno(self): return self.f.fileno()
        def read(self, size): sizes.append(size); return self.f.read(size)
    monkeypatch.setattr(os, 'fdopen', lambda *a, **k: Stream(real(*a, **k)))
    bound = ccr.INSTALLED_MACRO_ARTIFACT_BYTES
    assert ccr._read_agent_os_state(str(tmp_path), installed_byte_budget=bound)[1] is None
    assert sizes == [bound + 1, bound + 1]


@pytest.mark.parametrize('mutation', ['replace', 'rewrite', 'parent'])
def test_changed_source_identity_or_content_is_refused(tmp_path, monkeypatch, mutation):
    p = artifact(tmp_path); content = p.read_bytes(); real = os.open; calls = 0
    def open_changed(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if mutation == 'replace':
                new = p.with_suffix('.new'); new.write_bytes(content); new.replace(p)
            elif mutation == 'rewrite':
                p.write_bytes(content.replace(b'workstreams', b'workstreamz'))
            else:
                old = p.parent.with_name('old-governance'); p.parent.rename(old)
                p.parent.mkdir(); p.write_bytes(content)
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', open_changed)
    doc, error = ccr._read_agent_os_state(str(tmp_path), installed_byte_budget=ccr.INSTALLED_MACRO_ARTIFACT_BYTES)
    assert doc is None and error


def test_bounded_slice_never_produces_global_counts_or_reconciliation(store):
    runtime = Runtime.at(store, create=False)
    jobs = runtime.jobs.list_jobs(); attempts = runtime.attempts.list_attempts()
    result = inbox.project_runtime_inputs(jobs=jobs, attempts=attempts, workers=None,
        provenance_by_job={}, completeness='bounded')
    assert result.counts == {'jobs': None, 'attempts': None, 'workers': None}
    assert result.suppressed is None
    assert any('global Jobs/Attempts/Workers' in x for x in result.degraded)


def test_bounded_unknown_review_attempt_does_not_classify_terminal(store):
    runtime = Runtime.at(store, create=False)
    job = dataclasses.replace(runtime.jobs.list_jobs()[0], reviews_job_id='NOT-IN-SLICE')
    result = inbox.project_runtime_inputs(jobs=[job], attempts=[], workers=None,
        provenance_by_job={}, completeness='bounded')
    assert result.attention == [] and result.suppressed is None
    assert any('required Attempt evidence unavailable' in x for x in result.degraded)


def test_pure_and_legacy_assembly_are_identical(store, frozen_git):
    packet = empty_inputs()['boot_packet']; now = '2026-09-21T00:00:00Z'
    dt = datetime.fromisoformat(now.replace('Z', '+00:00'))
    legacy = inbox.build_inbox(repo_root=store, boot_packet=packet, now=now)
    runtime = Runtime.at(store, create=False)
    jobs=runtime.jobs.list_jobs(); attempts=runtime.attempts.list_attempts(); workers=runtime.workers.list_workers()
    provenance = {job.job_id: inbox.ceo_intent_provenance(runtime, job.job_id)[0] for job in jobs}
    pure = inbox.project_runtime_inputs(jobs=jobs, attempts=attempts, workers=workers,
        provenance_by_job=provenance, completeness='whole', now=dt)
    result = inbox.compose_inbox(runtime_projection=pure, boot_packet=packet,
        mastermind_grounding=legacy['grounding']['mastermind'],
        runtime_grounding=legacy['grounding']['runtime_db'], generated_at=now)
    assert result == legacy
