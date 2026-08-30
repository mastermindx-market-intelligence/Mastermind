from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import socket
import stat
import uuid
from pathlib import Path

import pytest

from scripts import runtime_observability_sidecar as sidecar_cli
from scripts.runtime_observability_sidecar import (
    CliConfigurationError,
    _observe_owned_socket,
    _remove_owned_socket,
    parse_args,
    validate_cli_configuration,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCER = REPO_ROOT / "common" / "runtime_diagnostics.py"
PACKAGE_ROOT = REPO_ROOT / "integrations" / "runtime_observability"
CLI = REPO_ROOT / "scripts" / "runtime_observability_sidecar.py"


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_producer_imports_only_standard_library_and_common() -> None:
    roots = imported_roots(PRODUCER)
    forbidden = {
        "asyncio",
        "concurrent",
        "httpx",
        "logging",
        "multiprocessing",
        "opentelemetry",
        "psycopg",
        "requests",
        "sqlite3",
        "subprocess",
        "threading",
        "urllib",
    }
    assert roots.isdisjoint(forbidden)
    assert roots <= {
        "__future__",
        "collections",
        "common",
        "dataclasses",
        "datetime",
        "json",
        "math",
        "pathlib",
        "re",
        "socket",
        "typing",
        "uuid",
    }


def test_p0_package_has_no_lifecycle_backend_or_network_clients() -> None:
    forbidden = {
        "control_plane",
        "agentos",
        "boto3",
        "duckdb",
        "grafana",
        "httpx",
        "linear",
        "loki",
        "opentelemetry",
        "prometheus_client",
        "psycopg",
        "requests",
        "slack_sdk",
        "sqlite3",
        "subprocess",
    }
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        assert imported_roots(path).isdisjoint(forbidden), path


def test_p0_source_has_no_business_mutation_vocabulary() -> None:
    forbidden_tokens = {
        "create_job(",
        "claim_job(",
        "requeue(",
        "retry_job(",
        "cancel_worker(",
        "write_runtime_binding(",
        "create_dialogue(",
        "create_wake(",
    }
    paths = [PRODUCER, CLI, *sorted(PACKAGE_ROOT.glob("*.py"))]
    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        for token in forbidden_tokens:
            assert token not in source, (path, token)


def test_producer_has_no_retry_sleep_thread_file_or_tcp_path() -> None:
    source = PRODUCER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in names
    assert "sleep" not in names
    assert "Thread" not in names
    assert "AF_INET" not in source
    assert "AF_INET6" not in source
    assert "SOCK_STREAM" not in source
    assert source.count("sendto(") == 1


def test_cli_accepts_only_absolute_disposable_unix_socket_path() -> None:
    args = parse_args(
        [
            "--socket-path",
            "/tmp/mastermind-observability.sock",
            "--max-events",
            "3",
        ]
    )
    validated = validate_cli_configuration(args, effective_uid=501)
    assert validated.socket_path == Path("/tmp/mastermind-observability.sock").resolve(
        strict=False
    )
    assert validated.max_events == 3


@pytest.mark.parametrize(
    "argv",
    [
        ["--socket-path", "relative.sock"],
        ["--socket-path", "https://example.com/socket"],
        ["--socket-path", "/var/run/mastermind.sock"],
        ["--socket-path", "/tmp/../var/tmp/mastermind.sock"],
        ["--socket-path", "/tmp/mastermind.sock", "--max-events", "0"],
        ["--socket-path", "/tmp/mastermind.sock", "--max-events", "10001"],
    ],
)
def test_cli_refuses_unsafe_configuration(argv: list[str]) -> None:
    args = parse_args(argv)
    with pytest.raises(CliConfigurationError):
        validate_cli_configuration(args, effective_uid=501)


def test_cli_refuses_symlinked_ancestor_below_disposable_root() -> None:
    sandbox = Path("/tmp") / f"mmx-observability-{uuid.uuid4().hex}"
    target = sandbox / "target"
    link = sandbox / "link"
    try:
        target.mkdir(parents=True)
        link.symlink_to(target, target_is_directory=True)
        args = parse_args(["--socket-path", str(link / "diagnostics.sock")])
        with pytest.raises(CliConfigurationError, match="symlink"):
            validate_cli_configuration(args, effective_uid=501)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def test_cleanup_does_not_unlink_replacement_socket() -> None:
    path = Path("/tmp") / f"mmx-observability-{uuid.uuid4().hex}.sock"
    first = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        first.bind(str(path))
        _observed, ownership = _observe_owned_socket(
            path,
            receiver=first,
            effective_uid=os.geteuid(),
        )
        path.unlink()
        replacement.bind(str(path))

        removed = _remove_owned_socket(
            path,
            receiver=first,
            effective_uid=os.geteuid(),
            expected_ownership=ownership,
        )

        assert removed is False
        assert path.exists()
        assert first.fileno() >= 0
    finally:
        first.close()
        replacement.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def test_cleanup_refuses_after_bound_receiver_is_closed() -> None:
    path = Path("/tmp") / f"mmx-observability-{uuid.uuid4().hex}.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        receiver.bind(str(path))
        _observed, ownership = _observe_owned_socket(
            path,
            receiver=receiver,
            effective_uid=os.geteuid(),
        )
        receiver.close()

        removed = _remove_owned_socket(
            path,
            receiver=receiver,
            effective_uid=os.geteuid(),
            expected_ownership=ownership,
        )

        assert removed is False
        assert path.exists()
    finally:
        receiver.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def test_cleanup_unlinks_exact_socket_while_receiver_is_live() -> None:
    path = Path("/tmp") / f"mmx-observability-{uuid.uuid4().hex}.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        receiver.bind(str(path))
        _observed, ownership = _observe_owned_socket(
            path,
            receiver=receiver,
            effective_uid=os.geteuid(),
        )

        removed = _remove_owned_socket(
            path,
            receiver=receiver,
            effective_uid=os.geteuid(),
            expected_ownership=ownership,
        )

        assert removed is True
        assert not path.exists()
        assert receiver.fileno() >= 0
    finally:
        receiver.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def test_main_restores_umask_when_socket_construction_fails(monkeypatch) -> None:
    path = Path("/tmp") / f"mmx-observability-{uuid.uuid4().hex}.sock"
    previous = os.umask(0o027)
    try:
        monkeypatch.setattr(sidecar_cli.os, "geteuid", lambda: 501)

        def fail_socket(*_args, **_kwargs):
            raise OSError("forced socket constructor failure")

        monkeypatch.setattr(sidecar_cli.socket, "socket", fail_socket)
        with pytest.raises(OSError, match="forced socket constructor failure"):
            sidecar_cli.main(["--socket-path", str(path)])

        observed = os.umask(0o027)
        assert observed == 0o027
    finally:
        os.umask(previous)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def test_cli_refuses_root_execution() -> None:
    args = parse_args(["--socket-path", "/tmp/mastermind.sock"])
    with pytest.raises(CliConfigurationError, match="root"):
        validate_cli_configuration(args, effective_uid=0)


def test_cli_defines_only_unix_datagram_transport() -> None:
    source = CLI.read_text(encoding="utf-8")
    assert "AF_UNIX" in source
    assert "SOCK_DGRAM" in source
    assert "AF_INET" not in source
    assert "SOCK_STREAM" not in source
    assert "http://" not in source
    assert "https://" not in source


def test_p0_package_is_importable_without_optional_dependencies() -> None:
    for name in (
        "integrations.runtime_observability",
        "integrations.runtime_observability.contract",
        "integrations.runtime_observability.sinks",
        "integrations.runtime_observability.sidecar",
    ):
        assert importlib.util.find_spec(name) is not None
