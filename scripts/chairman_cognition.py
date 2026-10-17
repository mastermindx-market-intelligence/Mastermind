#!/usr/bin/env python3
"""Evaluate one Chairman-cognition JSON document without side effects."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.chairman_cognition import (  # noqa: E402
    ERROR_SCHEMA,
    ChairmanCognitionError,
    evaluate_document,
)


class _DuplicateKeyError(ValueError):
    """A JSON object repeated a key before A1 closed-map validation."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError("duplicate JSON object key")
        result[key] = value
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input path or '-' for stdin")
    parser.add_argument("--pretty", action="store_true", help="pretty-print output")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--coordination-review", metavar="PATH", help="review a project-scoped candidate from an owner-supplied context JSON file")
    mode.add_argument("--coordination-brief", metavar="PATH", help="render existing compiled Agent OS context for one coordination judgment")
    mode.add_argument("--coordination-return", metavar="PATH", help="review complete existing harness result evidence, not its shortened summary")
    return parser


def _read(path: str) -> object:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=_strict_object)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = _read(args.input)
        if not isinstance(raw, dict):
            raise ChairmanCognitionError("top-level JSON must be an object")
        coordination_path = args.coordination_review or args.coordination_brief or args.coordination_return
        if coordination_path:
            if args.input == "-" and coordination_path == "-":
                raise ChairmanCognitionError("two inputs cannot share stdin")
            if coordination_path == "-":
                review_text = sys.stdin.read(1024 * 1024 + 1)
            else:
                with Path(coordination_path).open(encoding="utf-8") as stream:
                    review_text = stream.read(1024 * 1024 + 1)
            if len(review_text.encode("utf-8")) > 1024 * 1024:
                raise ChairmanCognitionError("coordination review exceeds input bound")
            review = json.loads(review_text, object_pairs_hook=_strict_object)
            if args.coordination_review:
                keys = {"context", "candidate"}
            elif args.coordination_brief:
                keys = {"context", "context_bundle", "bundle_source_ref"}
            else:
                keys = {"context", "observation", "candidate_result", "expected_turn", "expected_provider_session_id", "expected_provider_native_turn_id"}
            if not isinstance(review, dict) or set(review) != keys:
                raise ChairmanCognitionError("invalid coordination input fields")
            from control_plane.chairman_coordination import evaluate_coordination_candidate, render_coordination_brief, evaluate_coordination_return
            if args.coordination_review:
                packet = evaluate_coordination_candidate(raw, context=review["context"], candidate=review["candidate"])
            elif args.coordination_brief:
                packet = render_coordination_brief(raw, context=review["context"], context_bundle=review["context_bundle"], bundle_source_ref=review["bundle_source_ref"])
            else:
                from control_plane.executive_orchestration_result import RawRoleResultObservation
                from control_plane.operator_harness_contract import CandidateResult, TurnRef
                try:
                    observation = RawRoleResultObservation(**review["observation"])
                    candidate_result = CandidateResult(**review["candidate_result"])
                    expected_turn = TurnRef(**review["expected_turn"])
                except (TypeError, ValueError, RecursionError) as exc:
                    raise ChairmanCognitionError("invalid existing harness result evidence") from exc
                packet = evaluate_coordination_return(raw, context=review["context"], observation=observation, candidate_result=candidate_result, expected_turn=expected_turn, expected_provider_session_id=review["expected_provider_session_id"], expected_provider_native_turn_id=review["expected_provider_native_turn_id"])
        else:
            packet = evaluate_document(raw)
    except (
        ChairmanCognitionError,
        _DuplicateKeyError,
        OSError,
        json.JSONDecodeError,
        UnicodeError,
    ):
        print(
            json.dumps(
                {"schema": ERROR_SCHEMA, "error": "INVALID_INPUT"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            packet,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
