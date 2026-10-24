"""End-to-end source tests for the existing live owner ports to cockpit seam.

These are hermetic port witnesses; no owner network client or auth exists here.
They exercise the exact normalizers, deterministic receipt and source-approved
read-only cockpit, not a hand-written finding or a parallel owner registry.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.executive_cross_plane_live import acquire_live_cross_plane_view
from control_plane.session_truth_live_acquire import (
    LiveAcquisitionError,
    LiveOwnerPorts,
    LiveScope,
)
from control_plane.session_truth_snapshots import (
    EXECUTIVE_SCHEMA,
    GITHUB_SCHEMA,
    IDENTITY_SCHEMA,
    LINEAR_SCHEMA,
    SLACK_SCHEMA,
)

MASTER = "mastermindx-market-intelligence/Mastermind"
NOW = "2026-08-27T08:00:00Z"
SHA = "a" * 40
SKILLPACK_SHA = "b" * 40


def _pr(number=170, *, workstream="WS:TARGET", linear="MAS-6",
        operation_key="op-live-001"):
    return {
        "repository": MASTER, "number": number, "state": "open",
        "draft": False, "head_sha": SHA, "base_sha": SKILLPACK_SHA,
        "merge_sha": None, "ci": "success", "workstream": workstream,
        "linear": linear, "portfolio_mode": "contributes", "wave": None,
        "authority": "read-only", "completion": "BUILT_NOT_PROVEN",
        "proof_state": None, "operation_key": operation_key,
        "pickup_head_sha": None,
    }


def _base():
    return {
        "skillpack": {
            "available": True, "sha": SKILLPACK_SHA,
            "repository": MASTER, "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.1", "minimum_bootstrap_major": 1,
        },
        "agentos": {
            "available": True, "source_sha": SHA,
            "state": {
                "schema": "mastermind.agent_os_state.v1",
                "source_records_digest": "sha256:" + "1" * 64,
                "workstreams": [{
                    "key": "TARGET", "updated": "2026-08-27",
                    "projection_revision": 7,
                    "prs": [{"number": 170, "state": "open"}],
                }],
            },
            "contexts": [{
                "schema": "mastermind.agent_os_context.v1",
                "target": {"workstream": "WS:TARGET"},
                "sections": [],
                "source_records_digest": "sha256:" + "2" * 64,
            }],
        },
    }


class Owners:
    def __init__(self, *, include_orphan=False, relation=True):
        self.calls = []
        self.scopes = []
        self.include_orphan = include_orphan
        self.relation = relation

    async def base(self, scope):
        self.calls.append("base")
        return _base()

    async def github(self, scope):
        self.calls.append("github")
        prs = [_pr()]
        if self.include_orphan:
            # A self-declared orphan with the *same* operation key must not
            # create an authoritative workstream card or MAS-99 binding.
            prs.append(_pr(999, workstream="WS:BOGUS", linear="MAS-99"))
        return {
            "schema": GITHUB_SCHEMA, "available": True,
            "observed_at": NOW, "pull_requests": prs,
        }

    async def linear(self, scope):
        self.calls.append("linear")
        self.scopes.append(scope)
        issues = []
        for item in scope.linear:
            own = item == "MAS-6" and self.relation
            issues.append({
                "id": item, "status": "In Progress", "parent_id": None,
                "workstream": "WS:TARGET" if own else None,
                "completion": None,
                "projection_revision": 7 if own else None,
                "github_relations": (
                    [{"repository": MASTER, "number": 170,
                      "relation": "program_gate"}] if own else []
                ),
                "updated_at": NOW,
            })
        return {
            "schema": LINEAR_SCHEMA, "available": True,
            "observed_at": NOW, "issues": issues,
        }

    async def slack(self, scope):
        self.calls.append("slack")
        return {"schema": SLACK_SCHEMA, "available": False,
                "reason": "SLACK_SCOPED_OPERATION_NOT_READ"}

    async def executive(self, scope):
        self.calls.append("executive")
        return {"schema": EXECUTIVE_SCHEMA, "available": False,
                "reason": "EXECUTIVE_SCOPED_OPERATION_NOT_READ"}

    async def identities(self, scope):
        self.calls.append("identities")
        return {"schema": IDENTITY_SCHEMA, "available": False,
                "reason": "IDENTITIES_SCOPED_BINDINGS_NOT_READ"}

    def ports(self):
        return LiveOwnerPorts(
            base=self.base, github=self.github, linear=self.linear,
            slack=self.slack, executive=self.executive,
            identities=self.identities,
        )


def _scope():
    return LiveScope(
        workstreams=("WS:TARGET",), linear=(),
        repositories=(MASTER,), operation_key="op-live-001",
        requires_executive=False,
    )


def _render(owners, *, ports=None, stale_after_seconds=600):
    return asyncio.run(acquire_live_cross_plane_view(
        scope=_scope(), ports=owners.ports() if ports is None else ports,
        observed_started_at=NOW, observed_ended_at=NOW,
        stale_after_seconds=stale_after_seconds,
    ))


def test_injected_live_owners_render_one_exact_card_without_reacquisition():
    owners = Owners()
    doc = _render(owners)
    assert doc["schema"] == "mastermind.executive_cross_plane_view.v1"
    assert doc["capability"] == {"effect": "NONE", "read_only": True}
    assert doc["state"] == "DEGRADED"  # missing scoped execution/identity is not healthy
    assert [c["workstream"] for c in doc["cards"]] == ["WS:TARGET"]
    card = doc["cards"][0]
    assert [pr["number"] for pr in card["github"]["pull_requests"]] == [170]
    assert [i["issue_id"] for i in card["linear"]["issues"]] == ["MAS-6"]
    assert owners.calls.count("base") == owners.calls.count("github") == 1
    assert len(owners.calls) == len(set(owners.calls)) == 6
    assert owners.scopes[0].linear == ("MAS-6",)
    assert card["github"]["freshness"] == "CURRENT"


def test_missing_native_linear_link_does_not_mint_issue_ownership():
    owners = Owners(relation=False)
    doc = _render(owners)
    assert doc["capability"]["effect"] == "NONE"
    assert [c["workstream"] for c in doc["cards"]] == ["WS:TARGET"]
    assert doc["cards"][0]["linear"]["issues"] == []
    assert doc["state"] == "DEGRADED"


def test_orphan_github_self_declaration_and_operation_key_cannot_create_card():
    owners = Owners(include_orphan=True)
    doc = _render(owners)
    assert "MAS-99" in owners.scopes[0].linear
    assert [c["workstream"] for c in doc["cards"]] == ["WS:TARGET"]
    assert all(c["workstream"] != "WS:BOGUS" for c in doc["cards"])
    codes = {f["code"] for f in doc["unattributed_findings"]}
    assert "ORPHAN_GITHUB_CARRIER" in codes
    assert doc["state"] == "DEGRADED"
    assert doc["capability"]["effect"] == "NONE"


def test_source_failure_does_not_become_empty_healthy_document():
    owners = Owners()

    async def fail(_scope):
        raise RuntimeError("secret provider detail may not leak")

    ports = dataclasses.replace(owners.ports(), github=fail)
    with pytest.raises(LiveAcquisitionError, match="github owner read failed") as err:
        _render(owners, ports=ports)
    assert "secret provider detail" not in str(err.value)
    assert "linear" not in owners.calls
