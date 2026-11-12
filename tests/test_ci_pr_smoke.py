"""PR smoke selects bounded source-proximate modules; merge queue owns full tests."""
from __future__ import annotations

import importlib
import importlib.util
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.ci_pr_smoke import (
    SmokeUnqualified, check_changed_python, select_modules,
    _IDENTITY_PIN_REGISTRIES, _MAX_REGISTRY_BYTES, _MAX_SELECTED_MODULES,
    _quoted_path_in, _registry_blob, _reviewed_registries,
)

_FABRIC_REGISTRY, FABRIC_CHAIN, FABRIC_TESTS = _IDENTITY_PIN_REGISTRIES[0]
_INCIDENT_REGISTRY, INCIDENT_CHAIN, INCIDENT_TESTS = _IDENTITY_PIN_REGISTRIES[1]


def repo(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ci_pytest_policy.py").write_text(
        "def test_baseline(): assert True\n", encoding="utf-8",
    )
    return tmp_path


def identity_repo(tmp_path: Path, fabric: bytes = b"", incident: bytes = b""):
    root = repo(tmp_path)
    for _path, _chain, tests in _IDENTITY_PIN_REGISTRIES:
        for name in tests:
            (root / name).write_text("def test_pin(): assert True\n", encoding="utf-8")
    # Synthetic registry chains are plain chain text: the selector only does
    # quoted-literal containment against these bytes.
    return root, ((fabric, FABRIC_TESTS), (incident, INCIDENT_TESTS))


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


def test_complete_group_refuses_to_drop_the_fourth_applicable_module(tmp_path):
    root = repo(tmp_path)
    paths = tuple(f"tests/test_customer_{i}.py" for i in range(4))
    for path in paths:
        (root / path).write_text("def test_customer(): assert True\n")
    assert len(select_modules(root, paths, identity_registries=())) == 4
    with pytest.raises(SmokeUnqualified, match="SMOKE_SELECTION_EXCEEDS_BUDGET"):
        select_modules(root, paths, identity_registries=(), require_complete=True)


def test_complete_group_deduplicates_owners_before_counting_and_never_slices(tmp_path):
    source = "integrations/customer.py"
    root, registries = identity_repo(tmp_path, fabric=repr(source).encode())
    selected = select_modules(root, (source, *FABRIC_TESTS),
                              identity_registries=registries, require_complete=True)
    assert selected == ("tests/test_ci_pytest_policy.py", *FABRIC_TESTS)
    extra = "tests/test_customer.py"
    (root / extra).write_text("def test_customer(): assert True\n")
    with pytest.raises(SmokeUnqualified, match="SMOKE_SELECTION_EXCEEDS_BUDGET"):
        select_modules(root, (source, extra), identity_registries=registries,
                       require_complete=True)


@pytest.mark.parametrize("fault", ["missing", "directory", "symlink", "oversized"])
def test_complete_group_refuses_unavailable_applicable_tests(tmp_path, fault):
    root = repo(tmp_path)
    path = "tests/test_customer.py"
    file = root / path
    if fault == "directory":
        file.mkdir()
    elif fault == "symlink":
        file.symlink_to(root / "tests/test_ci_pytest_policy.py")
    elif fault == "oversized":
        file.write_text("#" + "x" * 160000 + "\n")
    with pytest.raises(SmokeUnqualified, match="SMOKE_APPLICABLE_TEST_UNAVAILABLE"):
        select_modules(root, (path,), identity_registries=(), require_complete=True)


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
    # main() always appends the live registry guard node; the synthetic root
    # carries a passing stand-in so this test isolates the stage pin.
    (root / ci_pr_smoke._REGISTRY_GUARD_TEST).write_text(
        "def test_live_identity_registry_keys_are_quoted_literals_in_their_chain():\n"
        "    pass\n"
    )
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
        tmp_path,
        fabric=b"REVIEWED_FILES['integrations/hermes_attended_fabric/native.py'] = {}\n",
    )
    assert select_modules(
        root, ("integrations/hermes_attended_fabric/native.py",),
        identity_registries=registries,
    ) == ("tests/test_ci_pytest_policy.py", *FABRIC_TESTS)


