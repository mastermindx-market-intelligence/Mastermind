"""Closed pool-policy candidate authoring; no installed policy or provider use."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ops.native_fabric.quota_continuity import policy_change as policy
from ops.native_fabric.quota_continuity import policy_edit as edit


def raw(value):
    return json.dumps(value, sort_keys=True).encode()


def source():
    return {"schema": "fixture-policy", "routing": {"execute_order": ["glm", "grok"]},
            "pools": {"glm": {"model": "original-model", "enabled": False},
                      "grok": {"windows": {"weekly": {"limit": 100, "remaining_pct": 50}}}},
            "retained": {"source": "fixture", "limits": [1, 2, 3]}}


def edits():
    return {"schema": edit.EDITS_SCHEMA,
            "pool_upserts": {"glm": {"model": "candidate-model", "enabled": False}}}


def digest(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def files(tmp_path):
    inputs = tmp_path / "policy_inputs"
    outputs = tmp_path / "policy_candidates"
    inputs.mkdir(mode=0o700)
    outputs.mkdir(mode=0o700)
    current, changes = inputs / "policy.yaml", inputs / "edit.json"
    current.write_bytes(raw(source()))
    changes.write_bytes(raw(edits()))
    return current, changes, outputs / "candidate.json"


def stage(files):
    current, changes, output = files
    return edit.stage_edit(current, changes, output,
                           expected_source_sha256=digest(current.read_bytes()))


def test_proposal_preserves_untouched_semantics_and_keeps_qualification_explicit():
    original = source()
    request = edits()
    request["pool_upserts"]["candidate-pool"] = {"model": "new-model", "enabled": False}
    candidate, preview = edit.propose_edit(raw(original), raw(request),
                                           expected_source_sha256=digest(raw(original)))
    proposed = json.loads(candidate)
    assert proposed["retained"] == original["retained"]
    assert proposed["routing"] == original["routing"]
    assert proposed["pools"]["grok"] == original["pools"]["grok"]
    assert proposed["pools"]["glm"]["model"] == "candidate-model"
    assert preview["changes"]["pools"] == {"added": ["candidate-pool"], "removed": [], "changed": ["glm"]}
    assert "QUALIFY_ADDED_POOLS_AND_MODELS" in preview["requirements"]
    assert preview["activation_authorized"] is False
    assert original == source()


def test_explicit_remove_and_routing_replacement_do_not_leave_hidden_old_values():
    request = {"schema": edit.EDITS_SCHEMA, "pool_removals": ["glm"],
               "routing": {"execute_order": ["grok"]}}
    candidate, preview = edit.propose_edit(raw(source()), raw(request),
                                           expected_source_sha256=digest(raw(source())))
    assert set(json.loads(candidate)["pools"]) == {"grok"}
    assert json.loads(candidate)["routing"] == request["routing"]
    assert preview["changes"]["routing_changed"] is True
    assert "DRAIN_OR_RETAIN_ACTIVE_BINDINGS" in preview["requirements"]


@pytest.mark.parametrize("change_set", [
    {}, {"schema": "wrong"}, {"schema": edit.EDITS_SCHEMA, "enable_now": True},
    {"schema": edit.EDITS_SCHEMA, "pool_removals": ["glm", "glm"]},
    {"schema": edit.EDITS_SCHEMA, "pool_removals": [{}]},
    {"schema": edit.EDITS_SCHEMA, "pool_removals": ["glm"], "pool_upserts": {"glm": {}}},
    {"schema": edit.EDITS_SCHEMA, "pool_upserts": {"../secret": {}}},
    {"schema": edit.EDITS_SCHEMA, "pool_upserts": {"glm": False}},
    {"schema": edit.EDITS_SCHEMA, "routing": []},
])
def test_closed_edit_schema_rejects_ambiguous_or_unknown_operations(change_set):
    with pytest.raises(policy.PolicyChangeError):
        edit.parse_edits(raw(change_set))


@pytest.mark.parametrize("value", [b'{"schema":"one","schema":"two"}', b'{"x":NaN}',
    b'{"x":1e999}', b'{"x":"\\ud800"}', b"\xff", b"[]", b"{}" * 200000,
    b'{"x":' + b"[" * 30 + b"0" + b"]" * 30 + b"}"])
def test_bounded_strict_json_edits(value):
    with pytest.raises(policy.PolicyChangeError):
        edit.parse_edits(value)


def test_noop_unknown_removal_and_stale_parent_are_refused():
    for request, code in [({"schema": edit.EDITS_SCHEMA}, "POLICY_EDITS_NO_CHANGE"),
                          ({"schema": edit.EDITS_SCHEMA, "pool_removals": ["missing"]},
                           "POLICY_REMOVE_UNKNOWN_POOL")]:
        with pytest.raises(policy.PolicyChangeError, match=code):
            edit.propose_edit(raw(source()), raw(request), expected_source_sha256=digest(raw(source())))
    with pytest.raises(policy.PolicyChangeError, match="EXPECTED_SOURCE_REVISION_CHANGED"):
        edit.propose_edit(raw(source()), raw(edits()), expected_source_sha256="f" * 64)


def test_known_credential_material_never_creates_an_artifact(files):
    current, changes, output = files
    request = edits()
    request["pool_upserts"]["glm"]["api_key"] = "synthetic-private-key"
    changes.write_bytes(raw(request))
    with pytest.raises(policy.PolicyChangeError, match="CREDENTIAL_MATERIAL_REFUSED"):
        stage(files)
    assert list(output.parent.iterdir()) == []
    assert current.read_bytes() == raw(source())


def test_stage_is_exclusive_private_and_preserves_input_bytes(files):
    current, changes, output = files
    original = current.read_bytes(), changes.read_bytes()
    result = stage(files)
    assert result["state"] == "STAGED" and result["candidate_written"] is True
    assert result["live_policy_changed"] is False and result["activation_authorized"] is False
    assert result["replay_authorized"] is False
    assert (current.read_bytes(), changes.read_bytes()) == original
    assert list(output.parent.iterdir()) == [output]
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_nlink == 1
    assert digest(output.read_bytes()) == result["candidate_source_sha256"]
    with pytest.raises(policy.PolicyChangeError, match="CANDIDATE_DESTINATION_OCCUPIED"):
        stage(files)
    readback = edit.verify_candidate(output, expected_candidate_sha256=result["candidate_source_sha256"])
    assert readback["state"] == "ARTIFACT_PRESENT_VERIFIED"
    assert readback["candidate_written"] is False
    assert readback["original_stage_success_proven"] is False


@pytest.mark.parametrize("target_kind", ["file", "symlink", "directory"])
def test_existing_destination_is_never_replaced(files, target_kind):
    current, changes, output = files
    if target_kind == "file":
        output.write_bytes(b"outside-owner")
    elif target_kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(current)
    before = output.lstat()
    with pytest.raises(policy.PolicyChangeError, match="CANDIDATE_DESTINATION_OCCUPIED"):
        stage(files)
    assert output.lstat().st_ino == before.st_ino
    assert current.read_bytes() == raw(source())
    assert len(list(output.parent.iterdir())) == 1


def test_public_or_symlink_parent_and_live_source_directory_are_refused(files):
    current, changes, output = files
    output.parent.chmod(0o755)
    with pytest.raises(policy.PolicyChangeError, match="CANDIDATE_DIRECTORY_NOT_PRIVATE"):
        stage(files)
    output.parent.chmod(0o700)
    alias = output.parent.parent / "alias"
    alias.symlink_to(output.parent, target_is_directory=True)
    for destination in (alias / "candidate", current.parent / "candidate"):
        with pytest.raises(policy.PolicyChangeError, match="CANDIDATE_DESTINATION_INVALID"):
            edit.stage_edit(current, changes, destination, expected_source_sha256=digest(current.read_bytes()))
    assert not output.exists()


@pytest.mark.parametrize("moving", [0, 1])
def test_source_or_edit_drift_before_publication_refuses_and_cleans_own_stage(files, monkeypatch, moving):
    original = policy._require_current
    changed = False
    def recheck(item):
        nonlocal changed
        if not changed:
            files[moving].write_bytes(files[moving].read_bytes() + b"\n")
            changed = True
        return original(item)
    monkeypatch.setattr(policy, "_require_current", recheck)
    with pytest.raises(policy.PolicyChangeError, match="POLICY_SOURCE_CHANGED"):
        stage(files)
    assert list(files[2].parent.iterdir()) == []


def test_no_replace_race_keeps_competing_destination(files, monkeypatch):
    def competing(*args, **kwargs):
        files[2].write_bytes(b"another-writer")
        raise FileExistsError()
    monkeypatch.setattr(edit.os, "link", competing)
    with pytest.raises(policy.PolicyChangeError, match="CANDIDATE_DESTINATION_OCCUPIED"):
        stage(files)
    assert files[2].read_bytes() == b"another-writer"
    assert list(files[2].parent.iterdir()) == [files[2]]


def test_lost_link_ack_retains_exact_candidate_and_forbids_replay(files, monkeypatch):
    original = os.link
    def lost(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("PRIVATE_PATH_CANARY")
    monkeypatch.setattr(edit.os, "link", lost)
    with pytest.raises(edit.CandidatePublicationUnknown) as raised:
        stage(files)
    assert "PRIVATE_PATH_CANARY" not in str(raised.value)
    assert files[2].is_file()
    assert list(files[2].parent.iterdir()) == [files[2]]
    result = edit.verify_candidate(files[2], expected_candidate_sha256=raised.value.candidate_sha256)
    assert result["state"] == "ARTIFACT_PRESENT_VERIFIED" and result["replay_authorized"] is False


def test_readback_failure_after_publication_preserves_unknown_original(files, monkeypatch):
    original = policy._read_source
    def fail_read(path):
        if Path(path) == files[2]:
            raise policy.PolicyChangeError("SOURCE_UNAVAILABLE")
        return original(path)
    monkeypatch.setattr(policy, "_read_source", fail_read)
    with pytest.raises(edit.CandidatePublicationUnknown):
        stage(files)
    assert files[2].exists()
    assert list(files[2].parent.iterdir()) == [files[2]]


def test_cli_module_composes_without_duplicate_error_classes_or_path_leaks(files):
    current, changes, output = files
    command = [sys.executable, "-B", "-m", "ops.native_fabric.quota_continuity.policy_change",
               "stage", "--policy", str(current), "--edits", str(changes),
               "--output", str(output), "--expected-source-sha256", digest(current.read_bytes())]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["state"] == "STAGED"
    again = subprocess.run(command, capture_output=True, text=True, check=False)
    assert again.returncode == 2 and not again.stderr
    refusal = json.loads(again.stdout)
    assert refusal["code"] == "CANDIDATE_DESTINATION_OCCUPIED"
    assert str(output) not in again.stdout
    verified = subprocess.run([sys.executable, "-B", "-m", "ops.native_fabric.quota_continuity.policy_change",
        "verify-candidate", "--candidate", str(output),
        "--expected-candidate-sha256", receipt["candidate_source_sha256"]], capture_output=True, text=True)
    assert verified.returncode == 0
    assert json.loads(verified.stdout)["state"] == "ARTIFACT_PRESENT_VERIFIED"


def model_source():
    value = source()
    value["pools"]["glm"].update(models={"executor": "fast", "reviewer": "deep"},
        model_capabilities={"fast": ["text"], "deep": ["text", "tools"]})
    return value


def test_model_assignment_preserves_other_roles_limits_and_capability_definitions():
    value = model_source()
    request = {"schema": edit.EDITS_SCHEMA, "model_assignments": {"glm": {"executor": "deep"}}}
    candidate, preview = edit.propose_edit(raw(value), raw(request), expected_source_sha256=digest(raw(value)))
    updated = json.loads(candidate)
    assert updated["pools"]["glm"]["models"] == {"executor": "deep", "reviewer": "deep"}
    assert updated["pools"]["glm"]["model_capabilities"] == value["pools"]["glm"]["model_capabilities"]
    assert updated["pools"]["glm"]["enabled"] is False
    assert updated["pools"]["grok"] == value["pools"]["grok"]
    assert preview["status"] == "CRITICAL_POLICY_CHANGE" and preview["activation_authorized"] is False


@pytest.mark.parametrize("assignment,code", [
    ({"missing": {"executor": "deep"}}, "POLICY_MODEL_POOL_UNKNOWN"),
    ({"grok": {"executor": "deep"}}, "POLICY_MODEL_MAP_UNAVAILABLE"),
    ({"glm": {"unknown-role": "deep"}}, "POLICY_MODEL_ROLE_UNKNOWN"),
    ({"glm": {"executor": "unknown-model"}}, "POLICY_MODEL_CAPABILITY_UNKNOWN"),
    ({"glm": {"executor": 1}}, "POLICY_MODEL_ASSIGNMENT_INVALID"),
    ({"glm": {}}, "POLICY_MODEL_ASSIGNMENT_INVALID"),
])
def test_unknown_pool_role_or_model_is_not_an_implicit_grant(assignment, code):
    value = model_source()
    request = {"schema": edit.EDITS_SCHEMA, "model_assignments": assignment}
    with pytest.raises(policy.PolicyChangeError, match=code):
        edit.propose_edit(raw(value), raw(request), expected_source_sha256=digest(raw(value)))


def test_pool_replacement_and_model_assignment_cannot_ambiguously_target_same_pool():
    request = edits()
    request["model_assignments"] = {"glm": {"executor": "deep"}}
    with pytest.raises(policy.PolicyChangeError, match="POLICY_MODEL_ASSIGNMENT_INVALID"):
        edit.parse_edits(raw(request))
