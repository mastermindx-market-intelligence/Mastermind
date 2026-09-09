from __future__ import annotations

import ast
import errno
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import scripts.validate_mastermind_plugins as plugin_validator
from scripts.validate_mastermind_plugins import VALIDATION_SCHEMA, validate_repository

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
CORTEX_SKILLS = ("orient-mastermind-mission",)


def _copy_package(destination: Path) -> None:
    shutil.copytree(ROOT / ".agents", destination / ".agents")
    shutil.copytree(ROOT / "plugins", destination / "plugins")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _validate_repository_twice_without_exception(root: Path) -> dict[str, object]:
    try:
        first = validate_repository(root)
        second = validate_repository(root)
    except Exception as error:
        pytest.fail(f"repository validator raised {type(error).__name__}: {error}")
    assert first == second
    serialized = json.dumps(first, sort_keys=True)
    assert str(root) not in serialized
    assert all(not error["path"].startswith("/") for error in first["errors"])  # type: ignore[index]
    return first


def _codes_without_exception(root: Path) -> set[str]:
    result = _validate_repository_twice_without_exception(root)
    return {error["code"] for error in result["errors"]}  # type: ignore[index]


def _replace_with_owned_symlink(path: Path, sibling_name: str) -> Path:
    """Move a fixture node aside and replace it with an owned sibling symlink."""
    sibling = path.parent / sibling_name
    path.rename(sibling)
    path.symlink_to(sibling, target_is_directory=True)
    return sibling


def _closed_json_document_paths() -> tuple[str, ...]:
    return (
        ".agents/plugins/marketplace.json",
        "plugins/mastermind-sol/.codex-plugin/plugin.json",
        "plugins/mastermind-operator/.codex-plugin/plugin.json",
        "plugins/mastermind-cortex/.codex-plugin/plugin.json",
        "plugins/mastermind-sol/references/app-bindings.template.json",
        "plugins/mastermind-operator/references/app-bindings.template.json",
        "plugins/mastermind-cortex/fixtures/orientation-cases.json",
    )


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
            {
                "name": "mastermind-cortex",
                "version": "0.1.0",
                "manifest": "plugins/mastermind-cortex/.codex-plugin/plugin.json",
                "skills": list(CORTEX_SKILLS),
            },
        ],
        "errors": [],
    }


def test_symlinked_repository_root_is_refused_before_package_content_is_opened(
    tmp_path: Path,
) -> None:
    """The supplied root itself is part of the no-follow trust boundary."""
    _copy_package(tmp_path)
    redirected_root = tmp_path.parent / "redirected-root"
    redirected_root.symlink_to(tmp_path, target_is_directory=True)

    result = _validate_repository_twice_without_exception(redirected_root)

    assert result["ok"] is False
    assert "SYMLINK_FORBIDDEN" in {error["code"] for error in result["errors"]}  # type: ignore[index]


def test_agents_ancestor_symlink_is_refused_before_its_marketplace_is_read(
    tmp_path: Path,
) -> None:
    """An owned sibling redirect is still outside the supplied lexical package tree."""
    _copy_package(tmp_path)
    _replace_with_owned_symlink(tmp_path / ".agents", "owned-agents")

    result = _validate_repository_twice_without_exception(tmp_path)

    assert result["ok"] is False
    assert "SYMLINK_FORBIDDEN" in {error["code"] for error in result["errors"]}  # type: ignore[index]


