"""Controller policy admission/refusal; fixtures do not establish live trust."""
import dataclasses
import hashlib
import json

import pytest

from control_plane import executive_authority as a
from control_plane import executive_release_contract as c
from integrations.business_mcp_auth.contracts import VerifiedPrincipal


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def source(policy):
    lines = ["executive_release_controller_policy:"]
    for key, value in policy.items():
        if type(value) is list:
            lines.append(f"  {key}:")
            lines.extend(f"    - {item}" for item in value)
        else:
            scalar = str(value).lower() if type(value) is bool else str(value)
            lines.append(f"  {key}: {scalar}")
    return ("# owner snapshot\n" + "\n".join(lines) + "\nother_policy:\n  enabled: true\n").encode()


@pytest.fixture
def inputs():
    issuer = "https://identity.example.test/"
    resource = "https://executive.example.test/"
    principal = VerifiedPrincipal(
        policy_id="release-policy", issuer=issuer,
        issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(), resource=resource,
        subject_digest="a" * 64, client_ref="b" * 64,
        scopes=("mastermind.executive.intent.submit", "mastermind.executive.read"),
        issued_at=100, expires_at=1000, jti_digest=None)
    effect = {
        "schema": "mastermind.executive_release_effect/v1",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "protected_source_sha": "1" * 40, "source_policy_mode": "exact_protected_master",
        "installer_source_commit": "1" * 40, "installer_source_tree": "2" * 40,
        "installer_profile_digest": "c" * 64, "from_release_commit": "3" * 40,
        "from_release_tree": "4" * 40, "from_installed_manifest_digest": "d" * 64,
        "to_release_commit": "1" * 40, "to_release_tree": "2" * 40,
        "staged_artifact_digest": "e" * 64, "staged_content_metadata_digest": "f" * 64,
        "platform": "darwin", "architecture": "arm64",
        "configuration_transition_digest": "1" * 64, "compatibility_proof_digest": "2" * 64,
        "preservation_plan_digest": "3" * 64,
        "rollback_evidence": {"kind": "upgrade", "rollback_readiness_digest": "4" * 64},
        "action": "executive.release.upgrade",
    }
    policy = {
        "schema": "mastermind.executive_release_controller_policy/v1",
        "policy_id": principal.policy_id, "generation": 7, "enabled": True,
        "issuer_digest": principal.issuer_digest,
        "resource_digest": hashlib.sha256(resource.encode()).hexdigest(),
        "subject_digests": [principal.subject_digest], "client_refs": [principal.client_ref],
        "required_scopes": list(principal.scopes), "actions": [effect["action"]],
        "target_refs": ["5" * 64], "installer_profile_digests": [effect["installer_profile_digest"]],
        "source_policy_modes": [effect["source_policy_mode"]],
        "max_approval_lifetime_seconds": 300, "confirmation_requirement": "delegated",
    }
    return principal, effect, policy


def evaluate(inputs, **kwargs):
    principal, effect, policy = inputs
    return a.authorize_release_transition(
        principal, c.validate_normalized_effect(effect),
        a.ReleaseControllerPolicy.from_bytes(source(policy)),
        target_ref=kwargs.pop("target_ref", "5" * 64),
        now_ms=kwargs.pop("now_ms", 200000), **kwargs)


def test_existing_installed_map_is_unconfigured_and_worker_behavior_unchanged():
    assert a.ReleaseControllerPolicy.load().configuration_state is a.ReleasePolicyState.UNCONFIGURED
    worker = a.ExecutiveAuthorityPolicy.load()
    assert worker.allowed == a.PHASE1B_ALLOWED
    assert worker.authorize(["READ"]).requested == ("READ",)
    with pytest.raises(a.AuthorityDenied):
        worker.authorize(["executive.release.upgrade"])


