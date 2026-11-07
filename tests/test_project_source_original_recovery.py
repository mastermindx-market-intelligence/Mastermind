"""Original command custody after artifact commit but before INTENT."""
import hashlib
import json
import os

import pytest

from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts, TerminalInputError
from tests.test_terminal_original_input_supervisor import empty_owner
from tests.test_workspace_source_operations import lookup, SCOPE, STAMP, FP


def payload():
    return {"schema":"mastermind.project_source_original_input.v1", "action":"ADOPT_PLAN",
            "request":{"request_id":lookup()["request_id"],"work_ref":"WS:TEST","private_goal":"source-private-canary"},
            "actor":{"decided_at":"2026-11-04","rationale":"retained private rationale"},
            "initial_snapshot":{"raw":b"literal original source bytes"},"source_binding":{}}


def test_actual_private_original_lookup_recovers_same_bytes_ref_and_stamp_without_event_or_job(tmp_path):
    runtime,supervisor,adapter=empty_owner(tmp_path)
    private=ProjectSourceOriginalInput(supervisor)
    assert private.lookup_original(lookup(),SCOPE,guard=lambda:True) is None
    assert not supervisor.runs_root.exists()
    body=payload()
    ref=private.prepare(lookup(),SCOPE,payload=body,trusted_recipe_fingerprint=FP,permission_binding_digest=STAMP)
    recovered=private.lookup_original(lookup(),SCOPE,guard=lambda:True)
    assert recovered["private_payload"]==body and recovered["original_input"]==ref.to_dict()
    assert recovered["permission_binding_digest"]==STAMP and recovered["recipe_fingerprint_sha256"]==FP
    assert recovered["request_sha256"]==hashlib.sha256(json.dumps(body["request"],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    # Complete the incumbent idempotent prepare with recovered ORIGINAL bytes,
    # rather than minting tomorrow's actor/date or a replacement fingerprint.
    assert private.prepare(lookup(),SCOPE,payload=recovered["private_payload"],trusted_recipe_fingerprint=FP,
        permission_binding_digest=STAMP)==ref
    assert private.read(lookup(),SCOPE,original_input=ref.to_dict(),trusted_recipe_fingerprint=FP,
        trusted_request_sha256=recovered["request_sha256"])==body
    assert runtime.store.list_events()==[] and runtime.jobs.list_jobs()==[] and adapter.spec is None


def test_lookup_original_rechecks_own_scope_and_authority_and_does_not_read_foreign(tmp_path):
    _,supervisor,_=empty_owner(tmp_path);private=ProjectSourceOriginalInput(supervisor)
    private.prepare(lookup(),SCOPE,payload=payload(),trusted_recipe_fingerprint=FP)
    assert private.lookup_original(lookup(),"9"*64,guard=lambda:True) is None
    calls=[]
    def guard():calls.append(True);return len(calls)<2
    with pytest.raises(PermissionError):private.lookup_original(lookup(),SCOPE,guard=guard)


def test_low_level_lookup_refuses_fifo_without_blocking_and_never_rewrites_it(tmp_path):
    import signal
    root=tmp_path/"runs";root.mkdir(mode=0o700)
    helper=TerminalOriginalInputArtifacts(root)
    ref=helper.prepare(command_id="original",issuer_scope_sha256=SCOPE,fingerprint_sha256=FP,payload=b"private")
    from control_plane.terminal_original_input_artifacts import _stable_key, PRIVATE_SUBDIR, ARTIFACT_FILENAME
    path=root/PRIVATE_SUBDIR/_stable_key("original",SCOPE)/ARTIFACT_FILENAME
    path.unlink();os.mkfifo(path,0o600);inode=path.lstat().st_ino
    def timeout(*_):raise AssertionError("private FIFO blocked")
    previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(2)
    try:
        with pytest.raises(TerminalInputError):helper.lookup_original(command_id="original",issuer_scope_sha256=SCOPE)
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    assert path.lstat().st_ino==inode