def test_identity_modules_are_fixed_dependencies_not_cap_victims(tmp_path):
    root, registries = identity_repo(
        tmp_path,
        fabric=b"REVIEWED_FILES['ops/executive_os/autonomy_control.py'] = {}\n",
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
        tmp_path,
        fabric=b"REVIEWED_FILES['integrations/hermes_attended_fabric/native.py'] = {}\n",
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
        tmp_path,
        fabric=b"REVIEWED_FILES['integrations/hermes_attended_fabric/native.py'] = {}\n",
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
        tmp_path,
        incident=b"REVIEWED_FILES['control_plane/executive_incident_origin.py'] = {}\n",
    )
    assert select_modules(
        root, ("control_plane/executive_incident_origin.py",),
        identity_registries=registries,
    ) == ("tests/test_ci_pytest_policy.py", *INCIDENT_TESTS)


def test_distinct_registries_stack_their_own_owning_modules(tmp_path):
    root, registries = identity_repo(
        tmp_path,
        fabric=b"REVIEWED_FILES['integrations/hermes_attended_fabric/native.py'] = {}\n",
        incident=b"REVIEWED_FILES['ops/executive_os/provider_incident_forward.py'] = {}\n",
    )
    selected = select_modules(root, (
        "integrations/hermes_attended_fabric/native.py",
        "ops/executive_os/provider_incident_forward.py",
    ), identity_registries=registries)
    assert selected == ("tests/test_ci_pytest_policy.py",
                        *FABRIC_TESTS, *INCIDENT_TESTS)


def test_both_frozen_pin_registries_are_wired_with_chains_and_distinct_owning_tests():
    assert [(path, chain) for path, chain, _ in _IDENTITY_PIN_REGISTRIES] == [
        ("tests/executive_fabric_release_identity_review.py",
         ("tests/executive_fabric_release_identity_review.py",
          "tests/test_hermes_workspace_oauth_identity_review.py")),
        ("tests/executive_incident_identity_review.py",
         ("tests/executive_incident_identity_review.py",)),
    ]
    owned = [name for _p, _c, tests in _IDENTITY_PIN_REGISTRIES for name in tests]
    assert owned and len(set(owned)) == len(owned)


# Literal matching: selection fires on a quoted path in the chain text and on
# nothing else. Both quote styles count; a partial or unquoted spelling does
# not, and that choice is deliberate (see the unquoted-mention test below).
def test_quoted_literal_match_covers_both_quote_styles_and_nothing_less():
    text = (b"REVIEWED_FILES = {'app/one.py': {}}\n"
            b'REVIEWED_FILES["app/two.py"] = {}\n')
    assert _quoted_path_in(text, "app/one.py")
    assert _quoted_path_in(text, "app/two.py")
    assert not _quoted_path_in(text, "app/one")
    assert not _quoted_path_in(text, "one.py")
    assert not _quoted_path_in(text, "docs/other.py")


def test_unquoted_path_mention_does_not_select(tmp_path):
    """An unquoted mention must not select; this is a chosen non-over-selection.

    Matching unquoted text would fire on comments, identifiers and prose. The
    matching under-selection risk — a real runtime key with no quoted spelling
    anywhere in its chain — is closed by the live guard, which fails the
    registry's own PR, instead of by widening this match.
    """
    root, registries = identity_repo(
        tmp_path,
        fabric=(b"# reviewed: integrations/hermes_attended_fabric/native.py\n"
                b"REVIEWED_FILES = {'app/main.py': {}}\n"),
    )
    assert select_modules(
        root, ("integrations/hermes_attended_fabric/native.py",),
        identity_registries=registries,
    ) == ("tests/test_ci_pytest_policy.py",)


