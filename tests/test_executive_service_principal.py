"""Acceptance tests for the A1 typified NON-CEO service principal.

Hermetic: stdlib + pytest + ``tmp_path`` only.  No installed service, no socket,
no network, no provider, no credential, no global ``subprocess`` patch, no real
Job outside the in-repo runtime temp database.

The point of this file is twofold:

1. prove the closed identity/authority shape of the tier, and
2. PIN THE BLOCKER: the existing single mutation sink cannot durably carry the
   typed service-principal provenance schema or a ``task_kind`` marker, and these
   tests trigger the real refusals rather than trusting a documented string.

Repair round 2 adds three more laws to prove:

* **A1** - the intent id is a hash of exactly (schema, principal_id,
  operation_key), so a changed objective or a changed grounding SHA for the same
  logical operation is the sink's existing whole-envelope conflict, never a
  second Job;
* **A2** - the typed block states the WRITE ceiling (``write_authorities``, always
  empty) *and* the truthful READ/RESEARCH grant (``requested_authorities`` /
  ``effective_authorities``), with drift refused in both directions; and
* **A3** - ``submit()`` fails closed while the tier is ``NOT_YET_ADMITTED``.
  Because of A3 the reachable-sink proof lives HERE, calling the unchanged sink
  directly (``test_hermetic_sink_reachability_proof_*``), so no production-facing
  callable mutates Runtime in this state.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

from control_plane import ceo_intent
from control_plane import executive_service_principal as esp
from control_plane.ceo_intent import (
    INTENT_SCHEMA,
    CeoIntentConflict,
    CeoIntentError,
    command_id_for,
    submit_intent,
)
from control_plane.executive_runtime import (
    JobRegistry,
    JobStatus,
    Runtime,
    StateConflict,
    _has_executive_provenance,
)
from control_plane.executive_service_principal import (
    ADMITTED,
    ALLOWED_TASK_KINDS,
    INTENT_ID_PREFIX,
    NOT_YET_ADMITTED,
    READ_OPERATIONS,
    REGISTRY,
    SCHEMA,
    SERVICE_SEAT,
    TASK_KIND,
    ServicePrincipal,
    ServicePrincipalNotAdmitted,
    ServicePrincipalRefused,
    admission_status,
    command_id,
    derive_intent,
    durable_provenance,
    fingerprint,
    service_principal,
    submit,
    validate_grant,
    validate_provenance,
)

_ROOT = Path(__file__).resolve().parent.parent
_MASTERMIND_SHA = "1" * 40
_MACRO_SHA = "2" * 40
_GROUNDING = {"mastermind_sha": _MASTERMIND_SHA, "macro_sha": _MACRO_SHA}

_PROPOSED_ENVELOPE_KEYS = {
    "schema",
    "intent_id",
    "actor",
    "objective",
    "department",
    "priority",
    "grounding",
    "execution_contract",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _request(**overrides) -> dict:
    """A harmless READ/RESEARCH audit request in the sink's review vocabulary."""

    request = {
        "operation_key": "site-health-audit",
        "objective": "Audit published site and source health for the VPS site.",
        "department": "executive-infrastructure",
        "priority": 3,
        "execution_profile": "research_only",
        "grounding": dict(_GROUNDING),
    }
    request.update(overrides)
    return request


def _principal() -> ServicePrincipal:
    return service_principal("svc-site-maintenance")


def _derived(**overrides) -> dict:
    return derive_intent(_principal(), _request(**overrides), now=0)


def _sink_submit(runtime, request: dict | None = None):
    """The hermetic reachability path: the UNCHANGED sink, called directly.

    ``submit()`` is deliberately closed while the tier is ``NOT_YET_ADMITTED``
    (A3), so the reachable part of this tier is exercised here, where the test
    owns the call, instead of through a production-facing callable that would
    mutate Runtime while unadmitted.
    """

    derived = derive_intent(_principal(), request if request is not None else _request(), now=0)
    return submit_intent(runtime, derived["envelope"])


def _source_lines(relative: str) -> list[str]:
    return (_ROOT / relative).read_text(encoding="utf-8").splitlines()


def _source_window(relative: str, first: int, last: int) -> str:
    """1-based inclusive slice of a source file, as the line numbers are cited."""

    return "\n".join(_source_lines(relative)[first - 1 : last])


# ---------------------------------------------------------------------------
# 1. closed schema — drift, unknown ids, actor shape, reserved identities
# ---------------------------------------------------------------------------


