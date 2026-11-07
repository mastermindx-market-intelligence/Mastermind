"""Run immutable candidate tests in an isolated installed Hermes runtime.

Invoke with the installed hermes_cli._launchers.runtime_command(code=...), using
runpy.run_path(this_file, run_name="__main__") as the entry code.
The caller supplies a GitHub-read-back manifest and exact owner source fixture;
this runner never clones, changes the installation, or contacts a provider.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-root", required=True)
    parser.add_argument("--owner-root", required=True)
    parser.add_argument("--hermes-root", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--hermes-sha", choices=("2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19",
        "1c0cd667746d3395fe9e1b6c74f8f85952486f18"),
        default="2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19")
    args = parser.parse_args()
    root, owner, hermes = (Path(p).resolve() for p in (args.adapter_root, args.owner_root, args.hermes_root))
    expected_hermes = args.hermes_sha
    actual = subprocess.run(["git", "-C", str(hermes), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if actual != expected_hermes:
        raise RuntimeError("Installed Hermes source differs from the qualified ABI")
    subprocess.run(["git", "-C", str(hermes), "diff", "--exit-code", "HEAD", "--"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
    manifest = json.loads(Path(args.manifest).read_text())
    if manifest["candidate"] != args.candidate:
        raise RuntimeError("Candidate identity mismatch")
    for relative, expected in manifest["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Candidate source checksum mismatch")
    owner_bytes = (owner / "engine/fabric_inference_client.py").read_bytes()
    if hashlib.sha256(owner_bytes).hexdigest() != "0817202d609637ce024b5f4f1bbe6ba4507825424649f407a235bdf5ef441b8e":
        raise RuntimeError("APPLICATION owner source checksum mismatch")
    package = root / "integrations/hermes_application_fabric"
    sys.path[:0] = [str(root), str(owner), str(package / "tests"), str(package / "qualification")]
    sys.dont_write_bytecode = True

    # Every test endpoint is numeric loopback. Imports/catalog probes must not
    # turn an isolated contract fixture into an external provider operation.
    original_connect = socket.socket.connect
    blocked_connections, sdk_constructions = [], []

    def local_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ("127.0.0.1", "::1"):
            blocked_connections.append(str(address[0]))
            raise RuntimeError("External network disabled in qualification")
        return original_connect(sock, address)

    socket.socket.connect = local_connect
    import openai

    class ForbiddenOpenAI:
        def __init__(self, *_, **__):
            sdk_constructions.append("OpenAI")
            raise AssertionError("Unexpected standard OpenAI construction")

    class ForbiddenAsyncOpenAI:
        def __init__(self, *_, **__):
            sdk_constructions.append("AsyncOpenAI")
            raise AssertionError("Unexpected standard AsyncOpenAI construction")

    openai.OpenAI, openai.AsyncOpenAI = ForbiddenOpenAI, ForbiddenAsyncOpenAI
    print(json.dumps({"candidate": args.candidate, "hermes": actual,
        "owner": "25ba92bb52120fae550b54c29f82929c0b77d37b", "owner_source_verified": True,
        "owner_verification_scope": "client_bytes_only",
        "python": sys.version.split()[0], "jsonschema": importlib.metadata.version("jsonschema"),
        "mode": "installed-native-loopback-fixture", "live_provider_acceptance": False}), flush=True)
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().discover(str(package / "tests"), pattern="test_*.py"))
    # The original unpatched ABI and the attended patched ABI have separate
    # exact-source jobs. Keep every unpatched case, including attended agent
    # construction; the gateway extension is exercised by qualify_gateway.py.
    for pattern in ("test_installed_native.py", "test_native_schema.py", "test_attended_native.py"):
        suite.addTests(unittest.TestLoader().discover(str(package / "qualification"), pattern=pattern))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skips": len(result.skipped),
        "sdk_constructions": sdk_constructions, "blocked_external_connections": len(blocked_connections),
        "live_provider_acceptance": False}), flush=True)
    return 0 if result.wasSuccessful() and result.testsRun == 87 and not result.skipped and not sdk_constructions else 1


if __name__ == "__main__":
    raise SystemExit(main())
