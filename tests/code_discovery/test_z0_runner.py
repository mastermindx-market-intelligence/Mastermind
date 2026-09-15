"""Deterministic artifact tests for the production-inert Z0 host runner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from experiments.code_discovery.discovery_contract import RepositoryIndexStatus
from experiments.code_discovery.z0_runner import (
    RESULT_SCHEMA_VERSION,
    ZOEKT_REQUIRES_ARCHITECTURE_REVISION,
    build_result_payload,
    choose_decision,
    write_result_artifacts,
)


def _status(health: str = "healthy") -> RepositoryIndexStatus:
    observed = datetime(2026, 8, 30, 12, tzinfo=UTC)
    return RepositoryIndexStatus(
        repository_id="mastermind",
        ref_label="master",
        indexed_commit_sha="a" * 40,
        source_tree_digest="b" * 64,
        shard_namespace="z0-mastermind",
        health=health,
        coverage="covered",
        generated_at=observed,
        observed_at=observed,
        freshness_seconds=1.0,
    )


def test_result_payload_binds_exact_inputs_and_refuses_unmeasured_acceptance(
    tmp_path: Path,
) -> None:
    """A green local index alone cannot produce a CI3 acceptance decision."""

    status = _status()
    decision = choose_decision((status,), benchmarks_complete=False)
    assert decision == ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    payload = build_result_payload(
        decision=decision,
        generated_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
        request_digest="1" * 64,
        toolchain_lock_sha256="2" * 64,
        bundle_sha256="3" * 64,
        bundle_manifest_sha256="4" * 64,
        manifest_digest="c" * 64,
        path_policy_digest="d" * 64,
        tool_schema_digest="e" * 64,
        zoekt_source_commit="5f833dde1bc4b1a8f99007617b4b721e44506c4f",
        indexer_sha256="f" * 64,
        webserver_sha256="0" * 64,
        statuses=(status,),
        resource_observations={"benchmarks_complete": False},
    )
    result_path = tmp_path / "z0-result.json"
    report_path = tmp_path / "z0-report.md"
    write_result_artifacts(payload, result_path=result_path, report_path=report_path)

    assert json.loads(result_path.read_text()) == payload
    assert payload["schema_version"] == RESULT_SCHEMA_VERSION
    assert payload["request_digest"] == "1" * 64
    assert payload["toolchain_lock_sha256"] == "2" * 64
    assert payload["bundle_sha256"] == "3" * 64
    assert payload["bundle_manifest_sha256"] == "4" * 64
    assert report_path.read_bytes() == (
        "# Z0 Global Discovery Falsifier Result\n\n"
        "Decision: ZOEKT_REQUIRES_ARCHITECTURE_REVISION\n\n"
        "Generated at: 2026-08-30T12:00:00+00:00\n\n"
        f"Request digest: {'1' * 64}\n\n"
        f"Toolchain lock SHA-256: {'2' * 64}\n\n"
        f"Bundle SHA-256: {'3' * 64}\n\n"
        f"Bundle manifest SHA-256: {'4' * 64}\n\n"
        "## Repository/ref status\n\n"
        f"- mastermind/master: health=healthy; coverage=covered; indexed_sha={'a' * 40}\n\n"
        "This is a disposable production-inert experiment result. It does not "
        "provision a persistent service, capability profile, credential, MCP "
        "endpoint, CI3 grant, or deployment.\n"
    ).encode("utf-8")


@pytest.mark.parametrize(
    "field",
    (
        "request_digest",
        "toolchain_lock_sha256",
        "bundle_sha256",
        "bundle_manifest_sha256",
    ),
)
def test_result_payload_rejects_malformed_host_identity(field: str) -> None:
    """A malformed host identity cannot enter the immutable result pair."""

    identities = {
        "request_digest": "1" * 64,
        "toolchain_lock_sha256": "2" * 64,
        "bundle_sha256": "3" * 64,
        "bundle_manifest_sha256": "4" * 64,
    }
    identities[field] = "A" * 64

    with pytest.raises(ValueError, match=field):
        build_result_payload(
            decision=ZOEKT_REQUIRES_ARCHITECTURE_REVISION,
            generated_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
            **identities,
            manifest_digest="c" * 64,
            path_policy_digest="d" * 64,
            tool_schema_digest="e" * 64,
            zoekt_source_commit="5f833dde1bc4b1a8f99007617b4b721e44506c4f",
            indexer_sha256="f" * 64,
            webserver_sha256="0" * 64,
            statuses=(_status(),),
            resource_observations={"benchmarks_complete": False},
        )


def test_corrupt_or_unavailable_status_selects_no_safe_global_index() -> None:
    """The decision surface has no optimistic fallback for a falsified health row."""

    assert choose_decision((_status("corrupt"),), benchmarks_complete=True) == (
        "NO_SAFE_GLOBAL_INDEX"
    )