def test_closed_schema_refuses_drift_unknown_ids_and_reserved_actors():
    derived = _derived()
    assert set(derived) == {
        "schema", "intent_id", "envelope", "provenance", "admission", "derived_at_ms",
    }
    assert derived["schema"] == SCHEMA
    assert set(derived["envelope"]) <= _PROPOSED_ENVELOPE_KEYS | {"workstream"}
    assert set(derived["provenance"]) == {
        "schema",
        "actor",
        "principal_id",
        "task_kind",
        "write_authorities",
        "requested_authorities",
        "effective_authorities",
    }

    # unknown principal id
    with pytest.raises(ServicePrincipalRefused, match="unknown principal id"):
        service_principal("svc-rogue-maintenance")

    # the registered principal's own block is canonical and accepted
    assert validate_provenance(dict(derived["provenance"])) == derived["provenance"]

    # drift in either direction is refused
    for mutate, match in (
        (lambda block: block.__setitem__("note", "extra"), "unexpected key"),
        (lambda block: block.pop("task_kind"), "missing required key"),
        (lambda block: block.__setitem__("schema", INTENT_SCHEMA), "provenance.schema must be"),
        (lambda block: block.__setitem__("task_kind", "implementation"), "task_kind must be"),
        (lambda block: block.__setitem__("write_authorities", ["WRITE_BRANCH"]), "must be empty"),
        (lambda block: block.__setitem__("requested_authorities", ["READ"]), "requested_authorities"),
        (lambda block: block.__setitem__("effective_authorities", ["READ"]), "effective_authorities"),
        (lambda block: block.__setitem__("actor", "svc-other"), "does not match registered"),
        (lambda block: block.__setitem__("principal_id", "svc-rogue"), "unknown principal id"),
    ):
        block = dict(derived["provenance"])
        mutate(block)
        with pytest.raises(ServicePrincipalRefused, match=match):
            validate_provenance(block)

    # actor shape: the module's pattern is the sink's pattern, not a look-alike
    assert ceo_intent._ACTOR_RE.pattern == __import__(
        "control_plane.executive_service_principal", fromlist=["_ACTOR_RE"]
    )._ACTOR_RE.pattern

    for actor in ("", "x", "-leading-dash", "has space", "bad/name", "a" * 65, 7):
        with pytest.raises(
            ServicePrincipalRefused,
            match="bounded identifier|must be a string|must not be empty",
        ):
            ServicePrincipal(
                principal_id="svc-shape", actor=actor, purpose="shape probe"
            )

    # reserved identities: the CEO stamp and the human/attributed seats
    for actor in ("ceo-sol", "CEO_SOL", "ceo.sol", "chairman", "chairman-chris", "chris", "operator"):
        with pytest.raises(ServicePrincipalRefused, match="reserved identity"):
            ServicePrincipal(principal_id="svc-x", actor=actor, purpose="reserved probe")


# ---------------------------------------------------------------------------
# 2. READ/RESEARCH only
# ---------------------------------------------------------------------------


def test_read_only_ceiling_refuses_write_authority_and_foreign_task_kinds():
    # non-research task kinds are refused at construction
    for kinds in ({"implementation"}, {"research", "tests"}, {"mechanical"}, {"review"}):
        with pytest.raises(ServicePrincipalRefused, match="only the reviewed task kind|refused"):
            ServicePrincipal(
                principal_id="svc-kinds", actor="svc-kinds", purpose="kind probe",
                allowed_task_kinds=frozenset(kinds),
            )
    assert ALLOWED_TASK_KINDS == frozenset({TASK_KIND})

    # any write authority is refused, and the refusal names it
    for operations in (
        {"READ", "RESEARCH", "WRITE_BRANCH"},
        {"RUN_TESTS"},
        {"MERGE"},
        {"READ", "DEPLOY"},
    ):
        with pytest.raises(ServicePrincipalRefused, match="write authority is not available"):
            ServicePrincipal(
                principal_id="svc-ops", actor="svc-ops", purpose="op probe",
                allowed_operations=frozenset(operations),
            )
    assert READ_OPERATIONS == frozenset({"READ", "RESEARCH"})

    # a seat outside coo is refused in both directions
    for field, value in (("owner_seat", "ceo"), ("escalation_target", "chairman")):
        with pytest.raises(ServicePrincipalRefused, match="must be 'coo'"):
            ServicePrincipal(
                principal_id="svc-seat", actor="svc-seat", purpose="seat probe", **{field: value}
            )

    # the write profile, declared write paths, and validation commands are refused
    with pytest.raises(ServicePrincipalRefused, match="execution_profile must be 'research_only'"):
        _derived(
            execution_profile="bounded_code_change",
            allowed_write_paths=["docs/service-principal-probe.md"],
            validation={"pytest_targets": ["tests/test_service_principal_probe.py"]},
        )
    for kwargs in (
        {"allowed_write_paths": ["docs/x.md"]},
        {"validation": {"pytest_targets": ["tests/test_x.py"]}},
    ):
        # The existing research_only profile refuses these before this module's own
        # "may not declare" guard is reached ("grants no write authority" for paths,
        # "grants no test authority" for validation); either refusal is a refusal, so
        # the test accepts all three and never asserts which layer fired first.
        with pytest.raises(
            ServicePrincipalRefused, match="may not declare|grants no write authority|grants no test authority"
        ):
            _derived(**kwargs)

    # the derived envelope requests exactly READ/RESEARCH and carries no write path
    envelope = _derived()["envelope"]
    contract = envelope["execution_contract"]
    assert contract["requested_authorities"] == ["READ", "RESEARCH"]
    assert "allowed_write_paths" not in contract
    assert "validation_commands" not in contract
    assert "worktree" not in contract and "branch" not in contract


