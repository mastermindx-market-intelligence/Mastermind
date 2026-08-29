from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validate_mastermind_plugins import (
    MANIFESTS,
    MARKETPLACE,
    TEMPLATES,
    VALIDATION_SCHEMA,
    validate_repository,
)

ROOT = Path(__file__).resolve().parents[1]
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


def _copy_package(destination: Path) -> None:
    shutil.copytree(ROOT / ".agents", destination / ".agents")
    shutil.copytree(ROOT / "plugins", destination / "plugins")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sol(name: str) -> str:
    return (ROOT / "plugins/mastermind-sol/skills" / name / "SKILL.md").read_text(
        encoding="utf-8"
    )


def _operator(name: str) -> str:
    return (ROOT / "plugins/mastermind-operator/skills" / name / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_repository_plugin_package_is_valid() -> None:
    result = validate_repository(ROOT)
    assert result == {
        "schema": VALIDATION_SCHEMA,
        "ok": True,
        "marketplace": ".agents/plugins/marketplace.json",
        "plugins": [
            {
                "name": "mastermind-sol",
                "version": "0.1.0",
                "manifest": "plugins/mastermind-sol/.codex-plugin/plugin.json",
                "skills": list(SOL_SKILLS),
            },
            {
                "name": "mastermind-operator",
                "version": "0.1.0",
                "manifest": "plugins/mastermind-operator/.codex-plugin/plugin.json",
                "skills": list(OPERATOR_SKILLS),
            },
        ],
        "errors": [],
    }


def test_repository_documents_match_the_closed_contract() -> None:
    assert json.loads((ROOT / ".agents/plugins/marketplace.json").read_text()) == MARKETPLACE
    for plugin in ("mastermind-sol", "mastermind-operator"):
        manifest = json.loads(
            (ROOT / "plugins" / plugin / ".codex-plugin/plugin.json").read_text()
        )
        expected = MANIFESTS[plugin]
        assert manifest["name"] == expected["name"]
        assert manifest["version"] == "0.1.0"
        assert manifest["author"] == {"name": "Mastermind-X"}
        assert manifest["skills"] == "./skills/"
        assert manifest["interface"]["displayName"] == expected["interface"]["displayName"]
        assert len(manifest["interface"]["longDescription"]) >= 80
        assert manifest["interface"]["capabilities"] == ["Read"]
        assert "apps" not in manifest and "mcpServers" not in manifest
        template = json.loads(
            (ROOT / "plugins" / plugin / "references/app-bindings.template.json").read_text()
        )
        assert template == TEMPLATES[plugin]
        assert all(binding["app_id"] is None for binding in template["bindings"])


@pytest.mark.parametrize("skill", SOL_SKILLS)
def test_every_sol_skill_has_dynamic_current_source_gate(skill: str) -> None:
    text = _sol(skill)
    for marker in (
        "## Mandatory current-source gate",
        "Read protected Mastermind `master`",
        "docs/sol_skills/INDEX.md",
        "same exact commit",
        "modifying workflow is unavailable",
    ):
        assert marker in text


@pytest.mark.parametrize("skill", OPERATOR_SKILLS)
def test_every_operator_skill_requires_one_bound_operation(skill: str) -> None:
    text = _operator(skill)
    assert "one already-bound operation and dialogue" in text
    assert (
        "never choose actor, Job, Attempt, Worker, provider, account, host, channel, or thread"
        in text
    )


def test_key_workflow_semantics_are_explicit() -> None:
    assert "STEWARD_APP_UNAVAILABLE" in _sol("open-executive-cockpit")
    assert "do not infer healthy state from absence" in _sol("open-executive-cockpit")
    assert "Do not majority-vote among sources" in _sol("reconcile-company-state")
    assert "EFFECT_UNKNOWN" in _sol("reconcile-company-state")
    assert "explicit current Chairman confirmation" in _sol("draft-ceo-intent")
    assert "QUEUED is not dispatched or executing" in _sol("draft-ceo-intent")
    assert "never supply raw authority" in _sol("draft-ceo-intent")
    assert "original user and machine outcome" in _sol("review-worker-return")
    assert "CI green is not acceptance" in _sol("review-worker-return")
    assert "one explicit continuation, repair, or STOP edge" in _sol("review-worker-return")
    assert "exact immutable head" in _sol("review-pull-request")
    assert "changed-path census" in _sol("review-pull-request")
    assert "Do not merge from this skill" in _sol("review-pull-request")
    assert "No generic save-memory action exists" in _sol("close-out-program")
    assert "Agent OS through a reviewed Git carrier" in _sol("close-out-program")
    assert "explicit terminal STOP" in _sol("close-out-program")
    assert "Pickup ACK does not claim START" in _operator("receive-commission")
    assert "START only after gates clear" in _operator("receive-commission")
    assert "RESULT is not acceptance or STOP" in _operator("finish-operation")
    assert "await one explicit Sol CONTINUE, REQUEST_REPAIR, or STOP" in _operator(
        "finish-operation"
    )
    assert "never self-merge" in _operator("finish-operation")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("manifest_apps", "LIVE_APP_BINDING_FORBIDDEN"),
        ("manifest_mcp", "MCP_DECLARATION_FORBIDDEN"),
        ("installed_app_id", "INSTALLED_APP_ID_FORBIDDEN"),
        ("missing_sol_gate", "CURRENT_SOURCE_GATE_MISSING"),
        ("missing_operator_gate", "BOUND_OPERATION_GATE_MISSING"),
    ),
)
def test_structural_authority_mutations_are_refused(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    _copy_package(tmp_path)
    manifest = tmp_path / "plugins/mastermind-sol/.codex-plugin/plugin.json"
    template = tmp_path / "plugins/mastermind-sol/references/app-bindings.template.json"
    if mutation in {"manifest_apps", "manifest_mcp"}:
        value = json.loads(manifest.read_text())
        value["apps" if mutation == "manifest_apps" else "mcpServers"] = "forbidden"
        _write_json(manifest, value)
    elif mutation == "installed_app_id":
        value = json.loads(template.read_text())
        value["bindings"][0]["app_id"] = "asdk_app_not_allowed_in_p1"
        _write_json(template, value)
    elif mutation == "missing_sol_gate":
        (tmp_path / "plugins/mastermind-sol/skills/draft-ceo-intent/SKILL.md").write_text(
            "---\nname: draft-ceo-intent\ndescription: Broken.\n---\n\nDraft.\n"
        )
    else:
        path = tmp_path / "plugins/mastermind-operator/skills/return-progress/SKILL.md"
        path.write_text(path.read_text().replace("one already-bound operation and dialogue", "work"))
    result = validate_repository(tmp_path)
    assert result["ok"] is False
    assert expected_code in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("root_kind", ("marketplace", "plugin"))
@pytest.mark.parametrize("filename", (".app.json", "mcp.json", ".mcp.json"))
def test_live_binding_files_are_refused(
    tmp_path: Path, root_kind: str, filename: str
) -> None:
    _copy_package(tmp_path)
    parent = (
        tmp_path / ".agents/plugins"
        if root_kind == "marketplace"
        else tmp_path / "plugins/mastermind-sol"
    )
    (parent / filename).write_text("{}\n")
    result = validate_repository(tmp_path)
    expected = (
        "LIVE_APP_BINDING_FORBIDDEN"
        if filename == ".app.json"
        else "MCP_DECLARATION_FORBIDDEN"
    )
    assert expected in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    (
        (
            "plugins/mastermind-sol/skills/bootstrap-mastermind/SKILL.md",
            "\nCurrent job is JOB-991.\n",
            "LIVE_STATE_FORBIDDEN",
        ),
        (
            "plugins/mastermind-sol/references/authority-boundaries.md",
            "\nToken xoxb-not-a-real-token\n",
            "SECRET_MARKER_FORBIDDEN",
        ),
        (
            "plugins/mastermind-operator/skills/return-progress/SKILL.md",
            "\nSearch all Slack and post to any channel.\n",
            "GENERIC_OPERATOR_AUTHORITY_FORBIDDEN",
        ),
    ),
)
def test_forbidden_package_text_is_refused(
    tmp_path: Path, path: str, content: str, expected: str
) -> None:
    _copy_package(tmp_path)
    target = tmp_path / path
    target.write_text(target.read_text() + content)
    result = validate_repository(tmp_path)
    assert expected in {error["code"] for error in result["errors"]}


