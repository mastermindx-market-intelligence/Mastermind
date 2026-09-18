"""Acceptance tests for the A1 typified NON-CEO service principal (A2 admitted).

Hermetic: stdlib + pytest + ``tmp_path`` only.  No installed service, no socket,
no network, no provider, no credential, no global ``subprocess`` patch, no real
Job outside the in-repo runtime temp database.

The point of this file is twofold:

1. prove the closed identity/authority shape of the tier, and
2. prove the A2 admission: the EXISTING single sink durably carries the strict
   ``mastermind.executive_service_intent.v1`` envelope (typed service evidence in
   ``event.payload["provenance"]``), seats it explicitly on ``coo``, enforces the
   READ/RESEARCH ceiling in the sink itself, and is still NOT read as CEO
   provenance by the unchanged readers.

The laws proved here:

* **A1** - the intent id is a hash of exactly (schema, principal_id,
  operation_key), so a changed objective or a changed grounding SHA for the same
  logical operation is the sink's existing whole-envelope conflict, never a
  second Job;
* **A2** - the typed block states the WRITE ceiling (``write_authorities``, always
  empty) *and* the truthful READ/RESEARCH grant (``requested_authorities`` /
  ``effective_authorities``), with drift refused in both directions; the sink
  itself refuses any write authority, any declared write path, any non-READ
  ``authority_level``, a reserved identity, a non-``svc-`` intent id, a foreign
  ``task_kind``, an unknown key, and a v2-shaped service envelope; and
* **A3** - the submission gate stays LIVE: open while ``admission_status()`` is
  ``ADMITTED``, closed the moment that verdict regresses.

The reachable-sink proof now goes through the public ``submit()`` - the tier is
admitted, so no test needs to bypass the production-facing callable to prove the
contract.  Every refusal is triggered for real rather than trusted.
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
    INTENT_SCHEMA_SERVICE,
    RECEIPT_SCHEMA_SERVICE,
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
    "principal_id",
    "task_kind",
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


def _submit(runtime, request: dict | None = None):
    """The reachable path: the PUBLIC ``submit()`` into the single sink.

    A2 admits the strict service schema, so the tier's own production-facing
    callable is the reachable path; the test no longer has to call the sink
    directly to prove the contract.
    """

    return submit(_principal(), request if request is not None else _request(), runtime)


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
    # A2: the envelope rides the strict SERVICE schema, not the CEO one, and
    # carries the two typed service keys the sink's service branch requires.
    assert derived["envelope"]["schema"] == INTENT_SCHEMA_SERVICE
    assert derived["envelope"]["schema"] != INTENT_SCHEMA
    assert derived["envelope"]["principal_id"] == _principal().principal_id
    assert derived["envelope"]["task_kind"] == TASK_KIND == "research"
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
# 3. authority is refused independently of actor (mirrors tests/test_ceo_intent.py:490)
# ---------------------------------------------------------------------------


def test_authority_is_refused_independently_of_actor(tmp_path: Path):
    """The service principal's actor is provenance, not privilege."""

    runtime = Runtime.at(tmp_path / "runtime")
    for actor in (_principal().actor, "svc-other-actor"):
        envelope = copy.deepcopy(_derived()["envelope"])
        envelope["actor"] = actor
        envelope["intent_id"] = f"svc-esp-{actor.replace('-', '').replace('_', '')}"
        envelope["execution_contract"] = {"requested_authorities": ["MERGE"]}
        # The SINK's service ceiling refuses the write authority before the
        # downstream policy is ever consulted; the actor value changes nothing.
        with pytest.raises(CeoIntentError, match="READ/RESEARCH only"):
            submit_intent(runtime, envelope)
    assert runtime.jobs.list_jobs() == []

    # the caller cannot name its own identity or authority, structurally
    for privileged in ("actor", "schema", "requested_authorities", "authority_level"):
        with pytest.raises(ServicePrincipalRefused, match="refused by the existing normalizer"):
            derive_intent(_principal(), _request(**{privileged: "anything"}), now=0)


# ---------------------------------------------------------------------------
# 4. hermetic sink reachability — through the PUBLIC submit() (A2 admitted)
# ---------------------------------------------------------------------------