def test_descriptor_snapshot_refuses_missing_nofollow_capability_before_reading_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing a required descriptor flag must fail closed, not degrade to flag value zero."""
    monkeypatch.delattr(plugin_validator.os, "O_NOFOLLOW", raising=False)

    result = validate_repository(ROOT)

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("capability", ("supports_dir_fd", "supports_fd", "supports_follow_symlinks"))
def test_descriptor_snapshot_refuses_each_missing_descriptor_primitive(
    monkeypatch: pytest.MonkeyPatch, capability: str
) -> None:
    """Capability-set loss is rejected before package bytes are admitted."""
    monkeypatch.setattr(plugin_validator.os, capability, frozenset())

    result = validate_repository(ROOT)

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


def test_descriptor_snapshot_handles_unavailable_nofollow_stat_as_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A platform without no-follow stat support returns a validator refusal, never TypeError."""
    actual_stat = plugin_validator.os.stat

    def unavailable_stat(*args: object, **kwargs: object) -> os.stat_result:
        if kwargs.get("follow_symlinks") is False:
            raise TypeError("follow_symlinks unsupported")
        return actual_stat(*args, **kwargs)

    monkeypatch.setattr(plugin_validator.os, "stat", unavailable_stat)
    result = _validate_repository_twice_without_exception(ROOT)

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


