from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

import pytest
from test_executive_fabric_composition import root_stats

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
    (repo / "ops" / "executive_os" / "bootstrap-host.sh").write_text(
        "CONTROL_USER=\"_mastermind_exec\"\n"
        "CONTROL_GROUP=\"_mastermind_exec\"\n"
        "CONTROL_UID=\"450\"\n"
        "CONTROL_GID=\"450\"\n"
        "WORKER_USER=\"_mastermind_worker\"\n"
        "WORKER_GROUP=\"_mastermind_worker\"\n"
        "WORKER_UID=\"451\"\n"
        "WORKER_GID=\"451\"\n",
        encoding="utf-8",
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


def _identities(m):
    return m.ServiceIdentities(
        control_user="_mastermind_exec", control_group="_mastermind_exec",
        control_uid=450, control_gid=450,
        worker_user="_mastermind_worker", worker_group="_mastermind_worker",
        worker_uid=451, worker_gid=451,
    )


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
    assert m.RELEASE_PATHS[:4] == (
        "control_plane",
        "ops/executive_os",
        "scripts/executive_os_linux_worker.py",
        "scripts/executive_os_remote_worker_gateway.py",
    )
    assert all("vendor" not in item for item in m.RELEASE_PATHS)
    assert "integrations" not in m.RELEASE_PATHS
    assert "integrations/business_mcp_auth" not in m.RELEASE_PATHS
    assert "integrations/mastermind_secretary_mcp" not in m.RELEASE_PATHS


def test_real_git_archive_preserves_runtime_byok_modules_and_role_data(tmp_path: Path) -> None:
    """Exercise the install owner's pathspecs and isolated first-party imports.

    The fixture is a source archive, not an installed interpreter or unit proof.
    No enrollment, credential, provider, supervision or live host is invoked.
    """
    import yaml

    m = _load()
    repo, _, _ = _source_repo(tmp_path)
    # Use actual tracked source bytes, with no checkout-wide sys.path fallback.
    source = m._git(ROOT, "archive", "HEAD", "--", *m.RELEASE_PATHS).stdout
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
        m._safe_archive_members(archive)
        archive.extractall(repo, filter="data")
    decoys = (
        "vendor/hermes/secret.txt", "integrations/unrelated/secret.txt",
        "integrations/business_mcp_auth/server.py", "integrations/business_mcp_auth/jwks.py",
        "integrations/mastermind_secretary_mcp/adapter.py",
        "unrelated/private.txt", "scripts/ohf/private-probe.py",
    )
    for relative in decoys:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"excluded fixture\n")
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "runtime source closure with excluded decoys", cwd=repo)
    sha = _git("rev-parse", "HEAD", cwd=repo)
    (repo / "common/untracked-private.txt").write_bytes(b"untracked fixture\n")
    required = (
        "common/__init__.py", "integrations/__init__.py",
        "scripts/ohf/__init__.py", "scripts/ohf/redaction.py",
        "scripts/ohf/capability_skill_projection.py", "scripts/ohf/laboratory.py",
        "scripts/ohf/protocol.py", "scripts/ohf/fixtures/__init__.py",
        "ops/native_fabric/quota_continuity/candidate/paid_yaml_runtime.py",
        "ops/native_fabric/quota_continuity/candidate/paid_pyyaml_6_0_3.zip",
        "ops/native_fabric/quota_continuity/candidate/paid_pyyaml_provenance.json",
        "integrations/hermes_runtime/supervisor.py", "integrations/hermes_harness/native_byok.py",
        "integrations/hermes_runtime/profile.py", "integrations/hermes_models/profile_config.py",
        "integrations/hermes_steward/client.py", "integrations/hermes_steward/hermes.mcp.yaml",
        "integrations/business_mcp_auth/__init__.py", "integrations/business_mcp_auth/claims.py",
        "integrations/business_mcp_auth/contracts.py", "integrations/mastermind_secretary_mcp/__init__.py",
        "integrations/mastermind_secretary_mcp/schemas.py",
        *(f"integrations/hermes_delegate/{name}.py" for name in
          ("__init__", "admission", "bridge", "carriers", "executive", "handoff",
           "policy", "schema", "tool")),
        "integrations/hermes_harness/native_executive_consumer.py",
        "integrations/hermes_harness/native_tool_registration.py",
        "integrations/hermes_runtime/native_gateway_entry.py",
        *(f"integrations/hermes_runtime/profiles/{role}.yaml" for role in ("mmmeta", "mmsecretary")),
        *(f"integrations/hermes_qualification/profiles/{role}/{name}"
          for role in ("mmmeta", "mmsecretary") for name in ("config.yaml", "SOUL.md")),
        *(f"integrations/hermes_models/profiles/{role}.hermes-providers.yaml"
          for role in ("mmmeta", "mmsecretary")),
    )
    raw = m._git(repo, "archive", sha, "--", *m.RELEASE_PATHS).stdout
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        m._safe_archive_members(archive)
        names = set(archive.getnames())
        assert set(required) <= names
        assert not (set(decoys) | {"common/untracked-private.txt"}) & names
        for relative in required:
            assert archive.extractfile(relative).read() == (repo / relative).read_bytes()
        archive.extractall(extracted, filter="data")
    modules = [
        "integrations.hermes_runtime.supervisor", "integrations.hermes_harness.native_byok",
        "integrations.hermes_runtime.install", "integrations.hermes_runtime.system_service",
        "integrations.hermes_runtime.profile", "integrations.hermes_harness.native_mcp",
        "integrations.hermes_models.profile_config", "integrations.hermes_steward.client",
        "integrations.hermes_harness.native_executive_consumer",
        "integrations.hermes_harness.native_tool_registration",
        "integrations.hermes_runtime.native_gateway_entry",
        # The selected-child reply decoder imports this canonical envelope owner.
        "integrations.hermes_delegate.executive",
    ]
    probe = (
        "import importlib,json,pathlib,sys\n"
        "root=pathlib.Path(sys.argv[1]).resolve()\n"
        "sys.path.insert(0,str(root))\n"
        "sys.path.append(sys.argv[2])\n"
        "for name in json.loads(sys.argv[3]): importlib.import_module(name)\n"
        "for name,module in tuple(sys.modules.items()):\n"
        " if name.split('.')[0] in {'common','control_plane','ops','integrations'}:\n"
        "  origin=getattr(module,'__file__',None)\n"
        "  if origin: assert pathlib.Path(origin).resolve().is_relative_to(root),(name,origin)\n"
        "print('ISOLATED_RUNTIME_BYOK_IMPORTS_OK')\n"
    )
    # -I -S disables repository editable-install hooks and ambient PYTHONPATH;
    # only this fixture plus the explicitly selected PyYAML dependency is added.
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe, str(extracted),
         str(Path(yaml.__file__).resolve().parent.parent), json.dumps(modules)],
        cwd=tmp_path, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.strip() == "ISOLATED_RUNTIME_BYOK_IMPORTS_OK"

    # Reach the actual installed entrypoints with no checkout/site fallback.
    # The gateway deliberately has no --help option; its closed parser refusal
    # proves import closure, while an arbitrary failure must never count as proof.
    from ops.executive_os.remote_worker_gateway_service import SERVICE_CHECK_SCHEMA
    for entrypoint, expected_rc in (
        ("executive_os_linux_worker.py", 0),
        ("executive_os_remote_worker_gateway.py", 64),
    ):
        invocation = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(extracted / "scripts" / entrypoint), "--help"],
            cwd=tmp_path, capture_output=True, text=True, timeout=20,
        )
        assert invocation.returncode == expected_rc, invocation.stderr[-3000:]
        if expected_rc == 0:
            assert "usage:" in invocation.stdout and not invocation.stderr
        else:
            assert not invocation.stdout
            assert json.loads(invocation.stderr) == {
                "schema": SERVICE_CHECK_SCHEMA, "ok": False, "code": "ARGUMENTS_INVALID",
            }


    # A checkout or the explicit third-party dependency path cannot supply a
    # missing first-party consumer member in a fresh isolated interpreter.
    for leaf in ("policy", "executive"):
        member = extracted / "integrations/hermes_delegate" / f"{leaf}.py"
        retained = member.read_bytes()
        member.unlink()
        try:
            refused = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-c", probe, str(extracted),
                 str(Path(yaml.__file__).resolve().parent.parent), json.dumps(modules)],
                cwd=tmp_path, capture_output=True, text=True, timeout=20,
            )
            assert refused.returncode != 0
            assert "ISOLATED_RUNTIME_BYOK_IMPORTS_OK" not in refused.stdout
            assert "ModuleNotFoundError" in refused.stderr
            assert f"integrations.hermes_delegate.{leaf}" in refused.stderr
        finally:
            member.write_bytes(retained)


