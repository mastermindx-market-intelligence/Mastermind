"""Focused capture tests for the fixed Macro plan-adoption compiler source.

Every test runs against the actual installed parent helpers: the production
module and the incumbent planning capture are imported from the real
``control_plane`` package, and every Git interaction is a real local temporary
repository with no remotes and no fetches.  Tiny synthetic owner/contract/
compiler sources distinguish captured bytes from ambient modules.  When the
parent repository is not importable -- this worker's isolated capture sandbox
-- the module skips truthfully instead of faking the incumbent helper.
"""

import hashlib
import os
import subprocess
import sys
import types

import pytest

try:
    from control_plane.project_plan_adoption_compiler_source import (
        ADOPTION_SOURCE_ROLES,
        REPOSITORY,
        CapturedProjectPlanAdoptionCompilers,
        capture_project_plan_adoption_compilers,
    )
    from control_plane.project_planning_compiler_source import (
        ProjectPlanningCompilerSourceChanged,
        ProjectPlanningCompilerUnavailable,
    )
except Exception as _import_error:  # parent repository unavailable in this sandbox
    pytest.skip(
        "actual parent control_plane unavailable: %r" % (_import_error,),
        allow_module_level=True,
    )

_ALIAS_NAMES = (
    "scripts",
    "scripts.agentos",
    "scripts.agentos_project_plan_contract",
    "scripts.agentos_plan_adoption",
)
_IDENTITY = ("-c", "user.email=capture@example", "-c", "user.name=capture", "-c", "commit.gpgsign=false")


def _sources(token):
    """Tiny synthetic sources whose markers identify the captured bytes."""
    owner = (
        "MARKER = 'owner-%s'\n"
        "\n"
        "def bound_contract():\n"
        "    return _project_plan_contract()\n" % token
    )
    contract = (
        "MARKER = 'contract-%s'\n"
        "CONTRACT_VALUE = 'contract-bytes-%s'\n" % (token, token)
    )
    compiler = (
        "MARKER = 'compiler-%s'\n"
        "\n"
        "def compile_adopt(request):\n"
        "    import scripts.agentos as owner_module\n"
        "    return {'compiler': MARKER, 'owner': owner_module.MARKER, 'request': request}\n"
        % token
    )
    return {
        "scripts/agentos.py": owner,
        "scripts/agentos_project_plan_contract.py": contract,
        "scripts/agentos_plan_adoption.py": compiler,
    }


def _git(repo, *args):
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    subprocess.run(
        ["git", *args], cwd=str(repo), env=env, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _head(repo):
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, stdout=subprocess.PIPE
    )
    return out.stdout.decode().strip()


def _blob(repo, commit, path):
    out = subprocess.run(
        ["git", "show", commit + ":" + path], cwd=str(repo), check=True, stdout=subprocess.PIPE
    )
    return out.stdout


def _build_repo(tmp_path, token, *, pre=None, post=None):
    """A real local repo: sources committed at CODE, then DATA advanced past it.

    ``pre`` runs before the code commit (so the code commit itself is deformed)
    and ``post`` runs after it, before the pure DATA-advance commit.
    """
    repo = tmp_path / ("macro-" + token)
    for rel, text in _sources(token).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if pre is not None:
        pre(repo)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, *_IDENTITY, "commit", "-qm", "code")
    code_commit = _head(repo)
    (repo / "DATA_NOTE.md").write_text("data advance %s\n" % token, encoding="utf-8")
    if post is not None:
        post(repo)
    _git(repo, "add", "-A")
    _git(repo, *_IDENTITY, "commit", "-qm", "advance")
    return repo, code_commit, _head(repo)


def _capture(repo, code_commit, head, **overrides):
    return capture_project_plan_adoption_compilers(
        macro_root=str(repo), expected_macro_sha=head, code_commit=code_commit, **overrides
    )


def _aliases():
    return {name: sys.modules.get(name) for name in _ALIAS_NAMES}


def _assert_clean_slate(before):
    assert _aliases() == before


def _unavailable(func, *args, **kwargs):
    with pytest.raises(ProjectPlanningCompilerUnavailable) as excinfo:
        func(*args, **kwargs)
    refusal = excinfo.value
    assert type(refusal).__module__ == "control_plane.project_planning_compiler_source"
    return refusal