# ---------------------------------------------------------------------------
# 3. authority is refused independently of actor (mirrors tests/test_ceo_intent.py:492-501)
# ---------------------------------------------------------------------------


def test_authority_is_refused_independently_of_actor(tmp_path: Path):
    """The service principal's actor is provenance, not privilege."""

    runtime = Runtime.at(tmp_path / "runtime")
    for actor in (_principal().actor, "ceo-sol"):
        envelope = copy.deepcopy(_derived()["envelope"])
        envelope["actor"] = actor
        envelope["intent_id"] = f"svc-esp-{actor.replace('-', '').replace('_', '')}"
        envelope["execution_contract"] = {"requested_authorities": ["MERGE"]}
        with pytest.raises(CeoIntentError, match="authority is denied"):
            submit_intent(runtime, envelope)
    assert runtime.jobs.list_jobs() == []

    # the caller cannot name its own identity or authority, structurally
    for privileged in ("actor", "schema", "requested_authorities", "authority_level"):
        with pytest.raises(ServicePrincipalRefused, match="refused by the existing normalizer"):
            derive_intent(_principal(), _request(**{privileged: "anything"}), now=0)


# ---------------------------------------------------------------------------
# 4. hermetic sink reachability — the UNCHANGED sink, called directly (A3 move)
# ---------------------------------------------------------------------------


def test_hermetic_sink_reachability_proof_one_coo_job_no_dispatch_and_duplicate(tmp_path: Path):
    """What this tier CAN reach today, proven against the real sink.

    ``submit()`` is closed while unadmitted (A3), so the proof calls
    ``control_plane.ceo_intent.submit_intent`` directly - the same envelope
    ``derive_intent`` returns - and asserts the whole reachable contract.
    """

    request = _request()
    runtime = Runtime.at(tmp_path / "runtime")
    first = _sink_submit(runtime, request)
    second = _sink_submit(runtime, request)

    assert first["accepted"] is True
    assert first["dispatched"] is False
    assert first["status"] == JobStatus.QUEUED.value
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["job_id"] == first["job_id"]
    assert second["fingerprint"] == first["fingerprint"]
    assert first["intent_id"].startswith(INTENT_ID_PREFIX)

    reader = Runtime.at(tmp_path / "runtime")
    jobs = reader.jobs.list_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.job_id == first["job_id"]
    assert job.status is JobStatus.QUEUED
    assert job.owner_seat == SERVICE_SEAT == "coo"
    assert job.escalation_target == SERVICE_SEAT
    assert job.requested_authorities == ["READ", "RESEARCH"]

    # No dispatch: the sink never starts work, and nothing here can.
    assert job.attempt_count == 0
    assert job.current_attempt_id is None

    # Fingerprint/command-id identity is the sink's own derivation, reused.
    derived = _derived()
    assert fingerprint(derived) == ceo_intent.intent_fingerprint(derived["envelope"])
    assert command_id(derived) == command_id_for(derived["intent_id"])

    # Provenance lands in the EVENT PAYLOAD, never in the events.actor column.
    durable = durable_provenance(reader, job.job_id)
    assert durable["events_actor"] == "operator"
    assert durable["command_id"] == command_id(derived)
    provenance = durable["provenance"]
    assert provenance["actor"] == _principal().actor
    assert provenance["fingerprint"] == first["fingerprint"]
    assert provenance["grounding"] == _GROUNDING
    assert len([e for e in reader.events.list_events(job_id=job.job_id) if e.event_type == "JOB_CREATED"]) == 1

    # ...and the production-facing path is closed, so this tier cannot mutate
    # Runtime through it while the verdict stands (A3, detail in section 7).
    with pytest.raises(ServicePrincipalNotAdmitted):
        submit(_principal(), request, runtime)
    assert len(Runtime.at(tmp_path / "runtime").jobs.list_jobs()) == 1


