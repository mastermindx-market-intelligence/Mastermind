"""P4 pure-contract vectors and adversarial schema/wire validation."""

import base64
import copy
import hashlib
import json
import pytest
from control_plane import executive_release_contract as c
from control_plane.ceo_request import app_request_ref


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def fixtures():
    h = lambda n: format(n, "064x")
    principal = dict(
        policy_id="test-policy",
        issuer_digest=h(1),
        resource_digest=h(2),
        subject_digest=h(3),
        client_ref=h(4),
        scopes=["mastermind.executive.intent.submit", "mastermind.executive.read"],
    )
    effect = dict(
        schema="mastermind.executive_release_effect/v1",
        repository="mastermindx-market-intelligence/Mastermind",
        protected_source_sha="1" * 40,
        source_policy_mode="exact_protected_master",
        installer_source_commit="1" * 40,
        installer_source_tree="2" * 40,
        installer_profile_digest=h(5),
        from_release_commit="3" * 40,
        from_release_tree="4" * 40,
        from_installed_manifest_digest=h(6),
        to_release_commit="1" * 40,
        to_release_tree="2" * 40,
        staged_artifact_digest=h(7),
        staged_content_metadata_digest=h(8),
        platform="darwin",
        architecture="arm64",
        configuration_transition_digest=h(9),
        compatibility_proof_digest=h(10),
        preservation_plan_digest=h(11),
        rollback_evidence=dict(kind="upgrade", rollback_readiness_digest=h(12)),
        action="executive.release.upgrade",
    )
    grant = dict(
        schema="mastermind.executive_release_grant/v1",
        principal_digest=digest(principal),
        authority_policy_hash=h(13),
        policy_id="test-policy",
        policy_generation=1,
        action=effect["action"],
        target_ref=h(14),
        transition_digest=digest(effect),
        installer_profile_digest=h(5),
        confirmation_requirement="delegated",
        confirmation_evidence_digest=h(15),
        granted_at_ms=1000,
        expires_at_ms=301000,
    )
    op = "p4-c1-a1-canary"
    approval = dict(
        schema="mastermind.executive_release_approval/v1",
        operation_key=op,
        request_ref=app_request_ref(op),
        approved_transition_ref="p4-approval:" + app_request_ref(op),
        action=effect["action"],
        owner_installation_id="11111111-1111-4111-8111-111111111111",
        target_ref=h(14),
        principal_projection=principal,
        normalized_requested_effect=effect,
        transition_digest=digest(effect),
        grant=grant,
        effective_grant_digest=digest(grant),
        created_at_ms=1000,
        expires_at_ms=301000,
        owner_seal=dict(
            key_id="key-v1",
            trust_generation=1,
            mac=base64.urlsafe_b64encode(bytes(32)).decode().rstrip("="),
        ),
    )
    policy = dict(
        schema="mastermind.executive_release_controller_policy/v1",
        policy_id="test-policy",
        generation=1,
        enabled=False,
        issuer_digest=h(1),
        resource_digest=h(2),
        subject_digests=[h(3)],
        client_refs=[h(4)],
        required_scopes=principal["scopes"],
        actions=[effect["action"]],
        target_refs=[h(14)],
        installer_profile_digests=[h(5)],
        source_policy_modes=["exact_protected_master"],
        max_approval_lifetime_seconds=300,
        confirmation_requirement="delegated",
    )
    return principal, effect, grant, approval, policy


def test_independent_operation_vector():
    assert (
        c.approval_ref_for("p4-c1-a1-canary")
        == "p4-approval:req-3157657ad525db975a658632b11fbbd7"
    )


def test_exact_payload_canonicalization_and_fingerprint():
    principal, effect, grant, approval, policy = fixtures()
    validated = c.validate_approval_evidence(copy.deepcopy(approval))
    expected = dict(
        operation_key=approval["operation_key"],
        approved_transition_ref=approval["approved_transition_ref"],
        approval_evidence_digest=digest(approval),
        authenticated_principal_digest=digest(principal),
        target_ref=approval["target_ref"],
        action_family=approval["action"],
        normalized_requested_effect_digest=digest(effect),
    )
    fp = hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_REQUEST_V1\0" + canonical(expected)
    ).hexdigest()
    assert c.request_fingerprint_for(validated) == fp
    assert c.broker_request_id_for(fp) == "p4r-" + fp[:48]
    assert c.canonical_release_bytes(validated) == canonical(approval)


def test_original_does_not_change_when_caller_mutates_input():
    _, _, _, approval, _ = fixtures()
    validated = c.validate_approval_evidence(approval)
    before = c.canonical_release_bytes(validated)
    approval["expires_at_ms"] += 1
    approval["principal_projection"]["scopes"].append("extra")
    approval["normalized_requested_effect"]["rollback_evidence"][
        "rollback_readiness_digest"
    ] = ("f" * 64)
    assert c.canonical_release_bytes(validated) == before


@pytest.mark.parametrize(
    "field",
    [
        "issuer_digest",
        "resource_digest",
        "subject_digests",
        "client_refs",
        "required_scopes",
        "actions",
        "target_refs",
        "installer_profile_digests",
        "source_policy_modes",
    ],
)
def test_present_disabled_policy_stays_strict(field):
    *_, policy = fixtures()
    del policy[field]
    with pytest.raises((ValueError, TypeError)):
        c.validate_release_policy(policy)


def test_none_policy_is_not_a_valid_grant():
    with pytest.raises((ValueError, TypeError)):
        c.validate_release_policy(None)


