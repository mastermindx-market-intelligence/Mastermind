"""EVAL-R0 Task 6: create-only artifact store."""
from __future__ import annotations

import copy
import os
import uuid

import pytest

from scripts.agent_eval import contracts, scoring, store, validity
from scripts.agent_eval.canonical import add_document_digest
from scripts.agent_eval.errors import ArtifactConflictError, ContractError, VerificationContextError
from tests.agent_eval_factories import (
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_run_draft,
    build_two_arm_experiment,
    fresh_run_id,
)

VALIDATOR_KW = dict(
    validator_id="mastermind.eval_r0_finalizer.v1",
    validator_version="1",
    validator_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    validated_at="2026-08-25T00:00:10Z",
    created_at="2026-08-25T00:00:11Z",
)


@pytest.fixture()
def fresh_store(tmp_path):
    return store.ArtifactStore(tmp_path / "eval_root")


def _graph():
    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    return scenario, config_a, config_b, experiment


def _finalize(scenario, configuration, experiment, arm_id="arm_a", replicate_index=1, **kwargs):
    draft = build_run_draft(scenario, configuration, experiment, arm_id=arm_id, replicate_index=replicate_index, **kwargs)
    return validity.finalize_run_receipt(scenario, configuration, experiment, draft, **VALIDATOR_KW)


def _score(run: dict) -> dict:
    return scoring.build_technical_integrity_scorer_pass(
        run,
        scorer_pass_id=f"scorer-pass:{uuid.uuid4()}",
        scorer_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
        created_at="2026-08-25T00:00:12Z",
    )


# ---------------------------------------------------------------------------
# Global ID/path mappings
# ---------------------------------------------------------------------------


def test_scenario_path_mapping() -> None:
    scenario, *_rest = _graph()
    path = store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    assert path == store.Path("scenarios/evaluation_contract_integrity/baseline_case/v1/scenario.json")


def test_configuration_path_mapping() -> None:
    _scenario, config_a, _config_b, _experiment = _graph()
    path = store.configuration_path(config_a["configuration_id"])
    uuid_part = config_a["configuration_id"].split(":", 1)[1]
    assert str(path) == f"configurations/{uuid_part}/configuration.json"


def test_experiment_path_mapping() -> None:
    _scenario, _config_a, _config_b, experiment = _graph()
    path = store.experiment_path(experiment["experiment_id"])
    uuid_part = experiment["experiment_id"].split(":", 1)[1]
    assert str(path) == f"experiments/{uuid_part}/manifest.json"


def test_run_path_mapping() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    run = _finalize(scenario, config_a, experiment)
    path = store.run_path(run["run_id"])
    uuid_part = run["run_id"].split(":", 1)[1]
    assert str(path) == f"runs/{uuid_part}/receipt.json"


def test_global_id_maps_resolve_without_a_mutable_index(fresh_store) -> None:
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)
    fresh_store.create(experiment)
    # a fresh ArtifactStore instance over the SAME root resolves everything
    # purely from the schema-derived path -- no shared index/state.
    reopened = store.ArtifactStore(fresh_store.root)
    assert reopened.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"]) == scenario
    assert reopened.resolve_configuration(config_a["configuration_id"]) == config_a
    assert reopened.resolve_experiment(experiment["experiment_id"]) == experiment


# ---------------------------------------------------------------------------
# Path hazards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "segment",
    ["", "a" * 300, "has/slash", "has\\backslash", ".", "..", "trailing.", "trailing ", "CON", "con.txt", "a\x00b"],
)
def test_path_segment_validation_rejects_hazards(segment: str) -> None:
    with pytest.raises(ContractError):
        store._validate_path_segment(segment)


def test_path_segment_validation_accepts_normal_segment() -> None:
    store._validate_path_segment("baseline_case")  # must not raise


# ---------------------------------------------------------------------------
# Root escape / symlink parents
# ---------------------------------------------------------------------------


def test_root_must_not_be_a_symlink(tmp_path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real_dir)
    with pytest.raises(ContractError):
        store.ArtifactStore(link)


def test_resolve_within_root_rejects_absolute_path(fresh_store) -> None:
    with pytest.raises(ContractError):
        fresh_store._resolve_within_root("/etc/passwd")


