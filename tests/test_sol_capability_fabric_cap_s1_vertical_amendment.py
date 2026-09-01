from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-cap-s1-vertical-amendment.md"
)
IDENTITY_AMENDMENT = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-identity-amendment.md"
)
PARENT = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-agent-operator-capability-convergence-owner-amendment.md"
)
DEFAULT_POLICY = ROOT / "config/executive_agent_capabilities.json"
INSTALLER = ROOT / "ops/executive_os/install.sh"
PACKAGE_ROOT = ROOT / "plugins/mastermind-operator"


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


def test_amendment_restores_the_protected_complete_vertical_law() -> None:
    amendment = _read(AMENDMENT)
    parent = _read(PARENT)

    _assert_prose(
        parent,
        "first PR should still deliver the complete useful vertical",
        "rather than merging an unused digest library alone",
    )
    _assert_prose(
        amendment,
        "There is no independently releasable parser-only SCF-PKG1",
        "internal implementation phase inside one CAP-S1 carrier",
        "infrastructure replacing product",
        "supplements and, where it conflicts, supersedes",
        IDENTITY_AMENDMENT.name,
    )


def test_machine_readable_sequence_has_no_standalone_parser_release() -> None:
    amendment = _read(AMENDMENT)
    block = _marked_block(
        amendment,
        "<!-- SCF_CAP_S1_SEQUENCE_BEGIN -->",
        "<!-- SCF_CAP_S1_SEQUENCE_END -->",
    )
    sequence = [item.strip() for item in _fenced_body(block, "text").split("->")]

    assert sequence == ["SCF-PKG0", "CAP-S1", "CAP-PROMOTE1"]
    assert "SCF-PKG1" not in sequence
    _assert_prose(
        amendment,
        "independently releasable parser-only SCF-PKG1",
        "Internal commits and test phases",
    )


def test_vertical_contract_requires_one_real_read_only_codex_consumer() -> None:
    amendment = _read(AMENDMENT)
    block = _marked_block(
        amendment,
        "<!-- SCF_CAP_S1_VERTICAL_BEGIN -->",
        "<!-- SCF_CAP_S1_VERTICAL_END -->",
    )
    contract = json.loads(_fenced_body(block, "json"))

    assert contract == {
        "operation": "CAP-S1",
        "parent": "SCF-PKG0",
        "independent_implementation_prs": 1,
        "provider": "codex-app-server",
        "real_provider_required": True,
        "real_model_turn_required": True,
        "write_capable": False,
        "production_armed": False,
        "default_policy_migrated": False,
        "general_model_route_added": False,
        "skills": [
            "escalate-decision",
            "finish-operation",
            "receive-commission",
            "return-progress",
        ],
        "terminal_capability_state": "BUILT_NOT_PROVEN",
        "isolated_canary_state_when_all_proof_passes": "PROVEN_LIVE",
    }

    _assert_prose(
        amendment,
        "real isolated read-only Codex App Server attempt",
        "A fake App Server may prove protocol mechanics but cannot satisfy",
        "receive -> progress -> decision/escalation -> finish/result",
        "Exactly one real provider canary",
        "EFFECT_UNKNOWN",
        "do not blind-retry",
    )


def test_cap_s1_keeps_default_policy_routes_and_host_receipts_unchanged() -> None:
    amendment = _read(AMENDMENT)
    default_policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))

    assert default_policy["schema_version"] == "mastermind.executive_agent_capabilities/v3"
    assert default_policy["plugins"] == {}
    assert "capability_packages" not in default_policy

    _assert_prose(
        amendment,
        "config/executive_agent_capabilities.json",
        "config/executive_worker_routes.json",
        "control_plane/executive_autonomy.py expected digests",
        "installed Executive configs or host receipts",
        "CAP-S1 uses one explicit immutable V4 canary policy",
        "CAP-PROMOTE1 may migrate the checked-in default policy only after CAP-S1",
        "must not rewrite or auto-refresh historical installed receipts",
    )


def test_existing_installer_already_places_the_package_in_exact_release_closure() -> None:
    amendment = _read(AMENDMENT)
    installer = _read(INSTALLER)

    for source_file in (
        ".codex-plugin/plugin.json",
        "references/app-bindings.template.json",
        "references/dialogue-boundary.md",
        "skills/escalate-decision/SKILL.md",
        "skills/finish-operation/SKILL.md",
        "skills/receive-commission/SKILL.md",
        "skills/return-progress/SKILL.md",
    ):
        assert (PACKAGE_ROOT / source_file).is_file()

    assert '/usr/bin/git -C "$SOURCE_REPO" archive --format=tar "$EXPECTED_SHA"' in installer
    assert '/usr/sbin/chown -R root:wheel "$STAGING"' in installer
    assert '/bin/chmod -R go-w "$STAGING"' in installer
    assert '/bin/chmod 0755 "$STAGING"' in installer

    _assert_prose(
        amendment,
        "full `git archive` of one accepted Mastermind commit",
        "control and worker service UIDs can read and traverse it",
        "is already part of the canonical exact-release source closure",
        "must not point Codex at a mutable provider home",
    )


def test_vertical_includes_real_producer_consumer_comparator_and_cleanup() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "control_plane/executive_capability_packages.py",
        "control_plane/executive_agent_capabilities.py",
        "control_plane/operator_harness_contract.py",
        "control_plane/codex_operator_adapter.py",
        "scripts/ohf/protocol.py",
        "scripts/ohf/cap_s1_mastermind_operator_canary.py",
        "scripts/ohf/capability_skill_projection.py",
        "tests/test_cap_s1_mastermind_operator_canary.py",
        "exact requested-vs-observed comparator decision",
        "process/resource/artifact cleanup",
        "first work turn allowed only on exact match",
        "same required name observed more than once",
        "extra unclassified custom Skill",
        "Skill resolved outside the one staged root",
        "first turn attempted before LaunchDecision.ALLOW",
    )


def test_no_rebuild_and_stop_boundaries_remain_explicit() -> None:
    amendment = _read(AMENDMENT)

    _assert_prose(
        amendment,
        "not the provider-neutral materializer owned by HF1",
        "must not introduce a generic package installer",
        "add a general Model Router route",
        "Do not migrate default policy",
        "begin non-Codex parity on the same carrier",
        "PREFERRED_AVENUE: CTO Sol",
        "WHY NOT FABLE",
        "PLACEMENT_STATE: WAITING_CAPACITY / needs_placement",
        "No worker-facing commission is emitted until a concrete eligible receiver",
        "package/registry/adapter source BUILT_NOT_PROVEN",
        "exact isolated Codex four-Skill canary path PROVEN_LIVE",
        "checked-in default V4 policy NOT_BUILT",
        "provider-neutral materializer SPEC_ONLY / HF1-GATED",
    )