# ---------------------------------------------------------------------------
# 5. A1 — STABLE LOGICAL-OPERATION IDENTITY
# ---------------------------------------------------------------------------


def test_a1_intent_id_depends_only_on_principal_and_operation_key():
    base = _derived()
    changed_objective = _derived(objective="A completely different objective for the same audit.")
    changed_grounding = _derived(grounding={"mastermind_sha": "a" * 40, "macro_sha": "b" * 40})
    other_operation = _derived(operation_key="source-health-audit")

    # same principal + same operation_key => same intent id, whatever else moved
    assert base["intent_id"] == changed_objective["intent_id"]
    assert base["intent_id"] == changed_grounding["intent_id"]
    assert command_id(base) == command_id(changed_objective)
    # a different operation_key is a different logical operation
    assert other_operation["intent_id"] != base["intent_id"]
    assert base["intent_id"].startswith(INTENT_ID_PREFIX)

    # The whole-envelope fingerprint DOES move: that difference is the conflict
    # the sink adjudicates, not a second identity this module invents.
    assert fingerprint(base) != fingerprint(changed_objective)
    assert fingerprint(base) != fingerprint(changed_grounding)

    # The quoted sink predicates this law relies on are still where we cite them.
    assert "find_event_by_command_id(command_id)" in _source_window(
        "control_plane/ceo_intent.py", 984, 990
    )
    assert "if fingerprint is not None and recorded != fingerprint:" in _source_window(
        "control_plane/ceo_intent.py", 783, 790
    )
    assert 'return f"{COMMAND_ID_PREFIX}{intent_id}"' in _source_window(
        "control_plane/ceo_intent.py", 660, 666
    )
    pins = admission_status()["identity"]["conflict_predicates"]
    assert {pin["line"] for pin in pins} == {"L986", "L785", "L662"}
    for pin in pins:
        assert pin["file"] == "control_plane/ceo_intent.py"


def test_a1_duplicate_changed_objective_and_changed_grounding_stay_one_job(tmp_path: Path):
    """(i) duplicate -> same Job; (ii)/(iii) same operation, changed envelope -> conflict."""

    runtime = Runtime.at(tmp_path / "runtime")
    base = _derived()["envelope"]
    first = submit_intent(runtime, copy.deepcopy(base))
    assert first["accepted"] is True
    assert first["duplicate"] is False
    first_command_id = command_id_for(base["intent_id"])

    # (i) exact duplicate: same Job, reconciled (duplicate=true), no second event
    again = submit_intent(runtime, copy.deepcopy(base))
    assert again["duplicate"] is True
    assert again["job_id"] == first["job_id"]
    assert again["fingerprint"] == first["fingerprint"]

    # (ii)/(iii) changed objective / changed grounding SHAs under the SAME
    # principal + operation_key: same intent id, same durable command id, a
    # DIFFERENT whole-envelope fingerprint, so the sink's own conflict predicate
    # refuses instead of minting a second Job.
    for changed_request in (
        _request(objective="A different objective for the same logical operation."),
        _request(grounding={"mastermind_sha": "a" * 40, "macro_sha": "b" * 40}),
    ):
        changed = derive_intent(_principal(), changed_request, now=0)["envelope"]
        assert changed["intent_id"] == base["intent_id"]
        assert command_id_for(changed["intent_id"]) == first_command_id
        with pytest.raises(CeoIntentConflict, match="already accepted with a different envelope"):
            submit_intent(runtime, changed)

    reader = Runtime.at(tmp_path / "runtime")
    jobs = reader.jobs.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_id == first["job_id"]
    assert len(
        [e for e in reader.events.list_events(job_id=first["job_id"]) if e.event_type == "JOB_CREATED"]
    ) == 1


