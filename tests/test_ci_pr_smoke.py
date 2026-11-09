"""PR smoke selects bounded source-proximate modules; merge queue owns full tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci_pr_smoke import (
    SmokeUnqualified, check_changed_python, select_modules, _MAX_SELECTED_MODULES,
)


def repo(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ci_pytest_policy.py").write_text(
        "def test_baseline(): assert True\n", encoding="utf-8",
    )
    return tmp_path


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