@pytest.mark.parametrize(
    "case",
    [
        "operation_ref",
        "effect_digest",
        "principal_digest",
        "grant_digest",
        "target",
        "action",
        "expiry",
    ],
)
def test_approval_cross_field_conflicts(case):
    _, _, _, a, _ = fixtures()
    if case == "operation_ref":
        a["approved_transition_ref"] = "p4-approval:req-" + "0" * 32
    if case == "effect_digest":
        a["normalized_requested_effect"]["to_release_commit"] = "f" * 40
    if case == "principal_digest":
        a["principal_projection"]["subject_digest"] = "e" * 64
    if case == "grant_digest":
        a["effective_grant_digest"] = "a" * 64
    if case == "target":
        a["target_ref"] = "b" * 64
    if case == "action":
        a["action"] = "executive.release.rollback"
    if case == "expiry":
        a["expires_at_ms"] = a["grant"]["expires_at_ms"] + 1
    with pytest.raises((ValueError, TypeError)):
        c.validate_approval_evidence(a)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":1}',
        b'{"x":1.0}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{ "x":1}',
        b'{"x":1}\n',
        b"[]",
        b'{"x":' + b"[" * 9 + b"0" + b"]" * 9 + b"}",
        b'{"x":"' + b"x" * 16384 + b'"}',
    ],
)
def test_wire_rejects_invalid_or_noncanonical(raw):
    with pytest.raises((ValueError, TypeError)):
        c.parse_release_json(raw)


def test_no_live_proof_claim_for_structural_seal():
    # All-zero MAC is intentionally syntactically valid. This validator must
    # neither need a key nor claim it has authenticated the evidence.
    _, _, _, approval, _ = fixtures()
    v = c.validate_approval_evidence(approval)
    assert c.canonical_release_bytes(v) == canonical(approval)


@pytest.mark.parametrize(
    "extra", ["principal", "approved", "shell", "authorization", "__proto__"]
)
def test_unexpected_top_level_fields(extra):
    _, effect, _, _, _ = fixtures()
    effect[extra] = True
    with pytest.raises((ValueError, TypeError)):
        c.validate_normalized_effect(effect)


def admission_fixture():
    _, _, _, approval, _ = fixtures()
    return dict(
        schema="mastermind.executive_release_admission/v1",
        operation_key=approval["operation_key"],
        approved_transition_ref=approval["approved_transition_ref"],
        target_ref=approval["target_ref"],
        owner_installation_id=approval["owner_installation_id"],
        boot_id="22222222-2222-4222-8222-222222222222",
        request_fingerprint="1" * 64,
        effective_grant_digest=approval["effective_grant_digest"],
        maintenance_sequence=1,
        admission_event_command_id="p4-admit:" + approval["request_ref"],
        target_observation_digest="2" * 64,
        admission_contract_digest="3" * 64,
    )


def test_complete_admission_schema_roundtrip():
    value = admission_fixture()
    assert c.canonical_release_bytes(c.validate_admission(value)) == canonical(value)


@pytest.mark.parametrize("field", list(admission_fixture()))
def test_admission_requires_each_field(field):
    value = admission_fixture()
    del value[field]
    with pytest.raises((ValueError, TypeError)):
        c.validate_admission(value)


@pytest.mark.parametrize("value", [True, 0, -1, 1.0, 2**63, "1", None])
def test_admission_sequence_is_bounded_integer(value):
    record = admission_fixture()
    record["maintenance_sequence"] = value
    with pytest.raises((ValueError, TypeError)):
        c.validate_admission(record)


@pytest.mark.parametrize(
    "key", ["approved_transition_ref", "admission_event_command_id"]
)
def test_admission_refs_join_the_same_operation(key):
    value = admission_fixture()
    value[key] += "a"
    with pytest.raises((ValueError, TypeError)):
        c.validate_admission(value)


def test_a1_has_no_direct_effect_imports_or_entry_points():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(c.__file__).read_text())
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not imports.intersection(
        {
            "sqlite3",
            "subprocess",
            "socket",
            "requests",
            "httpx",
            "hmac",
            "os",
            "time",
            "datetime",
        }
    )
    assert not {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }.intersection({"approve", "prepare", "commit", "sign"})


def precondition_fixture():
    _, effect, grant, approval, _ = fixtures()
    result = {
        key: "a" * 64
        for key in (
            "from_installed_manifest_digest installed_configuration_digest "
            "python_runtime_provenance_digest provider_binary_attestation_digest "
            "authority_policy_hash grant_digest approval_evidence_digest staged_artifact_digest "
            "staged_content_metadata_digest compatibility_proof_digest preservation_plan_digest "
            "issuer_binding_digest admission_contract_digest production_arming_digest"
        ).split()
    }
    result.update(
        schema="mastermind.executive_release_preconditions/v1",
        owner_installation_id=approval["owner_installation_id"],
        target_ref=approval["target_ref"],
        boot_id="22222222-2222-4222-8222-222222222222",
    )
    return result


def prepared_fixture():
    principal, effect, grant, approval, _ = fixtures()
    fields = {
        key: "b" * 64
        for key in (
            "schema_digest action_target_digest expected_source_and_precondition_digest "
            "admission_contract_digest"
        ).split()
    }
    fields.update(
        token_schema="mastermind.executive_release_prepared.v1",
        app_id="mastermind.executive",
        owner_installation_id=approval["owner_installation_id"],
        app_generation=1,
        trust_generation=1,
        key_id="key-v1",
        authenticated_principal_digest=digest(principal),
        approved_transition_ref=approval["approved_transition_ref"],
        approval_evidence_digest=digest(approval),
        policy_id="test-policy",
        policy_generation=1,
        authority_policy_hash=grant["authority_policy_hash"],
        effective_grant_digest=digest(grant),
        confirmation_requirement="delegated",
        privilege_class="EXECUTIVE_RELEASE_TRANSITION",
        operation_key=approval["operation_key"],
        action_family=effect["action"],
        target_ref=approval["target_ref"],
        boot_id="22222222-2222-4222-8222-222222222222",
        platform="darwin",
        normalized_requested_effect=effect,
        normalized_requested_effect_digest=digest(effect),
        issued_at_ms=1000,
        expires_at_ms=301000,
        issued_monotonic_ns=1000000000,
        expires_monotonic_ns=301000000000,
    )
    identity = {
        key: fields[key]
        for key in (
            "operation_key",
            "approved_transition_ref",
            "approval_evidence_digest",
            "authenticated_principal_digest",
            "target_ref",
            "action_family",
            "normalized_requested_effect_digest",
        )
    }
    fields["request_fingerprint"] = hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_REQUEST_V1\0" + canonical(identity)
    ).hexdigest()
    return fields


