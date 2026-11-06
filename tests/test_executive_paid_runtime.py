"""Focused discriminating tests for the paid SEALED_WORKER evidence joins.

Real owners only: the existing Executive Runtime module, the closed capacity
join reader and, where present on this remote, the canonical paid contract
owner.  No fake production owner, no alternate Runtime and no alternate store
is created; the SQLite fixtures hold ordinary ``worker_quota_classes`` /
``jobs`` / ``attempts`` / ``events`` rows shaped exactly like the existing
capacity selection and ``JOB_CLAIMED``/``ATTEMPT_REMOTE_LAUNCH_PINNED``
writes.

The deeper launch-material discriminators run only where the canonical paid
contract owner is importable; on remotes without the full paid stack they
skip with an explicit reason and are never simulated or downgraded to fakes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3

import pytest

try:  # integrated layout: the parent Runtime owns this leaf module
    from control_plane.executive_paid_runtime import (
        PAID_ADAPTER_ID,
        PAID_CAPACITY_BINDING_SCHEMA,
        PAID_MODELS,
        PAID_PROFILE_ID,
        PAID_PROVIDER,
        PAID_RESULT_RECEIPT_SCHEMA,
        is_paid_attempt,
        paid_claim_binding,
        paid_launch_binding_identity,
        paid_physical_binding_from_worker_source,
        paid_sealed_worker_result_payload,
        validated_paid_launch_material,
        validated_paid_terminal_evidence,
        validated_paid_worker_source_document,
        _paid_compiler_subset,
        _paid_metadata_markers,
    )
except ImportError:  # standalone leaf checkout: same module, package-less
    from executive_paid_runtime import (
        PAID_ADAPTER_ID,
        PAID_CAPACITY_BINDING_SCHEMA,
        PAID_MODELS,
        PAID_PROFILE_ID,
        PAID_PROVIDER,
        PAID_RESULT_RECEIPT_SCHEMA,
        is_paid_attempt,
        paid_claim_binding,
        paid_launch_binding_identity,
        paid_physical_binding_from_worker_source,
        paid_sealed_worker_result_payload,
        validated_paid_launch_material,
        validated_paid_terminal_evidence,
        validated_paid_worker_source_document,
        _paid_compiler_subset,
        _paid_metadata_markers,
    )

import control_plane.executive_runtime as er
from control_plane.executive_capacity_join import JOIN_SCHEMA
from control_plane.executive_orchestration_principal import (
    build_placement_snapshot,
    digest as orchestration_digest,
)

PROVIDER_CAPACITY_SCHEMA = "mastermind.provider_capacity.v1"
PAID_METADATA_SCHEMA = "mastermind.executive_paid_process_launch/v1"
PAID_ATTESTATION_SCHEMA = "mastermind.executive_paid_model_launch_attestation/v1"
PAID_WORKER_SOURCE_SCHEMA = "mastermind.paid_worker_source/v1"
PAID_PHYSICAL_SCHEMA = "mastermind.paid_fabric_host_binding/v1"
GRANT_SCHEMA = "mastermind.executive_effective_grant/v1"
PROVENANCE_SCHEMA = "mastermind.executive_orchestration_provenance/v1"
DIALOGUE_SOURCE_SCHEMA = "mastermind.executive_dialogue_source/v1"

PROFILE_DIGEST = "c" * 64
CAPABILITY_POLICY_VERSION = "paid-capability-policy-1"
CAPABILITY_POLICY_DIGEST = "d" * 64
POLICY_SHA = "1" * 64
GRANT_SHA = "2" * 64
ISOLATION_SHA = "3" * 64
SOURCE_MANIFEST_SHA = "4" * 64
BINARY_SHA = "5" * 64
PERMISSION_SHA = "6" * 64
SERVICE_SOURCE_SHA = "7" * 64
COMMISSION_CONTENT_SHA = "8" * 64
from control_plane.paid_model_execution_contract import paid_host_reference
HOST_REF = paid_host_reference("ubuntu0", "ubuntu0")
ROOT_ID = "JOB-ROOT-1"
JOB_ID = "JOB-CHILD-1"
OTHER_JOB_ID = "JOB-OTHER-9"
ATTEMPT_ID = "ATT-" + "a1b2c3d4e5f60718293a4b5c6d7e8f90"
WORKER_ID = "paid-worker-1"
QUOTA_CLASS = "paid-quota"
ACCOUNT_LABEL = "acct-paid-1"
WORKER_USER = "paid_worker_1"
WORKER_UID = 60001
WORKER_GID = 60001
BRIDGE_UID = 501
PIN_VERSION = 3
FENCE_GENERATION = 7
PROMPT = "Analyse the supplied sealed text and answer with the result schema."
RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer"],
}


def _canonical(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _contract_owner():
    from control_plane import paid_model_execution_contract as contract
    return contract


def _paid_constraints() -> dict:
    return {
        "execution_profile_id": PAID_PROFILE_ID,
        "execution_profile_digest": PROFILE_DIGEST,
        "capability_policy_version": CAPABILITY_POLICY_VERSION,
        "capability_policy_digest": CAPABILITY_POLICY_DIGEST,
    }


def _capacity_join_wire(worker_source_config_digest: str) -> dict:
    return {
        "schema": JOIN_SCHEMA,
        "host_ref": HOST_REF,
        "capacity_capability_id": "cap-paid-1",
        "provider_capacity_schema": PROVIDER_CAPACITY_SCHEMA,
        "worker_source_config_digest": worker_source_config_digest,
    }


def _paid_capacity_metadata() -> dict:
    return {
        "adapter_id": PAID_ADAPTER_ID,
        "capacity_join": _capacity_join_wire("9" * 64),
        "worker_provider": PAID_PROVIDER,
        "model_alias": "glm-5.3",
        **_paid_constraints(),
    }


@pytest.fixture()
def capacity_row():
    """One selection-shaped capacity row, exactly like the existing query."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE worker_quota_classes (
          worker_id TEXT NOT NULL, quota_class TEXT NOT NULL,
          provider TEXT NOT NULL, model TEXT, metadata_json TEXT NOT NULL,
          PRIMARY KEY(worker_id, quota_class)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE workers (
          worker_id TEXT PRIMARY KEY, provider TEXT NOT NULL,
          account_label TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO workers VALUES (?,?,?)", (WORKER_ID, PAID_PROVIDER,
                                               ACCOUNT_LABEL)
    )
    connection.execute(
        "INSERT INTO worker_quota_classes VALUES (?,?,?,?,?)",
        (WORKER_ID, QUOTA_CLASS, PAID_PROVIDER, "glm-5.3",
         _canonical(_paid_capacity_metadata())),
    )

    def selected(worker_id: str = WORKER_ID, quota_class: str = QUOTA_CLASS):
        return connection.execute(
            """
            SELECT q.*, w.provider AS worker_provider, w.account_label
            FROM worker_quota_classes q JOIN workers w ON w.worker_id=q.worker_id
            WHERE q.worker_id=? AND q.quota_class=?
            """,
            (worker_id, quota_class),
        ).fetchone()

    selected.connection = connection
    return selected


