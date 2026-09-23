#!/usr/bin/env python3
"""Isolated tests for private_tunnel_service.py.

All mutations stay inside temp HOME fixtures. launchd, official profiles,
and real credentials are never touched. Subprocess and health GET are mocked.
"""
from __future__ import annotations

import io
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import private_service as gw  # noqa: E402
import private_tunnel_service as svc  # noqa: E402

C1 = "chatgpt1"
C1_TUNNEL = "tunnel_6aa740b21fd48191bb273e2a63572984"
OTHER = "acct-b"
OTHER_TUNNEL = "tunnel_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CmdRecorder:
    def __init__(self, handler=None, default=None):
        self.handler = handler
        self.default = default if default is not None else FakeResult(1, "", "not loaded")
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *, check: bool = True, timeout: float = 30.0):
        self.calls.append(list(cmd))
        if self.handler is not None:
            result = self.handler(list(cmd))
            if result is not None:
                if isinstance(result, BaseException):
                    if check:
                        raise result
                    return FakeResult(1, "", str(result))
                return result
        if isinstance(self.default, BaseException):
            if check:
                raise self.default
            return FakeResult(1, "", str(self.default))
        return self.default


def _print_running(plist: str, label: str) -> str:
    return (
        f"gui/501/{label} = {{\n"
        "\tactive count = 1\n"
        f"\tpath = {plist}\n"
        "\tstate = running\n"
        "\tpid = 4321\n"
        "}\n"
    )


def _alias_running_json(account: str = C1) -> str:
    return json.dumps(
        {
            "alias": f"studio-direct-private-{account}",
            "process_running": True,
            "running": True,
            "tmux": {
                "running": True,
                "session_name": f"tunnel-mcp__studio-direct-private-{account}__deadbeef",
            },
        }
    )


def _alias_stopped_json(account: str = C1) -> str:
    return json.dumps(
        {
            "alias": f"studio-direct-private-{account}",
            "process_running": False,
            "running": False,
            "tmux": {"running": False},
        }
    )


@contextmanager
def IsolatedHome():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        home = tmp / "home"
        home.mkdir()
        (home / "Library" / "LaunchAgents").mkdir(parents=True)
        pinned = tmp / "pinned-tunnel-client"
        pinned.write_text("#!/bin/sh\n", encoding="utf-8")
        pinned.chmod(0o755)
        with mock.patch.dict(os.environ, {"HOME": str(home)}), mock.patch.object(
            svc, "PINNED_TUNNEL_CLIENT", str(pinned)
        ):
            yield tmp, home


def _capture_stdout(call):
    buf = io.StringIO()
    with mock.patch("sys.stdout", buf):
        rc = call()
    return rc, buf.getvalue()


def _make_bin(tmp: Path, name: str = "tunnel-client") -> Path:
    path = tmp / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _make_key(home: Path, account: str = C1) -> str:
    path = home / ".config" / "tunnel-client" / "credentials" / f"{account}-runtime-key"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test-placeholder-not-a-live-key\n", encoding="utf-8")
    path.chmod(0o600)
    return f"file:{path}"


