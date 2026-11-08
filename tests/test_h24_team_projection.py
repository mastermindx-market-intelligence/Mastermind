"""H24-06 source proof: real reducers, bounded Runtime and signed test principals.

All keys, grants, sockets and Runtime state are test fixtures. No installed
account, provider, service or production acceptance is exercised here.
"""
import asyncio
import copy
import hashlib
import inspect
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from common.executive_workspace_contract import canonical
from control_plane.mission_workspace import compose_mission_workspace_v3
from integrations.secretary_team_access.team_projection import (
    CURRENTNESS_SCHEMA, DISPLAY_ACTIONS, MAX_OUTPUT_BYTES, project_team, render_operator_text,
)
from integrations.secretary_team_access.mission import _parse_utc
from tests.test_mission_workspace import (
    STAMP, _child_row, _attempt_row, _owner_observation_inputs,
    _refresh_observation_digests, _index_with_refs,
)
from tests.test_workspace_mission_result_service import mission_owner, call_pair
from tests.test_workspace_result_service import result_owner, service
from tests.test_workspace_read_app import rsa_key

SELECTION = {"work_ref": "WS:ONE", "root_job_id": "JOB-1"}


def fixture_mission(*, orphan=False, partial=False, wake=None, observation="SAME"):
    """Real Mission reducer over closed test-owned Control Room/Fabric inputs."""
    args = _owner_observation_inputs()
    fabric = args["fabric_view"]
    fabric["root"].update(status="RUNNING", orchestration_role="aggregation")
    fabric["root"]["result"]["state"] = "IN_PROGRESS"
    rows = []
    for job, role, parent, depth, status in (
        ("JOB-2", "aggregation", "JOB-1", 1, "RUNNING"),
        ("JOB-3", "work", "JOB-2", 2, "QUEUED"),
        ("JOB-4", "review", "JOB-2", 2, "COMPLETED"),
        ("JOB-5", "repair", "JOB-2", 2, "QUEUED"),
    ):
        row = copy.deepcopy(fabric["root"])
        row.update(_child_row(job))
        row.update(orchestration_role=role, parent_job_id=parent, depth=depth, status=status)
        row["result"]["state"] = {"RUNNING": "IN_PROGRESS", "QUEUED": "NOT_STARTED",
                                  "COMPLETED": "COMPLETED"}[status]
        if status != "QUEUED":
            attempt = _attempt_row()
            attempt.update(attempt_id="ATT-" + str(int(job[4:])) * 32, status=status,
                           finished_at=STAMP if status == "COMPLETED" else None)
            row.update(attempt_count=1, current_attempt_id=attempt["attempt_id"], latest_attempt=attempt)
        rows.append(row)
    if orphan:
        rows[-1].update(parent_job_id="JOB-99", depth=7)
    fabric["children"] = rows
    if partial:
        fabric["unjoined_job_count"] = 2
        fabric["unjoined_job_ids"] = ["JOB-80", "JOB-81"]
        fabric["runtime"]["acquisition"]["provenance"] = {
            "state": "PARTIAL", "unjoined_job_ids": ["JOB-80", "JOB-81"]}
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    if wake:
        responsibility["dispatch"]["w3c"] = {
            "state": "RESOLVED", "reason": "fixture", "terminal_state": "APPLIED",
            "wake_state": wake, "terminal_applied": True,
            "source_receipt": {"observed_at": STAMP, "freshness": "SOURCE_EVIDENCE_TIME",
                "snapshot_digest": "d" * 64, "terminal_source_owner": "executive_terminal_return",
                "wake_source_owner": "wake_ledger"}}
    _refresh_observation_digests(args)
    generation = dict(fabric["runtime"]["acquisition"]["generation"])
    index = _index_with_refs([], root_job_id="JOB-1",
        absent=["JOB-1", "JOB-2", "JOB-3", "JOB-4", "JOB-5"],
        snapshot_digest="c" * 64, generation=generation)
    args["fabric_view"] = {"schema": "mastermind.fabric_job_view.v3",
                           "fabric_view": fabric, "result_refs": index}
    if observation == "MISSING":
        args["owner_observation"] = None
    elif observation == "CONFLICT":
        args["owner_observation"].update(state="CONFLICT", control_room=None)
    return compose_mission_workspace_v3(**args)


