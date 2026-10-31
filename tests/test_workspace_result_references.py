"""Local producer/contract tests over the real existing owners.

The cache fixture, validity publication, join/qualified guards, index
composer and companion validators are the actual existing owners; supplied
Fabric data proves derivation shape, never live acceptance.
"""
import copy
from types import SimpleNamespace

import pytest

from common.executive_workspace_contract import (
    FRAME_SCHEMA_V2, MAX_RESULT_RESPONSE_BYTES, canonical,
)
from common.executive_workspace_result_references_contract import (
    BODY_KEYS, CATALOGUE_KEYS, CONTROL_ROOM_RECEIPT_KEYS, OPERATION,
    REASON_CODES, SCHEMA, SOURCE_OBSERVATION_KEYS, frame_selection,
    unavailable, validate_body,
)
from control_plane.fabric_job_view import (
    ORCHESTRATION_TERMINAL_RECEIPT_SCHEMA, SCHEMA_V3, _TERMINAL_RECEIPT_KEYS,
    compose_fabric_result_reference_index,
)
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.workspace_result_references import read_result_references
from integrations.mastermind_workspace_app.contract import RESOURCE, SCOPE
from scripts import chairman_control_room as ccr
from tests.test_mission_workspace import _inputs_v2
from tests.test_workspace_read_service import STAMP, cache_fixture

SELECTION = {"work_ref": "WS:ONE", "root_job_id": "JOB-001"}
DIGEST = "d" * 64
ATTEMPT = "ATT-" + "a" * 32


def frame(selection=None):
    return {"schema": FRAME_SCHEMA_V2, "operation": OPERATION,
            "selection": dict(SELECTION) if selection is None else selection,
            "principal": {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
                          "subject_digest": "b" * 64, "client_ref": "fixture-web",
                          "resource": RESOURCE, "scopes": [SCOPE]}}


def owner(cache, acquire):
    return WorkspaceReadService(cache=cache, runtime=object(),
                                authorize=lambda principal: True, armed={},
                                runtime_identity={}, mission_v3_acquire=acquire)


def read(tmp_path, selection=None, *, mutate=None, acquire=None):
    """Run the producer against the real cache fixture and real guards."""
    owners, clock, cache = cache_fixture(tmp_path)
    owners[0].state_cache["doc"]["sources"] = {"agent_os_state_generated_at": STAMP}
    if mutate is not None:
        mutate(owners, clock)
    return read_result_references(
        owner(cache, acquire if acquire is not None else _acquire()),
        frame(selection))


# ---------------------------------------------------------------------------
# Real Fabric v3 companion: actual frozen v2 fixture + actual index composer.
# ---------------------------------------------------------------------------


def _terminal_receipt(job_id="JOB-001", attempt_id=ATTEMPT):
    receipt = {
        "schema_version": ORCHESTRATION_TERMINAL_RECEIPT_SCHEMA,
        "status": "COMPLETED", "job_id": job_id, "attempt_id": attempt_id,
        "orchestration_role": "work", "execution_mode": "SEALED_WORKER",
        "result_seal_command_id": "seal-" + job_id,
        "result_evidence": {"note": "fixture"},
        "result_envelope": {"summary": "fixture"},
        "result_envelope_digest": "e" * 64,
        "artifact_receipt_digest": "f" * 64,
        "validation_receipt_digest": "0" * 64,
        "effective_grant_digest": "1" * 64,
        "terminal_evidence_digest": "2" * 64,
    }
    assert set(receipt) == _TERMINAL_RECEIPT_KEYS
    return receipt


def _generation(state="SAME", before=1, after=1):
    return {"schema": "mastermind.runtime_read_observation.v1", "state": state,
            "source_identity": "c" * 64, "before": before, "after": after}


def _snapshot(jobs=(), attempts=(), digest=DIGEST, root="JOB-001"):
    return SimpleNamespace(root_job_id=root, jobs=list(jobs), attempts=list(attempts),
                           jobs_truncated=False, attempts_truncated_job_ids=(),
                           snapshot_digest=digest)


def _job(status="COMPLETED", receipt=None, attempt_id=ATTEMPT,
         root="JOB-001", job_id="JOB-001"):
    return SimpleNamespace(job_id=job_id, root_job_id=root, status=status,
                           result=receipt, current_attempt_id=attempt_id,
                           orchestration_role="work")


