"""Opt-in disposable macOS proof of the real native port, never a fleet rollout.

Run from the managed source checkout with --run-disposable-probe. This opens a
background, account-free fixture for at most 180 seconds and performs ONE click.
The report explicitly does not claim live Fabric admission or production release.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import plistlib
import secrets
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

from integrations.workbench_action_mcp.action_artifacts import ActionHostBinding, adopt_artifact_store
from integrations.workbench_action_mcp.contracts import ActionCaller, ActionScope, ProjectActionBinding
from integrations.workbench_app_use.contracts import NativeAppGrant, native_target
from integrations.workbench_app_use.native_port import NativeAppPort
from integrations.workbench_app_use.peekaboo_adapter import PeekabooAdapter, PeekabooConfig, _boot_id

BUNDLE = "com.mastermind.native-app-use-probe"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-disposable-probe", action="store_true")
    parser.add_argument("--report", required=True)
    parser.add_argument("--peekaboo-binary", default="/opt/homebrew/bin/peekaboo")
    parser.add_argument("--bridge-socket")
    args = parser.parse_args()
    if sys.platform != "darwin" or not args.run_disposable_probe:
        parser.error("explicit disposable macOS probe required")
    report_path = Path(args.report)
    if not report_path.is_absolute():
        parser.error("absolute report path required")
    report = {"schema": "mastermind.native_app_use_real_path_proof.v1",
        "live_fabric_admission_proven": False, "production_deployment_proven": False,
        "scope": "disposable native fixture through Workbench action port",
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    provider = None
    fixture_pid = None
    fixture_identity = None
    root = Path(__file__).resolve().parents[1]
    report["candidate_source_sha256"] = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [*sorted((root / "integrations/workbench_app_use").glob("*.py")),
                     root / "integrations/workbench_action_mcp/action_artifacts.py",
                     root / "tests/fixtures/native_app_use/Probe.swift"]}
    try:
        with tempfile.TemporaryDirectory(prefix="mmx-native-proof-") as temp:
            temporary = Path(temp)
            app = temporary / "MastermindNativeProbe.app"
            macos = app / "Contents" / "MacOS"
            macos.mkdir(parents=True, mode=0o700)
            (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleExecutable": "MastermindNativeProbe", "CFBundleIdentifier": BUNDLE,
                "CFBundleName": "Mastermind Native Probe", "CFBundlePackageType": "APPL",
                "LSUIElement": True}))
            subprocess.run(["/usr/bin/swiftc", str(root / "tests/fixtures/native_app_use/Probe.swift"),
                "-o", str(macos / "MastermindNativeProbe"), "-framework", "AppKit"],
                check=True, timeout=60, capture_output=True)
            boot = _boot_id()
            host = ActionHostBinding(hashlib.sha256(socket.gethostname().encode()).hexdigest(), boot)
            binary_input = Path(args.peekaboo_binary)
            if not binary_input.is_absolute():
                raise RuntimeError("qualified Peekaboo executable must be absolute")
            binary = binary_input.resolve(strict=True)
            bridge_socket = None
            if args.bridge_socket:
                bridge_input = Path(args.bridge_socket)
                if not bridge_input.is_absolute():
                    raise RuntimeError("qualified Peekaboo bridge path must be absolute")
                bridge_info = bridge_input.lstat()
                if (not stat.S_ISSOCK(bridge_info.st_mode)
                        or bridge_info.st_uid != os.getuid()):
                    raise RuntimeError("qualified Peekaboo bridge is not an owned socket")
                bridge_socket = str(bridge_input)
            binary_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            provider = PeekabooAdapter(PeekabooConfig(str(binary), binary_digest,
                str(Path.home()), host, os.getuid(), ("click_element",),
                bridge_socket=bridge_socket))
            report.update({"carrier": provider.carrier, "binary_sha256": binary_digest,
                "session_ref": provider.session_ref, "permissions": provider.permissions()})
            if report["permissions"].get("observation_ready") is not True:
                raise RuntimeError("actual harness child lacks native observation permission; no UI probe launched")
            def active():
                return sorted(row["pid"] for row in provider._run(["app", "list"])["apps"]
                              if row.get("is_active") is True)
            before_active = active()
            nonce = secrets.token_hex(16)
            app_receipt = temporary / "fixture-result.json"
            subprocess.run(["/usr/bin/open", "-g", "-n", str(app), "--args",
                            "--receipt", str(app_receipt), "--nonce", nonce],
                           check=True, timeout=8, capture_output=True)
            deadline = time.monotonic() + 8
            while not app_receipt.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            initial = json.loads(app_receipt.read_text())
            if initial.get("nonce") != nonce or initial.get("count") != 0:
                raise RuntimeError("fixture did not establish exact zero preimage")
            fixture_pid = initial["pid"]
            apps = [row for row in provider.applications()["applications"]
                    if row["bundle_id"] == BUNDLE and row["pid"] == fixture_pid]
            if len(apps) != 1:
                raise RuntimeError("fixture exact application identity unavailable")
            fixture_identity = {key: value for key, value in apps[0].items() if key != "name"}
            windows = provider.windows(**fixture_identity)["windows"]
            if len(windows) != 1:
                raise RuntimeError("fixture exact window unavailable")
            target = windows[0]["target"]
            report["target"] = target
            artifacts = temporary / "action-evidence"
            artifacts.mkdir(mode=0o700)
            with ExitStack() as stack:
                root_fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
                store_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
                stack.callback(os.close, root_fd); stack.callback(os.close, store_fd)
                info = os.fstat(root_fd)
                now = lambda: time.time_ns() // 1_000_000
                caller = ActionCaller(hashlib.sha256(nonce.encode()).hexdigest(),
                    "native-proof-fixture", "native-proof:local", ("workbench.action",),
                    now() // 1000 + 120)
                scope = ActionScope(root_fd, info.st_dev, info.st_ino, "context:native-proof",
                    "responsibility:native-proof", "operation:native-proof",
                    "owner:disposable-fixture", "generation:" + nonce,
                    ("fixture-result.json",), now() + 120000)
                binding = ProjectActionBinding(caller, "project:native-proof", scope)
                grant = NativeAppGrant("qualification:" + nonce, host.host_id, boot,
                    provider.session_ref, scope.generation, (BUNDLE,), ("click_element",),
                    scope.expires_at_ms, (native_target(target),))
                port = NativeAppPort(resolve_binding=lambda c, p: binding,
                    resolve_grant=lambda b: grant, clock_ms=now, action_token_key=secrets.token_bytes(32),
                    artifact_store=adopt_artifact_store(store_fd), host_binding=host, provider=provider)
                observation = port.observe(caller, project_ref=binding.project_ref, target=target)
                elements = observation["content"]["ui_elements"]
                candidates = [row for row in elements if type(row) is dict
                    and any(value == "Increment proof" for value in row.values())]
                if len(candidates) != 1 or type(candidates[0].get("id")) is not str:
                    report["fixture_elements"] = elements
                    raise RuntimeError("unique fixture accessibility button unavailable")
                preparation = port.prepare(caller, project_ref=binding.project_ref,
                    observation_ref=observation["observation_ref"],
                    native_command={"action": "click_element",
                                    "arguments": {"element_id": candidates[0]["id"]}})
                result = port.run(caller, project_ref=binding.project_ref,
                                  action_ref=preparation["action_ref"])
                report["native_action"] = result
                after = json.loads(app_receipt.read_text())
                readback_deadline = time.monotonic() + 2
                while after["count"] == 0 and time.monotonic() < readback_deadline:
                    time.sleep(.05)
                    after = json.loads(app_receipt.read_text())
                report["counter_after_action"] = after["count"]
                report["fixture_nonce_matched"] = after.get("nonce") == nonce
                # Read-only reconciliation; do not retry an unknown native call.
                recovered = port.reconcile(caller, project_ref=binding.project_ref,
                                           action_ref=preparation["action_ref"])
                report["reconciliation_matches"] = recovered == result
                if result["effect_state"] == "APPLIED" and after["count"] == 1:
                    repeated = port.run(caller, project_ref=binding.project_ref,
                                        action_ref=preparation["action_ref"])
                    report["duplicate_delivery_same_receipt"] = repeated == result
                    report["counter_after_duplicate"] = json.loads(app_receipt.read_text())["count"]
                report["original_action_evidence"] = {
                    path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "record": json.loads(path.read_bytes())}
                    for path in artifacts.iterdir() if path.suffix == ".json"}
                report["foreground_unchanged"] = active() == before_active
                report["status"] = ("PROVEN" if result["effect_state"] == "APPLIED"
                    and after["count"] == 1 and report.get("counter_after_duplicate") == 1
                    and report["foreground_unchanged"] else "NOT_PROVEN")
    except Exception as error:
        report["status"] = "NOT_PROVEN"
        report["error"] = type(error).__name__ + ": " + str(error)[:1000]
    finally:
        if provider is not None and fixture_identity is not None:
            try:
                current = provider.applications()["applications"]
                if any(all(row.get(key) == value for key, value in fixture_identity.items())
                       for row in current):
                    os.kill(fixture_pid, signal.SIGTERM)
            except Exception:
                report["fixture_cleanup"] = "unconfirmed; fixture has a 180-second maximum lifetime"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
