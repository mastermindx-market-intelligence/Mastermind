from __future__ import annotations

import asyncio
import copy
import dataclasses

import pytest

from control_plane.session_truth import build_receipt
from control_plane.session_truth_live_acquire import (
    LiveAcquisitionError,
    LiveOwnerPorts,
    LiveScope,
    acquire_live_session_truth_inputs,
)
from control_plane.session_truth_snapshots import (
    EXECUTIVE_SCHEMA,
    GITHUB_SCHEMA,
    IDENTITY_SCHEMA,
    LINEAR_SCHEMA,
    SLACK_SCHEMA,
)

NOW = "2026-10-04T00:00:00Z"
MASTER = "mastermindx-market-intelligence/Mastermind"


def _scope(**overrides):
    values = dict(
        workstreams=("WS:CTX",),
        linear=(),
        repositories=(MASTER,),
        operation_key="op-context",
        requires_executive=True,
    )
    values.update(overrides)
    return LiveScope(**values)


def _pr(*, number=1, workstream="WS:CTX", linear="MAS-10", operation_key="op-context"):
    return {
        "repository": MASTER,
        "number": number,
        "state": "open",
        "draft": True,
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "merge_sha": None,
        "ci": "pending",
        "workstream": workstream,
        "linear": linear,
        "portfolio_mode": "implementation",
        "wave": "R1",
        "authority": "implementation",
        "completion": "merge-is-done",
        "proof_state": "open",
        "operation_key": operation_key,
        "pickup_head_sha": "a" * 40,
    }


def _github(rows=None):
    return {
        "schema": GITHUB_SCHEMA,
        "available": True,
        "observed_at": NOW,
        "pull_requests": list(rows or []),
    }


def _linear(ids=()):
    return {
        "schema": LINEAR_SCHEMA,
        "available": True,
        "observed_at": NOW,
        "issues": [
            {
                "id": item,
                "status": "In Progress",
                "parent_id": None,
                "workstream": "WS:CTX",
                "completion": "implementation",
                "projection_revision": index,
                "github_relations": [],
                "updated_at": NOW,
            }
            for index, item in enumerate(ids, start=1)
        ],
    }


def _slack():
    return {
        "schema": SLACK_SCHEMA,
        "available": True,
        "observed_at": NOW,
        "channels": [],
        "messages": [],
    }


def _executive():
    return {
        "schema": EXECUTIVE_SCHEMA,
        "available": True,
        "observed_at": NOW,
        "fresh": True,
        "do_not_submit": False,
        "grounding_sha": "c" * 40,
        "operations": [],
    }


def _identities():
    return {
        "schema": IDENTITY_SCHEMA,
        "available": True,
        "observed_at": NOW,
        "bindings": [],
    }


def _base():
    return {
        "skillpack": {
            "repository": MASTER,
            "sha": "c" * 40,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.1",
            "minimum_bootstrap_major": 1,
            "available": True,
        },
        "agentos": {
            "available": True,
            "source_sha": "d" * 40,
            "state": {
                "schema": "agent_os_state.v1",
                "generated_at": NOW,
                "source_records_digest": "sha256:" + "1" * 64,
                "workstreams": [],
                "warnings": [],
            },
            "contexts": [],
            "warnings": [],
        },
    }


class Ports:
    def __init__(self, github_rows=None):
        self.calls = []
        self.github_rows = list(github_rows or [])
        self.downstream_scopes = []

    async def base(self, scope):
        self.calls.append("base")
        return _base()

    async def github(self, scope):
        self.calls.append("github")
        return _github(self.github_rows)

    async def linear(self, scope):
        self.calls.append("linear")
        self.downstream_scopes.append(("linear", scope))
        return _linear(scope.linear)

    async def slack(self, scope):
        self.calls.append("slack")
        self.downstream_scopes.append(("slack", scope))
        return _slack()

    async def executive(self, scope):
        self.calls.append("executive")
        self.downstream_scopes.append(("executive", scope))
        return _executive()

    async def identities(self, scope):
        self.calls.append("identities")
        self.downstream_scopes.append(("identities", scope))
        return _identities()

    def bundle(self):
        return LiveOwnerPorts(
            base=self.base,
            github=self.github,
            linear=self.linear,
            slack=self.slack,
            executive=self.executive,
            identities=self.identities,
        )