def _attempt(attempt_id=ATTEMPT, job_id="JOB-001", receipt=None):
    return SimpleNamespace(job_id=job_id, attempt_id=attempt_id, status="COMPLETED",
                           result=receipt, execution_mode="SEALED_WORKER")


def _completed_snapshot():
    receipt = _terminal_receipt()
    return _snapshot(jobs=[_job(receipt=receipt)], attempts=[_attempt(receipt=receipt)])


def _acquire(snapshot=None, generation=None):
    """Existing frozen Fabric-v2 fixture + actual v3 index composer."""
    snapshot = snapshot if snapshot is not None else _completed_snapshot()
    generation = generation if generation is not None else _generation()
    root = SELECTION["root_job_id"]

    def acquire(runtime, observed_root, **kwargs):
        assert kwargs == {"armed": {}, "runtime_identity": {}}
        assert observed_root == root
        fabric = _inputs_v2()["fabric_view"]
        fabric["generated_at"] = STAMP
        fabric["root"].update(job_id=root, root_job_id=root)
        fabric["runtime"]["acquisition"] = {
            "schema": "mastermind.fabric_runtime_acquisition.v1",
            "query": {"kind": "root_discovery", "root_job_id": root},
            "owner": "executive_runtime", "snapshot_digest": snapshot.snapshot_digest,
            "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                        "attempts_total": 340, "creation_events_per_job": 1},
            "truncation": {"jobs": False, "attempt_job_ids": [], "roots": False,
                           "projection": False},
            "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
            "generation": generation,
        }
        return {"schema": SCHEMA_V3, "fabric_view": fabric,
                "result_refs": compose_fabric_result_reference_index(snapshot, generation)}

    return acquire


# ---------------------------------------------------------------------------
# AVAILABLE: real guards, real terminal receipt derivation, real budgets.
# ---------------------------------------------------------------------------


def test_available_body_is_exact_and_self_validating(tmp_path):
    result = read(tmp_path)
    assert set(result) == {"ok", "result"} and result["ok"] is True
    body = result["result"]
    assert set(body) == set(BODY_KEYS) and body["schema"] == SCHEMA
    assert body["availability"] == "AVAILABLE" and body["reason_codes"] == []
    assert body["selection"] == SELECTION
    index = body["index"]
    assert index["schema"] == "mastermind.fabric_result_reference_index.v1"
    assert index["root_job_id"] == "JOB-001" and index["truncated"] is False
    assert index["availability"] == "AVAILABLE"
    assert index["absent_job_ids"] == [] and index["omitted_job_ids"] == []
    assert index["snapshot_digest"] == DIGEST
    # Positive actual derivation: the real composer's narrow terminal
    # receipt locator produced exactly this ref from the supplied completed
    # attempt, and the strict existing index validator admitted it.
    assert index["refs"] == [{"root_job_id": "JOB-001", "job_id": "JOB-001",
                              "attempt_id": ATTEMPT,
                              "result_envelope_digest": "e" * 64,
                              "orchestration_role": "work",
                              "validation": "UNVALIDATED"}]
    observation = body["source_observation"]
    assert set(observation) == set(SOURCE_OBSERVATION_KEYS)
    assert observation["state"] == "SAME" and observation["selection"] == SELECTION
    assert set(observation["control_room"]) == set(CONTROL_ROOM_RECEIPT_KEYS)
    assert (observation["control_room"]["instance_before"]
            == observation["control_room"]["instance_after"])
    assert observation["runtime"] == index["generation"]
    assert observation["runtime"]["state"] == "SAME"
    assert observation["runtime"]["before"] == observation["runtime"]["after"]
    assert body["catalogue"] == {"generated_at": STAMP, "freshness": "CURRENT"}
    assert set(body["catalogue"]) == set(CATALOGUE_KEYS)
    assert len(canonical(result)) + 1 <= MAX_RESULT_RESPONSE_BYTES
    assert validate_body(body, SELECTION) is body


