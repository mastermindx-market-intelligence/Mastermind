"""Finite, unprivileged protocol qualification using an existing Chisel binary.

Only synthetic loopback traffic and a new private /tmp fixture are permitted.
This never invokes the production tunnel owner or reads its credentials/journals.
An existing reverse listener requires its original client's stop for revocation;
authfile reload alone only changes new reverse admission and incoming SSH ACLs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import stat
import subprocess
import threading
import time


ADDRESSES = ("127.0.0.1", "127.0.0.2", "127.0.0.3")
RESERVED_PORTS = {22, 80, 443, 4142, 50142}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def port_for(addresses):
    held = []
    try:
        first = socket.socket()
        held.append(first)
        first.bind((addresses[0], 0))
        port = first.getsockname()[1]
        require(port not in RESERVED_PORTS, "ephemeral port overlaps production")
        for address in addresses[1:]:
            other = socket.socket()
            held.append(other)
            other.bind((address, port))
        return port
    finally:
        for connection in held:
            connection.close()


def execute(binary, expected_sha256, root):
    binary, root = Path(binary), Path(root)
    require(os.geteuid() != 0, "fixture must run without root")
    require(root.is_absolute() and root.parent == Path("/tmp")
            and root.name.startswith("mmx-hermes-chisel-protocol-"), "fixture path refused")
    info = binary.lstat()
    require(binary.is_absolute() and stat.S_ISREG(info.st_mode)
            and info.st_uid == 0 and info.st_mode & 0o022 == 0, "binary custody refused")
    raw = binary.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, "binary digest changed")
    version = subprocess.run([str(binary), "--version"], capture_output=True,
                             text=True, timeout=5, check=True).stdout.strip()
    require(version == "1.12.0", "fixture source qualification is version-specific")
    root.mkdir(mode=0o700, exist_ok=False)
    deadline = time.monotonic() + 55
    children, handles, events = [], [], []
    arrivals, lock = Counter(), threading.Lock()
    denied_tokens = []
    backend = backend_thread = None
    authfile, keyfile = root / "users.json", root / "server.key"
    credential = "hermes-protocol-fixture:" + secrets.token_urlsafe(32)
    receipt = {
        "schema": "hermes_application_chisel_protocol_fixture_v1",
        "binary_sha256": expected_sha256, "version": version,
        "uid": os.geteuid(), "fixture_root": str(root),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "tested_pair": "existing Linux binary in client and server modes",
        "events": events, "passed": False,
        "production_tunnel_proven": False, "application_proven": False,
        "root_qualification_attestation": False,
        "m2_client_linux_server_session_proven": False,
    }

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(1)
            data = b""
            try:
                while b"\n" not in data and len(data) <= 512:
                    fragment = self.request.recv(513 - len(data))
                    if not fragment:
                        return
                    data += fragment
                if not data.endswith(b"\n") or len(data) > 512:
                    return
                with lock:
                    arrivals[data.decode("ascii").strip()] += 1
                self.request.sendall(b"ACK:" + data)
            except (OSError, UnicodeError):
                return

    def wait_for(label, predicate, seconds=8):
        end = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.05)
        raise RuntimeError(label + " deadline")

    def start(name, argv, environment):
        log = root / (name + ".log")
        handle = log.open("xb")
        os.chmod(log, 0o600)
        handles.append(handle)
        process = subprocess.Popen(argv, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=handle, stderr=subprocess.STDOUT)
        children.append((name, process))
        events.append({"action": "start", "name": name, "pid": process.pid})
        return process, log

    def stop(name, process):
        signal_sent = process.poll() is None
        if signal_sent:
            process.terminate()
        try:
            code = process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait(timeout=3)
        events.append({"action": "terminal", "name": name, "pid": process.pid,
                       "returncode": code, "termination_requested": signal_sent})

    def probe(address, port, token):
        data = (token + "\n").encode("ascii")
        try:
            with socket.create_connection((address, port), timeout=0.5) as connection:
                connection.settimeout(0.5)
                connection.sendall(data)
                received = b""
                while len(received) < len(data) + 4:
                    fragment = connection.recv(len(data) + 4 - len(received))
                    if not fragment:
                        break
                    received += fragment
                return received == b"ACK:" + data
        except OSError:
            return False

    def success(address, port, label):
        token = label + "-" + secrets.token_hex(12)
        require(probe(address, port, token), label + " forwarding failed")
        with lock:
            require(arrivals[token] == 1, label + " duplicate backend arrival")
        events.append({"action": "forwarded_once", "label": label, "address": address})

    def replace_grants(grants, label):
        previous = authfile.stat().st_ino if authfile.exists() else None
        pending = root / (label + ".users.pending")
        with pending.open("xb") as handle:
            os.chmod(pending, 0o600)
            handle.write((json.dumps({credential: grants}, sort_keys=True) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending, authfile)
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        current = authfile.stat().st_ino
        require(previous is None or previous != current, "authfile replacement kept inode")
        events.append({"action": "atomic_authfile_replace", "label": label,
                       "old_inode": previous, "new_inode": current})

    try:
        backend = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
        backend_thread.start()
        backend_port = backend.server_address[1]
        require(backend_port not in RESERVED_PORTS, "backend overlaps production")
        relay_port, forward_port, server_port = port_for(ADDRESSES), port_for(ADDRESSES[:1]), port_for(ADDRESSES[:1])
        require(len({backend_port, relay_port, forward_port, server_port}) == 4, "fixture port collision")
        reverse = [f"R:{address}:{relay_port}:127.0.0.1:{backend_port}" for address in ADDRESSES]
        reverse_grants = ["^" + re.escape(f"R:{address}:{relay_port}") + "$" for address in ADDRESSES]
        forward_grant = "^" + re.escape(f"127.0.0.1:{backend_port}") + "$"
        replace_grants(reverse_grants + [forward_grant], "initial")
        subprocess.run([str(binary), "server", "--host", "127.0.0.1", "--port", "0",
                        "--keygen", str(keyfile)], env={}, stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=5, check=True)
        os.chmod(keyfile, 0o600)
        server, server_log = start("server", [str(binary), "server", "--host", "127.0.0.1",
            "--port", str(server_port), "--reverse", "--authfile", str(authfile),
            "--keyfile", str(keyfile), "--keepalive", "20s"], {})
        fingerprint = []

        def server_ready():
            require(server.poll() is None, "fixture server exited")
            match = re.search(r"Fingerprint ([A-Za-z0-9+/]{43}=)", server_log.read_text())
            if match:
                fingerprint[:] = [match.group(1)]
            return bool(fingerprint) and "Listening" in server_log.read_text()

        wait_for("server startup", server_ready)
        endpoint = f"http://127.0.0.1:{server_port}"
        common = [str(binary), "client", "--fingerprint", fingerprint[0], "--keepalive", "20s", endpoint]
        environment = {"AUTH": credential}
        original, original_log = start("reverse-original", common + reverse, environment)
        forward, forward_log = start("forward-retained", common + [f"127.0.0.1:{forward_port}:127.0.0.1:{backend_port}"], environment)
        wait_for("original reverse handshake", lambda: "Connected" in original_log.read_text())
        wait_for("forward handshake", lambda: "Connected" in forward_log.read_text())
        wait_for("all reverse listeners", lambda: all(probe(address, relay_port,
            "reverse-readiness-" + secrets.token_hex(12)) for address in ADDRESSES))
        wait_for("forward listener", lambda: probe("127.0.0.1", forward_port,
            "forward-readiness-" + secrets.token_hex(12)))
        for address in ADDRESSES:
            success(address, relay_port, "initial-reverse-" + address)
        success("127.0.0.1", forward_port, "initial-forward")
        restricted_log_offset = server_log.stat().st_size
        replace_grants(reverse_grants[:1], "restricted")
        denial_message = f"Denied connection to 127.0.0.1:{backend_port} (ACL)".encode()

        def forward_revoked():
            require(server.poll() is None and forward.poll() is None, "retained process exited")
            require(forward_log.read_text().count("Connected") == 1,
                    "forward client changed authenticated connection")
            token = "revocation-observation-" + secrets.token_hex(12)
            if probe("127.0.0.1", forward_port, token):
                return False
            if denial_message not in server_log.read_bytes()[restricted_log_offset:]:
                return False
            denied_tokens.append(token)
            return True

        wait_for("fresh forward ACL reload", forward_revoked)
        # Existing reverse accepts are not covered by the server's incoming-SSH ACL.
        require(original_log.read_text().count("Connected") == 1,
                "original reverse client reconnected")
        success("127.0.0.2", relay_port, "retained-reverse-requires-stop")
        stop("reverse-original", original)
        wait_for("original reverse listener removal", lambda: not probe("127.0.0.2", relay_port,
            "closed-listener-" + secrets.token_hex(12)))
        refused, refused_log = start("reverse-refused", common + reverse[1:2], environment)
        reverse_denial = f"access to 'R:127.0.0.2:{relay_port}' denied".lower()
        wait_for("new reverse refusal", lambda: reverse_denial in refused_log.read_text().lower())
        token = "new-reverse-denied-" + secrets.token_hex(12)
        require(not probe("127.0.0.2", relay_port, token), "revoked new reverse was usable")
        denied_tokens.append(token)
        stop("reverse-refused", refused)
        allowed, allowed_log = start("reverse-allowed", common + reverse[:1], environment)
        wait_for("allowed reverse handshake", lambda: "Connected" in allowed_log.read_text())
        wait_for("allowed reverse listener", lambda: probe("127.0.0.1", relay_port,
            "allowed-readiness-" + secrets.token_hex(12)))
        success("127.0.0.1", relay_port, "new-reverse-allowed")
        replace_grants(reverse_grants + [forward_grant], "restored")

        def forward_restored():
            require(server.poll() is None and forward.poll() is None, "retained process exited")
            require(forward_log.read_text().count("Connected") == 1,
                    "forward client changed authenticated connection")
            return probe("127.0.0.1", forward_port, "restore-observation-" + secrets.token_hex(12))

        wait_for("fresh forward restoration", forward_restored)
        success("127.0.0.1", forward_port, "restored-forward")
        require(server.poll() is None and forward.poll() is None and allowed.poll() is None,
                "qualified fixture process did not remain alive")
        require(forward_log.read_text().count("Connected") == 1,
                "forward client changed authenticated connection")
        receipt.update(simultaneous_three_reverse_addresses=True, atomic_rename_reload=True,
            new_reverse_client_acl_refresh=True, retained_forward_client_new_channel_acl_refresh=True,
            existing_reverse_listener_revocation_without_stop=False,
            retained_forward_authenticated_connections=1, fresh_forward_acl_denial_observed=True,
            server_pid=server.pid, retained_forward_pid=forward.pid,
            ephemeral_ports={"server": server_port, "relay": relay_port,
                             "forward": forward_port, "backend": backend_port},
            passed=True)
    except Exception as exc:
        receipt["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        for name, process in reversed(children):
            try:
                stop(name, process)
            except Exception as exc:
                receipt["passed"] = False
                events.append({"action": "cleanup_failed", "name": name, "error": type(exc).__name__})
        if backend is not None:
            backend.shutdown()
            backend.server_close()
        if backend_thread is not None:
            backend_thread.join(timeout=2)
        for handle in handles:
            handle.close()
        with lock:
            receipt["denied_probe_backend_arrivals"] = sum(arrivals[t] for t in denied_tokens)
            receipt["total_backend_arrivals"] = sum(arrivals.values())
            receipt["duplicate_nonce_arrivals"] = sum(max(0, n - 1) for n in arrivals.values())
        if receipt["denied_probe_backend_arrivals"]:
            receipt["passed"] = False
        if receipt["duplicate_nonce_arrivals"]:
            receipt["passed"] = False
        receipt["owned_processes_terminal"] = all(p.poll() is not None for _, p in children)
        receipt["passed"] = receipt["passed"] and receipt["owned_processes_terminal"]
        for private in (authfile, keyfile, *root.glob("*.users.pending")):
            private.unlink(missing_ok=True)
        receipt["synthetic_private_files_removed"] = not authfile.exists() and not keyfile.exists()
        receipt["logs"] = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                   "bytes": p.stat().st_size} for p in root.glob("*.log")}
        (root / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--fixture-root", required=True)
    args = parser.parse_args()
    result = execute(args.binary, args.expected_sha256, args.fixture_root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
