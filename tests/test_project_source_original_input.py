"""Actual accepted Supervisor artifact owner with source-specific private codec."""
import hashlib
import json
import pytest

from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.terminal_original_input_artifacts import TerminalInputError
from tests.test_terminal_original_input_supervisor import empty_owner
from tests.test_workspace_source_operations import lookup, SCOPE, FP


def material():
    return {"schema": "mastermind.project_source_original_input.v1", "action": "ADOPT_PLAN",
            "request": {"request_id": lookup()["request_id"], "work_ref": "WS:TEST", "value": "原文"},
            "actor": {"decided_at": "2026-11-04", "rationale": "private-rationale-canary"},
            "initial_snapshot": {"raw_bytes": b"---\r\n\xff\x00Exact original bytes\r\n"},
            "source_binding": {"commit": "a" * 40}}


def request_hash(payload):
    return hashlib.sha256(json.dumps(payload["request"], sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_actual_custody_roundtrip_original_binary_and_day_without_job_or_public_private_bytes(tmp_path):
    runtime, supervisor, adapter = empty_owner(tmp_path)
    owner = ProjectSourceOriginalInput(supervisor)
    original = material()
    ref = owner.prepare(lookup(), SCOPE, payload=original, trusted_recipe_fingerprint=FP).to_dict()
    restored = owner.read(lookup(), SCOPE, original_input=ref, trusted_recipe_fingerprint=FP,
                          trusted_request_sha256=request_hash(original))
    assert restored == original
    assert "private-rationale-canary" not in json.dumps(ref)
    assert runtime.store.list_events() == [] and runtime.jobs.list_jobs() == [] and adapter.spec is None
    assert owner.prepare(lookup(), SCOPE, payload=original, trusted_recipe_fingerprint=FP).to_dict() == ref
    original["actor"]["decided_at"] = "2026-11-05"
    with pytest.raises(TerminalInputError):
        owner.prepare(lookup(), SCOPE, payload=original, trusted_recipe_fingerprint=FP)


@pytest.mark.parametrize("change", ["scope", "request", "fingerprint", "artifact"])
def test_committed_original_binding_is_mandatory_for_private_read(tmp_path, change):
    _, supervisor, _ = empty_owner(tmp_path)
    owner = ProjectSourceOriginalInput(supervisor)
    value = material()
    ref = owner.prepare(lookup(), SCOPE, payload=value, trusted_recipe_fingerprint=FP).to_dict()
    scope, fp, sha = SCOPE, FP, request_hash(value)
    if change == "scope": scope = "8" * 64
    if change == "fingerprint": fp = "8" * 64
    if change == "request": sha = "8" * 64
    if change == "artifact": ref["artifact_sha256"] = "8" * 64
    with pytest.raises((TerminalInputError, ValueError)):
        owner.read(lookup(), scope, original_input=ref, trusted_recipe_fingerprint=fp,
                   trusted_request_sha256=sha)


def test_existing_256kib_budget_is_not_enlarged(tmp_path):
    runtime, supervisor, _ = empty_owner(tmp_path)
    owner = ProjectSourceOriginalInput(supervisor)
    value = material()
    value["initial_snapshot"]["raw_bytes"] = b"x" * (256 * 1024)
    with pytest.raises(ValueError):
        owner.prepare(lookup(), SCOPE, payload=value, trusted_recipe_fingerprint=FP)
    assert not supervisor.runs_root.exists() and runtime.store.list_events() == []


def test_custom_values_do_not_run_serialization_hooks_or_touch_filesystem(tmp_path):
    _, supervisor, _ = empty_owner(tmp_path)
    owner = ProjectSourceOriginalInput(supervisor)
    class Forbidden(dict):
        def items(self): pytest.fail("custom items invoked")
    value = material()
    value["actor"] = Forbidden()
    with pytest.raises(ValueError):
        owner.prepare(lookup(), SCOPE, payload=value, trusted_recipe_fingerprint=FP)
    assert not supervisor.runs_root.exists()