def test_hermetic_sink_reachability_proof_one_coo_job_no_dispatch_and_duplicate(tmp_path: Path):
    """What this tier reaches, proven through the real public path."""

    request = _request()
    runtime = Runtime.at(tmp_path / "runtime")
    first = _submit(runtime, request)
    second = _submit(runtime, request)

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
    assert provenance["schema"] == INTENT_SCHEMA_SERVICE
    assert provenance["principal_id"] == _principal().principal_id
    assert provenance["task_kind"] == TASK_KIND
    assert provenance["requested_authorities"] == ["READ", "RESEARCH"]
    assert provenance["effective_authorities"] == ["READ", "RESEARCH"]
    assert provenance["write_authorities"] == []
    assert provenance["fingerprint"] == first["fingerprint"]
    assert provenance["grounding"] == _GROUNDING
    assert len([e for e in reader.events.list_events(job_id=job.job_id) if e.event_type == "JOB_CREATED"]) == 1

    # A third identical submission still reconciles to the one durable Job.
    assert _submit(runtime, request)["job_id"] == first["job_id"]
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
        "control_plane/ceo_intent.py", 1098, 1108
    )
    assert "if fingerprint is not None and recorded != fingerprint:" in _source_window(
        "control_plane/ceo_intent.py", 902, 910
    )
    assert 'return f"{COMMAND_ID_PREFIX}{intent_id}"' in _source_window(
        "control_plane/ceo_intent.py", 757, 764
    )
    pins = admission_status()["identity"]["conflict_predicates"]
    assert {pin["line"] for pin in pins} == {"L1103", "L906", "L761"}
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

    # ...and with the tier ADMITTED a normal request DOES reach the monkeypatched
    # sink: the drift refusals above are the pre-sink order, not a closed gate.
    sentinel = {"accepted": True}
    monkeypatch.setattr(
        ceo_intent, "submit_intent", lambda *a, **k: sink_calls.append(a) or sentinel
    )
    assert submit(_principal(), _request(), object()) == sentinel
    assert len(sink_calls) == 1


# ---------------------------------------------------------------------------
# 7. A3 — THE LIVE SUBMISSION GATE (open on ADMITTED, closed on regression)
# ---------------------------------------------------------------------------


def test_a3_submission_gate_is_live_and_closes_on_regression(monkeypatch, tmp_path: Path):
    status = admission_status()
    assert status["status"] == ADMITTED

    sink_calls: list = []
    sentinel = {"accepted": True}
    monkeypatch.setattr(
        ceo_intent, "submit_intent", lambda *a, **k: sink_calls.append(a) or sentinel
    )

    # (a) ADMITTED: the public path reaches the sink (the sentinel proves the
    #     call; no real runtime is involved).
    assert submit(_principal(), _request(), object()) == sentinel
    assert len(sink_calls) == 1

    # (b) The gate is a LIVE read, not a hard-coded refusal: force the verdict to
    #     regress and the SAME call fails closed BEFORE any runtime access.  A
    #     sentinel runtime is passed on purpose: reading it at all would raise
    #     AttributeError, so this proves the refusal precedes runtime access.
    regressed = dict(status, status=NOT_YET_ADMITTED)
    monkeypatch.setattr(esp, "admission_status", lambda: regressed)
    with pytest.raises(ServicePrincipalNotAdmitted) as caught:
        submit(_principal(), _request(), object())
    message = str(caught.value)
    assert "NOT_YET_ADMITTED" in message
    assert regressed["reason"] in message
    for predicate in regressed["predicates"]:
        assert predicate["file"] in message
        assert predicate["line"] in message
    assert len(sink_calls) == 1

    # (c) a REAL runtime is untouched while the gate is closed.
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(ServicePrincipalNotAdmitted):
        submit(_principal(), _request(), runtime)
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []
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
    receipt = _submit(runtime, request)
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
# 9. A2 — the sink carries the strict service schema, with its ceiling
# ---------------------------------------------------------------------------