def test_linux_identities_are_consumed_from_canonical_bootstrap_source(tmp_path: Path) -> None:
    m = _load()
    repo, _sha, _tree = _source_repo(tmp_path)
    identities = m.load_canonical_identities(repo, require_root_owner=False)
    assert identities == _identities(m)
    source = SCRIPT.read_text(encoding="utf-8")
    assert '_mastermind_exec' not in source
    assert '_mastermind_worker' not in source
    assert 'CONTROL_UID = 450' not in source
    assert 'WORKER_UID = 451' not in source




def test_identity_plan_refuses_collisions() -> None:
    m = _load()
    clean = {
        "users_by_name": {},
        "users_by_uid": {},
        "groups_by_name": {},
        "groups_by_gid": {},
    }
    identities = _identities(m)
    plan = m.classify_identity_plan(clean, identities)
    assert plan["control"] == "create"
    assert plan["worker"] == "create"

    collision = json.loads(json.dumps(clean))
    collision["users_by_uid"]["450"] = "somebody"
    with pytest.raises(m.EnrollmentError, match="UID 450"):
        m.classify_identity_plan(collision, identities)

    exact = {
        "users_by_name": {
            "_mastermind_exec": {"uid": 450, "gid": 450, "home": "/var/lib/mastermind-executive/control/home", "shell": "/usr/sbin/nologin"},
            "_mastermind_worker": {"uid": 451, "gid": 451, "home": "/var/lib/mastermind-executive/workers/codex-01/provider-home", "shell": "/usr/sbin/nologin"},
        },
        "users_by_uid": {"450": "_mastermind_exec", "451": "_mastermind_worker"},
        "groups_by_name": {"_mastermind_exec": 450, "_mastermind_worker": 451},
        "groups_by_gid": {"450": "_mastermind_exec", "451": "_mastermind_worker"},
    }
    assert m.classify_identity_plan(exact, identities) == {"control": "verify", "worker": "verify"}


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
        identities=_identities(m),
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
        "openssl req",
        "openssl x509",
        "systemctl daemon-reload",
        "systemctl enable",
        "systemctl start",
        "capacity-observe",
        "RuntimeStore",
        "sqlite3",
    ):
        assert forbidden not in source


