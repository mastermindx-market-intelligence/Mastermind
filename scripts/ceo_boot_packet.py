"""Print the read-only CEO boot packet assembled from Agent OS.

The stable entrypoint for :mod:`control_plane.ceo_boot_packet` — the Phase 1D-A
bridge that lets the AI CEO seat reconstruct organizational state from canonical
stores instead of conversational memory.  Executive OS READS Agent OS: this command
never writes into the Macro checkout, never dispatches, never schedules, and never
arms anything.

The default company-wide mode ALWAYS exits 0 once the arguments parse. A missing
or stale Macro checkout is an orientation gap, not a control-plane fault.

With --workstream, an explicit --macro-root and --expected-macro-sha are required.
This entrypoint reads the existing canonical Agent OS context_bundle.v1 JSON.
Missing named context is a nonzero read failure, never a
fallback to a generic brief. This is evidence, not authority or native admission.
No memory compiler, renderer, store or execution lifecycle is added.

    python3 scripts/ceo_boot_packet.py
    python3 scripts/ceo_boot_packet.py --json
    python3 scripts/ceo_boot_packet.py --macro-root ~/Documents/Cluade/"Macro Dashboard"
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.ceo_boot_packet import (  # noqa: E402  (after sys.path bootstrap)
    DEFAULT_TIMEOUT,
    ENV_MACRO_ROOT,
    bounded_subprocess_runner,
    build_packet,
    git_sha,
    render_packet,
    resolve_macro_root,
)
from control_plane.session_truth_contract import valid_source_records_digest  # noqa: E402

# Transport ceiling, not the compiler's token budget. Never clip constraints.
_CONTEXT_MAX_BYTES = 256 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate context key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError("non-JSON context constant")


def _workstream_context(args: argparse.Namespace) -> int:
    """Forward one exact Agent OS context read through existing process ownership."""
    def unavailable(reason: str) -> int:
        sys.stderr.write(f"Agent OS context unavailable: {reason}. No generic brief fallback.\n")
        return 1

    root, _, _ = resolve_macro_root(
        args.macro_root, os.environ,
        Path(args.repo_root) if args.repo_root else _ROOT,
    )
    if root is None:
        return unavailable("no usable Macro checkout; supply --macro-root")
    root = root.resolve()
    if git_sha(root) != args.expected_macro_sha:
        return unavailable("Macro checkout does not match the expected source pin")
    argv = [sys.executable, "-B", os.fspath(root / "scripts" / "agentos.py"),
            "compile-context", "--workstream", args.workstream,
            "--json", "--budget", str(args.context_budget or 4000)]
    if args.now is not None:
        argv += ["--now", args.now]
    try:
        observed = bounded_subprocess_runner(
            argv, cwd=root, timeout=args.timeout, max_bytes=_CONTEXT_MAX_BYTES,
        )
    except (OSError, RuntimeError, ValueError):
        # Never expose a raw process error, retry, or claim the reader settled.
        return unavailable("reader failed; reconcile the existing reader before another attempt")
    if observed["timed_out"]:
        return unavailable("reader timed out")
    if observed["limit_exceeded"]:
        return unavailable("transport output limit exceeded; context was not truncated")
    if observed["invalid_utf8"]:
        return unavailable("reader emitted invalid UTF-8")
    if observed["code"] != 0:
        return unavailable(f"canonical compiler exit {observed['code']}; inspect the exact workstream record")
    raw = observed["stdout"]
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
        if not isinstance(payload, dict) or payload.get("schema") != "context_bundle.v1":
            raise ValueError("wrong context schema")
        target = payload.get("target")
        if not isinstance(target, dict) or target.get("workstream") != f"WS:{args.workstream}":
            raise ValueError("wrong context target")
        for field in ("sections", "excluded", "omitted_due_to_budget", "degraded"):
            if not isinstance(payload.get(field), list):
                raise ValueError("incomplete context")
        for field in ("source_records_digest", "repo_sha", "generated_at"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                raise ValueError("missing context provenance")
        if not re.fullmatch(r"[0-9a-f]{40}", payload["repo_sha"]):
            raise ValueError("noncanonical Git source identity")
        if not valid_source_records_digest(payload["source_records_digest"]):
            raise ValueError("noncanonical source-record digest")
        if "no_answer_reason" not in payload:
            raise ValueError("missing context answer state")
    except (ValueError, TypeError, RecursionError):
        return unavailable("invalid or mismatched canonical context response")
    if (
        payload["repo_sha"] != args.expected_macro_sha
        or git_sha(root) != args.expected_macro_sha
    ):
        return unavailable("Macro source changed or canonical provenance mismatched the expected pin")
    # Preserve all owner fields, including warnings, omissions, source digest,
    # no-answer and legitimate mandatory-constraint token-budget overrun.
    sys.stdout.write(raw)
    if not raw.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CEO boot packet assembled from the Agent OS store.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit the mastermind.ceo_boot_packet.v1 document instead of text",
    )
    parser.add_argument(
        "--repo-root",
        help="Mastermind checkout/release root to project as this packet's source",
    )
    parser.add_argument(
        "--macro-root",
        help=f"Macro checkout to read Agent OS from (overrides ${ENV_MACRO_ROOT})",
    )
    parser.add_argument(
        "--since", help="brief window: 1h | 24h | 7d | overnight | YYYY-MM-DD",
    )
    parser.add_argument(
        "--now", help="freeze the clock (ISO-8601) — reproducibility",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"seconds allowed for the Agent OS reader (default {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--workstream",
        help="read one exact WS:KEY as canonical context_bundle.v1 JSON, not the global brief",
    )
    parser.add_argument(
        "--context-budget", type=int,
        help="token budget passed to Agent OS with --workstream (default 4000)",
    )
    parser.add_argument(
        "--expected-macro-sha",
        help="required with --workstream: exact Macro HEAD before/after the read and in its provenance",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.workstream is not None:
        # Scoped recovery must never inherit the global brief's discovery ladder.
        if not args.macro_root or not args.macro_root.strip():
            parser.error("--workstream requires an explicit --macro-root; no discovery fallback")
        if args.expected_macro_sha is None:
            parser.error("--workstream requires --expected-macro-sha from the source owner")
        args.workstream = args.workstream.removeprefix("WS:")
        if not re.fullmatch(r"[A-Z0-9][A-Za-z0-9._-]{1,63}", args.workstream):
            parser.error("--workstream must name one exact workstream key")
        if args.since is not None:
            parser.error("--since applies to the company brief, not workstream context")
        if args.expected_macro_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", args.expected_macro_sha):
            parser.error("--expected-macro-sha must be exactly 40 lowercase hex characters")
        if args.context_budget is not None and args.context_budget <= 0:
            parser.error("--context-budget must be positive")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            parser.error("--timeout must be finite and positive for workstream context")
        return _workstream_context(args)
    if args.context_budget is not None or args.expected_macro_sha is not None:
        parser.error("--context-budget and --expected-macro-sha require --workstream")

    packet = build_packet(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        macro_root_flag=args.macro_root,
        since=args.since,
        now=args.now,
        timeout=args.timeout,
    )

    if args.json:
        sys.stdout.write(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_packet(packet))

    # Fail open by contract: a degraded packet is still a delivered packet.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