def test_service_schema_is_durably_carried_with_typed_evidence(tmp_path: Path):
    """A2 admitted: the sink stamps the SERVICE schema plus the typed evidence."""

    status = admission_status()
    assert status["status"] == ADMITTED
    assert _derived()["admission"]["status"] == ADMITTED

    runtime = Runtime.at(tmp_path / "runtime")
    receipt = _submit(runtime)
    assert receipt["schema"] == RECEIPT_SCHEMA_SERVICE
    assert receipt["schema"] == "mastermind.executive_service_intent_receipt.v1"

    reader = Runtime.at(tmp_path / "runtime")
    durable = durable_provenance(reader, receipt["job_id"])
    provenance = durable["provenance"]
    assert provenance["schema"] == INTENT_SCHEMA_SERVICE
    assert provenance["actor"] == _principal().actor
    assert provenance["principal_id"] == _principal().principal_id
    assert provenance["task_kind"] == TASK_KIND
    assert provenance["requested_authorities"] == ["READ", "RESEARCH"]
    assert provenance["effective_authorities"] == ["READ", "RESEARCH"]
    assert provenance["write_authorities"] == []
    assert set(provenance) == {
        "schema", "intent_id", "actor", "fingerprint", "grounding",
        "principal_id", "task_kind", "requested_authorities",
        "effective_authorities", "write_authorities",
    }
    assert SCHEMA not in json.dumps(durable)

    # resolve/replay rebuilds the SERVICE receipt from durable state only
    resolved = ceo_intent.resolve_intent(reader, receipt["intent_id"])
    assert resolved["schema"] == RECEIPT_SCHEMA_SERVICE
    assert resolved["job_id"] == receipt["job_id"]
    assert resolved["duplicate"] is False

    # task_kind rides the envelope and the durable provenance, never a create_job
    # parameter: the runtime Job API is unchanged.
    assert "task_kind" not in inspect.signature(JobRegistry.create_job).parameters

    # (e) the recorded path:line evidence must still describe the real code.
    #     The module's pins are ``L<number>`` STRINGS, never bare integer
    #     literals: the D8 identity ratchet flags unexplained 4xx-9xx integers
    #     in added production source, and a source-line citation is not an
    #     identity.
    windows = {
        "L633": _source_window("control_plane/ceo_intent.py", 628, 640),
        "L578": _source_window("control_plane/ceo_intent.py", 570, 600),
        "L855": _source_window("control_plane/ceo_intent.py", 850, 866),
        "L1158": _source_window("control_plane/ceo_intent.py", 1152, 1166),
    }
    assert "_SERVICE_REQUIRED_KEYS" in windows["L633"]
    assert "def _require_service_ceiling" in windows["L578"]
    assert 'value["principal_id"] = intent["principal_id"]' in windows["L855"]
    assert 'owner_seat="coo"' in windows["L1158"]
    for predicate in status["predicates"]:
        assert predicate["line"] in windows, predicate
        assert predicate["file"] == "control_plane/ceo_intent.py"
        assert predicate["line"].startswith("L") and predicate["line"][1:].isdigit()

    # (f) the anchors this tier deliberately did NOT edit.
    assert "_JOB_SEATS = frozenset({\"coo\", \"ceo\", \"chairman\"})" in _source_window(
        "control_plane/executive_runtime.py", 146, 146
    )
    assert "def _has_executive_provenance(" in _source_window(
        "control_plane/executive_runtime.py", 928, 942
    )
    assert "if owner_seat != \"coo\" and not _has_executive_provenance(" in _source_window(
        "control_plane/executive_runtime.py", 10287, 10297
    )


