"""control_plane.ceo_request — MAS-75 PR-A shared normalization/derivation law.

Hermetic: stdlib + pytest only.  No network, no socket, no runtime database.
Three families are proven here:

* the exact current MCP normalization semantics (adjudication §4.2), preserved
  bit-for-bit and shared by both execution profiles (§4.3), including every
  privileged field being structurally impossible to supply (§4.1);
* the two transport-specific canonical intent identity functions (§6), pinned
  against the LITERAL frozen vectors from the adjudication text — never values
  computed by the function under test;
* the §15.1 cross-transport golden fixture: literal intent ids, canonical
  envelope UTF-8 byte lengths, and fingerprints, built through the existing
  ``control_plane.ceo_intent`` envelope/fingerprint code paths.

``integrations.executive_mcp.schemas`` is imported here ONLY for a compatibility
check (its own already-frozen ``FORBIDDEN_INPUT_FIELDS`` tuple and its
``_validate_submit``); ``control_plane.ceo_request`` itself never imports it —
see the import-boundary check at the bottom of this file.

MAS-75 PR-A P1 repair (single canonical authority): ``schemas._validate_submit``
is now a pure DELEGATING WRAPPER over ``normalize_high_level_request`` below —
it holds no independent field/path/validation policy of its own.  The
"byte-for-byte"/"refusal parity" tests near the bottom of this file therefore
no longer compare two independently-arrived-at implementations; they are
DELEGATION-WIRING checks that the wrapper still calls through and still maps
errors/messages correctly.  The boundary-edge probes (operation_key/objective/
priority/attempt_limit accept-vs-refuse edges) still attack
``normalize_high_level_request`` DIRECTLY as well, so the canonical law keeps
its own regression fence independent of the MCP wrapper.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from control_plane import ceo_intent
from control_plane import ceo_request as cr
from integrations.executive_mcp import schemas


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _research_only_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_key": "options-chain-browser-closure-001",
        "objective": "Implement the assigned bounded deliverable and return evidence.",
        "department": "executive-infrastructure",
        "priority": 10,
        "execution_profile": "research_only",
    }
    payload.update(overrides)
    return payload


def _bounded_code_change_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_key": "options-chain-browser-closure-002",
        "objective": "Implement the assigned bounded deliverable and return evidence.",
        "department": "executive-infrastructure",
        "priority": 5,
        "execution_profile": "bounded_code_change",
        "allowed_write_paths": ["control_plane/thing.py"],
        "validation": {"pytest_targets": ["tests/test_thing.py"]},
    }
    payload.update(overrides)
    return payload


# ===========================================================================
# §4.1 — required/optional fields; nothing else accepted
# ===========================================================================


def test_required_fields_are_exactly_the_documented_five():
    assert cr.REQUIRED_FIELDS == frozenset(
        {"operation_key", "objective", "department", "priority", "execution_profile"}
    )
    assert cr.OPTIONAL_FIELDS == frozenset(
        {"workstream", "allowed_write_paths", "validation", "attempt_limit"}
    )


def test_missing_required_field_refuses():
    payload = _research_only_payload()
    del payload["department"]
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)


@pytest.mark.parametrize("field", sorted(schemas.FORBIDDEN_INPUT_FIELDS))
def test_privileged_field_is_structurally_refused(field: str):
    """§4.1 — nothing else is accepted; every privileged field refuses.

    Reuses the MCP gateway's own frozen ``FORBIDDEN_INPUT_FIELDS`` enumeration
    (actor, requested_authorities, raw argv, branch, worktree, job id/status,
    dispatched, constraints, authority_level, schema, intent_id, grounding
    SHAs, policy hash) so both transports are pinned against one list.
    """

    payload = _research_only_payload()
    payload[field] = "smuggled"
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)


def test_unknown_field_refuses():
    payload = _research_only_payload()
    payload["totally_unknown"] = 1
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)


def test_non_mapping_payload_refuses():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(["not", "a", "mapping"])


# ===========================================================================
# §4.2 — exact current normalization semantics
# ===========================================================================


def test_operation_key_is_not_stripped():
    payload = _research_only_payload(operation_key=" options-chain-browser-closure-001")
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)


def test_objective_is_stripped_and_empty_after_strip_refuses():
    payload = _research_only_payload(objective="   hello world   ")
    normalized = cr.normalize_high_level_request(payload)
    assert normalized["objective"] == "hello world"

    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(_research_only_payload(objective="   \n\t  "))


def test_department_is_exact_form_no_strip_no_case_repair():
    # Uppercase would need case-folding to become legal; it must REFUSE, never
    # be silently lowercased.
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(department="Executive-Infrastructure")
        )
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(department=" executive-infrastructure")
        )


def test_execution_profile_is_exact_form_no_case_fold():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(execution_profile="Research_Only")
        )


def test_workstream_is_exact_form_no_strip():
    normalized = cr.normalize_high_level_request(
        _research_only_payload(workstream="WS:MAS-75")
    )
    assert normalized["workstream"] == "WS:MAS-75"
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(workstream=" WS:MAS-75")
        )


def test_allowed_write_paths_strip_normalize_dedupe_sort():
    payload = _bounded_code_change_payload(
        allowed_write_paths=[
            "  control_plane/b.py",
            "./control_plane//a.py",
            "control_plane/b.py",
        ]
    )
    normalized = cr.normalize_high_level_request(payload)
    assert normalized["allowed_write_paths"] == [
        "control_plane/a.py",
        "control_plane/b.py",
    ]


@pytest.mark.parametrize(
    "bad_path",
    [
        "/absolute/path.py",
        "~/home/path.py",
        "../escape.py",
        "control_plane\\windows.py",
        "control_plane/.git/config",
    ],
)
def test_allowed_write_paths_refuses_escape_and_git_internals(bad_path: str):
    payload = _bounded_code_change_payload(allowed_write_paths=[bad_path])
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)


def test_omitted_and_empty_allowed_write_paths_are_identical():
    omitted = cr.normalize_high_level_request(_research_only_payload())
    empty = cr.normalize_high_level_request(
        _research_only_payload(allowed_write_paths=[])
    )
    assert omitted["allowed_write_paths"] == empty["allowed_write_paths"] == []


def test_validation_targets_are_relative_path_fenced_deduped_sorted():
    payload = _bounded_code_change_payload(
        validation={
            "pytest_targets": ["tests/test_b.py", "tests/test_a.py", "tests/test_b.py"],
            "compileall_paths": ["control_plane", "engine"],
        }
    )
    normalized = cr.normalize_high_level_request(payload)
    assert normalized["validation"]["pytest_targets"] == [
        "tests/test_a.py",
        "tests/test_b.py",
    ]
    assert normalized["validation"]["compileall_paths"] == ["control_plane", "engine"]


def test_pytest_target_must_resolve_under_tests_and_be_py():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _bounded_code_change_payload(validation={"pytest_targets": ["control_plane/x.py"]})
        )
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _bounded_code_change_payload(validation={"pytest_targets": ["tests/test_a.txt"]})
        )


def test_compileall_path_must_not_be_a_py_file():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _bounded_code_change_payload(validation={"compileall_paths": ["control_plane/x.py"]})
        )


def test_git_diff_check_true_survives_false_is_removed():
    true_payload = _bounded_code_change_payload(
        validation={
            "pytest_targets": ["tests/test_thing.py"],
            "git_diff_check": True,
        }
    )
    normalized_true = cr.normalize_high_level_request(true_payload)
    assert normalized_true["validation"]["git_diff_check"] is True

    false_payload = _bounded_code_change_payload(
        validation={
            "pytest_targets": ["tests/test_thing.py"],
            "git_diff_check": False,
        }
    )
    normalized_false = cr.normalize_high_level_request(false_payload)
    assert "git_diff_check" not in normalized_false["validation"]


def test_git_diff_check_must_be_a_real_bool():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _bounded_code_change_payload(
                validation={
                    "pytest_targets": ["tests/test_thing.py"],
                    "git_diff_check": 1,
                }
            )
        )


def test_omitted_and_all_empty_validation_are_identical():
    research = cr.normalize_high_level_request(_research_only_payload())
    research_explicit_empty = cr.normalize_high_level_request(
        _research_only_payload(validation={})
    )
    assert research["validation"] == research_explicit_empty["validation"] == {}

    all_false = cr.normalize_high_level_request(
        _research_only_payload(validation={"git_diff_check": False})
    )
    assert all_false["validation"] == {}


def test_attempt_limit_default_and_bounds():
    omitted = cr.normalize_high_level_request(_research_only_payload())
    assert omitted["attempt_limit"] == 2 == cr.DEFAULT_ATTEMPT_LIMIT

    for legal in (1, 2, 3):
        normalized = cr.normalize_high_level_request(
            _research_only_payload(attempt_limit=legal)
        )
        assert normalized["attempt_limit"] == legal

    for illegal in (0, 4, -1):
        with pytest.raises(cr.CeoRequestInvalid):
            cr.normalize_high_level_request(_research_only_payload(attempt_limit=illegal))


def test_attempt_limit_bool_is_not_an_int():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(_research_only_payload(attempt_limit=True))


def test_priority_bool_is_not_an_int():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(_research_only_payload(priority=True))


def test_derived_authorities_are_sorted():
    assert cr.derive_authorities("research_only") == ["READ", "RESEARCH"]
    assert cr.derive_authorities("bounded_code_change") == [
        "READ",
        "RUN_TESTS",
        "WRITE_BRANCH",
    ]


def test_validation_argv_family_ordering_is_pytest_compileall_git():
    commands = cr.build_validation_commands(
        {
            "git_diff_check": True,
            "compileall_paths": ["control_plane"],
            "pytest_targets": ["tests/test_a.py"],
        }
    )
    assert commands == [
        ["python3", "-m", "pytest", "-q", "tests/test_a.py"],
        ["python3", "-m", "compileall", "control_plane"],
        ["git", "diff", "--check"],
    ]


def test_build_validation_commands_empty_or_none_is_empty():
    assert cr.build_validation_commands(None) == []
    assert cr.build_validation_commands({}) == []


# ===========================================================================
# §4.3 — execution profiles
# ===========================================================================


def test_research_only_forbids_write_paths_and_validation():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(allowed_write_paths=["control_plane/x.py"])
        )
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(validation={"pytest_targets": ["tests/test_a.py"]})
        )


def test_bounded_code_change_requires_write_path_and_validation():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _bounded_code_change_payload(allowed_write_paths=[])
        )
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(_bounded_code_change_payload(validation={}))


def test_unknown_execution_profile_refuses():
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(
            _research_only_payload(execution_profile="deploy_everything")
        )


def test_no_profile_grows_a_high_authority(monkeypatch: pytest.MonkeyPatch):
    """A profile mutated to escape the reviewed ceiling is an INTERNAL defect."""

    monkeypatch.setattr(
        cr,
        "EXECUTION_PROFILES",
        {**cr.EXECUTION_PROFILES, "research_only": ("READ", "RESEARCH", "DEPLOY")},
    )
    with pytest.raises(cr.CeoRequestInternalError) as excinfo:
        cr.derive_authorities("research_only")
    assert excinfo.value.caller_fault is False


def test_derive_authorities_unknown_profile_is_caller_fault():
    with pytest.raises(cr.CeoRequestInvalid) as excinfo:
        cr.derive_authorities("not_a_real_profile")
    assert excinfo.value.caller_fault is True


# ===========================================================================
# §4.4 — typed internal errors
# ===========================================================================


def test_error_hierarchy_and_caller_fault_flags():
    assert issubclass(cr.CeoRequestInvalid, cr.CeoRequestError)
    assert issubclass(cr.CeoRequestInternalError, cr.CeoRequestError)
    assert cr.CeoRequestInvalid("x").caller_fault is True
    assert cr.CeoRequestInternalError("x").caller_fault is False


# ===========================================================================
# §6 — transport-specific intent identity, literal frozen vectors
# ===========================================================================

_LITERAL_VECTORS = (
    (
        "options-chain-browser-closure-001",
        "mcp-400560e76b2e72590f12d30f782bfc4d",
        "slack-4e40f3d7656227ee9dcead6b00c9d5f2",
    ),
    (
        "mas-75-pr-a-research-proof-001",
        "mcp-5c6f5256500080fc8f4f4ecceb9ff62a",
        "slack-e824a09702dce2aeed46fb41d16711e6",
    ),
    (
        "ceo-slack-canary-001",
        "mcp-1822467f893259d7322d9f0be5ee051c",
        "slack-9ccec918320bf1518d89144be5a4ad42",
    ),
)


@pytest.mark.parametrize("operation_key,mcp_expected,slack_expected", _LITERAL_VECTORS)
def test_literal_transport_identity_vectors(
    operation_key: str, mcp_expected: str, slack_expected: str
):
    """§6.2 — literal regression expectations, never computed by the function
    under test."""

    assert cr.mcp_intent_id(operation_key) == mcp_expected
    assert cr.slack_intent_id(operation_key) == slack_expected


def test_mcp_identity_matches_the_existing_frozen_mcp_gateway_derivation():
    """MINOR 10: after the refactor, ``schemas.derive_intent_id`` DELEGATES to
    ``cr.mcp_intent_id`` — it is no longer an independent re-derivation. This
    assertion therefore pins the delegation WIRING (that ``schemas`` still
    calls through to the shared law and returns its exact value), not two
    independently-arrived-at derivations. It still guards against a real
    regression: it fails if the delegation is ever removed and the two
    diverge (adjudication §6.1, §15)."""

    for operation_key, _mcp_expected, _slack_expected in _LITERAL_VECTORS:
        assert cr.mcp_intent_id(operation_key) == schemas.derive_intent_id(operation_key)


def test_cross_transport_identities_are_never_inferred_from_each_other():
    """Cross-transport dedupe is NOT inferred (§6): one operation_key mints two
    independent, differently-prefixed, differently-namespaced ids."""

    for operation_key, mcp_expected, slack_expected in _LITERAL_VECTORS:
        mcp_id = cr.mcp_intent_id(operation_key)
        slack_id = cr.slack_intent_id(operation_key)
        assert mcp_id != slack_id
        assert mcp_id.startswith("mcp-")
        assert slack_id.startswith("slack-")
        assert mcp_id == mcp_expected
        assert slack_id == slack_expected


def test_derive_branch_and_worktree():
    intent_id = cr.mcp_intent_id("options-chain-browser-closure-001")
    assert cr.derive_branch(intent_id) == f"codex/{intent_id}"
    assert cr.derive_worktree("/tmp/ws", intent_id) == f"/tmp/ws/{intent_id}"
    # Trailing slash on the workspace root must not double up.
    assert cr.derive_worktree("/tmp/ws/", intent_id) == f"/tmp/ws/{intent_id}"


def test_derive_worktree_requires_an_absolute_workspace_root():
    intent_id = cr.mcp_intent_id("options-chain-browser-closure-001")
    with pytest.raises(cr.CeoRequestInternalError):
        cr.derive_worktree("relative/ws", intent_id)


# ===========================================================================
# §5 — trusted v1 derivation / envelope assembly
# ===========================================================================

_FIXTURE_GROUNDING = {
    "mastermind_sha": "1111111111111111111111111111111111111111",
    "macro_sha": "2222222222222222222222222222222222222222",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
}
_FIXTURE_WORKSPACE_ROOT = "/tmp/mas75-workspaces"


def _fixture_payload() -> dict[str, object]:
    return {
        "operation_key": "options-chain-browser-closure-001",
        "objective": "Implement the assigned bounded deliverable and return evidence.",
        "department": "executive-infrastructure",
        "priority": 10,
        "execution_profile": "research_only",
    }


def test_build_trusted_envelope_derives_actor_schema_authority_level():
    normalized = cr.normalize_high_level_request(_fixture_payload())
    intent_id = cr.mcp_intent_id(normalized["operation_key"])
    envelope = cr.build_trusted_envelope(
        normalized,
        intent_id=intent_id,
        workspace_root=_FIXTURE_WORKSPACE_ROOT,
        grounding=_FIXTURE_GROUNDING,
    )
    assert envelope["actor"] == "ceo-sol" == cr.ACTOR
    assert envelope["schema"] == ceo_intent.INTENT_SCHEMA == "mastermind.ceo_intent.v1"
    assert envelope["execution_contract"]["authority_level"] == "A0" == cr.AUTHORITY_LEVEL
    assert envelope["execution_contract"]["branch"] == f"codex/{intent_id}"
    assert envelope["execution_contract"]["worktree"] == f"{_FIXTURE_WORKSPACE_ROOT}/{intent_id}"


# ===========================================================================
# §15.1 — cross-transport golden fixture (literal, never computed loosely)
# ===========================================================================

_GOLDEN_MCP_INTENT_ID = "mcp-400560e76b2e72590f12d30f782bfc4d"
_GOLDEN_MCP_ENVELOPE_BYTES = 654
_GOLDEN_MCP_FINGERPRINT = (
    "2afba2ba02b4d2d7f3875cd2c13612f7d27fa44b7d9cd268f9f867542df6ccbe"
)

_GOLDEN_SLACK_INTENT_ID = "slack-4e40f3d7656227ee9dcead6b00c9d5f2"
_GOLDEN_SLACK_ENVELOPE_BYTES = 660
_GOLDEN_SLACK_FINGERPRINT = (
    "d35b07a3c259046ada8d849fc57575a2f2d7b44de5ede8d8db5e9f1a570666b8"
)


def _golden_envelope(intent_id: str) -> dict[str, object]:
    normalized = cr.normalize_high_level_request(_fixture_payload())
    return cr.build_trusted_envelope(
        normalized,
        intent_id=intent_id,
        workspace_root=_FIXTURE_WORKSPACE_ROOT,
        grounding=_FIXTURE_GROUNDING,
    )


def test_golden_fixture_mcp_v1():
    intent_id = cr.mcp_intent_id("options-chain-browser-closure-001")
    assert intent_id == _GOLDEN_MCP_INTENT_ID

    envelope = _golden_envelope(intent_id)
    validated = ceo_intent.validate_intent(envelope)
    canonical = ceo_intent.canonical_bytes(validated)
    fingerprint = ceo_intent.intent_fingerprint(validated)

    assert len(canonical) == _GOLDEN_MCP_ENVELOPE_BYTES
    assert fingerprint == _GOLDEN_MCP_FINGERPRINT


def test_golden_fixture_slack_v1():
    intent_id = cr.slack_intent_id("options-chain-browser-closure-001")
    assert intent_id == _GOLDEN_SLACK_INTENT_ID

    envelope = _golden_envelope(intent_id)
    validated = ceo_intent.validate_intent(envelope)
    canonical = ceo_intent.canonical_bytes(validated)
    fingerprint = ceo_intent.intent_fingerprint(validated)

    assert len(canonical) == _GOLDEN_SLACK_ENVELOPE_BYTES
    assert fingerprint == _GOLDEN_SLACK_FINGERPRINT


def test_golden_fixture_envelopes_differ_only_where_transport_identity_propagates():
    """§15.1 — intent id, branch, worktree differ; everything else is identical."""

    mcp_intent_id = cr.mcp_intent_id("options-chain-browser-closure-001")
    slack_intent_id = cr.slack_intent_id("options-chain-browser-closure-001")
    mcp_envelope = ceo_intent.validate_intent(_golden_envelope(mcp_intent_id))
    slack_envelope = ceo_intent.validate_intent(_golden_envelope(slack_intent_id))

    for key in ("actor", "objective", "department", "priority", "grounding"):
        assert mcp_envelope[key] == slack_envelope[key]

    mcp_contract = mcp_envelope["execution_contract"]
    slack_contract = slack_envelope["execution_contract"]
    for key in ("requested_authorities", "authority_level", "attempt_limit"):
        assert mcp_contract[key] == slack_contract[key]

    assert mcp_contract["branch"] != slack_contract["branch"]
    assert mcp_contract["worktree"] != slack_contract["worktree"]
    assert mcp_envelope["intent_id"] != slack_envelope["intent_id"]


# ===========================================================================
# delegation-wiring parity between the shared law and the MCP wrapper
# (pre-P1-repair this section proved parity between two INDEPENDENT copies;
# post-repair ``schemas._validate_submit`` delegates to ``cr`` directly, so
# these now pin the WRAPPER's call-through + error-mapping behavior instead)
# ===========================================================================


@pytest.mark.parametrize(
    "payload_factory",
    [
        _research_only_payload,
        lambda: _bounded_code_change_payload(
            allowed_write_paths=["./control_plane//b.py", "control_plane/a.py"],
            validation={
                "pytest_targets": ["tests/test_b.py", "tests/test_a.py"],
                "compileall_paths": ["control_plane"],
                "git_diff_check": True,
            },
            attempt_limit=3,
            workstream="WS:MAS-75",
        ),
    ],
)
def test_normalization_matches_the_existing_mcp_gateway_byte_for_byte(payload_factory):
    """The shared law and ``integrations.executive_mcp.schemas`` must agree.

    MAS-75 PR-A P1 repair: ``schemas._validate_submit`` is now a pure
    DELEGATING WRAPPER over ``cr.normalize_high_level_request`` — this is no
    longer a parity check between two independently-arrived-at
    implementations, it is a DELEGATION-WIRING check: it proves the wrapper
    still calls through and returns the shared law's own normalized dict
    unchanged for the same accepted MCP-shaped input (the compatibility
    property adjudication §15 requires, now satisfied by construction rather
    than by two copies happening to agree).
    """

    payload = payload_factory()
    mcp_normalized = schemas._validate_submit(payload)
    shared_normalized = cr.normalize_high_level_request(payload)
    assert mcp_normalized == shared_normalized


# ===========================================================================
# import-boundary law (adjudication §3, §4.4)
# ===========================================================================


def test_module_imports_no_integrations_or_sdk_surface():
    """``control_plane.ceo_request`` must not import the MCP gateway package or
    any Slack/MCP SDK (grep receipt duplicated here as a durable regression)."""

    import control_plane.ceo_request as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if re.match(r"^\s*(import|from)\s", line)
    ]
    for line in import_lines:
        assert "integrations" not in line, line
        assert "slack_sdk" not in line, line
        assert not re.match(r"^(import|from)\s+mcp\b", line), line


# ===========================================================================
# MAJOR 3, kills M3 — refusal-parity corpus across §4.2's exact boundaries
# ===========================================================================
#
# Pre-P1-repair, this pinned two PHYSICAL copies (the shared
# ``control_plane.ceo_request`` law and the MCP gateway's own independently
# re-implemented ``schemas._validate_submit``) together on the refusal
# surface. Post-repair, ``schemas._validate_submit`` is a wrapper that calls
# straight into ``cr.normalize_high_level_request`` and maps the error type —
# so this corpus now proves the WRAPPER's mapping is complete (every one of
# these §4.2 refusal boundaries, exercised directly against the canonical
# law, also refuses through the wrapper with ``invalid_input`` and the
# translated-if-needed message), never that two independent copies happen to
# agree.

_REFUSAL_CASES = [
    (
        "operation_key_leading_space",
        _research_only_payload,
        {"operation_key": " options-chain-browser-closure-001"},
    ),
    (
        "operation_key_trailing_space",
        _research_only_payload,
        {"operation_key": "options-chain-browser-closure-001 "},
    ),
    (
        "operation_key_uppercase",
        _research_only_payload,
        {"operation_key": "Options-Chain-Browser-Closure-001"},
    ),
    ("operation_key_too_long", _research_only_payload, {"operation_key": "a" * 97}),
    ("objective_empty_after_strip", _research_only_payload, {"objective": "   \n\t  "}),
    (
        "objective_exceeds_max_by_one",
        _research_only_payload,
        {"objective": "a" * 4001},
    ),
    (
        "objective_control_char",
        _research_only_payload,
        {"objective": "objective with \x07 control char"},
    ),
    (
        "objective_surrogate",
        _research_only_payload,
        {"objective": "objective with \ud800 surrogate"},
    ),
    (
        "department_uppercase",
        _research_only_payload,
        {"department": "Executive-Infrastructure"},
    ),
    (
        "unknown_execution_profile",
        _research_only_payload,
        {"execution_profile": "deploy_everything"},
    ),
    ("priority_below_min", _research_only_payload, {"priority": -101}),
    ("priority_above_max_by_one", _research_only_payload, {"priority": 101}),
    ("attempt_limit_zero", _research_only_payload, {"attempt_limit": 0}),
    ("attempt_limit_four", _research_only_payload, {"attempt_limit": 4}),
    ("attempt_limit_bool", _research_only_payload, {"attempt_limit": True}),
    ("unknown_field", _research_only_payload, {"totally_unknown_field_xyz": 1}),
    (
        "research_only_with_write_paths",
        _research_only_payload,
        {"allowed_write_paths": ["control_plane/thing.py"]},
    ),
    (
        "bounded_code_change_without_validation",
        _bounded_code_change_payload,
        {"validation": {}},
    ),
    (
        "absolute_write_path",
        _bounded_code_change_payload,
        {"allowed_write_paths": ["/etc/passwd"]},
    ),
    (
        "dotdot_write_path",
        _bounded_code_change_payload,
        {"allowed_write_paths": ["../escape.py"]},
    ),
    (
        "tilde_write_path",
        _bounded_code_change_payload,
        {"allowed_write_paths": ["~/home/path.py"]},
    ),
]


@pytest.mark.parametrize(
    "base_factory,overrides",
    [(case[1], case[2]) for case in _REFUSAL_CASES],
    ids=[case[0] for case in _REFUSAL_CASES],
)
def test_refusal_parity_corpus_both_copies_refuse_identically(base_factory, overrides):
    """MAJOR 3, kills M3 — every §4.2 refusal boundary refuses on BOTH the
    shared law directly (``CeoRequestInvalid``) and through the MCP wrapper
    (``GatewayError`` with code ``invalid_input``).  Post-P1-repair the second
    call is a delegation-wiring check on ``schemas._validate_submit``, not an
    independent implementation — it still kills a real mutant: a wrapper that
    stopped delegating, or mapped ``caller_fault`` wrong, would surface here."""

    payload = base_factory(**overrides)
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)
    with pytest.raises(schemas.GatewayError) as excinfo:
        schemas._validate_submit(payload)
    assert excinfo.value.code == "invalid_input"


@pytest.mark.parametrize("value", [4000])
def test_objective_length_bound_accept_edge_is_identical_between_copies(value):
    """MAJOR 3 boundary probe — the ACCEPT side of the objective length bound
    (§4.2): the canonical law accepts, and the MCP wrapper's delegated result
    normalizes to the same dict (post-P1-repair this is delegation-wiring,
    not two copies happening to agree)."""

    payload = _research_only_payload(objective="a" * value)
    cr_normalized = cr.normalize_high_level_request(payload)
    schema_normalized = schemas._validate_submit(payload)
    assert cr_normalized == schema_normalized


def test_objective_length_bound_refuse_edge_is_identical_between_copies():
    """MAJOR 3 boundary probe — the REFUSE side, one character past the
    accept edge: the canonical law and the delegating MCP wrapper refuse
    identically."""

    payload = _research_only_payload(objective="a" * 4001)
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)
    with pytest.raises(schemas.GatewayError) as excinfo:
        schemas._validate_submit(payload)
    assert excinfo.value.code == "invalid_input"


@pytest.mark.parametrize("value", [-100, 100])
def test_priority_bound_accept_edge_is_identical_between_copies(value):
    """MAJOR 3 boundary probe — the ACCEPT side of the priority min/max bound
    (§4.2): identical between the canonical law and the delegating MCP
    wrapper."""

    payload = _research_only_payload(priority=value)
    cr_normalized = cr.normalize_high_level_request(payload)
    schema_normalized = schemas._validate_submit(payload)
    assert cr_normalized == schema_normalized


@pytest.mark.parametrize("value", [-101, 101])
def test_priority_bound_refuse_edge_is_identical_between_copies(value):
    """MAJOR 3 boundary probe — the REFUSE side, one past the priority
    min/max accept edge: the canonical law and the delegating MCP wrapper
    refuse identically."""

    payload = _research_only_payload(priority=value)
    with pytest.raises(cr.CeoRequestInvalid):
        cr.normalize_high_level_request(payload)
    with pytest.raises(schemas.GatewayError) as excinfo:
        schemas._validate_submit(payload)
    assert excinfo.value.code == "invalid_input"
