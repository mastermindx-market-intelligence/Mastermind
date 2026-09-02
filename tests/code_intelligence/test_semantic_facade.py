"""C0 falsifier — sealed facade dispatcher and pre-turn binding receipt.

The facade is the only thing a model ever touches. It must refuse to serve a
single call until its binding receipt matches the expected seal, and it must
re-verify the seal after every call so that a backend which writes the tree is
caught before its answer is published.
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
from experiments.code_intelligence.lsp_backend import DirectLspBackend
from experiments.code_intelligence.semantic_contract import (
    SemanticContractError,
    semantic_tool_schema_digest,
    validate_semantic_request,
)
from experiments.code_intelligence.semantic_facade import (
    FacadeError,
    SemanticFacade,
)
from experiments.code_intelligence.workspace_seal import (
    capture_workspace_seal,
    create_external_scratch,
    workspace_binding_digest,
)

PYTHON = Path(sys.executable).resolve()
SERVER = Path(__file__).parent / "servers" / "fake_lsp_server.py"
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


def _make_repo(root: Path, marker: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CORPUS / "src", root / "src")
    shutil.copytree(CORPUS / "tests", root / "tests")
    if marker:
        (root / "src" / "sample" / "marker.py").write_text(
            f"def {marker}() -> str:\n    return \"{marker}\"\n", encoding="utf-8"
        )
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "c")):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       capture_output=True, env=GIT_ENV, shell=False)
    return root


def _facade(root: Path, scratch_parent: Path, mode: str = "ok") -> SemanticFacade:
    seal = capture_workspace_seal(root)
    scratch = create_external_scratch(parent=scratch_parent, seal=seal)
    backend = DirectLspBackend(
        spec=ExecutableSpec(path=PYTHON, sha256=_python_digest(),
                            argv_suffix=(str(SERVER), mode)),
        language="python",
    )
    facade = SemanticFacade(seal=seal, backend=backend, scratch=scratch)
    facade.start()
    return facade


@pytest.fixture
def facade(tmp_path: Path):
    item = _facade(_make_repo(tmp_path / "repo"), tmp_path / "scratch")
    yield item
    item.close()


class TestBindingReceipt:
    def test_receipt_binds_every_required_identity(self, facade: SemanticFacade) -> None:
        receipt = facade.binding_receipt()
        for field in (
            "workspace_binding_digest",
            "facade_source_digest",
            "semantic_schema_digest",
            "backend_identity_digest",
            "language_server_digests",
            "startup_unix_ms",
            "candidate_tree_before",
            "candidate_tree_after",
        ):
            assert field in receipt, field

    def test_schema_digest_in_receipt_matches_the_frozen_contract(
        self, facade: SemanticFacade
    ) -> None:
        assert facade.binding_receipt()["semantic_schema_digest"] == semantic_tool_schema_digest()

    def test_workspace_digest_in_receipt_matches_the_seal(
        self, facade: SemanticFacade
    ) -> None:
        assert facade.binding_receipt()["workspace_binding_digest"] == workspace_binding_digest(
            facade.seal
        )

    def test_calls_are_refused_until_the_receipt_is_validated(self, tmp_path: Path) -> None:
        seal = capture_workspace_seal(_make_repo(tmp_path / "repo"))
        scratch = create_external_scratch(parent=tmp_path / "scratch", seal=seal)
        backend = DirectLspBackend(
            spec=ExecutableSpec(path=PYTHON, sha256=_python_digest(),
                                argv_suffix=(str(SERVER), "ok")),
            language="python",
        )
        facade = SemanticFacade(seal=seal, backend=backend, scratch=scratch)
        with pytest.raises(FacadeError) as excinfo:
            facade.call(validate_semantic_request("workspace_status", {}))
        assert excinfo.value.code == "FACADE_NOT_BOUND"

    def test_receipt_validation_against_a_foreign_seal_is_refused(
        self, facade: SemanticFacade, tmp_path: Path
    ) -> None:
        other = capture_workspace_seal(_make_repo(tmp_path / "other"))
        with pytest.raises(FacadeError) as excinfo:
            facade.validate_binding(expected=other)
        assert excinfo.value.code == "BINDING_RECEIPT_MISMATCH"

    def test_receipt_validation_against_its_own_seal_passes(
        self, facade: SemanticFacade
    ) -> None:
        facade.validate_binding(expected=facade.seal)


class TestDispatch:
    def test_workspace_status_round_trip(self, facade: SemanticFacade) -> None:
        response = facade.call(validate_semantic_request("workspace_status", {}))
        assert response.tool == "workspace_status"
        assert response.workspace_binding_digest == workspace_binding_digest(facade.seal)
        assert response.backend_digest

    def test_find_symbol_round_trip(self, facade: SemanticFacade) -> None:
        response = facade.call(
            validate_semantic_request("find_symbol", {"name": "LiveProducer"})
        )
        rows = response.payload["rows"]
        assert rows and rows[0]["relative_file"] == "src/sample/producer.py"

    def test_every_tool_is_dispatchable(self, facade: SemanticFacade) -> None:
        for tool, args in [
            ("workspace_status", {}),
            ("symbol_overview", {"relative_file": "src/sample/producer.py"}),
            ("find_symbol", {"name": "consume"}),
            ("find_references", {"name": "consume"}),
            ("find_implementations", {"name": "Producer"}),
            ("diagnostics", {"relative_file": "src/sample/consumer.py"}),
        ]:
            assert facade.call(validate_semantic_request(tool, args)).tool == tool

    def test_seal_is_reverified_after_every_call(self, facade: SemanticFacade) -> None:
        facade.call(validate_semantic_request("workspace_status", {}))
        assert facade.seal_verifications >= 2

    def test_backend_write_is_caught_before_publication(
        self, facade: SemanticFacade
    ) -> None:
        (Path(facade.seal.resolved_root) / ".semantic-cache").write_text("x", encoding="utf-8")
        with pytest.raises(FacadeError) as excinfo:
            facade.call(validate_semantic_request("workspace_status", {}))
        assert excinfo.value.code == "CANDIDATE_TREE_WRITE_DETECTED"

    def test_failures_are_not_auto_resent(self, tmp_path: Path) -> None:
        item = _facade(_make_repo(tmp_path / "repo"), tmp_path / "scratch", mode="slow")
        try:
            with pytest.raises(FacadeError):
                item.call(
                    validate_semantic_request(
                        "symbol_overview", {"relative_file": "src/sample/producer.py"}
                    ),
                    timeout=2,
                )
            assert item.backend_calls == 1
        finally:
            item.close()


class TestHostileArguments:
    @pytest.mark.parametrize(
        "bad", ["/etc/passwd", "../outside.py", "src/../../etc/hosts", "~/secret.py"]
    )
    def test_location_escapes_never_reach_the_backend(
        self, facade: SemanticFacade, bad: str
    ) -> None:
        with pytest.raises(SemanticContractError):
            facade.call(validate_semantic_request("diagnostics", {"relative_file": bad}))

    def test_unknown_tool_never_reaches_the_backend(self, facade: SemanticFacade) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("activate_project", {"project": "other"})

    def test_project_switch_argument_is_rejected(self, facade: SemanticFacade) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("find_symbol", {"name": "x", "project": "beta"})


class TestTwoWorktreeIsolation:
    def test_alpha_and_beta_never_cross_read(self, tmp_path: Path) -> None:
        alpha = _facade(
            _make_repo(tmp_path / "alpha", marker="WORKTREE_ALPHA_ONLY"),
            tmp_path / "scratch-a",
        )
        beta = _facade(
            _make_repo(tmp_path / "beta", marker="WORKTREE_BETA_ONLY"),
            tmp_path / "scratch-b",
        )
        try:
            request = validate_semantic_request("symbol_overview", {"limit": 100})
            alpha_names = {r.get("symbol") for r in alpha.call(request).payload["rows"]}
            beta_names = {r.get("symbol") for r in beta.call(request).payload["rows"]}
            assert "WORKTREE_ALPHA_ONLY" in alpha_names
            assert "WORKTREE_BETA_ONLY" not in alpha_names
            assert "WORKTREE_BETA_ONLY" in beta_names
            assert "WORKTREE_ALPHA_ONLY" not in beta_names
        finally:
            alpha.close()
            beta.close()

    def test_the_two_facades_carry_different_binding_digests(self, tmp_path: Path) -> None:
        alpha = _facade(_make_repo(tmp_path / "alpha", marker="A_ONLY"), tmp_path / "sa")
        beta = _facade(_make_repo(tmp_path / "beta", marker="B_ONLY"), tmp_path / "sb")
        try:
            assert (
                alpha.binding_receipt()["workspace_binding_digest"]
                != beta.binding_receipt()["workspace_binding_digest"]
            )
        finally:
            alpha.close()
            beta.close()