def test_service_sink_refuses_write_authority_reserved_actors_and_bad_shapes(tmp_path: Path):
    """Every refusal the A2 ceiling and the closed values promise, triggered."""

    runtime = Runtime.at(tmp_path / "runtime")
    base = _derived()["envelope"]

    probes = (
        # the read-only ceiling
        ({"execution_contract": {"requested_authorities": ["WRITE_BRANCH"]}}, "READ/RESEARCH only"),
        ({"execution_contract": {"requested_authorities": ["RUN_TESTS"]}}, "READ/RESEARCH only"),
        ({"execution_contract": {"requested_authorities": ["READ", "MERGE"]}}, "READ/RESEARCH only"),
        (
            {"execution_contract": {"requested_authorities": ["READ"], "allowed_write_paths": ["docs/x.md"]}},
            "may not declare allowed_write_paths",
        ),
        (
            {"execution_contract": {"requested_authorities": ["READ"], "authority_level": "A3"}},
            "READ level",
        ),
        # reserved identities
        ({"actor": "ceo-sol"}, "reserved identity"),
        ({"actor": "chairman"}, "reserved identity"),
        ({"actor": "chris"}, "reserved identity"),
        ({"actor": "operator"}, "reserved identity"),
        # the service id domain and closed values
        ({"intent_id": "esp-not-svc"}, "must start with 'svc-'"),
        ({"intent_id": "CEO-2026-08-13-A"}, "must start with 'svc-'"),
        ({"task_kind": "implementation"}, "intent.task_kind must be"),
        ({"principal_id": "site-maintenance"}, "intent.principal_id has an unsupported form"),
        ({"principal_id": "svc-X"}, "intent.principal_id has an unsupported form"),
        # unknown keys
        ({"extra_key": "x"}, r"unexpected key\(s\): \['extra_key'\]"),
        ({"provenance": {}}, r"unexpected key\(s\): \['provenance'\]"),
    )
    for overrides, match in probes:
        probe = copy.deepcopy(base)
        probe.update(overrides)
        with pytest.raises(CeoIntentError, match=match):
            submit_intent(runtime, probe)

    # ...and a service-schema envelope shaped like v2 is refused by exact keys.
    v2_shaped = copy.deepcopy(base)
    v2_shaped["intent_kind"] = "executive_coo_cycle"
    v2_shaped["business_impact"] = "material"
    with pytest.raises(
        CeoIntentError, match=r"unexpected key\(s\): \['business_impact', 'intent_kind'\]"
    ):
        submit_intent(runtime, v2_shaped)

    # A valid service envelope still lands exactly one Job: the refusals above
    # are the probes failing, not a broken happy path.
    assert runtime.jobs.list_jobs() == []
    assert _submit(runtime)["accepted"] is True
    assert len(Runtime.at(tmp_path / "runtime").jobs.list_jobs()) == 1


def test_service_stamp_does_not_satisfy_the_ceo_seat_gate(tmp_path: Path):
    """The service stamp can never be reused to seat a Job above coo.

    This is the A2 point: the durable provenance schema is the SERVICE schema, so
    the runtime's CEO branch (which keys on the raw v1 schema) does not fire.
    """

    runtime = Runtime.at(tmp_path / "runtime")
    receipt = _submit(runtime)
    reader = Runtime.at(tmp_path / "runtime")
    stamp = durable_provenance(reader, receipt["job_id"])["provenance"]
    assert stamp["schema"] == INTENT_SCHEMA_SERVICE

    assert _has_executive_provenance(dict(stamp), target="ceo") is False
    assert _has_executive_provenance(dict(stamp), target="chairman") is False

    for seat in ("ceo", "chairman"):
        with pytest.raises(StateConflict, match=f"owner_seat='{seat}' requires"):
            runtime.jobs.create_job(
                f"service stamp cannot seat {seat!r}",
                owner_seat=seat,
                provenance=dict(stamp),
            )
        with pytest.raises(StateConflict, match=f"escalation_target='{seat}' requires"):
            runtime.jobs.create_job(
                f"service stamp cannot escalate to {seat!r}",
                owner_seat=SERVICE_SEAT,
                escalation_target=seat,
                provenance=dict(stamp),
            )

    # the tier's own Job keeps the coo seats it was created with
    own = reader.jobs.get_job(receipt["job_id"])
    assert own.owner_seat == SERVICE_SEAT == "coo"
    assert own.escalation_target == SERVICE_SEAT
    assert own.requested_authorities == ["READ", "RESEARCH"]


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
# 11. RESIDUAL RAW-v1 RUNTIME GAP (unchanged, OWNED by executive_runtime.py)
# ---------------------------------------------------------------------------
#
# A2 closed the SCHEMA-ONLY hole for the service tier: the durable provenance the
# sink stamps for a service intent now carries the SERVICE schema, so it no
# longer satisfies the CEO branch of ``_has_executive_provenance`` (pinned in
# section 9 by ``test_service_stamp_does_not_satisfy_the_ceo_seat_gate``).
#
# The residual is what A2 cannot and must not touch: the CEO branch of
# ``_has_executive_provenance`` is still SCHEMA-ONLY
# (``executive_runtime.py`` L937-L938, cited here as a string).  A RAW
# ``mastermind.ceo_intent.v1`` stamp - the stamp ANY v1 CEO submission receives -
# is compared on its schema and its actor is DISCARDED, while the human-seat
# branch checks schema AND actor.  The test below pins that residual as a known,
# documented Runtime gap instead of fixing it: the gate and the OWNED runtime
# are outside this packet's fences.  This tier's own Jobs ride the explicit
# ``coo`` seats (section 4), so the residual is *reuse* of a raw-v1 stamped
# provenance by another runtime holder, never a Job this tier can create.


