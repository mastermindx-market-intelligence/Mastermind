"""Offline, reporting-only inventory of declared GitHub workflow dependencies.

Reads local workflow files and writes JSON only to stdout. No network, subprocess,
workflow evaluation, settings changes, timing inference, or readiness verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path
import sys

import yaml

SCHEMA = "ci-workflow-inventory/1"
MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 500
MAX_NODES = 50000
MAX_DEPTH = 64
MAX_ALIASES = 100
EXPRESSION = "${{"
MATRIX_REFERENCE = re.compile(r"\bmatrix(?:\.([A-Za-z_][A-Za-z0-9_]*)|\[\s*(['\"])([A-Za-z_][A-Za-z0-9_-]*)\2\s*\])")
KNOWN_SHELLS = {"bash", "pwsh", "python", "sh", "cmd", "powershell"}


class InventoryError(ValueError):
    """Unsupported or incomplete source; never a readiness decision."""


class WorkflowLoader(yaml.SafeLoader):
    """Local YAML resolver: preserve the workflow key 'on' and reject duplicates."""


# Do not mutate PyYAML's process-global resolver. GitHub uses on/off as strings.
WorkflowLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in entries
          if tag != "tag:yaml.org,2002:bool"]
    for key, entries in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF")
)


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise yaml.constructor.ConstructorError(
                None, None, "merge keys require separate inspection", key_node.start_mark
            )
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                None, None, "mapping key must be scalar", key_node.start_mark
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None, "duplicate mapping key", key_node.start_mark
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


WorkflowLoader.add_constructor("tag:yaml.org,2002:map", _mapping)


def _bounded_graph(value):
    """Reject cyclic/oversized alias expansion before selecting output fields."""
    stack = [(value, 0, frozenset())]
    count = 0
    while stack:
        item, depth, ancestors = stack.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise InventoryError("document structure exceeds inspection limits")
        if isinstance(item, (dict, list)):
            identity = id(item)
            if identity in ancestors:
                raise InventoryError("recursive aliases require separate inspection")
            next_ancestors = ancestors | {identity}
            children = list(item.keys()) + list(item.values()) if isinstance(item, dict) else item
            stack.extend((child, depth + 1, next_ancestors) for child in children)


def _text(value, field):
    if not isinstance(value, str) or len(value) > 4096:
        raise InventoryError(f"{field}: expected bounded string")
    return value


def _strings(value, field):
    if isinstance(value, str):
        return [_text(value, field)]
    if not isinstance(value, list) or len(value) > 1000:
        raise InventoryError(f"{field}: expected string or string list")
    return [_text(item, field) for item in value]


def _scalar(value, field):
    if value is None or type(value) in (int, bool):
        return value
    if isinstance(value, str):
        return _text(value, field)
    if type(value) is float and math.isfinite(value):
        return value
    raise InventoryError(f"{field}: expected finite scalar")


def _permissions(value, source):
    if value is None:
        return {"source": source, "declared": None}
    if isinstance(value, str):
        return {"source": source, "declared": _text(value, "permissions")}
    if not isinstance(value, dict):
        raise InventoryError("permissions: expected mapping or string")
    return {"source": source, "declared": {
        _text(k, "permission name"): _text(v, "permission value") for k, v in value.items()
    }}


def _runner(value):
    if value is None:
        raise InventoryError("ordinary job is missing runs-on")
    if isinstance(value, dict):
        if not value or set(value) - {"group", "labels"}:
            raise InventoryError("runs-on: unsupported mapping")
        selector = {}
        if "group" in value:
            selector["group"] = _text(value["group"], "runner group")
        if "labels" in value:
            selector["labels"] = _strings(value["labels"], "runner labels")
        if not selector.get("group") and not selector.get("labels"):
            raise InventoryError("runs-on: empty group and labels")
        flat = [selector.get("group", "")] + selector.get("labels", [])
        kind = "dynamic" if any(EXPRESSION in item for item in flat) else "group_or_labels"
        return {"kind": kind, "selector": selector}
    labels = _strings(value, "runs-on")
    if not labels:
        raise InventoryError("runs-on: empty label list")
    if any(EXPRESSION in label for label in labels):
        kind = "dynamic"
    elif any(label.lower() == "self-hosted" for label in labels):
        kind = "self_hosted_labels"
    elif len(labels) == 1 and re.fullmatch(r"(?:ubuntu|windows|macos)-[A-Za-z0-9.+-]+", labels[0]):
        kind = "hosted_style_label"
    else:
        kind = "custom_labels"
    return {"kind": kind, "selector": value}


def _string_values(value):
    """Visit scalar strings after the document graph has passed its bounds."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def _matrix(job, runner):
    strategy = job.get("strategy", {})
    if not isinstance(strategy, dict):
        raise InventoryError("strategy: expected mapping")
    matrix = strategy.get("matrix")
    if matrix is None:
        return {"declared": False}
    if isinstance(matrix, str):
        return {"declared": True, "dynamic": True, "expression": _text(matrix, "matrix")}
    if not isinstance(matrix, dict):
        raise InventoryError("matrix: expected mapping or expression")
    axes = sorted(_text(k, "matrix axis") for k in matrix if k not in {"include", "exclude"})
    expression_text = " ".join(
        expression for selector in _string_values(runner.get("selector"))
        for expression in re.findall(r"\$\{\{(.*?)\}\}", selector, re.S)
    )
    referenced = sorted({match.group(1) or match.group(3)
                         for match in MATRIX_REFERENCE.finditer(expression_text)})
    unresolved = (["unsupported matrix reference syntax"]
                  if re.search(r"\bmatrix\b", MATRIX_REFERENCE.sub("", expression_text)) else [])
    choices = {}
    for key in referenced:
        values = []
        declared = matrix.get(key)
        if isinstance(declared, list):
            values.extend(declared)
        elif isinstance(declared, str):
            values.append(declared)
        elif key in matrix:
            choices[key] = {"unresolved": "unsupported routing axis"}
            continue
        included = matrix.get("include", [])
        if not isinstance(included, list) or any(not isinstance(row, dict) for row in included):
            choices[key] = {"unresolved": "include alternatives are not statically available"}
            continue
        values.extend(row[key] for row in included if key in row)
        # Report only scalar routing alternatives, never arbitrary matrix payloads.
        if not values:
            choices[key] = {"unresolved": "no declared routing alternatives"}
        elif any(not isinstance(v, (str, int, bool, float)) and v is not None for v in values):
            choices[key] = {"unresolved": "non-scalar routing alternatives"}
        else:
            choices[key] = [_scalar(v, "matrix runner choice") for v in values]
    return {
        "declared": True, "dynamic": any(EXPRESSION in value for value in _string_values(matrix)),
        "axes": axes, "runner_choices": choices,
        "unresolved_runner_references": unresolved,
        "include_count": len(matrix["include"]) if isinstance(matrix.get("include"), list) else None,
        "exclude_count": len(matrix["exclude"]) if isinstance(matrix.get("exclude"), list) else None,
        "max_parallel": _scalar(strategy.get("max-parallel"), "max-parallel"),
        "expansion": "not_evaluated",
    }