def test_a1_different_operation_key_gets_a_second_job_and_command_id(tmp_path: Path):
    runtime = Runtime.at(tmp_path / "runtime")
    first_envelope = _derived()["envelope"]
    second_envelope = _derived(operation_key="source-health-audit")["envelope"]

    first = submit_intent(runtime, first_envelope)
    second = submit_intent(runtime, second_envelope)

    assert first["job_id"] != second["job_id"]
    assert first["fingerprint"] != second["fingerprint"]
    assert command_id_for(first_envelope["intent_id"]) != command_id_for(second_envelope["intent_id"])
    assert {job.job_id for job in Runtime.at(tmp_path / "runtime").jobs.list_jobs()} == {
        first["job_id"],
        second["job_id"],
    }


# ---------------------------------------------------------------------------
# 6. A2 — TRUTHFUL GRANT IN THE TYPED BLOCK (write ceiling + READ/RESEARCH grant)
# ---------------------------------------------------------------------------


def test_a2_typed_block_states_the_write_ceiling_and_the_reviewed_read_grant():
    block = _derived()["provenance"]
    assert block["write_authorities"] == []
    assert block["requested_authorities"] == ["READ", "RESEARCH"]
    assert block["effective_authorities"] == ["READ", "RESEARCH"]
    assert validate_provenance(dict(block)) == block
    assert validate_grant(_derived()) == block

    contract = _derived()["envelope"]["execution_contract"]
    assert contract["requested_authorities"] == block["requested_authorities"]
    assert contract["requested_authorities"] == block["effective_authorities"]


def test_a2_block_grant_drift_from_the_registry_is_refused():
    for mutate, match in (
        (lambda b: b.__setitem__("requested_authorities", ["READ"]), "requested_authorities"),
        (lambda b: b.__setitem__("effective_authorities", ["READ"]), "effective_authorities"),
        (
            lambda b: b.__setitem__("requested_authorities", ["READ", "RESEARCH", "RUN_TESTS"]),
            "requested_authorities",
        ),
        (lambda b: b.__setitem__("write_authorities", ["WRITE_BRANCH"]), "must be empty"),
        (lambda b: b.__setitem__("requested_authorities", "READ,RESEARCH"), "must be a list"),
        (lambda b: b.__setitem__("effective_authorities", []), "must not be empty"),
    ):
        block = dict(_derived()["provenance"])
        mutate(block)
        with pytest.raises(ServicePrincipalRefused, match=match):
            validate_provenance(block)
        tampered = copy.deepcopy(_derived())
        tampered["provenance"] = block
        with pytest.raises(ServicePrincipalRefused, match=match):
            validate_grant(tampered)


def test_a2_envelope_grant_drift_from_the_block_is_refused_before_any_sink_call(
    monkeypatch, tmp_path: Path
):
    sink_calls: list = []
    monkeypatch.setattr(ceo_intent, "submit_intent", lambda *a, **k: sink_calls.append(a))

    for granted, match in (
        (["READ"], "envelope.execution_contract.requested_authorities"),
        (["READ", "RESEARCH", "WRITE_BRANCH"], "envelope requests write authority"),
        ([], "must not be empty"),
    ):
        tampered = copy.deepcopy(_derived())
        tampered["envelope"]["execution_contract"]["requested_authorities"] = granted
        with pytest.raises(ServicePrincipalRefused, match=match):
            validate_grant(tampered)

    # An unknown contract key (a write path, an argv validation) is refused too.
    tampered = copy.deepcopy(_derived())
    tampered["envelope"]["execution_contract"]["allowed_write_paths"] = ["docs/x.md"]
    with pytest.raises(ServicePrincipalRefused, match="unexpected key"):
        validate_grant(tampered)

    # The pre-sink ORDER is pinned in source: derive -> validate_grant -> gate -> sink.
    source = (_ROOT / "control_plane" / "executive_service_principal.py").read_text(encoding="utf-8")
    submit_body = source.split("def submit(", 1)[1]
    assert submit_body.index("validate_grant(derived)") < submit_body.index("ceo_intent.submit_intent(")

    # ...and a normal request cannot reach the monkeypatched sink either (A3).
    with pytest.raises(ServicePrincipalNotAdmitted):
        submit(_principal(), _request(), object())
    assert sink_calls == []


# ---------------------------------------------------------------------------
# 7. A3 — FAIL CLOSED WHILE NOT_YET_ADMITTED
# ---------------------------------------------------------------------------