def project(body, **kwargs):
    selection = {"work_ref": body["program"]["work_ref"],
                 "root_job_id": body["result_refs"]["root_job_id"]}
    return project_team(body, selection=selection,
                        now=kwargs.pop("now", _parse_utc(body["generated_at"]) + 1), **kwargs)


def card(view, job):
    return next(row for row in view["cards"] if row["job_id"] == job)


def actual_pair(owner):
    response = call_pair(owner)
    assert response["ok"] is True, response
    pair = response["result"]
    assert pair["availability"] == "AVAILABLE", pair
    return pair


def actual_acceptance(tmp_path, monkeypatch, *, consume=True, complete=True):
    from tests.test_product_acceptance_read_projection import case
    from tests.test_product_acceptance_workspace_read import provider
    with case(tmp_path, monkeypatch, consume=consume, complete=complete) as (
        runtime, requester, target, _, selected, run
    ):
        before = runtime.events.list_events()
        def read(bound):
            svc, request, _ = provider(tmp_path, runtime, requester.reader, selected, bound)
            return asyncio.run(svc.handle_frame(request))
        response = run(read)
        assert response["ok"] is True, response
        assert runtime.events.list_events() == before
        return response["result"], selected, target.job_id


def test_nested_team_distinguishes_pending_started_review_and_repair():
    body = fixture_mission()
    before = copy.deepcopy(body)
    view = project(body)
    assert view["currentness"]["state"] == "CURRENT"
    assert card(view, "JOB-2")["role"] == "aggregation"
    assert card(view, "JOB-2")["start_evidence"] == "OBSERVED"
    assert card(view, "JOB-3")["job_state"] == "QUEUED"
    assert card(view, "JOB-3")["start_evidence"] == "UNPROVEN"
    assert card(view, "JOB-3")["parent_job_id"] == "JOB-2"
    assert card(view, "JOB-3")["depth"] == 2
    assert card(view, "JOB-4")["role"] == "review"
    assert card(view, "JOB-5")["role"] == "repair"
    assert all(c["original_root_job_id"] == "JOB-1" for c in view["cards"])
    assert all(c["product_acceptance"]["accepted"] is None for c in view["cards"])
    assert all(c["placement"]["state"] == "UNAVAILABLE" for c in view["cards"])
    assert all(c["effects"]["state"] is None for c in view["cards"])
    assert view["principal"]["owed_turn"]["seat"] == "ceo"
    assert card(view, "JOB-1")["decision_needed"] is True
    assert body == before
    text = render_operator_text(view)
    assert "parent=JOB-2 depth=2 QUEUED" in text and "Display only" in text
    assert len(canonical(view)) + 1 <= MAX_OUTPUT_BYTES


def test_missing_parent_and_depth_conflict_preserve_original_lineage():
    orphan = project(fixture_mission(orphan=True))
    row = card(orphan, "JOB-5")
    assert row["parent_job_id"] == "JOB-99" and row["depth"] == 7
    assert row["lineage"] == "MISSING_PARENT"
    assert orphan["currentness"]["state"] == "PARTIAL"
    body = fixture_mission()
    body["children"]["items"][-1]["depth"] = 11
    conflict = project(body)
    assert card(conflict, "JOB-5")["lineage"] == "DEPTH_CONFLICT"
    assert card(conflict, "JOB-5")["depth"] == 11


