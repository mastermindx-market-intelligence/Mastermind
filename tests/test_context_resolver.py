from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest

from control_plane.context_resolver import (
    CONTEXT_PACK_SCHEMA,
    ContextResolverError,
    build_context_pack,
    render_context_pack,
)
from control_plane.operating_context_projection import ContextBundleFact
from scripts import context_resolver as context_cli

MASTER = "mastermindx-market-intelligence/Mastermind"


def _receipt() -> dict:
    return {
        "schema": "mastermind.session_truth_receipt.v1",
        "semantic_hash": "9" * 64,
        "scope": {
            "workstreams": ["WS:CTX"],
            "linear": [],
            "repositories": [MASTER],
            "operation_key": "op-context",
            "requires_executive": True,
        },
        "skillpack": {
            "available": True,
            "repository": MASTER,
            "sha": "a" * 40,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.1",
            "minimum_bootstrap_major": 1,
        },
        "observations": {
            "agentos": {
                "available": True,
                "source_sha": "b" * 40,
                "state": {
                    "schema": "agent_os_state.v1",
                    "source_records_digest": "sha256:" + "c" * 64,
                    "workstreams": [],
                },
                "contexts": [
                    {
                        "schema": "context_bundle.v1",
                        "target": {"workstream": "WS:CTX"},
                        "source_records_digest": "sha256:" + "d" * 64,
                        "sections": [{"id": "current"}],
                    },
                    {
                        "schema": "context_bundle.v1",
                        "target": {"workstream": "WS:OTHER"},
                        "source_records_digest": "sha256:" + "e" * 64,
                        "sections": [{"id": "unrelated"}],
                    },
                ],
                "warnings": [],
            },
            "github": {
                "available": True,
                "observed_at": "2026-10-03T22:00:00Z",
                "pull_requests": [
                    {
                        "repository": MASTER,
                        "number": 1200,
                        "workstream": "WS:CTX",
                        "linear": "MAS-1200",
                        "operation_key": "op-context",
                        "head_sha": "1" * 40,
                        "state": "open",
                    },
                    {
                        "repository": MASTER,
                        "number": 1201,
                        "workstream": "WS:OTHER",
                        "linear": "MAS-1201",
                        "operation_key": "op-other",
                        "head_sha": "2" * 40,
                        "state": "open",
                    },
                ],
            },
            "linear": {
                "available": True,
                "observed_at": "2026-10-03T22:00:00Z",
                "issues": [
                    {
                        "id": "MAS-1200",
                        "workstream": "WS:CTX",
                        "parent_id": None,
                        "projection_revision": "projection-7",
                        "github_relations": [],
                    },
                    {
                        "id": "MAS-1201",
                        "workstream": "WS:OTHER",
                        "parent_id": None,
                        "projection_revision": "projection-other",
                        "github_relations": [],
                    },
                ],
            },
            "slack": {
                "available": True,
                "observed_at": "2026-10-03T22:00:00Z",
                "messages": [
                    {
                        "channel_id": "CCTX",
                        "ts": "100.1",
                        "operation_key": "op-context",
                        "payload_hash": "payload-context",
                    },
                    {
                        "channel_id": "COTHER",
                        "ts": "100.2",
                        "operation_key": "op-other",
                        "payload_hash": "payload-other",
                    },
                ],
            },
            "executive": {
                "available": True,
                "observed_at": "2026-10-03T22:00:00Z",
                "grounding_sha": "a" * 40,
                "operations": [
                    {
                        "operation_key": "op-context",
                        "payload_hash": "exec-context",
                        "status": "STARTED",
                    },
                    {
                        "operation_key": "op-other",
                        "payload_hash": "exec-other",
                        "status": "STARTED",
                    },
                ],
            },
            "identities": {
                "available": True,
                "observed_at": "2026-10-03T22:00:00Z",
                "bindings": [],
            },
        },
        "findings": [
            {
                "code": "BUILD_VISIBILITY_STALE",
                "severity": "WARNING",
                "canonical_owner": "github",
                "subject": "WS:CTX",
                "source_a": None,
                "source_b": None,
                "repair_owner": "slack",
                "modification_consequence": "none",
                "details": {},
            }
        ],
        "admission": {
            "mode": "GROUNDING_PARTIAL",
            "modification_safe": True,
            "required_sources_unavailable": [],
            "optional_sources_unavailable": [],
        },
    }


