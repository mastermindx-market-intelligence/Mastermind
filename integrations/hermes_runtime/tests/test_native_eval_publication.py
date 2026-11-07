"""Original SQLite settlement, retirement and create-only artifact journeys.

Native source custody and the already admitted runtime claim are explicit
fixture edges. No listener, live service, provider, credential or inference
is used. Existing pinned native owner bodies perform the state transitions.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from integrations.hermes_runtime import native_eval_inputs as inputs
from integrations.hermes_runtime import native_eval_publication as publication
from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime import native_request_observation as observation
from integrations.hermes_runtime import native_transport_observation as transport
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests.test_native_eval_inputs import (
    admission_db, compile_selected, marker, source_owner, trial,
    lifecycle, decoded_fixture, actual_result, engine, native, native_trial, execute_trial, actual_custom_effort, success,
    current_result, signed, rsa_key, joined, owner, env, isolated_git_env, identity,
)
from integrations.hermes_runtime.tests.test_native_request_observation import module
from integrations.hermes_runtime.tests.test_native_transport_observation import run_call, retained_read, sdk
from scripts.agent_eval.canonical import canonical_json_bytes
from scripts.agent_eval.errors import ContractDefect, ContractError


@pytest.fixture
def original(trial, admission_db, monkeypatch):
    a, t = admission_db, trial
    t.session, t.principal = "session-a", f"uid:{os.getuid()}"
    value = marker(t)
    row = a.core["admit_session_input"](a.db, epoch=2, principal_id=t.principal, session_id=t.session,
        request_id=value["input"]["submission_id"],
        payload={"text": t.text, "finite": True, inputs.MARKER_KEY: value})
    a.conn.execute("ALTER TABLE sessions ADD COLUMN runtime_generation INTEGER DEFAULT 3")
    a.conn.execute("ALTER TABLE sessions ADD COLUMN runtime_revision INTEGER DEFAULT 0")
    # Worker cleanup is unrelated to this no-worker fixture. The actual native
    # settlement, result codec, transfer settlement and transaction execute.
    a.core.update(_retire_admission_workers=lambda *_: None, STEERING="steering")
    compile_selected(a.patched["hermes_state_runtime.py"],
        {"settle_session_input", "settle_steer_transfers", "cancel_session_input"},
        a.core, "hermes_state_runtime.py")
    a.core["_CANCEL_QUEUED"] = "UPDATE session_admissions SET status='terminal',outcome='cancelled' WHERE admission_id=?"
    terminal_path = Path(__file__).parent / "fixtures/request_observation/hermes_state_terminal.py.source"
    compile_selected(terminal_path.read_bytes(), {"compact_result"}, vars(a.terminal), str(terminal_path))
    module(monkeypatch, "hermes_state_runtime", **{key: value for key, value in a.core.items() if not key.startswith("__")})
    authority = SimpleNamespace(db=a.db, profile_id=t.owner.profile_id, epoch=2)
    t.owner.binding = SimpleNamespace(authority=authority)
    runner = SimpleNamespace(session_authority=authority,
        session_control_server=SimpleNamespace(private_handlers={}))
    params = {"operation": "publish_evaluation", "profile_id": t.owner.profile_id,
        "session_id": t.session, "submission_id": value["input"]["submission_id"],
        "input_sha256": control.input_digest(t.text), "admission_id": row["admission_id"],
        "evaluation_binding": {"run_id": value["run_id"], "binding_sha256": value["binding_sha256"]}}
    home = Path(t.owner.profile_id)
    monkeypatch.setattr(publication, "_now", lambda: "2026-11-07T18:00:00Z")

    def finish(outcome="completed", *, answer="original public answer", partial=False, result=True):
        a.conn.execute("UPDATE session_admissions SET status='started',generation=3 WHERE admission_id=?",
                       (row["admission_id"],))
        saved = {"result": {"final_response": answer, "partial": partial,
            "messages": [], "_messages_are_turn_suffix": True}, "usage": {"raw-private-usage": "never copied"}}
        return a.core["settle_session_input"](a.db, epoch=2, admission_id=row["admission_id"],
            generation=3, outcome=outcome, result=saved if result else None)

    def publish():
        return publication.publish_original(runner, home, params, t.principal, owner=t.owner, role="mmmeta")

    def frozen():
        raw = a.core["_admission"](a.conn, row["admission_id"])
        return json.loads(raw["eval_publication_json"]) if raw["eval_publication_json"] is not None else None

    def retire():
        a.db._execute_write(lambda conn: a.retirement.retire_terminal_receipts(conn, (t.session,)))

    return SimpleNamespace(a=a, t=t, marker=value, row=row, runner=runner, params=params, home=home,
                           finish=finish, publish=publish, frozen=frozen, retire=retire)


def test_original_terminal_freezes_once_and_publishes_without_copying_answer(original, monkeypatch):
    o = original
    o.finish()
    first = o.publish()
    assert first["status"] == "PUBLISHED" and first["publication"]["disposition"] == "CREATED"
    frozen = o.frozen()
    run = frozen["run"]
    raw = canonical_json_bytes(frozen)
    assert b"original public answer" not in raw and b"never copied" not in raw
    assert run["evidence"]["output"]["digest"] == "sha256:" + hashlib.sha256(b"original public answer").hexdigest()
    assert run["execution"]["runner_code_ref"] == o.marker["producer"]["runner_code_ref"]
    assert run["execution"]["model_served"] is None
    assert run["effect"]["state"] == "EFFECT_UNKNOWN" and run["cleanup"]["status"] == "UNPROVEN"
    assert run["validity"]["status"] != "VALID"
    assert "REQUIRED_OBSERVATION_UNAVAILABLE" in run["validity"]["reason_codes"]
    assert all(value is False for key, value in first["publication"].items() if key in {
        "complete_evaluation", "provider_delivery_proven", "model_identity_verified"})
    monkeypatch.setattr(publication, "_now", lambda: (_ for _ in ()).throw(AssertionError("cannot refinalize")))
    second = o.publish()
    assert second["publication"]["disposition"] == "IDEMPOTENT"
    assert canonical_json_bytes(o.frozen()) == raw
    assert o.t.owner.store.resolve_run(o.marker["run_id"]) == run
    assert o.a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 1


def test_frozen_v2_publication_replays_without_current_schema_upgrade(original, monkeypatch):
    from scripts.agent_eval.canonical import add_document_digest
    o = original
    builder = publication._build_run
    def prior_builder(*args, **kwargs):
        # Explicit prior-producer fixture. Original freeze/store/replay run;
        # only the old schema selection is supplied at this historical edge.
        run = builder(*args, **kwargs)
        run["schema"] = inputs.contracts.RUN_SCHEMA_V2
        return add_document_digest(run, "run_digest")
    monkeypatch.setattr(publication, "_build_run", prior_builder)
    o.finish()
    assert o.publish()["status"] == "PUBLISHED"
    before = canonical_json_bytes(o.frozen())
    assert o.frozen()["run"]["schema"] == inputs.contracts.RUN_SCHEMA_V2
    monkeypatch.setattr(publication, "_build_run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no rebuilding")))
    monkeypatch.setattr(publication, "_now", lambda: (_ for _ in ()).throw(AssertionError("no new clock")))
    assert o.publish()["publication"]["disposition"] == "IDEMPOTENT"
    assert canonical_json_bytes(o.frozen()) == before


@pytest.mark.parametrize("retire_before", [False, True])
def test_freeze_survives_both_retirement_orders_and_actual_result_expiry(original, retire_before, monkeypatch):
    o = original
    o.finish()
    if retire_before:
        o.retire()
    o.publish()
    before = canonical_json_bytes(o.frozen())
    if not retire_before:
        o.retire()
    o.a.retirement.time.time = lambda: 3000000
    o.a.db._execute_write(lambda conn: o.a.retirement.prune_retired_tombstones(conn))
    assert o.a.conn.execute("SELECT 1 FROM state_meta WHERE key=?",
        (o.a.terminal.RESULT_PREFIX + o.row["admission_id"],)).fetchone() is None
    monkeypatch.setattr(publication, "_build_run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no rebuilding")))
    assert o.publish()["publication"]["disposition"] == "IDEMPOTENT"
    assert canonical_json_bytes(o.frozen()) == before
    assert "eval_publication_json" not in o.a.core["_row"](o.a.core["_admission"](o.a.conn, o.row["admission_id"]))


def test_original_producer_and_later_finalizer_are_distinct(original):
    o = original
    o.finish()
    o.t.owner.producer = {**o.t.owner.producer,
        "runner_code_ref": "git:mastermindx-market-intelligence/Mastermind@" + "b" * 40}
    o.publish()
    run = o.frozen()["run"]
    assert run["execution"]["runner_code_ref"].endswith("a" * 40)
    assert run["validity"]["validator_code_ref"].endswith("b" * 40)


@pytest.mark.parametrize("outcome,expected", [
    ("completed", ("COMPLETED", "NATIVE_COMPLETED")),
    ("failed", ("FAILED", "NATIVE_FAILED")),
    ("interrupted", ("FAILED", "NATIVE_INTERRUPTED")),
    ("rejected", ("FAILED", "NATIVE_REJECTED")),
    ("cancelled", ("CANCELLED", "NATIVE_CANCELLED")),
])
def test_exact_terminal_outcome_and_missing_result_remain_honest(original, outcome, expected):
    o = original
    if outcome == "cancelled":
        o.a.core["cancel_session_input"](o.a.db, epoch=2, admission_id=o.row["admission_id"])
    else:
        o.finish(outcome, result=False)
    o.publish()
    record = o.frozen()
    assert record["native_outcome"] == outcome
    run = record["run"]
    assert (run["execution"]["completion_status"], run["execution"]["termination_reason"]) == expected
    assert run["evidence"]["output"] is None
    assert {item["reason"] for item in run["observation_availability"]["unavailable"]} == {"NOT_RETAINED"}
    assert o.a.conn.execute("SELECT 1 FROM state_meta WHERE key=?",
        (o.a.terminal.RESULT_PREFIX + o.row["admission_id"],)).fetchone() is None


def test_native_partial_is_not_reported_complete(original):
    original.finish(partial=True)
    original.publish()
    assert original.frozen()["run"]["execution"]["completion_status"] == "PARTIAL"


@pytest.mark.parametrize("status,outcome", [
    ("queued", None), ("started", None), ("unknown", None),
    ("terminal", "steering"), ("terminal", "steered"), ("terminal", "unknown-new-outcome"),
])
def test_unsettled_or_transfer_admission_cannot_freeze(original, status, outcome):
    o = original
    o.a.conn.execute("UPDATE session_admissions SET status=?,outcome=? WHERE admission_id=?",
                    (status, outcome, o.row["admission_id"]))
    with pytest.raises(RuntimeRefusal, match="TERMINAL_REQUIRED"):
        o.publish()
    assert o.frozen() is None and o.t.owner.store.resolve_run(o.marker["run_id"]) is None


@pytest.mark.parametrize("field,value", [
    ("session_id", "foreign"), ("submission_id", "foreign"), ("input_sha256", "0" * 64),
    ("admission_id", None), ("evaluation_binding", {"run_id": "foreign", "binding_sha256": "0" * 64}),
    ("artifact_root", "/caller-selected"), ("run", {}),
])
def test_caller_can_select_only_the_exact_original_identity(original, field, value):
    o = original
    o.finish()
    o.params[field] = value
    with pytest.raises((RuntimeRefusal, ContractError)):
        o.publish()
    assert o.frozen() is None


def test_original_principal_and_root_identity_cannot_be_substituted(original):
    o = original
    o.finish()
    original_principal = o.t.principal
    o.t.principal = "foreign"
    with pytest.raises(RuntimeRefusal, match="ORIGINAL_MISMATCH"):
        o.publish()
    o.t.principal = original_principal
    o.t.owner.publication = copy.deepcopy(o.t.owner.publication)
    o.t.owner.publication["root_identity"]["inode"] += 1
    with pytest.raises(RuntimeRefusal, match="ORIGINAL_STORE_REQUIRED"):
        o.publish()
    assert o.frozen() is None


@pytest.mark.parametrize("stage", ["lost_commit_response", "freeze_readback", "after_artifact_link"])
def test_lost_publication_boundary_reconciles_same_bytes_without_another_execution(original, monkeypatch, stage):
    o = original
    o.finish()
    if stage == "lost_commit_response":
        before = o.a.db._execute_write
        def lose(write):
            before(write)
            raise OSError("fixture lost commit response")
        monkeypatch.setattr(o.a.db, "_execute_write", lose)
    elif stage == "freeze_readback":
        before = o.a.db._read_ctx
        monkeypatch.setattr(o.a.db, "_read_ctx", lambda: (_ for _ in ()).throw(OSError("fixture readback failure")))
    else:
        before = o.t.owner.store._complete_publication
        monkeypatch.setattr(o.t.owner.store, "_complete_publication", lambda *_: (_ for _ in ()).throw(OSError("fixture sync failure")))
    with pytest.raises(publication.PublicationEffectUnknown):
        o.publish()
    frozen = canonical_json_bytes(o.frozen())
    assert (o.t.owner.store.resolve_run(o.marker["run_id"]) is not None) == (stage == "after_artifact_link")
    if stage == "lost_commit_response":
        monkeypatch.setattr(o.a.db, "_execute_write", before)
    elif stage == "freeze_readback":
        monkeypatch.setattr(o.a.db, "_read_ctx", before)
    else:
        monkeypatch.setattr(o.t.owner.store, "_complete_publication", before)
    result = o.publish()
    assert result["status"] == "PUBLISHED"
    assert result["publication"]["disposition"] == ("IDEMPOTENT" if stage == "after_artifact_link" else "CREATED")
    assert canonical_json_bytes(o.frozen()) == frozen
    assert o.a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 1


def test_frozen_record_corruption_never_rebuilds_or_overwrites(original):
    o = original
    o.finish()
    o.publish()
    retained = o.t.owner.store.resolve_run(o.marker["run_id"])
    damaged = o.frozen()
    damaged["binding_sha256"] = "0" * 64
    o.a.conn.execute("UPDATE session_admissions SET eval_publication_json=? WHERE admission_id=?",
                    (json.dumps(damaged), o.row["admission_id"]))
    with pytest.raises(RuntimeRefusal, match="RECORD_MISMATCH"):
        o.publish()
    assert o.t.owner.store.resolve_run(o.marker["run_id"]) == retained


def test_same_uid_private_control_uses_existing_handler_and_lost_response_classification(original, monkeypatch):
    o = original
    o.finish()
    async def install():
        control.install_private_control(o.runner, o.home, "mmmeta", evaluation_owner=o.t.owner)
    asyncio.run(install())
    handler = o.runner.session_control_server.private_handlers[control.conversation_contract("mmmeta").native_verb]
    assert handler(o.params, "uid:foreign")["status"] == "REFUSED"
    capability = handler({"operation": "evaluation_capabilities", "profile_id": str(o.home)}, o.t.principal)
    assert capability["evaluation"]["producer"] == o.t.owner.producer
    result = handler(o.params, o.t.principal)
    assert result["status"] == "PUBLISHED"
    monkeypatch.setattr(o.t.owner.store, "create", lambda *_: (_ for _ in ()).throw(OSError("fixture response loss")))
    assert handler(o.params, o.t.principal)["status"] == "EFFECT_UNKNOWN"
    assert o.frozen() is not None


def test_private_prewrite_refusal_and_unavailable_read_are_not_mutation_uncertainty(original, monkeypatch):
    o = original
    async def install():
        control.install_private_control(o.runner, o.home, "mmmeta", evaluation_owner=o.t.owner)
    asyncio.run(install())
    handler = o.runner.session_control_server.private_handlers[control.conversation_contract("mmmeta").native_verb]
    result = handler(o.params, o.t.principal)
    assert result["status"] == "REFUSED" and result["reason"].endswith("TERMINAL_REQUIRED")
    assert o.frozen() is None
    monkeypatch.setattr(o.t.owner, "check", lambda: (_ for _ in ()).throw(OSError("fixture source read unavailable")))
    result = handler(o.params, o.t.principal)
    assert result["status"] == "UNAVAILABLE" and o.frozen() is None


def test_current_writer_epoch_is_fenced_but_original_execution_epoch_remains_historical(original):
    o = original
    o.finish()
    o.a.conn.execute("UPDATE runtime_epoch SET epoch=3")
    o.a.conn.commit()
    with pytest.raises(RuntimeRefusal, match="ORIGINAL_OR_WRITER_UNAVAILABLE"):
        o.publish()
    assert o.frozen() is None
    o.runner.session_authority.epoch = 3
    o.publish()
    assert o.a.core["_admission"](o.a.conn, o.row["admission_id"])["owner_epoch"] == 2


@pytest.mark.parametrize("kind,reason", [("malformed", "OBSERVATION_CONFLICT"), ("oversized", "OBSERVATION_LIMIT")])
def test_unusable_retained_result_freezes_honest_absence_without_raw_content(original, kind, reason):
    o = original
    o.finish(result=False)
    value = "{broken" if kind == "malformed" else "x" * (publication.MAX_RETAINED_RESULT_BYTES + 1)
    o.a.conn.execute("INSERT INTO state_meta VALUES(?,?)", (o.a.terminal.RESULT_PREFIX + o.row["admission_id"], value))
    o.publish()
    run = o.frozen()["run"]
    assert run["evidence"]["output"] is None
    assert {row["reason"] for row in run["observation_availability"]["unavailable"]} == {reason}


def test_legacy_marker_stays_readable_but_cannot_invent_publication_provenance(original):
    from integrations.hermes_runtime.tests.test_native_eval_inputs import reseal
    o = original
    o.finish()
    value = copy.deepcopy(o.marker)
    value["schema"] = inputs.LEGACY_MARKER_SCHEMA
    value.pop("producer")
    value.pop("publication")
    reseal(value)
    inputs.validate_marker(value, text=o.t.text)
    o.a.conn.execute("UPDATE session_admissions SET payload_json=? WHERE admission_id=?",
        (json.dumps({"text": o.t.text, "finite": True, inputs.MARKER_KEY: value}), o.row["admission_id"]))
    o.params["evaluation_binding"]["binding_sha256"] = value["binding_sha256"]
    with pytest.raises(RuntimeRefusal, match="PROVENANCE_NOT_RETAINED"):
        o.publish()
    assert o.frozen() is None


def test_existing_artifact_is_not_proof_of_original_frozen_publication(original, monkeypatch):
    o = original
    o.finish()
    o.publish()
    run = o.frozen()["run"]
    # An unconfirmed or corrupted original freeze cannot be replaced with a
    # shape-valid existing file. The same ID must never be overwritten.
    o.a.conn.execute("UPDATE session_admissions SET eval_publication_json=NULL WHERE admission_id=?",
                    (o.row["admission_id"],))
    monkeypatch.setattr(publication, "_now", lambda: "2026-11-07T19:00:00Z")
    refused = o.publish()
    assert refused["status"] == "REFUSED" and refused["reason"] == "EVALUATION_ARTIFACT_CONFLICT"
    assert refused["frozen_record_retained"] is True
    assert o.t.owner.store.resolve_run(o.marker["run_id"]) == run
    assert o.frozen()["run"]["run_digest"] != run["run_digest"]


@pytest.fixture
def wire_projection(lifecycle, engine, tmp_path, monkeypatch, request):
    openai = pytest.importorskip("openai")
    mode = getattr(request, "param", "ordinary")
    selected = {}
    t = native_trial(lifecycle, tmp_path)
    original_turn = lifecycle.turn_for
    def turn_for(*args, **kwargs):
        turn = original_turn(*args, **kwargs)
        original_agent = turn._ctx.AIAgent
        def build(**options):
            agent = original_agent(**options)
            agent._current_turn_id = "turn-A"
            return agent
        turn._ctx.AIAgent = build
        return turn
    monkeypatch.setattr(lifecycle, "turn_for", turn_for)
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        if mode == "raised_attempt":
            raise httpx.ConnectError("fixture transport loss", request=request)
        if mode == "retry_restore" and len(bodies) <= 2:
            selected["agent"].provider = "PRIVATE_OTHER_PROVIDER" if len(bodies) == 1 else selected["provider"]
            return httpx.Response(500, headers={"retry-after-ms": "1"}, json={"error": {"message": "fixture"}})
        # Restore after the observed edge: a later correct label cannot erase
        # a different selector measured at client creation or an earlier send.
        selected["agent"].provider = selected["provider"]
        return httpx.Response(200, json=success("glm-5.3"))
    def downstream(out):
        selected.update(agent=out["agent"], provider=out["agent"].provider)
        extra, top = actual_custom_effort(out["agent"].reasoning_config["effort"])
        assert extra == {}
        out["kwargs"].update(top)
        def make_client():
            if mode == "factory_change":
                out["agent"].provider = "PRIVATE_OTHER_PROVIDER"
            hooks = {}
            if mode == "send_change":
                hooks = {"request": [lambda _request: setattr(out["agent"], "provider", "PRIVATE_OTHER_PROVIDER")]}
            return openai.OpenAI(
                api_key="synthetic-fixture", base_url="https://api.z.ai/api/paas/v4/",
                max_retries=2 if mode == "retry_restore" else 0,
                http_client=httpx.Client(transport=httpx.MockTransport(handler), event_hooks=hooks))
        if mode == "raised_attempt":
            with pytest.raises(openai.APIConnectionError):
                engine.invoke(out["agent"], out["kwargs"], make_client, request_id="eval-request")
        else:
            engine.invoke(out["agent"], out["kwargs"], make_client, request_id="eval-request")
    out = execute_trial(lifecycle, t, after_request=downstream)
    receipt = {"admission_id": "eval-admission", "ref": {"profile_id": t.owner.profile_id, "session_id": t.session},
        "sequence": 1, "status": "terminal", "outcome": "failed" if mode == "raised_attempt" else "completed",
        "authority_epoch": 2, "execution_generation": 3}
    # The native lifecycle fixture's role is mmsecretary. It exercises the same
    # selected private historical projection without enabling that role live.
    projected = control._project_original_result(receipt, out["marker"], out["saved"], role="mmsecretary")
    assert "request_observation" in projected and "evaluation_inputs" in projected
    assert len(bodies) == (3 if mode == "retry_restore" else 1)
    def build(value=None):
        return publication._build_run(out["marker"], receipt, projected if value is None else value,
            finalizer_ref=t.owner.producer["runner_code_ref"], now="2026-11-08T00:00:00Z", missing_reason="NOT_OBSERVED")
    return SimpleNamespace(projected=projected, build=build, marker=out["marker"], bodies=bodies)


def test_actual_sdk_and_pinned_worker_observations_feed_conservative_native_receipt(wire_projection):
    w = wire_projection
    run = w.build()
    assert run["execution"]["model_requested"] == "glm-5.3"
    assert run["execution"]["provider"] == "custom"
    runtime = w.projected["request_observation"]["transport"]
    provider = transport._scalar("custom", "model")
    assert runtime["schema"] == transport.SCHEMA
    assert all(row["runtime_provider"] == provider and row["provider_client_check"] == "matched"
        for row in runtime["dispatches"])
    assert all(row["runtime_provider"] == provider for row in runtime["attempts"])
    assert run["execution"]["auth_realm_class"] is None
    assert run["execution"]["reasoning_effort"] == "low" and run["randomness"]["seed"] == 0
    assert run["execution"]["process_fingerprint"] is not None
    assert run["execution"]["native_session_fingerprint"] is not None
    assert run["randomness"]["sampling_parameters_digest"] is None
    assert run["execution"]["model_served"] is None
    assert run["observation_availability"]["coverage"]["provider_requests"]["status"] == "PARTIAL"
    assert run["observations"]["observed_network_destinations"] == []
    assert run["schema"] == inputs.contracts.RUN_SCHEMA_V3
    selected = w.projected["evaluation_inputs"]
    expected_sources = inputs.observed_record_sources(selected)
    assert run["observations"]["observed_sources"] == expected_sources and expected_sources
    assert run["observation_availability"]["coverage"]["observed_sources"] == {
        "status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
    assert run["validity"]["status"] != "VALID"


def test_acquired_inventory_without_assembly_is_not_a_run_source(wire_projection):
    value = copy.deepcopy(wire_projection.projected)
    value["evaluation_inputs"]["assemblies"] = []
    run = wire_projection.build(value)
    assert run["observations"]["observed_sources"] == []
    assert run["observation_availability"]["coverage"]["observed_sources"]["status"] == "UNOBSERVED"


@pytest.mark.parametrize("change", ["unused_assembly", "retry_counter", "wire_content", "wire_fields", "missing_eval", "duplicate_event"])
def test_ambiguous_or_changed_cross_boundary_payload_never_exports_scalar_evidence(wire_projection, change):
    w = wire_projection
    value = copy.deepcopy(w.projected)
    obs = value["request_observation"]
    if change == "unused_assembly":
        value["evaluation_inputs"]["assemblies"] = []
    elif change == "retry_counter":
        obs["transport"]["calls"][0]["retry_count"] += 1
    elif change == "wire_content":
        obs["transport"]["attempts"][0]["request"]["content_sha256"] = "0" * 64
    elif change == "wire_fields":
        obs["transport"]["attempts"][0]["request"]["content_fields"] = []
    elif change == "missing_eval":
        value.pop("evaluation_inputs")
    else:
        obs["observations"].append(copy.deepcopy(obs["observations"][0]))
    run = w.build(value)
    assert run["execution"]["model_requested"] is None
    assert run["execution"]["provider"] is None
    assert run["execution"]["reasoning_effort"] is None
    assert run["randomness"]["seed"] is None


def historical_transport(value):
    value = copy.deepcopy(value)
    value["schema"] = transport.PREVIOUS_SCHEMA
    for record in value["dispatches"]:
        record.pop("runtime_provider")
        record.pop("provider_client_check")
    for record in value["attempts"]:
        record.pop("runtime_provider")
    return value


def test_transport_v1_remains_closed_and_survives_the_original_retained_reader(engine, monkeypatch):
    doc, carrier = run_call(engine, lambda: sdk(lambda request: httpx.Response(200, json=success())))
    saved, read = retained_read(engine, carrier, monkeypatch)
    legacy = historical_transport(doc["transport"])
    assert transport.validate_document(legacy) == legacy
    saved[observation.RESULT_KEY]["transport"] = legacy
    assert read()["request_observation"]["transport"] == legacy
    legacy["dispatches"][0]["runtime_provider"] = doc["transport"]["dispatches"][0]["runtime_provider"]
    assert read()["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"


@pytest.mark.parametrize("change", ["missing", "raw_label", "false_match", "attempt_shape", "schema"])
def test_provider_projection_is_closed_in_the_authenticated_retained_reader(engine, monkeypatch, change):
    _, carrier = run_call(engine, lambda: sdk(lambda request: httpx.Response(200, json=success())))
    saved, read = retained_read(engine, carrier, monkeypatch)
    value = saved[observation.RESULT_KEY]["transport"]
    dispatch, attempt = value["dispatches"][0], value["attempts"][0]
    if change == "missing":
        dispatch.pop("runtime_provider")
    elif change == "raw_label":
        dispatch["runtime_provider"]["value"] = "PRIVATE_PROVIDER"
    elif change == "false_match":
        dispatch["runtime_provider"] = {"status": "absent"}
    elif change == "attempt_shape":
        attempt["runtime_provider"] = {"status": "present", "value": "PRIVATE_PROVIDER"}
    else:
        value["schema"] += "-unknown"
    observed = read()
    assert observed["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"
    assert observed["answer"] == "[redacted]" and "PRIVATE_PROVIDER" not in json.dumps(observed)


@pytest.mark.parametrize("wire_projection", ["factory_change", "send_change", "retry_restore"], indirect=True)
def test_actual_provider_changes_cannot_be_hidden_by_restored_agent_labels(wire_projection):
    w = wire_projection
    run = w.build()
    assert run["execution"]["provider"] is None
    unavailable = {item["path"]: item["reason"] for item in run["observation_availability"]["unavailable"]}
    assert unavailable["execution.provider"] == "OBSERVATION_CONFLICT"
    assert run["execution"]["model_requested"] == "glm-5.3"
    assert "PRIVATE_OTHER_PROVIDER" not in json.dumps(w.projected)
    if len(w.bodies) == 3:
        attempts = w.projected["request_observation"]["transport"]["attempts"]
        assert [a["runtime_provider"] for a in attempts] == [
            transport._scalar(label, "model") for label in ("custom", "PRIVATE_OTHER_PROVIDER", "custom")]
    assert run["effect"]["state"] == "EFFECT_UNKNOWN" and run["validity"]["status"] != "VALID"


@pytest.mark.parametrize("wire_projection", ["raised_attempt"], indirect=True)
def test_raised_original_http_attempt_still_measures_runtime_selector_without_delivery(wire_projection):
    value = wire_projection.projected["request_observation"]["transport"]
    run = wire_projection.build()
    assert value["attempts"][0]["state"] == "raised" and value["attempts"][0]["response"] is None
    assert run["execution"]["provider"] == "custom" and run["execution"]["completion_status"] == "FAILED"
    assert run["execution"]["model_served"] is None
    assert value["provider_delivery_proven"] is value["model_identity_verified"] is False
    assert run["validity"]["status"] != "VALID"


@pytest.mark.parametrize("change", ["historical_v1", "dispatch_missing", "attempt_missing", "client_missing",
    "client_conflict", "dispatch_conflict", "attempt_conflict", "overflow", "entered", "missing_attempt"])
def test_provider_scalar_requires_every_retained_original_witness(wire_projection, change):
    from integrations.hermes_runtime import native_transport_observation as transport
    value = copy.deepcopy(wire_projection.projected)
    doc = value["request_observation"]["transport"]
    dispatch, attempt = doc["dispatches"][0], doc["attempts"][0]
    if change == "historical_v1":
        doc = value["request_observation"]["transport"] = historical_transport(doc)
    elif change == "dispatch_missing":
        dispatch["runtime_provider"] = {"status": "unobserved"}
        dispatch["provider_client_check"] = "unavailable"
    elif change == "attempt_missing":
        attempt["runtime_provider"] = {"status": "unobserved"}
    elif change == "client_missing":
        dispatch["provider_client_check"] = "unavailable"
    elif change == "client_conflict":
        dispatch["provider_client_check"] = "conflicting"
    elif change in {"dispatch_conflict", "attempt_conflict"}:
        target = dispatch if change == "dispatch_conflict" else attempt
        target["runtime_provider"] = transport._scalar("other-runtime-selector", "model")
    elif change == "overflow":
        doc["overflow"] = True
    elif change == "entered":
        dispatch.update(state="entered", finished_at_ms=None, duration_ms=None)
    else:
        doc["attempts"] = []
    assert transport.validate_document(doc) == doc
    run = wire_projection.build(value)
    assert run["execution"]["provider"] is None and run["validity"]["status"] != "VALID"
    unavailable = {item["path"]: item["reason"] for item in run["observation_availability"]["unavailable"]}
    assert unavailable["execution.provider"] == ("OBSERVATION_CONFLICT" if change.endswith("conflict") else "NOT_OBSERVED")
    if change == "historical_v1":
        assert run["execution"]["model_requested"] == "glm-5.3"
        assert run["randomness"]["seed"] == 0 and run["execution"]["reasoning_effort"] == "low"


def test_future_wall_clock_does_not_invent_time_or_block_honest_invalid_receipt(wire_projection):
    value = copy.deepcopy(wire_projection.projected)
    execution = value["request_observation"]["transport"]["execution"]
    execution["started_at_ms"] = execution["finished_at_ms"] = 4102444800000
    run = wire_projection.build(value)
    assert run["timing"]["started_at"] is run["timing"]["completed_at"] is None
    assert run["timing"]["monotonic_duration_ms"] == execution["duration_ms"]
    absent = {row["path"]: row["reason"] for row in run["observation_availability"]["unavailable"]}
    assert absent["timing.started_at"] == absent["timing.completed_at"] == "OBSERVATION_CONFLICT"


@pytest.fixture
def original_reader(original, monkeypatch):
    """Actual native lookup/retirement/result bodies, no private socket."""
    o = original
    compile_selected(o.a.patched["hermes_state_runtime.py"],
        {"find_session_admission", "get_session_admission"}, o.a.core, "hermes_state_runtime.py")
    runtime = __import__("hermes_state_runtime")
    vars(runtime).update({name: o.a.core[name] for name in ("find_session_admission", "get_session_admission")})
    source = Path(__file__).parent / "fixtures/request_observation/gateway__session_results.py.source"
    results = module(monkeypatch, "gateway.session_results", _admission=o.a.core["_admission"],
        _RESULT_PREFIX=o.a.terminal.RESULT_PREFIX, load_result=o.a.terminal.load_result)
    compile_selected(source.read_bytes(), {"admission_result"}, vars(results), str(source))
    db = SimpleNamespace(_read_ctx=o.a.db._read_ctx, close=lambda: None)
    monkeypatch.setattr(control, "_db", lambda _: db)
    params = {**o.params, "operation": "read_original", "admission_id": None}
    def read():
        return control._read_original(o.home, params, o.t.principal, role="mmmeta")
    return SimpleNamespace(o=o, params=params, read=read)


@pytest.mark.parametrize("expired", [False, True])
def test_lost_admission_reply_recovers_existing_identity_after_real_retirement(original_reader, expired):
    r, o = original_reader, original_reader.o
    o.finish()
    o.retire()
    if expired:
        o.a.retirement.time.time = lambda: 3000000
        o.a.db._execute_write(lambda conn: o.a.retirement.prune_retired_tombstones(conn))
    statements = []
    o.a.conn.set_trace_callback(statements.append)
    value = r.read()
    o.a.conn.set_trace_callback(None)
    assert value["status"] == "OBSERVED"
    assert value["admission"]["admission_id"] == o.row["admission_id"]
    assert value["evaluation_binding"] == o.params["evaluation_binding"]
    assert ("answer" not in value) if expired else value["answer"] == "original public answer"
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE"))
                   for sql in statements)
    assert o.a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 0
    # The recovered ID can select only the same publisher/frozen run.
    o.params["admission_id"] = value["admission"]["admission_id"]
    assert o.publish()["status"] == "PUBLISHED"


@pytest.mark.parametrize("bad", [None, {}, [], "", "foreign-admission", "x" * 9000])
def test_terminal_identity_pointer_never_creates_or_substitutes_an_original(original_reader, bad):
    r, o = original_reader, original_reader.o
    o.finish()
    o.retire()
    key = o.a.terminal.identity_key(o.t.principal, o.t.session, o.params["submission_id"])
    o.a.conn.execute("UPDATE state_meta SET value=? WHERE key=?", (json.dumps(bad), key))
    if bad == "foreign-admission":
        assert r.read()["status"] == "EFFECT_UNKNOWN"
    else:
        with pytest.raises(RuntimeRefusal, match="ORIGINAL_MISMATCH"):
            r.read()
    assert o.a.conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] == 0


@pytest.mark.parametrize("field,bad", [
    ("input_sha256", "0" * 64), ("evaluation_binding", {"run_id": "foreign", "binding_sha256": "0" * 64}),
])
def test_retired_recovery_still_requires_original_input_and_eval_binding(original_reader, field, bad):
    r, o = original_reader, original_reader.o
    o.finish()
    o.retire()
    r.params[field] = bad
    with pytest.raises(RuntimeRefusal, match="ORIGINAL_MISMATCH"):
        r.read()


def complete_historical_trial_fixture(original, monkeypatch, *, answer=" \nOriginal 原始 output\t\n"):
    """Explicit synthetic complete producer; never a current native observation.

    Actual admission, settlement, freeze, ArtifactStore and read owners execute.
    Only the historical complete producer facts are supplied at this fixture edge.
    """
    from tests.agent_eval_factories import build_run_draft_fields
    from scripts.agent_eval.validity import finalize_run_receipt
    o = original
    def fixture_producer(marker, receipt, projected, *, finalizer_ref, now, missing_reason):
        scenario, config = marker["scenario"], marker["configuration"]
        draft = build_run_draft_fields(scenario, config, {"experiment_id": "unused-fixture"},
            arm_id="fixture", replicate_index=1, run_id=marker["run_id"])
        draft.update(schema=inputs.contracts.RUN_DRAFT_SCHEMA_V3, comparison=copy.deepcopy(marker["comparison"]))
        draft["execution"].update(marker["producer"], completion_status="COMPLETED", termination_reason="NATIVE_COMPLETED")
        output = projected["terminal_metadata"]["output"]
        draft["evidence"]["output"] = {
            "artifact_ref": publication._original_ref(marker, receipt) + "#final_response",
            "digest": "sha256:" + output["sha256"]}
        draft["observation_availability"] = {"unavailable": [], "coverage": {
            key: {"status": "COMPLETE", "reason": None}
            for key in sorted(inputs.contracts.RUN_OBSERVATION_COVERAGE_KEYS)}}
        run = finalize_run_receipt(scenario, config, marker["experiment"], draft,
            validator_id=publication.VALIDATOR_ID, validator_version=publication.VALIDATOR_VERSION,
            validator_code_ref=finalizer_ref, validated_at=now, created_at=now)
        assert run["validity"]["status"] == "VALID"
        return run
    monkeypatch.setattr(publication, "_build_run", fixture_producer)
    o.finish(answer=answer)
    assert o.publish()["status"] == "PUBLISHED"
    return answer


def read_trial(original):
    o = original
    return publication.read_original_trial(o.runner, o.home,
        {**o.params, "operation": "read_evaluation_trial"}, o.t.principal, owner=o.t.owner, role="mmmeta")


def no_trial_writes(original, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("a trial read must not publish, create, admit or write")
    monkeypatch.setattr(original.a.db, "_execute_write", forbidden)
    monkeypatch.setattr(original.t.owner.store, "create", forbidden)
    monkeypatch.setattr(original.t.owner, "select", forbidden)
    monkeypatch.setattr(publication, "publish_original", forbidden)


@pytest.mark.parametrize("retired", [False, True])
def test_trial_read_joins_actual_frozen_store_and_original_output(original, monkeypatch, retired):
    from scripts.ohf.harness2_recursion import Trial
    o = original
    answer = complete_historical_trial_fixture(o, monkeypatch)
    if retired:
        o.retire()
    frozen = canonical_json_bytes(o.frozen())
    no_trial_writes(o, monkeypatch)
    response = read_trial(o)
    assert response["status"] == "TRIAL_OBSERVED"
    assert response["trial_summary"]["eligible_for_consumption"] is True
    assert response["trial_summary"]["run_id"] == o.marker["run_id"]
    trial = publication.decode_trial(response["trial"], admission_id=o.row["admission_id"],
        evaluation_binding=o.params["evaluation_binding"])
    assert type(trial) is Trial and trial.output == answer.encode("utf-8")
    from integrations.hermes_runtime import native_eval_operator as operator
    recovery = {"schema": operator.RECOVERY_SCHEMA, "run_id": o.marker["run_id"],
        **{key: value for key, value in o.params.items() if key != "operation"}}
    receipt, summary = operator._trial_response(response, recovery, o.home,
        expected_admission=response["admission"])
    assert receipt == response["admission"] and summary == response["trial_summary"]
    assert trial.run == o.t.owner.store.resolve_run(o.marker["run_id"])
    assert canonical_json_bytes(o.frozen()) == frozen
    # Returned data is detached from the frozen publication and store.
    response["trial"]["run"]["execution"]["model_served"] = "caller-change"
    assert canonical_json_bytes(o.frozen()) == frozen


@pytest.mark.parametrize("outcome,answer", [
    ("completed", "original public answer"), ("completed", ""), ("failed", ""),
    ("failed", "x" * (control.MAX_ANSWER_BYTES + 1)),
])
def test_trial_read_preserves_current_invalid_run_without_returning_trial_or_answer(
        original, monkeypatch, outcome, answer):
    o = original
    o.finish(outcome, answer=answer)
    o.publish()
    no_trial_writes(o, monkeypatch)
    def cannot_construct(*_args, **_kwargs):
        pytest.fail("ineligible original evidence must keep its summary without constructing a Trial")
    monkeypatch.setattr(publication, "decode_trial", cannot_construct)
    response = read_trial(o)
    assert response["status"] == "REFUSED"
    assert response["reason"] == "NATIVE_EFFECT_REQUIRES_RECONCILIATION"
    assert response["trial_summary"] == publication._trial_summary(o.frozen()["run"],
        eligible=False, reason=response["reason"])
    assert response["trial_summary"]["validity"] == "INVALID_EFFECT_UNKNOWN"
    assert "trial" not in response and b"original public answer" not in canonical_json_bytes(response)


@pytest.mark.parametrize("boundary,reason", [
    ("empty", "NATIVE_EVAL_TRIAL_OUTPUT_CONFLICT"),
    ("limit", "NATIVE_EVAL_TRIAL_DOCUMENT_LIMIT"),
    ("privacy", "NATIVE_EVAL_TRIAL_EVIDENCE_INVALID"),
])
def test_trial_read_preserves_valid_run_summary_when_output_cannot_be_consumed(
        original, monkeypatch, boundary, reason):
    o = original
    complete_historical_trial_fixture(o, monkeypatch, answer="" if boundary == "empty" else "public output")
    if boundary == "limit":
        monkeypatch.setattr(publication, "MAX_TRIAL_BYTES", 1)
    elif boundary == "privacy":
        original_check = publication.assert_public_safe_evidence
        def privacy_refusal(value):
            if isinstance(value, dict) and value.get("schema") == publication.TRIAL_SCHEMA:
                raise ContractError([ContractDefect("$.output", "PRIVACY_FIXTURE", "fixture privacy boundary refusal")])
            return original_check(value)
        monkeypatch.setattr(publication, "assert_public_safe_evidence", privacy_refusal)
    no_trial_writes(o, monkeypatch)
    response = read_trial(o)
    assert response["status"] == "REFUSED" and response["reason"] == reason
    assert response["trial_summary"] == publication._trial_summary(o.frozen()["run"], eligible=False, reason=reason)
    assert response["trial_summary"]["validity"] == "VALID" and "trial" not in response
    from integrations.hermes_runtime import native_eval_operator as operator
    recovery = {"schema": operator.RECOVERY_SCHEMA, "run_id": o.marker["run_id"],
        **{key: value for key, value in o.params.items() if key != "operation"}}
    _, summary = operator._trial_response(response, recovery, o.home, expected_admission=response["admission"])
    assert summary == response["trial_summary"]


def test_trial_read_does_not_repair_a_frozen_but_unpublished_run(original, monkeypatch):
    o = original
    o.finish()
    monkeypatch.setattr(o.t.owner.store, "create", lambda *_: (_ for _ in ()).throw(OSError("fixture publication loss")))
    with pytest.raises(publication.PublicationEffectUnknown):
        o.publish()
    assert o.frozen() is not None and o.t.owner.store.resolve_run(o.marker["run_id"]) is None
    no_trial_writes(o, monkeypatch)
    with pytest.raises(RuntimeRefusal, match="TRIAL_ARTIFACT_NOT_RETAINED"):
        read_trial(o)
    assert o.t.owner.store.resolve_run(o.marker["run_id"]) is None


def test_trial_read_refuses_actual_output_expiry_despite_surviving_publication(original, monkeypatch):
    o = original
    complete_historical_trial_fixture(o, monkeypatch)
    o.retire()
    o.a.retirement.time.time = lambda: 3000000
    o.a.db._execute_write(lambda conn: o.a.retirement.prune_retired_tombstones(conn))
    assert o.a.conn.execute("SELECT 1 FROM state_meta WHERE key=?",
        (o.a.terminal.RESULT_PREFIX + o.row["admission_id"],)).fetchone() is None
    assert o.frozen() is not None
    no_trial_writes(o, monkeypatch)
    response = read_trial(o)
    assert response["status"] == "REFUSED" and response["reason"] == "NATIVE_EVAL_TRIAL_OUTPUT_NOT_RETAINED"
    assert response["trial_summary"]["validity"] == "VALID"
    assert response["trial_summary"]["eligible_for_consumption"] is False and "trial" not in response


@pytest.mark.parametrize("change", ["run", "scenario", "root", "principal", "mid-read-owner"])
def test_trial_read_refuses_changed_original_graph_or_owner(original, monkeypatch, change):
    o = original
    complete_historical_trial_fixture(o, monkeypatch)
    if change == "run":
        run = copy.deepcopy(o.frozen()["run"])
        run["execution"]["model_served"] = "changed"
        monkeypatch.setattr(o.t.owner.store, "resolve_run", lambda *_: run)
    elif change == "scenario":
        scenario = copy.deepcopy(o.marker["scenario"])
        scenario["objective"] += " changed"
        monkeypatch.setattr(o.t.owner.store, "resolve_scenario", lambda *_: scenario)
    elif change == "root":
        o.t.owner.publication = copy.deepcopy(o.t.owner.publication)
        o.t.owner.publication["root_identity"]["inode"] += 1
    elif change == "principal":
        o.t.principal = "foreign"
    else:
        original_resolver = o.t.owner.store.resolve_run
        def changed(run_id):
            result = original_resolver(run_id)
            o.runner.session_authority = SimpleNamespace(db=o.a.db, profile_id=o.t.owner.profile_id, epoch=2)
            return result
        monkeypatch.setattr(o.t.owner.store, "resolve_run", changed)
    no_trial_writes(o, monkeypatch)
    with pytest.raises(RuntimeRefusal):
        read_trial(o)


def test_trial_read_refuses_changed_original_output_bytes(original, monkeypatch):
    o = original
    complete_historical_trial_fixture(o, monkeypatch)
    key = o.a.terminal.RESULT_PREFIX + o.row["admission_id"]
    raw = o.a.conn.execute("SELECT value FROM state_meta WHERE key=?", (key,)).fetchone()[0]
    saved = o.a.terminal.load_result(raw)
    saved["result"]["final_response"] = "different output"
    o.a.conn.execute("UPDATE state_meta SET value=? WHERE key=?", (json.dumps(o.a.terminal.encode_result(saved)), key))
    no_trial_writes(o, monkeypatch)
    response = read_trial(o)
    assert response["status"] == "REFUSED" and response["reason"] == "NATIVE_EVAL_TRIAL_OUTPUT_CONFLICT"
    assert "trial" not in response


@pytest.mark.parametrize("change", ["admission", "binding", "stage", "output", "field", "limit"])
def test_trial_decoder_cannot_move_evidence_or_truncate_it(original, monkeypatch, change):
    o = original
    complete_historical_trial_fixture(o, monkeypatch)
    response = read_trial(o)
    document = response["trial"]
    admission, binding = o.row["admission_id"], copy.deepcopy(o.params["evaluation_binding"])
    if change == "admission":
        admission = "other-admission"
    elif change == "binding":
        binding["binding_sha256"] = "b" * 64
    elif change == "stage":
        document["output"]["stage"] = "raw_response"
    elif change == "output":
        document["output"]["text"] += " "
    elif change == "field":
        document["grant"] = True
    else:
        monkeypatch.setattr(publication, "MAX_TRIAL_BYTES", 1)
    with pytest.raises(RuntimeRefusal):
        publication.decode_trial(document, admission_id=admission, evaluation_binding=binding)


def test_trial_private_read_loss_is_unavailable_and_uses_the_original_handler(original, monkeypatch):
    o = original
    o.finish()
    o.publish()
    async def install():
        control.install_private_control(o.runner, o.home, "mmmeta", evaluation_owner=o.t.owner)
    asyncio.run(install())
    handler = o.runner.session_control_server.private_handlers[control.conversation_contract("mmmeta").native_verb]
    request = {**o.params, "operation": "read_evaluation_trial"}
    assert handler(request, "foreign")["status"] == "REFUSED"
    no_trial_writes(o, monkeypatch)
    response = handler(request, o.t.principal)
    assert response["status"] == "REFUSED" and "trial_summary" in response
    monkeypatch.setattr(o.t.owner.store, "resolve_run", lambda *_: (_ for _ in ()).throw(TimeoutError("read loss")))
    assert handler(request, o.t.principal)["status"] == "UNAVAILABLE"