def test_open_gap_raw_v1_stamp_still_satisfies_the_schema_only_ceo_branch(tmp_path: Path):
    """RESIDUAL: a RAW v1 stamp passes the CEO seat gate; the service stamp does not.

    Recorded, never fixed here.  The fix is an actor-aware (or distinct-schema)
    gate in the OWNED runtime, not in this tier.
    """

    raw_v1 = {
        "schema": INTENT_SCHEMA,
        "intent_id": "CEO-OPEN-GAP-PROBE",
        "actor": _principal().actor,
        "fingerprint": "0" * 64,
        "grounding": dict(_GROUNDING),
    }

    # (a) the predicate: the raw v1 schema passes CEO and fails the human seat.
    assert _has_executive_provenance(dict(raw_v1), target="ceo") is True
    assert _has_executive_provenance(dict(raw_v1), target="chairman") is False

    # ...and the schema-only branch is still exactly where the record says it is.
    source = (_ROOT / "control_plane" / "executive_runtime.py").read_text(encoding="utf-8")
    assert 'if target == "ceo":\n        return schema == "mastermind.ceo_intent.v1"' in source

    # (b) ADMITTED today with a raw v1 stamp.  A caller-side ``Object()``
    #     sentinel cannot work here (``_has_executive_provenance`` requires a
    #     dict), so the probe uses the raw dict itself.
    runtime = Runtime.at(tmp_path / "runtime")
    seated = runtime.jobs.create_job(
        "residual probe: ceo seat with a raw v1 stamp",
        owner_seat="ceo",
        provenance=dict(raw_v1),
    )
    assert seated.owner_seat == "ceo"

    # REFUSED: the human seat's branch is actor-aware (schema AND actor).
    with pytest.raises(StateConflict, match="owner_seat='chairman' requires"):
        runtime.jobs.create_job(
            "residual probe: chairman seat",
            owner_seat="chairman",
            provenance=dict(raw_v1),
        )

    # REFUSED: the same seat with no provenance at all, and with the SERVICE
    # stamp this tier actually emits - the A2 fix, pinned here as the contrast.
    with pytest.raises(StateConflict, match="owner_seat='ceo' requires"):
        runtime.jobs.create_job("residual probe: no provenance", owner_seat="ceo")

    service_receipt = _submit(runtime)
    reader = Runtime.at(tmp_path / "runtime")
    service_stamp = durable_provenance(reader, service_receipt["job_id"])["provenance"]
    assert service_stamp["schema"] == INTENT_SCHEMA_SERVICE
    with pytest.raises(StateConflict, match="owner_seat='ceo' requires"):
        runtime.jobs.create_job(
            "residual probe: service stamp",
            owner_seat="ceo",
            provenance=dict(service_stamp),
        )

    # The tier's own Job keeps the explicit coo seats.
    own = reader.jobs.get_job(service_receipt["job_id"])
    assert own.owner_seat == SERVICE_SEAT == "coo"
    assert own.escalation_target == SERVICE_SEAT
