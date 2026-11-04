"""Pure resident-input compiler coverage; fixtures establish no live trust."""

import ast
import hashlib
import json
from pathlib import Path
import traceback

import pytest
import copy

from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane.executive_release_contract import canonical_release_bytes
from ops.executive_os import release_owner_resident_inputs as r

OWNER = "11111111-1111-4111-8111-111111111111"
TARGET = "5" * 64
COMMIT = "1" * 40
TREE = "2" * 40
BOOT = "abcdef12-3456-4789-abcd-123456789abc"
PROVENANCE = "a" * 64
NOW = 2_000_000_000
OBSERVED = "2026-09-29T12:00:00Z"


def _policy_mapping():
    return {
        "schema": "mastermind.executive_release_controller_policy/v1",
        "policy_id": "release-policy",
        "generation": 7,
        "enabled": True,
        "issuer_digest": "1" * 64,
        "resource_digest": "2" * 64,
        "subject_digests": ["3" * 64],
        "client_refs": ["4" * 64],
        "required_scopes": ["mastermind.executive.intent.submit"],
        "actions": ["executive.release.upgrade"],
        "target_refs": [TARGET],
        "installer_profile_digests": ["6" * 64],
        "source_policy_modes": ["exact_protected_master"],
        "max_approval_lifetime_seconds": 300,
        "confirmation_requirement": "delegated",
    }


def _policy_source(mapping=None):
    value = _policy_mapping() if mapping is None else mapping
    lines = ["executive_release_controller_policy:"]
    for key, item in value.items():
        if type(item) is list:
            lines.append(f"  {key}:")
            lines.extend(f"    - {entry}" for entry in item)
        else:
            scalar = str(item).lower() if type(item) is bool else str(item)
            lines.append(f"  {key}: {scalar}")
    return ("\n".join(lines) + "\n").encode()


def _policy():
    return ReleaseControllerPolicy.from_bytes(_policy_source())


def _registration():
    return json.loads(
        r.compile_registration(
            owner_installation_id=OWNER,
            target_ref=TARGET,
            key_id="release-owner-key.v1",
            trust_generation=1,
            app_generation=2,
            registration_generation=3,
        )
    )


def _issuer(policy=None):
    return {
        "schema": "mastermind.executive_release_issuer_binding/v1",
        "owner_installation_id": OWNER,
        "target_ref": TARGET,
        "release_commit": COMMIT,
        "release_tree": TREE,
        "boot_id": BOOT,
        "role": "control",
        "control_uid": 450,
        "app_peer_uid": 458,
        "policy": _policy_mapping(),
        "binding_evidence_digest": "7" * 64,
        "observed_at": OBSERVED,
    }


