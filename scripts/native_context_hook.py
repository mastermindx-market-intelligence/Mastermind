#!/usr/bin/env python3
"""Stateless startup hook. Defaults to unbound orientation, never global hydration.

Prints JSON to stdout only. No configuration, transcript, or memory-file writes.
Install/source selection belongs to the existing native installation owner.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from integrations.native_context.adapter import (  # noqa: E402
    Binding, ContextError, MAX_EVENT_BYTES, ReaderResult, encode_response, hook_fragment, render_hook,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    result.add_argument("--provider", choices=("codex", "claude"), required=True)
    result.add_argument("--workstream")
    result.add_argument("--macro-root", type=Path)
    result.add_argument("--expected-macro-sha")
    result.add_argument("--expected-mastermind-sha", dest="expected_reader_sha")
    result.add_argument("--continuation-ref")
    result.add_argument("--hydrate", action="store_true")
    result.add_argument("--max-context-bytes", type=int, default=6000)
    result.add_argument("--compiler-budget", type=int, default=4000)
    result.add_argument("--timeout", type=float, default=10.0)
    result.add_argument("--emit-hook-fragment", action="store_true",
                        help="print an unbound orientation fragment; never install it")
    return result


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    supplied = (args.workstream, args.macro_root, args.expected_macro_sha, args.expected_reader_sha)
    if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
        p.error("bound mode requires workstream, explicit Macro root, and both expected source pins")
    if (args.hydrate or args.continuation_ref) and not args.workstream:
        p.error("hydration/continuation requires an explicit source binding")
    if args.emit_hook_fragment:
        if args.workstream or args.hydrate:
            p.error("global fragments must remain unbound; task binding belongs to the existing launcher")
        fragment = hook_fragment(provider=args.provider, python=Path(sys.executable), script=Path(__file__).resolve())
        print(json.dumps(fragment, indent=2))
        return 0
    try:
        binding = (Binding(args.workstream, args.macro_root, args.expected_macro_sha,
                           args.expected_reader_sha, args.continuation_ref)
                   if args.workstream else None)
        # Reject oversize input without parsing or using any transcript/cwd path.
        raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
        reader = None
        if args.hydrate:
            # Even imports are deferred until render_hook accepts the event/binding.
            def reader(bound: Binding, budget: int, timeout: float) -> ReaderResult:
                try:
                    from integrations.native_context.bridge import installed_reader
                    return installed_reader(_ROOT)(bound, budget, timeout)
                except (ImportError, OSError):
                    return ReaderResult(False)
        response = render_hook(raw, provider=args.provider, binding=binding, reader=reader,
                               hydrate=args.hydrate, max_context_bytes=args.max_context_bytes,
                               compiler_budget=args.compiler_budget, timeout=args.timeout)
        sys.stdout.buffer.write(encode_response(response))
        return 0
    except (ContextError, ValueError, TypeError, OSError):
        # A configuration error is diagnostic, not authorization to block the user.
        sys.stderr.write("Native context hook unavailable: invalid local configuration or input. No payload emitted.\n")
        sys.stdout.write("{}\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