def test_resolve_within_root_rejects_traversal_escape(fresh_store) -> None:
    with pytest.raises(ContractError):
        fresh_store._resolve_within_root("../../etc/passwd")


def test_create_rejects_symlink_parent_directory(fresh_store) -> None:
    scenario, *_rest = _graph()
    # pre-create a symlinked directory where the scenario's family directory
    # would normally go
    scenarios_dir = fresh_store.root / "scenarios"
    scenarios_dir.mkdir(parents=True)
    outside = fresh_store.root.parent / "outside_family"
    outside.mkdir()
    (scenarios_dir / "evaluation_contract_integrity").symlink_to(outside)
    with pytest.raises(ContractError) as excinfo:
        fresh_store.create(scenario)
    assert any(d.code == "SYMLINK_PARENT_REJECTED" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# Nonregular / oversized file
# ---------------------------------------------------------------------------


def test_resolve_returns_none_for_nonregular_artifact_path(fresh_store) -> None:
    scenario, *_rest = _graph()
    path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    path.parent.mkdir(parents=True)
    os.mkfifo(path)  # a FIFO is not a regular file
    with pytest.raises(ContractError) as excinfo:
        fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"])
    assert any(d.code == "NONREGULAR_FILE_REJECTED" for d in excinfo.value.defects)


def test_oversized_stored_file_is_rejected_by_metadata_before_reading(fresh_store) -> None:
    scenario, *_rest = _graph()
    path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * (store.MAX_CANONICAL_ARTIFACT_BYTES + 1))
    with pytest.raises(ContractError) as excinfo:
        fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"])
    assert any(d.code == "ARTIFACT_TOO_LARGE" for d in excinfo.value.defects)


def test_exact_boundary_size_is_permitted(fresh_store) -> None:
    scenario, *_rest = _graph()
    fresh_store.create(scenario)
    path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    size = path.stat().st_size
    assert size <= store.MAX_CANONICAL_ARTIFACT_BYTES  # sanity: real fixture is well under the bound
    # directly craft a file at EXACTLY the boundary (trailing JSON
    # whitespace is legal and does not change the parsed document) and
    # confirm the bound check is a strict "> limit", never ">= limit".
    padded = path.read_bytes() + b" " * (store.MAX_CANONICAL_ARTIFACT_BYTES - size)
    assert len(padded) == store.MAX_CANONICAL_ARTIFACT_BYTES
    path.write_bytes(padded)
    resolved = fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"])
    assert resolved == scenario  # exact-boundary size is permitted, not refused


def test_one_byte_over_boundary_is_refused(fresh_store) -> None:
    scenario, *_rest = _graph()
    fresh_store.create(scenario)
    path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    size = path.stat().st_size
    padded = path.read_bytes() + b" " * (store.MAX_CANONICAL_ARTIFACT_BYTES - size + 1)
    assert len(padded) == store.MAX_CANONICAL_ARTIFACT_BYTES + 1
    path.write_bytes(padded)
    with pytest.raises(ContractError) as excinfo:
        fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"])
    assert any(d.code == "ARTIFACT_TOO_LARGE" for d in excinfo.value.defects)


