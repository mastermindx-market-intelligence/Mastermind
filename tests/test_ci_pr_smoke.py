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
