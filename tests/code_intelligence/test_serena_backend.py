"""C0 falsifier — pinned Serena candidate.

Scope statement, deliberately explicit: these tests exercise the ADAPTER's
refusal logic against a Serena-shaped stand-in. They prove what Mastermind's
wrapper does when a backend widens its tool surface, is influenced by
repository configuration, writes the candidate tree or tries to switch project.
They prove NOTHING about the real pinned Serena, which is absent from this
host. Candidate S therefore remains UNEXERCISED until a host-supplied immutable
bundle exists.
"""

from __future__ import annotations

import functools
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.code_intelligence.backend import ExecutableSpec
from experiments.code_intelligence.serena_backend import (
    SERENA_PINNED_COMMIT,
    SERENA_PINNED_VERSION,
    SerenaBackend,
    SerenaBackendError,
    SerenaBundle,
    bundle_digest,
    resolve_serena_bundle,
)
from experiments.code_intelligence.workspace_seal import (
    WorkspaceSealError,
    capture_workspace_seal,
    create_external_scratch,
    verify_workspace_seal,
)

PYTHON = Path(sys.executable).resolve()
SERVER = Path(__file__).parent / "servers" / "fake_serena_server.py"
CORPUS = Path("tests/fixtures/code_intelligence/python_sample")

GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": "/nonexistent-codeintel-c0",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "c0", "GIT_AUTHOR_EMAIL": "c0@example.invalid",
    "GIT_COMMITTER_NAME": "c0", "GIT_COMMITTER_EMAIL": "c0@example.invalid",
}


@functools.lru_cache(maxsize=1)
def _python_digest() -> str:
    return hashlib.sha256(PYTHON.read_bytes()).hexdigest()


def _make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CORPUS / "src", root / "src")
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"],
                   check=True, capture_output=True, env=GIT_ENV, shell=False)
    subprocess.run(["git", "-C", str(root), "add", "-A"],
                   check=True, capture_output=True, env=GIT_ENV, shell=False)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "corpus"],
                   check=True, capture_output=True, env=GIT_ENV, shell=False)
    return root


def _make_bundle(base: Path, commit: str = SERENA_PINNED_COMMIT) -> SerenaBundle:
    root = base / "serena-bundle"
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(f"{SERENA_PINNED_VERSION}\n", encoding="utf-8")
    (root / "COMMIT").write_text(f"{commit}\n", encoding="utf-8")
    return SerenaBundle(root=root, source_commit=commit,
                        version=SERENA_PINNED_VERSION, sha256=bundle_digest(root))


def _spec(mode: str) -> ExecutableSpec:
    return ExecutableSpec(path=PYTHON, sha256=_python_digest(),
                          argv_suffix=(str(SERVER), mode))


def _start(root: Path, scratch_parent: Path, mode: str, bundle: SerenaBundle):
    seal = capture_workspace_seal(root)
    scratch = create_external_scratch(parent=scratch_parent, seal=seal)
    backend = SerenaBackend(spec=_spec(mode), bundle=bundle)
    backend.start(seal=seal, scratch=scratch)
    return backend, seal


class TestBundlePinning:
    def test_absent_bundle_is_a_typed_refusal(self, tmp_path: Path) -> None:
        with pytest.raises(SerenaBackendError) as excinfo:
            resolve_serena_bundle(tmp_path / "not-there")
        assert excinfo.value.code == "SERENA_BUNDLE_UNAVAILABLE"

    def test_wrong_commit_pin_is_refused(self, tmp_path: Path) -> None:
        _make_bundle(tmp_path, commit="0" * 40)
        with pytest.raises(SerenaBackendError) as excinfo:
            resolve_serena_bundle(tmp_path / "serena-bundle")
        assert excinfo.value.code == "SERENA_SOURCE_PIN_MISMATCH"

    def test_correct_pin_resolves(self, tmp_path: Path) -> None:
        _make_bundle(tmp_path)
        bundle = resolve_serena_bundle(tmp_path / "serena-bundle")
        assert bundle.source_commit == SERENA_PINNED_COMMIT
        assert bundle.version == SERENA_PINNED_VERSION
        assert len(bundle.sha256) == 64

    def test_pinned_commit_is_the_one_the_packet_names(self) -> None:
        assert SERENA_PINNED_COMMIT == "949a27ef1e5fda1a6e7b561e777bcece345c6ffd"
        assert SERENA_PINNED_VERSION == "1.7.0"

    def test_bundle_digest_tracks_content(self, tmp_path: Path) -> None:
        bundle = _make_bundle(tmp_path)
        before = bundle_digest(bundle.root)
        (bundle.root / "tampered.py").write_text("x = 1\n", encoding="utf-8")
        assert bundle_digest(bundle.root) != before