def _configs():
    control = json.dumps(
        {
            "schema_version": "mastermind.executive_control_config/v1",
            "proof_base_sha": COMMIT,
            "python_runtime_provenance_digest": PROVENANCE,
            "control_uid": 450,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    broker = json.dumps(
        {
            "schema": "mastermind.executive_privileged_broker_config.v1",
            "release_root": "/Library/Application Support/MastermindExecutive/releases/" + COMMIT,
            "receipt_root": "/var/db/mastermind-executive/privileged-actions/receipts",
            "allowed_peer_uids": [450],
            "timeout_seconds": 120,
            "broker_version": "1",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return control, broker


def _installed(**changes):
    policy = changes.pop("policy", _policy())
    control, broker = _configs()
    values = {
        "registration": _registration(),
        "release_commit": COMMIT,
        "release_tree": TREE,
        "control_config_bytes": control,
        "broker_config_bytes": broker,
        "authority_map_bytes": policy._raw,
        "python_runtime_provenance_digest": PROVENANCE,
        "provider_attestation_bytes": b'{"accepted":"fixture"}\n',
        "provider_attestation_observed_at": OBSERVED,
        "issuer_binding_receipt": _issuer(policy),
        "issuer_binding_observed_at": OBSERVED,
        "boot_id": BOOT,
        "policy": policy,
        "app_peer_uid": 458,
        "_now_seconds": NOW,
    }
    values.update(changes)
    return json.loads(r.compile_installed_evidence(**values))


def _physical_evidence(**changes):
    value = {
        "actuator_generation": 7,
        "before": {
            "release_commit": COMMIT,
            "release_tree": TREE,
            "installed_manifest_digest": "d" * 64,
            "configuration_digest": _installed()["installed_configuration_digest"],
            "broker_source_commit": COMMIT,
            "broker_source_tree": TREE,
            "broker_binary_digest": "f" * 64,
            "service_generation_digests": {
                "control": "1" * 64,
                "worker": "2" * 64,
                "relay": "3" * 64,
                "gateway": "4" * 64,
                "broker": "5" * 64,
            },
        },
        "publication_operation_key": "release-resident-v2-test-001",
        "predecessor_evidence_digest": "6" * 64,
    }
    value.update(copy.deepcopy(changes))
    return value


def _v2_installed_raw(**physical_changes):
    policy = _policy()
    control, broker = _configs()
    configuration_files = [
        {"path": "config/control.json", "sha256": hashlib.sha256(control).hexdigest()},
        {"path": "config/authority_map.yml", "sha256": hashlib.sha256(policy._raw).hexdigest()},
        {"path": "config/privileged-broker.json", "sha256": hashlib.sha256(broker).hexdigest()},
    ]
    configuration_digest = hashlib.sha256(canonical_release_bytes({
        "schema": "mastermind.executive_installed_configuration_set/v1",
        "files": configuration_files,
    })).hexdigest()
    policy = _policy()
    control, broker = _configs()
    physical = _physical_evidence(**physical_changes)
    if "before" not in physical_changes:
        physical["before"]["configuration_digest"] = configuration_digest
    return r.compile_installed_evidence(
        registration=_registration(),
        release_commit=COMMIT,
        release_tree=TREE,
        control_config_bytes=control,
        broker_config_bytes=broker,
        authority_map_bytes=policy._raw,
        python_runtime_provenance_digest=PROVENANCE,
        provider_attestation_bytes=b'{"accepted":"fixture"}\n',
        provider_attestation_observed_at=OBSERVED,
        issuer_binding_receipt=_issuer(policy),
        issuer_binding_observed_at=OBSERVED,
        boot_id=BOOT,
        policy=policy,
        app_peer_uid=458,
        physical_evidence=physical,
        _now_seconds=NOW,
    )


def test_registration_is_exact_canonical_disabled_document():
    raw = r.compile_registration(
        owner_installation_id=OWNER,
        target_ref=TARGET,
        key_id="release-owner-key.v1",
        trust_generation=1,
        app_generation=2,
        registration_generation=3,
    )
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert raw[:-1] == canonical_release_bytes(json.loads(raw))
    assert set(json.loads(raw)) == r._REGISTRATION_FIELDS
    assert json.loads(raw)["enabled"] is False


@pytest.mark.parametrize(
    "change,code",
    [
        ({"enabled": True}, "REGISTRATION_ARMED"),
        ({"owner_installation_id": "00000000-0000-0000-0000-000000000000"}, "REGISTRATION_OWNER"),
        ({"target_ref": "0" * 64}, "REGISTRATION_TARGET"),
        ({"target_ref": "A" * 64}, "REGISTRATION_TARGET"),
        ({"key_id": "bad key"}, "REGISTRATION_KEY"),
        ({"trust_generation": True}, "REGISTRATION_GENERATION"),
        ({"app_generation": 0}, "REGISTRATION_GENERATION"),
        ({"registration_generation": 1 << 63}, "REGISTRATION_GENERATION"),
    ],
)
def test_registration_refuses_arming_and_invalid_identity(change, code):
    values = dict(
        owner_installation_id=OWNER,
        target_ref=TARGET,
        key_id="release-owner-key.v1",
        trust_generation=1,
        app_generation=2,
        registration_generation=3,
        enabled=False,
    )
    values.update(change)
    with pytest.raises(r.ReleaseOwnerInputError, match=f"^{code}$"):
        r.compile_registration(**values)


def test_empty_registry_has_only_exact_fields_and_no_transition():
    value = json.loads(r.compile_empty_registry(registration_generation=3, registry_generation=1))
    assert value == {
        "schema": "mastermind.executive_release_owner_staged_registry/v1",
        "registration_generation": 3,
        "registry_generation": 1,
        "transitions": [],
    }
    with pytest.raises(r.ReleaseOwnerInputError, match="^REGISTRY_GENERATION$"):
        r.compile_empty_registry(registration_generation=True, registry_generation=1)


def test_issuer_receipt_is_exact_and_uses_supplied_independent_digest():
    value = _issuer()
    raw = r.validate_issuer_binding_receipt(
        value,
        owner_installation_id=OWNER,
        target_ref=TARGET,
        release_commit=COMMIT,
        release_tree=TREE,
        boot_id=BOOT,
        policy=_policy(),
        app_peer_uid=458,
        _now_seconds=NOW,
    )
    assert json.loads(raw) == value
    assert json.loads(raw)["binding_evidence_digest"] == "7" * 64


@pytest.mark.parametrize(
    "field,replacement,code",
    [
        ("owner_installation_id", "22222222-2222-4222-8222-222222222222", "ISSUER_BINDING_MISMATCH"),
        ("target_ref", "8" * 64, "ISSUER_BINDING_MISMATCH"),
        ("release_commit", "8" * 40, "ISSUER_BINDING_MISMATCH"),
        ("release_tree", "8" * 40, "ISSUER_BINDING_MISMATCH"),
        ("boot_id", "other-boot", "ISSUER_BINDING_MISMATCH"),
        ("role", "app", "ISSUER_BINDING_MISMATCH"),
        ("control_uid", 451, "ISSUER_BINDING_MISMATCH"),
        ("app_peer_uid", True, "ISSUER_BINDING_MISMATCH"),
        ("binding_evidence_digest", "0" * 64, "ISSUER_EVIDENCE"),
        ("observed_at", "2999-01-01T00:00:00Z", "ISSUER_TIME"),
    ],
)
def test_issuer_receipt_refuses_join_and_evidence_drift(field, replacement, code):
    value = _issuer()
    value[field] = replacement
    with pytest.raises(r.ReleaseOwnerInputError, match=f"^{code}$"):
        r.validate_issuer_binding_receipt(
            value,
            owner_installation_id=OWNER,
            target_ref=TARGET,
            release_commit=COMMIT,
            release_tree=TREE,
            boot_id=BOOT,
            policy=_policy(),
            app_peer_uid=458,
            _now_seconds=NOW,
        )


def test_issuer_receipt_refuses_extra_missing_and_policy_mismatch():
    for mutate, code in (
        (lambda value: value.update(extra="x"), "ISSUER_BINDING_FIELDS"),
        (lambda value: value.pop("role"), "ISSUER_BINDING_FIELDS"),
        (lambda value: value["policy"].update(generation=8), "ISSUER_POLICY"),
    ):
        value = _issuer()
        mutate(value)
        with pytest.raises(r.ReleaseOwnerInputError, match=f"^{code}$"):
            r.validate_issuer_binding_receipt(
                value,
                owner_installation_id=OWNER,
                target_ref=TARGET,
                release_commit=COMMIT,
                release_tree=TREE,
                boot_id=BOOT,
                policy=_policy(),
                app_peer_uid=458,
                _now_seconds=NOW,
            )


def test_issuer_receipt_keeps_control_uid_fixed_at_450():
    value = _issuer()
    value["control_uid"] = 451
    with pytest.raises(r.ReleaseOwnerInputError, match="^ISSUER_UID$"):
        r.validate_issuer_binding_receipt(
            value,
            owner_installation_id=OWNER,
            target_ref=TARGET,
            release_commit=COMMIT,
            release_tree=TREE,
            boot_id=BOOT,
            policy=_policy(),
            control_uid=451,
            app_peer_uid=458,
            _now_seconds=NOW,
        )


def test_issuer_receipt_refuses_boolean_uid_equal_to_integer_one():
    value = _issuer()
    value["app_peer_uid"] = True
    with pytest.raises(r.ReleaseOwnerInputError, match="^ISSUER_BINDING_MISMATCH$"):
        r.validate_issuer_binding_receipt(
            value,
            owner_installation_id=OWNER,
            target_ref=TARGET,
            release_commit=COMMIT,
            release_tree=TREE,
            boot_id=BOOT,
            policy=_policy(),
            app_peer_uid=1,
            _now_seconds=NOW,
        )


@pytest.mark.parametrize(
    "boot_id",
    [
        "boot-accepted-1",
        "00000000-0000-0000-0000-000000000000",
        BOOT.upper(),
        BOOT.replace("-", ""),
    ],
)
def test_installed_evidence_requires_canonical_nonzero_boot_uuid(boot_id):
    issuer = _issuer()
    issuer["boot_id"] = boot_id
    with pytest.raises(r.ReleaseOwnerInputError, match="^INSTALLED_BOOT$"):
        _installed(boot_id=boot_id, issuer_binding_receipt=issuer)


def test_installed_evidence_has_exact_digests_ordering_and_disarming():
    value = _installed()
    control, broker = _configs()
    policy = _policy()
    files = [
        {"path": "config/control.json", "sha256": hashlib.sha256(control).hexdigest()},
        {"path": "config/authority_map.yml", "sha256": hashlib.sha256(policy._raw).hexdigest()},
        {"path": "config/privileged-broker.json", "sha256": hashlib.sha256(broker).hexdigest()},
    ]
    expected_configuration = hashlib.sha256(canonical_release_bytes({
        "schema": "mastermind.executive_installed_configuration_set/v1",
        "files": files,
    })).hexdigest()
    assert value["installed_configuration_digest"] == expected_configuration
    assert value["control_config_digest"] == hashlib.sha256(control).hexdigest()
    assert value["broker_config_digest"] == hashlib.sha256(broker).hexdigest()
    assert value["provider_attestation_role"] == "codex_worker"
    assert value["issuer_binding_role"] == "control"
    assert value["production_disarming"] == {
        "schema": "mastermind.executive_release_disarming/v1",
        "commit_prepared_release_transition": False,
        "installer_arming": False,
        "worker_start": False,
    }


def test_v2_physical_evidence_compiles_exact_canonical_test_document():
    """Synthetic evidence only; this is test data, not installed state."""
    raw = _v2_installed_raw()
    value = json.loads(raw)
    physical = _physical_evidence()
    assert value["schema"] == (
        "mastermind.executive_release_owner_installed_evidence/v2"
    )
    assert set(value) == r._EVIDENCE_V2_FIELDS
    assert value["actuator_generation"] == 7
    physical["before"]["configuration_digest"] = value["before"]["configuration_digest"]
    assert value["before"] == physical["before"]
    assert value["publication_operation_key"] == physical["publication_operation_key"]
    assert value["predecessor_evidence_digest"] == (
        physical["predecessor_evidence_digest"]
    )
    assert raw == canonical_release_bytes(value) + b"\n"
    assert all(
        value["production_disarming"][name] is False
        for name in value["production_disarming"]
        if name != "schema"
    )


def test_v2_compile_preserves_supplied_generation_and_rejects_allocation_inputs():
    raw = _v2_installed_raw(actuator_generation=(1 << 63) - 1)
    assert json.loads(raw)["actuator_generation"] == (1 << 63) - 1
    import inspect
    assert inspect.signature(r.compile_installed_evidence).parameters[
        "physical_evidence"
    ].default is None


@pytest.mark.parametrize(
    "generation",
    [0, True, False, -1, 1 << 63, "7", 7.0],
)
def test_v2_generation_is_exact_bounded_integer(generation):
    with pytest.raises(
        r.ReleaseOwnerInputError, match="^EVIDENCE_ACTUATOR_GENERATION$"
    ):
        _v2_installed_raw(actuator_generation=generation)


@pytest.mark.parametrize(
    "change,code",
    [
        ({"extra_v2": 7}, "EVIDENCE_V2_ADDITIONS"),
        ({}, "EVIDENCE_V2_ADDITIONS"),
        ({"publication_operation_key": ""}, "EVIDENCE_OPERATION_KEY"),
        ({"publication_operation_key": True}, "EVIDENCE_OPERATION_KEY"),
        ({"predecessor_evidence_digest": "0" * 64}, "EVIDENCE_PREDECESSOR"),
        ({"predecessor_evidence_digest": "A" * 64}, "EVIDENCE_PREDECESSOR"),
    ],
)
def test_v2_refuses_extra_missing_and_invalid_physical_fields(change, code):
    def apply(document):
        if "extra_v2" in change:
            document["extra_v2"] = change["extra_v2"]
        elif change:
            document.update(change)
        if not change:
            document.pop("predecessor_evidence_digest")

    def changed(**arguments):
        physical = _physical_evidence()
        physical["before"]["configuration_digest"] = arguments.pop(
            "configuration_digest"
        )
        apply(physical)
        return r.compile_installed_evidence(
            registration=_registration(),
            release_commit=COMMIT,
            release_tree=TREE,
            control_config_bytes=control,
            broker_config_bytes=broker,
            authority_map_bytes=policy._raw,
            python_runtime_provenance_digest=PROVENANCE,
            provider_attestation_bytes=b'{"accepted":"fixture"}\n',
            provider_attestation_observed_at=OBSERVED,
            issuer_binding_receipt=_issuer(policy),
            issuer_binding_observed_at=OBSERVED,
            boot_id=BOOT,
            policy=policy,
            app_peer_uid=458,
            physical_evidence=physical,
            _now_seconds=NOW,
        )

    policy = _policy()
    control, broker = _configs()
    configuration_files = [
        {"path": "config/control.json", "sha256": hashlib.sha256(control).hexdigest()},
        {"path": "config/authority_map.yml", "sha256": hashlib.sha256(policy._raw).hexdigest()},
        {"path": "config/privileged-broker.json", "sha256": hashlib.sha256(broker).hexdigest()},
    ]
    aggregate = hashlib.sha256(canonical_release_bytes({
        "schema": "mastermind.executive_installed_configuration_set/v1",
        "files": configuration_files,
    })).hexdigest()
    with pytest.raises(r.ReleaseOwnerInputError, match=f"^{code}$"):
        changed(configuration_digest=aggregate)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("release_commit", "9" * 40, "EVIDENCE_BEFORE_RELEASE_MISMATCH"),
        ("release_tree", "9" * 40, "EVIDENCE_BEFORE_RELEASE_MISMATCH"),
        ("broker_source_commit", "9" * 40, "EVIDENCE_BEFORE_RELEASE_MISMATCH"),
        ("broker_source_tree", "9" * 40, "EVIDENCE_BEFORE_RELEASE_MISMATCH"),
        ("installed_manifest_digest", "0" * 64, "EVIDENCE_BEFORE_DIGEST"),
        ("broker_binary_digest", "0" * 64, "EVIDENCE_BEFORE_DIGEST"),
        ("configuration_digest", 7, "EVIDENCE_BEFORE_DIGEST"),
    ],
)
def test_v2_before_field_joins_and_digests_are_exact(field, value, code):
    before = _physical_evidence()["before"]
    aggregate = json.loads(_v2_installed_raw())["before"]["configuration_digest"]
    before["configuration_digest"] = aggregate
    before[field] = value
    with pytest.raises(r.ReleaseOwnerInputError, match=f"^{code}$"):
        _v2_installed_raw(before=before)


@pytest.mark.parametrize(
    "role",
    ["control", "worker", "relay", "gateway", "broker"],
)
def test_v2_rejects_each_nonzero_role_digest_substitute(role):
    before = _physical_evidence()["before"]
    before["service_generation_digests"][role] = "0" * 64
    with pytest.raises(r.ReleaseOwnerInputError, match="^EVIDENCE_SERVICE_DIGEST$"):
        _v2_installed_raw(before=before)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda before: before.update(
                configuration_digest="aaaaaaaa" + "e" * 56
            ),
            "EVIDENCE_CONFIG_JOIN",
        ),
        (lambda before: before.pop("gateway"), "EVIDENCE_SERVICE_FIELDS"),
        (lambda before: before.update(extra="x"), "EVIDENCE_BEFORE_FIELDS"),
    ],
)
def test_v2_rejects_wrong_configuration_and_closed_roles(mutate, code):
    before = json.loads(_v2_installed_raw())["before"]
    roles = before["service_generation_digests"]
    mutate(roles if code == "EVIDENCE_SERVICE_FIELDS" else before)
    with pytest.raises(r.ReleaseOwnerInputError, match=f"^{code}$"):
        _v2_installed_raw(before=before)