@pytest.mark.parametrize("raw,state,code", [
    (b"other_policy:\n  enabled: true\n", a.ReleasePolicyState.UNCONFIGURED, "RELEASE_POLICY_UNCONFIGURED"),
])
def test_absence_is_typed_and_refuses_before_principal(raw, state, code):
    policy = a.ReleaseControllerPolicy.from_bytes(raw)
    assert policy.configuration_state is state
    with pytest.raises(a.ReleaseAuthorityDenied, match=f"^{code}$"):
        a.authorize_release_transition(None, None, policy, target_ref="5" * 64, now_ms=0)


def test_disabled_present_policy_is_validated_but_cannot_grant(inputs):
    inputs[2]["enabled"] = False
    policy = a.ReleaseControllerPolicy.from_bytes(source(inputs[2]))
    assert policy.configuration_state is a.ReleasePolicyState.DISABLED
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_DISABLED$"):
        evaluate(inputs)
    del inputs[2]["client_refs"]
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
        a.ReleaseControllerPolicy.from_bytes(source(inputs[2]))


def test_complete_delegated_grant_binds_whole_policy_and_effect(inputs):
    principal, effect, policy = inputs
    result = evaluate(inputs)
    projection = a.release_principal_projection(principal)
    assert result["authority_policy_hash"] == hashlib.sha256(source(policy)).hexdigest()
    assert result["principal_digest"] == digest(projection.to_dict())
    assert result["transition_digest"] == digest(effect)
    assert result["policy_generation"] == 7
    assert result["granted_at_ms"] == 200000
    assert result["expires_at_ms"] == 500000
    assert c.validate_release_grant(result) == result
    before = c.canonical_release_bytes(result)
    effect["staged_artifact_digest"] = "0" * 64
    policy["generation"] += 1
    assert c.canonical_release_bytes(result) == before
    changed = evaluate(inputs)
    assert changed["confirmation_evidence_digest"] != result["confirmation_evidence_digest"]


@pytest.mark.parametrize("field", sorted(a._RELEASE_LIST_FIELDS))
@pytest.mark.parametrize("value", [[], ["*"], ["x", "x"], ["x"] * 33])
def test_present_lists_are_explicit_unique_bounded(inputs, field, value):
    inputs[2][field] = value
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
        a.ReleaseControllerPolicy.from_bytes(source(inputs[2]))


@pytest.mark.parametrize("edit", [
    lambda s: s.replace(b"enabled: true", b"enabled: yes"),
    lambda s: s.replace(b"generation: 7", b"generation: true"),
    lambda s: s.replace(b"generation: 7", b"generation: 07"),
    lambda s: s.replace(b"generation: 7", b"generation: 7\n  generation: 7"),
    lambda s: s + b"executive_release_controller_policy:\n",
    lambda s: s.replace(b"controller_policy:", b"controller_policy: &alias"),
    lambda s: s.replace(b"controller_policy:", b"controller_policy: {}"),
    lambda s: s.replace(b"controller_policy:", b"controller_policy:\xc2\xa0"),
    lambda s: s.replace(b"executive_release_controller_policy:", b"'executive_release_controller_policy':"),
    lambda s: s.replace(b"  actions:\n    - executive.release.upgrade", b"  actions: [executive.release.upgrade]"),
    lambda s: s.replace(b"  actions:", b"  actions: *alias"),
    lambda s: s.replace(b"  enabled: true", b"  unknown: true"),
    lambda s: s.replace(b"  enabled", b"\tenabled"),
    lambda s: s + b"\x00",
    lambda s: b"\xff",
])
def test_parser_rejects_ambiguous_yaml_and_unknown_fields(inputs, edit):
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
        a.ReleaseControllerPolicy.from_bytes(edit(source(inputs[2])))


@pytest.mark.parametrize("field,value", [
    ("policy_id", "different-policy"), ("issuer_digest", "9" * 64),
    ("resource_digest", "9" * 64), ("subject_digests", ["9" * 64]),
    ("client_refs", ["9" * 64]), ("required_scopes", ["another.scope", "mastermind.executive.intent.submit"]),
])
def test_each_principal_policy_mismatch_refuses(inputs, field, value):
    inputs[2][field] = value
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_PRINCIPAL_NOT_AUTHORIZED$"):
        evaluate(inputs)


