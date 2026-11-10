"""Executable contracts for the source-plan view and incumbent native startup hook."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.session_bridge import project_task_context as ctx
from integrations.session_bridge import agentos_session_start as hook


def plan():
    tasks = []
    for i, deps in ((1, []), (2, ["P1.T1"]), (3, [])):
        tasks.append({"id": f"P1.T{i}", "title": f"Outcome {i}", "requirement_ids": [f"R{i}"],
                      "depends_on": deps, "state": "pending", "evidence": [],
                      "acceptance": [{"id": "A1", "text": f"Observe consumer outcome {i}"}]})
    return {"schema": ctx.SCHEMA, "workstream": "WS:FIXTURE", "objective": "Finish the whole project",
            "requirements": [{"id": f"R{i}", "text": f"Retain requirement {i}"} for i in (1, 2, 3)],
            "allowed_paths": ["integrations/session_bridge"],
            "non_goals": ["No replacement runtime, permission changes or unbounded loops"], "tasks": tasks}


def raw(value):
    return ("# Existing project plan\n\n```mastermind-plan\n" + json.dumps(value) + "\n```\n").encode()


def project(value):
    return ctx.project_plan(value, source_sha256=hashlib.sha256(raw(value)).hexdigest(),
                            source_path="docs/plans/fixture.md", workstream="WS:FIXTURE")


def mark_source_done(value, key):
    task = next(t for t in value["tasks"] if t["id"] == key)
    task["state"] = "done"
    task["evidence"] = [{"criterion_id": c["id"], "result": "pass",
                         "definition_sha256": ctx.definition_digests(value)[key],
                         "ref": "https://github.com/example/repo/commit/" + "a" * 40}
                        for c in task["acceptance"]]


def test_initial_projection_preserves_full_mission_and_one_focus():
    value = plan()
    result = project(value)
    assert result["objective"] == value["objective"]
    assert result["requirements"] == value["requirements"]
    assert result["non_goals"] == value["non_goals"]
    assert result["focus"]["id"] == "P1.T1"
    assert result["source_ready_ids"] == ["P1.T1", "P1.T3"]
    assert result["execution_authority"] is False
    assert result["mission_accepted"] == "UNOBSERVED"
    assert result["evidence_authentication"] == "NOT_PERFORMED"


def test_dependency_only_opens_after_fresh_complete_evidence_coverage():
    value = plan()
    value["tasks"][0]["state"] = "done"
    assert "P1.T2" not in project(value)["source_ready_ids"]
    mark_source_done(value, "P1.T1")
    assert project(value)["focus"]["id"] == "P1.T2"
    assert project(value)["source_complete_ids"] == ["P1.T1"]


def test_failed_or_partial_evidence_does_not_complete_task():
    value = plan()
    value["tasks"][0]["acceptance"].append({"id": "A2", "text": "Prove interruption recovery"})
    mark_source_done(value, "P1.T1")
    value["tasks"][0]["evidence"][1]["result"] = "fail"
    assert project(value)["focus"]["missing_or_stale_evidence"] == ["A2"]
    assert project(value)["source_complete_ids"] == []


def test_requirement_change_invalidates_only_affected_subgraph():
    value = plan()
    for task in value["tasks"]:
        mark_source_done(value, task["id"])
    old = copy.deepcopy(value)
    value["requirements"][0]["text"] = "Changed first requirement"
    result = project(value)
    assert result["source_complete_ids"] == ["P1.T3"]
    diff = ctx.compare_plans(old, value)
    assert diff["changed_task_ids"] == ["P1.T1", "P1.T2"]
    assert diff["unchanged_task_ids"] == ["P1.T3"]
    assert diff["scope_review_required"] is True


def test_completed_downstream_does_not_override_incomplete_ancestor():
    value = plan()
    mark_source_done(value, "P1.T2")
    assert "P1.T2" not in project(value)["source_complete_ids"]


def test_all_source_done_still_requires_parent_acceptance():
    value = plan()
    for task in value["tasks"]:
        mark_source_done(value, task["id"])
    result = project(value)
    assert result["next_action_kind"] == "REVIEW_PARENT_ACCEPTANCE"
    assert result["mission_accepted"] == "UNOBSERVED"
    assert result["focus"] is None


def test_blocked_lane_does_not_hide_independent_work():
    value = plan()
    value["tasks"][0].update(state="blocked", blocker="Waiting for exact permission")
    assert project(value)["focus"]["id"] == "P1.T3"
    assert project(value)["source_ready_ids"] == ["P1.T3"]


def test_active_task_is_preserved_and_dependency_conflict_is_explicit():
    value = plan()
    value["tasks"][1]["state"] = "in_progress"
    result = project(value)
    assert result["focus"]["id"] == "P1.T2"
    assert result["next_action_kind"] == "RECONCILE_ACTIVE_DEPENDENCIES"


def test_delegates_retain_original_receipts_without_becoming_new_focus():
    value = plan()
    value["tasks"][0].update(state="in_progress", execution_lane="delegated",
                             native_ref="runtime:t3:environment:project:thread:original-run")
    result = project(value)
    assert result["focus"]["id"] == "P1.T3"
    assert result["active_delegated_tasks"][0]["id"] == "P1.T1"
    assert result["active_delegated_tasks"][0]["native_ref"].endswith("original-run")


def test_all_remaining_work_blocked_returns_blocker_review():
    value = plan()
    for task in value["tasks"]:
        task.update(state="blocked", blocker="Exact external gate")
    assert project(value)["next_action_kind"] == "REVIEW_BLOCKERS"


def test_preferred_task_cannot_jump_dependency():
    value = plan()
    value["focus_task_id"] = "P1.T2"
    assert project(value)["focus"]["id"] == "P1.T1"


def test_task_state_change_does_not_invalidate_completed_definition():
    value = plan()
    before = ctx.definition_digests(value)
    value["tasks"][0]["state"] = "in_progress"
    value["tasks"][0]["next_action"] = "Run affected tests"
    assert ctx.definition_digests(value) == before


def test_scope_removal_is_reported_not_silently_accepted():
    before = plan()
    after = copy.deepcopy(before)
    after["requirements"].pop()
    after["tasks"].pop()
    after["scope_decision_ref"] = "agentos:decision:fixture"
    result = ctx.compare_plans(before, after)
    assert result["removed_requirement_ids"] == ["R3"]
    assert result["removed_task_ids"] == ["P1.T3"]
    assert result["decision_authentication"] == "NOT_PERFORMED"
    assert result["scope_review_required"] is True


@pytest.mark.parametrize("mutation,reason", [
    (lambda p: p.update(schema="future"), "SCHEMA_UNSUPPORTED"),
    (lambda p: p.update(extra="ignored scope"), "SHAPE_INVALID"),
    (lambda p: p.update(focus_task_id=[]), "FOCUS_UNKNOWN"),
    (lambda p: p["tasks"].append(copy.deepcopy(p["tasks"][0])), "DUPLICATE_TASK"),
    (lambda p: p["requirements"].append({"id": "R4", "text": "Lost requirement"}), "REQUIREMENT_UNCOVERED"),
    (lambda p: p["tasks"][0].update(depends_on=["P9.T9"]), "DEPENDENCY_INVALID"),
    (lambda p: p["tasks"][0].update(depends_on=["P1.T2"]), "DEPENDENCY_CYCLE"),
    (lambda p: p["tasks"][0].update(depends_on=["P1.T1"]), "DEPENDENCY_INVALID"),
    (lambda p: p["tasks"][0].update(state="blocked"), "BLOCKER_REQUIRED"),
    (lambda p: p["tasks"][0].update(state="running"), "STATE_INVALID"),
    (lambda p: p["tasks"][0].update(execution_lane="unknown"), "LANE_INVALID"),
    (lambda p: p["tasks"][0].update(state="in_progress", execution_lane="delegated"), "DELEGATE_REFERENCE_REQUIRED"),
    (lambda p: p.update(allowed_paths=["../secrets"]), "PATH_INVALID"),
    (lambda p: p.update(allowed_paths=["/tmp/project"]), "PATH_INVALID"),
    (lambda p: p["tasks"][0].update(requirement_ids=["R9"]), "REQUIREMENT_UNKNOWN"),
])
def test_invalid_task_tree_is_rejected(mutation, reason):
    value = plan()
    mutation(value)
    with pytest.raises(ctx.PlanContextError, match=reason):
        ctx.parse_plan(raw(value))


def test_multiple_principal_foci_rejected():
    value = plan()
    value["tasks"][0]["state"] = value["tasks"][2]["state"] = "in_progress"
    with pytest.raises(ctx.PlanContextError, match="MULTIPLE_PRINCIPAL_FOCI"):
        project(value)


@pytest.mark.parametrize("content,reason", [
    (b"# No structured block", "BLOCK_COUNT"),
    (raw(plan()) + raw(plan()), "BLOCK_COUNT"),
    (b"```mastermind-plan\n{broken}\n```", "PARSE_INVALID"),
    (b'```mastermind-plan\n{"a":1,"a":2}\n```', "DUPLICATE_KEY"),
    (b'```mastermind-plan\n{"a":NaN}\n```', "NONFINITE"),
    (b"x" * (ctx.MAX_PLAN_BYTES + 1), "SIZE_INVALID"),
])
def test_malformed_input_fails_explicitly(content, reason):
    with pytest.raises(ctx.PlanContextError, match=reason):
        ctx.parse_plan(content)


@pytest.mark.parametrize("ref", ["file:///etc/passwd", "https://github.com/example/repo/blob/main/a.md",
    "https://example.com/proof", "https://user:password@github.com/a/b/issues/1",
    "https://github.com/a/b/issues/1?token=secret", "runtime:bad\ncommand"])
def test_unsafe_or_floating_evidence_refs_rejected(ref):
    value = plan()
    mark_source_done(value, "P1.T1")
    value["tasks"][0]["evidence"][0]["ref"] = ref
    with pytest.raises(ctx.PlanContextError, match="EVIDENCE_REF_INVALID"):
        project(value)


@pytest.fixture
def plan_file(tmp_path):
    root = tmp_path / "assigned workspace"
    path = root / "docs/plans/fixture.md"
    path.parent.mkdir(parents=True)
    content = raw(plan())
    path.write_bytes(content)
    return root, path, hashlib.sha256(content).hexdigest()


def test_exact_file_read_and_cli_leave_source_unchanged(plan_file):
    root, path, digest = plan_file
    before = path.read_bytes()
    result = subprocess.run([sys.executable, "-m", "integrations.session_bridge.project_task_context",
        "--workspace-root", str(root), "--plan-path", "docs/plans/fixture.md", "--plan-sha256", digest,
        "--workstream", "WS:FIXTURE"], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["source_sha256"] == digest
    assert path.read_bytes() == before
    assert not result.stderr


def test_stale_plan_sha_refuses_new_unreviewed_scope(plan_file):
    root, path, digest = plan_file
    path.write_bytes(path.read_bytes() + b"\nChanged scope\n")
    with pytest.raises(ctx.PlanContextError, match="REVISION_CHANGED"):
        ctx.load_context(workspace_root=root, relative_path="docs/plans/fixture.md",
                         expected_sha256=digest, workstream="WS:FIXTURE")


@pytest.mark.parametrize("relative", ["../fixture.md", "/tmp/fixture.md", ".env", "docs/plans/../fixture.md"])
def test_no_arbitrary_path_reads(plan_file, relative):
    root, _, digest = plan_file
    with pytest.raises(ctx.PlanContextError, match="PATH_INVALID"):
        ctx.read_plan(root, relative, digest)


def test_symlink_plan_not_followed(plan_file):
    root, path, digest = plan_file
    real = path.with_name("real.md")
    path.rename(real)
    path.symlink_to(real)
    with pytest.raises(ctx.PlanContextError, match="READ_UNAVAILABLE"):
        ctx.read_plan(root, "docs/plans/fixture.md", digest)


def test_symlink_parent_not_followed(plan_file):
    root, path, digest = plan_file
    directory = path.parent
    real = directory.with_name("real")
    directory.rename(real)
    directory.symlink_to(real)
    with pytest.raises(ctx.PlanContextError, match="READ_UNAVAILABLE"):
        ctx.read_plan(root, "docs/plans/fixture.md", digest)


def test_wrong_workstream_cannot_inject_neighbor_plan(plan_file):
    root, _, digest = plan_file
    with pytest.raises(ctx.PlanContextError, match="WORKSTREAM_MISMATCH"):
        ctx.load_context(workspace_root=root, relative_path="docs/plans/fixture.md",
                         expected_sha256=digest, workstream="WS:OTHER")


def test_large_context_is_explicit_not_truncated():
    value = plan()
    value["requirements"][0]["text"] = "a" * 4096
    for i in range(4, 35):
        task = copy.deepcopy(value["tasks"][0])
        task.update(id=f"P1.T{i}", title="x" * 512)
        value["tasks"].append(task)
    with pytest.raises(ctx.PlanContextError, match="CONTEXT_TOO_LARGE"):
        project(value)


def owner_reader(workstream, budget, *, owner_root):
    bundle = {"schema": "context_bundle.v1", "target": {"workstream": workstream},
              "no_answer_reason": None, "sections": [{"id": "workstream", "items": [
                  "Accepted: preserve phase zero", "Next: finish entire project"]}],
              "degraded": [], "excluded": [], "omitted_due_to_budget": []}
    data = json.dumps(bundle).encode()
    return data, {"workstream": workstream, "bundle_sha256": hashlib.sha256(data).hexdigest(),
                  "execution_authority": False}


@pytest.mark.parametrize("source", ["startup", "compact", "resume", "clear", "fork"])
def test_incumbent_hook_consumes_plan_without_adding_runtime_owner(plan_file, source):
    root, _, digest = plan_file
    event = {"hook_event_name": "SessionStart", "source": source,
             "session_id": "native-original", "cwd": str(root)}
    result = hook.session_start_context(event, workspace_root=root, owner_root=root,
        workstream="WS:FIXTURE", reader=owner_reader,
        plan_path="docs/plans/fixture.md", plan_sha256=digest)
    text = result["hookSpecificOutput"]["additionalContext"]
    assert "Accepted: preserve phase zero" in text
    assert "Retain requirement 1" in text and "Retain requirement 3" in text
    assert '"execution_authority":false' in text
    assert '"mission_accepted":"UNOBSERVED"' in text
    assert '"task_detail_scope":"FULL_FOCUS; OFF_FOCUS_ACCEPTANCE_AT_EXACT_SOURCE"' in text
    assert len(text.encode()) <= hook.MAX_CONTEXT_BYTES


def test_stale_hook_binding_reports_gap_without_silently_rebinding(plan_file):
    root, _, _ = plan_file
    event = {"hook_event_name": "SessionStart", "source": "compact",
             "session_id": "native-original", "cwd": str(root)}
    text = hook.session_start_context(event, workspace_root=root, owner_root=root,
        workstream="WS:FIXTURE", reader=owner_reader, plan_path="docs/plans/fixture.md",
        plan_sha256="0" * 64)["hookSpecificOutput"]["additionalContext"]
    assert "PLAN_REVISION_CHANGED" in text
    assert "Retain requirement" not in text
    assert "Accepted: preserve phase zero" in text


def test_sibling_workspace_cannot_load_plan(plan_file, tmp_path):
    root, _, digest = plan_file
    event = {"hook_event_name": "SessionStart", "source": "resume", "session_id": "other", "cwd": str(tmp_path)}
    assert hook.session_start_context(event, workspace_root=root, owner_root=root,
        workstream="WS:FIXTURE", reader=owner_reader, plan_path="docs/plans/fixture.md",
        plan_sha256=digest) == {}


def test_cli_missing_revision_returns_typed_error_not_stack_trace(plan_file):
    root, _, _ = plan_file
    out, err = io.StringIO(), io.StringIO()
    code = ctx.main(["--workspace-root", str(root), "--plan-path", "docs/plans/fixture.md",
                     "--plan-sha256", "missing", "--workstream", "WS:FIXTURE"], stdout=out, stderr=err)
    assert code == 2 and out.getvalue() == ""
    assert err.getvalue() == "PLAN_EXPECTED_DIGEST_REQUIRED\n"


def test_contract_binding_survives_status_evidence_and_prose_saves(plan_file):
    root, path, _ = plan_file
    value = plan()
    contract = ctx.contract_digest(value)
    mark_source_done(value, "P1.T1")
    value["focus_task_id"] = "P1.T2"
    path.write_bytes(raw(value) + b"\nObserved progress, not a new requirement.\n")
    result = ctx.load_context(workspace_root=root, relative_path="docs/plans/fixture.md",
        expected_contract_sha256=contract, workstream="WS:FIXTURE")
    assert result["focus"]["id"] == "P1.T2"
    assert result["source_binding"] == "MATCHED_CONTRACT_CURRENT_PROGRESS"
    assert result["contract_sha256"] == contract
    assert result["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_changed_scope_rejected_by_stable_contract(plan_file):
    root, path, _ = plan_file
    value = plan()
    contract = ctx.contract_digest(value)
    value["requirements"][0]["text"] = "Newly added behavior"
    path.write_bytes(raw(value))
    with pytest.raises(ctx.PlanContextError, match="CONTRACT_CHANGED"):
        ctx.read_plan(root, "docs/plans/fixture.md", expected_contract_sha256=contract)


def test_ambiguous_double_binding_rejected(plan_file):
    root, _, digest = plan_file
    with pytest.raises(ctx.PlanContextError, match="EXPECTED_DIGEST_REQUIRED"):
        ctx.read_plan(root, "docs/plans/fixture.md", digest,
                      expected_contract_sha256=ctx.contract_digest(plan()))


def test_native_compact_hook_reads_latest_progress_under_same_contract(plan_file):
    root, path, _ = plan_file
    value = plan()
    contract = ctx.contract_digest(value)
    mark_source_done(value, "P1.T1")
    path.write_bytes(raw(value))
    event = {"hook_event_name": "SessionStart", "source": "compact",
             "session_id": "original", "cwd": str(root)}
    text = hook.session_start_context(event, workspace_root=root, owner_root=root,
        workstream="WS:FIXTURE", reader=owner_reader, plan_path="docs/plans/fixture.md",
        plan_contract_sha256=contract)["hookSpecificOutput"]["additionalContext"]
    assert '"source_complete_ids":["P1.T1"]' in text
    assert "MATCHED_CONTRACT_CURRENT_PROGRESS" in text
    assert "Retain requirement 3" in text


def test_downstream_row_completion_matches_dependency_closure():
    value = plan()
    mark_source_done(value, "P1.T2")
    result = project(value)
    assert result["task_tree"][1]["source_complete"] is False


def test_nonregular_file_cannot_hang_reader(plan_file):
    import os
    root, path, digest = plan_file
    path.unlink()
    os.mkfifo(path)
    result = subprocess.run([sys.executable, "-m", "integrations.session_bridge.project_task_context",
        "--workspace-root", str(root), "--plan-path", "docs/plans/fixture.md",
        "--plan-sha256", digest, "--workstream", "WS:FIXTURE"],
        capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert "PLAN_FILE_INVALID" in result.stderr


def test_invalid_unicode_is_typed_error():
    value = plan()
    value["objective"] = chr(0xd800)
    with pytest.raises(ctx.PlanContextError, match="TEXT_INVALID"):
        ctx.parse_plan(raw(value))


def test_contract_digest_validates_public_input():
    with pytest.raises(ctx.PlanContextError, match="SHAPE_INVALID"):
        ctx.contract_digest({})


@pytest.mark.parametrize("mutation", [
    lambda p: p["tasks"][0]["acceptance"][0].update(text="Changed acceptance"),
    lambda p: p["tasks"][1].update(depends_on=[]),
    lambda p: p["tasks"][0].update(title="Changed outcome"),
])
def test_task_contract_change_requires_scope_review(mutation):
    before = plan()
    after = copy.deepcopy(before)
    mutation(after)
    assert ctx.compare_plans(before, after)["scope_review_required"] is True


def test_progress_does_not_require_scope_reapproval():
    before = plan()
    after = copy.deepcopy(before)
    mark_source_done(after, "P1.T1")
    assert ctx.compare_plans(before, after)["scope_review_required"] is False


def test_missing_optional_plan_preserves_incumbent_context(plan_file):
    root, path, digest = plan_file
    path.unlink()
    event = {"hook_event_name": "SessionStart", "source": "resume",
             "session_id": "native-original", "cwd": str(root)}
    text = hook.session_start_context(event, workspace_root=root, owner_root=root,
        workstream="WS:FIXTURE", reader=owner_reader, plan_path="docs/plans/fixture.md",
        plan_sha256=digest)["hookSpecificOutput"]["additionalContext"]
    assert "PLAN_READ_UNAVAILABLE" in text
    assert "Accepted: preserve phase zero" in text
    assert len(text.encode()) <= hook.MAX_CONTEXT_BYTES
