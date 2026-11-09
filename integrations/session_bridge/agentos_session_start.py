#!/usr/bin/env python3
"""Supply exact Agent OS context to an explicitly focused Codex SessionStart.

This is an attended, read-only orientation adapter. It creates no assignment,
runtime receipt, parent transfer, subscription, checkpoint, or execution loop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ops.fabric_launch.agentos import OWNER_ROOT, read_context, validate_bundle
from ops.fabric_launch.context import LaunchInputError

MAX_EVENT_BYTES = 64 * 1024
MAX_CONTEXT_BYTES = 32 * 1024
SOURCES = frozenset({"startup", "resume", "clear", "compact", "fork"})
WORKSTREAM = re.compile(r"WS:[A-Z][A-Z0-9-]{0,95}\Z")
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")


def _output(text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def _unavailable(workstream: str, reason: str) -> dict:
    return _output(
        f"Agent OS context focus {workstream}: context unavailable ({reason}). "
        "No project bundle was supplied. Recover the current workstream and latest "
        "handoff through the existing Agent OS reader before relying on remembered "
        "project state. This observation does not block other authorized work or "
        "establish runtime ownership."
    )


def _directory(value) -> Path:
    if not isinstance(value, (str, Path)) or not Path(value).is_absolute():
        raise LaunchInputError("SESSION_CONTEXT_PATH_INVALID")
    try:
        path = Path(value).resolve(strict=True)
        if not path.is_dir():
            raise OSError("not a directory")
        return path
    except (OSError, RuntimeError, ValueError):
        raise LaunchInputError("SESSION_CONTEXT_PATH_UNAVAILABLE") from None


def _owner_session_start_context(event, *, workspace_root, workstream, owner_root=OWNER_ROOT,
                          budget=4000, reader=read_context, charter_root=None,
                          owner_session=None, owner=None) -> dict:
    """Expand one explicit context focus; workspace equality grants no authority."""
    if (type(workstream) is not str or not WORKSTREAM.fullmatch(workstream)
            or type(budget) is not int or not 800 <= budget <= 12000):
        raise LaunchInputError("SESSION_CONTEXT_FOCUS_INVALID")
    if (type(event) is not dict or event.get("hook_event_name") != "SessionStart"
            or type(event.get("source")) is not str or event["source"] not in SOURCES
            or type(event.get("session_id")) is not str
            or not SESSION_ID.fullmatch(event["session_id"])):
        raise LaunchInputError("SESSION_CONTEXT_EVENT_INVALID")
    if _directory(event.get("cwd")) != _directory(workspace_root):
        return {}
    if any(value is not None for value in (charter_root, owner_session, owner)):
        # Opt-in original-owner resume only. This never invokes Stop, starts a
        # task, initiates a turn, or promotes the organizational bundle to a grant.
        if event['source'] != 'resume' or any(value is None for value in
                (charter_root, owner_session, owner)):
            return {}
        from integrations.session_bridge.project_owner_continuation import collect_context, bounded_json
        result = collect_context(workspace_root=workspace_root,
            observed_workspace=event['cwd'], owner_session=owner_session,
            observed_session=event['session_id'], workstream=workstream,
            owner=owner, charter_root=charter_root, macro_root=owner_root,
            budget=budget, reader=reader)
        result['entrypoint'] = 'original_owner_resume'
        return _output(bounded_json(result))
    try:
        owner = _directory(owner_root)
        raw, observation = reader(
            workstream, budget,
            owner_root=owner,
        )
        validate_bundle(raw, workstream)
        if (type(observation) is not dict
                or observation.get("workstream") != workstream
                or observation.get("execution_authority") is not False
                or observation.get("bundle_sha256") != hashlib.sha256(raw).hexdigest()):
            raise LaunchInputError("AGENTOS_READ_OBSERVATION_MISMATCH")
        envelope = {
            "context_focus": workstream,
            "native_event_session_id": event["session_id"],
            "source": event["source"],
            "agentos_read_observation": observation,
            "runtime_ownership": "UNOBSERVED",
            "parent_custody": "UNOBSERVED",
            "outstanding_effects": "UNOBSERVED",
        }
        text = (
            "Agent OS project context (read-only organizational evidence).\n"
            "Use this context for the currently assigned objective. Current assignment "
            "and governing instructions take precedence. Recorded next actions and "
            "accepted outcomes are evidence; obtain current runtime and effect facts "
            "before continuing a worker or changing ownership. A fork or new session "
            "does not inherit another parent's custody.\n"
            "Acquisition observation; not Runtime PREPARE or a supplied-input receipt:\n"
            + json.dumps(envelope, sort_keys=True, allow_nan=False) + "\n"
            "Owner-produced context_bundle.v1 (verbatim):\n" + raw.decode("utf-8")
        )
        if len(text.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise LaunchInputError("AGENTOS_CONTEXT_DELIVERY_TOO_LARGE")
        return _output(text)
    except (LaunchInputError, OSError, ValueError, TypeError) as exc:
        reason = str(exc)
        return _unavailable(workstream, reason if SAFE_REASON.fullmatch(reason)
                            else "AGENTOS_CONTEXT_UNAVAILABLE")


def session_start_context(event, *, workspace_root, workstream, owner_root=OWNER_ROOT,
                          budget=4000, reader=read_context, charter_root=None,
                          owner_session=None, owner=None, plan_path=None, plan_sha256=None,
                          plan_contract_sha256=None) -> dict:
    """Compose an explicitly bound source-plan view with the incumbent hook.

    No registration or runtime activation occurs here. The optional plan is
    source evidence, never a replacement owner, a grant, or a continuation loop.
    """
    result = _owner_session_start_context(event, workspace_root=workspace_root,
        workstream=workstream, owner_root=owner_root, budget=budget, reader=reader,
        charter_root=charter_root, owner_session=owner_session, owner=owner)
    if not result or (plan_path is None and plan_sha256 is None and plan_contract_sha256 is None):
        return result
    from integrations.session_bridge.project_task_context import load_context, PlanContextError
    try:
        context = load_context(workspace_root=workspace_root, relative_path=plan_path,
                               expected_sha256=plan_sha256, workstream=workstream,
                               expected_contract_sha256=plan_contract_sha256)
        # Keep every requirement and every task identity/dependency; load the
        # complete off-focus acceptance details from the same pinned plan.
        brief = {k: v for k, v in context.items() if k != "task_tree"}
        brief["task_tree"] = [{k: row[k] for k in ("id", "title", "state", "depends_on",
            "requirement_ids", "definition_sha256", "missing_or_stale_evidence", "source_complete", "evidence")}
            for row in context["task_tree"]]
        brief["task_detail_scope"] = "FULL_FOCUS; OFF_FOCUS_ACCEPTANCE_AT_EXACT_SOURCE"
        addition = ("\nGitHub-owned plan projection. Source claims, not runtime permission or acceptance.\n"
                    + json.dumps(brief, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        original = result["hookSpecificOutput"]["additionalContext"]
        if len((original + addition).encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise PlanContextError("PLAN_CONTEXT_DELIVERY_TOO_LARGE")
        return _output(original + addition)
    except (PlanContextError, TypeError, ValueError) as exc:
        reason = str(exc)
        reason = reason if SAFE_REASON.fullmatch(reason) else "PLAN_CONTEXT_UNAVAILABLE"
        # A failed optional plan must not discard a healthy incumbent bundle.
        notice = (f"Project plan context was not supplied ({reason}). Read {workstream} through the "
            "existing Agent OS owner and the exact assigned GitHub plan separately. "
            "Do not infer that the project is complete or that runtime custody transferred.")
        original = result["hookSpecificOutput"]["additionalContext"]
        combined = original + "\n" + notice
        if len(combined.encode("utf-8")) <= MAX_CONTEXT_BYTES:
            return _output(combined)
        # Neither partial mission text nor silent truncation is a safe fallback.
        return _output(notice + " The incumbent context must also be read separately because the delivery limit was reached.")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise LaunchInputError("SESSION_CONTEXT_DUPLICATE_EVENT_KEY")
        value[key] = item
    return value


def _nonfinite(_):
    raise LaunchInputError("SESSION_CONTEXT_EVENT_INVALID")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LaunchInputError("SESSION_CONTEXT_ARGUMENTS_INVALID")


def main(argv=None, *, stdin=None, stdout=None, stderr=None, reader=read_context) -> int:
    parser = _Parser(description=__doc__, add_help=False)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--workstream", required=True)
    parser.add_argument("--macro-root", default=OWNER_ROOT, type=Path)
    parser.add_argument("--budget", default=4000, type=int)
    parser.add_argument("--charter-root", type=Path)
    parser.add_argument("--owner-session")
    parser.add_argument("--owner")
    parser.add_argument("--plan-path")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--plan-contract-sha256")
    stream = sys.stdin.buffer if stdin is None else stdin
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    try:
        args = parser.parse_args(argv)
        raw = stream.read(MAX_EVENT_BYTES + 1)
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_EVENT_BYTES:
            raise LaunchInputError("SESSION_CONTEXT_EVENT_SIZE_INVALID")
        event = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=_nonfinite)
        result = session_start_context(event, workspace_root=args.workspace_root,
            workstream=args.workstream, owner_root=args.macro_root,
            budget=args.budget, reader=reader, charter_root=args.charter_root,
            owner_session=args.owner_session, owner=args.owner,
            plan_path=args.plan_path, plan_sha256=args.plan_sha256,
            plan_contract_sha256=args.plan_contract_sha256)
    except (LaunchInputError, OSError, ValueError, TypeError, RecursionError) as exc:
        reason = str(exc)
        err.write((reason if SAFE_REASON.fullmatch(reason)
                   else "SESSION_CONTEXT_EVENT_INVALID") + "\n")
        result = {}
    out.write(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
    # Orientation gaps are explicit and never become an execution gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