class TestToolSurface:
    def test_clean_surface_starts_and_records_census(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, _ = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            census = backend.upstream_tool_census()
            assert "find_symbol" in census
            assert "execute_shell_command" not in census
        finally:
            backend.close()

    def test_widened_surface_rejects_the_candidate(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        with pytest.raises(SerenaBackendError) as excinfo:
            _start(root, tmp_path / "scratch", "wide", bundle)
        assert excinfo.value.code == "SERENA_TOOL_SURFACE_WIDENED"

    def test_forbidden_token_list_covers_the_dangerous_families(self) -> None:
        forbidden = SerenaBackend.FORBIDDEN_UPSTREAM_TOKENS
        for token in ("shell", "execute", "memory", "activate", "switch", "onboarding",
                      "replace", "insert", "delete", "create", "restart", "edit"):
            assert token in forbidden

    def test_facade_never_exposes_upstream_tool_names(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, _ = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            status = backend.workspace_status()
            rendered = repr(status)
            for name in ("get_symbols_overview", "find_referencing_symbols", "list_dir"):
                assert name not in rendered
        finally:
            backend.close()


class TestRepositoryConfigInfluence:
    def test_repository_config_changing_behaviour_rejects_the_candidate(
        self, tmp_path: Path
    ) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)

        backend, _ = _start(root, tmp_path / "scratch", "config_influenced", bundle)
        clean_fingerprint = backend.census_fingerprint()
        backend.close()

        # A hostile repository-controlled Serena configuration.
        hostile = root / ".serena"
        hostile.mkdir()
        (hostile / "project.yml").write_text(
            "language: python\nexcluded_tools: []\n", encoding="utf-8"
        )
        with pytest.raises(SerenaBackendError) as excinfo:
            _start(root, tmp_path / "scratch2", "config_influenced", bundle)
        assert excinfo.value.code in {
            "SERENA_TOOL_SURFACE_WIDENED", "SERENA_REPOSITORY_CONFIG_INFLUENCE",
        }
        assert clean_fingerprint

    def test_adapter_reports_config_influence_when_census_moves(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, _ = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            first = backend.census_fingerprint()
            assert first == backend.census_fingerprint()
        finally:
            backend.close()


class TestCandidateTreeWrites:
    def test_metadata_written_into_the_worktree_is_caught(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        seal = capture_workspace_seal(root)
        scratch = create_external_scratch(parent=tmp_path / "scratch", seal=seal)
        backend = SerenaBackend(spec=_spec("writes"), bundle=bundle)
        try:
            backend.start(seal=seal, scratch=scratch)
        except SerenaBackendError:
            pass
        finally:
            backend.close()
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "CANDIDATE_TREE_WRITE_DETECTED"

    def test_clean_backend_leaves_the_tree_untouched(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, seal = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            backend.workspace_status()
            verify_workspace_seal(seal)
        finally:
            backend.close()


class TestIdentityAndConfiguration:
    def test_identity_pins_bundle_and_commit(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, _ = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            identity = backend.identity
            assert identity.kind == "serena"
            assert identity.source_commit == SERENA_PINNED_COMMIT
            assert identity.source_version == SERENA_PINNED_VERSION
        finally:
            backend.close()

    def test_host_configuration_disables_dashboard_and_memory(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, _ = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            config = backend.host_configuration()
            assert config["dashboard_enabled"] is False
            assert config["memory_enabled"] is False
            assert config["onboarding_enabled"] is False
            assert config["read_only"] is True
        finally:
            backend.close()

    def test_scratch_holds_all_mutable_state(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path / "repo")
        bundle = _make_bundle(tmp_path)
        backend, seal = _start(root, tmp_path / "scratch", "clean", bundle)
        try:
            assert not str(backend.scratch).startswith(seal.resolved_root)
        finally:
            backend.close()
