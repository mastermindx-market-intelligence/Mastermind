"""Private fixed installed child; no caller paths, mutation or network."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.workspace_project_knowledge_read_contract import OPERATIONS, selection, validate_body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--expected-macro-sha", required=True)
    parser.add_argument("--operation", choices=OPERATIONS, required=True)
    parser.add_argument("--work-ref", required=True)
    parser.add_argument("--source-ref")
    parser.add_argument("--expected-revision")
    parser.add_argument("--discovery-ref")
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--code-root")
    parser.add_argument("--code-commit")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if (args.code_root is None) != (args.code_commit is None):
        raise ValueError("SOURCE_UNAVAILABLE")
    selected = {"work_ref": args.work_ref}
    if args.source_ref is not None: selected["source_ref"] = args.source_ref
    if args.expected_revision is not None: selected["expected_revision"] = args.expected_revision
    if args.discovery_ref is not None: selected["discovery_ref"] = args.discovery_ref
    if args.expected_source_commit is not None: selected["expected_source_commit"] = args.expected_source_commit
    selection(selected, operation=args.operation)
    from control_plane.agentos_project_knowledge import (
        read_project_knowledge_catalogue, read_project_communication_preference,
        read_project_knowledge_source, read_project_discovery_source)
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        kwargs = dict(macro_root=Path(args.macro_root), expected_macro_sha=args.expected_macro_sha,
            timeout=args.timeout, **selected)
        if args.code_root is not None:
            kwargs.update(code_root=Path(args.code_root), code_commit=args.code_commit)
        if args.operation == "project_knowledge_catalogue": value = read_project_knowledge_catalogue(**kwargs)
        elif args.operation == "project_knowledge_memory": value = read_project_communication_preference(**kwargs)
        elif args.operation == "project_discovery_source": value = read_project_discovery_source(**kwargs)
        else: value = read_project_knowledge_source(**kwargs)
        value = validate_body(value, operation=args.operation)
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
