"""Host-only production-inert result emitter for the Z0 falsifier."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .discovery_contract import RepositoryIndexStatus, discovery_tool_schema_digest
from .index_manifest import (
    IndexManifest,
    load_index_manifest,
    material_source_manifest_digest,
)
from .processes import ExecutableSpec, ZOEKT_SOURCE_COMMIT, ZoektProcessSet


RESULT_SCHEMA_VERSION: Final = "mastermind.codeintel_z0_result.v1"
ZOEKT_FACADE_ACCEPTED_FOR_CI3: Final = "ZOEKT_FACADE_ACCEPTED_FOR_CI3"
ZOEKT_REQUIRES_ARCHITECTURE_REVISION: Final = "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"
NO_SAFE_GLOBAL_INDEX: Final = "NO_SAFE_GLOBAL_INDEX"
_DECISIONS: Final = frozenset(
    {
        ZOEKT_FACADE_ACCEPTED_FOR_CI3,
        ZOEKT_REQUIRES_ARCHITECTURE_REVISION,
        NO_SAFE_GLOBAL_INDEX,
    }
)


def choose_decision(
    statuses: Sequence[RepositoryIndexStatus], *, benchmarks_complete: bool
) -> str:
    """Refuse optimistic acceptance from an index alone."""

    if not statuses or any(
        status.health != "healthy" or status.coverage != "covered" for status in statuses
    ):
        return NO_SAFE_GLOBAL_INDEX
    if not benchmarks_complete:
        return ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    return ZOEKT_FACADE_ACCEPTED_FOR_CI3


def build_result_payload(
    *,
    decision: str,
    generated_at: datetime,
    manifest_digest: str,
    path_policy_digest: str,
    tool_schema_digest: str,
    zoekt_source_commit: str,
    indexer_sha256: str,
    webserver_sha256: str,
    statuses: Sequence[RepositoryIndexStatus],
    resource_observations: Mapping[str, object],
) -> dict[str, object]:
    """Build a stable JSON-serializable evidence record."""

    if decision not in _DECISIONS:
        raise ValueError("unknown Z0 decision")
    for label, digest in (
        ("manifest_digest", manifest_digest),
        ("path_policy_digest", path_policy_digest),
        ("tool_schema_digest", tool_schema_digest),
        ("indexer_sha256", indexer_sha256),
        ("webserver_sha256", webserver_sha256),
    ):
        _require_sha256(label, digest)
    if zoekt_source_commit != ZOEKT_SOURCE_COMMIT:
        raise ValueError("result must name the exact pinned Zoekt source commit")
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "decision": decision,
        "generated_at": generated_at.astimezone(UTC).isoformat(),
        "manifest_digest": manifest_digest,
        "path_policy_digest": path_policy_digest,
        "tool_schema_digest": tool_schema_digest,
        "zoekt_source_commit": zoekt_source_commit,
        "binary_digests": {
            "zoekt_git_index": indexer_sha256,
            "zoekt_webserver": webserver_sha256,
        },
        "repository_statuses": [
            _status_payload(status)
            for status in sorted(
                statuses, key=lambda status: (status.repository_id, status.ref_label)
            )
        ],
        "resource_observations": dict(resource_observations),
    }


def write_result_artifacts(
    payload: Mapping[str, object], *, result_path: Path, report_path: Path
) -> None:
    """Write the machine and human artifacts explicitly requested by the host."""

    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise ValueError("result payload has an unexpected schema version")
    if payload.get("decision") not in _DECISIONS:
        raise ValueError("result payload has an unexpected decision")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_render_report(payload), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one disposable local composition; it never provisions a service."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--path-policy", type=Path, required=True)
    parser.add_argument("--indexer", type=Path, required=True)
    parser.add_argument("--indexer-sha256", required=True)
    parser.add_argument("--webserver", type=Path, required=True)
    parser.add_argument("--webserver-sha256", required=True)
    parser.add_argument("--shard-root", type=Path, required=True)
    parser.add_argument("--log-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--startup-timeout-seconds", type=float, default=10.0)
    arguments = parser.parse_args(argv)

    manifest = load_index_manifest(arguments.manifest)
    indexer = ExecutableSpec(
        arguments.indexer, arguments.indexer_sha256, ZOEKT_SOURCE_COMMIT
    )
    webserver = ExecutableSpec(
        arguments.webserver, arguments.webserver_sha256, ZOEKT_SOURCE_COMMIT
    )
    processes = ZoektProcessSet(
        indexer=indexer,
        webserver=webserver,
        shard_root=arguments.shard_root,
        log_root=arguments.log_root,
        startup_timeout_seconds=arguments.startup_timeout_seconds,
    )
    try:
        statuses = processes.build_indexes(manifest)
        processes.start_search()
        processes.assert_search_alive()
        payload = build_result_payload(
            decision=choose_decision(
                statuses, benchmarks_complete=False
            ),
            generated_at=datetime.now(UTC),
            manifest_digest=material_source_manifest_digest(manifest),
            path_policy_digest=_sha256_file(arguments.path_policy),
            tool_schema_digest=discovery_tool_schema_digest(),
            zoekt_source_commit=ZOEKT_SOURCE_COMMIT,
            indexer_sha256=indexer.sha256,
            webserver_sha256=webserver.sha256,
            statuses=statuses,
            resource_observations={
                "benchmarks_complete": False,
                "benchmark_gate": "separate evidenced ingestion required",
                "production_inert": True,
                "endpoint_scope": "loopback_disposable_only",
            },
        )
        write_result_artifacts(
            payload, result_path=arguments.result, report_path=arguments.report
        )
    finally:
        processes.close()
    return 0


def _status_payload(status: RepositoryIndexStatus) -> dict[str, object]:
    return {
        "repository_id": status.repository_id,
        "ref_label": status.ref_label,
        "indexed_commit_sha": status.indexed_commit_sha,
        "source_tree_digest": status.source_tree_digest,
        "shard_namespace": status.shard_namespace,
        "health": status.health,
        "coverage": status.coverage,
        "generated_at": status.generated_at.astimezone(UTC).isoformat(),
        "observed_at": status.observed_at.astimezone(UTC).isoformat(),
        "freshness_seconds": status.freshness_seconds,
    }


def _render_report(payload: Mapping[str, object]) -> str:
    statuses = payload["repository_statuses"]
    assert isinstance(statuses, list)
    rows = "\n".join(
        f"- {item['repository_id']}/{item['ref_label']}: "
        f"health={item['health']}; coverage={item['coverage']}; "
        f"indexed_sha={item['indexed_commit_sha']}"
        for item in statuses
        if isinstance(item, Mapping)
    )
    return (
        "# Z0 Global Discovery Falsifier Result\n\n"
        f"Decision: {payload['decision']}\n\n"
        f"Generated at: {payload['generated_at']}\n\n"
        "## Repository/ref status\n\n"
        f"{rows or '- none'}\n\n"
        "This is a disposable production-inert experiment result. It does not "
        "provision a persistent service, capability profile, credential, MCP "
        "endpoint, CI3 grant, or deployment.\n"
    )


def _require_sha256(label: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
