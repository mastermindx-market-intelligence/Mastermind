"""PR smoke selects bounded source-proximate modules; merge queue owns full tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci_pr_smoke import (
    SmokeUnqualified, check_changed_python, select_modules,
    _IDENTITY_PIN_REGISTRIES, _MAX_SELECTED_MODULES, _reviewed_registries,
)

_FABRIC_REGISTRY, FABRIC_TESTS = _IDENTITY_PIN_REGISTRIES[0]
_INCIDENT_REGISTRY, INCIDENT_TESTS = _IDENTITY_PIN_REGISTRIES[1]


def repo(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ci_pytest_policy.py").write_text(
        "def test_baseline(): assert True\n", encoding="utf-8",
    )
    return tmp_path


def identity_repo(tmp_path: Path, fabric=(), incident=()):
    root = repo(tmp_path)
    for _, tests in _IDENTITY_PIN_REGISTRIES:
        for name in tests:
            (root / name).write_text("def test_pin(): assert True\n", encoding="utf-8")
    return root, ((frozenset(fabric), FABRIC_TESTS), (frozenset(incident), INCIDENT_TESTS))


def test_source_module_selects_matching_test_without_positive_global_allowlist(tmp_path):
    root = repo(tmp_path)
    (root / "app").mkdir()
    (root / "app/module.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests/test_module.py").write_text("def test_module(): assert True\n", encoding="utf-8")
    assert select_modules(root, ("app/module.py",), identity_registries=()) == (
        "tests/test_ci_pytest_policy.py", "tests/test_module.py",
    )


def test_changed_test_is_included_and_capacity_is_bounded(tmp_path):
    root = repo(tmp_path)
    paths = []
    for i in range(10):
        path = f"tests/test_scope_{i}.py"
        (root / path).write_text("def test_ok(): assert True\n", encoding="utf-8")
        paths.append(path)
    selected = select_modules(root, paths, identity_registries=())
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
        select_modules(root, ("../private.py",), identity_registries=())


def test_no_source_matches_still_requires_deterministic_baseline(tmp_path):
    root = repo(tmp_path)
    assert select_modules(root, ("docs/user-guide.md",), identity_registries=()) == (
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
    selected = select_modules(root, changed, identity_registries=())
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
        select_modules(root, ("integrations/paper_desktop/bridge.py",),
                       identity_registries=())


def test_paper_compatibility_only_change_does_not_expand_smoke(tmp_path):
    root = repo(tmp_path)
    name = "tests/test_paper_tool_scoped_compatibility.py"
    (root / name).write_text("def test_tool(): assert True\n")
    assert select_modules(root, (name,), identity_registries=()) == (
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
    # The paper journey is under test here; the synthetic root is not a real
    # git repository, and the registry reader must fail closed on it.
    monkeypatch.setattr(ci_pr_smoke, "_reviewed_registries", lambda *_: ())
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
    root, registries = identity_repo(
        tmp_path, fabric=("integrations/hermes_attended_fabric/native.py",),
    )
    assert select_modules(
        root, ("integrations/hermes_attended_fabric/native.py",),
        identity_registries=registries,
    ) == ("tests/test_ci_pytest_policy.py", *FABRIC_TESTS)


def test_identity_modules_are_fixed_dependencies_not_cap_victims(tmp_path):
    root, registries = identity_repo(
        tmp_path, fabric=("ops/executive_os/autonomy_control.py",),
    )
    changed = ["ops/executive_os/autonomy_control.py"]
    for i in range(10):
        name = f"tests/test_z{i}.py"
        (root / name).write_text("def test_ok(): assert True\n", encoding="utf-8")
        changed.append(name)
    selected = select_modules(root, changed, identity_registries=registries)
    assert selected[0] == "tests/test_ci_pytest_policy.py"
    for name in FABRIC_TESTS:
        assert name in selected


@pytest.mark.parametrize("fault", ["missing", "symlink", "oversized"])
def test_identity_review_modules_cannot_be_silently_omitted(tmp_path, fault):
    root, registries = identity_repo(
        tmp_path, fabric=("integrations/hermes_attended_fabric/native.py",),
    )
    target = root / FABRIC_TESTS[1]
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
            identity_registries=registries,
        )


def test_source_outside_review_registry_keeps_legacy_selection(tmp_path):
    root, registries = identity_repo(
        tmp_path, fabric=("integrations/hermes_attended_fabric/native.py",),
    )
    (root / "app").mkdir()
    (root / "app/module.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests/test_module.py").write_text("def test_module(): assert True\n", encoding="utf-8")
    assert select_modules(
        root, ("app/module.py",), identity_registries=registries,
    ) == ("tests/test_ci_pytest_policy.py", "tests/test_module.py")


# The incident-source pins (tests/executive_incident_identity_review.py) are a
# second frozen registry enforced by tests/test_incident_identity_review.py:
# exactly the #2365 defect class for those five sources if left unwired.
def test_incident_reviewed_source_selects_only_its_owning_module(tmp_path):
    root, registries = identity_repo(
        tmp_path, incident=("control_plane/executive_incident_origin.py",),
    )
    assert select_modules(
        root, ("control_plane/executive_incident_origin.py",),
        identity_registries=registries,
    ) == ("tests/test_ci_pytest_policy.py", *INCIDENT_TESTS)


def test_distinct_registries_stack_their_own_owning_modules(tmp_path):
    root, registries = identity_repo(
        tmp_path,
        fabric=("integrations/hermes_attended_fabric/native.py",),
        incident=("ops/executive_os/provider_incident_forward.py",),
    )
    selected = select_modules(root, (
        "integrations/hermes_attended_fabric/native.py",
        "ops/executive_os/provider_incident_forward.py",
    ), identity_registries=registries)
    assert selected == ("tests/test_ci_pytest_policy.py",
                        *FABRIC_TESTS, *INCIDENT_TESTS)


def test_both_frozen_pin_registries_are_wired_with_distinct_owning_tests():
    assert [path for path, _ in _IDENTITY_PIN_REGISTRIES] == [
        "tests/executive_fabric_release_identity_review.py",
        "tests/executive_incident_identity_review.py",
    ]
    owned = [name for _, tests in _IDENTITY_PIN_REGISTRIES for name in tests]
    assert owned and len(set(owned)) == len(owned)


def _git_repo_with_registry(tmp_path: Path, registry: str,
                            path: str = _FABRIC_REGISTRY) -> tuple[Path, str]:
    root = tmp_path / "trusted"
    root.mkdir()
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(registry, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", path], check=True)
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
    registries = _reviewed_registries(root, sha)
    assert registries[0][1] == FABRIC_TESTS
    assert registries[0][0] == frozenset({
        "integrations/hermes_attended_fabric/native.py",
        "ops/executive_os/autonomy_control.py",
        "control_plane/executive_backup.py",
        "app/main.py",
    })
    # The incident registry is absent at this base: legacy empty mapping.
    assert registries[1] == (frozenset(), INCIDENT_TESTS)


def test_each_registry_is_extracted_from_its_own_base_blob(tmp_path):
    root, _ = _git_repo_with_registry(
        tmp_path,
        "REVIEWED_FILES = {'integrations/hermes_attended_fabric/native.py': "
        "{'sha256': 'a' * 64}}\n",
    )
    incident = root / _INCIDENT_REGISTRY
    incident.parent.mkdir(parents=True, exist_ok=True)
    incident.write_text(
        "REVIEWED_FILES = {'control_plane/executive_incident_origin.py': "
        "{'sha256': 'b' * 64}}\n", encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "add", _INCIDENT_REGISTRY], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@e.st", "-c", "user.name=t",
         "commit", "-q", "-m", "incident"], check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE,
    ).stdout.decode("ascii").strip()
    assert _reviewed_registries(root, sha) == (
        (frozenset({"integrations/hermes_attended_fabric/native.py"}), FABRIC_TESTS),
        (frozenset({"control_plane/executive_incident_origin.py"}), INCIDENT_TESTS),
    )


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
    root, _ = _git_repo_with_registry(tmp_path, registry)
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
    assert _reviewed_registries(root, sha)[0][0] == frozenset({
        "app/main.py",
        "integrations/hermes_runtime/native_session_control.py",
    })


def test_registry_missing_at_trusted_base_keeps_legacy_empty_mapping(tmp_path):
    root, _ = _git_repo_with_registry(tmp_path, "# placeholder\n")
    (root / _FABRIC_REGISTRY).unlink()
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@e.st", "-c", "user.name=t",
         "commit", "-q", "-am", "remove"], check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE,
    ).stdout.decode("ascii").strip()
    assert _reviewed_registries(root, sha) == (
        (frozenset(), FABRIC_TESTS), (frozenset(), INCIDENT_TESTS),
    )


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout


@pytest.mark.parametrize("ls_tree_stdout,ls_tree_rc", [
    (b"100644 blob abc0000000000000000000000000000000000000\tpath\n", 0),
    (b"", 1),
])
def test_unreadable_registry_blob_fails_closed(tmp_path, monkeypatch,
                                               ls_tree_stdout, ls_tree_rc):
    from scripts import ci_pr_smoke

    def fake_run(cmd, **_):
        if cmd[3] == "ls-tree":
            return _Proc(ls_tree_rc, ls_tree_stdout)
        return _Proc(1, b"")  # cat-file cannot read the blob

    monkeypatch.setattr(ci_pr_smoke.subprocess, "run", fake_run)
    with pytest.raises(SmokeUnqualified, match="SMOKE_REVIEWED_REGISTRY_UNREADABLE"):
        ci_pr_smoke._registry_blob(tmp_path, "base", "tests/x.py")


def test_confirmed_absent_registry_keeps_legacy_empty_mapping(tmp_path, monkeypatch):
    from scripts import ci_pr_smoke

    def fake_run(cmd, **_):
        if cmd[3] == "ls-tree":
            return _Proc(0, b"")
        return _Proc(1, b"")  # cat-file fails; listing proves absence

    monkeypatch.setattr(ci_pr_smoke.subprocess, "run", fake_run)
    assert ci_pr_smoke._registry_blob(tmp_path, "base", "tests/x.py") is None


@pytest.mark.parametrize("registry", [
    "REVIEWED_FILES = 'not-a-dict'\n",
    "REVIEWED_FILES = {key: value for key, value in pairs}\n",
    "REVIEWED_FILES = build_registry()\n",
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
    # Alias rebinding, multi-target assignment, dynamic subscript keys and
    # string-constant lookups can each mutate the runtime registry without
    # the extractor seeing it; they must fail closed, not under-extract.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "SHADOW = REVIEWED_FILES\n",
    "SHADOW = REVIEWED_FILES\n"
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n",
    "X = REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "REVIEWED_FILES[make_key()] = {}\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "globals()['REVIEWED_FILES'].update({'x.py': {}})\n",
    # Def-time expressions execute during registry import even though the
    # function bodies themselves never run.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "@REVIEWED_FILES.get('app/main.py')\n"
    "def deco():\n    pass\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "def take(x=REVIEWED_FILES):\n    return x\n",
    # Module-level execution other than the update gate: helper mutation,
    # called functions, exec/eval and attribute calls all run unreviewed
    # code whose registry effects static extraction cannot see.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "EXTRA = {'b.py': {}}\n"
    "EXTRA.update({'c.py': {}})\n"
    "REVIEWED_FILES.update(EXTRA)\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "def _m():\n    REVIEWED_FILES.update({'c.py': {}})\n"
    "_m()\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "exec(\"REVIEWED_FILES['c.py'] = {}\")\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "os.system('true')\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "match flag:\n    case _:\n        helper()\n",
    # Calls inside assigned or merged expressions execute at import.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "MORE = {'b.py': make()}\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "REVIEWED_FILES.update({'b.py': make()})\n",
    # A tracked helper name may not be aliased, rebound through an import,
    # or otherwise reused after its binding: any of those can change what
    # a later merge actually merges.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "MORE = {'b.py': {}}\n"
    "RESULT = MORE\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "MORE = {'b.py': {}}\n"
    "from x import y as MORE\n",
    # Class bodies execute at import like the module top level.
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "class Holder:\n    data = REVIEWED_FILES\n",
    "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
    "class Holder:\n    data = build()\n",
])
def test_malformed_present_registry_fails_closed(tmp_path, registry):
    root, sha = _git_repo_with_registry(tmp_path, registry)
    with pytest.raises(SmokeUnqualified, match="REGISTRY"):
        _reviewed_registries(root, sha)


def test_benign_top_level_class_parses_without_crashing(tmp_path):
    root, sha = _git_repo_with_registry(
        tmp_path,
        '"""Frozen reviewed literals with a helper class."""\n'
        "import typing\n"
        "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
        "class Span(typing.NamedTuple):\n"
        "    line: int\n"
        "    column: int\n",
    )
    assert _reviewed_registries(root, sha)[0][0] == frozenset({"app/main.py"})


def test_main_passes_identity_modules_to_the_test_runner(tmp_path, monkeypatch):
    import sys
    from scripts import ci_pr_smoke

    root, registries = identity_repo(
        tmp_path, fabric=("integrations/hermes_attended_fabric/native.py",),
    )
    (root / ".git").mkdir()
    source = root / "integrations/hermes_attended_fabric/native.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n")
    monkeypatch.setattr(ci_pr_smoke, "_diff_paths", lambda *_: (
        "integrations/hermes_attended_fabric/native.py",
    ))
    monkeypatch.setattr(ci_pr_smoke, "_reviewed_registries", lambda *_: registries)
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
    assert list(argv) == ["tests/test_ci_pytest_policy.py", *FABRIC_TESTS]
