"""Mutation-kill matrix for the H1 one-cockpit receipt validator.

Each test below disables exactly one enforcement rule in-memory (by
monkeypatching the private function that implements it) and proves that a
hostile packet which the REAL validator correctly flags would instead be
mistaken for clean evidence — i.e. the corresponding test in
``test_business_sol_canary_evidence.py`` would go GREEN for the wrong
reason (a false pass) if that rule were ever silently removed. This is the
proof that each rule is load-bearing, not merely present.

Required kill set (frozen commission): omitted refresh proof,
dispatched/attempt false-green, cockpit duplication, Personal merge,
inventory drift, stale evidence, issue-precedence downgrade, secret
screening.
"""

from __future__ import annotations

from typing import Any

import pytest

from integrations.business_sol_canary import evidence as ev
from tests.test_business_sol_canary_evidence import golden_packet

EVALUATED_AT = "2026-09-02T00:05:00Z"


def _validate(packet: dict[str, Any]) -> dict[str, Any]:
    return ev.validate_receipt(packet, evaluated_at=EVALUATED_AT)


def _codes(result: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


# ---------------------------------------------------------------------------
# 1. Omitted refresh proof (Steward post-expiry read requirement)
# ---------------------------------------------------------------------------


def test_kill_omitted_refresh_proof_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["steward_census"]["post_expiry_read"] = None

    real = _validate(packet)
    assert "STEWARD_POST_EXPIRY_READ_MISSING" in _codes(real)
    assert real["verdict"] == "UNKNOWN"

    monkeypatch.setattr(ev, "_validate_steward_census", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "STEWARD_POST_EXPIRY_READ_MISSING" not in _codes(mutated)
    assert mutated["verdict"] == "PASS", (
        "disabling the Steward census check turned a missing post-expiry "
        "refresh read into a false PASS — the real check is load-bearing"
    )


# ---------------------------------------------------------------------------
# 2. Dispatched/attempt false-green (Executive admission requirement)
# ---------------------------------------------------------------------------


def test_kill_dispatched_and_attempt_false_green_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["executive_admission"]["dispatched"] = True
    packet["executive_admission"]["attempts"] = 3
    packet["executive_admission"]["latest_attempt"] = {"worker": "w1"}
    # status_readback must still line up so the mutation isolates dispatch/attempt fields
    packet["executive_admission"]["status_readback"] = {"job_id": "job-0001", "status": "QUEUED"}

    real = _validate(packet)
    real_codes = _codes(real)
    assert "EXECUTIVE_DISPATCHED_TRUE" in real_codes
    assert "EXECUTIVE_ATTEMPTS_NONZERO" in real_codes
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_validate_executive_admission", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "EXECUTIVE_DISPATCHED_TRUE" not in _codes(mutated)
    assert "EXECUTIVE_ATTEMPTS_NONZERO" not in _codes(mutated)
    assert mutated["verdict"] == "PASS", (
        "disabling the Executive admission check turned a dispatched/"
        "attempted Job into a false PASS — the real check is load-bearing"
    )


# ---------------------------------------------------------------------------
# 3. Cockpit duplication (selected-in-controls / controls-duplicated)
# ---------------------------------------------------------------------------


def test_kill_cockpit_duplication_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["cockpit_selection"]["control_refs"] = ["dup-ref", "dup-ref"]

    real = _validate(packet)
    assert "COCKPIT_CONTROLS_DUPLICATED" in _codes(real)
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_validate_cockpit_selection", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "COCKPIT_CONTROLS_DUPLICATED" not in _codes(mutated)
    assert mutated["verdict"] == "PASS", (
        "disabling the cockpit-selection check turned duplicated control "
        "cockpits into a false PASS — the real check is load-bearing"
    )


# ---------------------------------------------------------------------------
# 4. Personal merge
# ---------------------------------------------------------------------------


def test_kill_personal_merge_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["personal_cockpit"]["merged_into_business"] = True

    real = _validate(packet)
    assert "PERSONAL_MERGED_INTO_BUSINESS" in _codes(real)
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_validate_personal_cockpit", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "PERSONAL_MERGED_INTO_BUSINESS" not in _codes(mutated)
    assert mutated["verdict"] == "PASS", (
        "disabling the Personal-cockpit check turned a Personal->Business "
        "merge into a false PASS — the real check is load-bearing"
    )


# ---------------------------------------------------------------------------
# 5. Package/plugin inventory drift
# ---------------------------------------------------------------------------


def test_kill_package_inventory_drift_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["protected_baseline"]["expected_package_inventory_digest"] = "0" * 64

    real = _validate(packet)
    assert "PACKAGE_INVENTORY_DRIFT" in _codes(real)
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_validate_protected_baseline", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "PACKAGE_INVENTORY_DRIFT" not in _codes(mutated)
    assert mutated["verdict"] == "PASS", (
        "disabling the protected-baseline check turned package inventory "
        "drift into a false PASS — the real check is load-bearing"
    )


# ---------------------------------------------------------------------------
# 6. Stale evidence
# ---------------------------------------------------------------------------


def test_kill_stale_evidence_check(monkeypatch: pytest.MonkeyPatch) -> None:
    # Move the evaluation instant far past the golden packet's own receipt
    # timestamp (rather than moving the receipt itself, which would also
    # place it before its own sub-evidence timestamps and trip the
    # contradictory-clock check — a different rule this test must not
    # exercise) so only staleness is in play.
    far_future_evaluated_at = "2026-09-10T00:05:00Z"
    packet = golden_packet()

    real = ev.validate_receipt(packet, evaluated_at=far_future_evaluated_at)
    assert "TIMESTAMP_STALE" in _codes(real)
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_check_receipt_staleness", lambda *args, **kwargs: None)
    mutated = ev.validate_receipt(packet, evaluated_at=far_future_evaluated_at)
    assert "TIMESTAMP_STALE" not in _codes(mutated)
    assert mutated["verdict"] == "PASS", (
        "disabling the receipt-staleness check turned a stale receipt into "
        "a false PASS — the real check is load-bearing"
    )


# ---------------------------------------------------------------------------
# 7. Issue-precedence downgrade (verdict aggregation)
# ---------------------------------------------------------------------------


def test_kill_issue_precedence_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["executive_admission"]["dispatched"] = True  # FAIL-severity issue
    packet["receipt_id"] = "user@example.com"  # REFUSED-severity issue

    real = _validate(packet)
    assert real["verdict"] == "REFUSED", "REFUSED must outrank FAIL when both are present"

    def _wrong_precedence_prefers_fail(issues):
        if not issues:
            return "PASS"
        severities = {issue.severity for issue in issues}
        # Deliberately WRONG precedence: checks FAIL before REFUSED.
        if "FAIL" in severities:
            return "FAIL"
        if "REFUSED" in severities:
            return "REFUSED"
        if "UNKNOWN" in severities:
            return "UNKNOWN"
        return "PASS"

    monkeypatch.setattr(ev, "_aggregate_verdict", _wrong_precedence_prefers_fail)
    mutated = _validate(packet)
    assert mutated["verdict"] == "FAIL", (
        "the mutated aggregator downgraded a REFUSED-level packet to FAIL — "
        "this proves the real precedence order (REFUSED > FAIL > UNKNOWN) "
        "is load-bearing, not incidental"
    )
    assert mutated["verdict"] != real["verdict"]


# ---------------------------------------------------------------------------
# 8. Secret screening
# ---------------------------------------------------------------------------


def test_kill_secret_screening_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["generation_id"] = "user@example.com"

    real = _validate(packet)
    assert "SECRET_EMAIL_ADDRESS" in _codes(real)
    assert real["verdict"] == "REFUSED"

    monkeypatch.setattr(ev, "_scan_for_secrets", lambda *args, **kwargs: [])
    mutated = _validate(packet)
    assert "SECRET_EMAIL_ADDRESS" not in _codes(mutated)
    assert mutated["verdict"] != "REFUSED", (
        "disabling secret screening lost the REFUSED classification for a "
        "leaked email address — the real scan is load-bearing"
    )


# ---------------------------------------------------------------------------
# Extra kills beyond the required 8 — same pattern, additional coverage.
# ---------------------------------------------------------------------------


def test_kill_rollback_readback_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["rollback"]["readback_confirmed"] = False

    real = _validate(packet)
    assert "ROLLBACK_READBACK_MISSING" in _codes(real)
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_validate_rollback", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "ROLLBACK_READBACK_MISSING" not in _codes(mutated)
    assert mutated["verdict"] == "PASS"


def test_kill_evidence_source_provenance_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provenance substitution is checked inline in ``validate_receipt``; a
    packet claiming ``ci_green`` provenance must never PASS. We isolate the
    rule by asserting the REAL behavior directly (there is no separate
    private function to patch — the guard IS the inline check), and prove
    it is necessary by constructing the counterfactual explicitly."""

    packet = golden_packet()
    packet["evidence_source_provenance"] = "ci_green"
    real = _validate(packet)
    assert real["verdict"] == "REFUSED"
    assert "EVIDENCE_SOURCE_NOT_LIVE_RECEIPT" in _codes(real)

    # Counterfactual: had the module treated any declared provenance as
    # equivalent to "live_receipt", this packet — which is otherwise fully
    # compliant — would PASS. Confirm the *only* difference between this
    # packet and a clean PASS is the provenance field, so the check is
    # proven necessary and sufficient for the REFUSED verdict.
    packet["evidence_source_provenance"] = "live_receipt"
    corrected = _validate(packet)
    assert corrected["verdict"] == "PASS"


def test_kill_correction_lineage_check(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = golden_packet()
    packet["is_correction"] = True
    packet["correction"] = None

    real = _validate(packet)
    assert "CORRECTION_LINEAGE_MISSING" in _codes(real)
    assert real["verdict"] == "FAIL"

    monkeypatch.setattr(ev, "_validate_correction", lambda *args, **kwargs: None)
    mutated = _validate(packet)
    assert "CORRECTION_LINEAGE_MISSING" not in _codes(mutated)
    assert mutated["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# Kill-matrix summary (documents the mapping enforced above).
# ---------------------------------------------------------------------------

KILL_MATRIX = {
    "omitted refresh proof": "test_kill_omitted_refresh_proof_check",
    "dispatched/attempt false-green": "test_kill_dispatched_and_attempt_false_green_check",
    "cockpit duplication": "test_kill_cockpit_duplication_check",
    "Personal merge": "test_kill_personal_merge_check",
    "inventory drift": "test_kill_package_inventory_drift_check",
    "stale evidence": "test_kill_stale_evidence_check",
    "issue-precedence downgrade": "test_kill_issue_precedence_downgrade",
    "secret screening": "test_kill_secret_screening_check",
}


def test_kill_matrix_is_complete() -> None:
    """Documents (and pins) that every mandatory kill from the commission
    has a corresponding test function defined in this module."""

    import sys

    module = sys.modules[__name__]
    for rule, test_name in KILL_MATRIX.items():
        assert hasattr(module, test_name), f"missing mutation-kill test for: {rule}"