@pytest.mark.parametrize("defect", ["duplicate", "self_parent", "cycle", "foreign_attempt"])
def test_lineage_and_attempt_corruption_refuse(defect):
    body = fixture_mission()
    rows = body["children"]["items"]
    if defect == "duplicate":
        rows[1]["job_id"] = rows[0]["job_id"]
    elif defect == "self_parent":
        rows[0]["parent_job_id"] = rows[0]["job_id"]
    elif defect == "cycle":
        rows[0]["parent_job_id"] = rows[1]["job_id"]
    else:
        rows[0]["latest_attempt"]["attempt_id"] = "ATT-" + "f" * 32
    with pytest.raises(ValueError):
        project(body)


def test_real_qualified_result_available_but_consumption_unproven(mission_owner):
    pair = actual_pair(mission_owner)
    body = pair["mission"]
    job = pair["selection"]["job_id"]
    first = project(body)
    assert card(first, job)["result"]["state"] == "REFERENCE_ONLY"
    joined = project(body, result_pairs=[pair])
    row = card(joined, job)
    assert row["result"]["state"] == "AVAILABLE"
    assert row["result"]["reference"]["validation"] == "UNVALIDATED"
    assert row["result"]["consumption"] == "UNPROVEN"
    assert row["result"]["review"]["verdict"] == "reject"
    assert row["result"]["review"]["latest_revision_currentness"] == "UNPROVEN"
    assert row["product_acceptance"]["accepted"] is None
    assert row["decision_needed"] is True
    assert "Review rejection" in row["display_actions"]
    assert first["fingerprint"] != joined["fingerprint"]
    assert "role_result" not in row["result"]


@pytest.mark.parametrize("defect", ["foreign_work", "foreign_root", "attempt", "envelope",
                                   "role", "snapshot", "generation", "content", "role_content", "oversized"])
def test_foreign_tampered_or_oversized_result_refuses(mission_owner, defect):
    pair = actual_pair(mission_owner)
    mission = copy.deepcopy(pair["mission"])
    if defect == "foreign_work":
        pair["selection"]["work_ref"] = "WS:OTHER"
    elif defect == "foreign_root":
        pair["selection"]["root_job_id"] = "JOB-999"
    elif defect == "attempt":
        pair["selection"]["attempt_id"] = "ATT-" + "f" * 32
    elif defect == "envelope":
        pair["selection"]["result_envelope_digest"] = "f" * 64
    elif defect == "role":
        pair["role_result"]["result"]["role"] = "work"
    elif defect == "snapshot":
        pair["mission"]["result_refs"]["snapshot_digest"] = "f" * 64
    elif defect == "generation":
        pair["role_result"]["source_observation"]["runtime"]["source_identity"] = "f" * 32
    elif defect == "content":
        pair["role_result"]["result"]["content"]["role_result"]["verdict"] = "approve"
    elif defect == "role_content":
        pair["role_result"]["result"]["content"]["role_result"] = "reject"
        pair["role_result"]["result"]["role_result_digest"] = hashlib.sha256(canonical("reject")).hexdigest()
    else:
        pair["role_result"]["result"]["content"]["summary"] = "x" * 17_000
    with pytest.raises(ValueError):
        project(mission, result_pairs=[pair])


def test_content_over_budget_keeps_metadata_without_inventing_complete_result(mission_owner):
    pair = actual_pair(mission_owner)
    # Use the existing producer's canonical content fallback, not a truncated result.
    pair["role_result"].update(availability="CONTENT_OVER_BUDGET", reason_codes=["CONTENT_OVER_BUDGET"])
    pair["role_result"]["result"].update(availability="CONTENT_OVER_BUDGET", content_complete=False,
        content=None, omitted=["role_result", "summary", "next_actions"])
    view = project(pair["mission"], result_pairs=[pair])
    row = card(view, pair["selection"]["job_id"])
    assert row["result"]["state"] == "CONTENT_OVER_BUDGET"
    assert row["result"]["consumption"] == "UNPROVEN"
    assert row["product_acceptance"]["accepted"] is None


def test_duplicate_result_and_forged_review_header_refuse(mission_owner):
    pair = actual_pair(mission_owner)
    with pytest.raises(ValueError, match="duplicate_result"):
        project(pair["mission"], result_pairs=[pair, pair])
    pair["role_result"]["result"]["review"]["verdict"] = "approve"
    with pytest.raises(ValueError, match="review_content_mismatch"):
        project(pair["mission"], result_pairs=[pair])


