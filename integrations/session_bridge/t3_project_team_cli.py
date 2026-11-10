"""Foreground, read-only project-team tools for T3 terminals and native agents.

All commands prepare or inspect data. Launch/delegate commands emit requests for
T3's existing authenticated tools, not a second dispatcher. The incumbent
ProjectTeamClient supports actual launch for an already-authorized injected runner.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
from typing import Any, Sequence

from .t3_project_team import (
    DependencyEvidence, MAX_DOCUMENT_BYTES, RoleBinding, TeamError, _native_id,
    _require, _shape, _text, parse_team, prepare_delegation, project_graph,
)
from .t3_web_client import NativeUnavailable, ThreadReceipt
from .t3_project_team_inventory import inventory_from_document
from .project_task_context import PlanContextError

MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProjectPlanInput:
    """Local source selection only; no authenticated help or Executive root."""

    workspace_root: str
    relative_path: str
    work_ref: str
    source_ref: str
    content_sha256: str

    def read_context(self) -> dict[str, Any]:
        from .project_task_context import load_context

        return load_context(workspace_root=self.workspace_root, relative_path=self.relative_path,
                            workstream=self.work_ref, expected_sha256=self.content_sha256)

    def arguments(self) -> list[str]:
        return ["--plan-workspace-root", self.workspace_root,
                "--project-plan", self.relative_path, "--plan-work-ref", self.work_ref,
                "--plan-source-ref", self.source_ref, "--plan-sha256", self.content_sha256]


def _project_plan_input(args) -> ProjectPlanInput | None:
    values = [getattr(args, name, None) for name in (
        "plan_workspace_root", "project_plan", "plan_work_ref", "plan_source_ref", "plan_sha256")]
    if all(value is None for value in values):
        return None
    _require(all(value is not None for value in values), "TEAM_PROJECT_HELP_PLAN_SELECTION_INCOMPLETE")
    return ProjectPlanInput(*values)


def _read(path: str, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit, "TEAM_INPUT_FILE_INVALID")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        _require(len(raw) <= limit, "TEAM_INPUT_FILE_INVALID")
        return raw
    finally:
        os.close(descriptor)


def _load_snapshot(path: str | None) -> dict[str, Any]:
    if path is None:
        return {"bindings": (), "observations": {}, "evidence": (), "uncertain_role_ids": (), "native_inventory": None}

    def unique(pairs):
        out = {}
        for key, value in pairs:
            _require(key not in out, "TEAM_DUPLICATE_JSON_KEY")
            out[key] = value
        return out

    def constant(_):
        raise TeamError("TEAM_NONFINITE_JSON")

    value = json.loads(_read(path, MAX_SNAPSHOT_BYTES), object_pairs_hook=unique, parse_constant=constant)
    _shape(value, {"bindings", "observations", "dependency_evidence", "uncertain_role_ids"}, {"native_inventory"})
    _require(type(value["bindings"]) is list and type(value["dependency_evidence"]) is list
             and type(value["uncertain_role_ids"]) is list and type(value["observations"]) is dict,
             "TEAM_SNAPSHOT_SHAPE_INVALID")
    bindings = []
    for raw in value["bindings"]:
        _shape(raw, {"role_id", "environment_id", "root_thread_id", "parent_thread_id", "task_id",
                     "receipt", "team_sha256"})
        _shape(raw["receipt"], {"request_id", "project_id", "thread_id", "run_id", "brief_sha256"},
               {"delivery"})
        bindings.append(RoleBinding(**{**raw, "receipt": ThreadReceipt(**raw["receipt"])}))
    evidence = []
    for raw in value["dependency_evidence"]:
        _shape(raw, {"role_id", "accepted_by_role_id", "team_sha256", "source_ref"})
        evidence.append(DependencyEvidence(**raw))
    return {"bindings": tuple(bindings), "observations": value["observations"],
            "evidence": tuple(evidence), "uncertain_role_ids": tuple(value["uncertain_role_ids"]),
            "native_inventory": inventory_from_document(value["native_inventory"])
            if value.get("native_inventory") is not None else None}


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False))


def launch_request(team, *, project_id: str, request_id: str, environment_id: str,
                   definition_ref: str | None = None,
                   project_context: dict[str, Any] | None = None,
                   project_source_ref: str | None = None) -> dict[str, Any]:
    """Native tool payload only. No OAuth, provider selection, launch or retries."""
    brief = team.root_handoff(project_id=project_id, request_id=request_id,
                             definition_ref=definition_ref, project_context=project_context,
                             project_source_ref=project_source_ref)
    _native_id(environment_id)
    arguments = {"projectId": project_id,
                 "title": "Project COO: " + request_id[:48], "message": brief.render(),
                 "workspaceStrategy": {"type": "worktree", "baseRef": team.mission.base_sha,
                                       "branch": "web/" + request_id, "startFromOrigin": False},
                 "clientRequestId": "team-" + hashlib.sha256(
                     (request_id + ":" + brief.fingerprint).encode()).hexdigest()[:48]}
    return {"tool": "t3_thread_launch", "arguments": arguments,
            "expected_environment_id": environment_id,
            "team_sha256": team.fingerprint, "brief_sha256": brief.fingerprint,
            "effect_state": "NOT_DISPATCHED", "execution_authorized": False,
            "recovery": "Retain original caller namespace and native receipt. Lost replies require original-effect reconciliation; never replay via a fresh CLI/OAuth client."}


def project_actions(*, definition: str, launcher: str, project_id: str,
                    request_id: str, environment_id: str, definition_ref: str | None = None,
                    project_plan: ProjectPlanInput | None = None) -> dict[str, Any]:
    """Importable native T3 actions; all are explicitly manual and read-only."""
    _text(definition, 4096)
    _text(launcher, 4096)
    _require(Path(launcher).is_absolute(), "TEAM_LAUNCHER_ABSOLUTE_PATH_REQUIRED")
    _native_id(project_id)
    _native_id(environment_id)
    _require(project_plan is None or type(project_plan) is ProjectPlanInput,
             "TEAM_PROJECT_HELP_PLAN_SELECTION_INVALID")
    base = [launcher]
    reference_args = ["--definition-ref", definition_ref] if definition_ref else []

    def command(action, *extra):
        plan_args = project_plan.arguments() if project_plan is not None and action != "graph" else []
        return shlex.join([*base, action, definition, *extra,
                           *(reference_args if action != "graph" else []), *plan_args])

    scripts = [
        ("Check project team", command("check")),
        ("Inspect project graph", command("graph")),
        ("Prepare COO launch request", command("launch-request", "--project-id", project_id,
                                              "--request-id", request_id, "--environment-id", environment_id)),
    ]
    return {"$schema": "https://t3.codes/schema/t3.json", "scripts": [
        {"name": name, "command": cmd, "icon": "configure", "runOnWorktreeCreate": False,
         "runOnSettle": False} for name, cmd in scripts]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "brief", "launch-request", "graph", "delegate", "actions"):
        sub = subparsers.add_parser(name)
        sub.add_argument("definition", help="Source-owned project-team JSON; never a runtime task store")
        if name != "graph":
            sub.add_argument("--definition-ref", help="Immutable GitHub reference for source-backed large teams")
        if name in {"brief", "launch-request", "actions"}:
            sub.add_argument("--project-id", required=True)
            sub.add_argument("--request-id", required=True)
        if name in {"launch-request", "actions"}:
            sub.add_argument("--environment-id", required=True)
        if name in {"graph", "delegate"}:
            sub.add_argument("--snapshot", required=name == "delegate",
                             help="Existing owner's retained bindings and current native reads")
        if name == "delegate":
            sub.add_argument("--parent-role", required=True)
            sub.add_argument("--child-role", required=True)
        if name == "actions":
            sub.add_argument("--launcher", required=True, help="Absolute path to the packaged CLI")
        if name in {"check", "brief", "launch-request", "actions"}:
            sub.add_argument("--project-plan", help="Assigned Markdown source plan relative to its workspace")
            sub.add_argument("--plan-workspace-root", help="Existing assigned workspace containing the plan")
            sub.add_argument("--plan-work-ref", help="Exact WS: selector; never an Executive root")
            sub.add_argument("--plan-source-ref", help="Immutable GitHub URL of that exact source plan")
            sub.add_argument("--plan-sha256", help="Expected SHA-256 of the exact source bytes")
    args = parser.parse_args(argv)
    try:
        team = parse_team(_read(args.definition, MAX_DOCUMENT_BYTES))
        plan_input = _project_plan_input(args)
        plan_context = plan_input.read_context() if plan_input is not None else None
        plan_source_ref = plan_input.source_ref if plan_input is not None else None
        plan_kwargs = {"project_context": plan_context, "project_source_ref": plan_source_ref}
        if args.command == "check":
            brief = team.root_handoff(project_id="preview-project", request_id="preview-request",
                                      definition_ref=args.definition_ref, **plan_kwargs)
            _emit({"valid": True, "schema": team.document()["schema"], "team_sha256": team.fingerprint,
                   "roles": len(team.roles), "max_depth": max(len(team.ancestors(r.role_id)) + 1 for r in team.roles),
                   "root_prompt_bytes": len(brief.render().encode()), "execution_authorized": False})
        elif args.command == "brief":
            print(team.root_handoff(project_id=args.project_id, request_id=args.request_id,
                                    definition_ref=args.definition_ref, **plan_kwargs).render(), end="")
        elif args.command == "launch-request":
            _emit(launch_request(team, project_id=args.project_id, request_id=args.request_id,
                                 environment_id=args.environment_id, definition_ref=args.definition_ref,
                                 **plan_kwargs))
        elif args.command in {"graph", "delegate"}:
            snapshot = _load_snapshot(args.snapshot)
            if args.command == "graph":
                snapshot.pop("evidence")
                _emit(project_graph(team, **snapshot))
            else:
                offer = prepare_delegation(team, parent_role_id=args.parent_role,
                                           child_role_id=args.child_role, definition_ref=args.definition_ref, **snapshot)
                _emit({"tool": "delegate_task", "arguments": offer.native_arguments(),
                       "offer": asdict(offer), "offer_sha256": offer.fingerprint,
                       "effect_state": "NOT_DISPATCHED", "execution_authorized": False})
        elif args.command == "actions":
            # Validate the complete eventual launch request before emitting a shell command.
            launch_request(team, project_id=args.project_id, request_id=args.request_id,
                           environment_id=args.environment_id, definition_ref=args.definition_ref,
                           **plan_kwargs)
            _emit(project_actions(definition=args.definition, launcher=args.launcher,
                                  project_id=args.project_id, request_id=args.request_id,
                                   environment_id=args.environment_id, definition_ref=args.definition_ref,
                                   project_plan=plan_input))
        return 0
    except TeamError as error:
        _emit({"error": str(error), "effect_state": "NOT_DISPATCHED"})
    except PlanContextError as error:
        _emit({"error": "TEAM_PROJECT_HELP_SOURCE_UNAVAILABLE", "reason": str(error),
               "effect_state": "NOT_DISPATCHED"})
    except (ValueError, TypeError, KeyError, OSError, RecursionError, UnicodeError, NativeUnavailable):
        _emit({"error": "TEAM_INPUT_OR_NATIVE_CONTRACT_INVALID", "effect_state": "NOT_DISPATCHED"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