@pytest.mark.parametrize(
    "validator,fixture",
    [
        (c.validate_precondition_manifest, precondition_fixture),
        (c.validate_prepared_payload, prepared_fixture),
    ],
)
def test_other_payloads_have_canonical_positive_vectors(validator, fixture):
    value = fixture()
    assert c.canonical_release_bytes(validator(value)) == canonical(value)


@pytest.mark.parametrize("field", list(prepared_fixture()))
def test_prepared_requires_every_field(field):
    record = prepared_fixture()
    del record[field]
    with pytest.raises((ValueError, TypeError)):
        c.validate_prepared_payload(record)


@pytest.mark.parametrize("field", list(precondition_fixture()))
def test_preconditions_require_every_field(field):
    record = precondition_fixture()
    del record[field]
    with pytest.raises((ValueError, TypeError)):
        c.validate_precondition_manifest(record)


@pytest.mark.parametrize(
    "field",
    [
        "request_fingerprint",
        "normalized_requested_effect_digest",
        "approved_transition_ref",
    ],
)
def test_prepared_internal_join_corruption(field):
    value = prepared_fixture()
    value[field] = "0" * 64
    with pytest.raises((ValueError, TypeError)):
        c.validate_prepared_payload(value)


def test_prepared_refresh_preserves_effect_identity():
    original = prepared_fixture()
    refreshed = copy.deepcopy(original)
    for field in ["issued_at_ms", "expires_at_ms"]:
        refreshed[field] += 1
    for field in ["issued_monotonic_ns", "expires_monotonic_ns"]:
        refreshed[field] += 1000000
    assert c.canonical_release_bytes(
        c.validate_prepared_payload(original)
    ) != c.canonical_release_bytes(c.validate_prepared_payload(refreshed))
    assert original["request_fingerprint"] == refreshed["request_fingerprint"]


@pytest.mark.parametrize(
    "field",
    [
        "issued_at_ms",
        "expires_at_ms",
        "issued_monotonic_ns",
        "expires_monotonic_ns",
        "app_generation",
        "trust_generation",
        "policy_generation",
    ],
)
def test_prepared_refuses_boolean_numbers(field):
    value = prepared_fixture()
    value[field] = True
    with pytest.raises((ValueError, TypeError)):
        c.validate_prepared_payload(value)


def rollback_approval():
    _, effect, grant, approval, _ = fixtures()
    effect.update(
        action="executive.release.rollback",
        source_policy_mode="frozen_accepted_ancestor",
        to_release_commit="5" * 40,
        to_release_tree="6" * 40,
        rollback_evidence={
            "kind": "rollback",
            "original_upgrade_request_id": "p4r-" + "7" * 48,
            "original_terminal_or_reconciliation_digest": "8" * 64,
            "retained_artifact_digest": "9" * 64,
            "preimage_digest": "a" * 64,
            "current_compatibility_digest": "b" * 64,
        },
    )
    grant.update(action=effect["action"], transition_digest=digest(effect))
    approval.update(
        action=effect["action"],
        transition_digest=digest(effect),
        effective_grant_digest=digest(grant),
    )
    return approval


def test_independent_rollback_vector():
    value = rollback_approval()
    result = c.validate_approval_evidence(value)
    assert c.canonical_release_bytes(result) == canonical(value)
    identity = dict(
        operation_key=value["operation_key"],
        approved_transition_ref=value["approved_transition_ref"],
        approval_evidence_digest=digest(value),
        authenticated_principal_digest=digest(value["principal_projection"]),
        target_ref=value["target_ref"],
        action_family=value["action"],
        normalized_requested_effect_digest=digest(value["normalized_requested_effect"]),
    )
    expected = hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_REQUEST_V1\0" + canonical(identity)
    ).hexdigest()
    assert c.request_fingerprint_for(result) == expected
    assert expected != c.request_fingerprint_for(
        c.validate_approval_evidence(fixtures()[3])
    )


RECORDS = [
    (c.validate_principal_projection, fixtures()[0]),
    (c.validate_normalized_effect, fixtures()[1]),
    (c.validate_release_grant, fixtures()[2]),
    (c.validate_approval_evidence, fixtures()[3]),
    (c.validate_release_policy, fixtures()[4]),
    (c.validate_precondition_manifest, precondition_fixture()),
    (c.validate_admission, admission_fixture()),
    (c.validate_prepared_payload, prepared_fixture()),
    (c.validate_approval_evidence, rollback_approval()),
]


@pytest.mark.parametrize(
    "validator,record,field",
    [(validator, record, field) for validator, record in RECORDS for field in record],
)
def test_closed_records_require_every_field_and_disallow_null(validator, record, field):
    value = copy.deepcopy(record)
    del value[field]
    with pytest.raises(ValueError):
        validator(value)
    value[field] = None
    with pytest.raises(ValueError):
        validator(value)


@pytest.mark.parametrize("validator,record", RECORDS)
def test_closed_records_refuse_extras_and_wrong_object_type(validator, record):
    value = copy.deepcopy(record)
    value["untrusted_approval"] = True
    for bad in (value, None, [], "{}", 1, True):
        with pytest.raises(ValueError):
            validator(bad)