def test_invalid_json_error_is_repository_relative(tmp_path: Path) -> None:
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-sol/.codex-plugin/plugin.json"
    path.write_text("{not-json}\n")
    result = validate_repository(tmp_path)
    assert result["ok"] is False
    assert str(tmp_path) not in json.dumps(result)
    assert all(not error["path"].startswith("/") for error in result["errors"])


def test_cli_receipt_is_deterministic_and_secret_free() -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/validate_mastermind_plugins.py"),
        "--root",
        str(ROOT),
        "--json",
    ]
    first = subprocess.run(command, check=False, capture_output=True, text=True)
    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["ok"] is True and result["errors"] == []
    assert "generated_at" not in result
    for marker in ("xoxb-", "ghp_", "sk-proj-", "BEGIN PRIVATE KEY"):
        assert marker not in first.stdout


def test_validator_is_stdlib_only_and_has_no_action_surface() -> None:
    path = ROOT / "scripts/validate_mastermind_plugins.py"
    text = path.read_text()
    tree = ast.parse(text, filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported <= {
        "__future__",
        "argparse",
        "json",
        "re",
        "sys",
        "pathlib",
        "typing",
    }
    for forbidden in (
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
        "subprocess.",
        "sqlite3.",
        "keyring.",
        "control_plane.",
        "integrations.",
        "os.system",
        "Popen(",
    ):
        assert forbidden not in text
