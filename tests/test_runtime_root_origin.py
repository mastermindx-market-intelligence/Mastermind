"""Focused unit tests for the pure legacy/root-creation classifier."""

import pytest
from types import SimpleNamespace

from control_plane.runtime_root_origin import classify_legacy_root_creation

INTENT_SCHEMA = "mastermind.ceo_intent.v1"
BOOT_SCHEMA = "mastermind.ceo_boot_packet.v1"


def make_job(job_id="JOB-101", **over):
    fields = dict(job_id=job_id, root_job_id=job_id, parent_job_id=None, depth=0, status="QUEUED",
        orchestration_role=None, orchestration_provenance=None, orchestration_provenance_digest=None)
    fields.update(over)
    return SimpleNamespace(**fields)


def make_grounding(**over):
    fields = dict(mastermind_sha="a" * 40, macro_sha="b" * 40, boot_packet_schema=BOOT_SCHEMA)
    fields.update(over)
    return fields


def make_provenance(intent_id="intent-alpha", **over):
    fields = dict(
        schema=INTENT_SCHEMA,
        intent_id=intent_id,
        actor="ceo.principal",
        fingerprint="c" * 64,
        grounding=make_grounding(),
        workstream="WS:ALPHA",
    )
    fields.update(over)
    return fields


def make_event(payload, job_id="JOB-101", **over):
    fields = dict(
        event_type="JOB_CREATED",
        aggregate_type="job",
        aggregate_id=job_id,
        job_id=job_id,
        payload=payload,
        command_id=None,
        attempt_id=None,
        worker_id=None,
        quota_class=None,
    )
    fields.update(over)
    return SimpleNamespace(**fields)


def make_generic_payload(job_id="JOB-101", **over):
    fields = dict(root_job_id=job_id, parent_job_id=None, depth=0, status="QUEUED", title="routine")
    fields.update(over)
    return fields


def make_legacy_payload(job_id="JOB-101", provenance=None, **over):
    payload = make_generic_payload(job_id=job_id)
    payload["provenance"] = make_provenance() if provenance is None else provenance
    payload.update(over)
    return payload


def generic_event(job_id="JOB-101", **over):
    return make_event(make_generic_payload(job_id=job_id), job_id=job_id, **over)


def legacy_event(job_id="JOB-101", intent_id="intent-alpha", provenance=None):
    if provenance is None:
        provenance = make_provenance(intent_id=intent_id)
    payload = make_legacy_payload(job_id=job_id, provenance=provenance)
    return make_event(payload, job_id=job_id, command_id="ceo-intent:" + intent_id)


# --- positive NON_CEO -------------------------------------------------------


def test_generic_creation_is_non_ceo():
    result = classify_legacy_root_creation(make_job(), generic_event())
    assert result == {"kind": "NON_CEO", "provenance": None}


@pytest.mark.parametrize("command_id", [None, "deploy-2026-10-12", "coo-cycle:JOB-9"])
def test_generic_command_ids_stay_non_ceo(command_id):
    result = classify_legacy_root_creation(make_job(), generic_event(command_id=command_id))
    assert result == {"kind": "NON_CEO", "provenance": None}


def test_absent_command_id_attribute_is_non_ceo():
    event = generic_event()
    del event.command_id
    assert classify_legacy_root_creation(make_job(), event) == {"kind": "NON_CEO", "provenance": None}


def test_explicit_null_payload_orchestration_fields_are_unresolved():
    payload = make_generic_payload(orchestration_role=None, orchestration_provenance_digest=None)
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


def test_current_completed_status_is_ignored():
    assert classify_legacy_root_creation(make_job(status="COMPLETED"), generic_event()) == {
        "kind": "NON_CEO",
        "provenance": None,
    }
    legacy = classify_legacy_root_creation(make_job(status="COMPLETED"), legacy_event())
    assert legacy["kind"] == "LEGACY_CEO"


# --- positive LEGACY_CEO ----------------------------------------------------