def test_deceptive_file_metadata_read_race_still_caught(fresh_store, monkeypatch) -> None:
    # simulate a file whose reported st_size understates its true content by
    # monkeypatching stat while leaving the on-disk bytes oversized -- the
    # bounded read (which reads MAX+1 bytes regardless of stat) must still
    # catch it, proving the defense is not solely metadata-based.
    scenario, *_rest = _graph()
    path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{" + b" " * store.MAX_CANONICAL_ARTIFACT_BYTES)

    import os as os_module

    real_lstat = os_module.stat_result

    class _FakeStat:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            if name == "st_size":
                return 1
            return getattr(self._real, name)

    original_lstat = store.Path.lstat

    def fake_lstat(self):
        result = original_lstat(self)
        return _FakeStat(result)

    monkeypatch.setattr(store.Path, "lstat", fake_lstat)
    with pytest.raises(ContractError) as excinfo:
        fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"])
    assert any(d.code == "ARTIFACT_TOO_LARGE" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# create / idempotent / conflict
# ---------------------------------------------------------------------------


def test_create_returns_created_disposition(fresh_store) -> None:
    scenario, *_rest = _graph()
    result = fresh_store.create(scenario)
    assert result.disposition == store.WriteDisposition.CREATED
    assert result.artifact_id == scenario["scenario_id"]
    assert result.artifact_digest == scenario["scenario_digest"]


def test_create_same_bytes_twice_is_idempotent(fresh_store) -> None:
    scenario, *_rest = _graph()
    first = fresh_store.create(scenario)
    second = fresh_store.create(scenario)
    assert first.disposition == store.WriteDisposition.CREATED
    assert second.disposition == store.WriteDisposition.IDEMPOTENT


def test_create_changed_bytes_at_same_id_is_a_conflict(fresh_store) -> None:
    scenario, *_rest = _graph()
    fresh_store.create(scenario)
    tampered = copy.deepcopy(scenario)
    tampered["objective"] = "a different objective entirely"
    tampered = add_document_digest({k: v for k, v in tampered.items() if k != "scenario_digest"}, "scenario_digest")
    with pytest.raises(ArtifactConflictError):
        fresh_store.create(tampered)


def test_create_rejects_a_draft_document(fresh_store) -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    with pytest.raises(ContractError) as excinfo:
        fresh_store.create(draft)
    assert any(d.code == "DRAFT_SCHEMA_REJECTED" for d in excinfo.value.defects)


def test_create_rejects_missing_dependency(fresh_store) -> None:
    scenario, config_a, _config_b, experiment = _graph()
    # never create scenario/config -- experiment references them but they
    # do not exist in the store yet
    with pytest.raises(VerificationContextError):
        fresh_store.create(experiment)


def test_topological_creation_order_scenario_before_run(fresh_store) -> None:
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)  # experiment's second arm must also resolve
    fresh_store.create(experiment)
    run = _finalize(scenario, config_a, experiment)
    result = fresh_store.create(run)
    assert result.disposition == store.WriteDisposition.CREATED


def test_orphan_scorer_pass_fails_verify_tree_graph(fresh_store) -> None:
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)
    fresh_store.create(experiment)
    run = _finalize(scenario, config_a, experiment)
    fresh_store.create(run)
    scorer_pass = _score(run)
    fresh_store.create(scorer_pass)
    # delete the run's file directly (simulating an orphaned scorer pass)
    run_path = fresh_store.root / store.run_path(run["run_id"])
    run_path.unlink()
    defects = fresh_store.verify_tree_graph()
    assert any(d.code == "RUN_NOT_RESOLVED" for d in defects)


# ---------------------------------------------------------------------------
# Corruption / interrupted publication
# ---------------------------------------------------------------------------


def test_corrupt_json_on_disk_is_reported_not_silently_accepted(fresh_store) -> None:
    scenario, *_rest = _graph()
    path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not valid json")
    with pytest.raises(ContractError) as excinfo:
        fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"])
    assert any(d.code == "CORRUPT_JSON" for d in excinfo.value.defects)


def test_interrupted_publication_leaves_no_recognizable_artifact(fresh_store) -> None:
    scenario, *_rest = _graph()
    # simulate a crash mid-publish: only a stray temp file exists, never the
    # final path
    final_path = fresh_store.root / store.scenario_path(scenario["scenario_id"], scenario["scenario_version"])
    final_path.parent.mkdir(parents=True)
    stray_temp = final_path.parent / ".tmp-write-stray.part"
    stray_temp.write_bytes(b"partial data")
    assert fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"]) is None
    assert fresh_store.verify_tree_graph() == ()  # stray temp file is not enumerated as an artifact
    # a fresh create() attempt succeeds normally afterward
    result = fresh_store.create(scenario)
    assert result.disposition == store.WriteDisposition.CREATED


def test_unsupported_hard_link_semantics_fail_closed(fresh_store, monkeypatch) -> None:
    scenario, *_rest = _graph()

    def raising_link(*args, **kwargs):
        raise OSError("hard links not supported on this filesystem (simulated)")

    monkeypatch.setattr(store.os, "link", raising_link)
    with pytest.raises(ContractError) as excinfo:
        fresh_store.create(scenario)
    assert any(d.code == "HARD_LINK_UNSUPPORTED" for d in excinfo.value.defects)
    # no final artifact was created
    assert fresh_store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"]) is None


