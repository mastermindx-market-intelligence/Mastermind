"""Actual Git objects and retained canonical parser; no company publication."""
import base64
import copy
import hashlib
import json
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from common.executive_workspace_contract import canonical
from common.workspace_project_session_contract import validate_source_observation
from control_plane.agentos_project_creation_source import read_from_macro_owner, AgentOsProjectCreationReader

FIXTURES = Path(__file__).parent / "fixtures"


def git(root, *args, input=None):
    return subprocess.run(["git", "-C", str(root), *args], input=input, text=True,
        capture_output=True, check=True).stdout.strip()


@pytest.fixture
def source(tmp_path):
    captured = json.loads((FIXTURES / "agentos-project-plan-parser-ed12006d.json").read_bytes())
    parser = zlib.decompress(base64.b64decode(captured["zlib_base64"], validate=True))
    assert hashlib.sha256(parser).hexdigest() == captured["sha256"]
    root = tmp_path / "macro"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic source fixture")
    git(root, "config", "user.email", "source-fixture@example.test")
    (root / "scripts").mkdir()
    (root / "scripts/agentos.py").write_bytes(parser)
    (root / "config").mkdir()
    (root / "config/mastermind_programs.yml").write_text("programs:\n  project-active-build-control: {}\n")
    git(root, "add", "scripts/agentos.py", "config/mastermind_programs.yml")
    git(root, "commit", "-qm", "Synthetic canonical parser base")
    base = git(root, "rev-parse", "HEAD")
    fixture = json.loads((FIXTURES / "project-authoring-proposal.json").read_text())
    request = copy.deepcopy(fixture["request"])
    request["expected_commit"] = base
    request_sha = hashlib.sha256(canonical(request)).hexdigest()
    content = fixture["proposal"]["content_utf8"].replace(
        "expected_commit: " + fixture["request"]["expected_commit"], "expected_commit: " + base).replace(
        "request_sha256: " + fixture["proposal"]["request_sha256"], "request_sha256: " + request_sha)
    path = fixture["proposal"]["path"]
    record = root / path
    record.parent.mkdir(parents=True)
    record.write_text(content)
    git(root, "add", path)
    git(root, "commit", "-qm", "Synthetic proposed workstream publication")
    return root, path, request_sha


def read(source):
    root, _, _ = source
    return read_from_macro_owner(macro_root=root, expected_macro_sha=git(root, "rev-parse", "HEAD"),
        work_ref="WS:SYNTHETIC-PROJECT")


def test_exact_git_source_and_actual_canonical_parser_qualify_request_origin(source):
    root, path, request_sha = source
    result = read(source)
    assert result == {"repository": "macro", "commit": git(root, "rev-parse", "HEAD"), "path": path,
        "request_sha256": request_sha, "content_sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
    assert "目标" not in json.dumps(result) and "synthetic-author" not in json.dumps(result)
    # Working-copy edits are never substituted for immutable source bytes.
    (root / path).write_text("Uncommitted foreign source")
    assert read(source) == result


@pytest.mark.parametrize("change", ["goal", "origin", "duplicate", "unknown_program", "symlink"])
def test_source_goal_marker_catalogue_and_file_shape_cannot_be_substituted(source, change):
    root, path, _ = source
    target = root / path
    text = target.read_text()
    if change == "goal":
        target.write_text(text.replace("Preserve this literal goal.", "A substituted goal."))
    elif change == "origin":
        target.write_text(text.replace("request_sha256: ", "request_sha256: f"))
    elif change == "duplicate":
        target.write_text(text + text[text.index("<!--"):])
    elif change == "unknown_program":
        (root / "config/mastermind_programs.yml").write_text("programs:\n  other-program: {}\n")
        git(root, "add", "config/mastermind_programs.yml")
    else:
        target.unlink()
        target.symlink_to("/unreadable/synthetic-owner-record")
    git(root, "add", path)
    git(root, "commit", "-qm", "Synthetic invalid source postimage")
    with pytest.raises(ValueError):
        read(source)


def test_head_drift_is_not_repaired_to_another_source_commit(source):
    root, _, _ = source
    with pytest.raises(ValueError, match="source_changed"):
        read_from_macro_owner(macro_root=root, expected_macro_sha="f" * 40, work_ref="WS:SYNTHETIC-PROJECT")


def test_root_creation_provenance_survives_later_macro_commits_without_borrowing_today_goal(source):
    root, path, _ = source
    original = read(source)
    (root / path).write_text((root / path).read_text().replace("Preserve this literal goal.", "Today's changed goal."))
    git(root, "add", path)
    git(root, "commit", "-qm", "Synthetic later source revision")
    result = read_from_macro_owner(macro_root=root, expected_macro_sha=git(root, "rev-parse", "HEAD"),
        record_commit=original["commit"], work_ref="WS:SYNTHETIC-PROJECT")
    assert result == original


def test_caller_cannot_supply_an_arbitrary_source_path(source):
    root, _, _ = source
    with pytest.raises(ValueError):
        read_from_macro_owner(macro_root=root, expected_macro_sha=git(root, "rev-parse", "HEAD"),
            work_ref="WS:../../foreign")


def test_a_caller_constructed_facade_has_no_installed_source_owner(source):
    root, _, _ = source
    with pytest.raises(ValueError, match="source_unavailable"):
        AgentOsProjectCreationReader(macro_root=root).read(work_ref="WS:SYNTHETIC-PROJECT",
            record_commit=git(root, "rev-parse", "HEAD"))


@pytest.mark.parametrize("site_available", [True, False])
def test_real_isolated_child_emits_only_closed_json_including_owner_dependency_failure(source, site_available):
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    root, _, _ = source
    interpreter = str(PYTHON_BINARY) if site_available and Path(PYTHON_BINARY).is_file() else sys.executable
    entry = Path(__file__).parents[1] / "scripts/agentos_project_creation_source_entry.py"
    current = git(root, "rev-parse", "HEAD")
    command = [interpreter, "-I", "-B"] + ([] if site_available else ["-S"])
    result = subprocess.run([*command, str(entry), "--macro-root", str(root), "--expected-macro-sha", current,
        "--record-commit", current, "--work-ref", "WS:SYNTHETIC-PROJECT"], capture_output=True, text=True, check=True)
    body = json.loads(result.stdout)
    assert validate_source_observation(body, work_ref="WS:SYNTHETIC-PROJECT", record_commit=current) == body
    assert result.stderr == ""
    assert set(body) == {"schema", "work_ref", "availability", "source", "reason"}
    assert body["schema"] == "mastermind.agentos_project_creation_source.v1"
    assert len(result.stdout.encode()) <= 4096
    if site_available:
        assert body["availability"] == "AVAILABLE" and body["source"] == read(source)
        with pytest.raises(ValueError):
            validate_source_observation(body, work_ref="WS:SYNTHETIC-PROJECT", record_commit="f" * 40)
    else:
        assert body["availability"] == "UNAVAILABLE" and body["source"] is None and body["reason"] == "SOURCE_UNAVAILABLE"