def test_legacy_v1_provenance_round_trip():
    result = classify_legacy_root_creation(make_job(), legacy_event())
    assert result["kind"] == "LEGACY_CEO"
    assert set(result["provenance"]) == {
        "schema",
        "intent_id",
        "actor",
        "fingerprint",
        "grounding",
        "workstream",
    }
    assert result["provenance"]["schema"] == INTENT_SCHEMA
    assert result["provenance"]["intent_id"] == "intent-alpha"
    assert result["provenance"]["actor"] == "ceo.principal"
    assert result["provenance"]["fingerprint"] == "c" * 64
    assert result["provenance"]["workstream"] == "WS:ALPHA"
    assert result["provenance"]["grounding"] == {
        "mastermind_sha": "a" * 40,
        "macro_sha": "b" * 40,
        "boot_packet_schema": BOOT_SCHEMA,
    }


def test_same_workstream_membership_survives_across_roots():
    first = classify_legacy_root_creation(make_job(job_id="JOB-201"), legacy_event(job_id="JOB-201"))
    second = classify_legacy_root_creation(
        make_job(job_id="JOB-202"), legacy_event(job_id="JOB-202", intent_id="intent-beta")
    )
    assert first["kind"] == second["kind"] == "LEGACY_CEO"
    assert first["provenance"]["workstream"] == "WS:ALPHA"
    assert second["provenance"]["workstream"] == "WS:ALPHA"


def test_returned_provenance_is_a_safe_copy():
    event = legacy_event()
    result = classify_legacy_root_creation(make_job(), event)
    result["provenance"]["intent_id"] = "tampered"
    result["provenance"]["grounding"]["mastermind_sha"] = "f" * 40
    again = classify_legacy_root_creation(make_job(), event)
    assert again["provenance"]["intent_id"] == "intent-alpha"
    assert again["provenance"]["grounding"]["mastermind_sha"] == "a" * 40


# --- envelope / identity rejection ------------------------------------------


def test_non_job_created_event_is_refused():
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), generic_event(event_type="JOB_UPDATED"))


def test_wrong_aggregate_type_is_refused():
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), generic_event(aggregate_type="run"))


def test_mismatched_aggregate_or_event_job_id_is_refused():
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), generic_event(aggregate_id="JOB-999"))
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), generic_event(job_id="JOB-999"))


@pytest.mark.parametrize("field", ["attempt_id", "worker_id", "quota_class"])
def test_creation_attribution_is_refused(field):
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), generic_event(**{field: "att-1"}))


def test_payload_must_be_a_mapping():
    event = generic_event()
    event.payload = ["not", "a", "mapping"]
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), event)


def test_missing_job_attribute_is_refused():
    job = make_job()
    del job.depth
    with pytest.raises(ValueError):
        classify_legacy_root_creation(job, generic_event())


@pytest.mark.parametrize("job_id", ["", "job-101", "JOB-", "JOB-abc", "RUN-101", "JOB-101 "])
def test_malformed_job_id_is_refused(job_id):
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(job_id=job_id), generic_event(job_id=job_id))


def test_non_root_job_is_refused():
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(root_job_id="JOB-2"), generic_event())
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(parent_job_id="JOB-2"), generic_event())


@pytest.mark.parametrize("depth", [1, "0", None, True, 0.0])
def test_malformed_depth_is_refused(depth):
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(depth=depth), generic_event())


@pytest.mark.parametrize(
    "over",
    [
        {"root_job_id": "JOB-999"},
        {"parent_job_id": "JOB-2"},
        {"depth": 3},
        {"depth": True},
        {"status": "RUNNING"},
        {"status": None},
    ],
)
def test_malformed_creation_state_is_refused(over):
    payload = make_generic_payload(**over)
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


# --- provenance routing -----------------------------------------------------


def test_explicit_null_provenance_is_malformed():
    payload = make_generic_payload(provenance=None)
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


def test_non_mapping_provenance_is_refused():
    payload = make_legacy_payload(provenance="ceo-intent:intent-alpha")
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


def test_ceo_intent_command_id_without_provenance_is_unresolved():
    with pytest.raises(ValueError):
        classify_legacy_root_creation(
            make_job(), generic_event(command_id="ceo-intent:intent-alpha")
        )