def test_v2_decoder_requires_canonical_bytes_and_returns_deep_detached_mapping():
    raw = _v2_installed_raw()
    decoded = r.decode_installed_evidence_v2(raw)
    decoded["before"]["service_generation_digests"]["worker"] = "changed"
    decoded["publication_operation_key"] = "changed"
    assert json.loads(raw)["publication_operation_key"] == (
        "release-resident-v2-test-001"
    )
    assert json.loads(raw)["before"]["service_generation_digests"]["worker"] == "2" * 64
    for noncanonical in (
        raw[:-1],
        canonical_release_bytes(json.loads(raw)),
        raw + b" ",
    ):
        with pytest.raises(r.ReleaseOwnerInputError):
            r.decode_installed_evidence_v2(noncanonical)


def test_v2_decoder_rejects_mixed_v1_and_inherited_shape_drift():
    v1 = _installed()
    with pytest.raises(r.ReleaseOwnerInputError, match="^EVIDENCE_V2_FIELDS$"):
        r.decode_installed_evidence_v2(canonical_release_bytes(v1) + b"\n")
    mixed = {**v1, **_physical_evidence()}
    with pytest.raises(r.ReleaseOwnerInputError, match="^EVIDENCE_V2_SCHEMA$"):
        r.decode_installed_evidence_v2(canonical_release_bytes(mixed) + b"\n")
    v2 = json.loads(_v2_installed_raw())
    v2["registration_generation"] = True
    with pytest.raises(
        r.ReleaseOwnerInputError, match="^EVIDENCE_REGISTRATION_GENERATION$"
    ):
        r.decode_installed_evidence_v2(canonical_release_bytes(v2) + b"\n")