def test_actual_acceptance_requires_original_parent_consumption(tmp_path, monkeypatch):
    companion, selected, subject = actual_acceptance(tmp_path, monkeypatch)
    view = project(companion["mission"], acceptance_companion=companion,
                   request_message_key=selected["request_message_key"])
    row = card(view, subject)
    assert row["product_acceptance"] == {"state": "ACCEPTED", "accepted": True, "current": True}
    assert row["result"]["consumption"] == "PROVEN_BY_ACCEPTANCE_OWNER"
    assert view["acceptance"]["receipt"]["parent_job_id"] == selected["root_job_id"]
    aged = project(companion["mission"], acceptance_companion=companion,
                   request_message_key=selected["request_message_key"],
                   now=_parse_utc(companion["mission"]["generated_at"]) + 500)
    assert aged["currentness"]["state"] == "HISTORICAL"
    assert card(aged, subject)["product_acceptance"]["current"] is False
    assert card(aged, subject)["decision_needed"] is None


@pytest.mark.parametrize("missing", ["parent", "consumption"])
def test_terminal_or_unconsumed_parent_is_not_product_acceptance(tmp_path, monkeypatch, missing):
    companion, selected, _ = actual_acceptance(tmp_path, monkeypatch,
        complete=missing != "parent", consume=missing != "consumption")
    view = project(companion["mission"], acceptance_companion=companion,
                   request_message_key=selected["request_message_key"])
    assert view["acceptance"]["state"] == "UNAVAILABLE"
    assert view["acceptance"]["reason_codes"] == [
        "PARENT_RETURN_UNVERIFIED" if missing == "parent" else "PARENT_CONSUMPTION_UNPROVEN"]
    assert all(c["product_acceptance"]["accepted"] is None for c in view["cards"])


@pytest.mark.parametrize("defect", ["request", "parent_attempt", "subject_digest", "embedded_mission", "rejected_enum"])
def test_acceptance_cannot_be_reused_for_foreign_or_changed_evidence(tmp_path, monkeypatch, defect):
    companion, selected, _ = actual_acceptance(tmp_path, monkeypatch)
    body = copy.deepcopy(companion["mission"])
    request_key = selected["request_message_key"]
    if defect == "request":
        request_key = "asd-mcp-" + "f" * 32
    elif defect == "parent_attempt":
        companion["product_acceptance"]["receipt"]["parent_attempt_id"] = "ATT-" + "f" * 32
    elif defect == "subject_digest":
        companion["product_acceptance"]["receipt"]["subject_result_envelope_digest"] = "f" * 64
    elif defect == "embedded_mission":
        companion["mission"]["program"]["title"] = "Different observation"
    else:
        companion["product_acceptance"]["state"] = "REJECTED"
    with pytest.raises(ValueError):
        project(body, acceptance_companion=companion, request_message_key=request_key)


@pytest.mark.parametrize("wake", ["ACCEPTED", "DELIVERED_UNACKNOWLEDGED", "TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"])
def test_mission_wake_is_not_child_consumption_or_product_acceptance(wake):
    view = project(fixture_mission(wake=wake))
    assert view["transport"]["scope"] == "MISSION"
    assert view["transport"]["wake_state"] == wake
    assert all(c["result"]["consumption"] == "UNPROVEN" for c in view["cards"])
    assert all(c["product_acceptance"]["accepted"] is None for c in view["cards"])


def test_wake_conflict_and_effect_uncertainty_survive_projection():
    body = fixture_mission(wake="ACCEPTED")
    body["transport"]["w3c"]["state"] = "EFFECT_UNKNOWN"
    view = project(body)
    assert view["transport"]["w3c_state"] == "EFFECT_UNKNOWN"
    assert view["transport"]["wake_state"] == "ACCEPTED"
    assert view["acceptance"]["state"] == "NOT_PROJECTED"