def test_capture_binds_exact_source_and_captured_bytes(tmp_path):
    repo, code_commit, head = _build_repo(tmp_path, "bind")
    before = _aliases()
    path_before = list(sys.path)
    captured = _capture(repo, code_commit, head)

    assert type(captured) is CapturedProjectPlanAdoptionCompilers
    assert type(captured.compiler) is types.ModuleType
    assert type(captured.owner) is types.ModuleType
    assert captured.compiler.__name__ == "scripts.agentos_plan_adoption"
    assert captured.owner.__name__ == "scripts.agentos"
    assert captured.compiler.MARKER == "compiler-bind"
    assert captured.owner.MARKER == "owner-bind"

    assert ADOPTION_SOURCE_ROLES == ("owner", "contract", "compiler")
    assert set(captured.source_binding) == set(ADOPTION_SOURCE_ROLES)
    for role, ref in captured.source_binding.items():
        assert set(ref) == {"repository", "path", "commit", "content_sha256"}
        assert ref["repository"] == REPOSITORY == "mastermindx-market-intelligence/macro"
        assert ref["commit"] == code_commit
        raw = _blob(repo, code_commit, ref["path"])
        assert ref["content_sha256"] == hashlib.sha256(raw).hexdigest()
    assert captured.source_binding["owner"]["path"] == "scripts/agentos.py"
    assert captured.source_binding["contract"]["path"] == "scripts/agentos_project_plan_contract.py"
    assert captured.source_binding["compiler"]["path"] == "scripts/agentos_plan_adoption.py"
    assert (
        captured.source_binding["compiler"]["content_sha256"]
        != captured.source_binding["contract"]["content_sha256"]
    )

    # A positive check, then no alias or sys.path leak after the capture.
    captured.check()
    _assert_clean_slate(before)
    assert list(sys.path) == path_before


def test_contract_binding_and_scope_call_with_restore(tmp_path):
    repo, code_commit, head = _build_repo(tmp_path, "scope")
    before = _aliases()
    path_before = list(sys.path)
    captured = _capture(repo, code_commit, head)

    # The captured owner resolves the captured contract even outside the scope:
    # the binding is a direct closure over the captured module object.
    via_owner = captured.owner.bound_contract()
    assert type(via_owner) is types.ModuleType
    assert via_owner.__name__ == "scripts.agentos_project_plan_contract"
    assert via_owner.MARKER == "contract-scope"
    assert via_owner.CONTRACT_VALUE == "contract-bytes-scope"

    with captured._scope():
        assert sys.modules["scripts.agentos_plan_adoption"] is captured.compiler
        assert sys.modules["scripts.agentos"] is captured.owner
        assert sys.modules["scripts.agentos_project_plan_contract"] is via_owner
        result = captured.compiler.compile_adopt({"n": 1})
        assert result == {
            "compiler": "compiler-scope",
            "owner": "owner-scope",
            "request": {"n": 1},
        }
    _assert_clean_slate(before)
    assert list(sys.path) == path_before

    # A failing body still restores the exact prior state and propagates the
    # caller's own exception unchanged.
    with pytest.raises(RuntimeError) as raised:
        with captured._scope():
            raise RuntimeError("adapter fault")
    assert str(raised.value) == "adapter fault"
    _assert_clean_slate(before)
    assert list(sys.path) == path_before


def test_captured_exec_fault_and_systemexit_refuse_closed(tmp_path):
    before = _aliases()
    path_before = list(sys.path)

    def faulting(repo):
        (repo / "scripts/agentos_plan_adoption.py").write_text(
            "raise RuntimeError('captured fault')\n", encoding="utf-8"
        )

    repo, code_commit, head = _build_repo(tmp_path, "fault", pre=faulting)
    refusal = _unavailable(_capture, repo, code_commit, head)
    assert "captured fault" not in str(refusal)
    _assert_clean_slate(before)
    assert list(sys.path) == path_before

    def exiting(repo):
        (repo / "scripts/agentos_plan_adoption.py").write_text(
            "import sys\nsys.exit(3)\n", encoding="utf-8"
        )

    repo2, code2, head2 = _build_repo(tmp_path, "exit", pre=exiting)
    with pytest.raises(ProjectPlanningCompilerUnavailable):
        _capture(repo2, code2, head2)  # SystemExit must not escape the capture
    _assert_clean_slate(before)
    assert list(sys.path) == path_before