def test_observation_cli_does_not_require_or_allow_worker_inputs(monkeypatch, capsys):
    m = _load()
    flags = ['--source-repo', '/root/source', '--expected-sha', 'c' * 40,
             '--expected-tree', 'd' * 40, '--component', 'hermes-host-observation',
             '--gateway-config-file', '/etc/mastermind-executive/remote-worker-gateway/input.json',
             '--gateway-config-sha256', 'e' * 64]
    args = m._parser().parse_args(flags)
    assert args.codex_source_binary is None and args.codex_version is None
    monkeypatch.setattr(m, 'apply_enrollment', lambda *_: pytest.fail('invalid inputs reached enrollment'))
    assert m.main(flags + ['--codex-version', '0.157.1']) == 64
    assert m.main(flags[:-2]) == 64


def test_observation_identity_plan_ignores_worker_collision():
    m = _load(); identities = _identities(m)
    state = dict(users_by_name={}, users_by_uid={'451': 'unrelated'},
                 groups_by_name={}, groups_by_gid={'451': 'unrelated'})
    assert m.classify_identity_plan(state, identities, gateway_only=True) == {'control': 'create'}
    with pytest.raises(m.EnrollmentError, match='already assigned'):
        m.classify_identity_plan(state, identities)


def test_observation_directories_and_unit_have_no_worker_surface(monkeypatch):
    m = _load(); identities = _identities(m)
    directories = []
    monkeypatch.setattr(m, '_mkdir', lambda path, uid, gid, mode: directories.append((path, uid, gid, mode)))
    m.ensure_directories(identities, gateway_only=True)
    assert (m.CONFIG_ROOT, 0, 0, 0o755) in directories
    assert (m.CONFIG_ROOT / 'remote-worker-gateway', 0, identities.control_gid, 0o750) in directories
    assert all(uid != identities.worker_uid and 'workers' not in path.parts for path, uid, _, _ in directories)
    assert all(path not in (m.RUN_ROOT, m.WORKSPACE_ROOT, m.BIN_ROOT) for path, *_ in directories)
    units = m.render_systemd_units(release_root=ROOT, codex_binary=None, identities=identities, gateway_only=True)
    assert set(units) == {'mastermind-executive-remote-worker-gateway.service'}
    unit = next(iter(units.values()))
    assert '/remote-worker-gateway/host-observation.json' in unit
    assert f'{ROOT}/scripts/executive_os_remote_worker_gateway.py' in unit
    active = [line.strip() for line in unit.splitlines() if not line.lstrip().startswith('#')]
    assert '[Install]' not in active and '__' not in unit


