from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / (
    "docs/superpowers/plans/"
    "2026-09-01-sol-capability-fabric-package-generation-convergence-index.md"
)
IDENTITY = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-identity-amendment.md"
)
VERTICAL = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-cap-s1-vertical-amendment.md"
)
PROTOCOL = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-cap-s1-protocol-attestation-amendment.md"
)
CORRECTION = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-content-digest-correction.md"
)
DESIGN = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-generation-design.md"
)
PLAN = ROOT / (
    "docs/superpowers/plans/"
    "2026-09-01-sol-capability-fabric-package-generation.md"
)
DEFAULT_POLICY = ROOT / "config/executive_agent_capabilities.json"
ROUTES = ROOT / "config/executive_worker_routes.json"
AUTONOMY = ROOT / "control_plane/executive_autonomy.py"

CORRECT_PACKAGE_DIGEST = (
    "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"
)
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


def test_index_is_the_mandatory_first_read_and_names_complete_precedence() -> None:
    index = _read(INDEX)

    assert "mandatory first read" in index
    ordered = [
        INDEX.name,
        PROTOCOL.name,
        VERTICAL.name,
        IDENTITY.name,
        CORRECTION.name,
        DESIGN.name,
        PLAN.name,
    ]
    positions = [index.index(name) for name in ordered]
    assert positions == sorted(positions)
    assert "Current protected Skillpack and universal source laws outrank this list" in index
    assert "superseded clause is not an alternate implementation choice" in index


def test_final_ruling_is_machine_readable_and_complete() -> None:
    index = _read(INDEX)
    block = _marked_block(
        index,
        "<!-- SCF_PKG_FINAL_RULING_BEGIN -->",
        "<!-- SCF_PKG_FINAL_RULING_END -->",
    )
    ruling = json.loads(_fenced_body(block, "json"))

    assert ruling == {
        "records_wave": "SCF-PKG0",
        "records_state_after_merge": (
            "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED"
        ),
        "first_implementation_wave": "CAP-S1",
        "standalone_parser_release_allowed": False,
        "implementation_pr_count": 1,
        "default_policy_schema_during_canary": (
            "mastermind.executive_agent_capabilities/v3"
        ),
        "canary_policy_schema": "mastermind.executive_agent_capabilities/v4",
        "source_package_namespace": "capability_packages",
        "runtime_plugin_namespace_state": "reserved-empty",
        "raw_profile_skill_identity_field": "skill_capabilities",
        "resolved_profile_runtime_name_field": "skills",
        "package_content_digest": CORRECT_PACKAGE_DIGEST,
        "digest_graph": "acyclic",
        "provider": "codex-app-server",
        "provider_process_required": True,
        "real_model_turn_required": True,
        "provider_neutral_materializer_required": False,
        "provider_neutral_materializer_owner": "HF1",
        "source_origin_modes": [
            "INSTALLED_RELEASE",
            "VERIFIED_EPHEMERAL_GIT_ARCHIVE",
        ],
        "provider_visible_root_kind": "ATTEMPT_LOCAL_VERIFIED_PROJECTION",
        "canonical_v4_canary_fixture": (
            "scripts/ohf/fixtures/"
            "executive_agent_capabilities_v4_mastermind_operator.json"
        ),
        "required_skill_names": EXPECTED_SKILLS,
        "checked_in_default_policy_migration_wave": "CAP-PROMOTE1",
        "general_route_added_in_cap_s1": False,
        "production_armed_in_cap_s1": False,
    }


def test_supersession_ledger_resolves_every_known_conflict() -> None:
    index = _read(INDEX)

    for old, final in (
        ("Package-content digest `a82a274a...`", CORRECT_PACKAGE_DIGEST),
        ("Package generation and Skill grant mutually bind", "Rejected circular graph"),
        ("Root `plugins` stores source-package generations", "`capability_packages`"),
        ("Raw V4 `profiles.<id>.skills`", "`skill_capabilities`"),
        ("`EffectiveSkillGrant.package_grant_digest`", "`package_source_digest`"),
        ("`SCF-PKG1` may merge as a parser-only PR", "Rejected"),
        ("CAP-S1 migrates checked-in default policy", "CAP-PROMOTE1"),
        ("Canonical fixture under `tests/fixtures/...`", "scripts/ohf/fixtures"),
        ("Provider consumes an installed release/archive root directly", "attempt-local"),
        ("`skills/list` must always return exact path", "Mode B"),
        ("Fake App Server `path` proves production protocol", "False"),
        ("`$name` alone proves source identity", "False"),
        ("Read-only canary may use `lab_allow_unclassified_readonly`", "Rejected"),
        ("Source verifier needs only file-level final `fstat`", "complete-tree"),
        ("Valid JSON may contain duplicate object keys", "Rejected"),
    ):
        assert old in index
        row = index[index.index(old) : index.index(old) + 700]
        assert final in row


