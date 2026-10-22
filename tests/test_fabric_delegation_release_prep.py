"""Adversarial tests for PR #1694's offline native-release and canary gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ops.native_fabric.delegation_access import qualify_release as release
from ops.native_fabric.delegation_access import canary_receipts as canary

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    temp = tmp_path_factory.mktemp("delegation-immutable")
    stage = temp / "reviewed"
    cmd = [sys.executable, str(ROOT / "ops/native_fabric/quota_continuity/rollout/build_review_stage.py"),
           "--output", str(stage)]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr[-1200:]
    baseline = json.loads((stage / "native-manifest.json").read_text())
    assert len(baseline) == 85
    prior = ROOT / "ops/native_fabric/grok47/overlay/fabric_operator_client.py"
    selected = prior.read_bytes()
    assert b"('grok', 'grok-4.7')" in selected
    native_stage = stage / "native-code-stage"
    inst = native_stage / release.OPERATOR
    inst.write_bytes(selected)
    baseline[release.OPERATOR] = release.sha(selected)
    # Only explicit code hashes are published; the stage metadata is not copied.
    fake_ext = temp / "kit" / "ext"
    fake_ext.mkdir(parents=True)
    prior_dir = release.generation.publish(native_stage, fake_ext, baseline)
    store = fake_ext.parent / "native-code-releases"
    selected_pointer = release.generation.select(store, prior_dir.name, None)
    assert selected_pointer["sequence"] == 1
    assert release.sha(prior_dir.joinpath(release.OPERATOR).read_bytes()) == release.sha(selected)
    x, y = release.instruction_span(selected)
    more = (
        b"\nStart with fabric_operator_scope; fabric_child_request once with "
        b"mastermind.fabric_operator_child_request.v1, then fabric_child_status, "
        b"fabric_child_result and fabric_child_acknowledge.\n"
    )
    candidate = selected[:y-len(release.END)] + more + selected[y-len(release.END):]
    assert release.instruction_span(candidate)
    assert candidate != selected
    cfile = temp / "candidate.py"
    cfile.write_bytes(candidate)
    return {"store": store, "generation": prior_dir.name, "candidate": cfile,
            "candidate_sha": release.sha(candidate), "selected_bytes": selected,
            "temp": temp}


def _qualify(installed, **kwargs):
    return release.qualify(
        installed["store"], installed["candidate"], installed["generation"],
        expected_candidate_sha=installed["candidate_sha"], **kwargs)


def test_offline_immutable_85_file_cas_and_only_operator_change(installed):
    before = (installed["store"] / "CURRENT.json").read_bytes()
    record = _qualify(installed)
    assert record["state"] == "QUALIFIED_ISOLATED_ONLY"
    assert record["native_file_count"] == 85
    assert record["changed_files"] == ["ext/fabric_operator_client.py"]
    assert record["scratch_published_and_verified"]
    assert record["scratch_stale_cas_refused"]
    assert not record["live_published"] and not record["live_selected"]
    assert not record["live_canaries_proven"]
    assert (installed["store"] / "CURRENT.json").read_bytes() == before


def test_rejects_stale_selected_generation(installed):
    with pytest.raises(release.QualificationRefused, match="selected generation differs"):
        release.qualify(installed["store"], installed["candidate"], "a"*64,
                        expected_candidate_sha=installed["candidate_sha"])


def test_rejects_unreviewed_or_mutated_operator(installed, tmp_path):
    with pytest.raises(release.QualificationRefused, match="unreviewed candidate"):
        release.qualify(installed["store"], installed["candidate"], installed["generation"])
    swapped = tmp_path / "candidate.py"
    swapped.write_bytes(installed["candidate"].read_bytes() + b"\n# unreviewed\n")
    with pytest.raises(release.QualificationRefused, match="unreviewed candidate"):
        release.qualify(installed["store"], swapped, installed["generation"],
                        expected_candidate_sha=installed["candidate_sha"])


def test_rejects_symlinked_candidate(installed, tmp_path):
    sym = tmp_path / "candidate.py"
    sym.symlink_to(installed["candidate"])
    with pytest.raises(release.QualificationRefused, match="symlinked source"):
        release.qualify(installed["store"], sym, installed["generation"],
                        expected_candidate_sha=installed["candidate_sha"])


def test_only_instruction_literal_mutates_and_protected_operator_binding_remains(installed):
    result = release.compose_instructions(installed["selected_bytes"],
                                           installed["candidate"].read_bytes())
    a, b = release.instruction_span(installed["selected_bytes"])
    c, d = release.instruction_span(result)
    assert result[:c] == installed["selected_bytes"][:a]
    assert result[d:] == installed["selected_bytes"][b:]
    assert b"('grok', 'grok-4.7')" in result
    old = installed["selected_bytes"].replace(b"('grok', 'grok-4.7')", b"('grok', 'grok-4.8')")
    with pytest.raises(release.QualificationRefused, match="Grok 4.7 binding"):
        release.compose_instructions(old, installed["candidate"].read_bytes())


def test_refuses_stage_without_protected_merge_proof(installed, tmp_path):
    with pytest.raises(release.QualificationRefused, match="staging requires"):
        _qualify(installed, stage_dir=tmp_path / "stage", stage_parent=tmp_path)


def test_staging_is_new_sibling_and_never_selects_live_generation(installed, tmp_path, monkeypatch):
    parent = tmp_path / "workspaces"
    parent.mkdir()
    target = parent / "operator-delegation-release"
    before = (installed["store"] / "CURRENT.json").read_bytes()
    # Synthetic merged-provenance only for the TEST, not a release assertion.
    monkeypatch.setattr(release, "_verify_merged_source", lambda repo, ref, raw: "e"*40)
    record = _qualify(installed, stage_dir=target, stage_parent=parent,
                      merged_repo=ROOT, merged_ref="synthetic-test")
    assert record["review_stage"] == str(target)
    assert record["protected_merged_source_sha"] == "e"*40
    assert json.loads((target / "qualification.json").read_text())["protected_merged_source_sha"] == "e"*40
    manifest = json.loads((target / "manifest.json").read_text())
    assert len(manifest) == 85
    for name, digest in manifest.items():
        assert hashlib.sha256((target / "source" / name).read_bytes()).hexdigest() == digest
    assert (installed["store"] / "CURRENT.json").read_bytes() == before
    with pytest.raises(release.QualificationRefused, match="fresh approved sibling"):
        _qualify(installed, stage_dir=target, stage_parent=parent,
                 merged_repo=ROOT, merged_ref="synthetic-test")


def _run(run_id: str, parent: str, root: str, generation: str, *, answer: str = "verified returned result") -> dict:
    sha = "b" * 64
    return {
        "run_id": run_id,
        "start_receipt": {"state": "STARTED", "run_id": run_id,
                          "root_id": root, "parent_run_id": parent,
                          "host": "ubuntu2", "support_sha256": "a"*64},
        "status": {
            "schema": "mastermind.fabric_mcp.v1", "action": "fabric_status",
            "root_verified": True,
            "status": {"run_id": run_id, "parent_run_id": parent,
                       "root_id": root, "state": "TERMINAL", "rc": 0,
                       "result_available": True},
        },
        "result": {"root_id": root, "accept_run_id": run_id,
                   "response_sha256": sha, "response_bytes": 35,
                   "adapter_response": answer},
        "parent_return": {"run_id": run_id, "principal_parent_id": parent,
                          "result_sha256": sha, "reviewed": True},
        "acceptance": {"accepted": True, "accepted_by": "reviewer",
                       "reviewed_response_sha256": sha},
        "observed_generation": generation,
    }


def _valid_receipts() -> dict:
    claude_root, codex_root, operator_root = "claude-root", "codex-root", "operator-root"
    claude_parent, codex_parent, operator_parent = "claude-session", "codex-thread", "principal-thread"
    generation = "c"*64
    operator = "fabric-operator-example"
    child = "fabric-leaf-example"
    return {
        "schema": canary.SCHEMA,
        "merged_source_sha": "d"*40,
        "selected_generation": generation,
        "source_merge_provenance": "verified_protected_master_readback",
        "runtime_generation_provenance": "verified_selected_runtime_readback",
        "cases": {
            "claude": {
                "root_id":claude_root, "immediate_parent_id":claude_parent,
                "parent_identity_verified":True,
                "skill_session": {"principal":"claude", "loaded":True,
                                  "session_id":"fresh-claude", "skill_sha256":"a"*64},
                "worker": _run("claude-readonly-leaf", claude_parent, claude_root, generation,
                               answer=canary.EXPECTED_COMPUTATIONS["claude"]),
            },
            "codex": {
                "root_id":codex_root, "immediate_parent_id":codex_parent,
                "parent_identity_verified":True,
                "skill_session": {"principal":"codex", "loaded":True,
                                  "session_id":"fresh-codex", "skill_sha256":"a"*64},
                "worker": _run("codex-readonly-leaf", codex_parent, codex_root, generation,
                               answer=canary.EXPECTED_COMPUTATIONS["codex"]),
            },
            "operator": {
                "root_id":operator_root,"immediate_parent_id":operator_parent,
                "parent_identity_verified":True,
                "scope": {"root":operator_root, "operator_run":operator,
                          "child_budget_at_admission":1, "grant_verified":True},
                "operator_run":_run(operator,operator_parent,operator_root,generation,
                                    answer="Reviewed child transport digest: " + "b"*64),
                "child_run":_run(child,operator,operator_root,generation,
                                 answer=canary.EXPECTED_COMPUTATIONS["operator.child"]),
                "child_acknowledgment":{"run_id":child,"parent_run_id":operator,
                                        "acknowledged":True,"sha256":"b"*64},
                "principal_adjudicated_operator_result":True,
            },
        },
    }


def test_canary_contract_does_not_claim_live_proof_from_self_reported_json():
    report = canary.evaluate(_valid_receipts())
    assert report["state"] == "ASSERTIONS_PASS_PROVENANCE_NOT_VERIFIED"
    assert report["issues"] == []
    assert not report["live_proven"] and report["launches"] == 0


@pytest.mark.parametrize("tamper,reason", [
    (lambda x: x["cases"]["codex"]["worker"]["status"]["status"].update(root_id="other"),
     "codex.root_verified"),
    (lambda x: x["cases"]["claude"]["worker"]["status"]["status"].update(state="QUEUED"),
     "claude.terminal_result"),
    (lambda x: x["cases"]["operator"]["child_acknowledgment"].update(sha256="0"*64),
     "operator.same_parent_child_ack"),
    (lambda x: x["cases"]["operator"]["child_run"]["status"]["status"].update(parent_run_id="other"),
     "operator.child.parent"),
    (lambda x: x["cases"]["claude"]["worker"]["acceptance"].update(accepted=False),
     "claude.principal_acceptance"),
    (lambda x: x["cases"]["codex"]["skill_session"].update(loaded=False),
     "codex.real_session_skill_load"),
    (lambda x: x["cases"]["operator"]["scope"].update(child_budget_at_admission=0),
     "operator.admitted_scope"),
    (lambda x: x["cases"]["codex"]["worker"].update(run_id="claude-readonly-leaf"),
     "four_distinct_run_ids"),
])
def test_canary_contract_refuses_missing_or_forged_required_evidence(tamper, reason):
    data = _valid_receipts()
    tamper(data)
    result = canary.evaluate(data)
    assert result["state"] == "REFUSED"
    assert reason in result["issues"]
    assert result["live_proven"] is False


def _rebind_direct_case_identity(case: dict, *, root: str, parent: str) -> None:
    case["root_id"] = root
    case["immediate_parent_id"] = parent
    worker = case["worker"]
    worker["start_receipt"].update(root_id=root, parent_run_id=parent)
    worker["status"]["status"].update(root_id=root, parent_run_id=parent)
    worker["result"]["root_id"] = root
    worker["parent_return"]["principal_parent_id"] = parent


@pytest.mark.parametrize("borrowed", ["root", "parent"])
def test_canary_refuses_separately_consistent_borrowed_claude_codex_identity(borrowed):
    data = _valid_receipts()
    claude = data["cases"]["claude"]
    codex = data["cases"]["codex"]
    root = claude["root_id"] if borrowed == "root" else codex["root_id"]
    parent = claude["immediate_parent_id"] if borrowed == "parent" else codex["immediate_parent_id"]
    _rebind_direct_case_identity(codex, root=root, parent=parent)
    result = canary.evaluate(data)
    assert result["state"] == "REFUSED"
    assert "distinct_case_identities" in result["issues"]


def test_canary_refuses_separately_consistent_operator_borrowed_claude_root():
    data = _valid_receipts()
    borrowed = data["cases"]["claude"]["root_id"]
    operator = data["cases"]["operator"]
    operator["root_id"] = borrowed
    operator["scope"]["root"] = borrowed
    for name in ("operator_run", "child_run"):
        item = operator[name]
        item["start_receipt"]["root_id"] = borrowed
        item["status"]["status"]["root_id"] = borrowed
        item["result"]["root_id"] = borrowed
    result = canary.evaluate(data)
    assert result["state"] == "REFUSED"
    assert "distinct_case_identities" in result["issues"]


@pytest.mark.parametrize("field,expected_issue", [
    ("response_bytes", "codex.result_payload"),
    ("child_budget", "operator.admitted_scope"),
])
def test_canary_rejects_bool_as_numeric_receipt_field(field, expected_issue):
    data = _valid_receipts()
    if field == "response_bytes":
        data["cases"]["codex"]["worker"]["result"]["response_bytes"] = True
    else:
        data["cases"]["operator"]["scope"]["child_budget_at_admission"] = True
    result = canary.evaluate(data)
    assert result["state"] == "REFUSED"
    assert expected_issue in result["issues"]


def test_canary_expected_digest_literals_match_runbook():
    import hashlib
    doc = (ROOT / "docs/release/FABRIC_DELEGATION_1694_ROLLOUT.md").read_text()
    for kind, payload in canary.CANARY_INPUTS.items():
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert digest == canary.EXPECTED_COMPUTATIONS[kind]
        assert payload in doc and digest in doc


@pytest.mark.parametrize("kind", ["claude", "codex", "operator.child"])
def test_canary_refuses_wrong_computed_work_even_when_task_terminal_accepted(kind):
    report = _valid_receipts()
    record = (report["cases"]["operator"]["child_run"] if kind == "operator.child"
              else report["cases"][kind]["worker"])
    record["result"]["adapter_response"] = "0" * 64
    result = canary.evaluate(report)
    assert result["state"] == "REFUSED"
    assert kind + ".computed_task_result" in result["issues"]
    assert result["live_proven"] is False


def test_canary_refuses_digest_present_only_in_extra_echo_text():
    report = _valid_receipts()
    value = canary.EXPECTED_COMPUTATIONS["claude"]
    report["cases"]["claude"]["worker"]["result"]["adapter_response"] = (
        "The task request includes this expected digest: " + value
    )
    result = canary.evaluate(report)
    assert result["state"] == "REFUSED"
    assert "claude.computed_task_result" in result["issues"]


def test_canary_refuses_operator_return_without_exact_child_transport_digest():
    report = _valid_receipts()
    report["cases"]["operator"]["operator_run"]["result"]["adapter_response"] = (
        "Child completed, no digest included"
    )
    result = canary.evaluate(report)
    assert result["state"] == "REFUSED"
    assert "operator.child_digest_returned_to_principal" in result["issues"]


@pytest.mark.parametrize("invalid_rc", [False, 0.0])
def test_canary_refuses_falsey_noninteger_worker_exit_code(invalid_rc):
    report = _valid_receipts()
    report["cases"]["codex"]["worker"]["status"]["status"]["rc"] = invalid_rc
    result = canary.evaluate(report)
    assert result["state"] == "REFUSED"
    assert "codex.terminal_result" in result["issues"]


def test_canary_duplicate_json_keys_refused():
    with pytest.raises(ValueError, match="duplicate receipt JSON key"):
        json.loads('{"schema":"one","schema":"two"}',
                   object_pairs_hook=canary._no_duplicate_keys)