def test_dynamically_built_key_is_not_selected_statically(tmp_path):
    """A concatenated key spelling carries no quoted literal of the whole
    path, so static selection cannot see it. The live guard flags exactly
    this shape on the registry's own PR (next test)."""
    root, registries = identity_repo(
        tmp_path,
        fabric=(b"REVIEWED_FILES = {'app/main.py': {}}\n"
                b"REVIEWED_FILES['ops/' + 'x.py'] = {}\n"),
    )
    assert select_modules(root, ("ops/x.py",), identity_registries=registries) == (
        "tests/test_ci_pytest_policy.py",
    )


def _git_repo_with_files(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    root = tmp_path / "trusted"
    root.mkdir()
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@e.st", "-c", "user.name=t",
         "commit", "-q", "-m", "registry"], check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE,
    ).stdout.decode("ascii").strip()
    return root, sha


def test_chain_text_is_read_from_the_trusted_base_blobs(tmp_path):
    registry = (
        "REVIEWED_FILES = {'integrations/hermes_attended_fabric/native.py': "
        "{'sha256': 'a' * 64}}\n"
        "REVIEWED_FILES['ops/executive_os/autonomy_control.py'] = "
        "{'sha256': 'b' * 64}\n"
        "MORE = {'control_plane/executive_backup.py': {'sha256': 'c' * 64}}\n"
        "REVIEWED_FILES.update(MORE)\n"
    )
    sub = ("REVIEWED_FILES = {'ops/native_fabric/hidden.py': {'sha256': 'd' * 64}}\n")
    incident = ("REVIEWED_FILES = {'control_plane/executive_incident_origin.py': "
                "{'sha256': 'e' * 64}}\n")
    root, sha = _git_repo_with_files(tmp_path, {
        _FABRIC_REGISTRY: registry,
        FABRIC_CHAIN[1]: sub,
        _INCIDENT_REGISTRY: incident,
    })
    # The fabric chain text is the registry blob plus the sub-registry blob;
    # the incident registry reads only its own single-file chain.
    assert _reviewed_registries(root, sha) == (
        (registry.encode("utf-8") + sub.encode("utf-8"), FABRIC_TESTS),
        (incident.encode("utf-8"), INCIDENT_TESTS),
    )


def test_sub_registry_chain_key_selects_the_owners(tmp_path):
    """A key living only in the imported sub-registry still fires the fabric
    owners: the chain text concatenates both blobs before matching."""
    registry = (
        "from tests.test_hermes_workspace_oauth_identity_review import (\n"
        "    REVIEWED_FILES as OTHER_REVIEWED_FILES,\n"
        ")\n"
        "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
        "REVIEWED_FILES.update(OTHER_REVIEWED_FILES)\n"
    )
    sub = ("REVIEWED_FILES = {'integrations/hermes_runtime/native_session_control.py': "
           "{'sha256': 'b' * 64}}\n")
    files = {
        _FABRIC_REGISTRY: registry,
        FABRIC_CHAIN[1]: sub,
        "tests/test_ci_pytest_policy.py": "def test_baseline(): assert True\n",
    }
    for name in FABRIC_TESTS:
        files[name] = "def test_pin(): assert True\n"
    root, sha = _git_repo_with_files(tmp_path, files)
    selected = select_modules(
        root, ("integrations/hermes_runtime/native_session_control.py",),
        identity_registries=_reviewed_registries(root, sha),
    )
    assert selected == ("tests/test_ci_pytest_policy.py", *FABRIC_TESTS)


def test_registry_missing_at_trusted_base_keeps_legacy_empty_mapping(tmp_path):
    root, sha = _git_repo_with_files(tmp_path, {"README.md": "# none\n"})
    assert _reviewed_registries(root, sha) == (
        (b"", FABRIC_TESTS), (b"", INCIDENT_TESTS),
    )


def test_over_bound_registry_blob_fails_closed(tmp_path):
    root, sha = _git_repo_with_files(tmp_path, {
        _FABRIC_REGISTRY: "#" * (_MAX_REGISTRY_BYTES + 1),
    })
    with pytest.raises(SmokeUnqualified, match="SMOKE_REVIEWED_REGISTRY_OVER_BOUND"):
        _reviewed_registries(root, sha)


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


