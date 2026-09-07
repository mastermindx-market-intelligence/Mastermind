#!/usr/bin/env python3
"""Verify, stage, or read back one BSC-U1 native app-reference artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from integrations.business_sol_installation import (
    InstallationContractError,
    canonical_json,
    compile_installation_bindings,
    preflight_installation,
    stage_compilation,
    verify_staged_compilation,
)


# A ceremony document is small. Bound decoding before normalization or staging;
# in-memory dict tests cannot detect duplicate JSON members lost by json.loads.
MAX_JSON_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_JSON_INTEGER_DIGITS = 64


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InstallationContractError("INVALID_INPUT")
        result[key] = value
    return result


def _reject_json_constant(_literal: str) -> Any:
    raise InstallationContractError("INVALID_INPUT")


def _bounded_json_integer(literal: str) -> int:
    # Do not depend on interpreter-wide int conversion settings.
    if len(literal.lstrip("-")) > MAX_JSON_INTEGER_DIGITS:
        raise InstallationContractError("INVALID_INPUT")
    return int(literal)


def _check_json_depth(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        node, parent_depth = pending.pop()
        if type(node) not in (dict, list):
            continue
        depth = parent_depth + 1
        if depth > MAX_JSON_DEPTH:
            raise InstallationContractError("INVALID_INPUT")
        children = node.values() if type(node) is dict else node
        pending.extend((child, depth) for child in children)


def _json_file(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_JSON_BYTES + 1)
        if len(payload) > MAX_JSON_BYTES:
            raise InstallationContractError("INVALID_INPUT")
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
            parse_int=_bounded_json_integer,
        )
        _check_json_depth(value)
        return value
    except (OSError, UnicodeError, ValueError, RecursionError):
        # Never expose decoder input, filesystem paths, or exception text.
        raise InstallationContractError("INVALID_INPUT") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and stage the native Mastermind Sol app-reference artifact. "
            "This tool does not call ChatGPT, OAuth, MCP, Executive OS, or a workspace API."
        )
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("preflight", "stage", "verify"),
        default="preflight",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--expected-preimage-digest")
    return parser


def _emit(value: object, *, stream: object = sys.stdout) -> None:
    payload = canonical_json(value).decode("utf-8")
    print(payload, file=stream)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        template = _json_file(args.template)
        request = _json_file(args.request)
        if args.mode == "preflight":
            result = preflight_installation(template, request)
            _emit(result)
            return 0 if result["status"] == "READY_TO_COMPILE" else 3

        compilation = compile_installation_bindings(template, request)
        if args.output_root is None or args.source_root is None:
            raise InstallationContractError("INVALID_INPUT")
        if args.mode == "stage":
            if args.expected_preimage_digest is None:
                raise InstallationContractError("INVALID_INPUT")
            staged = stage_compilation(
                compilation,
                output_root=args.output_root,
                source_root=args.source_root,
                expected_preimage_digest=args.expected_preimage_digest,
            )
            _emit(
                {
                    "public_receipt": compilation.public_receipt,
                    "stage_receipt": staged.stage_receipt,
                    "rollback_manifest": staged.rollback_manifest,
                }
            )
            return 0

        result = verify_staged_compilation(
            compilation,
            output_root=args.output_root,
            source_root=args.source_root,
        )
        _emit(result)
        return 0
    except InstallationContractError as exc:
        _emit(
            {
                "schema": "mastermind.business_sol_installation_error.v1",
                "status": "REFUSED",
                "code": exc.code,
                "workspace_effect_applied": False,
                "oauth_effect_applied": False,
                "production_acceptance_granted": False,
            },
            stream=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