@pytest.mark.parametrize("validator,record", RECORDS)
def test_each_record_is_immutable_and_roundtrips(validator, record):
    result = validator(record)
    encoded = c.canonical_release_bytes(result)
    assert encoded == canonical(record)
    assert (
        c.canonical_release_bytes(validator(c.parse_release_json(encoded))) == encoded
    )
    with pytest.raises(TypeError):
        result[next(iter(result))] = "changed"
    projected = result.to_dict()
    projected.clear()
    assert c.canonical_release_bytes(result) == encoded
    # Wire form, rather than the type of a constructed Python object, is the
    # schema/identity boundary. Revalidation always checks its actual contents.
    assert dict(result) == dict(validator(result))


@pytest.mark.parametrize(
    "path",
    [
        ("owner_seal",),
        ("principal_projection",),
        ("grant",),
        ("normalized_requested_effect",),
        ("normalized_requested_effect", "rollback_evidence"),
    ],
)
def test_unknown_nested_approval_field_refused(path):
    value = fixtures()[3]
    child = value
    for name in path:
        child = child[name]
    child["forged_field"] = "secret-must-not-appear"
    with pytest.raises(ValueError) as error:
        c.validate_approval_evidence(value)
    assert "secret-must-not-appear" not in str(error.value)


@pytest.mark.parametrize(
    "field",
    [
        "subject_digests",
        "client_refs",
        "required_scopes",
        "actions",
        "target_refs",
        "installer_profile_digests",
        "source_policy_modes",
    ],
)
@pytest.mark.parametrize("case", ["empty", "duplicate", "wrong_type", "wildcard"])
def test_policy_collection_constraints(field, case):
    value = fixtures()[4]
    original = value[field]
    value[field] = {
        "empty": [],
        "duplicate": original * 2,
        "wrong_type": original[0],
        "wildcard": ["*"],
    }[case]
    with pytest.raises(ValueError):
        c.validate_release_policy(value)


def test_policy_and_scope_upper_boundaries():
    value = fixtures()[4]
    value["subject_digests"] = [format(i, "064x") for i in range(32)]
    c.validate_release_policy(value)
    value["subject_digests"].append(format(32, "064x"))
    with pytest.raises(ValueError):
        c.validate_release_policy(value)
    principal = fixtures()[0]
    principal["scopes"] = [f"scope-{i:02}" for i in range(16)]
    c.validate_principal_projection(principal)
    principal["scopes"].append("scope-16")
    with pytest.raises(ValueError):
        c.validate_principal_projection(principal)


def test_sorted_scope_and_client_requirements():
    principal = fixtures()[0]
    principal["scopes"].reverse()
    with pytest.raises(ValueError):
        c.validate_principal_projection(principal)
    policy = fixtures()[4]
    policy["required_scopes"] = ["mastermind.executive.read"]
    with pytest.raises(ValueError):
        c.validate_release_policy(policy)
    policy = fixtures()[4]
    policy["client_refs"] = ["oauth-client-unavailable"]
    with pytest.raises(ValueError):
        c.validate_release_policy(policy)


@pytest.mark.parametrize("bad", [0, 301, -1, True, 1.0, "300"])
def test_policy_max_lifetime(bad):
    policy = fixtures()[4]
    policy["max_approval_lifetime_seconds"] = bad
    with pytest.raises(ValueError):
        c.validate_release_policy(policy)


@pytest.mark.parametrize("bad", [0, 1000, 301001, True, 1.0, 2**63])
def test_grant_expiry_order_and_bound(bad):
    grant = fixtures()[2]
    grant["expires_at_ms"] = bad
    with pytest.raises(ValueError):
        c.validate_release_grant(grant)


@pytest.mark.parametrize("bad", ["", "*", "foo/bar", "é", "x" * 161, "abc\n"])
def test_closed_identifier_vocabulary(bad):
    principal = fixtures()[0]
    principal["policy_id"] = bad
    with pytest.raises(ValueError):
        c.validate_principal_projection(principal)


@pytest.mark.parametrize("bad", ["0" * 63, "A" * 64, "0" * 65, "0" * 64 + "\n", True])
def test_digest_representation_is_exact(bad):
    principal = fixtures()[0]
    principal["subject_digest"] = bad
    with pytest.raises(ValueError):
        c.validate_principal_projection(principal)


@pytest.mark.parametrize(
    "bad",
    [
        "00000000-0000-0000-0000-000000000000",
        "11111111111141118111111111111111",
        "{11111111-1111-4111-8111-111111111111}",
        "aaaaaaaa-AAAA-4aaa-8aaa-aaaaaaaaaaaa",
    ],
)
def test_only_canonical_non_nil_uuid(bad):
    value = admission_fixture()
    value["boot_id"] = bad
    with pytest.raises(ValueError):
        c.validate_admission(value)


@pytest.mark.parametrize(
    "bad",
    [
        "A" * 43 + "=",
        "A" * 42,
        "A" * 42 + "B",
        "+" * 43,
        "/" * 43,
    ],
)
def test_seal_requires_canonical_base64url_exact_32_bytes(bad):
    value = fixtures()[3]
    value["owner_seal"]["mac"] = bad
    with pytest.raises(ValueError):
        c.validate_approval_evidence(value)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":{"b":1,"b":2}}',
        b'{"x":1,"\\u0078":2}',
        b'{"x":-1}',
        b'{"x":9223372036854775808}',
        b'{"x":-0}',
        b'{"x":1e0}',
        b'{"x":null}',
        b'{"x":"\\ud800"}',
        b'{"x":"\xff"}',
        b"{} ",
    ],
)
def test_more_wire_ambiguities_are_rejected(raw):
    with pytest.raises(ValueError):
        c.parse_release_json(raw)


def test_unicode_key_and_huge_integer_have_payload_free_errors():
    for raw in [b'{"secret-key-\\ud800":1}', b'{"x":' + b"1" * 5000 + b"}"]:
        with pytest.raises(c.ReleaseContractError) as caught:
            c.parse_release_json(raw)
        assert caught.value.field == "payload"
        assert "secret-key" not in str(caught.value)
    with pytest.raises(c.ReleaseContractError):
        c.canonical_release_bytes({"secret-key-\ud800": 1})


