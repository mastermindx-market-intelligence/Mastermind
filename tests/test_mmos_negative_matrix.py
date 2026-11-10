"""MMOS V1 negative-case matrix (T3_HANDOFF_V2 §6) — Director H free rows.

Adversarial tests at the exact mutation boundary for the §6 failure rows whose
boundary modules are NOT owned by a concurrent director lane.  Rows whose
boundary lives in an owned path (t3_execution_adapter, executive_runtime /
worker_adapter / #2329 guard, dsh_acp_runtime, *.tsx renderers, hermes-native
TS mirror) are recorded as written hand-off designs in
``integrations/mmos/NEGATIVE_MATRIX_V1.md`` and ``.../LANE_NEGATIVE_MATRIX_DIRECTOR_H.md``.

Rows proven here (with the §6 failure case they kill):

* NM-13 stale lease: an expired-but-held lease blocks NEW execution while only
  the exact writer (correct epoch) may retire it; expiry alone is never
  reclaim-safety.  Boundary: ``WorkspaceLeaseStore.acquire_single_writer`` /
  ``release`` / ``reclaim_eligible``.
* NM-06 gateway stopped: a stopped-gateway error code classifies as a
  distinct ``gateway_stopped`` label (never busy/disconnected/effect-unknown)
  and offers only read/status continuations — the gateway's owner starts it,
  never an auto-restart/remake from here.  Boundary:
  ``hermes_native_continuity.classify_error_code``.
* NM-09 provider 429: a rate-limited quota readback must become a typed
  unknown with probe evidence — never observed numbers, never a silent retry
  against another endpoint/account.  Boundary:
  ``provider_quota_observation.observe_provider`` status dispatch.
* NM-16 green-but-unmerged: CI-green on an OPEN unmerged PR must never read
  as integrated/closable; integration knowledge enters only through the
  explicit ``integration_state`` fact.  Boundary:
  ``github_pr_lifecycle.assess_pr_lifecycle``.
"""
from __future__ import annotations

import dataclasses

import pytest

from control_plane import provider_quota_observation
from control_plane.github_pr_lifecycle import (
    EffectState,
    ExplicitDisposition,
    IntegrationState,
    LifecycleIssue,
    LifecycleVerdict,
    PreservationState,
    PullRequestLifecycleFacts,
    PullRequestState,
    SourceCoverage,
    WorkState,
    assess_pr_lifecycle,
)
from control_plane.workspace_lease import (
    RETENTION_DIRTY_RETAINED,
    WorkspaceLeaseConflict,
    WorkspaceLeaseStore,
    reclaim_eligible,
)
from integrations.session_bridge import hermes_native_continuity as continuity

REPO = "gh:mastermind/fabric"
HOST = "host-a"
NOW = 1_700_000_000_000
REV = "a" * 40


def _acquire(store, *, writer_ref, workspace_ref, now_ms, expires_ms=None):
    return store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
        workspace_ref=workspace_ref, base_revision=REV, writer_ref=writer_ref,
        now_ms=now_ms, expires_ms=expires_ms)


# ---------------------------------------------------------------------------
# NM-13 — stale lease blocks NEW execution; only the exact writer may retire it
# ---------------------------------------------------------------------------