def _seed_gateway(account: str, port: int) -> dict:
    roots = gw._build_runtime_roots(account)
    roots["base"].mkdir(parents=True, exist_ok=True)
    files = {}
    for name in gw.STAGE_FILES:
        dest = roots["base"] / name
        dest.write_text(f"// {name}\n", encoding="utf-8")
        files[name] = gw._sha256_file(dest)
    config = {
        "accountLabel": account,
        "host": "127.0.0.1",
        "idleTimeoutMs": 18_000_000,
        "port": port,
        "testMode": False,
    }
    roots["config"].write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    roots["plist"].parent.mkdir(parents=True, exist_ok=True)
    roots["plist"].write_bytes(b"gateway-plist")
    (roots["base"] / "state").mkdir(exist_ok=True)
    (roots["base"] / "logs").mkdir(exist_ok=True)
    manifest = {
        "account": account,
        "backend": "/backend",
        "configHash": gw._sha256_file(roots["config"]),
        "files": files,
        "host": "127.0.0.1",
        "label": f"com.mastermind.studio-direct-private.{account}",
        "node": "/node",
        "plistHash": gw._sha256_file(roots["plist"]),
        "port": port,
        "source": "/src",
        "version": 1,
    }
    roots["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return roots


def _stage_args(
    home,
    tmp,
    account=C1,
    tunnel_id=C1_TUNNEL,
    port=45018,
    key_ref=None,
    profile=None,
    binary=None,
    organization_id=None,
    rotate_runtime_key=False,
):
    _seed_gateway(account, port)
    key_ref = key_ref or _make_key(home, account)
    binary = binary or Path(svc.PINNED_TUNNEL_CLIENT)
    profile = profile or str(svc._canonical_profile(account))
    return mock.Mock(
        account=account,
        tunnel_id=tunnel_id,
        profile=profile,
        runtime_key_ref=key_ref,
        organization_id=organization_id,
        rotate_runtime_key=rotate_runtime_key,
        tunnel_client=str(binary),
    ), binary, key_ref


def _stopped_alias_handler(account=C1):
    def handler(cmd):
        if cmd[:2] == ["launchctl", "print"]:
            return FakeResult(1, "", "not loaded")
        if len(cmd) >= 4 and cmd[1:4] == ["runtimes", "status", f"studio-direct-private-{account}"]:
            return FakeResult(0, _alias_stopped_json(account), "")
        if cmd[:2] == ["launchctl", "bootstrap"]:
            return FakeResult(0, "", "")
        if cmd[:2] == ["launchctl", "bootout"]:
            return FakeResult(0, "", "")
        if cmd[:2] == ["launchctl", "kickstart"]:
            return FakeResult(0, "", "")
        return FakeResult(1, "", "unused")

    return handler


def _do_stage(home, tmp, account=C1, tunnel_id=C1_TUNNEL, port=45018, recorder=None):
    args, binary, key_ref = _stage_args(home, tmp, account, tunnel_id, port)
    rec = recorder or CmdRecorder(handler=_stopped_alias_handler(account))
    with mock.patch.object(svc, "_run", rec):
        rc, out = _capture_stdout(lambda: svc.cmd_stage(args))
    return rc, out, args, binary, key_ref, rec


class TestIdentity(unittest.TestCase):
    def test_alias_lookup_failure_does_not_authorize_second_supervisor(self):
        with mock.patch.object(svc, "_run", return_value=FakeResult(1, "", "permission denied")):
            with self.assertRaisesRegex(SystemExit, "could not be established"):
                svc._managed_alias_running(Path("/tc"), C1)

    def test_explicit_missing_alias_is_safe_for_launchd_start(self):
        message = f"alias studio-direct-private-{C1} is not known; run create or connect first"
        with mock.patch.object(svc, "_run", return_value=FakeResult(1, "", message)):
            self.assertFalse(svc._managed_alias_running(Path("/tc"), C1))

    def test_labels_and_pinned_binary(self):
        self.assertEqual(svc._tunnel_label(C1), "com.mastermind.studio-direct-tunnel.chatgpt1")
        self.assertEqual(svc._gateway_label(C1), "com.mastermind.studio-direct-private.chatgpt1")
        self.assertEqual(svc._managed_alias(C1), "studio-direct-private-chatgpt1")
        self.assertEqual(
            svc.PINNED_TUNNEL_CLIENT,
            "/opt/homebrew/Cellar/tunnel-client/0.0.14/libexec/tunnel-client",
        )
        self.assertEqual(svc.TRANSPORT_TTL, "5h")
        self.assertEqual(svc.MAX_CONCURRENT_REQUESTS, 4)
        self.assertEqual(svc.ACCOUNT_PORTS[C1], 45018)

    def test_argv_uses_separate_flag_tokens(self):
        argv = svc._expected_argv(Path("/tc"), Path("/p.yaml"), 45019)
        self.assertEqual(argv[0], "/tc")
        self.assertEqual(argv[1], "run")
        self.assertIn("--profile-file", argv)
        self.assertEqual(argv[argv.index("--mcp.connection-max-ttl") + 1], "5h")
        self.assertEqual(argv[argv.index("--mcp.max-concurrent-requests") + 1], "4")
        self.assertEqual(argv[argv.index("--mcp.startup-wait-timeout") + 1], "30s")
        self.assertNotIn("--mcp.connection-max-ttl5h", argv)
        self.assertNotIn("--log.http-raw-unsafe", argv)
        self.assertEqual(argv[argv.index("--health.listen-addr") + 1], "127.0.0.1:45019")


class TestStrictTunnelHealth(unittest.TestCase):
    def test_requires_successful_control_plane_poll(self):
        payload = {
            "healthz": {"ok": True},
            "readyz": {"ok": True},
            "control_plane_poll": {"ok": False},
            "result": "fail",
        }
        with mock.patch.object(
            svc, "_run", return_value=FakeResult(0, json.dumps(payload), "")
        ):
            self.assertEqual(
                svc._strict_tunnel_health(Path("/tc"), 45031),
                (True, False, False),
            )

    def test_nonzero_health_exit_cannot_false_green(self):
        payload = {
            "healthz": {"ok": True},
            "readyz": {"ok": True},
            "control_plane_poll": {"ok": True},
            "result": "ok",
        }
        with mock.patch.object(
            svc, "_run", return_value=FakeResult(1, json.dumps(payload), "")
        ):
            self.assertEqual(
                svc._strict_tunnel_health(Path("/tc"), 45031),
                (False, False, False),
            )

    def test_ready_only_when_local_and_poll_are_ready(self):
        payload = {
            "healthz": {"ok": True},
            "readyz": {"ok": True},
            "control_plane_poll": {"ok": True},
            "result": "ok",
        }
        with mock.patch.object(
            svc, "_run", return_value=FakeResult(0, json.dumps(payload), "")
        ):
            self.assertEqual(
                svc._strict_tunnel_health(Path("/tc"), 45031),
                (True, True, True),
            )


class TestPinnedTunnelClient(unittest.TestCase):
    def test_non_pinned_tunnel_client_refused(self):
        with self.assertRaisesRegex(SystemExit, "pinned path"):
            svc._resolve_tunnel_client("/tmp/not-the-pinned-client")

    def test_pinned_tunnel_client_resolves_exact_path(self):
        expected = Path(svc.PINNED_TUNNEL_CLIENT)
        with mock.patch.object(gw, "_resolve_abs", return_value=expected) as resolve:
            self.assertEqual(
                svc._resolve_tunnel_client(svc.PINNED_TUNNEL_CLIENT),
                expected,
            )
        resolve.assert_called_once_with("--tunnel-client", svc.PINNED_TUNNEL_CLIENT)


class TestStageHappyPath(unittest.TestCase):
    def test_stage_writes_owned_profile_plist_and_hashes(self):
        with IsolatedHome() as (tmp, home):
            rc, out, args, binary, key_ref, rec = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            roots = svc._build_tunnel_roots(C1)
            self.assertTrue(payload["staged"])
            self.assertEqual(payload["transportTTL"], "5h")
            self.assertEqual(payload["gatewayPort"], 45018)
            self.assertEqual(payload["healthPort"], 45019)
            self.assertTrue(roots["profile"].is_file())
            self.assertEqual(stat.S_IMODE(roots["profile"].stat().st_mode), 0o600)
            profile = json.loads(roots["profile"].read_text(encoding="utf-8"))
            self.assertEqual(profile["control_plane"]["tunnel_id"], C1_TUNNEL)
            self.assertEqual(profile["control_plane"]["api_key"], key_ref)
            self.assertTrue(profile["control_plane"]["api_key"].startswith("file:"))
            self.assertEqual(profile["mcp"]["server_urls"][0]["url"], "http://127.0.0.1:45018/mcp")
            self.assertFalse(profile["admin_ui"]["open_browser"])
            plist = plistlib.loads(roots["plist"].read_bytes())
            self.assertEqual(plist["Label"], "com.mastermind.studio-direct-tunnel.chatgpt1")
            self.assertTrue(plist["RunAtLoad"])
            self.assertEqual(plist["ProgramArguments"], svc._expected_argv(binary, roots["profile"], 45019))
            self.assertNotIn("CONTROL_PLANE_API_KEY", plist.get("EnvironmentVariables", {}))
            manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["profileHash"], svc._sha256_file(roots["profile"]))
            self.assertEqual(manifest["plistHash"], svc._sha256_file(roots["plist"]))
            self.assertEqual(manifest["runtimeKeyRef"], key_ref)
            alias_calls = [c for c in rec.calls if c[1:3] == ["runtimes", "status"]]
            self.assertEqual(alias_calls[0][3], "studio-direct-private-chatgpt1")

    def test_restage_is_idempotent_when_exact(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            before = (
                roots["profile"].read_bytes(),
                roots["plist"].read_bytes(),
                roots["manifest"].read_bytes(),
            )
            rec = CmdRecorder(handler=_stopped_alias_handler(C1))
            with mock.patch.object(svc, "_run", rec):
                rc2, _ = _capture_stdout(lambda: svc.cmd_stage(args))
            self.assertEqual(rc2, 0)
            self.assertEqual(roots["profile"].read_bytes(), before[0])
            self.assertEqual(roots["plist"].read_bytes(), before[1])
            self.assertEqual(roots["manifest"].read_bytes(), before[2])

    def test_runtime_key_rotation_requires_explicit_flag_and_preserves_prior(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, old_key_ref, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            before = (
                roots["profile"].read_bytes(),
                roots["plist"].read_bytes(),
                roots["manifest"].read_bytes(),
            )
            new_key_ref = _make_key(home, "rotated")
            args.runtime_key_ref = new_key_ref
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler(C1))
            ):
                with self.assertRaisesRegex(SystemExit, "--rotate-runtime-key"):
                    svc.cmd_stage(args)
            self.assertEqual(roots["profile"].read_bytes(), before[0])
            self.assertEqual(roots["plist"].read_bytes(), before[1])
            self.assertEqual(roots["manifest"].read_bytes(), before[2])
            self.assertNotEqual(old_key_ref, new_key_ref)

    def test_runtime_key_rotation_succeeds_only_when_explicit_and_stopped(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, old_key_ref, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            new_key_ref = _make_key(home, "rotated")
            args.runtime_key_ref = new_key_ref
            args.rotate_runtime_key = True
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler(C1))
            ):
                rc2, out = _capture_stdout(lambda: svc.cmd_stage(args))
            self.assertEqual(rc2, 0)
            self.assertTrue(json.loads(out)["runtimeKeyRotated"])
            profile = json.loads(roots["profile"].read_text(encoding="utf-8"))
            manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(profile["control_plane"]["api_key"], new_key_ref)
            self.assertEqual(manifest["runtimeKeyRef"], new_key_ref)
            self.assertNotEqual(manifest["runtimeKeyRef"], old_key_ref)

    def test_runtime_key_rotation_can_pair_with_one_way_org_enrichment(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            new_key_ref = _make_key(home, "rotated")
            args.runtime_key_ref = new_key_ref
            args.organization_id = "org-ChrisAdmin123"
            args.rotate_runtime_key = True
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler(C1))
            ):
                rc2, _ = _capture_stdout(lambda: svc.cmd_stage(args))
            self.assertEqual(rc2, 0)
            profile = json.loads(roots["profile"].read_text(encoding="utf-8"))
            manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(profile["control_plane"]["api_key"], new_key_ref)
            self.assertEqual(
                profile["control_plane"]["organization_id"], "org-ChrisAdmin123"
            )
            self.assertEqual(manifest["runtimeKeyRef"], new_key_ref)
            self.assertEqual(manifest["organizationId"], "org-ChrisAdmin123")

    def test_runtime_key_rotation_refuses_tampered_owned_profile(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            original_manifest = roots["manifest"].read_bytes()
            roots["profile"].write_text('{"tampered":true}\n', encoding="utf-8")
            args.runtime_key_ref = _make_key(home, "rotated")
            args.rotate_runtime_key = True
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler(C1))
            ):
                with self.assertRaisesRegex(SystemExit, "profile hash diverges"):
                    svc.cmd_stage(args)
            self.assertEqual(roots["manifest"].read_bytes(), original_manifest)

    def test_runtime_key_rotation_refuses_while_launchd_service_is_loaded(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            args.runtime_key_ref = _make_key(home, "rotated")
            args.rotate_runtime_key = True
            label = svc._tunnel_label(C1)

            def handler(cmd):
                if cmd[:2] == ["launchctl", "print"]:
                    return FakeResult(
                        0, _print_running(str(roots["plist"]), label), ""
                    )
                if len(cmd) >= 4 and cmd[1:4] == [
                    "runtimes", "status", "studio-direct-private-chatgpt1"
                ]:
                    return FakeResult(0, _alias_stopped_json(C1), "")
                return FakeResult(1, "", "unused")

            before = roots["manifest"].read_bytes()
            with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)):
                with self.assertRaisesRegex(
                    SystemExit, "while tunnel service is running"
                ):
                    svc.cmd_stage(args)
            self.assertEqual(roots["manifest"].read_bytes(), before)

    def test_restage_can_add_missing_organization_once_but_not_rebind(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            args.organization_id = "org-ChrisAdmin123"
            rec = CmdRecorder(handler=_stopped_alias_handler(C1))
            with mock.patch.object(svc, "_run", rec):
                rc2, _ = _capture_stdout(lambda: svc.cmd_stage(args))
            self.assertEqual(rc2, 0)
            profile = json.loads(roots["profile"].read_text(encoding="utf-8"))
            self.assertEqual(
                profile["control_plane"]["organization_id"], "org-ChrisAdmin123"
            )
            manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["organizationId"], "org-ChrisAdmin123")

            accepted = (
                roots["profile"].read_bytes(),
                roots["plist"].read_bytes(),
                roots["manifest"].read_bytes(),
            )
            args.organization_id = "org-Different123"
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler(C1))
            ):
                with self.assertRaisesRegex(SystemExit, "one-way addition"):
                    svc.cmd_stage(args)
            self.assertEqual(roots["profile"].read_bytes(), accepted[0])
            self.assertEqual(roots["plist"].read_bytes(), accepted[1])
            self.assertEqual(roots["manifest"].read_bytes(), accepted[2])

            args.organization_id = None
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler(C1))
            ):
                with self.assertRaisesRegex(SystemExit, "one-way addition"):
                    svc.cmd_stage(args)
            self.assertEqual(roots["profile"].read_bytes(), accepted[0])
            self.assertEqual(roots["plist"].read_bytes(), accepted[1])
            self.assertEqual(roots["manifest"].read_bytes(), accepted[2])

    def test_other_account_uses_manifest_port(self):
        with IsolatedHome() as (tmp, home):
            rc, out, _, _, _, _ = _do_stage(
                home, tmp, account=OTHER, tunnel_id=OTHER_TUNNEL, port=45020
            )
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            self.assertEqual(payload["gatewayPort"], 45020)
            self.assertEqual(payload["healthPort"], 45021)
            profile = json.loads(svc._canonical_profile(OTHER).read_text(encoding="utf-8"))
            self.assertEqual(profile["mcp"]["server_urls"][0]["url"], "http://127.0.0.1:45020/mcp")


    def test_stage_persists_optional_organization_context(self):
        with IsolatedHome() as (tmp, home):
            args, binary, key_ref = _stage_args(
                home,
                tmp,
                account=OTHER,
                tunnel_id=OTHER_TUNNEL,
                port=45020,
                organization_id="org-ChrisAdmin123",
            )
            rec = CmdRecorder(handler=_stopped_alias_handler(OTHER))
            with mock.patch.object(svc, "_run", rec):
                rc, out = _capture_stdout(lambda: svc.cmd_stage(args))
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            self.assertEqual(payload["organizationId"], "org-ChrisAdmin123")
            roots = svc._build_tunnel_roots(OTHER)
            profile = json.loads(roots["profile"].read_text(encoding="utf-8"))
            self.assertEqual(
                profile["control_plane"]["organization_id"], "org-ChrisAdmin123"
            )
            manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["organizationId"], "org-ChrisAdmin123")
            self.assertEqual(profile["control_plane"]["api_key"], key_ref)
            self.assertEqual(
                plistlib.loads(roots["plist"].read_bytes())["ProgramArguments"],
                svc._expected_argv(binary, roots["profile"], 45021),
            )


