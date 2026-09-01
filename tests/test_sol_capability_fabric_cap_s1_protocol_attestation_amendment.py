from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-cap-s1-protocol-attestation-amendment.md"
)
VERTICAL = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-cap-s1-vertical-amendment.md"
)
PROTECTED_SKILL_SET = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-agent-operator-skill-set-exposure-amendment.md"
)
DEFAULT_POLICY = ROOT / "config/executive_agent_capabilities.json"

EXPECTED_SKILLS = [
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress",
]


def _read(path: Path) -> str:
    payload = path.read_bytes()
    assert payload
    assert payload.endswith(b"\n")
    assert b"\x00" not in payload
    return payload.decode("utf-8")


def _prose(value: str) -> str:
    return " ".join(value.split())


def _assert_prose(value: str, *markers: str) -> None:
    normalized = _prose(value)
    for marker in markers:
        assert _prose(marker) in normalized


def _marked_block(text: str, begin: str, end: str) -> str:
    _before, marker, remainder = text.partition(begin)
    assert marker
    body, marker, _after = remainder.partition(end)
    assert marker
    return body.strip()


def _fenced_body(block: str, language: str) -> str:
    opener = f"```{language}\n"
    assert block.startswith(opener)
    assert block.endswith("```")
    return block[len(opener) : -3].strip()


def test_amendment_narrowly_repairs_the_provider_reported_path_assumption() -> None:
    amendment = _read(AMENDMENT)
    protected = _read(PROTECTED_SKILL_SET)

    _assert_prose(protected, "exact provider-reported path")
    _assert_prose(
        amendment,
        "supplements and, where it conflicts, supersedes only",
        PROTECTED_SKILL_SET.name,
        VERTICAL.name,
        "A fake server's convenient `path` field cannot become production protocol truth",
        "absence of `path`",
        "no model turn is allowed",
    )


def test_machine_protocol_strategy_requires_path_evidence_without_name_only_fallback() -> None:
    amendment = _read(AMENDMENT)
    block = _marked_block(
        amendment,
        "<!-- SCF_CAP_S1_PROTOCOL_STRATEGY_BEGIN -->",
        "<!-- SCF_CAP_S1_PROTOCOL_STRATEGY_END -->",
    )
    strategy = json.loads(_fenced_body(block, "json"))

    assert strategy["schema_authority"] == "exact_pinned_codex_binary_generated"
    assert strategy["skills_list"] == {
        "force_reload": True,
        "provider_path_present": "require_exact_expected_skill_directory",
        "provider_path_absent": (
            "require_fresh_process_causal_isolation_and_explicit_skill_input_path"
        ),
    }
    assert strategy["fresh_process_baseline_enabled_skills"] == []
    assert strategy["after_exact_extra_root_enabled_skills"] == EXPECTED_SKILLS
    assert strategy["after_extra_root_clear_enabled_skills"] == []
    assert strategy["explicit_skill_input"] == {
        "required": True,
        "name_required": True,
        "absolute_skill_md_path_required": True,
        "name_only_fallback_allowed": False,
    }
    assert strategy["skills_changed_notification"] == (
        "invalidate_attestation_and_abort_acceptance"
    )
    assert strategy["unclassified_policy"] == "fail_closed_on_write"
    assert strategy["laboratory_unclassified_allowance"] is False
    assert strategy["unsupported_path_result"] == "SKILL_PATH_ATTESTATION_UNAVAILABLE"


def test_exact_binary_generated_schema_is_the_action_time_protocol_authority() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "codex app-server generate-json-schema --out <sealed-temp-dir>",
        "with `--experimental`",
        "exact generated schema",
        "same binary",
        "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
        "current official OpenAI App Server documentation as corroborating discovery",
        "fake App Server only as a protocol test double",
        "future `main` branch feature",
        "does not silently depend",
    )


def test_causal_sequence_proves_empty_add_four_clear_empty_before_cleanup() -> None:
    amendment = _read(AMENDMENT)
    block = _marked_block(
        amendment,
        "<!-- SCF_CAP_S1_CAUSAL_SEQUENCE_BEGIN -->",
        "<!-- SCF_CAP_S1_CAUSAL_SEQUENCE_END -->",
    )
    sequence = [item.strip() for item in _fenced_body(block, "text").split("->")]

    assert sequence == [
        "fresh process",
        "skills/extraRoots/set []",
        "skills/list forceReload=true == enabled set {}",
        "verify exact package source snapshot",
        "skills/extraRoots/set [<exact package root>/skills]",
        "skills/list forceReload=true == enabled set {four exact Operator Skills}",
        "construct four composite ObservedCapabilityIdentity rows",
        "compare requested vs observed == ALLOW",
        "thread/start",
        "four exact path-bound Skill turns with pre/post source checks",
        "skills/extraRoots/set []",
        "skills/list forceReload=true == enabled set {}",
        "terminate process and prove cleanup",
    ]
    _assert_prose(
        amendment,
        "AMBIENT_SKILL_SURFACE_NOT_EMPTY",
        "SKILL_SET_CAUSALITY_FAILED",
        "does not whitelist remembered",
    )


