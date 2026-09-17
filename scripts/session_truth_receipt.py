#!/usr/bin/env python3
"""Stable read-only CLI for the deterministic Session Truth Receipt.

The CLI composes existing R1 acquisition, normalization, validation, finding,
admission and rendering contracts. It owns no network client, persistence,
retry/failover, projection, lifecycle, queue, identity inference, or source
mutation behavior.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import TextIO

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.session_truth import build_receipt, render_receipt  # noqa: E402
from control_plane.session_truth_acquire import (  # noqa: E402
    AcquisitionError,
    collect_agentos,
    collect_skillpack,
)
from control_plane.session_truth_contract import (  # noqa: E402
    INPUT_SCHEMA,
    SessionTruthContractError,
    canonical_json,
)
from control_plane.session_truth_snapshots import (  # noqa: E402
    EXECUTIVE_SCHEMA,
    GITHUB_SCHEMA,
    IDENTITY_SCHEMA,
    LINEAR_SCHEMA,
    SLACK_SCHEMA,
    load_snapshot,
    normalize_executive,
    normalize_github,
    normalize_identities,
    normalize_linear,
    normalize_slack,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build one deterministic read-only Session Truth Receipt."
    )
    parser.add_argument("--workstream", action="append", required=True)
    parser.add_argument("--repository", action="append", required=True)
    parser.add_argument("--linear", action="append", default=[])
    parser.add_argument("--operation-key")
    parser.add_argument("--requires-executive", action="store_true")
    parser.add_argument("--github-snapshot", required=True)
    parser.add_argument("--linear-snapshot", required=True)
    parser.add_argument("--slack-snapshot", required=True)
    parser.add_argument("--executive-snapshot", required=True)
    parser.add_argument("--identity-snapshot", required=True)
    parser.add_argument("--macro-root")
    parser.add_argument("--protected-skillpack-sha", required=True)
    parser.add_argument("--now")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser


def _utc_now_z() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normal_snapshot(path: str, schema: str, normalizer):
    return normalizer(load_snapshot(path, schema))


def _error(stream: TextIO, message: str) -> int:
    safe = " ".join(message.replace("\r", " ").replace("\n", " ").split())
    safe = safe[:220] or "session truth input rejected"
    stream.write(f"session-truth error: {safe}\n")
    return 2


def main(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    root = _ROOT if repo_root is None else Path(repo_root)
    env = os.environ if environ is None else environ
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr

    observed_started_at = args.now or _utc_now_z()
    try:
        skillpack = collect_skillpack(
            root,
            protected_sha=args.protected_skillpack_sha,
            bootstrap_major=1,
        )
        agentos = collect_agentos(
            args.macro_root,
            args.workstream,
            environ=env,
            now=args.now,
        )
        github = _normal_snapshot(
            args.github_snapshot,
            GITHUB_SCHEMA,
            normalize_github,
        )
        linear = _normal_snapshot(
            args.linear_snapshot,
            LINEAR_SCHEMA,
            normalize_linear,
        )
        slack = _normal_snapshot(
            args.slack_snapshot,
            SLACK_SCHEMA,
            normalize_slack,
        )
        executive = _normal_snapshot(
            args.executive_snapshot,
            EXECUTIVE_SCHEMA,
            normalize_executive,
        )
        identities = _normal_snapshot(
            args.identity_snapshot,
            IDENTITY_SCHEMA,
            normalize_identities,
        )
        inputs = {
            "schema": INPUT_SCHEMA,
            "scope": {
                "workstreams": list(args.workstream),
                "linear": list(args.linear),
                "repositories": list(args.repository),
                "operation_key": args.operation_key,
                "requires_executive": bool(args.requires_executive),
            },
            "skillpack": skillpack,
            "agentos": agentos,
            "github": github,
            "linear": linear,
            "slack": slack,
            "executive": executive,
            "identities": identities,
        }
        observed_ended_at = args.now or _utc_now_z()
        receipt = build_receipt(
            inputs,
            observed_started_at=observed_started_at,
            observed_ended_at=observed_ended_at,
        )
    except AcquisitionError:
        return _error(err, "canonical acquisition failed")
    except SessionTruthContractError:
        return _error(err, "invalid session truth input")

    try:
        rendered = (
            canonical_json(receipt) + "\n"
            if args.emit_json
            else render_receipt(receipt)
        )
    except SessionTruthContractError:
        return _error(err, "invalid session truth output")
    out.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