class TestWrongInputs(unittest.TestCase):
    def test_invalid_organization_id_refused(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(
                home,
                tmp,
                organization_id="workspace-not-an-org",
            )
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler())
            ):
                with self.assertRaisesRegex(SystemExit, "organization id"):
                    svc.cmd_stage(args)
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_group_writable_home_refused_before_stage(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp)
            home.chmod(0o775)
            with self.assertRaisesRegex(SystemExit, "HOME permissions"):
                svc.cmd_stage(args)
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_symlinked_home_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "real-home"
            target.mkdir()
            target.chmod(0o700)
            link = root / "linked-home"
            link.symlink_to(target, target_is_directory=True)
            key = target / "runtime-key"
            key.write_text("fixture\n", encoding="utf-8")
            key.chmod(0o600)
            with mock.patch.dict(os.environ, {"HOME": str(link)}):
                with self.assertRaisesRegex(SystemExit, "HOME must be a non-symlink"):
                    svc._parse_file_ref(f"file:{link / 'runtime-key'}")

    def test_group_or_other_readable_runtime_key_refused_before_stage(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp)
            key_path = Path(args.runtime_key_ref[5:])
            key_path.chmod(0o640)
            with self.assertRaisesRegex(SystemExit, "deny group/other access"):
                svc.cmd_stage(args)
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_symlinked_runtime_key_parent_refused(self):
        with IsolatedHome() as (tmp, home):
            target = tmp / "credential-target"
            target.mkdir()
            key = target / "runtime-key"
            key.write_text("test-placeholder-not-a-live-key\n", encoding="utf-8")
            key.chmod(0o600)
            link = home / "credential-link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(SystemExit, "symlink ancestor"):
                svc._parse_file_ref(f"file:{link / 'runtime-key'}")

    def test_group_writable_runtime_key_parent_refused_before_stage(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp)
            key_path = Path(args.runtime_key_ref[5:])
            key_path.parent.chmod(0o770)
            with self.assertRaisesRegex(SystemExit, "parent permissions"):
                svc.cmd_stage(args)
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_runtime_key_owned_by_other_uid_refused_before_stage(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp)
            key_path = Path(args.runtime_key_ref[5:])
            info = os.lstat(key_path)
            foreign = mock.Mock(st_mode=info.st_mode, st_uid=os.getuid() + 1)
            real_lstat = os.lstat

            def fake_lstat(candidate):
                if Path(candidate) == key_path:
                    return foreign
                return real_lstat(candidate)

            with mock.patch.object(svc.os, "lstat", side_effect=fake_lstat):
                with self.assertRaisesRegex(SystemExit, "owner mismatch"):
                    svc.cmd_stage(args)
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_wrong_tunnel_id_refused_on_restage(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            before = roots["profile"].read_bytes()
            args.tunnel_id = OTHER_TUNNEL
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("diverge", str(ctx.exception))
            self.assertEqual(roots["profile"].read_bytes(), before)

    def test_chatgpt1_refuses_non_45018_gateway_port(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp, port=45019)
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("45018", str(ctx.exception))
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_wrong_runtime_key_ref_refused(self):
        with IsolatedHome() as (tmp, home):
            _seed_gateway(C1, 45018)
            binary = _make_bin(tmp)
            args = mock.Mock(
                account=C1,
                tunnel_id=C1_TUNNEL,
                profile=str(svc._canonical_profile(C1)),
                runtime_key_ref="env:CONTROL_PLANE_API_KEY",
                organization_id=None,
                tunnel_client=str(binary),
            )
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("file:", str(ctx.exception))
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_missing_key_file_refused(self):
        with IsolatedHome() as (tmp, home):
            missing = (
                home
                / ".config"
                / "tunnel-client"
                / "credentials"
                / "does-not-exist-runtime-key"
            )
            args, _, _ = _stage_args(home, tmp, key_ref=f"file:{missing}")
            with mock.patch.object(
                svc, "_run", CmdRecorder(handler=_stopped_alias_handler())
            ):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("not found", str(ctx.exception))

    def test_runtime_key_outside_home_refused(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(
                home, tmp, key_ref="file:/tmp/not-an-owned-studio-key"
            )
            with self.assertRaisesRegex(SystemExit, "outside HOME"):
                svc.cmd_stage(args)
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_wrong_profile_path_refused(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(
                home, tmp, profile=str(home / "other.yaml")
            )
            (home / "other.yaml").write_text("x")
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("owned path", str(ctx.exception))

    def test_raw_key_value_refused(self):
        with IsolatedHome() as (tmp, home):
            _seed_gateway(C1, 45018)
            args = mock.Mock(
                account=C1,
                tunnel_id=C1_TUNNEL,
                profile=str(svc._canonical_profile(C1)),
                runtime_key_ref="sk-not-a-file-ref",
                organization_id=None,
                tunnel_client=str(_make_bin(tmp)),
            )
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("file:", str(ctx.exception))

    def test_uppercase_account_not_aliased(self):
        with IsolatedHome() as (tmp, home):
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_stage(mock.Mock(account="ChatGPT1"))
            self.assertIn("lowercase", str(ctx.exception))
            self.assertFalse(
                (home / ".local" / "share" / "studio-direct-mcp" / "private" / "chatgpt1").exists()
            )


class TestCollisionsAndTamper(unittest.TestCase):
    def test_running_tmux_alias_blocks_stage(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp)

            def handler(cmd):
                if cmd[:2] == ["launchctl", "print"]:
                    return FakeResult(1, "", "not loaded")
                if cmd[1:3] == ["runtimes", "status"]:
                    return FakeResult(0, _alias_running_json(), "")
                return FakeResult(1, "", "unused")

            writes = []
            with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)), mock.patch.object(
                svc, "_atomic_write_text", side_effect=lambda *a, **k: writes.append(a[0])
            ):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("managed alias", str(ctx.exception))
            self.assertEqual(writes, [])
            self.assertFalse(svc._canonical_profile(C1).exists())

    def test_running_tmux_alias_blocks_start(self):
        with IsolatedHome() as (tmp, home):
            rc, _, args, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)

            def handler(cmd):
                if cmd[:2] == ["launchctl", "print"]:
                    return FakeResult(1, "", "not loaded")
                if cmd[1:3] == ["runtimes", "status"]:
                    return FakeResult(0, _alias_running_json(), "")
                if cmd[:2] == ["launchctl", "bootstrap"]:
                    raise AssertionError("must not bootstrap while alias runs")
                return FakeResult(1, "", "unused")

            with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_start(mock.Mock(account=C1))
            self.assertIn("managed alias", str(ctx.exception))

    def test_foreign_plist_blocks_start(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            foreign = str(home / "foreign.plist")
            label = svc._tunnel_label(C1)

            def handler(cmd):
                if cmd[:2] == ["launchctl", "print"]:
                    return FakeResult(0, _print_running(foreign, label), "")
                if cmd[1:3] == ["runtimes", "status"]:
                    return FakeResult(0, _alias_stopped_json(), "")
                if cmd[:2] == ["launchctl", "bootstrap"]:
                    raise AssertionError("must not bootstrap a foreign job")
                return FakeResult(1, "", "unused")

            with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_start(mock.Mock(account=C1))
            self.assertIn("exact install", str(ctx.exception))

    def test_non_pinned_manifest_refuses_before_client_execution(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            foreign = _make_bin(tmp, "foreign-tunnel-client")
            manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
            manifest["tunnelClient"] = str(foreign)
            roots["manifest"].write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            rec = CmdRecorder(handler=_stopped_alias_handler(C1))
            with mock.patch.object(svc, "_run", rec):
                with self.assertRaisesRegex(SystemExit, "corrupt tunnel manifest"):
                    svc.cmd_start(mock.Mock(account=C1))
            self.assertFalse(
                any(call and call[0] == str(foreign) for call in rec.calls)
            )
            self.assertFalse(any(call[:2] == ["launchctl", "bootstrap"] for call in rec.calls))

            rec = CmdRecorder(handler=_stopped_alias_handler(C1))
            with mock.patch.object(svc, "_run", rec):
                with self.assertRaisesRegex(SystemExit, "corrupt tunnel manifest"):
                    svc.cmd_status(mock.Mock(account=C1))
            self.assertFalse(
                any(call and call[0] == str(foreign) for call in rec.calls)
            )

    def test_profile_tamper_blocks_start(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            tampered = json.loads(roots["profile"].read_text(encoding="utf-8"))
            tampered["control_plane"]["tunnel_id"] = OTHER_TUNNEL
            roots["profile"].write_text(json.dumps(tampered), encoding="utf-8")
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_start(mock.Mock(account=C1))
            self.assertIn("hash mismatch", str(ctx.exception))

    def test_unmanifested_existing_profile_refused(self):
        with IsolatedHome() as (tmp, home):
            args, _, _ = _stage_args(home, tmp)
            profile = svc._canonical_profile(C1)
            profile.parent.mkdir(parents=True, exist_ok=True)
            profile.write_text("official-generated\n", encoding="utf-8")
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("unmanifested", str(ctx.exception))
            self.assertEqual(profile.read_text(encoding="utf-8"), "official-generated\n")

    def test_parent_symlink_refused(self):
        with IsolatedHome() as (tmp, home):
            evil = tmp / "evil"
            evil.mkdir()
            (home / ".local").symlink_to(evil)
            args, _, _ = _stage_args(home, tmp)
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(args)
            self.assertIn("symlink", str(ctx.exception).lower())


class TestStartStatusStop(unittest.TestCase):
    def test_start_bootstraps_exact_plist(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            rec = CmdRecorder(handler=_stopped_alias_handler())
            with mock.patch.object(svc, "_run", rec):
                rc2, out = _capture_stdout(lambda: svc.cmd_start(mock.Mock(account=C1)))
            self.assertEqual(rc2, 0)
            self.assertTrue(json.loads(out)["started"])
            boot = [c for c in rec.calls if c[:2] == ["launchctl", "bootstrap"]]
            self.assertEqual(boot[0][3], str(roots["plist"]))

    def test_status_separates_process_health_ready_and_actual_ttl(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            label = svc._tunnel_label(C1)

            def handler(cmd):
                if cmd[:2] == ["launchctl", "print"]:
                    return FakeResult(0, _print_running(str(roots["plist"]), label), "")
                if cmd[1:3] == ["runtimes", "status"]:
                    return FakeResult(0, _alias_stopped_json(), "")
                return FakeResult(1, "", "unused")

            with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)), mock.patch.object(
                svc, "_strict_tunnel_health", return_value=(True, False, False)
            ), mock.patch.object(svc, "_gateway_ready", return_value=True):
                rc2, out = _capture_stdout(lambda: svc.cmd_status(mock.Mock(account=C1)))
            self.assertEqual(rc2, 0)
            payload = json.loads(out)
            self.assertTrue(payload["running"])
            self.assertTrue(payload["healthy"])
            self.assertFalse(payload["ready"])
            self.assertFalse(payload["controlPlanePollReady"])
            self.assertEqual(payload["transportTTL"], "5h")
            self.assertEqual(payload["maxConcurrentRequests"], 4)
            self.assertEqual(payload["pid"], 4321)
            self.assertFalse(payload["managedAliasRunning"])
            self.assertEqual(payload["tunnelId"], C1_TUNNEL)

            # A green tunnel cannot hide a local gateway that cannot admit work.
            with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)), mock.patch.object(
                svc, "_strict_tunnel_health", return_value=(True, True, True)
            ), mock.patch.object(svc, "_gateway_ready", return_value=False):
                _, out = _capture_stdout(lambda: svc.cmd_status(mock.Mock(account=C1)))
            blocked = json.loads(out)
            self.assertTrue(blocked["tunnelReady"])
            self.assertFalse(blocked["gatewayReady"])
            self.assertFalse(blocked["ready"])

    def test_status_without_process_does_not_claim_health(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            strict = mock.Mock(return_value=(True, True, True))
            with mock.patch.object(svc, "_run", CmdRecorder(handler=_stopped_alias_handler())), mock.patch.object(
                svc, "_strict_tunnel_health", strict
            ):
                rc2, out = _capture_stdout(lambda: svc.cmd_status(mock.Mock(account=C1)))
            self.assertEqual(rc2, 0)
            payload = json.loads(out)
            self.assertFalse(payload["running"])
            self.assertFalse(payload["healthy"])
            self.assertFalse(payload["ready"])
            self.assertEqual(payload["transportTTL"], "5h")
            strict.assert_not_called()

    def test_stop_bootout_only_our_label(self):
        with IsolatedHome() as (tmp, home):
            rc, _, _, _, _, _ = _do_stage(home, tmp)
            self.assertEqual(rc, 0)
            roots = svc._build_tunnel_roots(C1)
            label = svc._tunnel_label(C1)
            seen = {"print": 0}

            def handler(cmd):
                if cmd[:2] == ["launchctl", "print"]:
                    seen["print"] += 1
                    if seen["print"] == 1:
                        return FakeResult(0, _print_running(str(roots["plist"]), label), "")
                    return FakeResult(1, "", "not loaded")
                if cmd[:2] == ["launchctl", "bootout"]:
                    return FakeResult(0, "", "")
                if cmd[1:3] == ["runtimes", "status"]:
                    return FakeResult(0, _alias_stopped_json(), "")
                return FakeResult(1, "", "unused")

            rec = CmdRecorder(handler=handler)
            with mock.patch.object(svc, "_run", rec):
                rc2, out = _capture_stdout(lambda: svc.cmd_stop(mock.Mock(account=C1)))
            self.assertEqual(rc2, 0)
            self.assertTrue(json.loads(out)["stopped"])
            bootout = [c for c in rec.calls if c[:2] == ["launchctl", "bootout"]]
            self.assertTrue(bootout[0][2].endswith(label))
            self.assertNotIn("com.mastermind.studio-direct-private.chatgpt1", bootout[0][2])


if __name__ == "__main__":
    unittest.main()