def inspect_workflow(text, path):
    """Return declared metadata only; supplied source is never executed."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise InventoryError("file exceeds inspection size limit")
    aliases = 0
    for token in yaml.scan(text):
        aliases += isinstance(token, yaml.tokens.AliasToken)
        if aliases > MAX_ALIASES:
            raise InventoryError("alias count exceeds inspection limit")
    try:
        workflow = yaml.load(text, Loader=WorkflowLoader)
    except (ValueError, TypeError, KeyError, OverflowError):
        # Safe constructors may raise ordinary Python errors containing source.
        raise InventoryError("invalid YAML scalar construction") from None
    _bounded_graph(workflow)
    if not isinstance(workflow, dict):
        raise InventoryError("workflow: expected mapping")
    triggers = workflow.get("on")
    if isinstance(triggers, dict):
        events = sorted(_text(key, "event") for key in triggers)
    elif isinstance(triggers, (str, list)):
        events = _strings(triggers, "on")
    else:
        raise InventoryError("workflow is missing a supported on declaration")
    raw_jobs = workflow.get("jobs")
    if not isinstance(raw_jobs, dict) or not raw_jobs:
        raise InventoryError("workflow is missing a nonempty jobs mapping")
    workflow_permissions = _permissions(workflow.get("permissions"), "workflow" if "permissions" in workflow else "external_default_unknown")
    jobs = []
    for job_id, job in raw_jobs.items():
        _text(job_id, "job id")
        if not isinstance(job, dict):
            raise InventoryError("job: expected mapping")
        reusable = job.get("uses")
        if reusable is not None:
            _text(reusable, "reusable workflow")
            if "runs-on" in job or "steps" in job:
                raise InventoryError("reusable job also declares runs-on or steps")
            runner = {"kind": "delegated", "selector": None}
        else:
            runner = _runner(job.get("runs-on"))
        steps = job.get("steps", [])
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise InventoryError("steps: expected list of mappings")
        actions, checkouts, shells, custom_shells = [], [], [], set()
        for step in steps:
            action = step.get("uses")
            if action is not None:
                actions.append(_text(action, "action reference"))
                if action.lower().startswith("actions/checkout@"):
                    inputs = step.get("with", {})
                    if not isinstance(inputs, dict):
                        raise InventoryError("checkout with: expected mapping")
                    repository = inputs.get("repository", "${{ github.repository }}")
                    checkouts.append({"repository": _text(repository, "checkout repository"),
                                      "explicit_token_input": "token" in inputs,
                                      "explicit_ssh_key_input": "ssh-key" in inputs,
                                      "access": "not_verified"})
            if "shell" in step:
                shell = _text(step["shell"], "shell")
                if shell in KNOWN_SHELLS:
                    shells.append(shell)
                else:
                    custom_shells.add(hashlib.sha256(shell.encode("utf-8")).hexdigest())
        environment = job.get("environment")
        if isinstance(environment, dict):
            environment = environment.get("name")
        if environment is not None:
            environment = _text(environment, "environment name")
        services = job.get("services", {})
        if not isinstance(services, dict):
            raise InventoryError("services: expected mapping")
        permissions = _permissions(job["permissions"], "job") if "permissions" in job else {
            "source": "inherited_workflow" if "permissions" in workflow else "external_default_unknown",
            "declared": workflow_permissions["declared"],
        }
        jobs.append({
            "id": job_id, "name": _text(job.get("name", job_id), "job name"),
            "needs": _strings(job["needs"], "needs") if "needs" in job else [],
            "conditional": "if" in job, "runner": runner, "matrix": _matrix(job, runner),
            "permissions": permissions, "reusable_workflow": reusable,
            "actions": sorted(set(actions)), "checkouts": checkouts,
            "environment": environment, "container_declared": "container" in job,
            "services": sorted(_text(k, "service name") for k in services),
            "step_shells": sorted(set(shells)), "custom_shell_template_sha256": sorted(custom_shells),
            "timeout_minutes": _scalar(job.get("timeout-minutes"), "timeout-minutes"),
            "concurrency_declared": "concurrency" in job,
        })
    return {"path": path, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "name": _text(workflow.get("name", path), "workflow name"), "events": events,
            "permissions": workflow_permissions, "concurrency_declared": "concurrency" in workflow,
            "jobs": jobs}


def build_inventory(root):
    root = Path(root)
    folder = root / ".github" / "workflows"
    report = {"schema": SCHEMA, "parser": {"library": "PyYAML", "version": yaml.__version__},
              "mode": "report_only", "workflows": [], "errors": [],
              "limitations": [
                  "source configuration only; workflow enablement and Git revision are not verified",
                  "runner labels do not prove registration, access, isolation, capacity or hosted billing",
                  "expressions, conditions and matrix expansion are not evaluated",
                  "partial structural inspection, not full workflow validity validation",
                  "selected names and selectors are source data; output is not a credential sanitizer",
                  "transitive actions, scripts, raw URLs, submodules and machine consumers are not inspected",
                  "no migration readiness, release authorization or security certification is inferred",
              ]}
    if (root / ".github").is_symlink() or folder.is_symlink() or not folder.is_dir():
        report["errors"].append({"path": ".github/workflows", "reason": "missing or symlinked workflow directory"})
        files = []
    else:
        try:
            files = sorted(p for p in folder.iterdir() if p.suffix in {".yml", ".yaml"})
        except OSError:
            files = []
            report["errors"].append({"path": ".github/workflows", "reason": "workflow directory unreadable"})
        if not files and not report["errors"]:
            report["errors"].append({"path": ".github/workflows", "reason": "no workflow files found"})
    discovered = len(files)
    if discovered > MAX_FILES:
        report["errors"].append({"path": ".github/workflows", "reason": "file count exceeds inspection limit"})
        files = files[:MAX_FILES]
    for file in files:
        relative = file.relative_to(root).as_posix()
        raw = None
        try:
            if file.is_symlink() or not file.is_file():
                raise InventoryError("workflow is not a regular non-symlink file")
            with file.open("rb") as handle:
                raw = handle.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise InventoryError("file exceeds inspection size limit")
            report["workflows"].append(inspect_workflow(raw.decode("utf-8"), relative))
        except (OSError, UnicodeDecodeError, InventoryError, yaml.YAMLError, RecursionError) as exc:
            error = {"path": relative, "reason": str(exc) if isinstance(exc, InventoryError) else type(exc).__name__}
            mark = getattr(exc, "problem_mark", None)
            if mark is not None:
                error["line"] = mark.line + 1
            if raw is not None and len(raw) <= MAX_FILE_BYTES:
                error["sha256"] = hashlib.sha256(raw).hexdigest()
            report["errors"].append(error)
    jobs = [job for workflow in report["workflows"] for job in workflow["jobs"]]
    report["coverage"] = {"discovered_files": discovered, "inspected_files": len(report["workflows"]),
                          "error_count": len(report["errors"]), "complete": not report["errors"]}
    report["summary"] = {"declared_jobs": len(jobs), "runner_kinds": dict(sorted(Counter(job["runner"]["kind"] for job in jobs).items()))}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository snapshot to inspect")
    args = parser.parse_args(argv)
    report = build_inventory(args.root)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["coverage"]["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