def test_child_effects_do_not_inherit_principal_effects():
    body = fixture_mission()
    from control_plane.mission_workspace import RUNTIME_CARD_KEYS
    runtime = dict.fromkeys(RUNTIME_CARD_KEYS)
    runtime.update(worker_id="principal-worker", effect_state="effect_unknown")
    body["principal"]["current_worker"] = runtime
    view = project(body)
    assert view["principal"]["current_worker"]["effect_state"] == "effect_unknown"
    assert all(c["effects"]["state"] is None for c in view["cards"])


def test_partial_omissions_and_display_window_never_mean_no_activity():
    body = fixture_mission(partial=True)
    view = project(body, limit=2)
    assert view["currentness"]["state"] == "PARTIAL"
    assert view["coverage"]["unjoined_job_count"] == 2
    assert view["coverage"]["unseen_population"] == "UNKNOWN"
    assert view["coverage"]["cards_in_snapshot"] == 5
    assert view["coverage"]["display_omitted_count"] == 3
    assert view["coverage"]["full_fleet"] is False
    empty_window = project(body, limit=0)
    assert empty_window["cards"] == [] and empty_window["coverage"]["cards_in_snapshot"] == 5
    assert empty_window["fingerprint"] == view["fingerprint"]


def test_unknown_counts_stay_null_and_result_omission_is_explicit():
    body = fixture_mission()
    body["children"].update(state="PARTIAL", coverage="INCOMPLETE", total_count=None,
                            overflow_count=None, unjoined_job_count=None)
    body["result_refs"].update(availability="PARTIAL", truncated=True,
                             absent_job_ids=["JOB-1", "JOB-2", "JOB-3", "JOB-4"],
                             omitted_job_ids=["JOB-5"])
    view = project(body)
    assert view["currentness"]["state"] == "PARTIAL"
    assert view["coverage"]["source_omitted_child_count"] is None
    assert view["coverage"]["unjoined_job_count"] is None
    assert view["coverage"]["result_omitted_count"] == 1
    assert card(view, "JOB-5")["result"]["state"] == "OMITTED"


def test_quiet_fingerprint_ignores_observation_churn_but_tracks_expiry():
    body = fixture_mission(wake="DELIVERED_UNACKNOWLEDGED")
    now = _parse_utc(body["generated_at"])
    first = project(body, now=now)
    churn = copy.deepcopy(body)
    churn["generated_at"] = "2026-09-20T00:00:01Z"
    runtime = churn["source"]["owner_observation"]["runtime"]
    runtime.update(source_identity="f" * 32, before=19, after=19)
    churn["result_refs"]["generation"].update(source_identity="f" * 32, before=19, after=19)
    control = churn["source"]["owner_observation"]["control_room"]
    control.update(publication_before=21, publication_after=21)
    churn["children"]["items"].reverse()
    churn["transport"]["w3c"]["source_receipt"]["observed_at"] = "2026-09-20T00:00:01Z"
    second = project(churn, now=now + 2, previous_fingerprint=first["fingerprint"])
    assert second["fingerprint"] == first["fingerprint"]
    assert second["changed"] is False and second["attention"]["reasoning_wake_recommended"] is False
    assert second["cards"] == [] and second["coverage"]["unchanged_suppressed_count"] == 5
    aged = project(churn, now=now + 500, previous_fingerprint=first["fingerprint"])
    assert aged["currentness"]["state"] == "HISTORICAL"
    assert aged["changed"] is True
    unchanged_aged = project(churn, now=now + 501, previous_fingerprint=aged["fingerprint"])
    assert unchanged_aged["currentness"]["state"] == "HISTORICAL"
    assert unchanged_aged["attention"]["reasoning_wake_recommended"] is False
    assert unchanged_aged["coverage"]["cards_in_snapshot"] == 5


