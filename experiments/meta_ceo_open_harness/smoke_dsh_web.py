#!/usr/bin/env python3
"""Provider-free, source-pinned DSH native Web startup acceptance probe.

A disposable read-only product smoke, NOT an Executive Job, model turn,
original-parent result, browser interaction or production install.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

DEFAULT_DSH_SHA = "687f282e8625c6b8d11ff58211a90524be2e4317"
SHA = re.compile(r"[0-9a-f]{40}\Z")
URL = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})(?:/|\b)")
SCHEMA = "mastermind.dsh_web_native_smoke.v1"
MAX_RESPONSE_BYTES = 256 * 1024


class Refused(Exception):
    """A typed reason; never confused with proof of successful startup."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


def command(argv: list[str], *, timeout: float = 8) -> str:
    try:
        done = subprocess.run(argv, check=False, text=True, capture_output=True,
                              timeout=timeout, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Refused("INPUT_UNAVAILABLE", "cannot run source-pin check") from error
    if done.returncode != 0:
        raise Refused("SOURCE_NOT_QUALIFIED", "git revision or clean-state check failed")
    return done.stdout.strip()


def verify_donor(source: Path, expected_sha: str, node: Path) -> dict[str, str]:
    if not SHA.fullmatch(expected_sha):
        raise Refused("INVALID_INPUT", "expected git revision must be 40 lowercase hex digits")
    if source.is_symlink() or not source.is_dir():
        raise Refused("SOURCE_NOT_QUALIFIED", "donor checkout is absent or a symlink")
    source = source.resolve(strict=True)
    top = Path(command(["git", "-C", str(source), "rev-parse", "--show-toplevel"]))
    if top.resolve() != source:
        raise Refused("SOURCE_NOT_QUALIFIED", "donor path is not the Git checkout root")
    actual = command(["git", "-C", str(source), "rev-parse", "HEAD"])
    if actual != expected_sha:
        raise Refused("PIN_MISMATCH", "donor HEAD does not match accepted immutable pin")
    if command(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"]):
        raise Refused("SOURCE_DIRTY", "donor tracked files contain modifications")
    if not (source / "node_modules").is_dir():
        raise Refused("DEPENDENCIES_MISSING", "donor node_modules directory is missing")
    entry = source / "apps/cli/lib/bin.js"
    if not entry.is_file() or entry.is_symlink():
        raise Refused("BUILD_MISSING", "built DSH CLI apps/cli/lib/bin.js is absent")
    if not node.is_file() or not os.access(node, os.X_OK):
        raise Refused("NODE_MISSING", "selected Node executable is unavailable")
    return {"donor_git_sha": actual, "donor": str(source), "node": str(node)}


def clean_env(scratch: Path, node: Path) -> dict[str, str]:
    dirs = {
        "HOME": scratch / "home", "DSH_HOME": scratch / "dsh-home",
        "XDG_CONFIG_HOME": scratch / "xdg-config", "XDG_CACHE_HOME": scratch / "xdg-cache",
        "TMPDIR": scratch / "tmp",
    }
    for directory in dirs.values():
        directory.mkdir(mode=0o700, parents=True)
    # No inherited provider keys, browser cookies, proxies, npm configs or NODE_OPTIONS.
    env = {key: str(value) for key, value in dirs.items()}
    env["PATH"] = str(node.parent) + ":/usr/bin:/bin"
    env["LANG"] = "C"
    return env


def wait_for_web(process: subprocess.Popen[str], lines: queue.Queue[str],
                 deadline: float) -> dict:
    opener = build_opener(ProxyHandler({}))  # Never use ambient HTTP proxy.
    announced_port = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Refused("STARTUP_EXITED", "Web CLI exited before serving the application")
        try:
            line = lines.get(timeout=min(0.15, max(0.01, deadline-time.monotonic())))
            matches = URL.findall(line)
            if matches:
                announced_port = int(matches[-1])
                if announced_port > 65535:
                    raise Refused("UNTRUSTED_ORIGIN", "app advertised an invalid port")
        except queue.Empty:
            pass
        if announced_port is None:
            continue
        origin = f"http://127.0.0.1:{announced_port}/"
        try:
            with opener.open(Request(origin, method="GET"), timeout=0.45) as response:
                code = response.status
                media_type = response.headers.get_content_type()
                data = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, URLError, HTTPError):
            continue
        if len(data) > MAX_RESPONSE_BYTES:
            raise Refused("INVALID_WEB_RESPONSE", "HTML document exceeds bounded limit")
        html = data.decode("utf-8", "replace").lower()
        if code != 200 or media_type != "text/html" or "<html" not in html:
            raise Refused("INVALID_WEB_RESPONSE", "Web HTTP response is not HTML 200")
        if re.search(r'id=[\"\']root[\"\']', html) is None or "<script" not in html:
            raise Refused("INVALID_WEB_RESPONSE", "DSH browser root/script markers missing")
        return {"status": "WEB_HTML_READ", "url": origin,
                "http_status": code, "content_type": media_type,
                "html_bytes": len(data), "root_mount_present": True,
                "script_tag_present": True}
    if announced_port is None:
        raise Refused("STARTUP_NO_LOOPBACK_URL", "no local IPv4 loopback URL announced")
    raise Refused("HTTP_NOT_READY", "announced loopback origin did not serve a valid app shell")


def terminate_own_process(process: subprocess.Popen[str]) -> bool:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
        return True
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
            return True
        except subprocess.TimeoutExpired:
            return False


def execute(source: Path, expected_sha: str, node: Path, timeout: float) -> dict:
    receipt: dict = {"schema": SCHEMA, "status": "NOT_STARTED",
                     "source_pin": expected_sha,
                     "provider_requests_observed": "NOT_INSTRUMENTED",
                     "model_inference_tested": False, "native_chat_tested": False,
                     "executive_or_fabric_called": False, "installed": False}
    try:
        if not 0.2 <= timeout <= 180:
            raise Refused("INVALID_INPUT", "timeout must be 0.2 through 180 seconds")
        provenance = verify_donor(source, expected_sha, node)
        receipt.update(provenance)
        with tempfile.TemporaryDirectory(prefix="mmx-dsh-native-smoke-") as temporary:
            scratch = Path(temporary)
            os.chmod(scratch, 0o700)
            env = clean_env(scratch, node)
            # The source checkout is a read-only dependency; web profile writes into scratch.
            argv = [str(node), str(source / "apps/cli/lib/bin.js"), "web", "--no-open",
                    "--host", "127.0.0.1", "--port", "0"]
            try:
                process = subprocess.Popen(argv, cwd=scratch, env=env, text=True,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           bufsize=1, start_new_session=True)
            except OSError as error:
                raise Refused("STARTUP_UNAVAILABLE", "cannot start pinned native CLI") from error
            messages: queue.Queue[str] = queue.Queue(maxsize=4096)
            def consume() -> None:
                assert process.stdout is not None
                while line := process.stdout.readline(4096):
                    try:
                        messages.put_nowait(line)
                    except queue.Full:
                        break
            reader = threading.Thread(target=consume, daemon=True)
            reader.start()
            try:
                observation = wait_for_web(process, messages, time.monotonic() + timeout)
                receipt.update(observation)
            finally:
                receipt["owned_process_stopped"] = terminate_own_process(process)
                reader.join(timeout=1)
                if process.stdout is not None:
                    process.stdout.close()
                if not receipt["owned_process_stopped"]:
                    receipt["status"] = "CLEANUP_UNKNOWN"
                    receipt["reason"] = "owned startup process could not be reaped"
            if receipt["status"] == "WEB_HTML_READ":
                receipt["status"] = "NATIVE_WEB_SHELL_PASS"
    except Refused as error:
        receipt["status"] = error.status
        receipt["reason"] = str(error)
    except (OSError, ValueError) as error:
        receipt["status"] = "INPUT_UNAVAILABLE"
        receipt["reason"] = type(error).__name__
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--expected-sha", default=DEFAULT_DSH_SHA)
    parser.add_argument("--node", type=Path, default=Path(shutil.which("node") or "node"))
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--receipt", type=Path, required=True,
                        help="new receipt file outside donor checkout; refuses overwrite")
    args = parser.parse_args()
    receipt = args.receipt.absolute()
    # Refuse invalid/occupied targets BEFORE running the external donor process.
    try:
        donor_root = args.donor.resolve(strict=True)
        if receipt == donor_root or receipt.is_relative_to(donor_root):
            raise Refused("INVALID_RECEIPT", "receipt must remain outside donor checkout")
        if receipt.exists() or receipt.is_symlink():
            raise Refused("EXISTING_RECEIPT", "do not overwrite an existing receipt")
        receipt.parent.mkdir(parents=True, exist_ok=True)
    except (Refused, OSError) as error:
        print(json.dumps({"status": "RECEIPT_NOT_PERSISTED", "reason": str(error)}), file=sys.stderr)
        return 2
    result = execute(args.donor, args.expected_sha, args.node.resolve(), args.timeout)
    try:
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(result, handle, sort_keys=True, indent=2)
            handle.write("\n")
    except (Refused, OSError) as error:
        print(json.dumps({"status": "RECEIPT_NOT_PERSISTED", "reason": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "receipt": str(receipt),
                      "native_chat_tested": False}, sort_keys=True))
    return 0 if result["status"] == "NATIVE_WEB_SHELL_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
