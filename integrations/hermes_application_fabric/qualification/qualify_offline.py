"""Qualify the adapter against the exact incumbent client, without Hermes/keys.

The owner checkout is read-only evidence. Only its checksum-verified client is
copied into a temporary import fixture; no owner package initializer is executed.
This is not role enrollment, a live provider run, or budget/lease acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import socket
import sys
import tempfile
import unittest


OWNER_COMMIT = "fff0025e10de394c6a297c7878518513f1dbe633"
OWNER_SHA256 = "0817202d609637ce024b5f4f1bbe6ba4507825424649f407a235bdf5ef441b8e"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-root", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    package = root / "integrations/hermes_application_fabric"
    source = (Path(args.owner_root).resolve() / "engine/fabric_inference_client.py").read_bytes()
    if hashlib.sha256(source).hexdigest() != OWNER_SHA256:
        raise RuntimeError("APPLICATION client checksum mismatch")
    validator = importlib.metadata.version("jsonschema")
    if validator != "4.26.0":
        raise RuntimeError("Use the qualified jsonschema dependency")

    blocked = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded(original):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ("127.0.0.1", "::1"):
                blocked.append("external_connection")
                raise RuntimeError("External network disabled in qualification")
            return original(sock, address)
        return connect

    socket.socket.connect = guarded(original_connect)
    socket.socket.connect_ex = guarded(original_connect_ex)
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="hermes-application-client-") as temporary:
        fixture = Path(temporary)
        (fixture / "engine").mkdir()
        (fixture / "engine/__init__.py").write_text("")
        (fixture / "engine/fabric_inference_client.py").write_bytes(source)
        sys.path[:0] = [str(root), str(fixture), str(package / "tests"), str(package / "qualification")]
        suite = unittest.TestSuite()
        suite.addTests(unittest.TestLoader().discover(str(package / "tests"), pattern="test_*.py"))
        suite.addTests(unittest.TestLoader().discover(str(package / "qualification"), pattern="test_native_schema.py"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print(json.dumps({"mode": "offline-original-client-loopback-fixture",
            "owner": OWNER_COMMIT, "owner_client_sha256": OWNER_SHA256,
            "owner_verification_scope": "client_bytes_only",
            "python": sys.version.split()[0], "jsonschema": validator,
            "tests_run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skips": len(result.skipped),
            "blocked_external_connections": len(blocked), "live_provider_acceptance": False}, sort_keys=True))
        return 0 if result.wasSuccessful() and result.testsRun == 68 and not result.skipped and not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