@pytest.mark.parametrize("command_id", ["", 7, ["ceo-intent:intent-alpha"]])
def test_malformed_command_id_is_refused(command_id):
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), generic_event(command_id=command_id))


# --- orchestration metadata -------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("orchestration_role", "aggregation"),
        ("orchestration_role", "planner"),
        ("orchestration_provenance_digest", "d" * 64),
    ],
)
def test_non_null_orchestration_metadata_is_refused(field, value):
    payload = make_generic_payload(**{field: value})
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


# --- legacy field validity --------------------------------------------------


@pytest.mark.parametrize(
    "over",
    [
        {"schema": "mastermind.ceo_intent.v2"},
        {"schema": "mastermind.executive_service_intent.v1"},
        {"schema": "mastermind.executive_principal_intent.v1"},
        {"schema": "mastermind.ceo_intent.v9"},
        {"schema": None},
        {"intent_id": "ab"},
        {"intent_id": "-lead"},
        {"intent_id": "has space"},
        {"actor": "a"},
        {"actor": "_lead"},
        {"fingerprint": "C" * 64},
        {"fingerprint": "c" * 63},
        {"fingerprint": None},
    ],
)
def test_malformed_or_unsupported_legacy_fields_are_refused(over):
    payload = make_legacy_payload(provenance=make_provenance(**over))
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


@pytest.mark.parametrize(
    "grounding",
    [
        {"mastermind_sha": "A" * 40},
        {"macro_sha": "b" * 39},
        {"boot_packet_schema": "mastermind.ceo_boot_packet.v2"},
        {"macro_sha": None},
    ],
)
def test_malformed_grounding_is_refused(grounding):
    provenance = make_provenance(grounding=make_grounding(**grounding))
    payload = make_legacy_payload(provenance=provenance)
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


def test_grounding_must_be_the_closed_canonical_shape():
    incomplete = make_legacy_payload(
        provenance=make_provenance(grounding={"mastermind_sha": "a" * 40, "macro_sha": "b" * 40})
    )
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(incomplete))
    extra = make_legacy_payload(provenance=make_provenance(grounding=make_grounding(extra="nope")))
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(extra))


def test_command_id_must_bind_the_intent_id():
    with pytest.raises(ValueError):
        classify_legacy_root_creation(
            make_job(),
            legacy_event(
                intent_id="intent-other",
                provenance=make_provenance(intent_id="intent-alpha"),
            ),
        )
    payload = make_legacy_payload()
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload, command_id=None))
    with pytest.raises(ValueError):
        classify_legacy_root_creation(
            make_job(), make_event(payload, command_id="intent-alpha")
        )


@pytest.mark.parametrize("workstream", ["WS:", "ws:ALPHA", "WS:ALPHA OK", "WS:_lead", None, 7])
def test_malformed_workstream_is_refused(workstream):
    payload = make_legacy_payload(provenance=make_provenance(workstream=workstream))
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


def test_missing_workstream_stays_unresolved():
    provenance = make_provenance()
    del provenance["workstream"]
    payload = make_legacy_payload(provenance=provenance)
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


def test_unexpected_provenance_keys_are_refused():
    payload = make_legacy_payload(provenance=make_provenance(carrier="service-bus"))
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), make_event(payload))


@pytest.mark.parametrize("field,value", [
    ("orchestration_role", "aggregation"),
    ("orchestration_provenance", {"creator": "ceo_intent"}),
    ("orchestration_provenance_digest", "d" * 64),
])
def test_job_metadata_cannot_be_hidden_by_generic_event(field, value):
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(**{field: value}), generic_event())


@pytest.mark.parametrize("field", [
    "orchestration_role", "orchestration_provenance", "orchestration_provenance_digest",
])
def test_missing_job_metadata_is_unresolved(field):
    job = make_job()
    delattr(job, field)
    with pytest.raises(ValueError):
        classify_legacy_root_creation(job, generic_event())


def test_missing_payload_parent_is_unresolved():
    event = generic_event()
    del event.payload["parent_job_id"]
    with pytest.raises(ValueError):
        classify_legacy_root_creation(make_job(), event)