def test_nm13_stale_lease_blocks_new_execution_and_only_the_exact_writer_retires(tmp_path):
    store = WorkspaceLeaseStore(str(tmp_path / "nm13-stale.sqlite"))
    held = _acquire(store, writer_ref="worker-alpha", workspace_ref="ws-run-1",
                    now_ms=NOW, expires_ms=NOW + 1_000)
    later = NOW + 60_000  # the lease expired while still held

    # (1) expiry alone does NOT reopen the checkout: new execution is refused
    #     with the holder's exact identity, and the stale lease is preserved.
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        _acquire(store, writer_ref="worker-beta", workspace_ref="ws-run-2", now_ms=later)
    conflict = caught.value
    assert conflict.reason == "SINGLE_WRITER_ALREADY_HELD"
    assert conflict.details["writer_ref"] == "worker-alpha"
    assert conflict.details["writer_epoch"] == 1
    assert store.read(held.lease_id).lease_status == "active"

    # (2) a wrong epoch (anyone but the exact writer) cannot retire it.
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        store.release(held.lease_id, writer_epoch=99, now_ms=later + 1)
    assert caught.value.reason == "STALE_WRITER_RELEASE"
    assert store.read(held.lease_id).lease_status == "active"

    # (3) the exact writer may still retire its own run — the exact-run
    #     cancel analog — even though the lease had expired.
    released = store.release(held.lease_id, writer_epoch=1, now_ms=later + 2,
                             retention_state=RETENTION_DIRTY_RETAINED)
    assert released.lease_status == "released"
    assert released.retention_state == RETENTION_DIRTY_RETAINED

    # (4) only after that exact-writer retirement does new execution proceed.
    fresh = _acquire(store, writer_ref="worker-beta", workspace_ref="ws-run-2",
                     now_ms=later + 3)
    assert fresh.lease_status == "active"
    assert fresh.lease_id != held.lease_id


def test_nm13_expiry_alone_is_never_reclaim_safety_settlement_is(tmp_path):
    store = WorkspaceLeaseStore(str(tmp_path / "nm13-reclaim.sqlite"))
    held = _acquire(store, writer_ref="worker-alpha", workspace_ref="ws-run-1",
                    now_ms=NOW, expires_ms=NOW + 1_000)
    later = NOW + 60_000

    def blocked_by():
        decision = reclaim_eligible(store.reclaim_view(now_ms=later), now_ms=later)
        eligible = [e["workspace_ref"] for e in decision["eligible"]]
        row = next(e for e in decision["ineligible"] if e["workspace_ref"] == "ws-run-1")
        return eligible, row["blocked_by"]

    # (1) expired while still held: the live writer alone blocks reclamation —
    #     expiry never establishes safety.
    eligible, blockers = blocked_by()
    assert eligible == []
    assert "live_writer_present" in blockers

    # (2) exact-writer release with retained dirty output, activity not yet
    #     settled: still not reclaim-safe, refusal names the exact blocker.
    store.release(held.lease_id, writer_epoch=1, now_ms=later,
                  retention_state=RETENTION_DIRTY_RETAINED)
    eligible, blockers = blocked_by()
    assert eligible == []
    assert "native_activity_not_settled" in blockers

    # (3) explicit activity settlement — and nothing weaker — flips it.
    store.record_native_activity_settled(held.lease_id, now_ms=later + 1)
    decision = reclaim_eligible(store.reclaim_view(now_ms=later + 2), now_ms=later + 2)
    assert [entry["workspace_ref"] for entry in decision["eligible"]] == ["ws-run-1"]


# ---------------------------------------------------------------------------
# NM-06 — gateway stopped: distinct typed label; no mutation offered
# ---------------------------------------------------------------------------


def test_nm06_stopped_code_is_typed_gateway_stopped_and_offers_no_mutation():
    stopped = continuity.classify_error_code("NATIVE_GATEWAY_STOPPED")
    # A stopped gateway is a stopped gateway: typed gateway_stopped, never
    # idle/healthy, never collapsed into an honest-unknown blob.
    assert stopped["state"] == continuity.GATEWAY_STOPPED
    assert stopped["reason"] == "gateway_not_running"
    # No mutation is offered — in particular no fresh send and no
    # auto-retry/restart/remake of the gateway.
    assert continuity.fresh_send_allowed(stopped) is False
    continuations = continuity.permitted_continuations(stopped)
    assert [c["operation"] for c in continuations] == ["status"]
    assert all(c["idempotent"] for c in continuations)


def test_nm06_gateway_stopped_needs_a_label_distinct_from_busy_and_disconnected():
    stopped = continuity.classify_error_code("NATIVE_GATEWAY_STOPPED")
    assert stopped["state"] not in (
        continuity.GATEWAY_BUSY,
        continuity.VIEWER_DISCONNECTED,
        continuity.UNCLASSIFIED,
    )