def test_source_chain_is_one_origin_projection_provider_and_cleanup_path() -> None:
    index = _read(INDEX)
    block = _marked_block(
        index,
        "<!-- SCF_PKG_SOURCE_CHAIN_BEGIN -->",
        "<!-- SCF_PKG_SOURCE_CHAIN_END -->",
    )
    chain = [item.strip() for item in _fenced_body(block, "text").split("->")]

    assert chain == [
        "protected BSC-P1 package generation",
        "exact source origin (installed release OR verified ephemeral Git archive)",
        "descriptor-relative source verification",
        "byte-identical attempt-local package projection inside synthetic workspace",
        "projection verification + receipt",
        "extra root = <projection>/skills",
        "exact path-bearing Skill input = <projection>/skills/<name>/SKILL.md",
        "provider observation + causal baseline/add/clear proof",
        "composite ObservedCapabilityIdentity",
        "Executive/OHF comparison",
        "bounded real model behavior",
        "process/artifact/projection cleanup",
    ]
    assert "contains all seven package files" in index
    assert "../../references/dialogue-boundary.md" in index
    assert "not a durable package/install record" in index


def test_final_scope_has_one_fixture_and_preserves_production_no_edit_surfaces() -> None:
    index = _read(INDEX)
    canonical_fixture = (
        "scripts/ohf/fixtures/"
        "executive_agent_capabilities_v4_mastermind_operator.json"
    )

    assert canonical_fixture in index
    assert "tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json" not in index

    for path in (
        "control_plane/executive_capability_packages.py",
        "control_plane/executive_agent_capabilities.py",
        "control_plane/operator_harness_contract.py",
        "control_plane/codex_operator_adapter.py",
        "scripts/ohf/protocol.py",
        "scripts/ohf/capability_skill_projection.py",
        "scripts/ohf/cap_s1_mastermind_operator_canary.py",
        canonical_fixture,
        "scripts/ohf/fake_app_server.py",
        "tests/test_executive_capability_packages.py",
        "tests/test_executive_agent_capabilities_v4.py",
        "tests/test_cap_s1_mastermind_operator_canary.py",
    ):
        assert path in index

    for protected in (
        "config/executive_agent_capabilities.json",
        "config/executive_worker_routes.json",
        "control_plane/executive_autonomy.py",
        "scripts/executive_os_phase1c_worker.py",
        "ops/executive_os/install.sh",
        "plugins/mastermind-operator/**",
        "RemoteCodexOperatorAdapter/common worker-wire files",
    ):
        assert protected in index


def test_final_internal_order_has_real_consumer_proof_before_release() -> None:
    index = _read(INDEX)

    ordered_markers = [
        "1. **Path/owner/collision freeze.**",
        "2. **RED package tests.**",
        "3. **Package source implementation.**",
        "4. **RED V3/V4 registry tests.**",
        "5. **Registry implementation.**",
        "6. **RED comparator duplicate tests.**",
        "7. **Comparator correction.**",
        "8. **RED protocol tests.**",
        "9. **Projection and adapter implementation.**",
        "10. **Fake-server integration.**",
        "11. **Canary runner.**",
        "12. **Local/mutation/security gate.**",
        "13. **Exactly one real provider canary.**",
        "14. **Exact-head hosted proof and independent review.**",
        "15. **Expected-head release.**",
    ]
    positions = [index.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)
    assert "Internal phases do not create separate acceptance boundaries" in index


def test_default_policy_and_existing_runtime_bindings_remain_unchanged() -> None:
    policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    joined = ROUTES.read_text(encoding="utf-8") + AUTONOMY.read_text(encoding="utf-8")
    index = _read(INDEX)

    assert policy["schema_version"] == "mastermind.executive_agent_capabilities/v3"
    assert policy["plugins"] == {}
    assert "capability_packages" not in policy
    assert "mastermind-operator.p1" not in joined
    assert "general_route_added_in_cap_s1" in index
    assert '"general_route_added_in_cap_s1": false' in index
    assert '"production_armed_in_cap_s1": false' in index


def test_route_stop_and_records_release_boundaries_are_explicit() -> None:
    index = _read(INDEX)

    for marker in (
        "PREFERRED_AVENUE: CTO Sol",
        "WHY NOT FABLE",
        "RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE",
        "PLACEMENT_STATE: WAITING_CAPACITY / needs_placement",
        "No worker-facing commission, ACK, START, watcher or Git carrier exists for CAP-S1",
        "SCF-PKG0 = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED",
        "It does not implement V4",
    ):
        assert marker in index

    for stop in (
        "PACKAGE_GENERATION_OWNER_UNRESOLVED",
        "CAP_S1_SCOPE_COLLISION",
        "CAP_S1_STRUCTURED_INPUT_SCOPE_COLLISION",
        "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
        "SKILL_PATH_ATTESTATION_UNAVAILABLE",
        "AMBIENT_SKILL_SURFACE_NOT_EMPTY",
        "SKILL_SET_CAUSALITY_FAILED",
        "SKILLS_CHANGED_DURING_CANARY",
        "EFFECT_UNKNOWN",
        "PROVIDER_REALM_UNAVAILABLE",
        "CURRENT_SOURCE_MOVED",
        "ACTIVE_WRITER_COLLISION",
    ):
        assert stop in index