@pytest.mark.parametrize("field", ["provider_attestation_bytes", "control_config_bytes", "broker_config_bytes", "authority_map_bytes"])
def test_installed_evidence_refuses_empty_raw_inputs(field):
    with pytest.raises(r.ReleaseOwnerInputError):
        _installed(**{field: b""})


def test_installed_evidence_refuses_registration_and_config_join_drift():
    registration = _registration()
    registration["enabled"] = True
    with pytest.raises(r.ReleaseOwnerInputError, match="^REGISTRATION_ARMED$"):
        _installed(registration=registration)
    control, _ = _configs()
    changed = json.loads(control)
    changed["proof_base_sha"] = "8" * 40
    with pytest.raises(r.ReleaseOwnerInputError, match="^CONTROL_CONFIG_MISMATCH$"):
        _installed(control_config_bytes=json.dumps(changed).encode())
    with pytest.raises(r.ReleaseOwnerInputError, match="^AUTHORITY_POLICY_MISMATCH$"):
        _installed(authority_map_bytes=_policy_source({**_policy_mapping(), "generation": 8}))


@pytest.mark.parametrize("uid", [None, 451, True, 450.0])
def test_installed_evidence_requires_exact_control_uid(uid):
    control, _ = _configs()
    changed = json.loads(control)
    if uid is None:
        changed.pop("control_uid")
    else:
        changed["control_uid"] = uid
    with pytest.raises(r.ReleaseOwnerInputError, match="^CONTROL_CONFIG_MISMATCH$"):
        _installed(control_config_bytes=json.dumps(changed).encode())