def test_observation_config_is_digest_bound_exact_adoption_and_never_replaced(tmp_path, root_stats, monkeypatch):
    import dataclasses
    import hashlib
    from tests.test_remote_worker_gateway_service import _observation_fixture, _write
    m = _load()
    root, destination, document = _observation_fixture(tmp_path, monkeypatch)
    raw = destination.read_bytes(); destination.unlink()
    staged = root / 'operator-input.json'; staged.write_bytes(raw); staged.chmod(0o440)
    identities = dataclasses.replace(_identities(m), control_gid=root.stat().st_gid)
    args = m.Args(source_repo=ROOT, expected_sha='c' * 40, expected_tree='d' * 40,
                  component='hermes-host-observation', gateway_config_file=staged,
                  gateway_config_sha256=hashlib.sha256(raw).hexdigest())
    qualified, config = m._observation_input(args, identities)
    assert qualified == raw and config.hermes_role_metadata_read.implementation_sha == args.expected_sha
    monkeypatch.setattr(m.os, 'fchown', lambda fd, uid, gid: None)  # fixture metadata only
    digest = m._install_observation_config(raw, identities)
    original_inode = destination.stat().st_ino
    assert m._install_observation_config(raw, identities) == digest
    assert destination.stat().st_ino == original_inode
    assert stat.S_IMODE(destination.stat().st_mode) == 0o440
    assert destination.read_bytes() == raw
    with pytest.raises(m.EnrollmentError, match='input_changed'):
        m._observation_input(dataclasses.replace(args, gateway_config_sha256='0' * 64), identities)
    with pytest.raises(m.EnrollmentError, match='release_pin'):
        m._observation_input(dataclasses.replace(args, expected_sha='e' * 40), identities)
    replacement_args = dataclasses.replace(
        args, expected_sha='e' * 40, expected_gateway_unit_sha256='f' * 64)
    preserved, preserved_config = m._observation_input(replacement_args, identities)
    assert preserved == raw
    assert preserved_config.hermes_role_metadata_read.implementation_sha == args.expected_sha
    assert destination.stat().st_ino == original_inode
    destination.unlink()
    with pytest.raises(m.EnrollmentError, match='predecessor_config_required'):
        m._observation_input(replacement_args, identities)
    _write(destination, '{}', 0o440)
    with pytest.raises(m.EnrollmentError, match='conflict'):
        m._install_observation_config(raw, identities)
    assert destination.read_bytes() == b'{}'