def test_wire_depth_and_byte_boundaries():
    value = {"x": 1}
    for _ in range(7):
        value = {"x": value}
    raw = canonical(value)
    assert c.canonical_release_bytes(c.parse_release_json(raw)) == raw
    with pytest.raises(ValueError):
        c.parse_release_json(canonical({"x": value}))
    raw = b'{"x":"' + b"x" * (16384 - 8) + b'"}'
    assert len(raw) == 16384
    assert c.canonical_release_bytes(c.parse_release_json(raw)) == raw
    with pytest.raises(ValueError):
        c.parse_release_json(raw[:-2] + b'x"}')
    text = {"x": 'literal braces {} [] and escaped " quote \\'}
    assert c.canonical_release_bytes(
        c.parse_release_json(canonical(text))
    ) == canonical(text)


def test_approval_nested_objects_cannot_be_mutated():
    record = c.validate_approval_evidence(fixtures()[3])
    with pytest.raises(TypeError):
        record["principal_projection"]["scopes"][0] = "changed"
    with pytest.raises(TypeError):
        record["owner_seal"]["mac"] = "changed"


@pytest.mark.parametrize("key", ["policy_id", "target_ref", "installer_profile_digest"])
def test_rehashed_grant_still_must_match_approval(key):
    value = fixtures()[3]
    value["grant"][key] = "other-policy" if key == "policy_id" else "c" * 64
    value["effective_grant_digest"] = digest(value["grant"])
    with pytest.raises(ValueError):
        c.validate_approval_evidence(value)


def test_hash_does_not_hide_changed_operation_or_subject():
    value = fixtures()[3]
    before = c.request_fingerprint_for(value)
    value["principal_projection"]["subject_digest"] = "c" * 64
    value["grant"]["principal_digest"] = digest(value["principal_projection"])
    value["effective_grant_digest"] = digest(value["grant"])
    assert c.request_fingerprint_for(value) != before
    value["operation_key"] = "different-operation"
    value["request_ref"] = app_request_ref(value["operation_key"])
    value["approved_transition_ref"] = "p4-approval:" + value["request_ref"]
    assert c.request_fingerprint_for(value) != before


def test_short_request_id_collision_keeps_distinct_full_fingerprints():
    first, second = "1" * 48 + "2" * 16, "1" * 48 + "3" * 16
    assert first != second
    assert c.broker_request_id_for(first) == c.broker_request_id_for(second)
    # The consumer must compare full fingerprints; the pure ID helper neither
    # claims uniqueness of a truncated digest nor creates a reservation store.


def test_operation_ref_collision_does_not_collapse_full_effect_identity(monkeypatch):
    first = fixtures()[3]
    second = copy.deepcopy(first)
    second["operation_key"] = "different-normalized-operation"
    monkeypatch.setattr(c, "app_request_ref", lambda _: first["request_ref"])
    assert c.approval_ref_for(first["operation_key"]) == c.approval_ref_for(
        second["operation_key"]
    )
    assert c.request_fingerprint_for(first) != c.request_fingerprint_for(second)
    # Runtime must refuse an existing shortened Event ref with a different full
    # operation/effect. A pure record validator cannot adjudicate stored replay.


@pytest.mark.parametrize(
    "bad", ["aa", "Uppercase-operation", "space op", "a" * 97, True]
)
def test_existing_operation_key_law_is_not_broadened(bad):
    with pytest.raises(ValueError):
        c.approval_ref_for(bad)


def test_source_modes_match_pinned_owner_contract():
    import ast
    from pathlib import Path

    owner = Path(c.__file__).parents[1] / "ops/executive_os/install_source_policy.py"
    tree = ast.parse(owner.read_text())
    modes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "mode"
                    and isinstance(value, ast.Constant)
                ):
                    modes.add(value.value)
    assert modes == {"exact_protected_master", "frozen_accepted_ancestor"}
    assert set(c._SOURCE_MODES) == modes


# Parent terminal-status acceptance vectors; independent of worker implementation.
TERMINAL_TEST_STATES = (
    "NOT_FOUND",
    "STARTED",
    "PUBLISHED",
    "BROKER_RESTART_PENDING",
    "RECOVERING",
    "SUCCEEDED",
    "ROLLED_BACK",
    "FAILED_NOT_APPLIED",
)
TERMINAL_TEST_OUTCOMES = TERMINAL_TEST_STATES[5:]