@pytest.mark.parametrize(
    "case",
    [
        "foreign_root",
        "relative_root",
        "missing_fields",
        "wrong_schema",
        "bad_receipt_root",
        "boolean_peer",
        "extra_field",
    ],
)
def test_installed_evidence_requires_complete_installed_broker_contract(case):
    _, broker = _configs()
    changed = json.loads(broker)
    if case == "foreign_root":
        changed["release_root"] = "/untrusted/releases/" + COMMIT
    elif case == "relative_root":
        changed["release_root"] = "relative/releases/" + COMMIT
    elif case == "missing_fields":
        changed = {"schema": changed["schema"], "release_root": changed["release_root"]}
    elif case == "wrong_schema":
        changed["schema"] = "other"
    elif case == "bad_receipt_root":
        changed["receipt_root"] = "/untrusted/receipts"
    elif case == "boolean_peer":
        changed["allowed_peer_uids"] = [450, True]
    else:
        changed["extra"] = 1
    with pytest.raises(r.ReleaseOwnerInputError, match="^BROKER_CONFIG_MISMATCH$"):
        _installed(broker_config_bytes=json.dumps(changed).encode())


@pytest.mark.parametrize("prefix", ["/synthetic-private-marker", "synthetic-private-marker"])
def test_broker_refusal_traceback_does_not_echo_rejected_path(prefix):
    _, broker = _configs()
    changed = json.loads(broker)
    changed["release_root"] = prefix + "/releases/" + COMMIT
    with pytest.raises(r.ReleaseOwnerInputError) as caught:
        _installed(broker_config_bytes=json.dumps(changed).encode())
    assert str(caught.value) == "BROKER_CONFIG_MISMATCH"
    assert prefix not in "".join(traceback.format_exception(caught.value))