def test_observation_enrollment_reuses_release_owner_and_is_inert(monkeypatch):
    m = _load(); identities = _identities(m); events = []
    monkeypatch.setattr(m, '_require_hermes_source_checkout', lambda _: None)
    monkeypatch.setattr(m.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(m, 'assert_central_control_absent', lambda: None)
    monkeypatch.setattr(m, 'verify_root_source_custody', lambda _: None)
    monkeypatch.setattr(m, 'verify_source_identity', lambda *_: {'commit': 'c' * 40, 'tree': 'd' * 40})
    monkeypatch.setattr(m, 'load_canonical_identities', lambda _: identities)
    monkeypatch.setattr(m, '_observation_input', lambda *_: (b'qualified input', object()))
    monkeypatch.setattr(m, '_observation_config_adoption', lambda *_: False)
    monkeypatch.setattr(m, 'expected_hermes_role_units', lambda *_: {})
    monkeypatch.setattr(m, '_assert_release_input_adoption', lambda *_: None)
    monkeypatch.setattr(m, 'read_identity_state', lambda: {})
    monkeypatch.setattr(m, 'classify_identity_plan', lambda *a, **kw: {'control': 'create'})
    def gateway_step(*a, **kw):
        assert kw == {'gateway_only': True}; events.append('gateway-only')
    monkeypatch.setattr(m, 'ensure_service_identities', gateway_step)
    monkeypatch.setattr(m, 'ensure_directories', gateway_step)
    monkeypatch.setattr(m, 'install_release', lambda *a, **kw: ROOT)
    monkeypatch.setattr(m, '_install_observation_config', lambda *_: 'e' * 64)
    def units(release, codex, received, *, gateway_only):
        assert release == ROOT and codex is None and received is identities and gateway_only is True
        return ('mastermind-executive-remote-worker-gateway.service',)
    monkeypatch.setattr(m, 'install_inert_units', units)
    def forbidden(*a, **kw): pytest.fail('observation attempted Worker or lifecycle effect')
    for name in ('inspect_codex_source', 'install_codex_binary', '_run'):
        monkeypatch.setattr(m, name, forbidden)
    receipt = m.apply_enrollment(m.Args(source_repo=ROOT, expected_sha='c' * 40,
                                       expected_tree='d' * 40, hermes_runtime={},
                                       component='hermes-host-observation'))
    assert receipt['outcome'] == 'HOST_OBSERVATION_INSTALLED_INERT'
    assert receipt['services_activated'] is False and events == ['gateway-only', 'gateway-only']


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
        "/usr/bin/ssh",
        "subprocess.run([\"ssh\"",
        "/usr/bin/rsync",
        "requests.",
        "urllib.",
        "import socket",
        "socket.socket",
        "curl",
        "wget",
    ):
        assert forbidden not in source


def test_root_git_reads_disable_local_execution_vectors() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"GIT_OPTIONAL_LOCKS": "0"' in source
    assert '"-c", "core.fsmonitor=false"' in source
    assert '"-c", "core.hooksPath=/dev/null"' in source
    assert "verify_git_config_safe" in source
    assert '"filter."' in source
    assert '"include."' in source


def test_release_manifest_logic_is_executed_from_accepted_source_not_installed_copy() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    install = source.split("def install_release(", 1)[1].split("def render_systemd_units", 1)[0]
    assert 'manifest_tool = repo / "ops/executive_os/release_manifest.py"' in install
    assert 'os.fspath(manifest_tool)' in install
    assert 'destination / "ops/executive_os/release_manifest.py"' not in install
    assert 'staging / "ops/executive_os/release_manifest.py"' not in install