@pytest.mark.parametrize("state", ["PARTIAL", "HISTORICAL", "UNAVAILABLE"])
def test_noncurrent_owner_state_survives_unchanged_read(state):
    body = fixture_mission()
    body["read_state"]["state"] = state
    body["result_refs"].update(availability="UNAVAILABLE", refs=[], absent_job_ids=[], omitted_job_ids=[])
    first = project(body)
    second = project(body, previous_fingerprint=first["fingerprint"])
    assert second["currentness"]["state"] == state
    assert second["changed"] is False
    assert second["attention"]["reasoning_wake_recommended"] is False


@pytest.mark.parametrize("defect", ["digest", "noncurrent_refs", "v3_acceptance", "negative_count", "unknown_schema"])
def test_source_contradictions_fail_closed(defect):
    body = fixture_mission()
    if defect == "digest":
        body["result_refs"]["snapshot_digest"] = "f" * 64
    elif defect == "noncurrent_refs":
        body["read_state"]["state"] = "PARTIAL"
    elif defect == "v3_acceptance":
        body["acceptance"]["state"] = "ACCEPTED"
    elif defect == "negative_count":
        body["children"]["total_count"] = -1
    else:
        body["schema"] = "mastermind.mission_workspace.v99"
    with pytest.raises(ValueError):
        project(body)


@pytest.mark.parametrize("now", [float("nan"), float("inf"), float("-inf"), True, "now"])
def test_nonfinite_or_non_numeric_clock_refuses(now):
    with pytest.raises(ValueError, match="invalid_now"):
        project(fixture_mission(), now=now)


def test_future_timestamp_and_unparseable_timestamp_are_unavailable():
    body = fixture_mission()
    assert project(body, now=_parse_utc(body["generated_at"]) - 1)["currentness"]["freshness"] == "FUTURE"
    body["generated_at"] = "not-a-time"
    view = project_team(body, selection=SELECTION, now=0)
    assert view["currentness"]["state"] == "UNAVAILABLE"


def test_bounded_input_and_read_only_display_vocabulary():
    body = fixture_mission()
    body["program"]["title"] = "x" * 2_000_001
    with pytest.raises(ValueError, match="mission_over_budget"):
        project(body)
    view = project(fixture_mission())
    assert view["display_only"] is True and view["attention"]["dispatch_permitted"] is False
    assert set(CURRENTNESS_SCHEMA["required"]) == set(view["currentness"])
    assert all(set(c["display_actions"]) <= set(DISPLAY_ACTIONS) for c in view["cards"])
    assert "principal" not in inspect.signature(project_team).parameters
    assert "authorized" not in inspect.signature(project_team).parameters


def test_concurrent_projections_are_deterministic_detached_and_pure():
    body = fixture_mission()
    original = copy.deepcopy(body)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(lambda _: project(body), range(20)))
    assert all(out == outputs[0] for out in outputs)
    outputs[0]["cards"][1]["display_actions"].append("PRIVATE MUTATION")
    assert "PRIVATE MUTATION" not in repr(outputs[1])
    assert body == original


@pytest.mark.parametrize("observation", ["MISSING", "CONFLICT"])
def test_real_owner_unavailable_observation_remains_a_useful_view(observation):
    body = fixture_mission(observation=observation)
    original = copy.deepcopy(body)
    assert body["read_state"]["state"] != "CURRENT"
    assert body["source"]["owner_observation"]["state"] == (
        "UNKNOWN" if observation == "MISSING" else "CONFLICT")
    assert body["source"]["owner_observation"]["control_room"] is None
    first = project(body)
    assert first["currentness"]["state"] == "UNAVAILABLE"
    assert first["currentness"]["owner_state"] == body["read_state"]["state"]
    assert first["source"]["control_room_document_digest"] is None
    assert first["coverage"]["unseen_population"] == "UNKNOWN"
    assert all(c["decision_needed"] is None for c in first["cards"])
    assert all(c["product_acceptance"]["accepted"] is None for c in first["cards"])
    second = project(body, previous_fingerprint=first["fingerprint"])
    assert second["currentness"]["state"] == "UNAVAILABLE"
    assert second["attention"]["reasoning_wake_recommended"] is False
    assert body == original


