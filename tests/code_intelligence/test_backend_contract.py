"""C0 falsifier — backend protocol conformance and response bounding.

A backend may be swapped; the surface it answers through may not. These tests
pin the shape both candidates must satisfy and prove that a backend cannot leak
host state, secrets or unbounded results through its payload.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.code_intelligence.backend import (
    BackendIdentity,
    BackendPayloadError,
    ExecutableSpec,
    SemanticBackend,
    backend_identity_digest,
    guard_payload,
)
from experiments.code_intelligence.semantic_contract import MAX_LIMIT
from experiments.code_intelligence.workspace_seal import WorkspaceSeal


def _identity(kind: str = "fake") -> BackendIdentity:
    return BackendIdentity(
        kind=kind,
        source_version="0.0.0",
        source_commit="0" * 40,
        executable_sha256="a" * 64,
        language_servers=(("fake-python", "b" * 64),),
        configuration_digest="c" * 64,
    )


class FakeBackend:
    """Minimal conforming backend used to pin the protocol."""

    def __init__(self) -> None:
        self.started = False
        self.closed = False

    @property
    def identity(self) -> BackendIdentity:
        return _identity()

    def start(self, *, seal: WorkspaceSeal, scratch: Path) -> None:
        self.started = True

    def workspace_status(self):
        return guard_payload({"ready": True, "language_servers": ["fake-python"]})

    def symbol_overview(self, *, relative_file, query, limit):
        return guard_payload(
            {"rows": [{"symbol": "consume", "relative_file": "src/sample/consumer.py", "line": 8}]}
        )

    def find_symbol(self, *, name, relative_file, limit):
        return guard_payload(
            {"rows": [{"symbol": name, "relative_file": "src/sample/producer.py", "line": 20}]}
        )

    def find_references(self, *, name, relative_file, limit):
        return guard_payload(
            {"rows": [{"symbol": name, "relative_file": "src/sample/consumer.py", "line": 9}]}
        )

    def find_implementations(self, *, name, relative_file, limit):
        return guard_payload(
            {"rows": [{"symbol": "LiveProducer", "relative_file": "src/sample/producer.py", "line": 20}]}
        )

    def diagnostics(self, *, relative_file, limit):
        return guard_payload(
            {"rows": [{"relative_file": "src/sample/consumer.py", "line": 15, "kind": "undefined-name"}]}
        )

    def close(self) -> None:
        self.closed = True


class TestProtocolConformance:
    def test_fake_backend_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeBackend(), SemanticBackend)

    def test_every_facade_tool_has_a_backend_method(self) -> None:
        backend = FakeBackend()
        for tool in (
            "workspace_status",
            "symbol_overview",
            "find_symbol",
            "find_references",
            "find_implementations",
            "diagnostics",
        ):
            assert callable(getattr(backend, tool))

    def test_incomplete_backend_does_not_satisfy_the_protocol(self) -> None:
        class Partial:
            @property
            def identity(self) -> BackendIdentity:
                return _identity()

        assert not isinstance(Partial(), SemanticBackend)

    def test_identity_is_stable_and_digestible(self) -> None:
        backend = FakeBackend()
        first = backend_identity_digest(backend.identity)
        assert first == backend_identity_digest(backend.identity)
        assert len(first) == 64

    def test_identity_digest_tracks_every_field(self) -> None:
        base = _identity()
        digest = backend_identity_digest(base)
        for field, value in [
            ("kind", "other"),
            ("source_version", "9.9.9"),
            ("source_commit", "1" * 40),
            ("executable_sha256", "d" * 64),
            ("language_servers", (("x", "e" * 64),)),
            ("configuration_digest", "f" * 64),
        ]:
            mutated = BackendIdentity(
                **{**{k: getattr(base, k) for k in base.__dataclass_fields__}, field: value}
            )
            assert backend_identity_digest(mutated) != digest, field

    def test_identity_is_immutable(self) -> None:
        identity = _identity()
        with pytest.raises(Exception):
            identity.kind = "mutated"  # type: ignore[misc]


class TestPayloadGuard:
    def test_good_payload_passes_through(self) -> None:
        payload = guard_payload(
            {"rows": [{"symbol": "x", "relative_file": "src/a.py", "line": 1}]}
        )
        assert payload["rows"][0]["relative_file"] == "src/a.py"

    @pytest.mark.parametrize(
        "leak",
        [
            {"rows": [{"relative_file": "/Users/chriswong/secret.py", "line": 1}]},
            {"rows": [{"relative_file": "src/a.py", "line": 1, "note": "/opt/homebrew/bin/node"}]},
            {"note": "C:\\Windows\\system32"},
        ],
    )
    def test_absolute_paths_are_refused(self, leak: dict) -> None:
        with pytest.raises(BackendPayloadError) as excinfo:
            guard_payload(leak)
        assert excinfo.value.code == "PAYLOAD_ABSOLUTE_PATH"

    @pytest.mark.parametrize(
        "key", ["env", "environ", "argv", "command", "executable", "cwd", "root", "project_path"]
    )
    def test_host_control_keys_are_refused(self, key: str) -> None:
        with pytest.raises(BackendPayloadError) as excinfo:
            guard_payload({key: "anything"})
        assert excinfo.value.code == "PAYLOAD_HOST_LEAK"

    @pytest.mark.parametrize(
        "secret",
        [
            "ghp_0123456789012345678901234567890123456",
            "-----BEGIN RSA PRIVATE KEY-----",
            "xoxb-1111-2222-abcdefg",
            "AKIAIOSFODNN7EXAMPLE",
        ],
    )
    def test_secret_material_is_refused(self, secret: str) -> None:
        with pytest.raises(BackendPayloadError) as excinfo:
            guard_payload({"rows": [{"relative_file": "src/a.py", "line": 1, "note": secret}]})
        assert excinfo.value.code == "PAYLOAD_SECRET_SUSPECTED"

    def test_too_many_rows_are_refused(self) -> None:
        rows = [{"relative_file": "src/a.py", "line": i} for i in range(MAX_LIMIT + 1)]
        with pytest.raises(BackendPayloadError) as excinfo:
            guard_payload({"rows": rows})
        assert excinfo.value.code == "PAYLOAD_TOO_MANY_ROWS"

    def test_row_ceiling_exactly_at_limit_is_allowed(self) -> None:
        rows = [{"relative_file": "src/a.py", "line": i} for i in range(MAX_LIMIT)]
        assert len(guard_payload({"rows": rows})["rows"]) == MAX_LIMIT

    def test_traversal_in_a_row_is_refused(self) -> None:
        with pytest.raises(BackendPayloadError) as excinfo:
            guard_payload({"rows": [{"relative_file": "../outside.py", "line": 1}]})
        assert excinfo.value.code == "PAYLOAD_PATH_TRAVERSAL"

    def test_nul_byte_is_refused(self) -> None:
        with pytest.raises(BackendPayloadError):
            guard_payload({"rows": [{"relative_file": "src/a\x00.py", "line": 1}]})

    def test_excessive_nesting_is_refused(self) -> None:
        deep: dict = {"a": {}}
        cursor = deep["a"]
        for _ in range(50):
            cursor["a"] = {}
            cursor = cursor["a"]
        with pytest.raises(BackendPayloadError) as excinfo:
            guard_payload(deep)
        assert excinfo.value.code == "PAYLOAD_TOO_DEEP"


class TestExecutableSpec:
    def test_spec_is_immutable(self, tmp_path: Path) -> None:
        spec = ExecutableSpec(path=tmp_path / "bin", sha256="a" * 64, argv_suffix=())
        with pytest.raises(Exception):
            spec.sha256 = "b" * 64  # type: ignore[misc]

    def test_spec_rejects_a_malformed_digest(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            ExecutableSpec(path=tmp_path / "bin", sha256="not-a-digest", argv_suffix=())

    def test_argv_suffix_must_be_a_tuple_of_strings(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            ExecutableSpec(path=tmp_path / "bin", sha256="a" * 64, argv_suffix=("ok", 3))  # type: ignore[arg-type]


class TestFakeBackendBehaviour:
    def test_lifecycle_flags(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        seal = WorkspaceSeal(
            resolved_root=str(tmp_path), device=1, inode=2, uid=3, gid=4,
            git_common_dir="g", git_dir="g", head_sha="0" * 40,
            status_porcelain_v2_sha256="1" * 64, candidate_tree_sha256="2" * 64,
        )
        backend.start(seal=seal, scratch=tmp_path)
        assert backend.started
        backend.close()
        assert backend.closed

    def test_all_tools_return_bounded_relative_locations(self) -> None:
        backend = FakeBackend()
        for payload in (
            backend.symbol_overview(relative_file=None, query=None, limit=10),
            backend.find_symbol(name="Producer", relative_file=None, limit=10),
            backend.find_references(name="consume", relative_file=None, limit=10),
            backend.find_implementations(name="Producer", relative_file=None, limit=10),
            backend.diagnostics(relative_file=None, limit=10),
        ):
            for row in payload["rows"]:
                assert not row["relative_file"].startswith("/")
                assert ".." not in row["relative_file"]