def test_paid_claim_binding_returns_immutable_claim_data(capacity_row):
    binding = paid_claim_binding(capacity_row(), _paid_constraints())
    assert binding == {
        "schema_version": PAID_CAPACITY_BINDING_SCHEMA,
        "worker_id": WORKER_ID,
        "quota_class": QUOTA_CLASS,
        "provider": PAID_PROVIDER,
        "account_label": ACCOUNT_LABEL,
        "adapter_id": PAID_ADAPTER_ID,
        "capacity_join": _capacity_join_wire("9" * 64),
        "execution_profile_id": PAID_PROFILE_ID,
        "execution_profile_digest": PROFILE_DIGEST,
        "capability_policy_version": CAPABILITY_POLICY_VERSION,
        "capability_policy_digest": CAPABILITY_POLICY_DIGEST,
    }
    # Immutable claim DATA: the join snapshot is a fresh closed wire copy.
    assert binding["capacity_join"] is not _paid_capacity_metadata()[
        "capacity_join"
    ]


def test_paid_claim_binding_is_none_for_other_profiles(capacity_row):
    constraints = _paid_constraints() | {
        "execution_profile_id": "claude-code.executive.v1"
    }
    assert paid_claim_binding(capacity_row(), constraints) is None
    assert paid_claim_binding(
        capacity_row(), {"routing_policy_version": "rp1"}
    ) is None


def test_paid_claim_binding_refuses_non_mapping_constraints(capacity_row):
    with pytest.raises(er.StateConflict, match="constraints must be a mapping"):
        paid_claim_binding(capacity_row(), None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adapter_id", "attended-fabric"),
        ("execution_profile_digest", "ff" * 32),
        ("capability_policy_version", "other-policy"),
        ("capacity_join", {"schema": JOIN_SCHEMA}),
    ],
)
def test_paid_claim_binding_refuses_paid_metadata_drift(
    capacity_row, field, value
):
    metadata = _paid_capacity_metadata()
    metadata[field] = value
    capacity_row.connection.execute(
        "UPDATE worker_quota_classes SET metadata_json=? WHERE worker_id=?",
        (_canonical(metadata), WORKER_ID),
    )
    with pytest.raises(er.StateConflict):
        paid_claim_binding(capacity_row(), _paid_constraints())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "openai"),
        ("model", "gpt-5.3"),
        ("account_label", None),
    ],
)
def test_paid_claim_binding_refuses_foreign_capacity_identity(
    capacity_row, field, value
):
    connection = capacity_row.connection
    if field == "account_label":
        connection.execute("UPDATE workers SET account_label=NULL")
    else:
        connection.execute(
            f"UPDATE worker_quota_classes SET {field}=? WHERE worker_id=?",
            (value, WORKER_ID),
        )
    with pytest.raises(er.StateConflict):
        paid_claim_binding(capacity_row(), _paid_constraints())


def test_paid_claim_binding_refuses_foreign_worker_provider(capacity_row):
    # The selection joins the Worker row's provider as worker_provider; a
    # Worker whose provider differs from the quota provider cannot be paid.
    capacity_row.connection.execute(
        "UPDATE workers SET provider='openai' WHERE worker_id=?", (WORKER_ID,)
    )
    with pytest.raises(er.StateConflict):
        paid_claim_binding(capacity_row(), _paid_constraints())


def test_paid_claim_binding_refuses_noncanonical_capacity_metadata(capacity_row):
    metadata = _paid_capacity_metadata()
    capacity_row.connection.execute(
        "UPDATE worker_quota_classes SET metadata_json=? WHERE worker_id=?",
        (json.dumps(metadata), WORKER_ID),  # not canonical: key order/spacing
    )
    with pytest.raises(er.StateConflict):
        paid_claim_binding(capacity_row(), _paid_constraints())


