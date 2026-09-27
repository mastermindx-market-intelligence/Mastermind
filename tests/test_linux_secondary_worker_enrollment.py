from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "enroll_linux_secondary_worker.py"


def _load():
    assert SCRIPT.is_file(), "Linux secondary enrollment wrapper is not implemented"
    spec = importlib.util.spec_from_file_location("enroll_linux_secondary_worker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def _source_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "fixture@example.invalid", cwd=repo)
    _git("config", "user.name", "Fixture", cwd=repo)
    (repo / "control_plane").mkdir()
    (repo / "ops" / "executive_os").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "control_plane" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "ops" / "executive_os" / "release_manifest.py").write_text(
        "print('fixture')\n", encoding="utf-8"
    )
    (repo / "scripts" / "executive_os_linux_worker.py").write_text(
        "print('worker')\n", encoding="utf-8"
    )
    (repo / "scripts" / "executive_os_remote_worker_gateway.py").write_text(
        "print('gateway')\n", encoding="utf-8"
    )
    for name in (
        "mastermind-executive-worker.service.template",
        "mastermind-executive-worker.socket.template",
        "mastermind-executive-remote-worker-gateway.service.template",
    ):
        (repo / "ops" / "executive_os" / name).write_text("[Unit]\n", encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "fixture", cwd=repo)
    return repo, _git("rev-parse", "HEAD", cwd=repo), _git("rev-parse", "HEAD^{tree}", cwd=repo)


def test_closed_cli_and_bounded_claim() -> None:
    m = _load()
    parser = m._parser()
    actions = parser.parse_args(
        [
            "--source-repo",
            "/root/mastermind",
            "--expected-sha",
            "a" * 40,
            "--expected-tree",
            "b" * 40,
            "--codex-source-binary",
            "/tmp/codex",
            "--codex-version",
            "0.157.1",
            "--codex-sha256",
            "c" * 64,
        ]
    )
    assert actions.expected_sha == "a" * 40
    assert actions.codex_sha256 == "c" * 64
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "--host",
        "--worker-id",
        "--provider",
        "--credential",
        "--token",
        "--password",
        "--enable",
        "--start",
        "--restart",
        "--capacity",
    ):
        assert forbidden not in source
    assert "READY_FOR_PROVIDER_AND_MTLS_ENROLLMENT" in source
    assert "WORKER_READY" not in source
    assert "CAPACITY_READY" not in source


