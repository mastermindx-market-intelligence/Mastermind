"""Acceptance tests for the A1 typified NON-CEO service principal.

Hermetic: stdlib + pytest + ``tmp_path`` only.  No installed service, no socket,
no network, no provider, no credential, no global ``subprocess`` patch, no real
Job outside the in-repo runtime temp database.

The point of this file is twofold:

1. prove the closed identity/authority shape of the tier, and
2. PIN THE BLOCKER: the existing single mutation sink cannot durably carry the
   typed service-principal provenance schema or a ``task_kind`` marker, and these
   tests trigger the real refusals rather than trusting a documented string.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

from control_plane import ceo_intent
from control_plane.ceo_intent import INTENT_SCHEMA, CeoIntentError, command_id_for, submit_intent
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
    ServicePrincipalRefused,
    admission_status,
    command_id,
    derive_intent,
    durable_provenance,
    fingerprint,
    service_principal,
    submit,
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
        "schema", "actor", "principal_id", "task_kind", "authorities",
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
        (lambda block: block.__setitem__("authorities", ["WRITE_BRANCH"]), "must be empty"),
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
# 4. submit through the existing sink
# ---------------------------------------------------------------------------


def test_submit_creates_exactly_one_coo_job_and_reconciles_duplicates(tmp_path: Path):
    request = _request()
    runtime = Runtime.at(tmp_path / "runtime")
    first = submit(_principal(), request, runtime)
    second = submit(_principal(), request, runtime)

    assert first["accepted"] is True
    assert first["dispatched"] is False
    assert first["status"] == JobStatus.QUEUED.value
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


# ---------------------------------------------------------------------------
# 5. no CEO identity is ever emitted
# ---------------------------------------------------------------------------


def test_emitted_provenance_never_carries_a_ceo_identity(tmp_path: Path):
    request = _request()
    runtime = Runtime.at(tmp_path / "runtime")
    receipt = submit(_principal(), request, runtime)
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
# 6. the pinned blocker — the sink cannot carry the typed schema or task_kind
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
    receipt = submit(_principal(), _request(), runtime)
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
# 7. the registry is closed
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
# 8. KNOWN OPEN GAP (A2 follow-on, OWNED by executive_runtime.py / #699)
# ---------------------------------------------------------------------------
#
# The CEO branch of ``_has_executive_provenance`` is SCHEMA-ONLY
# (``executive_runtime.py`` L937-L938, cited here as a string): it compares the
# schema and DISCARDS the actor, while the chairman branch checks schema AND
# actor.  The stamp this tier's ``submit()`` leaves in
# ``event.payload["provenance"]`` is exactly
# ``schema=mastermind.ceo_intent.v1`` / ``actor=svc-site-maintenance``, so that
# stamp satisfies the CEO branch.  The tests below PIN that as a known,
# documented open gap instead of fixing it: the gate, the sink stamp, and the
# OWNED runtime (#699) are all outside this packet's fences.  The module's own
# ``submit()`` never passes ``owner_seat``/``escalation_target``, so its Jobs
# stay ``coo`` (asserted in section 4); the gap is *reuse* of the stamped
# provenance by any other runtime holder, not this path today.


def _durable_sink_stamp(tmp_path: Path) -> tuple[dict, dict]:
    """The sink's stamped provenance block and the sink's own receipt."""

    runtime = Runtime.at(tmp_path / "runtime")
    receipt = submit(_principal(), _request(), runtime)
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

    # (c) this tier's OWN submit path stays coo: it never passes a seat, so no
    # Job created by this module can be seated above coo - even in a database
    # that now also holds the ceo-seated probes above.
    reader = Runtime.at(tmp_path / "runtime")
    own = [job for job in reader.jobs.list_jobs() if job.job_id == receipt["job_id"]]
    assert len(own) == 1
    assert own[0].owner_seat == SERVICE_SEAT == "coo"
    assert own[0].escalation_target == SERVICE_SEAT
    assert own[0].requested_authorities == ["READ", "RESEARCH"]
