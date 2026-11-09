"""PR smoke selects bounded source-proximate modules; merge queue owns full tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci_pr_smoke import (
    SmokeUnqualified, check_changed_python, select_modules,
    _IDENTITY_PIN_REGISTRY, _IDENTITY_REVIEW_TESTS, _MAX_SELECTED_MODULES,
    _reviewed_sources,
)


def repo(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ci_pytest_policy.py").write_text(
        "def test_baseline(): assert True\n", encoding="utf-8",
    )
    return tmp_path


def identity_repo(tmp_path: Path, *reviewed: str) -> tuple[Path, frozenset[str]]:
    root = repo(tmp_path)
    for name in _IDENTITY_REVIEW_TESTS:
        (root / name).write_text("def test_pin(): assert True\n", encoding="utf-8")
    return root, frozenset(reviewed)


def test_source_module_selects_matching_test_without_positive_global_allowlist(tmp_path):
    root = repo(tmp_path)
    (root / "app").mkdir()
    (root / "app/module.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests/test_module.py").write_text("def test_module(): assert True\n", encoding="utf-8")
    assert select_modules(root, ("app/module.py",)) == (
        "tests/test_ci_pytest_policy.py", "tests/test_module.py",
    )


def test_changed_test_is_included_and_capacity_is_bounded(tmp_path):
    root = repo(tmp_path)
    paths = []
    for i in range(10):
        path = f"tests/test_scope_{i}.py"
        (root / path).write_text("def test_ok(): assert True\n", encoding="utf-8")
        paths.append(path)
    selected = select_modules(root, paths)
    assert len(selected) == _MAX_SELECTED_MODULES + 1
    assert selected[0] == "tests/test_ci_pytest_policy.py"
    assert len(set(selected)) == len(selected)


def test_source_python_syntax_is_checked_before_pytest(tmp_path):
    root = repo(tmp_path)
    (root / "app").mkdir()
    (root / "app/broken.py").write_text("def broken(: pass\n", encoding="utf-8")
    with pytest.raises(SmokeUnqualified, match="SYNTAX"):
        check_changed_python(root, ("app/broken.py",))


def test_smoke_refuses_path_escape(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(SmokeUnqualified, match="UNSAFE"):
        select_modules(root, ("../private.py",))


def test_no_source_matches_still_requires_deterministic_baseline(tmp_path):
    root = repo(tmp_path)
    assert select_modules(root, ("docs/user-guide.md",)) == (
        "tests/test_ci_pytest_policy.py",
    )


@pytest.mark.parametrize("source", [
    "integrations/paper_desktop/bridge.py",
    "integrations/paper_desktop/runtime_stage.py",
])
def test_paper_source_requires_stage_consistency_inside_existing_cap(tmp_path, source):
    root = repo(tmp_path)
    required = "tests/test_paper_runtime_stage.py"
    (root / required).write_text("def test_pin(): assert True\n")
    changed = [source]
    for i in range(10):
        name = f"tests/test_a{i}.py"
        (root / name).write_text("def test_ok(): assert True\n")
        changed.append(name)
    selected = select_modules(root, changed)
    assert required in selected
    assert selected[0] == "tests/test_ci_pytest_policy.py"
    assert len(selected) == _MAX_SELECTED_MODULES + 1


@pytest.mark.parametrize("fault", ["missing", "symlink", "oversized"])
def test_paper_required_stage_test_cannot_be_silently_omitted(tmp_path, fault):
    root = repo(tmp_path)
    target = root / "tests/test_paper_runtime_stage.py"
    if fault == "symlink":
        target.symlink_to(root / "tests/test_ci_pytest_policy.py")
    elif fault == "oversized":
        target.write_bytes(b"#" * 160_001)
    with pytest.raises(SmokeUnqualified, match="REQUIRED_TEST_UNAVAILABLE"):
        select_modules(root, ("integrations/paper_desktop/bridge.py",))


def test_paper_compatibility_only_change_does_not_expand_smoke(tmp_path):
    root = repo(tmp_path)
    name = "tests/test_paper_tool_scoped_compatibility.py"
    (root / name).write_text("def test_tool(): assert True\n")
    assert select_modules(root, (name,)) == (
        "tests/test_ci_pytest_policy.py", name,
    )


def test_real_smoke_runner_propagates_stage_pin_drift(tmp_path, monkeypatch):
    import hashlib
    import sys
    from scripts import ci_pr_smoke

    root = repo(tmp_path)
    (root / ".git").mkdir()
    source = root / "integrations/paper_desktop/bridge.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (root / "tests/test_paper_runtime_stage.py").write_text(
        "from pathlib import Path\nimport hashlib\n"
        "def test_current_generation_matches_source():\n"
        "    source = Path('integrations/paper_desktop/bridge.py')\n"
        f"    assert hashlib.sha256(source.read_bytes()).hexdigest() == {digest!r}\n"
    )
    monkeypatch.setattr(ci_pr_smoke, "_diff_paths", lambda *_: (
        "integrations/paper_desktop/bridge.py",
    ))
    monkeypatch.setattr(sys, "argv", ["smoke", "--repo", str(root),
                                      "--base", "base", "--head", "head"])
    assert ci_pr_smoke.main() == 0
    source.write_text("VALUE = 2\n")
    assert ci_pr_smoke.main() != 0


# A merge group certified #2365's scoped candidate without executing the
# frozen identity-review pins, then master's full pytest failed them
# (group 42592403849; push runs 42597437028/42611479873). An
# identity-reviewed source must select its owning review modules.
def test_identity_reviewed_source_selects_owning_review_modules(tmp_path):
    root, reviewed = identity_repo(
        tmp_path, "integrations/hermes_attended_fabric/native.py",
    )
    assert select_modules(
        root, ("integrations/hermes_attended_fabric/native.py",),
        reviewed_sources=reviewed,
    ) == ("tests/test_ci_pytest_policy.py", *_IDENTITY_REVIEW_TESTS)


def test_identity_modules_are_fixed_dependencies_not_cap_victims(tmp_path):
    root, reviewed = identity_repo(tmp_path, "ops/executive_os/autonomy_control.py")
    changed = ["ops/executive_os/autonomy_control.py"]
    for i in range(10):
        name = f"tests/test_z{i}.py"
        (root / name).write_text("def test_ok(): assert True\n", encoding="utf-8")
        changed.append(name)
    selected = select_modules(root, changed, reviewed_sources=reviewed)
    assert selected[0] == "tests/test_ci_pytest_policy.py"
    for name in _IDENTITY_REVIEW_TESTS:
        assert name in selected


@pytest.mark.parametrize("fault", ["missing", "symlink", "oversized"])
def test_identity_review_modules_cannot_be_silently_omitted(tmp_path, fault):
    root, reviewed = identity_repo(tmp_path, "integrations/hermes_attended_fabric/native.py")
    target = root / _IDENTITY_REVIEW_TESTS[1]
    if fault == "missing":
        target.unlink()
    elif fault == "symlink":
        target.unlink()
        target.symlink_to(root / "tests/test_ci_pytest_policy.py")
    else:
        target.write_bytes(b"#" * 160_001)
    with pytest.raises(SmokeUnqualified, match="REQUIRED_TEST_UNAVAILABLE"):
        select_modules(
            root, ("integrations/hermes_attended_fabric/native.py",),
            reviewed_sources=reviewed,
        )


def test_source_outside_review_registry_keeps_legacy_selection(tmp_path):
    root, reviewed = identity_repo(tmp_path, "integrations/hermes_attended_fabric/native.py")
    (root / "app").mkdir()
    (root / "app/module.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests/test_module.py").write_text("def test_module(): assert True\n", encoding="utf-8")
    assert select_modules(root, ("app/module.py",), reviewed_sources=reviewed) == (
        "tests/test_ci_pytest_policy.py", "tests/test_module.py",
    )


def _git_repo_with_registry(tmp_path: Path, registry: str) -> tuple[Path, str]:
    root = tmp_path / "trusted"
    root.mkdir()
    (root / _IDENTITY_PIN_REGISTRY).parent.mkdir(parents=True, exist_ok=True)
    (root / _IDENTITY_PIN_REGISTRY).write_text(registry, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", _IDENTITY_PIN_REGISTRY], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@e.st", "-c", "user.name=t",
         "commit", "-q", "-m", "registry"], check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE,
    ).stdout.decode("ascii").strip()
    return root, sha


def test_reviewed_registry_keys_come_from_the_trusted_base_blob(tmp_path):
    registry = (
        '"""Frozen reviewed literals."""\n'
        "REVIEWED_FILES = {\n"
        "    'integrations/hermes_attended_fabric/native.py': "
        "{'sha256': 'a' * 64, 'sites': ()},\n"
        "}\n"
        "REVIEWED_FILES['ops/executive_os/autonomy_control.py'] = "
        "{'sha256': 'b' * 64, 'sites': ()}\n"
        "MORE = {'control_plane/executive_backup.py': {'sha256': 'c' * 64}}\n"
        "REVIEWED_FILES.update(MORE)\n"
        "REVIEWED_FILES.update({'app/main.py': {'sha256': 'd' * 64}})\n"
    )
    root, sha = _git_repo_with_registry(tmp_path, registry)
    assert _reviewed_sources(root, sha) == frozenset({
        "integrations/hermes_attended_fabric/native.py",
        "ops/executive_os/autonomy_control.py",
        "control_plane/executive_backup.py",
        "app/main.py",
    })


def test_registry_follows_imported_reviewed_files_merge(tmp_path):
    registry = (
        "from tests.test_other_identity_review import (\n"
        "    REVIEWED_FILES as OTHER_REVIEWED_FILES,\n"
        ")\n"
        "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
        "REVIEWED_FILES.update(OTHER_REVIEWED_FILES)\n"
    )
    other = (
        "from pathlib import Path\n"
        "import pytest\n"
        "REVIEWED_FILES = {\n"
        "    'integrations/hermes_runtime/native_session_control.py': "
        "{'sha256': 'b' * 64},\n"
        "}\n"
        "def test_review(path):\n"
        "    for key in REVIEWED_FILES:\n"
        "        if key == path:\n"
        "            assert REVIEWED_FILES[key]['sha256']\n"
    )
    root, sha = _git_repo_with_registry(tmp_path, registry)
    (root / "tests/test_other_identity_review.py").write_text(other, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tests/"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@e.st", "-c", "user.name=t",
         "commit", "-q", "-m", "other"], check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE,
    ).stdout.decode("ascii").strip()
    # Test functions with control flow do not affect the imported registry.
    assert _reviewed_sources(root, sha) == frozenset({
        "app/main.py",
        "integrations/hermes_runtime/native_session_control.py",
    })


def test_registry_missing_at_trusted_base_keeps_legacy_empty_mapping(tmp_path):
    root, _ = _git_repo_with_registry(tmp_path, "# placeholder\n")
    (root / _IDENTITY_PIN_REGISTRY).unlink()
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@e.st", "-c", "user.name=t",
         "commit", "-q", "-am", "remove"], check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE,
    ).stdout.decode("ascii").strip()
    assert _reviewed_sources(root, sha) == frozenset()


@pytest.mark.parametrize("registry", [
    "REVIEWED_FILES = 'not-a-dict'\n",
    "REVIEWED_FILES = {key: value for key, value in pairs}\n",
    "OTHER = {}\n",
    "def broken(:\n",
    # Top-level control flow or unrecognized mutation of the registry cannot
    # prove the reviewed set, even when a dict literal is also present.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "if True:\n    REVIEWED_FILES['x.py'] = {}\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "for path in more:\n    REVIEWED_FILES.update(path)\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "REVIEWED_FILES |= {'x.py': {}}\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "del REVIEWED_FILES['app/main.py']\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "merge(REVIEWED_FILES)\n",
])
def test_malformed_present_registry_fails_closed(tmp_path, registry):
    root, sha = _git_repo_with_registry(tmp_path, registry)
    with pytest.raises(SmokeUnqualified, match="REGISTRY"):
        _reviewed_sources(root, sha)


def test_main_passes_identity_modules_to_the_test_runner(tmp_path, monkeypatch):
    import sys
    from scripts import ci_pr_smoke

    root, reviewed = identity_repo(tmp_path, "integrations/hermes_attended_fabric/native.py")
    (root / ".git").mkdir()
    source = root / "integrations/hermes_attended_fabric/native.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(ci_pr_smoke, "_diff_paths", lambda *_: (
        "integrations/hermes_attended_fabric/native.py",
    ))
    monkeypatch.setattr(ci_pr_smoke, "_reviewed_sources", lambda *_: reviewed)
    argv: list[str] = []

    class _Done:
        returncode = 0

    def fake_run(cmd, **_):
        start = cmd.index("pytest") + 1
        argv.extend(arg for arg in cmd[start:] if not arg.startswith("-"))
        return _Done()

    monkeypatch.setattr(ci_pr_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["smoke", "--repo", str(root),
                                      "--base", "base", "--head", "head"])
    assert ci_pr_smoke.main() == 0
    assert list(argv) == ["tests/test_ci_pytest_policy.py", *_IDENTITY_REVIEW_TESTS]