def terminal_fixture(state="SUCCEEDED", rollback_action=False):
    p, e, g, a, _ = fixtures()
    if rollback_action:
        a = rollback_approval()
        p = a["principal_projection"]
        e = a["normalized_requested_effect"]
        g = a["grant"]
    f = {
        "operation_key": a["operation_key"],
        "approved_transition_ref": a["approved_transition_ref"],
        "approval_evidence_digest": digest(a),
        "authenticated_principal_digest": digest(p),
        "target_ref": a["target_ref"],
        "action_family": a["action"],
        "normalized_requested_effect_digest": digest(e),
    }
    fp = hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_REQUEST_V1\x00"
        + json.dumps(f, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    s = dict(
        schema="mastermind.executive_release_terminal_status/v1",
        state=state,
        request_id="p4r-" + fp[:48],
        request_fingerprint=fp,
        **f,
        effective_grant_digest=digest(g),
        owner_installation_id=a["owner_installation_id"],
        action_target_digest=digest(
            {"action": a["action"], "target_ref": a["target_ref"]}
        ),
        from_release_commit=e["from_release_commit"],
        to_release_commit=e["to_release_commit"]
    )
    if state == "NOT_FOUND":
        return (a, s)
    pre = dict(
        schema="mastermind.executive_release_preconditions/v1",
        owner_installation_id=a["owner_installation_id"],
        target_ref=a["target_ref"],
        boot_id="22222222-2222-4222-8222-222222222222",
        authority_policy_hash=g["authority_policy_hash"],
        grant_digest=digest(g),
        approval_evidence_digest=digest(a),
    )
    for k in (
        "from_installed_manifest_digest",
        "staged_artifact_digest",
        "staged_content_metadata_digest",
        "compatibility_proof_digest",
        "preservation_plan_digest",
    ):
        pre[k] = e[k]
    for i, k in enumerate(
        (
            "installed_configuration_digest",
            "python_runtime_provenance_digest",
            "provider_binary_attestation_digest",
            "issuer_binding_digest",
            "admission_contract_digest",
            "production_arming_digest",
        ),
        30,
    ):
        pre[k] = format(i, "064x")
    admission = dict(
        schema="mastermind.executive_release_admission/v1",
        operation_key=a["operation_key"],
        approved_transition_ref=a["approved_transition_ref"],
        target_ref=a["target_ref"],
        owner_installation_id=a["owner_installation_id"],
        boot_id=pre["boot_id"],
        request_fingerprint=fp,
        effective_grant_digest=digest(g),
        maintenance_sequence=1,
        admission_event_command_id="p4-admit:" + a["request_ref"],
        target_observation_digest="a" * 64,
        admission_contract_digest=pre["admission_contract_digest"],
    )
    s.update(
        actuator_generation=1,
        journal_generation=1,
        started_at_ms=2000,
        preconditions=pre,
        expected_precondition_digest=digest(pre),
        admission=admission,
        admission_digest=digest(admission),
    )
    if state not in TERMINAL_TEST_OUTCOMES:
        return (a, s)
    before = dict(
        release_commit=e["from_release_commit"],
        release_tree=e["from_release_tree"],
        installed_manifest_digest=e["from_installed_manifest_digest"],
        configuration_digest=pre["installed_configuration_digest"],
        broker_source_commit=e["from_release_commit"],
        broker_source_tree=e["from_release_tree"],
        broker_binary_digest="b" * 64,
        service_generation_digests={
            k: format(i, "064x")
            for i, k in enumerate(
                ("control", "worker", "relay", "gateway", "broker"), 100
            )
        },
    )
    after = copy.deepcopy(before)
    if state == "SUCCEEDED":
        after.update(
            release_commit=e["to_release_commit"],
            release_tree=e["to_release_tree"],
            broker_source_commit=e["to_release_commit"],
            broker_source_tree=e["to_release_tree"],
            installed_manifest_digest="c" * 64,
        )
    rollback = (
        {"attempted": True, "restored_preimage_digest": digest(before)}
        if state == "ROLLED_BACK"
        else {"attempted": False}
    )
    r = {
        k: s[k]
        for k in (
            "request_id",
            "request_fingerprint",
            "approval_evidence_digest",
            "expected_precondition_digest",
            "admission_digest",
            "actuator_generation",
            "journal_generation",
            "started_at_ms",
        )
    }
    r.update(
        schema="mastermind.executive_release_terminal_receipt/v1",
        completed_at_ms=400000,
        outcome=state,
        before=before,
        after=after,
        rollback=rollback,
        postcondition_digest="d" * 64,
    )
    s["terminal_receipt"] = r
    return (a, s)


@pytest.mark.parametrize("state", TERMINAL_TEST_STATES)
def test_terminal_all_state_vectors_and_detachment(state):
    a, s = terminal_fixture(state)
    original = copy.deepcopy(s)
    out = c.validate_release_terminal_status(s, expected_approval=a)
    assert out.to_dict() == original
    s["request_id"] = "bad"
    a["operation_key"] = "bad"
    assert out.to_dict() == original
    assert len(c.canonical_release_bytes(out)) <= 16384


@pytest.mark.parametrize("state", TERMINAL_TEST_OUTCOMES)
def test_terminal_public_receipt_and_completion_after_expiry(state):
    a, s = terminal_fixture(state)
    out = c.validate_release_terminal_receipt(
        s["terminal_receipt"], expected_status=s, expected_approval=a
    )
    assert out.to_dict() == s["terminal_receipt"]
    s["terminal_receipt"]["postcondition_digest"] = "e" * 64
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_receipt(out, expected_status=s, expected_approval=a)


TERMINAL_TEST_COMMON = tuple(terminal_fixture("NOT_FOUND")[1])


@pytest.mark.parametrize("field", TERMINAL_TEST_COMMON)
def test_terminal_every_common_join_and_exact_set(field):
    a, s = terminal_fixture("NOT_FOUND")
    for val in (
        None,
        True,
        {},
        "invalid",
        s[field].upper() if isinstance(s[field], str) else "other",
    ):
        if val == s[field]:
            continue
        bad = copy.deepcopy(s)
        bad[field] = val
        with pytest.raises(c.ReleaseContractError):
            c.validate_release_terminal_status(bad, expected_approval=a)
    del s[field]
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


@pytest.mark.parametrize("state", TERMINAL_TEST_STATES)
def test_terminal_receipt_presence_and_unknown_field(state):
    a, s = terminal_fixture(state)
    s["unexpected"] = "value"
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)
    del s["unexpected"]
    if state in TERMINAL_TEST_OUTCOMES:
        del s["terminal_receipt"]
    else:
        s["terminal_receipt"] = terminal_fixture()[1]["terminal_receipt"]
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


@pytest.mark.parametrize(
    "field", ("actuator_generation", "journal_generation", "started_at_ms")
)
@pytest.mark.parametrize("value", (None, False, True, -1, 0, 2**63, 1.0, "1"))
def test_terminal_integer_grammar_and_start_bounds(field, value):
    a, s = terminal_fixture("STARTED")
    s[field] = value
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