@pytest.mark.parametrize("field,value", [
    ("actions", ["executive.release.rollback"]), ("target_refs", ["9" * 64]),
    ("installer_profile_digests", ["9" * 64]), ("source_policy_modes", ["frozen_accepted_ancestor"]),
])
def test_each_transition_policy_mismatch_refuses(inputs, field, value):
    inputs[2][field] = value
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_TRANSITION_NOT_AUTHORIZED$"):
        evaluate(inputs)


@pytest.mark.parametrize("principal", [None, True, {}, "principal", object()])
def test_public_values_cannot_supply_verified_principal(inputs, principal):
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_VERIFIED_PRINCIPAL_REQUIRED$"):
        evaluate((principal, inputs[1], inputs[2]))


@pytest.mark.parametrize("field,value", [
    ("client_ref", "oauth-client-unavailable"), ("client_ref", "*"),
    ("issued_at", True), ("expires_at", False), ("issued_at", 1001),
    ("issuer_digest", "9" * 64), ("scopes", []), ("scopes", ("mastermind.executive.read",)),
    ("issuer", "\ud800"), ("resource", "https://bad\nresource"),
])
def test_invalid_or_read_only_principal_cannot_grant(inputs, field, value):
    principal = dataclasses.replace(inputs[0], **{field: value})
    with pytest.raises(a.ReleaseAuthorityDenied):
        evaluate((principal, inputs[1], inputs[2]))


@pytest.mark.parametrize("now", [True, -1, 1.5, "200000", 1 << 63])
def test_clock_is_owner_integer_not_coerced(inputs, now):
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CLOCK_INVALID$"):
        evaluate(inputs, now_ms=now)


@pytest.mark.parametrize("now", [99999, 1000000, 1000001])
def test_authentication_must_be_current_without_expiry_grace(inputs, now):
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_PRINCIPAL_NOT_CURRENT$"):
        evaluate(inputs, now_ms=now)


def test_expiry_is_earliest_policy_and_authentication_bound(inputs):
    assert evaluate(inputs, now_ms=900000)["expires_at_ms"] == 1000000
    inputs[2]["max_approval_lifetime_seconds"] = 1
    assert evaluate(inputs)["expires_at_ms"] == 201000


def test_transition_and_policy_are_not_untyped_public_mappings(inputs):
    principal, effect, policy = inputs
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_IMMUTABLE_TRANSITION_REQUIRED$"):
        a.authorize_release_transition(principal, effect, a.ReleaseControllerPolicy.from_bytes(source(policy)),
                                       target_ref="5" * 64, now_ms=200000)
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_INSTALLED_POLICY_REQUIRED$"):
        a.authorize_release_transition(principal, c.validate_normalized_effect(effect), policy,
                                       target_ref="5" * 64, now_ms=200000)


def confirmation_fixture(inputs, **overrides):
    # Explicit internal fixture, NOT proof of an authenticated confirmation UI.
    principal, effect, policy = inputs
    fields = dict(principal_digest=digest(a.release_principal_projection(principal).to_dict()),
                  target_ref="5" * 64, transition_digest=digest(effect),
                  authority_policy_hash=hashlib.sha256(source(policy)).hexdigest(),
                  evidence_digest="6" * 64, expires_at_ms=210000)
    fields.update(overrides)
    return a._bind_trusted_release_confirmation(a._RELEASE_CONFIRMATION_CAPABILITY, **fields)


@pytest.mark.parametrize("value", [None, True, {}, {"approved": True}, "approved"])
def test_required_confirmation_refuses_model_assertions(inputs, value):
    inputs[2]["confirmation_requirement"] = "required"
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CONFIRMATION_PROVENANCE_REQUIRED$"):
        evaluate(inputs, confirmation=value)


def test_confirmation_constructor_and_unregistered_object_are_not_authority(inputs):
    inputs[2]["confirmation_requirement"] = "required"
    with pytest.raises(TypeError):
        a.TrustedReleaseConfirmation()
    forged = object.__new__(a.TrustedReleaseConfirmation)
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CONFIRMATION_PROVENANCE_REQUIRED$"):
        evaluate(inputs, confirmation=forged)


