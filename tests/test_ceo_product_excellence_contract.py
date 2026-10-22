"""Source-contract tests for universal CEO delegation and product excellence.

These checks prove source/policy packaging invariants, not provider loading,
Fabric admission, actual visual quality, or real-path product acceptance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ops.executive_os import provider_orchestrator_policy as policy


ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "skills" / "mastermind-fabric-orchestration"


def _read(relative: str) -> str:
    return (ROLES / relative).read_text(encoding="utf-8")


def test_common_contract_directs_meta_ceo_quality_and_economical_execution() -> None:
    core = _read("SKILL.md")
    assert "Chairman-delegated quality steward" in core
    assert "award-caliber" in core
    assert "independent design critique" in core
    assert "accepted outcome per total root expenditure" in core
    assert "current Chairman retains final authority" in core
    assert "admitted" in core and "EFFECT_UNKNOWN" in core


def test_meta_ceo_commissions_quality_instead_of_sharing_build_backlog() -> None:
    meta = _read("references/meta-ceo.md")
    assert "Do not act as a second implementation team" in meta
    assert "product excellence brief" in meta
    assert "real responsive user paths" in meta
    assert "design-direction critique" in meta
    assert "NOT_ACCEPTED" in meta


def test_downstream_acceptance_and_economic_responsibility() -> None:
    program = _read("references/program-ceo.md")
    operator = _read("references/operator.md")
    reviewer = _read("references/reviewer.md")
    assert "design-quality obligations" in program
    assert "whole-cycle cost" in program
    assert "visual and interaction evidence" in operator
    assert "product-quality falsifiers" in operator
    assert "do not certify an award" in reviewer
    assert "responsive" in reviewer and "accessibility" in reviewer


def test_incumbent_installer_uses_exact_current_role_hashes_and_policy() -> None:
    for relative, wanted in policy.ROLE_SHA256.items():
        actual = hashlib.sha256((ROLES / relative).read_bytes()).hexdigest()
        assert wanted == actual, f"stale provider-policy role digest for {relative}"
    body = policy._managed_text("")
    assert "Chairman-delegated quality steward" in body
    assert "award-caliber" in body


def test_no_unbounded_authority_or_forced_fixed_hierarchy() -> None:
    core = _read("SKILL.md")
    assert "Omit a layer that adds only relay overhead" in core
    assert "Skills cannot grant spawning rights" in core
    assert "current Chairman retains final authority" in core