def test_identity_plan_resumes_after_exact_group_only_partial_effect() -> None:
    m = _load()
    identities = m.ServiceIdentities(
        control_user="control-fixture", control_group="control-fixture",
        control_uid=1450, control_gid=1450,
        worker_user="worker-fixture", worker_group="worker-fixture",
        worker_uid=1451, worker_gid=1451,
    )
    state = {
        "users_by_name": {},
        "users_by_uid": {},
        "groups_by_name": {"control-fixture": 1450, "worker-fixture": 1451},
        "groups_by_gid": {"1450": "control-fixture", "1451": "worker-fixture"},
    }
    assert m.classify_identity_plan(state, identities) == {
        "control": "create_user",
        "worker": "create_user",
    }


def test_source_custody_rejects_writable_git_admin_and_tracked_parent(tmp_path: Path) -> None:
    m = _load()
    repo, _sha, _tree = _source_repo(tmp_path)
    owner = os.getuid()
    _git("config", "--unset", "user.email", cwd=repo)
    _git("config", "--unset", "user.name", cwd=repo)
    for key in ("core.ignorecase", "core.precomposeunicode"):
        subprocess.run(
            ["git", "config", "--unset-all", key], cwd=repo,
            capture_output=True, text=True, check=False,
        )

    # The ordinary fixture is safe under its current owner when the production
    # root-only expectation is parameterized for this hermetic discriminator.
    m.verify_root_source_custody(repo, expected_owner_uid=owner)

    git_dir = repo / ".git"
    original_git_mode = stat.S_IMODE(git_dir.lstat().st_mode)
    git_dir.chmod(original_git_mode | 0o020)
    with pytest.raises(m.EnrollmentError, match="git.*custody"):
        m.verify_root_source_custody(repo, expected_owner_uid=owner)
    git_dir.chmod(original_git_mode)

    scripts = repo / "scripts"
    original_scripts_mode = stat.S_IMODE(scripts.lstat().st_mode)
    scripts.chmod(original_scripts_mode | 0o020)
    with pytest.raises(m.EnrollmentError, match="source_directory_custody"):
        m.verify_root_source_custody(repo, expected_owner_uid=owner)
    scripts.chmod(original_scripts_mode)

def test_source_custody_rejects_writable_checkout_ancestor(tmp_path: Path, monkeypatch) -> None:
    m = _load()
    repo, _sha, _tree = _source_repo(tmp_path)
    owner = os.getuid()
    # The parent owner can substitute even a root-owned read-only child path.
    # This must refuse before the first root Git operation.
    original_mode = stat.S_IMODE(tmp_path.lstat().st_mode)
    tmp_path.chmod(original_mode | stat.S_IWOTH)
    monkeypatch.setattr(m, "_git", lambda *_a, **_k: pytest.fail("git before parent custody check"))
    try:
        with pytest.raises(m.EnrollmentError, match="source_ancestor_custody_invalid"):
            m.verify_root_source_custody(repo, expected_owner_uid=owner)
    finally:
        tmp_path.chmod(original_mode)


def test_source_custody_rejects_symlink_or_traversal_ancestor(tmp_path: Path, monkeypatch) -> None:
    m = _load()
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    repo, _sha, _tree = _source_repo(real_parent)
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    monkeypatch.setattr(m, "_git", lambda *_a, **_k: pytest.fail("git before parent custody check"))
    with pytest.raises(m.EnrollmentError, match="source_ancestor_custody_invalid"):
        m.verify_root_source_custody(alias / "repo", expected_owner_uid=os.getuid())
    with pytest.raises(m.EnrollmentError, match="source_ancestor_custody_invalid"):
        m.verify_root_source_custody(repo.parent / ".." / "real" / "repo", expected_owner_uid=os.getuid())