def test_stale_sole_root_still_reads_with_refs(tmp_path):
    source_stamp = "2026-09-20T00:00:00Z"
    def mutate(new_owners, new_clock):
        doc = new_owners[0].state_cache["doc"]
        row = doc["autonomy"]["responsibilities"][0]
        row["freshness"] = "stale"
        doc["sources"]["agent_os_state_generated_at"] = source_stamp
        row["validity"]["card"]["valid_for_ms"] = None
        with new_owners[0].state_lock:
            new_owners[0].state_cache["doc"] = doc
            ccr._publish_source_validity(new_owners[0], doc, tuple(new_clock),
                                         tuple(new_clock))

    body = read(tmp_path, mutate=mutate)["result"]
    assert body["availability"] == "AVAILABLE"
    assert body["catalogue"] == {"generated_at": source_stamp, "freshness": "STALE"}
    assert len(body["index"]["refs"]) == 1
    assert body["source_observation"]["state"] == "SAME"
    assert validate_body(body, SELECTION) is body


def test_index_partition_is_emitted_unchanged(tmp_path):
    holder = []

    def acquire(runtime, root, **kwargs):
        companion = _acquire()(runtime, root, **kwargs)
        holder.append(companion)
        return companion

    body = read(tmp_path, acquire=acquire)["result"]
    stored = holder[0]["result_refs"]
    assert body["index"] is stored
    assert stored["refs"] and stored["absent_job_ids"] == []
    assert stored["omitted_job_ids"] == [] and stored["truncated"] is False


# ---------------------------------------------------------------------------
# Refusals: actual 404 propagation, typed unavailable bodies, honest failures.
# ---------------------------------------------------------------------------


def test_missing_sole_root_refuses_before_runtime_with_actual_lookup_error(tmp_path):
    def acquire(*args, **kwargs):
        pytest.fail("Runtime read before sole-root admission")

    with pytest.raises(LookupError):
        read(tmp_path, {"work_ref": "WS:ONE", "root_job_id": "JOB-404"},
             acquire=acquire)


@pytest.mark.parametrize("mutation", ["ambiguous", "unresolved", "duplicate"])
def test_ambiguous_or_unresolved_selection_refuses_before_runtime(tmp_path, mutation):
    def mutate(new_owners, _clock):
        doc = new_owners[0].state_cache["doc"]
        row = doc["autonomy"]["responsibilities"][0]
        if mutation == "ambiguous":
            row["root_job_ambiguous"] = True
        elif mutation == "unresolved":
            row["runtime_root_state"] = "UNKNOWN"
        else:
            doc["work"] *= 2

    def acquire(*args, **kwargs):
        pytest.fail("Runtime read before sole-root admission")

    with pytest.raises(LookupError):
        read(tmp_path, mutate=mutate, acquire=acquire)