@pytest.mark.parametrize(
    "field",
    (
        "owner_installation_id",
        "target_ref",
        "approval_evidence_digest",
        "grant_digest",
        "authority_policy_hash",
        "from_installed_manifest_digest",
        "staged_artifact_digest",
        "staged_content_metadata_digest",
        "compatibility_proof_digest",
        "preservation_plan_digest",
    ),
)
def test_terminal_precondition_correlations_even_when_digest_recomputed(field):
    a, s = terminal_fixture("STARTED")
    s["preconditions"][field] = (
        "33333333-3333-4333-8333-333333333333"
        if field == "owner_installation_id"
        else "e" * 64
    )
    s["expected_precondition_digest"] = digest(s["preconditions"])
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


@pytest.mark.parametrize(
    "field",
    (
        "request_fingerprint",
        "effective_grant_digest",
        "boot_id",
        "admission_contract_digest",
        "target_ref",
        "owner_installation_id",
        "maintenance_sequence",
        "admission_event_command_id",
    ),
)
def test_terminal_admission_correlations_even_when_digest_recomputed(field):
    a, s = terminal_fixture("STARTED")
    s["admission"][field] = (
        0
        if field == "maintenance_sequence"
        else (
            "33333333-3333-4333-8333-333333333333"
            if field in ("boot_id", "owner_installation_id")
            else "e" * 64
        )
    )
    s["admission_digest"] = digest(s["admission"])
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


@pytest.mark.parametrize("state", TERMINAL_TEST_OUTCOMES)
@pytest.mark.parametrize("side", ("before", "after"))
@pytest.mark.parametrize("role", ("control", "worker", "relay", "gateway", "broker"))
def test_terminal_exact_service_role_map(state, side, role):
    a, s = terminal_fixture(state)
    del s["terminal_receipt"][side]["service_generation_digests"][role]
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


@pytest.mark.parametrize("state", ("ROLLED_BACK", "FAILED_NOT_APPLIED"))
def test_terminal_no_partial_mutation_can_equal_preimage(state):
    a, s = terminal_fixture(state)
    s["terminal_receipt"]["after"]["service_generation_digests"]["relay"] = "e" * 64
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


def test_terminal_shortened_id_collision_rejected():
    a, s = terminal_fixture("STARTED")
    fp = s["request_fingerprint"]
    s["request_fingerprint"] = fp[:48] + ("f" * 16 if fp[48:] != "f" * 16 else "e" * 16)
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=a)


def test_terminal_forged_approval_and_status_records_revalidated():
    a, s = terminal_fixture()
    a["owner_seal"]["mac"] = "bad"
    forged = c.ReleaseRecord(tuple(a.items()))
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(s, expected_approval=forged)
    a, s = terminal_fixture()
    s["request_fingerprint"] = "e" * 64
    forged = c.ReleaseRecord(tuple(s.items()))
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_receipt(
            s["terminal_receipt"], expected_status=forged, expected_approval=a
        )


@pytest.mark.parametrize("state", TERMINAL_TEST_STATES)
def test_terminal_original_rollback_action_all_outcomes(state):
    a, s = terminal_fixture(state, rollback_action=True)
    out = c.validate_release_terminal_status(s, expected_approval=a)
    assert out["action_family"] == "executive.release.rollback"
    if state in TERMINAL_TEST_OUTCOMES:
        assert (
            c.validate_release_terminal_receipt(
                s["terminal_receipt"], expected_status=s, expected_approval=a
            ).to_dict()
            == s["terminal_receipt"]
        )


@pytest.mark.parametrize(
    "timestamp,valid", [(999, False), (1000, True), (300999, True), (301000, False)]
)
def test_terminal_start_exact_lifetime_boundaries(timestamp, valid):
    a, s = terminal_fixture("STARTED")
    s["started_at_ms"] = timestamp
    if valid:
        c.validate_release_terminal_status(s, expected_approval=a)
    else:
        with pytest.raises(c.ReleaseContractError):
            c.validate_release_terminal_status(s, expected_approval=a)


def terminal_node(status, path):
    value = status
    for key in path:
        value = value[key]
    return value


TERMINAL_TEST_OBJECT_PATHS = (
    (),
    ("preconditions",),
    ("admission",),
    ("terminal_receipt",),
    ("terminal_receipt", "before"),
    ("terminal_receipt", "after"),
    ("terminal_receipt", "rollback"),
    ("terminal_receipt", "before", "service_generation_digests"),
    ("terminal_receipt", "after", "service_generation_digests"),
)
TERMINAL_TEST_FIELD_PATHS = tuple(
    (
        (path, key)
        for path in TERMINAL_TEST_OBJECT_PATHS
        for key in terminal_node(terminal_fixture("ROLLED_BACK")[1], path)
    )
)


@pytest.mark.parametrize("path,key", TERMINAL_TEST_FIELD_PATHS)
@pytest.mark.parametrize("mutation", ("missing", "null"))
def test_terminal_every_nested_field_is_required_and_nonnull(path, key, mutation):
    approval, status = terminal_fixture("ROLLED_BACK")
    node = terminal_node(status, path)
    if mutation == "missing":
        del node[key]
    else:
        node[key] = None
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(status, expected_approval=approval)


@pytest.mark.parametrize("path", TERMINAL_TEST_OBJECT_PATHS)
def test_terminal_every_object_refuses_unknown_fields(path):
    approval, status = terminal_fixture("ROLLED_BACK")
    terminal_node(status, path)["untrusted_field_never_echo"] = "payload"
    with pytest.raises(c.ReleaseContractError) as caught:
        c.validate_release_terminal_status(status, expected_approval=approval)
    assert "untrusted_field_never_echo" not in str(caught.value)
    assert "payload" != caught.value.code