@pytest.mark.parametrize("defect", ["same_without_receipts", "current_without_receipts",
                                   "foreign_selection", "unknown_with_receipt", "bad_digest"])
def test_nullable_observations_cannot_fabricate_qualified_source(defect):
    body = fixture_mission(observation="MISSING" if defect != "bad_digest" else "CONFLICT")
    observation = body["source"]["owner_observation"]
    if defect == "same_without_receipts":
        observation["state"] = "SAME"
    elif defect == "current_without_receipts":
        body["read_state"]["state"] = "CURRENT"
    elif defect == "foreign_selection":
        observation["selection"]["root_job_id"] = "JOB-999"
    elif defect == "unknown_with_receipt":
        observation["runtime"] = fixture_mission()["source"]["owner_observation"]["runtime"]
    else:
        observation["runtime"]["snapshot_digest"] = "not-a-digest"
    with pytest.raises(ValueError):
        project(body)


def test_unchanged_full_display_can_expand_without_a_reasoning_wake():
    body = fixture_mission()
    first = project(body, limit=1)
    expanded = project(body, previous_fingerprint=first["fingerprint"], limit=5,
                       suppress_unchanged_details=False)
    assert expanded["fingerprint"] == first["fingerprint"]
    assert expanded["changed"] is False
    assert expanded["attention"]["reasoning_wake_recommended"] is False
    assert expanded["details_included"] is True
    assert len(expanded["cards"]) == 5 and len(expanded["hierarchy"]) == 5
    assert expanded["coverage"]["unchanged_suppressed_count"] == 0
    assert expanded["coverage"]["display_omitted_count"] == 0
    assert card(expanded, "JOB-3")["parent_job_id"] == "JOB-2"
    assert expanded["cards"] == project(body)["cards"]


def test_unchanged_compact_text_explains_suppression():
    body = fixture_mission()
    first = project(body)
    quiet = project(body, previous_fingerprint=first["fingerprint"])
    assert "Details unchanged; 5 cards suppressed" in render_operator_text(quiet)


def test_full_display_retains_historical_truth_without_waking():
    body = fixture_mission()
    now = _parse_utc(body["generated_at"]) + 500
    first = project(body, now=now)
    second = project(body, now=now + 1, previous_fingerprint=first["fingerprint"],
                     suppress_unchanged_details=False)
    assert second["currentness"]["state"] == "HISTORICAL"
    assert second["cards"] == first["cards"]
    assert all(c["decision_needed"] is None for c in second["cards"])
    assert second["attention"]["reasoning_wake_recommended"] is False


@pytest.mark.parametrize("policy", [None, 0, 1, "false", []])
def test_detail_policy_is_an_explicit_boolean(policy):
    with pytest.raises(ValueError, match="invalid_detail_policy"):
        project(fixture_mission(), suppress_unchanged_details=policy)


def test_input_budget_precedes_whole_container_serialization(monkeypatch):
    from integrations.secretary_team_access import team_projection as projection
    body = fixture_mission()
    shared = "x" * 600_000
    body["program"]["attention_ids"] = [shared] * 5
    encoder = projection.canonical
    def bounded_encoder(value):
        assert value is not body, "over-budget container reached the full encoder"
        return encoder(value)
    monkeypatch.setattr(projection, "canonical", bounded_encoder)
    with pytest.raises(ValueError, match="mission_over_budget"):
        project(body)


@pytest.mark.parametrize("value", [
    {"unicode": ["雪", "😀", "é"]},
    {"escaped\nkey": "\u0000\n\t\"\\"},
    {"scalar": [None, True, False, 12, -3, 0.125], "empty": [{}, []]},
])
def test_byte_budget_counts_utf8_escapes_tokens_and_trailing_lf(value):
    from integrations.secretary_team_access.team_projection import _bounded_json
    size = len(canonical(value)) + 1
    assert _bounded_json(value, size, "budget") == value
    with pytest.raises(ValueError, match="budget"):
        _bounded_json(value, size - 1, "budget")