def test_a3_submit_fails_closed_while_not_yet_admitted(monkeypatch, tmp_path: Path):
    status = admission_status()
    assert status["status"] == NOT_YET_ADMITTED

    sink_calls: list = []
    monkeypatch.setattr(ceo_intent, "submit_intent", lambda *a, **k: sink_calls.append(a))

    # (a) the typed refusal, with the blocker predicates in the message.  A
    #     sentinel runtime is passed on purpose: reading it at all would raise
    #     AttributeError, so this proves the refusal precedes ANY runtime access.
    with pytest.raises(ServicePrincipalNotAdmitted) as caught:
        submit(_principal(), _request(), object())
    message = str(caught.value)
    assert "NOT_YET_ADMITTED" in message
    assert status["reason"] in message
    for predicate in status["predicates"]:
        assert predicate["file"] in message
        assert predicate["line"] in message
    assert sink_calls == []

    # (b) a REAL runtime is untouched too.
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(ServicePrincipalNotAdmitted):
        submit(_principal(), _request(), runtime)
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []
    assert sink_calls == []

    # (c) the gate is a live read of the admission verdict, not a hard-coded
    #     refusal: with an ADMITTED verdict the same call reaches the sink.  This
    #     is the positive control that the tier's path is blocked by admission
    #     ONLY, and it never touches a real runtime (the sink is monkeypatched).
    monkeypatch.setattr(esp, "admission_status", lambda: dict(status, status=ADMITTED))
    sentinel = {"accepted": True}
    monkeypatch.setattr(ceo_intent, "submit_intent", lambda *a, **k: sink_calls.append(a) or sentinel)
    assert submit(_principal(), _request(), object()) == sentinel
    assert len(sink_calls) == 1


def test_a3_no_other_module_level_callable_submits_anyway():
    """Exactly one module-level callable reaches the sink, and it is the gated one."""

    source = (_ROOT / "control_plane" / "executive_service_principal.py").read_text(encoding="utf-8")
    callers = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            target = inner.func
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
            if name in {"submit_intent", "create_job", "create_v2_orchestration_root"}:
                callers.add(node.name)
    assert callers == {"submit"}


# ---------------------------------------------------------------------------
# 8. no CEO identity is ever emitted
# ---------------------------------------------------------------------------