def test_source_identity_is_exact_and_clean(tmp_path: Path) -> None:
    m = _load()
    repo, sha, tree = _source_repo(tmp_path)
    observed = m.verify_source_identity(repo, sha, tree)
    assert observed == {"commit": sha, "tree": tree}

    (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(m.EnrollmentError, match="dirty"):
        m.verify_source_identity(repo, sha, tree)


def test_source_identity_refuses_wrong_commit_or_tree(tmp_path: Path) -> None:
    m = _load()
    repo, sha, tree = _source_repo(tmp_path)
    with pytest.raises(m.EnrollmentError, match="commit"):
        m.verify_source_identity(repo, "0" * 40, tree)
    with pytest.raises(m.EnrollmentError, match="tree"):
        m.verify_source_identity(repo, sha, "0" * 40)


def test_release_archive_scope_excludes_vendor_and_unneeded_surfaces() -> None:
    m = _load()
    assert m.RELEASE_PATHS == (
        "control_plane",
        "ops/executive_os",
        "scripts/executive_os_linux_worker.py",
        "scripts/executive_os_remote_worker_gateway.py",
    )
    assert all("vendor" not in item for item in m.RELEASE_PATHS)


def test_fixed_linux_identities_reuse_executive_numbers() -> None:
    m = _load()
    assert m.CONTROL_USER == "_mastermind_exec"
    assert m.CONTROL_GROUP == "_mastermind_exec"
    assert m.CONTROL_UID == 450
    assert m.CONTROL_GID == 450
    assert m.WORKER_USER == "_mastermind_worker"
    assert m.WORKER_GROUP == "_mastermind_worker"
    assert m.WORKER_UID == 451
    assert m.WORKER_GID == 451


def test_identity_plan_refuses_collisions() -> None:
    m = _load()
    clean = {
        "users_by_name": {},
        "users_by_uid": {},
        "groups_by_name": {},
        "groups_by_gid": {},
    }
    plan = m.classify_identity_plan(clean)
    assert plan["control"] == "create"
    assert plan["worker"] == "create"

    collision = json.loads(json.dumps(clean))
    collision["users_by_uid"]["450"] = "somebody"
    with pytest.raises(m.EnrollmentError, match="UID 450"):
        m.classify_identity_plan(collision)

    exact = {
        "users_by_name": {
            "_mastermind_exec": {"uid": 450, "gid": 450, "home": "/var/lib/mastermind-executive/control/home", "shell": "/usr/sbin/nologin"},
            "_mastermind_worker": {"uid": 451, "gid": 451, "home": "/var/lib/mastermind-executive/workers/codex-01/provider-home", "shell": "/usr/sbin/nologin"},
        },
        "users_by_uid": {"450": "_mastermind_exec", "451": "_mastermind_worker"},
        "groups_by_name": {"_mastermind_exec": 450, "_mastermind_worker": 451},
        "groups_by_gid": {"450": "_mastermind_exec", "451": "_mastermind_worker"},
    }
    assert m.classify_identity_plan(exact) == {"control": "verify", "worker": "verify"}


def test_central_control_antiduplication_is_observation_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for unit in (
        "mastermind-executive-control.service",
        "mastermind-executive-mcp.service",
        "mastermind-executive-sol-state-relay.service",
    ):
        assert unit in source
    for forbidden in (
        "systemctl disable",
        "systemctl enable",
        "systemctl start",
        "systemctl restart",
        "systemctl stop",
        "systemctl mask",
        "systemctl unmask",
    ):
        assert forbidden not in source


def test_codex_source_inspection_never_executes_mutable_input(tmp_path: Path) -> None:
    m = _load()
    source = tmp_path / "codex"
    source.write_bytes(b"\x7fELFfixture")
    source.chmod(0o755)

    info = m.inspect_codex_source(source)
    assert info["sha256"]
    assert info["identity"]["size"] == len(b"\x7fELFfixture")

    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(m.EnrollmentError, match="direct"):
        m.inspect_codex_source(link)

    text = SCRIPT.read_text(encoding="utf-8")
    install = text.split("def install_codex_binary(", 1)[1].split("def _safe_archive_members", 1)[0]
    assert "attest_codex_binary" not in install
    assert "subprocess" not in install
    assert "codex_source_digest_not_accepted" in install


def test_rendered_units_are_inert_and_use_stacked_runtime(tmp_path: Path) -> None:
    m = _load()
    release = tmp_path / "release"
    template_root = release / "ops" / "executive_os"
    template_root.mkdir(parents=True)
    for name in (
        "mastermind-executive-worker.service.template",
        "mastermind-executive-worker.socket.template",
        "mastermind-executive-remote-worker-gateway.service.template",
    ):
        source = ROOT / "ops" / "executive_os" / name
        (template_root / name).write_bytes(source.read_bytes())

    rendered = m.render_systemd_units(
        release_root=release,
        codex_binary=Path("/opt/mastermind-executive/bin/codex-0.157.1"),
    )
    worker = rendered["mastermind-executive-worker-codex-01.service"]
    sock = rendered["mastermind-executive-worker-codex-01.socket"]
    gateway = rendered["mastermind-executive-remote-worker-gateway.service"]

    assert "_mastermind_worker" in worker
    assert "scripts/executive_os_linux_worker.py" in worker
    assert "worker-codex-01.json" in worker
    assert "Service=mastermind-executive-worker-codex-01.service" in sock
    assert "_mastermind_exec" in gateway
    assert "scripts/executive_os_remote_worker_gateway.py" in gateway
    assert "__" not in worker + sock + gateway
    for unit in rendered.values():
        active = [line.strip() for line in unit.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        assert "[Install]" not in active
        assert not any(line.startswith("WantedBy=") for line in active)


def test_enrollment_source_never_logs_in_or_arms_provider_or_gateway() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "codex login",
        "claude auth",
        "device-auth",
        "auth.json",
        "provider-readiness",
        "certificate",
        "private key",
        "systemctl daemon-reload",
        "systemctl enable",
        "systemctl start",
        "capacity-observe",
        "RuntimeStore",
        "sqlite3",
    ):
        assert forbidden not in source


def test_apply_order_freezes_antidup_source_and_binary_before_identity_mutation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    body = source.split("def apply_enrollment(", 1)[1]
    antidup = body.index("assert_central_control_absent")
    custody = body.index("verify_root_source_custody")
    source_identity = body.index("verify_source_identity")
    inspect_binary = body.index("inspect_codex_source")
    identities = body.index("ensure_service_identities")
    release = body.index("install_release")
    binary = body.index("install_codex_binary")
    units = body.index("install_inert_units")
    final_antidup = body.rindex("assert_central_control_absent")
    assert antidup < custody < source_identity < inspect_binary < identities < release < binary < units < final_antidup


def test_module_has_no_network_or_remote_execution_surface() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "ssh",
        "rsync",
        "requests",
        "urllib",
        "import socket",
        "socket.socket",
        "curl",
        "wget",
    ):
        assert forbidden not in source