@pytest.mark.parametrize("state", TERMINAL_TEST_OUTCOMES)
@pytest.mark.parametrize("value", (0, 1, None, "false", [], {}))
def test_terminal_rollback_boolean_is_not_an_integer_or_other_value(state, value):
    approval, status = terminal_fixture(state)
    status["terminal_receipt"]["rollback"]["attempted"] = value
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(status, expected_approval=approval)


@pytest.mark.parametrize("state", TERMINAL_TEST_OUTCOMES)
def test_terminal_rollback_opposite_boolean_is_rejected(state):
    approval, status = terminal_fixture(state)
    status["terminal_receipt"]["rollback"]["attempted"] = state != "ROLLED_BACK"
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(status, expected_approval=approval)


@pytest.mark.parametrize("state", TERMINAL_TEST_STATES[:5])
def test_terminal_public_receipt_requires_a_complete_terminal_status(state):
    approval, status = terminal_fixture(state)
    receipt = terminal_fixture()[1]["terminal_receipt"]
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_receipt(
            receipt, expected_status=status, expected_approval=approval
        )


@pytest.mark.parametrize("field", tuple(terminal_fixture()[1]["terminal_receipt"]))
def test_terminal_public_receipt_revalidates_every_field(field):
    approval, status = terminal_fixture()
    receipt = copy.deepcopy(status["terminal_receipt"])
    receipt[field] = None
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_receipt(
            receipt, expected_status=status, expected_approval=approval
        )


def test_terminal_aggregate_size_is_checked_before_per_child_schema():
    approval, status = terminal_fixture()
    status["preconditions"]["padding"] = "p" * 9000
    status["admission"]["padding"] = "q" * 9000
    assert len(c.canonical_release_bytes(status["preconditions"])) < 16384
    assert len(c.canonical_release_bytes(status["admission"])) < 16384
    with pytest.raises(c.ReleaseContractError) as caught:
        c.validate_release_terminal_status(status, expected_approval=approval)
    assert caught.value.code == "SIZE"
    with pytest.raises(c.ReleaseContractError) as caught:
        c.validate_release_terminal_receipt(
            status["terminal_receipt"],
            expected_status=status,
            expected_approval=approval,
        )
    assert caught.value.code == "SIZE"


def test_terminal_aggregate_depth_is_checked_before_per_child_schema():
    approval, status = terminal_fixture()
    nested = []
    for _ in range(9):
        nested = [nested]
    status["terminal_receipt"]["before"]["extra"] = nested
    with pytest.raises(c.ReleaseContractError) as caught:
        c.validate_release_terminal_status(status, expected_approval=approval)
    assert caught.value.code == "DEPTH"


@pytest.mark.parametrize("state", TERMINAL_TEST_OUTCOMES)
def test_terminal_completion_cannot_precede_start(state):
    approval, status = terminal_fixture(state)
    status["terminal_receipt"]["completed_at_ms"] = status["started_at_ms"] - 1
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(status, expected_approval=approval)


def test_terminal_legacy_p2_receipt_or_status_does_not_become_p4_history():
    approval, status = terminal_fixture()
    legacy = {"request_id": status["request_id"], "status": "SUCCEEDED", "exit_code": 0}
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(legacy, expected_approval=approval)
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_receipt(
            legacy, expected_status=status, expected_approval=approval
        )


class TerminalSplitState(dict):
    def __init__(self, value, reported):
        super().__init__(value)
        self.reported = reported

    def get(self, key, default=None):
        return self.reported if key == "state" else super().get(key, default)


@pytest.mark.parametrize("reported", ["NOT_FOUND", "STARTED"])
@pytest.mark.parametrize(
    "actual", ["SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED", False, "UNRECOGNIZED"]
)
def test_terminal_discriminator_uses_the_validated_snapshot(reported, actual):
    approval, status = terminal_fixture(reported)
    status["state"] = actual
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_status(
            TerminalSplitState(status, reported), expected_approval=approval
        )


@pytest.mark.parametrize("reported", ["NOT_FOUND", "STARTED"])
@pytest.mark.parametrize("actual", ["SUCCEEDED", False, "UNRECOGNIZED"])
def test_terminal_receipt_expected_status_rejects_split_mapping(reported, actual):
    approval, status = terminal_fixture(reported)
    status["state"] = actual
    receipt = terminal_fixture()[1]["terminal_receipt"]
    with pytest.raises(c.ReleaseContractError):
        c.validate_release_terminal_receipt(
            receipt, expected_status=TerminalSplitState(status, reported),
            expected_approval=approval,
        )


@pytest.mark.parametrize("api", ["status", "receipt"])
def test_terminal_caller_discriminator_get_cannot_mutate_snapshot(api):
    class MutatingGet(dict):
        calls = 0

        def get(self, key, default=None):
            self.calls += 1
            self["state"] = "NOT_FOUND"
            self.pop("terminal_receipt", None)
            return super().get(key, default)

    approval, status = terminal_fixture()
    caller = MutatingGet(status)
    if api == "status":
        accepted = c.validate_release_terminal_status(caller, expected_approval=approval)
        assert accepted == c.validate_release_terminal_status(
            accepted, expected_approval=approval
        )
    else:
        accepted = c.validate_release_terminal_receipt(
            status["terminal_receipt"], expected_status=caller,
            expected_approval=approval,
        )
        assert accepted.to_dict() == status["terminal_receipt"]
    assert caller.calls == 0
    assert caller["state"] == "SUCCEEDED"


def test_terminal_source_mapping_items_is_read_once():
    class Once(dict):
        calls = 0

        def items(self):
            self.calls += 1
            assert self.calls == 1, "caller mapping re-read after snapshot"
            return super().items()

    approval, status = terminal_fixture()
    caller = Once(status)
    record = c.validate_release_terminal_status(caller, expected_approval=approval)
    assert caller.calls == 1
    assert record == c.validate_release_terminal_status(record, expected_approval=approval)