def test_unreadable_chain_blob_fails_closed_through_registry_reading(
        tmp_path, monkeypatch):
    from scripts import ci_pr_smoke

    def fake_run(cmd, **_):
        if cmd[3] == "ls-tree":
            return _Proc(0, b"100644 blob abc\ttests/x.py\n")
        return _Proc(1, b"")  # cat-file cannot read the blob

    monkeypatch.setattr(ci_pr_smoke.subprocess, "run", fake_run)
    with pytest.raises(SmokeUnqualified, match="SMOKE_REVIEWED_REGISTRY_UNREADABLE"):
        ci_pr_smoke._reviewed_registries(tmp_path, "base")


def test_confirmed_absent_registry_keeps_legacy_empty_mapping(tmp_path, monkeypatch):
    from scripts import ci_pr_smoke

    def fake_run(cmd, **_):
        if cmd[3] == "ls-tree":
            return _Proc(0, b"")
        return _Proc(1, b"")  # cat-file fails; listing proves absence

    monkeypatch.setattr(ci_pr_smoke.subprocess, "run", fake_run)
    assert ci_pr_smoke._registry_blob(tmp_path, "base", "tests/x.py") is None


def test_main_passes_identity_modules_to_the_test_runner(tmp_path, monkeypatch):
    import sys
    from scripts import ci_pr_smoke

    root, registries = identity_repo(
        tmp_path,
        fabric=b"REVIEWED_FILES['integrations/hermes_attended_fabric/native.py'] = {}\n",
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
    assert list(argv) == ["tests/test_ci_pytest_policy.py", *FABRIC_TESTS,
                          ci_pr_smoke._REGISTRY_GUARD_NODE]


def test_main_runs_the_live_registry_guard_on_every_smoke_candidate(tmp_path, monkeypatch):
    """A registry can gain keys with no chain member in the diff (a deferred
    import starts resolving once a later PR adds its module), so the guard
    must run even when nothing identity-related changed; when the whole guard
    module is already selected it is not added twice."""
    import sys
    from scripts import ci_pr_smoke

    root = repo(tmp_path)
    (root / ".git").mkdir()
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/guide.md").write_text("x\n")
    (root / ci_pr_smoke._REGISTRY_GUARD_TEST).write_text("def test_x():\n    pass\n")
    argv: list[str] = []

    class _Done:
        returncode = 0

    def fake_run(cmd, **_):
        argv[:] = [arg for arg in cmd[cmd.index("pytest") + 1:] if not arg.startswith("-")]
        return _Done()

    monkeypatch.setattr(ci_pr_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(ci_pr_smoke, "_reviewed_registries", lambda *_: ())
    monkeypatch.setattr(sys, "argv", ["smoke", "--repo", str(root),
                                      "--base", "base", "--head", "head"])
    monkeypatch.setattr(ci_pr_smoke, "_diff_paths", lambda *_: ("docs/guide.md",))
    assert ci_pr_smoke.main() == 0
    assert ci_pr_smoke._REGISTRY_GUARD_NODE in argv
    monkeypatch.setattr(ci_pr_smoke, "_diff_paths",
                        lambda *_: (ci_pr_smoke._REGISTRY_GUARD_TEST,))
    assert ci_pr_smoke.main() == 0
    assert ci_pr_smoke._REGISTRY_GUARD_TEST in argv
    assert ci_pr_smoke._REGISTRY_GUARD_NODE not in argv


def _chain_text_at_head(root: Path, chain: Sequence[str]) -> bytes:
    """Concatenated chain files from the checkout the guard imports from.

    Reading the same tree the registry module is imported from keeps the
    comparison like for like (CI checks out the candidate; a dirty local tree
    is compared against itself). Absent members fail with a message.
    """
    parts: list[bytes] = []
    for member in chain:
        file = root / member
        assert file.is_file() and not file.is_symlink(), (
            f"identity registry chain path {member} is absent from the checkout; "
            "update _IDENTITY_PIN_REGISTRIES with the chain change")
        parts.append(file.read_bytes())
    return b"".join(parts)


def _assert_runtime_keys_are_quoted_literals(module, chain_text: bytes,
                                             label: str) -> None:
    """Every runtime REVIEWED_FILES key must be quoted in the chain text."""
    keys = set(module.REVIEWED_FILES)
    assert keys, f"{label}: runtime REVIEWED_FILES has no keys"
    missing = sorted(key for key in keys if not _quoted_path_in(chain_text, key))
    assert not missing, (
        f"{label}: runtime keys absent as quoted literals from the chain text "
        f"(dynamically constructed keys are invisible to literal selection): "
        f"{missing}")


def test_live_identity_registry_keys_are_quoted_literals_in_their_chain():
    """Every wired registry's runtime keys must be quoted literals in its chain.

    Selection reads only quoted literals from trusted-base blobs, so a key
    constructed dynamically at import time would never select its owning
    tests. This guard imports each registry under the exact dotted name its
    owning pin tests use, reads the chain from the same checkout, and fails
    when any runtime key lacks a quoted spelling there. The one residual is
    a key built dynamically inside a function body, gated on a condition
    that is false while this guard runs.
    """
    root = Path(__file__).resolve().parents[1]
    for path, chain, _tests in _IDENTITY_PIN_REGISTRIES:
        module = importlib.import_module(path[:-len(".py")].replace("/", "."))
        _assert_runtime_keys_are_quoted_literals(
            module, _chain_text_at_head(root, chain), path)


def test_dynamic_runtime_key_is_flagged_by_the_guard(tmp_path):
    """A dynamically built runtime key fails the guard — modeled on a tmp
    module, never the real registry."""
    source = tmp_path / "tmp_dynamic_registry.py"
    source.write_text(
        "REVIEWED_FILES = {'app/main.py': {'sha256': 'a' * 64}}\n"
        "REVIEWED_FILES['ops/' + 'x.py'] = {}\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("tmp_dynamic_registry", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.REVIEWED_FILES) == {"app/main.py", "ops/x.py"}
    with pytest.raises(AssertionError, match=r"ops/x\.py"):
        _assert_runtime_keys_are_quoted_literals(
            module, source.read_bytes(), str(source))


def test_deferred_sub_registry_import_is_flagged_once_it_resolves(tmp_path, monkeypatch):
    """A registry edit can add a guarded import of a module that does not
    exist yet; the guard passes then. When a later PR adds that module, its
    keys reach the runtime registry without any chain member changing, so
    only the always-on guard (main appends it to every smoke run) sees them.
    Modeled on tmp modules, never the real registries."""
    registry = tmp_path / "tmp_deferred_registry.py"
    registry.write_text(
        "REVIEWED_FILES = {'app/main.py': {}}\n"
        "try:\n"
        "    from tmp_late_sub_registry import REVIEWED_FILES as LATE\n"
        "    REVIEWED_FILES.update(LATE)\n"
        "except ImportError:\n"
        "    pass\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    def load():
        spec = importlib.util.spec_from_file_location("tmp_deferred_registry", registry)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # Registry PR: the sub-registry does not exist yet, so the guard passes.
    _assert_runtime_keys_are_quoted_literals(load(), registry.read_bytes(), "pr1")
    # Later PR adds the sub-registry; the listed chain is still just the
    # registry, so the new key is not quoted there and the guard refuses.
    (tmp_path / "tmp_late_sub_registry.py").write_text(
        "REVIEWED_FILES = {'ops/late.py': {}}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match=r"ops/late\.py"):
        _assert_runtime_keys_are_quoted_literals(load(), registry.read_bytes(), "pr2")


_EDIT_CASES = [
    (member, tests)
    for _path, chain, tests in _IDENTITY_PIN_REGISTRIES
    for member in chain
]


@pytest.mark.parametrize("edited,owners", _EDIT_CASES)
def test_registry_or_chain_edit_selects_owners_and_the_live_registry_guard(
        edited, owners):
    root = Path(__file__).resolve().parents[1]
    picked = select_modules(root, [edited], identity_registries=())
    assert set(owners) <= set(picked)
    assert "tests/test_ci_pr_smoke.py" in picked