def _identities(pack: dict) -> set[str]:
    return {item["identity"] for item in pack["selected_items"]}


def test_exact_scope_excludes_unrelated_repository_rows():
    pack = build_context_pack(_receipt(), task="Implement context resolver")
    identities = _identities(pack)
    assert "skillpack" in identities
    assert "agentos:WS:CTX" in identities
    assert f"github-pr:{MASTER}#1200" in identities
    assert "linear:MAS-1200" in identities
    assert "executive:op-context" in identities
    assert "slack:CCTX:100.1" in identities
    assert "finding:BUILD_VISIBILITY_STALE:WS:CTX" in identities
    assert f"github-pr:{MASTER}#1201" not in identities
    assert "linear:MAS-1201" not in identities
    assert "executive:op-other" not in identities
    assert "slack:COTHER:100.2" not in identities


def test_context_pack_is_explicitly_navigation_not_authority():
    pack = build_context_pack(_receipt(), task="Recover current state")
    assert pack["schema"] == CONTEXT_PACK_SCHEMA
    assert pack["authoritative"] is False
    assert pack["derived_read_only"] is True
    assert pack["coverage"] == "complete"
    assert pack["continuation_mode"] == "FULL_RECOVERY"
    assert pack["material_change"] is False


def test_context_bundle_is_compatible_with_existing_projection_fact():
    pack = build_context_pack(_receipt(), task="Recover current state")
    bundle = pack["context_bundle"]
    fact = ContextBundleFact(
        context_bundle_id=bundle["context_bundle_id"],
        revision=bundle["revision"],
        context_digest=bundle["context_digest"],
        selected_items=tuple(bundle["selected_items"]),
        excluded=tuple(bundle["excluded"]),
        omitted_due_to_budget=tuple(bundle["omitted_due_to_budget"]),
        degraded=tuple(bundle["degraded"]),
    )
    assert fact.context_digest == bundle["context_digest"]


def test_budget_omission_is_visible_not_silently_truncated():
    pack = build_context_pack(_receipt(), task="Recover current state", max_items=2)
    assert pack["coverage"] == "partial"
    assert len(pack["selected_items"]) == 2
    assert pack["context_bundle"]["omitted_due_to_budget"]
    assert pack["selected_items"][0]["identity"] == "skillpack"


def test_changed_scoped_pr_is_a_material_invalidator():
    prior = build_context_pack(_receipt(), task="Recover current state")
    changed = _receipt()
    changed["semantic_hash"] = "8" * 64
    changed["observations"]["github"]["pull_requests"][0]["head_sha"] = "3" * 40
    current = build_context_pack(
        changed,
        task="Recover current state",
        prior_pack=prior,
    )
    codes = {(item["code"], item["identity"]) for item in current["invalidators"]}
    assert ("SELECTED_SOURCE_CHANGED", "source:github") in codes
    assert ("CONTEXT_ITEM_CHANGED", f"github-pr:{MASTER}#1200") in codes
    assert current["material_change"] is True
    assert current["continuation_mode"] == "DELTA_RECOVERY"


def test_unrelated_pr_change_does_not_restart_scope():
    prior = build_context_pack(_receipt(), task="Recover current state")
    changed = _receipt()
    changed["semantic_hash"] = "8" * 64
    changed["observations"]["github"]["pull_requests"][1]["head_sha"] = "4" * 40
    current = build_context_pack(
        changed,
        task="Recover current state",
        prior_pack=prior,
    )
    assert current["invalidators"] == []
    assert current["material_change"] is False
    assert current["context_bundle"]["revision"] == prior["context_bundle"]["revision"]
    assert (
        current["context_bundle"]["context_digest"]
        == prior["context_bundle"]["context_digest"]
    )