def test_emitted_provenance_never_carries_a_ceo_identity(tmp_path: Path):
    request = _request()
    runtime = Runtime.at(tmp_path / "runtime")
    receipt = _sink_submit(runtime, request)
    reader = Runtime.at(tmp_path / "runtime")
    emitted = json.dumps(
        {
            "derived": _derived(),
            "receipt": receipt,
            "admission": admission_status(),
            "durable": durable_provenance(reader, receipt["job_id"]),
        },
        sort_keys=True,
    ).lower()
    for forbidden in ("ceo-sol", "ceo_sol", "chairman", "chris"):
        assert forbidden not in emitted

    # The module never reaches for the CEO stamp or the CEO envelope builder.
    source = (_ROOT / "control_plane" / "executive_service_principal.py").read_text(
        encoding="utf-8"
    )
    reached = {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    assert "ACTOR" not in reached
    assert "build_trusted_envelope" not in reached
    assert "ceo_request.ACTOR" not in source.replace("control_plane.ceo_request.ACTOR", "@@")

    # And the CEO stamp is still exactly where the census says it is.
    assert '"ceo-sol"' in _source_window("control_plane/ceo_request.py", 130, 140)


# ---------------------------------------------------------------------------
# 9. the pinned blocker — the sink cannot carry the typed schema or task_kind
# ---------------------------------------------------------------------------


def test_sink_cannot_carry_the_typed_schema_or_task_kind(tmp_path: Path):
    """NOT_YET_ADMITTED, proven by triggering the exact refusing predicates."""

    status = admission_status()
    assert status["status"] == NOT_YET_ADMITTED != ADMITTED
    assert _derived()["admission"]["status"] == NOT_YET_ADMITTED

    runtime = Runtime.at(tmp_path / "runtime")
    derived = _derived()

    # (a) the typed schema is refused: the sink admits only the CEO intent schemas.
    typed = copy.deepcopy(derived["envelope"])
    typed["schema"] = SCHEMA
    with pytest.raises(CeoIntentError, match="intent.schema must be"):
        submit_intent(runtime, typed)

    # (b) the typed block cannot ride inside the envelope: exact-key-set refusal.
    with_block = copy.deepcopy(derived["envelope"])
    with_block["provenance"] = dict(derived["provenance"])
    with pytest.raises(CeoIntentError, match=r"unexpected key\(s\): \['provenance'\]"):
        submit_intent(runtime, with_block)

    # (c) task_kind has no carrier in the envelope, and no parameter on create_job.
    with_kind = copy.deepcopy(derived["envelope"])
    with_kind["execution_contract"] = dict(
        with_kind["execution_contract"], constraints={"task_kind": TASK_KIND}
    )
    with pytest.raises(CeoIntentError, match=r"unexpected key\(s\): \['task_kind'\]"):
        submit_intent(runtime, with_kind)
    assert "task_kind" not in inspect.signature(JobRegistry.create_job).parameters
    assert runtime.jobs.list_jobs() == []

    # (d) what IS reachable: the actor, durably, with the sink's own schema stamp.
    receipt = _sink_submit(runtime)
    reader = Runtime.at(tmp_path / "runtime")
    durable = durable_provenance(reader, receipt["job_id"])
    assert durable["provenance"]["actor"] == _principal().actor
    assert durable["provenance"]["schema"] == INTENT_SCHEMA
    assert durable["provenance"]["schema"] != SCHEMA
    assert SCHEMA not in json.dumps(durable)

    # (e) the recorded path:line evidence must still describe the real code.
    #     The module's pins are ``L<number>`` STRINGS, never bare integer
    #     literals: the D8 identity ratchet flags unexplained 4xx-9xx integers
    #     in added production source, and a source-line citation is not an
    #     identity.  The predicates below are unchanged.
    windows = {
        "L561": _source_window("control_plane/ceo_intent.py", 555, 575),
        "L562": _source_window("control_plane/ceo_intent.py", 555, 575),
        "L735": _source_window("control_plane/ceo_intent.py", 730, 745),
        "L163": _source_window("control_plane/ceo_intent.py", 160, 175),
    }
    assert "intent.schema must be" in windows["L561"]
    assert "_exact_keys" in windows["L562"] or "exact_keys" in windows["L562"]
    assert '"schema": intent["schema"],' in windows["L735"]
    assert "_CONSTRAINT_KEYS = frozenset(" in windows["L163"]
    for predicate in status["predicates"]:
        assert predicate["line"] in windows, predicate
        assert predicate["file"] == "control_plane/ceo_intent.py"
        assert predicate["line"].startswith("L") and predicate["line"][1:].isdigit()

    # (f) the A2 anchors this tier deliberately did NOT edit.
    assert "_JOB_SEATS = frozenset({\"coo\", \"ceo\", \"chairman\"})" in _source_window(
        "control_plane/executive_runtime.py", 146, 146
    )
    assert "def _has_executive_provenance(" in _source_window(
        "control_plane/executive_runtime.py", 928, 942
    )
    assert "if owner_seat != \"coo\" and not _has_executive_provenance(" in _source_window(
        "control_plane/executive_runtime.py", 10287, 10297
    )


# ---------------------------------------------------------------------------
# 10. the registry is closed
# ---------------------------------------------------------------------------


def test_registry_is_closed_and_look_alikes_confer_nothing():
    assert list(REGISTRY) == ["svc-site-maintenance"]
    registered = _principal()
    assert service_principal("svc-site-maintenance") == registered
    assert REGISTRY["svc-site-maintenance"] == registered

    # a look-alike dataclass with an unregistered id confers nothing
    look_alike = ServicePrincipal(
        principal_id="svc-site-maintenance-2",
        actor="svc-site-maintenance-2",
        purpose="look-alike probe",
    )
    with pytest.raises(ServicePrincipalRefused, match="not in the closed registry"):
        derive_intent(look_alike, _request(), now=0)
    with pytest.raises(ServicePrincipalRefused, match="not in the closed registry"):
        # The registry check precedes any runtime access; the sentinel never sees use.
        submit(look_alike, _request(), object())

    # a tampered copy of the registered definition is refused too
    tampered = ServicePrincipal(
        principal_id=registered.principal_id,
        actor=registered.actor,
        purpose="tampered purpose",
    )
    with pytest.raises(ServicePrincipalRefused, match="does not match its registered definition"):
        derive_intent(tampered, _request(), now=0)


# ---------------------------------------------------------------------------
# 11. KNOWN OPEN GAP (A2 follow-on, OWNED by executive_runtime.py / #699)
# ---------------------------------------------------------------------------
#
# The CEO branch of ``_has_executive_provenance`` is SCHEMA-ONLY
# (``executive_runtime.py`` L937-L938, cited here as a string): it compares the
# schema and DISCARDS the actor, while the chairman branch checks schema AND
# actor.  The stamp this tier's derived envelope receives from the sink in
# ``event.payload["provenance"]`` is exactly
# ``schema=mastermind.ceo_intent.v1`` / ``actor=svc-site-maintenance``, so that
# stamp satisfies the CEO branch.  The tests below PIN that as a known,
# documented open gap instead of fixing it: the gate, the sink stamp, and the
# OWNED runtime (#699) are all outside this packet's fences.  This tier never
# passes ``owner_seat``/``escalation_target`` (the sink's own ``coo`` defaults
# seat the Job, asserted in section 4), so the gap is *reuse* of the stamped
# provenance by any other runtime holder, not a Job this tier can create.


def _durable_sink_stamp(tmp_path: Path) -> tuple[dict, dict]:
    """The sink's stamped provenance block and the sink's own receipt.

    The stamp comes from calling the UNCHANGED sink directly, because ``submit()``
    is closed while unadmitted (A3): the gap is about what the sink stamps, not
    about a production path that mutates now.
    """

    runtime = Runtime.at(tmp_path / "runtime")
    receipt = _sink_submit(runtime)
    reader = Runtime.at(tmp_path / "runtime")
    stamp = durable_provenance(reader, receipt["job_id"])["provenance"]
    assert stamp["schema"] == INTENT_SCHEMA
    assert stamp["actor"] == _principal().actor
    return stamp, receipt


def test_open_gap_executive_provenance_gate_is_schema_only_A2(tmp_path: Path):
    """OPEN GAP: the CEO target accepts the sink's stamp because it ignores the actor."""

    stamp, _receipt = _durable_sink_stamp(tmp_path)

    # (a) the predicate, on the durable stamp: CEO True, chairman False.
    assert _has_executive_provenance(dict(stamp), target="ceo") is True
    assert _has_executive_provenance(dict(stamp), target="chairman") is False

    # ...and the schema-only branch is still exactly where the record says it is.
    source = (_ROOT / "control_plane" / "executive_runtime.py").read_text(encoding="utf-8")
    assert 'if target == "ceo":\n        return schema == "mastermind.ceo_intent.v1"' in source


def test_open_gap_ceo_seat_is_admitted_with_the_sink_stamp_A2(tmp_path: Path):
    """OPEN GAP: today ``create_job`` admits a ``ceo`` seat on the sink's stamp."""

    stamp, receipt = _durable_sink_stamp(tmp_path)
    runtime = Runtime.at(tmp_path / "runtime")

    # (b) ADMITTED today.  Recorded, never fixed here: the fix is an
    # actor-aware gate in the OWNED runtime, not in this tier.
    seated = runtime.jobs.create_job(
        "known open gap probe: ceo seat with the sink's v1 stamp",
        owner_seat="ceo",
        provenance=dict(stamp),
    )
    assert seated.owner_seat == "ceo"

    escalated = runtime.jobs.create_job(
        "known open gap probe: ceo escalation with the sink's v1 stamp",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance=dict(stamp),
    )
    assert escalated.escalation_target == "ceo"

    # REFUSED: the human seat's branch is actor-aware (schema AND actor).
    with pytest.raises(StateConflict, match="owner_seat='chairman' requires"):
        runtime.jobs.create_job(
            "known open gap probe: chairman seat",
            owner_seat="chairman",
            provenance=dict(stamp),
        )

    # REFUSED: the same seats with no provenance at all, and with this tier's
    # own typed schema - the gate keys on the CEO intent schema, not the actor.
    with pytest.raises(StateConflict, match="owner_seat='ceo' requires"):
        runtime.jobs.create_job("known open gap probe: no provenance", owner_seat="ceo")
    with pytest.raises(StateConflict, match="owner_seat='ceo' requires"):
        runtime.jobs.create_job(
            "known open gap probe: typed service-principal schema",
            owner_seat="ceo",
            provenance=dict(_derived()["provenance"]),
        )

    # (c) this tier's own envelope rides the sink's ``coo`` defaults: it never
    # carries a seat, so no Job created from it can be seated above coo - even in
    # a database that now also holds the ceo-seated probes above.
    reader = Runtime.at(tmp_path / "runtime")
    own = [job for job in reader.jobs.list_jobs() if job.job_id == receipt["job_id"]]
    assert len(own) == 1
    assert own[0].owner_seat == SERVICE_SEAT == "coo"
    assert own[0].escalation_target == SERVICE_SEAT
    assert own[0].requested_authorities == ["READ", "RESEARCH"]