def test_runtime_acquisition_failure_is_typed_source_unavailable(tmp_path):
    def acquire(runtime, root, **kwargs):
        raise RuntimeError("runtime owner down")

    body = read(tmp_path, acquire=acquire)["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["index"] is None
    assert body["catalogue"] == {"generated_at": None, "freshness": "UNKNOWN"}
    observation = body["source_observation"]
    assert observation["state"] == "UNKNOWN" and observation["selection"] == SELECTION
    assert observation["control_room"] is None and observation["runtime"] is None


def test_unqualified_cache_is_typed_source_unavailable(tmp_path):
    def expire(new_owners, new_clock):
        new_clock[:] = [62000, new_clock[1] + 61000, 62000, new_clock[3] + 61000]

    body = read(tmp_path, mutate=expire)["result"]
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["source_observation"]["state"] == "UNKNOWN"
    assert body["index"] is None


def test_changed_source_during_read_is_typed_conflict(tmp_path):
    owners, _, cache = cache_fixture(tmp_path)
    baseline = _acquire()

    def acquire(runtime, root, **kwargs):
        result = baseline(runtime, root, **kwargs)
        owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Changed"
        return result

    body = read_result_references(owner(cache, acquire), frame())["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_CHANGED"]
    assert body["source_observation"]["state"] == "CONFLICT"
    assert body["source_observation"]["control_room"] is None
    assert body["index"] is None
    assert body["catalogue"] == {"generated_at": None, "freshness": "UNKNOWN"}
    assert validate_body(body, SELECTION) is body


def test_malformed_index_is_typed_reference_index_unavailable(tmp_path):
    def acquire(runtime, root, **kwargs):
        companion = _acquire()(runtime, root, **kwargs)
        companion["result_refs"]["refs"][0]["result_envelope_digest"] = "nothex"
        return companion

    body = read(tmp_path, acquire=acquire)["result"]
    assert body["reason_codes"] == ["REFERENCE_INDEX_UNAVAILABLE"]
    assert body["index"] is None
    assert body["source_observation"]["state"] == "UNKNOWN"


def test_unfinalized_generation_never_reads_available(tmp_path):
    for generation in (_generation(state="CONFLICT", before=1, after=2),
                       _generation(state="UNKNOWN", before=None, after=None)):
        body = read(tmp_path, acquire=_acquire(generation=generation))["result"]
        assert body["availability"] == "UNAVAILABLE"
        assert body["reason_codes"] == ["REFERENCE_INDEX_UNAVAILABLE"]


def test_mismatched_root_companion_is_refused(tmp_path):
    snapshot = _completed_snapshot()
    snapshot.root_job_id = "JOB-002"
    body = read(tmp_path, acquire=_acquire(snapshot=snapshot))["result"]
    assert body["reason_codes"] == ["REFERENCE_INDEX_UNAVAILABLE"]


def test_over_budget_whole_body_is_typed_without_index_mutation(tmp_path, monkeypatch):
    import control_plane.workspace_result_references as producer_module
    holder = []

    def acquire(runtime, root, **kwargs):
        companion = _acquire()(runtime, root, **kwargs)
        holder.append(companion)
        return companion

    monkeypatch.setattr(producer_module, "MAX_RESULT_RESPONSE_BYTES", 64)
    body = read(tmp_path, acquire=acquire)["result"]
    assert body["reason_codes"] == ["OVER_BUDGET"]
    assert body["index"] is None
    assert body["source_observation"]["state"] == "UNKNOWN"
    assert body["catalogue"] == {"generated_at": None, "freshness": "UNKNOWN"}
    # The actual index partition is intact and untruncated after the refusal.
    stored = holder[0]["result_refs"]
    assert stored["availability"] == "AVAILABLE" and len(stored["refs"]) == 1
    assert stored["absent_job_ids"] == [] and stored["omitted_job_ids"] == []


# ---------------------------------------------------------------------------
# Contract-level refusals: request grammar, closed vocabulary, body budget.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("selection", [
    {"work_ref": "WS:ONE", "root_job_id": "JOB-001", "job_id": "JOB-001"},
    {"work_ref": "WS:ONE"},
    {"work_ref": "nope", "root_job_id": "JOB-001"},
    {"work_ref": "WS:ONE", "root_job_id": "JOB-001",
     "attempt_id": ATTEMPT, "result_envelope_digest": "e" * 64},
])
def test_list_request_accepts_only_the_normalized_two_key_selection(selection):
    with pytest.raises(ValueError):
        frame_selection(frame(selection))


@pytest.mark.parametrize("reason", ["NOPE", "source_unavailable", None, 7])
def test_unavailable_reason_is_closed_vocabulary(reason):
    with pytest.raises(ValueError):
        unavailable(SELECTION, reason)


@pytest.mark.parametrize("reason", sorted(REASON_CODES))
def test_typed_unavailable_shape_for_every_reason(reason):
    result = unavailable(SELECTION, reason)
    body = result["result"]
    assert result["ok"] is True
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == [reason]
    assert body["index"] is None
    assert body["catalogue"] == {"generated_at": None, "freshness": "UNKNOWN"}
    assert body["source_observation"]["selection"] == SELECTION
    assert body["source_observation"]["control_room"] is None
    assert body["source_observation"]["runtime"] is None
    expected = "CONFLICT" if reason == "SOURCE_CHANGED" else "UNKNOWN"
    assert body["source_observation"]["state"] == expected
    assert validate_body(body, SELECTION) is body


def test_validate_body_refuses_extra_field_or_mutation(tmp_path):
    body = read(tmp_path)["result"]
    with pytest.raises(ValueError):
        validate_body(dict(body, mission_current=True), SELECTION)
    with pytest.raises(ValueError):
        validate_body(dict(body, availability="PARTIAL"), SELECTION)
    with pytest.raises(ValueError):
        validate_body(dict(body, selection={"work_ref": "WS:ONE",
                                            "root_job_id": "JOB-002"}), SELECTION)
    bloated = copy.deepcopy(body)
    bloated["source_observation"]["control_room"]["document_digest"] = "x" * 40_000
    with pytest.raises(ValueError):
        validate_body(bloated, SELECTION)
