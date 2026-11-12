"""Produce one real ``mastermind.quota_economics_preview/v1`` artifact (WO-09).

Thin, explicit-argument wrapper around the genuine runtime producer in
``control_plane.quota_economics_preview_producer``. Defaults are derived from
the WO-03 projection's own recorded owner paths (the same incumbent owner
namespace pinned at ``control_plane/paid_fabric_backend.py:125``); nothing is
invented. The deployed broker database is only ever opened read-only.

Exit codes: 0 on success, 2 on any refused input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.executive_capacity_observation_producer import (
    validate_worker_capacity_source_config,
)
from control_plane.quota_economics_preview_producer import (
    PREVIEW_LIFETIME_SECONDS,
    QuotaEconomicsPreviewError,
    produce_quota_economics_preview,
)

BROKER_RELEASE_SOURCE = (
    ROOT / "ops/native_fabric/quota_continuity/source/lease_broker.py"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _owner_paths(projection_path: Path) -> tuple[Path, Path]:
    """Read the broker/pools paths recorded by the WO-03 projection itself."""
    document = json.loads(projection_path.read_bytes())
    owner = document.get("source_owner_ref")
    if not isinstance(owner, dict):
        raise SystemExit("2")
    leases = (owner.get("leases_sqlite") or {}).get("path")
    pools = (owner.get("pools_yaml") or {}).get("path")
    if not isinstance(leases, str) or not isinstance(pools, str):
        raise SystemExit("2")
    return Path(leases), Path(pools)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--broker", default=None)
    parser.add_argument("--pools-yaml", default=None)
    parser.add_argument("--observed-at", default=None)
    args = parser.parse_args(argv)

    projection_path = Path(args.projection)
    output_path = Path(args.output)
    try:
        broker_default, pools_default = _owner_paths(projection_path)
    except (OSError, ValueError):
        print("QUOTA_PREVIEW_PROJECTION_UNAVAILABLE", file=sys.stderr)
        return 2
    broker_path = Path(args.broker) if args.broker else broker_default
    pools_path = Path(args.pools_yaml) if args.pools_yaml else pools_default
    observed_at = args.observed_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # Real source identity through the existing trusted factory: every digest
    # is computed from real bytes on this machine; none are invented.
    connection = sqlite3.connect(f"file:{broker_path}?mode=ro", uri=True)
    try:
        generation = int(
            connection.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
        )
    finally:
        connection.close()
    config = validate_worker_capacity_source_config(
        {
            "schema_version": (
                "mastermind.executive_worker_capacity_source_config/v1"
            ),
            "host_ref": "host-"
            + hashlib.sha256(platform.node().encode()).hexdigest(),
            "capacity_capability_id": "quota_economics_preview",
            "broker_release_identity_digest": _sha256_file(BROKER_RELEASE_SOURCE),
            "broker_operation_identity_digest": _sha256_file(broker_path),
            "broker_generation": generation,
            "executive_peer_policy_digest": _sha256_file(projection_path),
            "worker_realm_metadata_policy_digest": _sha256_file(pools_path),
            "provider_binary_identity_digest": _sha256_file(
                Path(sys.executable).resolve()
            ),
        }
    )

    try:
        preview = produce_quota_economics_preview(
            source_config=config,
            projection_path=projection_path,
            broker_db_path=broker_path,
            observed_at=observed_at,
        )
    except QuotaEconomicsPreviewError as error:
        print(error.code, file=sys.stderr)
        return 2

    document = preview.to_dict()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = document["knowledge_summary"]
    print(f"schema={document['schema']}")
    print(f"status={document['status']}")
    print(f"preview_id={document['preview_id']}")
    print(f"expires_at={document['expires_at']} (lifetime={PREVIEW_LIFETIME_SECONDS}s)")
    print(f"suggested_option={document['suggested_option']}")
    print(
        "observed_vs_unknown="
        f"{summary['quota_observed']} observed / {summary['quota_unknown']} unknown"
    )
    print(f"resources={summary['resources_total']} options={len(document['options'])}")
    print(f"artifact={output_path}")
    print(f"artifact_sha256={_sha256_file(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