def test_real_owner_context_mechanics_bound_expiry_and_replay(inputs):
    inputs[2]["confirmation_requirement"] = "required"
    confirmation = confirmation_fixture(inputs)
    first = evaluate(inputs, confirmation=confirmation)
    assert first["confirmation_evidence_digest"] == "6" * 64
    assert first["expires_at_ms"] == 210000
    assert evaluate(inputs, confirmation=confirmation) == first
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CONFIRMATION_EXPIRED$"):
        evaluate(inputs, confirmation=confirmation, now_ms=210000)


@pytest.mark.parametrize("field", ["principal_digest", "target_ref", "transition_digest", "authority_policy_hash"])
def test_confirmation_cannot_be_reused_for_different_identity(inputs, field):
    inputs[2]["confirmation_requirement"] = "required"
    confirmation = confirmation_fixture(inputs, **{field: "9" * 64})
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CONFIRMATION_BINDING_MISMATCH$"):
        evaluate(inputs, confirmation=confirmation)


def test_confirmation_cannot_survive_receiver_process_change(inputs, monkeypatch):
    inputs[2]["confirmation_requirement"] = "required"
    confirmation = confirmation_fixture(inputs)
    pid = a._os.getpid()
    monkeypatch.setattr(a._os, "getpid", lambda: pid + 1)
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CONFIRMATION_BINDING_MISMATCH$"):
        evaluate(inputs, confirmation=confirmation)


def test_delegation_cannot_take_caller_confirmation(inputs):
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_UNEXPECTED_CONFIRMATION$"):
        evaluate(inputs, confirmation=True)


def test_token_rotation_does_not_change_logical_identity(inputs):
    first = evaluate(inputs)
    rotated = dataclasses.replace(inputs[0], issued_at=190, expires_at=1200, jti_digest="9" * 64)
    second = evaluate((rotated, inputs[1], inputs[2]))
    assert first == second


def test_no_implicit_policy_defaults_or_enabled_file_write(inputs, tmp_path):
    path = tmp_path / "authority.yml"
    original = source(inputs[2])
    path.write_bytes(original)
    mode = path.stat().st_mode
    policy = a.ReleaseControllerPolicy.load(path)
    assert policy.sha256 == hashlib.sha256(original).hexdigest()
    assert path.read_bytes() == original and path.stat().st_mode == mode
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_UNAVAILABLE$"):
        a.ReleaseControllerPolicy.load(tmp_path / "absent")


def test_generated_grant_composes_with_exact_accepted_a1_approval(inputs):
    from control_plane.ceo_request import app_request_ref
    principal, effect, _ = inputs
    grant = evaluate(inputs)
    operation = "controller-policy-composition"
    approval = dict(
        schema="mastermind.executive_release_approval/v1", operation_key=operation,
        request_ref=app_request_ref(operation), approved_transition_ref=c.approval_ref_for(operation),
        action=effect["action"], owner_installation_id="11111111-1111-4111-8111-111111111111",
        target_ref="5" * 64, principal_projection=a.release_principal_projection(principal),
        normalized_requested_effect=c.validate_normalized_effect(effect), transition_digest=digest(effect),
        grant=grant, effective_grant_digest=digest(grant.to_dict()),
        created_at_ms=200000, expires_at_ms=grant["expires_at_ms"],
        # Structural fixture only: no key/signing or cryptographic approval.
        owner_seal=dict(key_id="fixture-key", trust_generation=1, mac="A" * 43),
    )
    validated = c.validate_approval_evidence(approval)
    assert validated["grant"] == grant
    assert len(c.canonical_release_bytes(validated)) < 16384


def test_confirmation_seam_requires_owner_capability(inputs):
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_CONFIRMATION_PROVENANCE_REQUIRED$"):
        a._bind_trusted_release_confirmation(
            object(), principal_digest="1" * 64, target_ref="2" * 64,
            transition_digest="3" * 64, authority_policy_hash="4" * 64,
            evidence_digest="5" * 64, expires_at_ms=1)