def test_scoped_pr_linear_edge_is_added_before_downstream_reads():
    ports = Ports([_pr(linear="MAS-10")])
    result = asyncio.run(
        acquire_live_session_truth_inputs(scope=_scope(), ports=ports.bundle())
    )
    assert result["scope"]["linear"] == []
    assert [issue["id"] for issue in result["linear"]["issues"]] == ["MAS-10"]
    for _, observed_scope in ports.downstream_scopes:
        assert observed_scope.linear == ("MAS-10",)


def test_unrelated_pr_does_not_expand_linear_scope():
    ports = Ports(
        [
            _pr(
                number=2,
                workstream="WS:OTHER",
                linear="MAS-99",
                operation_key="op-other",
            )
        ]
    )
    result = asyncio.run(
        acquire_live_session_truth_inputs(scope=_scope(), ports=ports.bundle())
    )
    assert result["scope"]["linear"] == []
    for _, observed_scope in ports.downstream_scopes:
        assert observed_scope.linear == ()


def test_explicit_linear_seed_survives_without_pr_binding():
    ports = Ports([])
    result = asyncio.run(
        acquire_live_session_truth_inputs(
            scope=_scope(linear=("MAS-20",)),
            ports=ports.bundle(),
        )
    )
    assert result["scope"]["linear"] == ["MAS-20"]


def test_operation_key_can_bind_pr_linear_edge_without_workstream_match():
    ports = Ports(
        [
            _pr(
                number=3,
                workstream="WS:OTHER",
                linear="MAS-30",
                operation_key="op-context",
            )
        ]
    )
    result = asyncio.run(
        acquire_live_session_truth_inputs(scope=_scope(), ports=ports.bundle())
    )
    assert result["scope"]["linear"] == []
    assert [issue["id"] for issue in result["linear"]["issues"]] == ["MAS-30"]


def test_owner_failure_is_typed_and_does_not_become_empty_state():
    ports = Ports([])

    async def fail(_scope):
        raise RuntimeError("provider detail must not escape")

    bundle = dataclasses.replace(ports.bundle(), slack=fail)
    with pytest.raises(LiveAcquisitionError, match="slack owner read failed") as caught:
        asyncio.run(acquire_live_session_truth_inputs(scope=_scope(), ports=bundle))
    assert "provider detail" not in str(caught.value)


def test_secret_bearing_owner_document_is_refused_by_existing_normalizer():
    ports = Ports([])
    original = ports.github

    async def secret(scope):
        value = await original(scope)
        value["token"] = "do-not-accept"
        return value

    bundle = dataclasses.replace(ports.bundle(), github=secret)
    with pytest.raises(
        LiveAcquisitionError, match="GitHub observation normalization failed"
    ):
        asyncio.run(acquire_live_session_truth_inputs(scope=_scope(), ports=bundle))


def test_base_shape_is_closed():
    ports = Ports([])

    async def bad_base(_scope):
        value = _base()
        value["extra"] = {}
        return value

    bundle = dataclasses.replace(ports.bundle(), base=bad_base)
    with pytest.raises(LiveAcquisitionError, match="base owner read shape"):
        asyncio.run(acquire_live_session_truth_inputs(scope=_scope(), ports=bundle))


def test_scope_input_is_not_mutated():
    scope = _scope(linear=("MAS-20",))
    before = copy.deepcopy(scope)
    ports = Ports([_pr(linear="MAS-10")])
    asyncio.run(acquire_live_session_truth_inputs(scope=scope, ports=ports.bundle()))
    assert scope == before


def test_live_scope_rejects_duplicate_or_malformed_identities():
    with pytest.raises(LiveAcquisitionError):
        _scope(workstreams=("WS:CTX", "WS:CTX"))
    with pytest.raises(LiveAcquisitionError):
        _scope(repositories=("not-a-repo",))


def test_exact_port_bundle_is_required():
    ports = Ports([])
    with pytest.raises(LiveAcquisitionError, match="exact"):
        asyncio.run(
            acquire_live_session_truth_inputs(
                scope=_scope(),
                ports=object(),  # type: ignore[arg-type]
            )
        )


def test_live_inputs_feed_existing_session_truth_receipt_without_snapshot_files():
    ports = Ports([_pr(linear="MAS-10")])
    inputs = asyncio.run(
        acquire_live_session_truth_inputs(scope=_scope(), ports=ports.bundle())
    )
    receipt = build_receipt(
        inputs,
        observed_started_at=NOW,
        observed_ended_at=NOW,
    )
    assert receipt["schema"] == "mastermind.session_truth_receipt.v1"
    assert receipt["scope"]["linear"] == []
    assert receipt["observations"]["linear"]["issues"][0]["id"] == "MAS-10"