def test_descriptor_snapshot_is_iterative_for_deep_unexpected_directories(tmp_path: Path) -> None:
    """Unexpected nesting must be classified without recursive traversal failure."""
    _copy_package(tmp_path)
    nested = tmp_path / "plugins/mastermind-cortex/deep"
    nested.mkdir()
    fd = os.open(nested, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for _index in range(1050):
            os.mkdir("d", dir_fd=fd)
            next_fd = os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    finally:
        os.close(fd)

    result = _validate_repository_twice_without_exception(tmp_path)

    assert result["ok"] is False
    assert "UNEXPECTED_PACKAGE_DIRECTORY" in {error["code"] for error in result["errors"]}


def test_descriptor_snapshot_returns_typed_error_for_directory_fstat_failure_without_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A descriptor opened before fstat failure belongs to the snapshot and is cleaned up."""
    actual_fstat = plugin_validator.os.fstat
    calls = 0

    def fail_one_directory_fstat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EIO, "injected fstat failure")
        return actual_fstat(fd)

    monkeypatch.setattr(plugin_validator.os, "fstat", fail_one_directory_fstat)
    try:
        result = validate_repository(ROOT)
    except Exception as error:
        pytest.fail(f"repository validator raised {type(error).__name__}: {error}")

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


def test_descriptor_snapshot_refuses_byte_identical_file_replacement_at_open_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing an inspected file before its descriptor open cannot preserve trusted bytes."""
    _copy_package(tmp_path)
    target = tmp_path / ".agents/plugins/marketplace.json"
    original_open = plugin_validator.os.open
    replaced = False

    def replace_before_open(name: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal replaced
        if name == "marketplace.json" and not replaced:
            replaced = True
            replacement = target.with_name("marketplace-replacement.json")
            target.rename(replacement)
            target.write_bytes(replacement.read_bytes())
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(plugin_validator.os, "open", replace_before_open)
    result = validate_repository(tmp_path)

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


def test_descriptor_snapshot_refuses_late_directory_entry_after_fd_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name added after the captured listing is found again during settlement."""
    _copy_package(tmp_path)
    original_listdir = plugin_validator.os.listdir
    injected = False

    def add_after_listdir(fd: int) -> list[str]:
        nonlocal injected
        names = original_listdir(fd)
        if not injected and "marketplace.json" in names:
            injected = True
            created = os.open("late.txt", os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=fd)
            try:
                os.write(created, b"late\n")
            finally:
                os.close(created)
        return names

    monkeypatch.setattr(plugin_validator.os, "listdir", add_after_listdir)
    result = validate_repository(tmp_path)

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


def test_descriptor_snapshot_settles_agents_link_after_semantic_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A late .agents replacement is a descriptor-graph change even after all parsing succeeds."""
    _copy_package(tmp_path)
    original_scan = plugin_validator._scan_files

    def replace_after_scan(root: Path, errors: list[dict[str, str]]) -> None:
        original_scan(root, errors)
        agents = root / ".agents"
        moved = root / "old-agents"
        agents.rename(moved)
        shutil.copytree(moved, agents)

    monkeypatch.setattr(plugin_validator, "_scan_files", replace_after_scan)
    result = validate_repository(tmp_path)

    assert result["ok"] is False
    assert "PACKAGE_FILESYSTEM_INVALID" in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("value", ([], {}))
def test_malformed_marketplace_plugin_name_is_invalid_marketplace_without_traceback(
    tmp_path: Path, value: object
) -> None:
    _copy_package(tmp_path)
    path = tmp_path / ".agents/plugins/marketplace.json"
    marketplace = json.loads(path.read_text(encoding="utf-8"))
    marketplace["plugins"][0]["name"] = value
    _write_json(path, marketplace)

    assert "INVALID_MARKETPLACE" in _codes_without_exception(tmp_path)


@pytest.mark.parametrize(
    ("plugin", "value"),
    (("mastermind-sol", None), ("mastermind-operator", 1)),
)
def test_malformed_template_bindings_is_invalid_template_without_traceback(
    tmp_path: Path, plugin: str, value: object
) -> None:
    _copy_package(tmp_path)
    path = tmp_path / f"plugins/{plugin}/references/app-bindings.template.json"
    template = json.loads(path.read_text(encoding="utf-8"))
    template["bindings"] = value
    _write_json(path, template)

    assert "INVALID_APP_TEMPLATE" in _codes_without_exception(tmp_path)


def test_repository_documents_match_the_closed_contract() -> None:
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert marketplace == {
        "name": "mastermind-x",
        "interface": {"displayName": "Mastermind-X"},
        "plugins": [
            {
                "name": "mastermind-sol",
                "source": {"source": "local", "path": "./plugins/mastermind-sol"},
            },
            {
                "name": "mastermind-operator",
                "source": {
                    "source": "local",
                    "path": "./plugins/mastermind-operator",
                },
            },
            {
                "name": "mastermind-cortex",
                "source": {
                    "source": "local",
                    "path": "./plugins/mastermind-cortex",
                },
            },
        ],
    }
    expected_bindings = {
        "mastermind-sol": [
            (
                "mastermind-steward",
                "integrations/mastermind_secretary_mcp/schemas.py",
            ),
            ("mastermind-executive", "integrations/executive_mcp/schemas.py"),
        ],
        "mastermind-operator": [
            ("mastermind-dialogue", "integrations/mastermind_company_mcp/schemas.py")
        ],
    }
    for plugin, display_name in (
        ("mastermind-sol", "Mastermind Sol"),
        ("mastermind-operator", "Mastermind Operator"),
    ):
        manifest = json.loads(
            (ROOT / "plugins" / plugin / ".codex-plugin/plugin.json").read_text()
        )
        assert set(manifest) == {
            "name",
            "version",
            "description",
            "author",
            "skills",
            "interface",
        }
        assert manifest["name"] == plugin
        assert manifest["version"] == "0.1.0"
        assert manifest["author"] == {"name": "Mastermind-X"}
        assert manifest["skills"] == "./skills/"
        assert manifest["interface"]["displayName"] == display_name
        assert manifest["interface"]["category"] == "Productivity"
        assert len(manifest["interface"]["longDescription"]) >= 80
        assert manifest["interface"]["capabilities"] == ["Read"]
        assert "apps" not in manifest and "mcpServers" not in manifest
        template = json.loads(
            (ROOT / "plugins" / plugin / "references/app-bindings.template.json").read_text()
        )
        assert template["schema"] == "mastermind.plugin_app_bindings_template.v1"
        assert template["plugin"] == plugin
        assert template["plugin_version"] == "0.1.0"
        assert template["generated_file"] == ".app.json"
        assert template["generated_by_wave"] == "BSC-U1"
        assert [
            (binding["logical_name"], binding["contract_owner"])
            for binding in template["bindings"]
        ] == expected_bindings[plugin]
        assert all(binding["required"] is True for binding in template["bindings"])
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
    assert "explicit current Chairman intent" in _sol("draft-ceo-intent")
    assert "current standing authorization may cover it" in _sol("draft-ceo-intent")
    assert "do not invent a redundant approval loop" in _sol("draft-ceo-intent")
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
    assert "Emit exactly one pickup `ACK`" in _operator("receive-commission")
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
        ("wrong_manifest_version", "INVALID_MANIFEST"),
        ("extra_skill_directory", "SKILL_SET_MISMATCH"),
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
    elif mutation == "missing_operator_gate":
        path = tmp_path / "plugins/mastermind-operator/skills/return-progress/SKILL.md"
        path.write_text(path.read_text().replace("one already-bound operation and dialogue", "work"))
    elif mutation == "wrong_manifest_version":
        value = json.loads(manifest.read_text())
        value["version"] = "0.2.0"
        _write_json(manifest, value)
    else:
        extra = tmp_path / "plugins/mastermind-sol/skills/unreviewed-extra/SKILL.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("---\nname: unreviewed-extra\ndescription: Extra.\n---\n\nExtra.\n")
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


def test_unexpected_package_file_is_refused(tmp_path: Path) -> None:
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-sol/hooks/hidden.py"
    path.parent.mkdir(parents=True)
    path.write_text("print('hidden')\n")
    result = validate_repository(tmp_path)
    assert "UNEXPECTED_PACKAGE_FILE" in {error["code"] for error in result["errors"]}


def test_package_symlink_is_refused(tmp_path: Path) -> None:
    _copy_package(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("outside\n")
    link = tmp_path / "plugins/mastermind-sol/references/linked.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = validate_repository(tmp_path)
    assert "SYMLINK_FORBIDDEN" in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize(
    "relative_path",
    (
        ".agents/plugins/marketplace.json",
        "plugins/mastermind-cortex/.codex-plugin/plugin.json",
        "plugins/mastermind-cortex/fixtures/orientation-cases.json",
        "plugins/mastermind-cortex/skills/orient-mastermind-mission/SKILL.md",
        "plugins/mastermind-cortex/references/orientation-contract.md",
        "plugins/mastermind-cortex/references/source-claim-tracing-examples.md",
    ),
)
def test_unreadable_required_package_files_return_stable_repository_relative_errors(
    tmp_path: Path, relative_path: str
) -> None:
    """A required-file permission failure must be a typed result, not an inventory crash."""
    _copy_package(tmp_path)
    path = tmp_path / relative_path
    original_mode = path.stat().st_mode
    path.chmod(0)
    try:
        codes = _codes_without_exception(tmp_path)
    finally:
        path.chmod(original_mode)

    assert "PACKAGE_FILESYSTEM_INVALID" in codes


@pytest.mark.parametrize(
    "relative_path",
    ("plugins", "plugins/mastermind-cortex/skills"),
    ids=("plugins-root", "cortex-skills-root"),
)
def test_unreadable_package_directories_return_stable_repository_relative_errors(
    tmp_path: Path, relative_path: str
) -> None:
    """Directory enumeration failures must be represented, never raised or skipped."""
    _copy_package(tmp_path)
    path = tmp_path / relative_path
    original_mode = path.stat().st_mode
    path.chmod(0)
    try:
        codes = _codes_without_exception(tmp_path)
    finally:
        path.chmod(original_mode)

    assert "PACKAGE_FILESYSTEM_INVALID" in codes


def test_skills_path_as_regular_file_returns_stable_repository_relative_error(tmp_path: Path) -> None:
    """The required skills directory is untrusted filesystem state, not a precondition."""
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-cortex/skills"
    shutil.rmtree(path)
    path.write_text("not-a-directory\n", encoding="utf-8")

    assert "PACKAGE_FILESYSTEM_INVALID" in _codes_without_exception(tmp_path)


def test_unreadable_unexpected_package_file_returns_stable_repository_relative_error(
    tmp_path: Path,
) -> None:
    """An unreadable unexpected file must produce a refusal rather than stop scanning."""
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-sol/references/unreadable-extra.txt"
    path.write_text("untrusted\n", encoding="utf-8")
    original_mode = path.stat().st_mode
    path.chmod(0)
    try:
        codes = _codes_without_exception(tmp_path)
    finally:
        path.chmod(original_mode)

    assert "PACKAGE_FILESYSTEM_INVALID" in codes


def test_unexpected_empty_package_directory_is_refused_without_exception(tmp_path: Path) -> None:
    """A closed package tree cannot silently accept an empty extra directory."""
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-cortex/hidden-empty"
    path.mkdir()
    try:
        assert "UNEXPECTED_PACKAGE_DIRECTORY" in _codes_without_exception(tmp_path)
    finally:
        path.rmdir()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO nodes are unavailable")
def test_unexpected_package_fifo_is_refused_without_opening_it(tmp_path: Path) -> None:
    """A validator must classify a FIFO, never open it or silently omit it."""
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-cortex/references/hidden.pipe"
    os.mkfifo(path)
    try:
        assert "PACKAGE_FILESYSTEM_INVALID" in _codes_without_exception(tmp_path)
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix-domain sockets are unavailable")
def test_unexpected_package_socket_is_refused_without_opening_it() -> None:
    """A validator must classify a socket node without treating it as package text."""
    root = Path(tempfile.mkdtemp(prefix="cortex-v9-", dir=os.path.realpath(tempfile.gettempdir())))
    _copy_package(root)
    path = root / "plugins/mastermind-cortex/references/hidden.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(path))
        assert "PACKAGE_FILESYSTEM_INVALID" in _codes_without_exception(root)
    finally:
        listener.close()
        path.unlink(missing_ok=True)
        shutil.rmtree(root)


@pytest.mark.parametrize(
    "relative_path",
    (
        ".agents/plugins",
        "plugins",
        "plugins/mastermind-cortex",
        "plugins/mastermind-sol/references",
        "plugins/mastermind-cortex/skills",
    ),
)
def test_unreadable_package_ancestors_preserve_filesystem_error_identity(
    tmp_path: Path, relative_path: str
) -> None:
    """Unreadable roots and ancestors are not equivalent to absent package content."""
    _copy_package(tmp_path)
    path = tmp_path / relative_path
    original_mode = path.stat().st_mode
    path.chmod(0)
    try:
        assert "PACKAGE_FILESYSTEM_INVALID" in _codes_without_exception(tmp_path)
    finally:
        path.chmod(original_mode)


@pytest.mark.parametrize(
    ("plugin", "binding_index", "numeric"),
    (
        ("mastermind-sol", 0, "1"),
        ("mastermind-sol", 0, "1.0"),
        ("mastermind-sol", 0, "1e0"),
        ("mastermind-sol", 1, "1"),
        ("mastermind-sol", 1, "1.0"),
        ("mastermind-sol", 1, "1e0"),
        ("mastermind-operator", 0, "1"),
        ("mastermind-operator", 0, "1.0"),
        ("mastermind-operator", 0, "1e0"),
    ),
)
def test_closed_template_required_boolean_rejects_each_numeric_alias(
    tmp_path: Path, plugin: str, binding_index: int, numeric: str
) -> None:
    """Closed template equality must not accept Python's bool/int aliases."""
    _copy_package(tmp_path)
    path = tmp_path / f"plugins/{plugin}/references/app-bindings.template.json"
    text = path.read_text(encoding="utf-8")
    needle = '"required": true'
    positions = [match.start() for match in re.finditer(re.escape(needle), text)]
    assert len(positions) > binding_index
    start = positions[binding_index]
    mutated = text[:start] + f'"required": {numeric}' + text[start + len(needle):]
    path.write_text(mutated, encoding="utf-8")

    assert "INVALID_APP_TEMPLATE" in _codes_without_exception(tmp_path)


def test_closed_json_scalar_alias_sweep_refuses_all_120_mutations(tmp_path: Path) -> None:
    """Every closed JSON Boolean leaf rejects the three numeric alias spellings."""
    _copy_package(tmp_path)
    mutations: list[tuple[Path, str, int, str]] = []
    for relative_path in _closed_json_document_paths():
        path = tmp_path / relative_path
        text = path.read_text(encoding="utf-8")
        for index, match in enumerate(re.finditer(r"\b(?:true|false)\b", text)):
            aliases = (
                ("1", "1.0", "1e0")
                if match.group() == "true"
                else ("0", "0.0", "0e0")
            )
            for numeric in aliases:
                mutations.append((path, text, index, numeric))
    assert len(mutations) == 120

    for path, original, index, numeric in mutations:
        matches = list(re.finditer(r"\b(?:true|false)\b", original))
        match = matches[index]
        path.write_text(original[:match.start()] + numeric + original[match.end():], encoding="utf-8")
        try:
            result = _validate_repository_twice_without_exception(tmp_path)
            assert result["ok"] is False
        finally:
            path.write_text(original, encoding="utf-8")


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
            "dataclasses",
            "errno",
            "json",
            "os",
            "re",
            "stat",
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

@pytest.mark.parametrize("skill", SOL_SKILLS)
def test_every_sol_skill_loads_authority_reference(skill: str) -> None:
    text = _sol(skill)
    assert "../../references/authority-boundaries.md" in text
    assert "before interpreting any app, record, or action as authority" in text


@pytest.mark.parametrize("skill", OPERATOR_SKILLS)
def test_every_operator_skill_loads_dialogue_reference(skill: str) -> None:
    text = _operator(skill)
    assert "../../references/dialogue-boundary.md" in text
    assert "before ACK, START, return, or STOP handling" in text


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ("\nCurrent decision is DEC:SECRET-DECISION.\n", "LIVE_STATE_FORBIDDEN"),
        ("\nCurrent workstream is WS:PRIVATE-WORK.\n", "LIVE_STATE_FORBIDDEN"),
        ("\nCurrent Linear issue is MAS-999.\n", "LIVE_STATE_FORBIDDEN"),
        ("\nCurrent pull request is #999.\n", "LIVE_STATE_FORBIDDEN"),
        ("\nDigest: " + "a" * 64 + "\n", "LIVE_STATE_FORBIDDEN"),
    ),
)
def test_additional_live_company_identities_are_refused(
    tmp_path: Path, content: str, expected: str
) -> None:
    _copy_package(tmp_path)
    target = tmp_path / "plugins/mastermind-sol/skills/bootstrap-mastermind/SKILL.md"
    target.write_text(target.read_text() + content)
    result = validate_repository(tmp_path)
    assert expected in {error["code"] for error in result["errors"]}

@pytest.mark.parametrize(
    ("plugin", "skills"),
    (("mastermind-sol", SOL_SKILLS), ("mastermind-operator", OPERATOR_SKILLS)),
)
def test_skill_descriptions_are_trigger_only(plugin: str, skills: tuple[str, ...]) -> None:
    for skill in skills:
        text = (ROOT / "plugins" / plugin / "skills" / skill / "SKILL.md").read_text()
        description = next(
            line.removeprefix("description: ")
            for line in text.splitlines()
            if line.startswith("description: ")
        )
        assert description.startswith("Use when ")


def test_validator_rejects_missing_package_reference(tmp_path: Path) -> None:
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-sol/skills/bootstrap-mastermind/SKILL.md"
    path.write_text(path.read_text().replace(
        "../../references/authority-boundaries.md",
        "missing-authority-reference.md",
    ))
    result = validate_repository(tmp_path)
    assert "PACKAGE_REFERENCE_MISSING" in {error["code"] for error in result["errors"]}


def test_validator_rejects_nontrigger_skill_description(tmp_path: Path) -> None:
    _copy_package(tmp_path)
    path = tmp_path / "plugins/mastermind-operator/skills/return-progress/SKILL.md"
    text = path.read_text()
    lines = text.splitlines()
    lines[2] = "description: Return progress through the bound operation."
    path.write_text("\n".join(lines) + "\n")
    result = validate_repository(tmp_path)
    assert "INVALID_SKILL_DESCRIPTION" in {error["code"] for error in result["errors"]}