def test_parser_snapshot_handles_crlf_without_yaml_coercion(inputs):
    policy = a.ReleaseControllerPolicy.from_bytes(source(inputs[2]).replace(b"\n", b"\r\n"))
    assert policy.configuration_state is a.ReleasePolicyState.CONFIGURED


def test_source_limits_are_bounded(inputs):
    for raw in (b"", "not bytes", b"#" * (a._RELEASE_MAX_SOURCE_BYTES + 1)):
        with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
            a.ReleaseControllerPolicy.from_bytes(raw)


@pytest.mark.parametrize("outside", [
    b'"executive_release_controller_polic\\u0079":\n  enabled: false\n',
    b'? executive_release_controller_policy\n:\n  enabled: false\n',
    b'---\nother_document:\n  enabled: false\n',
    b'...\n',
    b'%YAML 1.2\n',
    b'*alias:\n  enabled: false\n',
    b'<<: *alias\n',
    b'other_policy: &root_alias\n  enabled: false\n',
    b'"different_escaped_root":\n  enabled: false\n',
])
@pytest.mark.parametrize("position", ["before", "after"])
def test_whole_document_root_shape_refuses_ambiguity(inputs, outside, position):
    valid = source(inputs[2])
    raw = outside + valid if position == "before" else valid + outside
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
        a.ReleaseControllerPolicy.from_bytes(raw)


def test_ordinary_authority_sections_survive_on_either_side(inputs):
    installed = a._POLICY_PATH.read_bytes()
    release = source(inputs[2])
    for raw in (installed + b"\n" + release, release + b"\n" + installed):
        policy = a.ReleaseControllerPolicy.from_bytes(raw)
        assert policy.configuration_state is a.ReleasePolicyState.CONFIGURED
        assert policy.sha256 == hashlib.sha256(raw).hexdigest()
    for raw in (b'# comment only\n', b'ordinary_section:\n  text: >\n    quoted "prose" remains other-owner data\n'):
        assert a.ReleaseControllerPolicy.from_bytes(raw).configuration_state is a.ReleasePolicyState.UNCONFIGURED


def test_duplicate_ordinary_root_is_ambiguous_before_authority(inputs):
    raw = source(inputs[2]) + b'other_policy:\n  enabled: false\n'
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
        a.ReleaseControllerPolicy.from_bytes(raw)


@pytest.mark.parametrize("opener,closer", [
    (b'ordinary_section:\n  note: "start\n', b'  end"\n'),
    (b"ordinary_section:\n  note: 'start\n", b"  end'\n"),
    (b'ordinary_section:\n  note: ["start\n', b'  end"]\n'),
    (b'ordinary_section:\n  note: {nested: "start\n', b'  end"}\n'),
    (b'ordinary_section:\n  note: &anchor "start\n', b'  end"\n'),
    (b'ordinary_section:\n  note: !!str "start\n', b'  end"\n'),
])
def test_other_section_multiline_content_cannot_become_authority(inputs, opener, closer):
    raw = opener + source(inputs[2]) + closer
    with pytest.raises(a.ReleaseAuthorityDenied, match="^RELEASE_POLICY_INVALID$"):
        a.ReleaseControllerPolicy.from_bytes(raw)


def test_other_section_single_line_values_and_block_prose_remain_supported(inputs):
    ordinary = b'''ordinary_data:
  quoted: "single line"
  apostrophe: 'it''s one value'
  flow: {nested: ["one", 'two']}
  plain: owner's description
  note: >
    Unbalanced "quotes and {brackets are plain block text.
    A mentioned executive_release_controller_policy: is text.
'''
    for raw in (ordinary + source(inputs[2]), source(inputs[2]) + ordinary):
        assert a.ReleaseControllerPolicy.from_bytes(raw).configuration_state is a.ReleasePolicyState.CONFIGURED