def test_source_modes_are_exact_release_or_exact_ephemeral_git_archive_only() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "INSTALLED_RELEASE",
        "VERIFIED_EPHEMERAL_GIT_ARCHIVE",
        "dirty candidate worktree's package bytes",
        "network-fetch a package",
        "<exact package root>/skills/<exact runtime name>/SKILL.md",
        "all seven file rows",
    )


def test_pathless_mode_uses_composite_provenance_not_fake_provider_precision() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "exact provider evidence supplies the enabled name set",
        "deterministic Mastermind verification supplies package source/generation",
        "fresh empty baseline plus one server-owned extra root",
        "client supplies the exact `SKILL.md` path",
        "type=skill",
        "each turn's text contains the same `$<name>` marker",
        "never accepted as the source binding by itself",
        "skill_content_digest=<closure>",
        "preserve the provenance of each field",
        "SKILL_PATH_ATTESTATION_UNAVAILABLE",
        "$name` fallback",
        "lower identity precision is allowed",
    )


def test_structured_skill_input_is_codex_closed_and_preserves_ordinary_turns() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "class CodexSkillTurnInput",
        "class CodexTurnInputEnvelope",
        "existing plain-string loaders remain valid",
        "one exact resolved V4 canary profile",
        "adapter derives the final absolute path",
        "wire input is one text item followed by one exact `skill` item",
        "current worker production composition",
        "RemoteCodexOperatorAdapter",
        "remain unchanged",
        "CAP_S1_STRUCTURED_INPUT_SCOPE_COLLISION",
        "without changing the provider-neutral `OperatorHarnessAdapter`",
        "no raw path enters Executive Job constraints",
    )


def test_v4_canary_adds_bundled_skill_disable_without_changing_v3() -> None:
    amendment = _read(AMENDMENT)
    policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))

    assert policy["schema_version"] == "mastermind.executive_agent_capabilities/v3"
    assert "capability_packages" not in policy
    _assert_prose(
        amendment,
        "skills.bundled.enabled=false",
        "V4 canary profile's security config projection and digest",
        "Valid V3 profiles and current V3 config/profile/policy digests remain",
    )


def test_skills_changed_and_source_movement_invalidate_without_blind_retry() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "immediately before every path-bound turn",
        "immediately after every turn",
        "forceReload=true",
        "Any `skills/changed` notification",
        "invalidates the launch attestation",
        "SKILLS_CHANGED_DURING_CANARY",
        "Do not rerun the same canary operation automatically",
        "never repaired by recomputing a new requested profile",
    )


def test_real_model_journey_invokes_each_exact_skill_with_path_item() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "turn 1: receive-commission",
        "turn 2: return-progress",
        "turn 3: escalate-decision",
        "turn 4: finish-operation",
        '{"type": "skill", "name": "<exact-name>", "path":',
        "pickup ACK is separated from START",
        "progress does not claim completion",
        "decision boundary is escalated",
        "RESULT does not claim Sol acceptance or STOP",
        "model output proves usefulness only",
    )


def test_fake_server_and_acceptance_falsifiers_cannot_lower_production_contract() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "skills/list rows with exact path",
        "skills/list rows without path",
        "same-name duplicates rather than deduplicating",
        "malformed/missing enabled state",
        "explicit path-bearing Skill input capture",
        "A fake-only pass is never terminal proof",
        "removing baseline-empty enforcement fails",
        "allowing `lab_allow_unclassified_readonly` fails",
        "accepting `$name` without a Skill input item fails",
        "omitting exact-binary schema generation fails",
        "allowing a second implementation PR for parser-only infrastructure fails",
    )

    for failure in (
        "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
        "SKILL_PROTOCOL_RUNTIME_SHAPE_MISMATCH",
        "AMBIENT_SKILL_SURFACE_NOT_EMPTY",
        "SKILL_SET_CAUSALITY_FAILED",
        "SKILL_PATH_ATTESTATION_UNAVAILABLE",
        "SKILL_INPUT_PATH_MISMATCH",
        "SKILL_SOURCE_CHANGED",
        "SKILLS_CHANGED_DURING_CANARY",
        "SKILL_INVOCATION_UNSUPPORTED",
        "CAP_S1_STRUCTURED_INPUT_SCOPE_COLLISION",
    ):
        assert failure in amendment