def test_missing_and_symlink_sources_refuse(tmp_path):
    before = _aliases()
    repo, code_commit, head = _build_repo(
        tmp_path, "missing", pre=lambda r: (r / "scripts/agentos_plan_adoption.py").unlink()
    )
    _unavailable(_capture, repo, code_commit, head)
    _assert_clean_slate(before)

    def symlinked(r):
        target = r / "scripts/agentos_plan_adoption.py"
        target.unlink()
        target.symlink_to("agentos.py")

    repo2, code2, head2 = _build_repo(tmp_path, "symlink", pre=symlinked)
    _unavailable(_capture, repo2, code2, head2)  # 120000 link is not a full 100644 blob
    _assert_clean_slate(before)


def test_wrong_head_non_ancestor_and_drift_refuse(tmp_path):
    repo, code_commit, head = _build_repo(tmp_path, "ident")
    before = _aliases()

    # Wrong expected HEAD (code commit is not the observed HEAD).
    refusal = _unavailable(_capture, repo, code_commit, code_commit)
    assert isinstance(refusal, ProjectPlanningCompilerSourceChanged)
    _assert_clean_slate(before)

    captured = _capture(repo, code_commit, head)

    # An uncommitted working-file change never substitutes captured bytes:
    # identity is derived from Git, not from the working tree.
    (repo / "scripts/agentos_plan_adoption.py").write_text(
        "MARKER = 'compiler-WORKINGTREE'\n", encoding="utf-8"
    )
    captured.check()
    with captured._scope():
        assert captured.compiler.MARKER == "compiler-ident"
    _assert_clean_slate(before)

    # A committed code change after the capture is drift: refused, never healed.
    (repo / "scripts/agentos_plan_adoption.py").write_text(
        "MARKER = 'compiler-NEXT'\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, *_IDENTITY, "commit", "-qm", "drift")
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        captured.check()

    # A code commit that is not an ancestor of the observed HEAD refuses.
    _git(repo, "checkout", "-q", "--orphan", "orphanline")
    _git(repo, *_IDENTITY, "commit", "-qm", "orphan")
    orphan_head = _head(repo)
    refusal = _unavailable(_capture, repo, code_commit, orphan_head)
    assert not isinstance(refusal, ProjectPlanningCompilerSourceChanged)
    _assert_clean_slate(before)


def test_ambient_aliases_never_substitute_captured_bytes(tmp_path):
    repo, code_commit, head = _build_repo(tmp_path, "ambient")
    before = _aliases()
    ambient_package = types.ModuleType("scripts")
    fake_owner = types.ModuleType("scripts.agentos")
    fake_owner.MARKER = "AMBIENT-OWNER"
    fake_contract = types.ModuleType("scripts.agentos_project_plan_contract")
    fake_contract.MARKER = "AMBIENT-CONTRACT"
    fake_compiler = types.ModuleType("scripts.agentos_plan_adoption")
    fake_compiler.MARKER = "AMBIENT-COMPILER"
    sys.modules.update(
        {
            "scripts": ambient_package,
            "scripts.agentos": fake_owner,
            "scripts.agentos_project_plan_contract": fake_contract,
            "scripts.agentos_plan_adoption": fake_compiler,
        }
    )
    try:
        captured = _capture(repo, code_commit, head)
        assert captured.compiler.MARKER == "compiler-ambient"
        assert captured.owner.MARKER == "owner-ambient"
        assert captured.owner.bound_contract().MARKER == "contract-ambient"
    finally:
        for name, module in before.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    _assert_clean_slate(before)


def test_input_refusals(tmp_path):
    repo, code_commit, head = _build_repo(tmp_path, "inputs")
    _unavailable(
        capture_project_plan_adoption_compilers,
        macro_root="relative/root", expected_macro_sha=head, code_commit=code_commit,
    )
    _unavailable(
        capture_project_plan_adoption_compilers,
        macro_root=str(repo), expected_macro_sha="0" * 39, code_commit=code_commit,
    )
    _unavailable(
        capture_project_plan_adoption_compilers,
        macro_root=str(repo), expected_macro_sha=head, code_commit=code_commit, timeout=0,
    )
    _unavailable(
        capture_project_plan_adoption_compilers,
        macro_root=str(repo), expected_macro_sha=head, code_commit=code_commit, timeout=16.0,
    )
    _unavailable(
        capture_project_plan_adoption_compilers,
        macro_root=str(repo), expected_macro_sha=head, code_commit=code_commit, runner="not-callable",
    )
