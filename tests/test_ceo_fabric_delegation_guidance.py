"""Protect explicit-assignment, paid-Fabric-first CEO guidance.

Source contract only: not proof of a local Codex skill installation or a
production worker START/return/acceptance.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_assignment_fence_is_explicit_and_unique():
    assert GUIDE.count("### Assigned Codex/Claude Meta-CEO: paid Fabric delegation first") == 1
    assert "Only a currently assigned principal or AI CEO" in GUIDE
    assert "ordinary Claude/Codex worker remains bounded" in GUIDE


def test_paid_worker_path_does_not_duplicate_broker_or_retry_planes():
    for token in (
        "WEB_CEO_DELEGATION.md",
        "fabric_task.py",
        "mastermind-fabric-delegate",
        "CODEX_THREAD_ID",
        "EFFECT_UNKNOWN",
        "original carrier",
        "provider/host controls",
    ):
        assert token in GUIDE
    assert "No separate broker, new queue, raw SSH" in GUIDE


def test_principal_judgment_and_real_adoption_proof_remain_distinct():
    for token in (
        "C0/C1/C2 implementation",
        "hard C3 architectural judgment",
        "compact",
        "source hashes",
        "full logs remain",
        "fresh assigned Codex principal",
        "paid Fabric START",
        "same-root identity",
    ):
        assert token in GUIDE