@pytest.fixture()
def dispatch_store():
    """Minimal jobs/attempts store for the paid dispatch classification."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE jobs (job_id TEXT PRIMARY KEY, constraints_json TEXT)"
    )
    connection.execute(
        """
        CREATE TABLE attempts (
          attempt_id TEXT PRIMARY KEY, job_id TEXT, launch_metadata_json TEXT
        )
        """
    )
    return connection


def _insert_dispatch_pair(connection, *, job_constraints, metadata):
    connection.execute(
        "INSERT INTO jobs VALUES (?,?)", (JOB_ID, _canonical(job_constraints))
    )
    connection.execute(
        "INSERT INTO attempts VALUES (?,?,?)",
        (ATTEMPT_ID, JOB_ID, _canonical(metadata)),
    )
    return connection.execute(
        "SELECT * FROM attempts WHERE attempt_id=?", (ATTEMPT_ID,)
    ).fetchone()


def test_paid_job_attempt_classifies_paid(dispatch_store):
    row = _insert_dispatch_pair(
        dispatch_store, job_constraints=_paid_constraints(), metadata={}
    )
    assert is_paid_attempt(dispatch_store, row) is True


def test_ordinary_attempt_classifies_not_paid(dispatch_store):
    row = _insert_dispatch_pair(
        dispatch_store,
        job_constraints={"routing_policy_version": "rp1"},
        metadata={
            "schema_version": "mastermind.executive_process_launch/v1",
            "routing": {"adapter_id": "attempt-bound-remote-worker"},
        },
    )
    assert is_paid_attempt(dispatch_store, row) is False


@pytest.mark.parametrize(
    "metadata",
    [
        {"schema_version": PAID_METADATA_SCHEMA},
        {
            "launch_attestation": {"schema_version": PAID_ATTESTATION_SCHEMA},
        },
        {"routing": {"adapter_id": PAID_ADAPTER_ID}},
        {"routing": {"execution_profile_id": PAID_PROFILE_ID}},
    ],
)
def test_paid_markers_on_nonpaid_job_refuse_downgrade(
    dispatch_store, metadata
):
    row = _insert_dispatch_pair(
        dispatch_store,
        job_constraints={"routing_policy_version": "rp1"},
        metadata=metadata,
    )
    with pytest.raises(
        er.StateConflict, match="refuse label downgrade"
    ):
        is_paid_attempt(dispatch_store, row)


def test_paid_dispatch_without_job_refuses(dispatch_store):
    dispatch_store.execute(
        "INSERT INTO attempts VALUES (?,?,?)", (ATTEMPT_ID, JOB_ID, "{}")
    )
    row = dispatch_store.execute(
        "SELECT * FROM attempts WHERE attempt_id=?", (ATTEMPT_ID,)
    ).fetchone()
    with pytest.raises(er.StateConflict, match="lost its Job"):
        is_paid_attempt(dispatch_store, row)


def test_paid_launch_binding_identity_is_exact():
    binding = paid_launch_binding_identity(
        root_job_id=ROOT_ID,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        effective_grant_digest=GRANT_SHA,
        commission_sha256=COMMISSION_CONTENT_SHA,
    )
    assert binding == {
        "root_id": ROOT_ID,
        "job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "effective_grant_digest": GRANT_SHA,
        "commission_sha256": COMMISSION_CONTENT_SHA,
    }


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"root_job_id": ""}, "root_id"),
        ({"job_id": None}, "job_id"),
        ({"attempt_id": 7}, "attempt_id"),
        ({"effective_grant_digest": "z" * 64}, "effective_grant_digest"),
        ({"commission_sha256": "ab" * 31}, "commission_sha256"),
    ],
)
def test_paid_launch_binding_identity_refuses_bad_facts(kwargs, field):
    base = {
        "root_job_id": ROOT_ID,
        "job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "effective_grant_digest": GRANT_SHA,
        "commission_sha256": COMMISSION_CONTENT_SHA,
    }
    base.update(kwargs)
    with pytest.raises(er.StateConflict, match="binding identity is invalid"):
        paid_launch_binding_identity(**base)


def _paid_source_document() -> dict:
    return {
        "schema_version": PAID_WORKER_SOURCE_SCHEMA,
        "worker_id": WORKER_ID,
        "provider": PAID_PROVIDER,
        "host_ref": HOST_REF,
        "model": "glm-5.3",
        "worker_uid": WORKER_UID,
        "worker_gid": WORKER_GID,
        "worker_user": WORKER_USER,
        "binary": {
            "path": "/usr/local/libexec/mastermind/glm-worker",
            "real_path": "/usr/local/libexec/mastermind/glm-worker",
            "version": "glm-worker 1.4.2",
            "sha256": BINARY_SHA,
            "team_identifier": None,
            "size": 184467,
            "device": 64768,
            "inode": 123456,
            "mode": 0o755,
            "uid": 0,
            "gid": 0,
            "mtime_ns": 1_700_000_000_000_000_000,
        },
        "permission_profile_sha256": PERMISSION_SHA,
        "execution_profile_digest": PROFILE_DIGEST,
        "service_source_sha256": SERVICE_SOURCE_SHA,
        "bridge_uid": BRIDGE_UID,
        "socket_path": "/run/mastermind/paid-worker-1.sock",
        "capacity_capability_id": "cap-paid-1",
        "capture_root": "/remote/capture",
        "qualification": {
            "registry_key":"ubuntu0","registry_sha256":"1"*64,"transport_alias":"ubuntu0",
            "host_env_path":"/remote/HOST_ENV.sh","host_env_sha256":"2"*64,
            "boot_id":"boot-identity-1",
            "capture_identity":{"device":1,"inode":2,"mode":0o700,"uid":WORKER_UID,"gid":WORKER_GID},
            "qualifier_source_manifest_sha256":"3"*64,"probe_sha256":"4"*64,
            "qualifier_sources_sha256":dict.fromkeys(("host_pull.sh","host_pull_backend.py",
                "host_pull_probe.template","paid_host_qualification.py","remote_sub.sh"),"5"*64),
        },
    }


def _claim_for(source_document: dict) -> tuple[dict, dict]:
    claim_join = _capacity_join_wire(_digest(source_document))
    claim = {
        "schema_version": PAID_CAPACITY_BINDING_SCHEMA,
        "worker_id": WORKER_ID,
        "quota_class": QUOTA_CLASS,
        "provider": PAID_PROVIDER,
        "account_label": ACCOUNT_LABEL,
        "adapter_id": PAID_ADAPTER_ID,
        "capacity_join": claim_join,
        "execution_profile_id": PAID_PROFILE_ID,
        "execution_profile_digest": PROFILE_DIGEST,
        "capability_policy_version": CAPABILITY_POLICY_VERSION,
        "capability_policy_digest": CAPABILITY_POLICY_DIGEST,
    }
    return claim, claim_join


def _validated_source_reference():
    source_document = _paid_source_document()
    claim, claim_join = _claim_for(source_document)
    return source_document, claim, claim_join


def test_paid_worker_source_document_joins_the_immutable_claim():
    source_document, claim, claim_join = _validated_source_reference()
    validated = validated_paid_worker_source_document(
        source_document,
        claim=claim,
        claim_join=claim_join,
        expected_model="glm-5.3",
    )
    assert validated == source_document


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda s: s.update({"schema_version": "mastermind.paid_worker_source/v2"}),
         "not the closed wire"),
        (lambda s: s.update({"extra_field": 1}), "not the closed wire"),
        (lambda s: s.update({"worker_id": "other-worker"}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"provider": "openai"}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"model": "glm-5.3-flash"}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"host_ref": "host-" + "c" * 64}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"capacity_capability_id": "cap-other"}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"execution_profile_digest": "aa" * 32}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"worker_user": "bad user!"}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"worker_uid": 0}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"bridge_uid": -1}),
         "differs from the claimed capacity"),
        (lambda s: s.update({"service_source_sha256": "short"}),
         "differs from the claimed capacity"),
        (lambda s: s["binary"].update({"sha256": "not-a-digest"}),
         "binary attestation is invalid"),
        (lambda s: s["binary"].update({"size": 0}),
         "binary attestation is invalid"),
        (lambda s: s["binary"].pop("mode"), "not the closed wire"),
        (lambda s: s.update({"socket_path": "relative/worker.sock"}),
         "path is not an absolute string"),
        (lambda s: s.update({"socket_path": "/run/../run/worker.sock"}),
         "path is not canonical"),
    ],
)
def test_paid_worker_source_document_discriminates_substitutions(mutation, reason):
    source_document, claim, claim_join = _validated_source_reference()
    mutation(source_document)
    with pytest.raises(er.StateConflict, match=re.escape(reason)):
        validated_paid_worker_source_document(
            source_document,
            claim=claim,
            claim_join=claim_join,
            expected_model="glm-5.3",
        )


def test_paid_worker_source_document_refuses_config_digest_drift():
    source_document, claim, claim_join = _validated_source_reference()
    source_document["worker_user"] = "different_user"
    with pytest.raises(
        er.StateConflict, match="lost the claimed config digest"
    ):
        validated_paid_worker_source_document(
            source_document,
            claim=claim,
            claim_join=claim_join,
            expected_model="glm-5.3",
        )


def test_paid_physical_binding_excludes_capacity_and_carries_source_digest():
    source_document, _claim, claim_join = _validated_source_reference()
    physical = paid_physical_binding_from_worker_source(
        source_document,
        worker_source_config_digest=claim_join["worker_source_config_digest"],
    )
    assert "capacity_capability_id" not in physical
    assert set(physical) == (
        set(source_document)
        - {"schema_version", "capacity_capability_id"}
        | {"schema_version", "worker_source_config_digest"}
    )
    assert physical["schema_version"] == PAID_PHYSICAL_SCHEMA
    assert (
        physical["worker_source_config_digest"]
        == claim_join["worker_source_config_digest"]
    )
    for key in ("worker_id", "host_ref", "model", "worker_uid", "binary"):
        assert physical[key] == source_document[key]
    assert orchestration_digest(physical) != orchestration_digest(source_document)


def test_paid_physical_binding_refuses_bad_inputs():
    source_document, _claim, claim_join = _validated_source_reference()
    with pytest.raises(er.StateConflict):
        paid_physical_binding_from_worker_source(
            dict(source_document, extra=1),
            worker_source_config_digest=claim_join["worker_source_config_digest"],
        )
    with pytest.raises(er.StateConflict):
        paid_physical_binding_from_worker_source(
            source_document,
            worker_source_config_digest="nope",
        )


def test_paid_compiler_subset_is_the_exact_sealed_input_view():
    request = {
        "binding": {"root_id": ROOT_ID},
        "physical_binding_sha256": GRANT_SHA,
        "launch_spec": {"prompt": PROMPT},
        "validation_commands": [],
        "paid_route": {"provider": PAID_PROVIDER},
        "paid_input": {"prompt": PROMPT, "result_schema": RESULT_SCHEMA},
        "paid_physical_binding": {"schema_version": PAID_PHYSICAL_SCHEMA},
        "paid_source_config": {"schema_version": PAID_WORKER_SOURCE_SCHEMA},
        "paid_account": {"provider": PAID_PROVIDER},
        "control_recovery": {"context": "turn-start"},
        "control_start": {"channel": "control"},
        "start_request_sha256": "aa" * 32,
    }
    subset = _paid_compiler_subset(request)
    assert set(subset) == {
        "binding",
        "physical_binding_sha256",
        "launch_spec",
        "validation_commands",
        "paid_route",
        "paid_input",
        "control_recovery",
    }
    assert subset["control_recovery"] == {"context": "turn-start"}


def test_paid_metadata_markers_are_closed():
    assert _paid_metadata_markers({"schema_version": PAID_METADATA_SCHEMA})
    assert _paid_metadata_markers(
        {"launch_attestation": {"schema_version": PAID_ATTESTATION_SCHEMA}}
    )
    assert _paid_metadata_markers({"routing": {"adapter_id": PAID_ADAPTER_ID}})
    assert _paid_metadata_markers(
        {"routing": {"execution_profile_id": PAID_PROFILE_ID}}
    )
    assert not _paid_metadata_markers({})
    assert not _paid_metadata_markers(
        {"routing": {"adapter_id": "attended-fabric"}}
    )
    assert not _paid_metadata_markers("not-a-mapping")
    assert not _paid_metadata_markers(None)


def test_paid_sealed_result_requires_work_or_repair_role():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
    row = connection.execute(
        "SELECT * FROM jobs WHERE job_id='missing'"
    ).fetchone()
    assert row is None
    for role in ("plan", "review", "aggregation", None):
        with pytest.raises(
            er.StateConflict, match="require the work or repair role"
        ):
            paid_sealed_worker_result_payload(
                connection, row, expected_role=role, terminal_payload={}
            )


def test_paid_terminal_evidence_refuses_non_paid_seals():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE attempts (
          attempt_id TEXT PRIMARY KEY, job_id TEXT,
          launch_metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "INSERT INTO attempts VALUES (?,?,?)", (ATTEMPT_ID, JOB_ID, "{}")
    )
    row = connection.execute(
        "SELECT * FROM attempts WHERE attempt_id=?", (ATTEMPT_ID,)
    ).fetchone()
    legacy_seal = {
        "schema_version": "mastermind.sealed_worker_result_receipt/v1",
        "provider_session_id": "provider-session",
    }
    with pytest.raises(
        er.StateConflict, match="not the paid result receipt"
    ):
        validated_paid_terminal_evidence(
            connection, attempt_row=row, seal=legacy_seal
        )
    with pytest.raises(
        er.StateConflict, match="not the paid result receipt"
    ):
        validated_paid_terminal_evidence(connection, attempt_row=row, seal={})
    drifted = dict(_paid_receipt_shaped_seal(), unexpected=1)
    with pytest.raises(
        er.StateConflict, match="not the paid result receipt"
    ):
        validated_paid_terminal_evidence(
            connection, attempt_row=row, seal=drifted
        )


def _paid_receipt_shaped_seal() -> dict:
    """A receipt-shaped seal for the closed-wire gate only (never accepted)."""
    seal = {"schema_version": PAID_RESULT_RECEIPT_SCHEMA}
    for key in (
        "orchestration_role",
        "session_epoch_id",
        "candidate_event_command_id",
        "observed_attestation_digest",
        "work_admission_command_id",
        "policy_sha",
        "execution_principal_snapshot_digest",
        "placement_snapshot_digest",
        "effective_grant_digest",
    ):
        seal.setdefault(key, "x")
    seal.setdefault("result_envelope", {})
    seal.setdefault("result_envelope_digest", "x")
    seal.setdefault("role_result_digest", "x")
    seal.setdefault("candidate_event_digest", "x")
    seal.setdefault("provider_turn_artifact_digest", "x")
    seal.setdefault("raw_result_observation_digest", "x")
    seal.setdefault("canonical_result_byte_length", 0)
    seal.setdefault("provider_session_id", None)
    seal.setdefault("provider_native_turn_id", None)
    seal.setdefault("job_id", JOB_ID)
    seal.setdefault("attempt_id", ATTEMPT_ID)
    seal.setdefault("worker_id", WORKER_ID)
    seal.setdefault("quota_class", QUOTA_CLASS)
    seal["orchestration_role"] = "work"
    return seal


# ---------------------------------------------------------------------------
# Deeper launch-material discriminators: they need the canonical paid
# contract owner for the compiled sealed-input descriptor, so they run only
# where the real paid stack is importable.  Nothing here is faked.
# ---------------------------------------------------------------------------


def test_runtime_profile_constants_match_the_contract_owner():
    contract = _contract_owner()
    assert contract.PROFILE_ID == PAID_PROFILE_ID
    assert contract.ADAPTER_ID == PAID_ADAPTER_ID
    assert contract.ATTESTATION_SCHEMA == PAID_ATTESTATION_SCHEMA
    assert set(contract.MODELS) == set(PAID_MODELS)


class PaidLaunchFixture:
    """One internally-consistent paid launch joined into a plain SQL fixture.

    This is ordinary row DATA shaped like the existing durable writes; it is
    not a Runtime, store or owner.  ``mutate`` runs on the fully built object
    graph before serialization so each test can drift exactly one fact.
    """

    def __init__(self, *, mutate=None) -> None:
        self.objects = self._build()
        if mutate is not None:
            mutate(self.objects)
        self.recompute()
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self._persist()

    def recompute(self) -> None:
        """Recompute every derived digest after a structural mutation.

        A refused compile keeps the previous descriptor-derived evidence; the
        module under test recompiles the sealed input itself and refuses
        before the evidence check ever runs.
        """
        objects = self.objects
        grant_sha = _digest(objects["grant"])
        objects["grant_sha"] = grant_sha
        request = objects["identity"]["request"]
        request["binding"]["effective_grant_digest"] = grant_sha
        request["launch_spec"]["effective_grant_digest"] = grant_sha
        objects["metadata"]["effective_grant_digest"] = grant_sha
        try:
            descriptor = objects["contract"].descriptor(
                _paid_compiler_subset(request)
            )
        except objects["contract"].PaidModelContractRefused:
            descriptor = None
        if descriptor is not None:
            objects["descriptor"] = descriptor
            evidence = objects["attestation"]["evidence"]
            evidence["policy_sha256"] = descriptor["policy_sha256"]
            evidence["prompt_sha256"] = descriptor["prompt_sha256"]
            evidence["request_body_sha256"] = descriptor["request_body_sha256"]
            evidence["result_schema_sha256"] = descriptor[
                "result_schema_sha256"
            ]
            evidence["physical_binding_sha256"] = objects["physical_sha"]
        self.reseal_metadata()

    # -- construction ------------------------------------------------------

    def _build(self) -> dict:
        contract = _contract_owner()
        source_document = _paid_source_document()
        claim, claim_join = _claim_for(source_document)
        grant = {
            "schema_version": GRANT_SCHEMA,
            "role": "work",
            "job_id": JOB_ID,
            "policy_sha": POLICY_SHA,
            "authorities": ["READ"],
            "write_paths": [],
            "validation_argv": [],
        }
        grant_sha = _digest(grant)
        binding = paid_launch_binding_identity(
            root_job_id=ROOT_ID,
            job_id=JOB_ID,
            attempt_id=ATTEMPT_ID,
            effective_grant_digest=grant_sha,
            commission_sha256=COMMISSION_CONTENT_SHA,
        )
        physical = paid_physical_binding_from_worker_source(
            source_document,
            worker_source_config_digest=claim_join[
                "worker_source_config_digest"
            ],
        )
        physical_sha = orchestration_digest(physical)
        fields = {
            "job_id": JOB_ID,
            "run_id": ATTEMPT_ID,
            "worker_id": WORKER_ID,
            "worker_user": WORKER_USER,
            "model": "glm-5.3",
            "timeout_seconds": 600,
            "effective_grant_digest": grant_sha,
            "authorities": ["READ"],
            "authority": None,
            "allowed_artifact_paths": [],
            "isolation_manifest_sha256": ISOLATION_SHA,
            "expected_base_sha": None,
            "expected_worker_uid": WORKER_UID,
            "expected_worker_gid": WORKER_GID,
        }
        request = {
            "binding": binding,
            "physical_binding_sha256": physical_sha,
            "launch_spec": {**fields, "prompt": PROMPT},
            "validation_commands": [],
            "paid_route": {
                "provider": PAID_PROVIDER,
                "host_ref": HOST_REF,
                "model": "glm-5.3",
                "parent_job_id": ROOT_ID,
            },
            "paid_input": {"prompt": PROMPT, "result_schema": RESULT_SCHEMA},
            "paid_physical_binding": physical,
            "paid_source_config": source_document,
            "paid_account": ACCOUNT_LABEL,
            "paid_quota_class": QUOTA_CLASS,
            "control_recovery": {"context": "turn-start"},
        }
        descriptor = contract.descriptor(_paid_compiler_subset(request))
        attestation = {
            "schema_version": PAID_ATTESTATION_SCHEMA,
            "profile_id": PAID_PROFILE_ID, "adapter_id": PAID_ADAPTER_ID,
            "execution_surface": "glm-model-only", "binding": binding,
            "paid_route": request["paid_route"], "worker_id": WORKER_ID, "quota_class": QUOTA_CLASS,
            "process_identity": {
                "observed_user": WORKER_USER,
                "effective_uid": WORKER_UID,
                "effective_gid": WORKER_GID,
                "real_uid": WORKER_UID,
                "real_gid": WORKER_GID,
                "pid": 4242, "session_id": 4242, "launch_nonce": "unit-nonce",

                "pgid": 4242,
                "start_identity": "start-identity-1",
                "boot_id": "boot-identity-1",
            },
            "lease_binding": {"lease_id":"lease-unit", "orchestrator_id":ROOT_ID, "pool":"glm",
                "account":ACCOUNT_LABEL,"host_ref":HOST_REF,"model":"glm-5.3",
                "controller_process":{"pid":111,"start_identity":"controller-start","boot_id":"control-boot"},
                "runtime_fence_generation":FENCE_GENERATION,"runtime_pin_version":PIN_VERSION},
            "evidence": {
                "capsule_binding_sha256":"6"*64,"capture_contract_sha256":"7"*64,
                "policy_sha256": descriptor["policy_sha256"],
                "prompt_sha256": descriptor["prompt_sha256"],
                "request_body_sha256": descriptor["request_body_sha256"],
                "result_schema_sha256": descriptor["result_schema_sha256"],
                "physical_binding_sha256": physical_sha,
                "pin_identity_sha256": "pending",
                "python_sha256": BINARY_SHA,
                "control_input_isolation_manifest_sha256": ISOLATION_SHA,
                "source_manifest_sha256": SOURCE_MANIFEST_SHA,
            },
        }
        identity = {
            "physical_binding_sha256": physical_sha,
            "request": request,
        }
        identity_sha = orchestration_digest(identity)
        attestation["evidence"]["pin_identity_sha256"] = identity_sha
        metadata = {
            "schema_version": PAID_METADATA_SCHEMA,
            "launch_attestation": attestation,
            "launch_attestation_sha256": orchestration_digest(attestation),
            "launch_attestation_path": (
                f"/runs/{JOB_ID}/{ATTEMPT_ID}/paid-launch-attestation.json"
            ),
            "authority_policy_hash": POLICY_SHA,
            "authorities": ["READ"],
            "effective_grant_digest": grant_sha,
            "write_paths": [],
            "validation_argv": [],
            "quota_class": QUOTA_CLASS,
            "routing": {
                "adapter_id": PAID_ADAPTER_ID,
                "policy_version":"unit-routing-v1", "preferred_model_aliases":["glm.paid.sealed-input"],
                "selected_model_alias":"glm.paid.sealed-input", "provider_alias":"glm",
                **_paid_constraints(),
            },
            "paid_recovery_binding": {"adapter_id": PAID_ADAPTER_ID},
            "paid_launch_identity": identity,
            "paid_launch_identity_sha256": identity_sha,
            er.REMOTE_LAUNCH_IDENTITY_KEY: {
                "schema_version": er.REMOTE_LAUNCH_IDENTITY_SCHEMA,
                "sha256": identity_sha,
            },
        }
        placement = build_placement_snapshot(
            worker_id=WORKER_ID,
            quota_class=QUOTA_CLASS,
            provider=PAID_PROVIDER,
            account_label=ACCOUNT_LABEL,
            observed_at_ms=1_700_000_000_000,
        )
        return {
            "contract": contract,
            "source_document": source_document,
            "claim": claim,
            "claim_join": claim_join,
            "binding": binding,
            "physical": physical,
            "physical_sha": physical_sha,
            "request": request,
            "identity": identity,
            "identity_sha": identity_sha,
            "attestation": attestation,
            "metadata": metadata,
            "grant": grant,
            "grant_sha": grant_sha,
            "placement": placement,
            "claim_payload": {
                "fence_generation":FENCE_GENERATION,"lease_owner":"unit-supervisor",
                **_paid_constraints(),
                "paid_capacity_binding": claim,
            },
            "pin_payload": {
                "identity_digest": identity_sha,
                "paid_runtime_pin_version": PIN_VERSION,
                "paid_runtime_fence_generation": FENCE_GENERATION,
            },
        }

    def reseal_metadata(self) -> None:
        """Recompute every digest under ``metadata`` after a mutation."""
        objects = self.objects
        identity = objects["identity"]
        identity_sha = orchestration_digest(identity)
        objects["identity_sha"] = identity_sha
        objects["attestation"]["evidence"]["pin_identity_sha256"] = identity_sha
        attestation = objects["attestation"]
        metadata = objects["metadata"]
        metadata["launch_attestation"] = attestation
        metadata["launch_attestation_sha256"] = orchestration_digest(attestation)
        metadata["paid_launch_identity"] = identity
        metadata["paid_launch_identity_sha256"] = identity_sha
        metadata[er.REMOTE_LAUNCH_IDENTITY_KEY] = {
            "schema_version": er.REMOTE_LAUNCH_IDENTITY_SCHEMA,
            "sha256": identity_sha,
        }
        objects["pin_payload"]["identity_digest"] = identity_sha

    def reseal_and_persist(self) -> None:
        """Reseal the derived digests and write metadata and pin Event rows."""
        self.reseal_metadata()
        self.update_metadata()
        self.update_event(
            "ATTEMPT_REMOTE_LAUNCH_PINNED",
            payload_json=_canonical(self.objects["pin_payload"]),
        )

    # -- persistence -------------------------------------------------------

    def _persist(self) -> None:
        objects = self.objects
        root_provenance = {
            "schema_version": PROVENANCE_SCHEMA,
            "creator": "ceo_intent",
            "source_id": "dialogue-parent-1",
            "source_digest": COMMISSION_CONTENT_SHA,
            "command_id": "cmd-root-create-1",
            "job_id": ROOT_ID,
            "parent_job_id": None,
            "root_job_id": ROOT_ID,
            "role": "aggregation",
        }
        dialogue_source = {
            "schema_version": DIALOGUE_SOURCE_SCHEMA,
            "work_ref": "WS:PAIDRUN1",
            "commission_ref": {
                "repository": "example-org/mastermind",
                "commit": "ab" * 20,
                "path": "commissions/paid-run-1.md",
                "content_sha256": COMMISSION_CONTENT_SHA,
            },
            "watch_mode": None,
        }
        creation_payload = {
            "provenance": {
                "workstream": "WS:PAIDRUN1",
                "dialogue_source": dialogue_source,
                "dialogue_source_digest": _digest(dialogue_source),
            }
        }
        child_provenance = {
            "schema_version": PROVENANCE_SCHEMA,
            "creator": "coo_cycle",
            "source_id": "plan-step-1",
            "source_digest": PROFILE_DIGEST,
            "command_id": "cmd-child-create-1",
            "job_id": JOB_ID,
            "parent_job_id": ROOT_ID,
            "root_job_id": ROOT_ID,
            "role": "work",
        }
        connection = self.connection
        connection.execute(
            """
            CREATE TABLE jobs (
              job_id TEXT PRIMARY KEY, parent_job_id TEXT, root_job_id TEXT,
              orchestration_role TEXT, constraints_json TEXT,
              validation_commands_json TEXT, result_json TEXT,
              orchestration_provenance_json TEXT,
              orchestration_provenance_digest TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE attempts (
              attempt_id TEXT PRIMARY KEY, job_id TEXT, worker_id TEXT,
              quota_class TEXT, authority_policy_hash TEXT,
              fence_generation INTEGER, pid INTEGER, pgid INTEGER,
              process_start_identity TEXT, boot_id TEXT,
              provider_session_id TEXT, exit_code INTEGER,
              launch_metadata_json TEXT, effective_grant_json TEXT,
              effective_grant_digest TEXT, placement_snapshot_json TEXT,
              placement_snapshot_digest TEXT,
              execution_principal_snapshot_json TEXT,
              execution_principal_snapshot_digest TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              aggregate_type TEXT, aggregate_id TEXT, event_type TEXT,
              command_id TEXT, actor TEXT, job_id TEXT, attempt_id TEXT,
              worker_id TEXT, quota_class TEXT, payload_json TEXT
            )
            """
        )
        connection.execute(
            "CREATE TABLE harness_session_epochs (attempt_id TEXT)"
        )
        constraints = {**_paid_constraints(), "routing_policy_version":"unit-routing-v1",
            "preferred_model_aliases":["glm.paid.sealed-input"]}
        connection.executemany(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    ROOT_ID,
                    None,
                    ROOT_ID,
                    "aggregation",
                    _canonical(constraints),
                    "[]",
                    None,
                    _canonical(root_provenance),
                    _digest(root_provenance),
                ),
                (
                    JOB_ID,
                    ROOT_ID,
                    ROOT_ID,
                    "work",
                    _canonical(constraints),
                    "[]",
                    None,
                    _canonical(child_provenance),
                    _digest(child_provenance),
                ),
            ],
        )
        attempt = objects["attempt"] = {
            "attempt_id": ATTEMPT_ID,
            "job_id": JOB_ID,
            "worker_id": WORKER_ID,
            "quota_class": QUOTA_CLASS,
            "authority_policy_hash": POLICY_SHA,
            "fence_generation": FENCE_GENERATION,
            "pid": 4242,
            "pgid": 4242,
            "process_start_identity": "start-identity-1",
            "boot_id": "boot-identity-1",
            "provider_session_id": None,
            "exit_code": None,
            "launch_metadata_json": _canonical(objects["metadata"]),
            "effective_grant_json": _canonical(objects["grant"]),
            "effective_grant_digest": _digest(objects["grant"]),
            "placement_snapshot_json": _canonical(objects["placement"]),
            "placement_snapshot_digest": _digest(objects["placement"]),
            "execution_principal_snapshot_json": None,
            "execution_principal_snapshot_digest": None,
        }
        connection.execute(
            "INSERT INTO attempts VALUES (" + ",".join("?" * 19) + ")",
            tuple(attempt.values()),
        )
        claim_event = objects["claim_event"] = {
            "aggregate_type": "job",
            "aggregate_id": JOB_ID,
            "event_type": "JOB_CLAIMED",
            "command_id": "cmd-claim-1",
            "actor": "operator",
            "job_id": JOB_ID,
            "attempt_id": ATTEMPT_ID,
            "worker_id": WORKER_ID,
            "quota_class": QUOTA_CLASS,
            "payload_json": _canonical(objects["claim_payload"]),
        }
        pin_event = objects["pin_event"] = {
            "aggregate_type": "attempt",
            "aggregate_id": ATTEMPT_ID,
            "event_type": "ATTEMPT_REMOTE_LAUNCH_PINNED",
            "command_id": "cmd-pin-1",
            "actor": "supervisor",
            "job_id": JOB_ID,
            "attempt_id": ATTEMPT_ID,
            "worker_id": WORKER_ID,
            "quota_class": QUOTA_CLASS,
            "payload_json": _canonical(objects["pin_payload"]),
        }
        running_event = {
            "aggregate_type": "attempt",
            "aggregate_id": ATTEMPT_ID,
            "event_type": "ATTEMPT_RUNNING",
            "command_id": "cmd-running-1",
            "actor": "supervisor",
            "job_id": JOB_ID,
            "attempt_id": ATTEMPT_ID,
            "worker_id": WORKER_ID,
            "quota_class": QUOTA_CLASS,
            "payload_json": _canonical({}),
        }
        creation_event = objects["creation_event"] = {
            "aggregate_type": "job",
            "aggregate_id": ROOT_ID,
            "event_type": "JOB_CREATED",
            "command_id": "cmd-root-create-1",
            "actor": "operator",
            "job_id": ROOT_ID,
            "attempt_id": None,
            "worker_id": None,
            "quota_class": None,
            "payload_json": _canonical(creation_payload),
        }
        connection.executemany(
            "INSERT INTO events (aggregate_type,aggregate_id,event_type,"
            "command_id,actor,job_id,attempt_id,worker_id,quota_class,"
            "payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                tuple(event[name] for name in (
                    "aggregate_type", "aggregate_id", "event_type",
                    "command_id", "actor", "job_id", "attempt_id",
                    "worker_id", "quota_class", "payload_json",
                ))
                for event in (
                    creation_event, claim_event, pin_event, running_event
                )
            ],
        )

    # -- accessors ---------------------------------------------------------

    def attempt_row(self):
        return self.connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (ATTEMPT_ID,)
        ).fetchone()

    def update_metadata(self) -> None:
        self.connection.execute(
            "UPDATE attempts SET launch_metadata_json=? WHERE attempt_id=?",
            (_canonical(self.objects["metadata"]), ATTEMPT_ID),
        )

    def update_attempt(self, **values) -> None:
        assignments = ",".join(f"{name}=?" for name in values)
        self.connection.execute(
            f"UPDATE attempts SET {assignments} WHERE attempt_id=?",
            (*values.values(), ATTEMPT_ID),
        )

    def update_event(self, event_type: str, **values) -> None:
        assignments = ",".join(f"{name}=?" for name in values)
        self.connection.execute(
            f"UPDATE events SET {assignments} WHERE event_type=?",
            (*values.values(), event_type),
        )


@pytest.fixture()
def paid_launch():
    """One internally-consistent paid launch fixture (contract owner real)."""
    return PaidLaunchFixture()


def _assert_refused(fixture: PaidLaunchFixture, reason: str):
    with pytest.raises(er.StateConflict, match=re.escape(reason)):
        validated_paid_launch_material(fixture.connection, fixture.attempt_row())


def test_paid_launch_metadata_must_be_the_closed_wire(paid_launch):
    paid_launch.objects["metadata"]["unexpected"] = 1
    paid_launch.reseal_and_persist()
    _assert_refused(paid_launch, "metadata is not the closed wire")


def test_paid_launch_metadata_schema_is_exact(paid_launch):
    paid_launch.objects["metadata"]["schema_version"] = (
        "mastermind.executive_process_launch/v1"
    )
    paid_launch.reseal_and_persist()
    _assert_refused(paid_launch, "metadata schema is invalid")


def test_paid_launch_pin_binds_the_identity_digest(paid_launch):
    paid_launch.objects["metadata"][er.REMOTE_LAUNCH_IDENTITY_KEY]["sha256"] = (
        "0" * 64
    )
    paid_launch.update_metadata()
    _assert_refused(paid_launch, "paid remote launch pin is invalid")


def test_paid_launch_attestation_digest_is_joined(paid_launch):
    paid_launch.objects["metadata"]["launch_attestation_sha256"] = "0" * 64
    paid_launch.update_metadata()
    _assert_refused(paid_launch, "paid launch attestation is invalid")


def test_paid_launch_attestation_path_is_canonical_absolute(paid_launch):
    paid_launch.objects["metadata"]["launch_attestation_path"] = (
        "runs/relative.json"
    )
    paid_launch.update_metadata()
    _assert_refused(paid_launch, "path is not an absolute string")
    paid_launch.objects["metadata"]["launch_attestation_path"] = (
        "/runs/../secrets.json"
    )
    paid_launch.update_metadata()
    _assert_refused(paid_launch, "path is not canonical")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority_policy_hash", "0" * 64),
        ("effective_grant_digest", "0" * 64),
        ("quota_class", "other-quota"),
        ("validation_argv", ["pytest", "-q"]),
    ],
)
def test_paid_launch_metadata_binds_the_attempt(paid_launch, field, value):
    paid_launch.objects["metadata"][field] = value
    paid_launch.update_metadata()
    _assert_refused(paid_launch, "lost its Attempt bindings")


@pytest.mark.parametrize(
    "routing",
    [
        {"adapter_id": "attended-fabric", **_paid_constraints()},
        {**_paid_constraints()},
        {"adapter_id": PAID_ADAPTER_ID},
    ],
)
def test_paid_launch_routing_identity_is_exact(paid_launch, routing):
    paid_launch.objects["metadata"]["routing"] = routing
    paid_launch.update_metadata()
    _assert_refused(paid_launch, "routing identity is invalid")


def test_paid_launch_routing_joins_the_job_constraints(paid_launch):
    paid_launch.objects["metadata"]["routing"]["execution_profile_digest"] = "ee" * 32
    paid_launch.update_metadata()
    _assert_refused(
        paid_launch, "requires the canonical paid execution profile"
    )


def test_paid_launch_requires_the_paid_job_profile(paid_launch):
    paid_launch.connection.execute(
        "UPDATE jobs SET constraints_json=? WHERE job_id=?",
        (_canonical({"execution_profile_id": "claude-code.executive.v1"}),
         JOB_ID),
    )
    _assert_refused(
        paid_launch, "requires the canonical paid execution profile"
    )


@pytest.mark.parametrize("role", ["review", "plan", "aggregation", None])
def test_paid_launch_accepts_work_and_repair_only(paid_launch, role):
    paid_launch.connection.execute(
        "UPDATE jobs SET orchestration_role=? WHERE job_id=?", (role, JOB_ID)
    )
    _assert_refused(paid_launch, "accepts work and repair Jobs only")


def test_paid_launch_refuses_shell_validation_jobs(paid_launch):
    paid_launch.connection.execute(
        "UPDATE jobs SET validation_commands_json=? WHERE job_id=?",
        (_canonical(["pytest", "-q"]), JOB_ID),
    )
    _assert_refused(paid_launch, "without shell validations")


@pytest.mark.parametrize(
    "authorities",
    [["READ", "WRITE_BRANCH"], ["WRITE_BRANCH"], ["RUN_TESTS"], []],
)
def test_paid_grant_authorities_are_read_research_only(authorities):
    def mutate(objects):
        objects["grant"]["authorities"] = list(authorities)
        objects["metadata"]["authorities"] = list(authorities)

    _assert_refused(
        PaidLaunchFixture(mutate=mutate), "READ with optional RESEARCH only"
    )


def test_paid_grant_must_join_the_attempt():
    def mutate(objects):
        objects["grant"]["job_id"] = OTHER_JOB_ID

    _assert_refused(
        PaidLaunchFixture(mutate=mutate),
        "placement/grant launch binding is invalid",
    )


def test_paid_placement_must_join_the_claimed_quota(paid_launch):
    placement = build_placement_snapshot(
        worker_id="other-worker",
        quota_class=QUOTA_CLASS,
        provider=PAID_PROVIDER,
        account_label=ACCOUNT_LABEL,
        observed_at_ms=1_700_000_000_000,
    )
    paid_launch.connection.execute(
        "UPDATE attempts SET placement_snapshot_json=?, "
        "placement_snapshot_digest=? WHERE attempt_id=?",
        (_canonical(placement), _digest(placement), ATTEMPT_ID),
    )
    _assert_refused(paid_launch, "paid placement lost the claimed quota")


def test_paid_claim_cardinality_is_exact(paid_launch):
    connection = paid_launch.connection
    duplicate = dict(paid_launch.objects["claim_event"])
    duplicate["command_id"] = "cmd-claim-2"
    connection.execute(
        "INSERT INTO events (aggregate_type,aggregate_id,event_type,"
        "command_id,actor,job_id,attempt_id,worker_id,quota_class,"
        "payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        tuple(duplicate[name] for name in (
            "aggregate_type", "aggregate_id", "event_type", "command_id",
            "actor", "job_id", "attempt_id", "worker_id", "quota_class",
            "payload_json",
        )),
    )
    _assert_refused(paid_launch, "claim cardinality is not exact")


def test_paid_claim_binding_must_be_the_closed_wire(paid_launch):
    claim_payload = paid_launch.objects["claim_payload"]
    claim_payload["paid_capacity_binding"] = dict(
        claim_payload["paid_capacity_binding"], unexpected=1
    )
    paid_launch.update_event(
        "JOB_CLAIMED", payload_json=_canonical(claim_payload)
    )
    _assert_refused(
        paid_launch, "claim capacity binding is not the closed wire"
    )


def test_paid_claim_join_must_validate(paid_launch):
    claim_payload = paid_launch.objects["claim_payload"]
    claim_payload["paid_capacity_binding"] = dict(
        claim_payload["paid_capacity_binding"],
        capacity_join={"schema": JOIN_SCHEMA},
    )
    paid_launch.update_event(
        "JOB_CLAIMED", payload_json=_canonical(claim_payload)
    )
    _assert_refused(paid_launch, "claim capacity join is invalid")


def test_paid_claim_account_joins_the_placement(paid_launch):
    claim_payload = paid_launch.objects["claim_payload"]
    claim_payload["paid_capacity_binding"] = dict(
        claim_payload["paid_capacity_binding"],
        account_label="other-account",
    )
    paid_launch.update_event(
        "JOB_CLAIMED", payload_json=_canonical(claim_payload)
    )
    _assert_refused(
        paid_launch, "claim profile or account differs from the immutable claim"
    )


def test_paid_claim_profile_joins_job_constraints_and_routing(paid_launch):
    claim_payload = paid_launch.objects["claim_payload"]
    claim_payload["paid_capacity_binding"] = dict(
        claim_payload["paid_capacity_binding"],
        execution_profile_digest="ee" * 32,
    )
    paid_launch.update_event(
        "JOB_CLAIMED", payload_json=_canonical(claim_payload)
    )
    _assert_refused(
        paid_launch, "claim profile or account differs from the immutable claim"
    )


def test_paid_launch_request_is_the_closed_wire(paid_launch):
    paid_launch.objects["identity"]["request"]["unexpected"] = 1
    paid_launch.reseal_and_persist()
    _assert_refused(paid_launch, "request is not the closed wire")


def test_paid_launch_request_validation_commands_are_empty(paid_launch):
    paid_launch.objects["identity"]["request"]["validation_commands"] = [
        ["pytest", "-q"]
    ]
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "sealed input differs from the pinned launch request"
    )


def test_paid_launch_route_joins_the_claimed_capacity(paid_launch):
    paid_launch.objects["identity"]["request"]["paid_route"] = dict(
        paid_launch.objects["request"]["paid_route"], parent_job_id=OTHER_JOB_ID
    )
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "route differs from the claimed capacity"
    )


def test_paid_launch_route_parent_is_none_only_for_roots(paid_launch):
    paid_launch.objects["identity"]["request"]["paid_route"] = dict(
        paid_launch.objects["request"]["paid_route"], parent_job_id=None
    )
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "route differs from the claimed capacity"
    )


def test_paid_sealed_input_must_compile_under_the_contract(paid_launch):
    paid_launch.objects["identity"]["request"]["launch_spec"][
        "timeout_seconds"
    ] = 999_999
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "does not compile under the canonical contract"
    )


def test_paid_physical_binding_must_match_the_source(paid_launch):
    request = paid_launch.objects["identity"]["request"]
    request["paid_physical_binding"] = dict(
        request["paid_physical_binding"],
        capacity_capability_id="cap-paid-1",
    )
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "physical host binding differs from the worker source"
    )


def test_paid_account_joins_the_immutable_claim(paid_launch):
    paid_launch.objects["identity"]["request"]["paid_account"] = {
        "provider": PAID_PROVIDER,
        "account_label": "other-account",
    }
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "account differs from the immutable claim"
    )


def test_paid_evidence_joins_the_compiled_descriptor(paid_launch):
    evidence = paid_launch.objects["attestation"]["evidence"]
    evidence["policy_sha256"] = "0" * 64
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "evidence differs from the compiled sealed input"
    )


def test_paid_evidence_python_digest_joins_the_source_binary(paid_launch):
    evidence = paid_launch.objects["attestation"]["evidence"]
    evidence["python_sha256"] = "0" * 64
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "evidence differs from the compiled sealed input"
    )


def test_paid_evidence_carries_the_source_manifest_receipt_hash(paid_launch):
    evidence = paid_launch.objects["attestation"]["evidence"]
    evidence["source_manifest_sha256"] = "not-a-digest"
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "evidence differs from the compiled sealed input"
    )


def test_paid_isolation_manifest_is_genuine_control_input(paid_launch):
    evidence = paid_launch.objects["attestation"]["evidence"]
    evidence["control_input_isolation_manifest_sha256"] = "0" * 64
    paid_launch.reseal_and_persist()
    _assert_refused(
        paid_launch, "evidence differs from the compiled sealed input"
    )


def test_paid_process_identity_joins_the_durable_attempt(paid_launch):
    paid_launch.objects["attestation"]["process_identity"]["pid"] = 4243
    paid_launch.reseal_and_persist()
    _assert_refused(paid_launch, "OS/process identity is invalid")


def test_paid_launch_carries_no_provider_session(paid_launch):
    paid_launch.update_attempt(provider_session_id="provider-session-1")
    _assert_refused(paid_launch, "OS/process identity is invalid")


def test_paid_pin_event_is_exact(paid_launch):
    paid_launch.objects["pin_payload"]["identity_digest"] = "0" * 64
    paid_launch.update_event(
        "ATTEMPT_REMOTE_LAUNCH_PINNED",
        payload_json=_canonical(paid_launch.objects["pin_payload"]),
    )
    _assert_refused(paid_launch, "pin receipt is invalid")


def test_paid_pin_event_records_positive_runtime_state(paid_launch):
    pin_payload = paid_launch.objects["pin_payload"]
    pin_payload["paid_runtime_pin_version"] = 0
    paid_launch.update_event(
        "ATTEMPT_REMOTE_LAUNCH_PINNED",
        payload_json=_canonical(pin_payload),
    )
    _assert_refused(paid_launch, "pin receipt is invalid")
    pin_payload["paid_runtime_pin_version"] = PIN_VERSION
    pin_payload["paid_runtime_fence_generation"] = 0
    paid_launch.update_event(
        "ATTEMPT_REMOTE_LAUNCH_PINNED",
        payload_json=_canonical(pin_payload),
    )
    _assert_refused(paid_launch, "pin receipt is invalid")


def test_paid_pin_fence_must_equal_the_durable_lease(paid_launch):
    paid_launch.update_attempt(fence_generation=FENCE_GENERATION + 1)
    _assert_refused(
        paid_launch, "current fence has no exact original adoption history"
    )


def test_paid_launch_binding_joins_the_root_commission():
    def mutate(objects):
        objects["identity"]["request"]["binding"]["root_id"] = OTHER_JOB_ID

    _assert_refused(
        PaidLaunchFixture(mutate=mutate),
        "binding differs from the immutable commission",
    )