@pytest.mark.parametrize("field", ["state", "wake_state", "terminal_state"])
def test_non_scalar_wake_enum_refuses_with_value_error(field):
    body = fixture_mission(wake="ACCEPTED")
    body["transport"]["w3c"][field] = []
    with pytest.raises(ValueError, match="invalid_wake"):
        project(body)


def test_unrepresentable_clock_and_untyped_source_time_are_conservative():
    with pytest.raises(ValueError, match="invalid_now"):
        project(fixture_mission(), now=10 ** 1000)
    body = fixture_mission()
    body["generated_at"] = 123
    view = project_team(body, selection=SELECTION, now=123)
    assert view["currentness"]["state"] == "UNAVAILABLE"
    assert view["currentness"]["generated_at"] is None


@pytest.mark.parametrize("revocation_stage", ["before_read", "after_owner_read"])
def test_two_signed_principals_share_mission_with_independent_revocation(
    result_owner, rsa_key, revocation_stage,
):
    """Real JWT verifier, sealed member authorizers, Runtime service and reducer."""
    from integrations.business_mcp_auth.contracts import subject_digest
    from integrations.mastermind_workspace_app.contract import (
        MEMBER_BINDINGS_SCHEMA, principal_frame, workspace_authorizers,
    )
    from tests.test_workspace_read_app import (
        ISSUER, NOW, _workspace_policy, _authenticator, _workspace_token, _make_app,
    )
    subjects = ["h24-test-meta-ceo", "h24-test-secretary"]
    policy = _workspace_policy(allowed_subject_digests=sorted(
        subject_digest(issuer=ISSUER, subject=s) for s in subjects))
    authenticator = _authenticator(rsa_key, policy=policy)
    tokens = [_workspace_token(rsa_key, sub=s) for s in subjects]
    principals = [asyncio.run(authenticator.verify_token(token, now=NOW)) for token in tokens]
    bindings = {"schema": MEMBER_BINDINGS_SCHEMA, "primary_profile": "member-0", "profiles": {
        f"member-{i}": {"enabled": True, "binding": dict(principal_frame(p),
            permission_digest=hashlib.sha256(f"h24-fixture-{i}".encode()).hexdigest())}
        for i, p in enumerate(principals)}}
    app_authorize, control_authorize = workspace_authorizers(policy=policy, load_bindings=lambda: bindings)
    svc = service(result_owner, authorize=control_authorize)
    seen = []
    revoke_after_read = [False]
    class Host:
        async def request(self, frame):
            seen.append(frame["principal"]["subject_digest"])
            response = await svc.handle_frame(frame)
            if revoke_after_read[0]:
                bindings["profiles"]["member-0"]["enabled"] = False
            return response
    http, _ = _make_app(rsa_key, client=Host(), policy=policy, authorize=app_authorize)
    selected = {k: result_owner["selection"][k] for k in ("work_ref", "root_job_id")}
    def read(index):
        return http.get("/workspace/mission/v3/current", params=selected,
                        headers={"Authorization": "Bearer " + tokens[index]})
    first, second = read(0), read(1)
    assert first.status_code == second.status_code == 200
    one, two = project(first.json()), project(second.json())
    assert one["fingerprint"] == two["fingerprint"]
    assert seen == [p.subject_digest for p in principals]
    assert all(token not in json.dumps(one) for token in tokens)
    count = len(seen)
    if revocation_stage == "before_read":
        bindings["profiles"]["member-0"]["enabled"] = False
    else:
        revoke_after_read[0] = True
    denied = read(0)
    assert denied.status_code == 403
    assert "root_job_id" not in denied.text and "children" not in denied.text
    assert len(seen) == count + (revocation_stage == "after_owner_read")
    revoke_after_read[0] = False
    other = read(1)
    assert other.status_code == 200
    assert project(other.json())["fingerprint"] == two["fingerprint"]
