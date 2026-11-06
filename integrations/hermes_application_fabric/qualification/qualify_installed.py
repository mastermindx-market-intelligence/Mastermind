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
    args = parser.parse_args()
    root, owner, hermes = (Path(p).resolve() for p in (args.adapter_root, args.owner_root, args.hermes_root))
    expected_hermes = "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"
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
    if hashlib.sha256(owner_bytes).hexdigest() != "3250f2ea9b56b4762619a960c23dd5cc57ae05c273fe8e2b63c89a0f868d0ce0":
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
        "owner": "2ef828e569b683b9dfaa94f81116da3ac55f6186", "owner_source_verified": True,
        "python": sys.version.split()[0], "jsonschema": importlib.metadata.version("jsonschema"),
        "mode": "installed-native-loopback-fixture", "live_provider_acceptance": False}), flush=True)
    suite = unittest.TestSuite()
    for directory in (package / "tests", package / "qualification"):
        suite.addTests(unittest.TestLoader().discover(str(directory), pattern="test_*.py"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skips": len(result.skipped),
        "sdk_constructions": sdk_constructions, "blocked_external_connections": len(blocked_connections),
        "live_provider_acceptance": False}), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped and not sdk_constructions else 1


if __name__ == "__main__":
    raise SystemExit(main())