# ---------------------------------------------------------------------------
# Secret policy (amendment §4.4)
# ---------------------------------------------------------------------------


def test_create_rejects_supplied_secret_shape_before_any_write(fresh_store) -> None:
    scenario, *_rest = _graph()
    tampered_fields = {k: v for k, v in scenario.items() if k != "scenario_digest"}
    tampered_fields["objective"] = "leaked credential sk-ant-abcdefgh12345678 in the objective text"
    tampered = add_document_digest(tampered_fields, "scenario_digest")
    with pytest.raises(ContractError):
        fresh_store.create(tampered)
    # no artifact directory tree was created as a side effect of the refusal
    assert not (fresh_store.root / "scenarios").exists()


def test_invalid_run_with_sanitized_private_destination_is_still_persisted(fresh_store) -> None:
    # a validity FAILURE (private network destination observed) is evidence,
    # never a reason to destroy the run -- and the sanitized observation
    # (digest only, no raw private IP) must not itself be rejected as a
    # supplied secret since it lives under observations.* (R-B1-4 exempt set).
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)
    fresh_store.create(experiment)
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [contracts.sanitize_observed_destination("10.0.0.9")]
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    result = fresh_store.create(run)
    assert result.disposition == store.WriteDisposition.CREATED
    stored_bytes = (fresh_store.root / store.run_path(run["run_id"])).read_bytes()
    assert b"10.0.0.9" not in stored_bytes


# ---------------------------------------------------------------------------
# Whole-tree graph verification
# ---------------------------------------------------------------------------


def test_verify_tree_graph_is_clean_for_a_fully_valid_tree(fresh_store) -> None:
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)
    fresh_store.create(experiment)
    run_valid = _finalize(scenario, config_a, experiment)
    fresh_store.create(run_valid)
    run_invalid = _finalize(scenario, config_a, experiment, model_served="claude-opus-9", run_id=fresh_run_id())
    fresh_store.create(run_invalid)
    fresh_store.create(_score(run_valid))
    fresh_store.create(_score(run_invalid))
    evidence = scoring.summarize_experiment(
        experiment,
        scenario,
        fresh_store.enumerate_runs(),
        fresh_store.enumerate_scorer_passes(),
        evidence_ref_id=f"evidence-ref:{uuid.uuid4()}",
        intended_owner="person:sol",
        review_at="2026-08-26T00:00:00Z",
        created_at="2026-08-25T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    fresh_store.create(evidence)
    assert fresh_store.verify_tree_graph() == ()


def test_verify_tree_graph_reports_stale_validity_without_repairing(fresh_store) -> None:
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)
    fresh_store.create(experiment)
    run = _finalize(scenario, config_a, experiment)
    fresh_store.create(run)
    run_path = fresh_store.root / store.run_path(run["run_id"])
    forged = copy.deepcopy(run)
    forged["validity"]["reason_codes"] = ["MODEL_SERVED_MISMATCH"]  # inconsistent with actual clean fields
    forged["validity"]["status"] = "INVALID_CONFIGURATION"
    forged = add_document_digest({k: v for k, v in forged.items() if k != "run_digest"}, "run_digest")
    from scripts.agent_eval.canonical import canonical_json_bytes as _cjb

    run_path.write_bytes(_cjb(forged))
    defects_before = fresh_store.verify_tree_graph()
    assert any(d.code == "VALIDITY_NOT_RECOMPUTABLE" for d in defects_before)
    # never repair -- the file on disk is untouched by verify_tree_graph
    defects_after = fresh_store.verify_tree_graph()
    assert defects_before == defects_after


def test_verify_tree_graph_enumeration_is_deterministic(fresh_store) -> None:
    scenario, config_a, config_b, experiment = _graph()
    fresh_store.create(scenario)
    fresh_store.create(config_a)
    fresh_store.create(config_b)
    fresh_store.create(experiment)
    first = fresh_store.verify_tree_graph()
    second = fresh_store.verify_tree_graph()
    assert first == second == ()