# ---------------------------------------------------------------------------
# NM-09 — provider 429: typed unknown, probe evidence, no numbers, no fallback
# ---------------------------------------------------------------------------


def test_nm09_rate_limited_429_is_typed_unknown_never_healthy_numbers(monkeypatch):
    seen: list[dict] = []

    def fake_fetch(url, *, credential, auth_kind, timeout_s):
        seen.append({"url": url, "credential": credential, "auth_kind": auth_kind})
        # A rate-limited response whose body *advertises* healthy numbers.
        return 429, b'{"remaining_percent": 99.9, "reset_at": "2099-01-01T00:00:00Z"}', {}

    monkeypatch.setattr(provider_quota_observation, "_fetch", fake_fetch)
    observation = provider_quota_observation.observe_provider(
        "ocfree", "account-primary", "tok-live-1")

    # Typed unknown: no observed numbers anywhere, no provenance claim.
    assert observation.observed is False
    assert observation.usage is None
    assert observation.usage_unit is None
    assert observation.limit is None
    assert observation.limit_unit is None
    assert observation.reset_at is None
    assert observation.cooldown_until is None
    assert observation.provenance is None
    assert observation.reason_code == "NOT_EXPOSED"  # closed vocabulary today

    # The refused observation keeps its evidence and the exact account:
    # never silently re-pointed at another account, never retried elsewhere.
    assert observation.account == "account-primary"
    assert observation.shared_quota_resource_ref == "ocfree:account-primary"
    assert observation.details["probes"] == [
        {"endpoint": "opencode.ai/zen/v1/usage", "status": 429}
    ]
    assert len(seen) == 1
    assert seen[0]["credential"] == "tok-live-1"


# ---------------------------------------------------------------------------
# NM-16 — CI green but unmerged/uninstalled must not read as integrated
# ---------------------------------------------------------------------------


def _facts(**overrides):
    base = dict(
        repository="owner/repo", number=7, state=PullRequestState.OPEN,
        merged=False, draft=False, work_state=WorkState.NONE,
        explicit_disposition=ExplicitDisposition.NONE,
        integration_state=IntegrationState.NOT_INTEGRATED,
        preservation_state=PreservationState.PRESERVED,
        source_coverage=SourceCoverage.COMPLETE,
        prior_effect_state=EffectState.NONE,
    )
    base.update(overrides)
    return PullRequestLifecycleFacts(**base)


def test_nm16_green_but_unmerged_never_reports_integrated_or_closable():
    # CI is green, the PR is OPEN and unmerged: green alone must not read as
    # shipped.  The verdict is reconcile, never close, and the delta is named.
    assessment = assess_pr_lifecycle(_facts())
    assert assessment.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert assessment.verdict is not LifecycleVerdict.CLOSE_CANDIDATE
    assert LifecycleIssue.UNIQUE_OR_UNINTEGRATED_DELTA in assessment.issues

    # Unverified integration is its own distinct reconcile reason.
    unknown = assess_pr_lifecycle(_facts(integration_state=IntegrationState.UNKNOWN))
    assert unknown.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert LifecycleIssue.INTEGRATION_STATE_UNKNOWN in unknown.issues

    # The facts grammar cannot even express CI greenness: integration
    # knowledge enters only through the explicit integration_state fact.
    names = {field.name for field in dataclasses.fields(PullRequestLifecycleFacts)}
    assert not {"ci", "ci_green", "checks", "check_status", "status"} & names

    # The one legitimate terminal path stays reachable: exact integration
    # plus proven preservation, still only ever a *candidate* verdict.
    integrated = assess_pr_lifecycle(
        _facts(integration_state=IntegrationState.EXACTLY_INTEGRATED))
    assert integrated.verdict is LifecycleVerdict.CLOSE_CANDIDATE
    assert LifecycleIssue.CURRENT_DELTA_ALREADY_INTEGRATED in integrated.issues
