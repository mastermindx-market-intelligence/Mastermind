#!/usr/bin/env python3
"""Validate the production-inert BSC-P1 skills-only plugin packages."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

VALIDATION_SCHEMA = "mastermind.plugin_package_validation.v1"
MARKETPLACE_PATH = Path(".agents/plugins/marketplace.json")
PLUGIN_VERSION = "0.1.0"

SOL_SKILLS = (
    "bootstrap-mastermind",
    "open-executive-cockpit",
    "reconcile-company-state",
    "draft-ceo-intent",
    "review-worker-return",
    "review-pull-request",
    "close-out-program",
)
OPERATOR_SKILLS = (
    "receive-commission",
    "return-progress",
    "escalate-decision",
    "finish-operation",
)
EXPECTED_SKILLS = {
    "mastermind-sol": SOL_SKILLS,
    "mastermind-operator": OPERATOR_SKILLS,
}

MARKETPLACE = {
    "name": "mastermind-x",
    "interface": {"displayName": "Mastermind-X"},
    "plugins": [
        {
            "name": "mastermind-sol",
            "source": {"source": "local", "path": "./plugins/mastermind-sol"},
        },
        {
            "name": "mastermind-operator",
            "source": {"source": "local", "path": "./plugins/mastermind-operator"},
        },
    ],
}

MANIFESTS = {
    "mastermind-sol": {
        "name": "mastermind-sol",
        "version": PLUGIN_VERSION,
        "description": (
            "Governed Chairman and Sol workflows for current-source recovery, "
            "company-state reconciliation, bounded CEO-intent drafting, return review, "
            "pull-request review, and durable closeout."
        ),
        "author": {"name": "Mastermind-X"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Mastermind Sol",
            "shortDescription": "Governed Chairman and Sol operating workflows",
            "longDescription": (
                "Recover current Mastermind truth, reconcile company state, draft bounded "
                "CEO intent, review returns and pull requests, and close out accepted work "
                "without creating another control plane."
            ),
            "developerName": "Mastermind-X",
            "category": "Productivity",
            "capabilities": ["Read"],
        },
    },
    "mastermind-operator": {
        "name": "mastermind-operator",
        "version": PLUGIN_VERSION,
        "description": (
            "Governed operator workflows for receiving one bound commission, returning "
            "progress, escalating a decision, and finishing one operation without generic "
            "Slack or lifecycle authority."
        ),
        "author": {"name": "Mastermind-X"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Mastermind Operator",
            "shortDescription": "Bound operator and company-dialogue workflows",
            "longDescription": (
                "Receive one already-bound operation, return progress or a decision request, "
                "and finish the operation through the governed company-dialogue lifecycle "
                "without generic Slack or runtime authority."
            ),
            "developerName": "Mastermind-X",
            "category": "Productivity",
            "capabilities": ["Read"],
        },
    },
}

TEMPLATES = {
    "mastermind-sol": {
        "schema": "mastermind.plugin_app_bindings_template.v1",
        "plugin": "mastermind-sol",
        "plugin_version": PLUGIN_VERSION,
        "generated_file": ".app.json",
        "generated_by_wave": "BSC-U1",
        "bindings": [
            {
                "logical_name": "mastermind-steward",
                "required": True,
                "contract_owner": "integrations/mastermind_secretary_mcp/schemas.py",
                "app_id": None,
            },
            {
                "logical_name": "mastermind-executive",
                "required": True,
                "contract_owner": "integrations/executive_mcp/schemas.py",
                "app_id": None,
            },
        ],
    },
    "mastermind-operator": {
        "schema": "mastermind.plugin_app_bindings_template.v1",
        "plugin": "mastermind-operator",
        "plugin_version": PLUGIN_VERSION,
        "generated_file": ".app.json",
        "generated_by_wave": "BSC-U1",
        "bindings": [
            {
                "logical_name": "mastermind-dialogue",
                "required": True,
                "contract_owner": "integrations/mastermind_company_mcp/schemas.py",
                "app_id": None,
            }
        ],
    },
}

REFERENCES = {
    "mastermind-sol": "authority-boundaries.md",
    "mastermind-operator": "dialogue-boundary.md",
}

ALLOWED_PACKAGE_FILES = frozenset(
    {MARKETPLACE_PATH.as_posix()}
    | {
        f"plugins/{plugin}/.codex-plugin/plugin.json"
        for plugin in EXPECTED_SKILLS
    }
    | {
        f"plugins/{plugin}/references/app-bindings.template.json"
        for plugin in EXPECTED_SKILLS
    }
    | {
        f"plugins/{plugin}/references/{reference}"
        for plugin, reference in REFERENCES.items()
    }
    | {
        f"plugins/{plugin}/skills/{skill}/SKILL.md"
        for plugin, skills in EXPECTED_SKILLS.items()
        for skill in skills
    }
)
SOL_GATE_MARKERS = (
    "Read protected Mastermind `master`",
    "`docs/sol_skills/INDEX.md`",
    "same exact commit",
    "modifying workflow is unavailable",
)
FORBIDDEN_FILES = {
    ".app.json": "LIVE_APP_BINDING_FORBIDDEN",
    "mcp.json": "MCP_DECLARATION_FORBIDDEN",
    ".mcp.json": "MCP_DECLARATION_FORBIDDEN",
}
SECRET_MARKERS = (
    "xoxb-",
    "xoxp-",
    "ghp_",
    "github_pat_",
    "sk-proj-",
    "sk-ant-",
    "begin private key",
    "begin openssh private key",
)
GENERIC_OPERATOR_PHRASES = (
    "search all slack",
    "post to any channel",
    "choose a provider",
    "choose an account",
    "select another worker",
    "pick a slack thread",
    "impersonate chairman",
)
FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\nname: (?P<name>[^\n]+)\ndescription: (?P<description>[^\n]+)\n"
    r"---[ \t]*\n(?P<body>.*)\Z",
    re.DOTALL,
)
SHA_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
RUNTIME_ID_RE = re.compile(r"\b(?:JOB|ATT|WORKER)-[A-Za-z0-9._:-]+\b")
SLACK_CHANNEL_RE = re.compile(r"\bC[A-Z0-9]{8,}\b")
SLACK_TS_RE = re.compile(r"\b\d{10}\.\d{6}\b")
APP_ID_RE = re.compile(r"\b(?:asdk_app|connector|templated_apps|plugin)_[A-Za-z0-9_-]+\b")


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "<outside-root>"


def _error(root: Path, path: Path, code: str, message: str) -> dict[str, str]:
    return {"path": _relative(root, path), "code": code, "message": message}


def _json(root: Path, path: Path, errors: list[dict[str, str]]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(_error(root, path, "MISSING_FILE", "required file is absent"))
    except UnicodeDecodeError:
        errors.append(_error(root, path, "INVALID_UTF8", "file is not UTF-8"))
    except json.JSONDecodeError:
        errors.append(_error(root, path, "INVALID_JSON", "file is not valid JSON"))
    return None


def _require_exact(
    root: Path,
    path: Path,
    actual: Any,
    expected: Any,
    code: str,
    errors: list[dict[str, str]],
) -> None:
    if actual != expected:
        errors.append(_error(root, path, code, "document differs from the closed BSC-P1 contract"))

MANIFEST_KEYS = {"name", "version", "description", "author", "skills", "interface"}
INTERFACE_KEYS = {
    "displayName", "shortDescription", "longDescription", "developerName",
    "category", "capabilities",
}


def _validate_manifest(
    root: Path, path: Path, plugin: str, manifest: Any, errors: list[dict[str, str]]
) -> None:
    if not isinstance(manifest, Mapping) or set(manifest) != MANIFEST_KEYS:
        errors.append(_error(root, path, "INVALID_MANIFEST", "manifest keys differ from the closed BSC-P1 contract"))
        return
    expected = MANIFESTS[plugin]
    for field in ("name", "version", "author", "skills"):
        if manifest[field] != expected[field]:
            errors.append(_error(root, path, "INVALID_MANIFEST", f"manifest {field} differs from the closed BSC-P1 contract"))
    if not isinstance(manifest["description"], str) or not manifest["description"].strip():
        errors.append(_error(root, path, "INVALID_MANIFEST", "description must be non-empty text"))
    interface = manifest["interface"]
    if not isinstance(interface, Mapping) or set(interface) != INTERFACE_KEYS:
        errors.append(_error(root, path, "INVALID_MANIFEST", "interface keys differ from the closed BSC-P1 contract"))
        return
    for field in ("displayName", "developerName", "category", "capabilities"):
        if interface[field] != expected["interface"][field]:
            errors.append(_error(root, path, "INVALID_MANIFEST", f"interface {field} differs from the closed BSC-P1 contract"))
    for field in ("shortDescription", "longDescription"):
        if not isinstance(interface[field], str) or not interface[field].strip():
            errors.append(_error(root, path, "INVALID_MANIFEST", f"interface {field} must be non-empty text"))
    if isinstance(interface["longDescription"], str) and len(interface["longDescription"]) < 80:
        errors.append(_error(root, path, "INVALID_MANIFEST", "interface longDescription must be at least 80 characters"))


def _validate_skill(
    root: Path,
    path: Path,
    plugin: str,
    name: str,
    errors: list[dict[str, str]],
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(_error(root, path, "MISSING_SKILL", "required SKILL.md is absent"))
        return
    except UnicodeDecodeError:
        errors.append(_error(root, path, "INVALID_UTF8", "file is not UTF-8"))
        return
    match = FRONTMATTER_RE.match(text)
    if match is None or match.group("name") != name or not match.group("description").strip():
        errors.append(
            _error(
                root,
                path,
                "INVALID_SKILL_FRONTMATTER",
                "frontmatter must contain the exact name and one-line description",
            )
        )
        return
    body = match.group("body")
    if plugin == "mastermind-sol":
        missing = [marker for marker in SOL_GATE_MARKERS if marker not in body]
        if missing:
            errors.append(
                _error(
                    root,
                    path,
                    "CURRENT_SOURCE_GATE_MISSING",
                    f"Sol skill is missing current-source marker(s): {missing}",
                )
            )
    elif "one already-bound operation and dialogue" not in body:
        errors.append(
            _error(
                root,
                path,
                "BOUND_OPERATION_GATE_MISSING",
                "Operator skill must require one already-bound operation and dialogue",
            )
        )


def _package_files(root: Path, errors: list[dict[str, str]]) -> list[Path]:
    paths: set[Path] = set()
    for package_root in (root / ".agents/plugins", root / "plugins"):
        if not package_root.exists():
            continue
        for path in package_root.rglob("*"):
            if path.is_symlink():
                errors.append(
                    _error(
                        root,
                        path,
                        "SYMLINK_FORBIDDEN",
                        "plugin packages may not contain symbolic links",
                    )
                )
            elif path.is_file():
                paths.add(path)
    return sorted(paths, key=lambda path: _relative(root, path))


def _scan_files(root: Path, errors: list[dict[str, str]]) -> None:
    templates = {
        (root / "plugins" / plugin / "references/app-bindings.template.json").resolve()
        for plugin in EXPECTED_SKILLS
    }
    for path in _package_files(root, errors):
        relative = _relative(root, path)
        if relative not in ALLOWED_PACKAGE_FILES:
            errors.append(
                _error(
                    root,
                    path,
                    "UNEXPECTED_PACKAGE_FILE",
                    "file is outside the closed BSC-P1 package inventory",
                )
            )
        forbidden_code = FORBIDDEN_FILES.get(path.name)
        if forbidden_code:
            errors.append(
                _error(root, path, forbidden_code, f"{path.name} is forbidden in skills-only P1")
            )
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(_error(root, path, "INVALID_UTF8", "file is not UTF-8"))
            continue
        lowered = text.casefold()
        if any(marker in lowered for marker in SECRET_MARKERS):
            errors.append(
                _error(root, path, "SECRET_MARKER_FORBIDDEN", "secret-shaped marker is forbidden")
            )
        if APP_ID_RE.search(text) and path.resolve() not in templates:
            errors.append(
                _error(root, path, "INSTALLED_APP_ID_FORBIDDEN", "installed app identifier is forbidden")
            )
        if SHA_RE.search(text) or RUNTIME_ID_RE.search(text) or SLACK_CHANNEL_RE.search(text) or SLACK_TS_RE.search(text):
            errors.append(
                _error(root, path, "LIVE_STATE_FORBIDDEN", "live repository, runtime, or transport identity is forbidden")
            )
        if "mastermind-operator" in path.parts:
            for phrase in GENERIC_OPERATOR_PHRASES:
                if phrase in lowered:
                    errors.append(
                        _error(
                            root,
                            path,
                            "GENERIC_OPERATOR_AUTHORITY_FORBIDDEN",
                            f"generic operator authority phrase is forbidden: {phrase}",
                        )
                    )


def validate_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[dict[str, str]] = []
    marketplace_path = root / MARKETPLACE_PATH
    _require_exact(root, marketplace_path, _json(root, marketplace_path, errors), MARKETPLACE, "INVALID_MARKETPLACE", errors)
    plugin_rows: list[dict[str, Any]] = []

    for plugin, skills in EXPECTED_SKILLS.items():
        plugin_root = root / "plugins" / plugin
        manifest_path = plugin_root / ".codex-plugin/plugin.json"
        manifest = _json(root, manifest_path, errors)
        if isinstance(manifest, Mapping):
            if "apps" in manifest:
                errors.append(
                    _error(root, manifest_path, "LIVE_APP_BINDING_FORBIDDEN", "P1 manifests must not reference .app.json")
                )
            if "mcpServers" in manifest or "mcp_servers" in manifest:
                errors.append(
                    _error(root, manifest_path, "MCP_DECLARATION_FORBIDDEN", "P1 manifests must not declare MCP servers")
                )
        _validate_manifest(root, manifest_path, plugin, manifest, errors)

        template_path = plugin_root / "references/app-bindings.template.json"
        template = _json(root, template_path, errors)
        if isinstance(template, Mapping):
            for binding in template.get("bindings", []):
                if isinstance(binding, Mapping) and binding.get("app_id") is not None:
                    errors.append(
                        _error(root, template_path, "INSTALLED_APP_ID_FORBIDDEN", "P1 symbolic app bindings require app_id null")
                    )
        _require_exact(root, template_path, template, TEMPLATES[plugin], "INVALID_APP_TEMPLATE", errors)

        reference_path = plugin_root / "references" / REFERENCES[plugin]
        try:
            if not reference_path.read_text(encoding="utf-8").strip():
                errors.append(_error(root, reference_path, "EMPTY_REFERENCE", "reference file is empty"))
        except FileNotFoundError:
            errors.append(_error(root, reference_path, "MISSING_FILE", "required reference is absent"))
        except UnicodeDecodeError:
            errors.append(_error(root, reference_path, "INVALID_UTF8", "file is not UTF-8"))

        skills_root = plugin_root / "skills"
        actual = sorted(path.name for path in skills_root.iterdir() if path.is_dir()) if skills_root.exists() else []
        if actual != sorted(skills):
            errors.append(
                _error(root, skills_root, "SKILL_SET_MISMATCH", f"skill directories must be exactly {sorted(skills)}; got {actual}")
            )
        for name in skills:
            _validate_skill(root, skills_root / name / "SKILL.md", plugin, name, errors)
        plugin_rows.append(
            {
                "name": plugin,
                "version": PLUGIN_VERSION,
                "manifest": _relative(root, manifest_path),
                "skills": list(skills),
            }
        )

    _scan_files(root, errors)
    errors.sort(key=lambda item: (item["path"], item["code"], item["message"]))
    return {
        "schema": VALIDATION_SCHEMA,
        "ok": not errors,
        "marketplace": MARKETPLACE_PATH.as_posix(),
        "plugins": plugin_rows,
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = validate_repository(Path(args.root))
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        for error in result["errors"]:
            print(f"{error['path']}: [{error['code']}] {error['message']}")
        print("PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
