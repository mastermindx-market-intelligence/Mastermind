#!/usr/bin/env python3
"""scripts.operation_assurance_compile — OLS-A2 bounded gather/compile CLI.

Two modes:
    operation-assurance-compile --repo-root DIR --repo REPO --revision SHA40
                                 --observed-at TIMESTAMP [--pretty]
        Gathers Agent OS source facts from DIR at the pinned SHA40 revision
        (the caller's own assertion; this CLI never runs git), compiles the
        frozen first target (WS:OPERATION-ASSURANCE unless --target-key is
        given), and prints the resulting mastermind.operation_assurance_model.v1
        bundle to stdout.

    operation-assurance-compile --from-facts FACTS.json|- [--pretty]
        Reads an already-gathered mastermind.operation_assurance_source_facts.v1
        document (from a file or stdin) and compiles it, without touching a
        filesystem checkout. REPAIR R2: a serialized revision_binding of
        GIT_HEAD_VERIFIED is NEVER trusted from this document alone — it is
        always downgraded to CALLER_ASSERTED_UNVERIFIED on ingest.

    operation-assurance-compile --from-facts FACTS.json|- --repo-root DIR [--pretty]
        Same ingest, PLUS an independent re-verification pass: DIR's own
        git HEAD (pure file reads, no subprocess) is resolved and compared
        against the ingested facts.revision. A match legitimately
        re-establishes revision_binding=GIT_HEAD_VERIFIED; a disagreement
        refuses (REVISION_MISMATCH); an unresolvable DIR leaves the
        downgraded, honest CALLER_ASSERTED_UNVERIFIED marker in place.

This CLI performs no write other than stdout/stderr, has no trusted-source
flag, and is not an implicit admission gate: a valid but structurally unsafe
compiled model still produces a normal model bundle and exit 0.

Exit contract (mirrors control_plane.operation_assurance CLI pattern)
-----------------------------------------------------------------
0   a valid compiled model bundle, including one carrying FAIL-eligible
    detections once checked downstream — this CLI does not itself run the
    checker;
2   malformed/refused input: bad arguments, a gather refusal
    (SourceGatherError), or a compiler refusal (CompilerError, including
    SOURCE_MISSING / SOURCE_PARTIAL / SOURCE_TRUNCATED / SOURCE_CONFLICTED);
3   internal refusal (never a partially trusted output).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":  # pragma: no cover - direct-execution import shim
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.operation_assurance_compiler import CompilerError, compile_operation_assurance_model
from control_plane.operation_assurance_sources import (
    FIRST_TARGET_WORKSTREAM_KEY,
    SourceFacts,
    SourceGatherError,
    gather_agent_os_source_facts,
    reestablish_revision_binding,
)

MAX_STDIN_BYTES = 8_388_608 + 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="operation-assurance-compile", add_help=True)
    parser.add_argument("--repo-root", help="checkout directory to gather from")
    parser.add_argument("--repo", help="repo identity string (e.g. org/name)")
    parser.add_argument("--revision", help="full 40-hex commit SHA")
    parser.add_argument("--observed-at", help="one UTC 'Z' cutoff timestamp for the whole gather")
    parser.add_argument("--from-facts", help="path to a source-facts JSON document, or '-' for stdin")
    parser.add_argument("--target-key", default=FIRST_TARGET_WORKSTREAM_KEY, help="workstream key to compile")
    parser.add_argument("--pretty", action="store_true")
    return parser


def _read_stdin_bytes() -> bytes:
    return sys.stdin.buffer.read(MAX_STDIN_BYTES)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    args = parser.parse_args(argv)  # argparse exits 2 on bad args, 0 on --help

    facts_mode = args.from_facts is not None
    other_gather_args_given = any([args.repo, args.revision, args.observed_at])

    if facts_mode and other_gather_args_given:
        print(
            "usage: --repo/--revision/--observed-at are not used with --from-facts "
            "(--repo-root alone is accepted, as an independent revision_binding re-verification pass)",
            file=sys.stderr,
        )
        return 2
    if not facts_mode and not (args.repo_root and args.repo and args.revision and args.observed_at):
        print(
            "usage: exactly one of (--repo-root --repo --revision --observed-at) or "
            "--from-facts [--repo-root] is required",
            file=sys.stderr,
        )
        return 2

    if facts_mode:
        try:
            if args.from_facts == "-":
                raw = _read_stdin_bytes()
            else:
                with open(args.from_facts, "rb") as fh:  # noqa: PTH123 - explicit caller-supplied read path
                    raw = fh.read(MAX_STDIN_BYTES)
        except OSError:
            print("INPUT_READ_ERROR: could not read the supplied source-facts input", file=sys.stderr)
            return 2
        try:
            # REPAIR B1: the ONE canonical, closed-wire ingest entry point —
            # never a bare json.loads()+from_dict() passthrough.
            facts = SourceFacts.from_json_bytes(raw)
            if args.repo_root is not None:
                # REPAIR R2: the ONLY lawful way an ingested document may
                # carry GIT_HEAD_VERIFIED — independent re-resolution
                # against a LIVE checkout in this SAME invocation, never a
                # trusted claim from the document itself.
                facts = reestablish_revision_binding(facts, args.repo_root)
        except SourceGatherError as exc:
            print(f"{exc.reason_code}: {exc}", file=sys.stderr)
            return 2
    else:
        missing = [
            name
            for name, value in (
                ("--repo-root", args.repo_root),
                ("--repo", args.repo),
                ("--revision", args.revision),
                ("--observed-at", args.observed_at),
            )
            if not value
        ]
        if missing:
            print(f"usage: missing required argument(s) {missing}", file=sys.stderr)
            return 2
        try:
            facts = gather_agent_os_source_facts(
                args.repo_root,
                repo=args.repo,
                revision=args.revision,
                observed_at=args.observed_at,
                target_workstream_key=args.target_key,
            )
        except SourceGatherError as exc:
            print(f"{exc.reason_code}: {exc}", file=sys.stderr)
            return 2
        except Exception:  # pragma: no cover - defense in depth, never a healthy default
            print("GATHER_INTERNAL_ERROR: gather refused", file=sys.stderr)
            return 3

    try:
        model = compile_operation_assurance_model(facts, target_workstream_key=args.target_key)
    except CompilerError as exc:
        print(f"{exc.reason_code}: {exc}", file=sys.stderr)
        return 2
    except Exception:  # pragma: no cover - defense in depth, never a healthy default
        print("COMPILER_INTERNAL_ERROR: compiler refused", file=sys.stderr)
        return 3

    if args.pretty:
        print(json.dumps(model.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(json.dumps(model.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