def test_task_change_requires_full_recovery():
    prior = build_context_pack(_receipt(), task="Recover current state")
    current = build_context_pack(
        _receipt(),
        task="Implement Project Atlas",
        prior_pack=prior,
    )
    assert current["continuation_mode"] == "FULL_RECOVERY"
    assert any(item["code"] == "TASK_CHANGED" for item in current["invalidators"])


def test_identical_inputs_are_byte_deterministic():
    left = build_context_pack(_receipt(), task="  Recover   current state ")
    right = build_context_pack(_receipt(), task="Recover current state")
    assert left == right
    assert json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def test_render_is_bounded_and_does_not_claim_execution():
    pack = build_context_pack(_receipt(), task="Recover current state")
    rendered = render_context_pack(pack)
    assert rendered.startswith("Mastermind Context Pack\n")
    assert "authoritative=true" not in rendered
    assert "executed=true" not in rendered
    assert f"github-pr:{MASTER}#1200" in rendered


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda doc: doc.update(schema="wrong"), "receipt schema"),
        (lambda doc: doc.update(semantic_hash="bad"), "semantic hash"),
        (lambda doc: doc["skillpack"].update(available=False), "Skillpack"),
    ],
)
def test_invalid_receipt_fails_closed(mutation, message):
    receipt = _receipt()
    mutation(receipt)
    with pytest.raises(ContextResolverError, match=message):
        build_context_pack(receipt, task="Recover current state")


def test_prior_pack_cannot_claim_authority():
    prior = build_context_pack(_receipt(), task="Recover current state")
    prior["authoritative"] = True
    with pytest.raises(ContextResolverError, match="authority"):
        build_context_pack(
            _receipt(),
            task="Recover current state",
            prior_pack=prior,
        )


def test_cli_emits_same_pack_as_library(tmp_path: Path):
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt()), encoding="utf-8")
    out = io.StringIO()
    err = io.StringIO()
    rc = context_cli.main(
        [
            "--receipt",
            str(receipt_path),
            "--task",
            "Recover current state",
            "--json",
        ],
        stdout=out,
        stderr=err,
    )
    assert rc == 0
    assert err.getvalue() == ""
    assert json.loads(out.getvalue()) == build_context_pack(
        _receipt(),
        task="Recover current state",
    )


def test_cli_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    out = io.StringIO()
    err = io.StringIO()
    rc = context_cli.main(
        ["--receipt", str(path), "--task", "Recover current state"],
        stdout=out,
        stderr=err,
    )
    assert rc == 2
    assert out.getvalue() == ""
    assert "valid UTF-8 JSON" in err.getvalue()


def test_build_does_not_mutate_receipt_or_prior():
    receipt = _receipt()
    before_receipt = copy.deepcopy(receipt)
    prior = build_context_pack(receipt, task="Recover current state")
    before_prior = copy.deepcopy(prior)
    build_context_pack(
        receipt,
        task="Recover current state",
        prior_pack=prior,
    )
    assert receipt == before_receipt
    assert prior == before_prior


def test_unrelated_agentos_change_does_not_restart_scope():
    prior = build_context_pack(_receipt(), task="Recover current state")
    changed = _receipt()
    changed["semantic_hash"] = "7" * 64
    changed["observations"]["agentos"]["state"]["source_records_digest"] = (
        "sha256:" + "f" * 64
    )
    changed["observations"]["agentos"]["contexts"][1]["source_records_digest"] = (
        "sha256:" + "6" * 64
    )
    current = build_context_pack(
        changed,
        task="Recover current state",
        prior_pack=prior,
    )
    assert current["invalidators"] == []
    assert current["material_change"] is False
    assert (
        current["selected_source_digests"]["agentos"]
        == prior["selected_source_digests"]["agentos"]
    )
    assert current["context_bundle"]["revision"] == prior["context_bundle"]["revision"]


def test_resolver_source_has_no_direct_io_network_or_runtime_imports():
    import ast

    source_path = Path(__file__).parents[1] / "control_plane" / "context_resolver.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    forbidden = {
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "time",
        "random",
        "app",
        "runtime",
    }
    assert imports.isdisjoint(forbidden)