def test_installed_evidence_refuses_issuer_and_timestamp_mismatch():
    with pytest.raises(r.ReleaseOwnerInputError, match="^ISSUER_TIME_MISMATCH$"):
        _installed(issuer_binding_observed_at="2026-09-29T12:00:01Z")
    with pytest.raises(r.ReleaseOwnerInputError, match="^PROVIDER_TIME$"):
        _installed(provider_attestation_observed_at="2999-01-01T00:00:00Z")
    with pytest.raises(r.ReleaseOwnerInputError, match="^ISSUER_BINDING_INVALID$"):
        _installed(issuer_binding_receipt=None)


def test_installed_evidence_hashes_complete_provider_and_issuer_file_bytes():
    value = _installed(provider_attestation_bytes=b"provider-receipt\n")
    assert value["provider_binary_attestation_digest"] == hashlib.sha256(b"provider-receipt\n").hexdigest()
    issuer_bytes = r.validate_issuer_binding_receipt(
        _issuer(),
        owner_installation_id=OWNER,
        target_ref=TARGET,
        release_commit=COMMIT,
        release_tree=TREE,
        boot_id=BOOT,
        policy=_policy(),
        app_peer_uid=458,
        _now_seconds=NOW,
    )
    assert value["issuer_binding_digest"] == hashlib.sha256(issuer_bytes).hexdigest()


