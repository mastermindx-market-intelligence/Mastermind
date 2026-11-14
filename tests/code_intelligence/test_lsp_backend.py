"""C0 falsifier — direct LSP candidate adapter.

These tests exercise the ADAPTER against a controlled stand-in server. They
prove root binding, refusal of workspace-mutating methods, position mapping,
bounded output, explicit degradation and two-worktree isolation. They make no
claim about any real language server's semantic power — that requires a real
pinned binary and is reported separately.
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
from experiments.code_intelligence.jsonrpc_stdio import JsonRpcError
from experiments.code_intelligence.lsp_backend import (
    DirectLspBackend,
    LspBackendError,
)
from experiments.code_intelligence.workspace_seal import (
    capture_workspace_seal,
    create_external_scratch,
    verify_workspace_seal,
)

PYTHON = Path(sys.executable).resolve()
SERVER = Path(__file__).parent / "servers" / "fake_lsp_server.py"
CORPUS = Path("tests/fixtures/code_intelligence/python_sample")

GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": "/nonexistent-codeintel-c0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "c0",
    "GIT_AUTHOR_EMAIL": "c0@example.invalid",
    "GIT_COMMITTER_NAME": "c0",
    "GIT_COMMITTER_EMAIL": "c0@example.invalid",
}


@functools.lru_cache(maxsize=1)
def _python_digest() -> str:
    return hashlib.sha256(PYTHON.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True, env=GIT_ENV, shell=False,
    )


def _make_corpus_repo(base: Path, marker: str | None = None) -> Path:
    root = base
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CORPUS / "src", root / "src")
    shutil.copytree(CORPUS / "tests", root / "tests")
    if marker:
        (root / "src" / "sample" / "marker.py").write_text(
            f"def {marker}() -> str:\n    return \"{marker}\"\n", encoding="utf-8"
        )
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "corpus")
    return root


def _spec(mode: str = "ok") -> ExecutableSpec:
    server_digest = hashlib.sha256(SERVER.read_bytes()).hexdigest()
    return ExecutableSpec(
        path=PYTHON,
        sha256=_python_digest(),
        argv_suffix=(str(SERVER), mode),
        argv_digests=((str(SERVER), server_digest),),
        targets=((
            "python:fake-lsp", server_digest, "stand_in", "mastermind-tests", "source",
            "argv_file:1",
        ),),
        target_sources=(("python:fake-lsp", SERVER.resolve()),),
    )


class _Harness:
    def __init__(self, root: Path, scratch: Path, mode: str = "ok") -> None:
        self.seal = capture_workspace_seal(root)
        self.scratch = create_external_scratch(parent=scratch, seal=self.seal)
        self.backend = DirectLspBackend(spec=_spec(mode), language="python")
        self.backend.start(seal=self.seal, scratch=self.scratch)

    def close(self) -> None:
        self.backend.close()


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    # Module-scoped on purpose: every test using this fixture is read-only, and
    # a fresh git repo + language-server launch per test cost ~11 minutes of the
    # 25-minute repository gate. Tests that mutate the tree build their own.
    base = tmp_path_factory.mktemp("lsp-shared")
    root = _make_corpus_repo(base / "repo")
    item = _Harness(root, base / "scratch")
    yield item
    item.close()


class TestRootBinding:
    def test_initialize_binds_exactly_the_sealed_root(self, harness: _Harness) -> None:
        assert harness.backend.initialized_root_uri == "file://" + harness.seal.resolved_root

    def test_workspace_status_reports_ready_and_bounded(self, harness: _Harness) -> None:
        status = harness.backend.workspace_status()
        assert status["ready"] is True
        assert status["language"] == "python"
        for value in status.values():
            assert not (isinstance(value, str) and value.startswith("/"))

    def test_foreign_locations_are_refused(self, tmp_path: Path) -> None:
        root = _make_corpus_repo(tmp_path / "repo")
        item = _Harness(root, tmp_path / "scratch", mode="wrong_root")
        try:
            with pytest.raises(LspBackendError) as excinfo:
                item.backend.find_symbol(name="LiveProducer", relative_file=None, limit=10)
            assert excinfo.value.code == "LSP_FOREIGN_LOCATION"
        finally:
            item.close()


class TestSemanticMapping:
    def test_find_symbol_returns_one_based_relative_rows(self, harness: _Harness) -> None:
        rows = harness.backend.find_symbol(
            name="LiveProducer", relative_file=None, limit=10
        )["rows"]
        assert {"symbol": "LiveProducer", "relative_file": "src/sample/producer.py",
                "line": 20} in [
            {"symbol": r["symbol"], "relative_file": r["relative_file"], "line": r["line"]}
            for r in rows
        ]

    def test_find_references_matches_the_answer_key(self, harness: _Harness) -> None:
        rows = harness.backend.find_references(
            name="consume", relative_file=None, limit=50
        )["rows"]
        found = sorted({(r["relative_file"], r["line"]) for r in rows})
        assert found == [
            ("src/sample/consumer.py", 8),
            ("tests/consumer_case.py", 11),
            ("tests/consumer_case.py", 15),
        ]

    def test_find_implementations_separates_live_from_dead(self, harness: _Harness) -> None:
        rows = harness.backend.find_implementations(
            name="Producer", relative_file=None, limit=10
        )["rows"]
        names = sorted({r["symbol"] for r in rows})
        assert names == ["DeadProducer", "LiveProducer"]

    def test_symbol_overview_of_one_file(self, harness: _Harness) -> None:
        rows = harness.backend.symbol_overview(
            relative_file="src/sample/producer.py", query=None, limit=50
        )["rows"]
        assert sorted(r["symbol"] for r in rows) == [
            "DeadProducer", "LiveProducer", "Producer",
            "make_dead_producer", "make_producer",
        ]

    def test_diagnostics_find_the_planted_undefined_name(self, harness: _Harness) -> None:
        rows = harness.backend.diagnostics(
            relative_file="src/sample/consumer.py", limit=10
        )["rows"]
        assert any(
            r["relative_file"] == "src/sample/consumer.py" and r["line"] == 15
            for r in rows
        )

    def test_rows_are_sorted_and_deduplicated(self, harness: _Harness) -> None:
        rows = harness.backend.find_references(
            name="consume", relative_file=None, limit=50
        )["rows"]
        keys = [(r["relative_file"], r["line"], r.get("character", 0)) for r in rows]
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys))

    def test_limit_is_honoured(self, harness: _Harness) -> None:
        rows = harness.backend.symbol_overview(
            relative_file=None, query=None, limit=2
        )["rows"]
        assert len(rows) <= 2


class TestRefusals:
    def test_unknown_relative_file_is_refused(self, harness: _Harness) -> None:
        with pytest.raises(LspBackendError) as excinfo:
            harness.backend.diagnostics(relative_file="src/absent.py", limit=10)
        assert excinfo.value.code == "FILE_NOT_IN_SEAL"

    def test_traversal_relative_file_is_refused(self, harness: _Harness) -> None:
        with pytest.raises(LspBackendError) as excinfo:
            harness.backend.diagnostics(relative_file="../outside.py", limit=10)
        assert excinfo.value.code in {"FILE_NOT_IN_SEAL", "INVALID_LOCATION"}

    def test_workspace_mutating_methods_are_never_sent(self, harness: _Harness) -> None:
        harness.backend.find_symbol(name="Producer", relative_file=None, limit=5)
        harness.backend.diagnostics(relative_file="src/sample/consumer.py", limit=5)
        assert harness.backend.methods_used <= harness.backend.ADMITTED_METHODS

    def test_admitted_method_set_excludes_mutation(self, harness: _Harness) -> None:
        forbidden = {
            "workspace/didChangeWorkspaceFolders",
            "workspace/executeCommand",
            "workspace/applyEdit",
            "textDocument/didChange",
            "textDocument/rename",
        }
        assert not (harness.backend.ADMITTED_METHODS & forbidden)

    def test_server_never_recorded_a_refused_call(self, harness: _Harness) -> None:
        census = harness.backend.refused_census()
        assert census == []


class TestDegradation:
    def test_missing_capability_is_explicit_not_silent(self, tmp_path: Path) -> None:
        root = _make_corpus_repo(tmp_path / "repo")
        item = _Harness(root, tmp_path / "scratch", mode="no_impl")
        try:
            with pytest.raises(LspBackendError) as excinfo:
                item.backend.find_implementations(
                    name="Producer", relative_file=None, limit=10
                )
            assert excinfo.value.code == "LSP_CAPABILITY_UNAVAILABLE"
        finally:
            item.close()

    def test_a_hung_server_surfaces_a_typed_timeout(self, tmp_path: Path) -> None:
        root = _make_corpus_repo(tmp_path / "repo")
        item = _Harness(root, tmp_path / "scratch", mode="slow")
        try:
            with pytest.raises((LspBackendError, JsonRpcError)) as excinfo:
                item.backend.symbol_overview(
                    relative_file="src/sample/producer.py", query=None, limit=5,
                    timeout=2,
                )
            assert excinfo.value.code in {"REQUEST_TIMEOUT", "LSP_REQUEST_FAILED"}
        finally:
            item.close()


class TestZeroWriteAndIsolation:
    def test_backend_never_writes_the_candidate_tree(self, harness: _Harness) -> None:
        harness.backend.symbol_overview(relative_file=None, query=None, limit=50)
        harness.backend.find_references(name="consume", relative_file=None, limit=50)
        harness.backend.diagnostics(relative_file="src/sample/consumer.py", limit=50)
        verify_workspace_seal(harness.seal)  # raises if a single byte moved

    def test_two_worktrees_never_cross_read(self, tmp_path: Path) -> None:
        alpha_root = _make_corpus_repo(tmp_path / "alpha", marker="WORKTREE_ALPHA_ONLY")
        beta_root = _make_corpus_repo(tmp_path / "beta", marker="WORKTREE_BETA_ONLY")
        alpha = _Harness(alpha_root, tmp_path / "scratch-a")
        beta = _Harness(beta_root, tmp_path / "scratch-b")
        try:
            alpha_rows = alpha.backend.symbol_overview(
                relative_file=None, query=None, limit=100
            )["rows"]
            beta_rows = beta.backend.symbol_overview(
                relative_file=None, query=None, limit=100
            )["rows"]
            alpha_names = {r["symbol"] for r in alpha_rows}
            beta_names = {r["symbol"] for r in beta_rows}
            assert "WORKTREE_ALPHA_ONLY" in alpha_names
            assert "WORKTREE_BETA_ONLY" not in alpha_names
            assert "WORKTREE_BETA_ONLY" in beta_names
            assert "WORKTREE_ALPHA_ONLY" not in beta_names
        finally:
            alpha.close()
            beta.close()

    def test_identity_records_the_pinned_executable(self, harness: _Harness) -> None:
        identity = harness.backend.identity
        assert identity.kind == "direct_lsp"
        assert identity.executable_sha256 == _python_digest()
        assert identity.language_servers


class TestB5Containment:
    """B5 — containment and publication must be fail-closed, not lexical."""

    def _harness(self, tmp_path: Path, mode: str) -> _Harness:
        return _Harness(_make_corpus_repo(tmp_path / "repo"), tmp_path / "scratch", mode)

    def test_percent_encoded_traversal_is_refused(self, tmp_path: Path) -> None:
        item = self._harness(tmp_path, "traversal")
        try:
            with pytest.raises(LspBackendError) as excinfo:
                item.backend.symbol_overview(
                    relative_file="src/sample/producer.py", query=None, limit=10
                )
            assert excinfo.value.code in {"LSP_FOREIGN_LOCATION", "LSP_URI_TRAVERSAL"}
        finally:
            item.close()

    def test_symlink_escape_is_refused_at_seal_time(self, tmp_path: Path) -> None:
        # Defence in depth: a tree containing a symlink that escapes the root
        # cannot even be SEALED, so no backend ever gets the chance to follow it.
        from experiments.code_intelligence.workspace_seal import WorkspaceSealError

        root = _make_corpus_repo(tmp_path / "repo")
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        (root / "escape_link").symlink_to(outside)
        with pytest.raises(WorkspaceSealError) as excinfo:
            _Harness(root, tmp_path / "scratch", "symlink_escape")
        assert excinfo.value.code == "TREE_TRAVERSAL_REFUSED"

    def test_a_symlinked_uri_inside_the_seal_is_still_strictly_resolved(
        self, tmp_path: Path
    ) -> None:
        # The adapter's own containment check, independent of the seal.
        item = self._harness(tmp_path, "ok")
        try:
            outside = tmp_path / "elsewhere.py"
            outside.write_text("x = 1\n", encoding="utf-8")
            with pytest.raises(LspBackendError) as excinfo:
                item.backend._resolve_uri("file://" + str(outside))
            assert excinfo.value.code == "LSP_URI_TRAVERSAL"
        finally:
            item.close()

    def test_real_document_symbol_range_shape_is_supported(self, tmp_path: Path) -> None:
        # Real servers return DocumentSymbol{range,selectionRange}, not Location.
        item = self._harness(tmp_path, "docsym_range")
        try:
            rows = item.backend.symbol_overview(
                relative_file="src/sample/producer.py", query=None, limit=50
            )["rows"]
            assert sorted(r["symbol"] for r in rows) == [
                "DeadProducer", "LiveProducer", "Producer",
                "make_dead_producer", "make_producer",
            ]
        finally:
            item.close()

    def test_oversized_nested_payload_is_refused(self, tmp_path: Path) -> None:
        item = self._harness(tmp_path, "wide")
        try:
            with pytest.raises(Exception) as excinfo:
                item.backend.symbol_overview(
                    relative_file="src/sample/producer.py", query=None, limit=100
                )
            # The frame ceiling refuses it before it is ever parsed - an earlier
            # and stronger defence than the payload width bound below.
            assert getattr(excinfo.value, "code", "") in {
                "PROTOCOL_FRAME_TOO_LARGE", "PAYLOAD_TOO_LARGE", "PAYLOAD_TOO_WIDE",
                "PAYLOAD_TOO_MANY_ROWS", "LSP_FOREIGN_LOCATION",
            }
        finally:
            item.close()

    def test_implementation_name_lookup_cannot_read_outside_the_seal(
        self, tmp_path: Path
    ) -> None:
        # _symbol_name_at() used to read root/relative_file before any universal
        # publication guard: a foreign row would have been read from disk.
        item = self._harness(tmp_path, "traversal")
        try:
            with pytest.raises(LspBackendError):
                item.backend.find_implementations(
                    name="Producer", relative_file=None, limit=10
                )
        finally:
            item.close()


class TestB5WirePayloadBounds:
    """The width/size bound is proven directly, not only via the frame ceiling."""

    def test_wide_collection_is_refused(self) -> None:
        from experiments.code_intelligence.backend import (
            MAX_COLLECTION_WIDTH, BackendPayloadError, guard_wire_payload,
        )

        with pytest.raises(BackendPayloadError) as excinfo:
            guard_wire_payload({"rows": [{"i": i} for i in range(MAX_COLLECTION_WIDTH + 1)]})
        assert excinfo.value.code == "PAYLOAD_TOO_WIDE"

    def test_oversized_canonical_payload_is_refused(self) -> None:
        from experiments.code_intelligence.backend import (
            BackendPayloadError, guard_wire_payload,
        )

        with pytest.raises(BackendPayloadError) as excinfo:
            guard_wire_payload({"blob": "x" * (2 * 1024 * 1024)})
        assert excinfo.value.code == "PAYLOAD_TOO_LARGE"

    def test_a_normal_payload_passes(self) -> None:
        from experiments.code_intelligence.backend import guard_wire_payload

        assert guard_wire_payload({"rows": [{"relative_file": "a.py", "line": 1}]})