def test_outputs_never_contain_raw_subject_client_or_secret_values():
    raw = r.compile_installed_evidence(**{
        **{
            "registration": _registration(),
            "release_commit": COMMIT,
            "release_tree": TREE,
            "control_config_bytes": _configs()[0],
            "broker_config_bytes": _configs()[1],
            "authority_map_bytes": _policy()._raw,
            "python_runtime_provenance_digest": PROVENANCE,
            "provider_attestation_bytes": b"secret-provider-receipt",
            "provider_attestation_observed_at": OBSERVED,
            "issuer_binding_receipt": _issuer(),
            "issuer_binding_observed_at": OBSERVED,
            "boot_id": BOOT,
            "policy": _policy(),
            "app_peer_uid": 458,
            "_now_seconds": NOW,
        }
    })
    for forbidden in (b"secret-provider-receipt", b"raw-subject", b"raw-client", b"access-token"):
        assert forbidden not in raw


def test_module_has_no_io_environment_network_or_random_surface():
    source = (Path(__file__).parents[1] / "ops/executive_os/release_owner_resident_inputs.py").read_text()
    tree = ast.parse(source)
    imports = {alias.name.split(".")[0] for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not imports & {"os", "pathlib", "socket", "secrets", "random", "subprocess", "urllib", "requests"}
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not called & {"open", "exec", "eval", "input"}


@pytest.mark.parametrize("value", [{"x": 1.5}, {"x": "line\nfeed"}, {"x": "é"}])
def test_canonical_file_bytes_refuses_float_control_and_nonascii_text(value):
    with pytest.raises(r.ReleaseOwnerInputError):
        r.canonical_file_bytes(value)


@pytest.mark.parametrize("field,replacement", [
    ("issuer_binding_owner_installation_id", "22222222-2222-4222-8222-222222222222"),
    ("issuer_binding_boot_id", "22222222-2222-4222-8222-222222222222"),
    ("issuer_binding_release_commit", "9" * 40),
    ("provider_attestation_observed_at", "2026-02-30T00:00:00Z"),
    ("issuer_binding_observed_at", "2026-09-30T00:00:00+00:00"),
])
def test_v2_decoder_rechecks_inherited_identity_and_timestamp(field, replacement):
    value = json.loads(_v2_installed_raw())
    value[field] = replacement
    with pytest.raises(r.ReleaseOwnerInputError):
        r.decode_installed_evidence_v2(canonical_release_bytes(value) + b"\n")


def test_v2_decoder_checks_configuration_join_without_compiler():
    value = json.loads(_v2_installed_raw())
    value["before"]["configuration_digest"] = "9" * 64
    with pytest.raises(r.ReleaseOwnerInputError, match="^EVIDENCE_CONFIG_JOIN$"):
        r.decode_installed_evidence_v2(canonical_release_bytes(value) + b"\n")
