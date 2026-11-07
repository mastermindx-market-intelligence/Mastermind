"""Qualify a latency-only delta on an existing APPLICATION provider/H2 stage.

This copies only the closed public dependency set into a temporary test tree.
It never rebuilds/selects a native release, enrolls a consumer or calls a provider.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parent
CONTRACT = PACKAGE / "source-contract.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_frozen(path, *, sha256=None, blob=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError("expected a regular qualification input: " + str(path))
    raw = path.read_bytes()
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("qualification input exceeds its bound")
    if sha256 is not None and digest(raw) != sha256:
        raise ValueError("input SHA256 drift: " + str(path))
    if blob is not None and git_blob(raw) != blob:
        raise ValueError("input Git blob drift: " + str(path))
    return raw


def apply_exact(source, section, *, reverse=False):
    """Apply one fixed-file unified patch using unique exact contexts, no fuzz."""
    lines = section.splitlines(True)
    pieces = re.split(r"(?m)^@@[^\n]*\n", "".join(lines[2:]))[1:]
    if not pieces:
        raise ValueError("empty patch section")
    replacements = []
    for piece in pieces:
        old = "".join(line[1:] for line in piece.splitlines(True)
                      if line.startswith((" ", "-")))
        new = "".join(line[1:] for line in piece.splitlines(True)
                      if line.startswith((" ", "+")))
        if reverse:
            old, new = new, old
        if not old or source.count(old) != 1:
            raise ValueError("patch context is absent or ambiguous")
        start = source.index(old)
        if replacements and start < replacements[-1][1]:
            raise ValueError("patch contexts overlap or are out of order")
        replacements.append((start, start + len(old), new))
    result, cursor = "", 0
    for start, end, new in replacements:
        result += source[cursor:start] + new
        cursor = end
    return result + source[cursor:]


def functions(source):
    found = {}

    def visit(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            name = prefix
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + "." + child.name if prefix else child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if name in found:
                        raise ValueError("ambiguous function qualification")
                    found[name] = ast.dump(child, include_attributes=False)
            visit(child, name)

    visit(ast.parse(source))
    return found


def extract_fixture(patch, path, expected_blob):
    sections = re.split(r"(?m)(?=^--- )", patch)
    matches = [part for part in sections
               if part.startswith("--- /dev/null\n+++ b/" + path + "\n")]
    if len(matches) != 1:
        raise ValueError("incumbent fixture payload is not unique")
    lines = matches[0].splitlines(True)[3:]
    if any(not line.startswith("+") for line in lines):
        raise ValueError("incumbent fixture is not an added-file payload")
    raw = "".join(line[1:] for line in lines).encode()
    if git_blob(raw) != expected_blob:
        raise ValueError("incumbent fixture payload drift")
    return raw


def materialize(stage_root, source_root, work, contract):
    manifest = json.loads(read_frozen(
        stage_root / "native-manifest.json",
        sha256=contract["stage_manifest_sha256"]))
    read_frozen(stage_root / "native-source-inventory.json",
                sha256=contract["stage_inventory_sha256"])
    package = work / "ops/native_fabric/quota_continuity"
    candidate = package / "candidate"
    candidate.mkdir(parents=True)
    (package / "source").mkdir()
    preimages = {}
    for path, expected in contract["public_stage_members"].items():
        if manifest.get(path) != expected:
            raise ValueError("public member differs from the closed stage manifest")
        raw = read_frozen(stage_root / "native-code-stage" / path, sha256=expected)
        name = Path(path).name
        alias = "go_shim.py" if name == "go_application_handler.py" else name
        (candidate / alias).write_bytes(raw)
        if path in contract["runtime_preimages"]:
            if digest(raw) != contract["runtime_preimages"][path]:
                raise ValueError("runtime preimage drift")
            preimages[path] = raw.decode()
    patch = read_frozen(PACKAGE / "application-h2-latency.patch",
                        sha256=contract["patch_sha256"]).decode()
    sections = [s for s in re.split(r"(?m)(?=^--- a/)", patch) if s.strip()]
    results = {}
    for section in sections:
        path = section.splitlines()[0][6:]
        if path not in preimages or path in results:
            raise ValueError("unexpected or repeated runtime path")
        if section.splitlines()[1] != "+++ b/" + path:
            raise ValueError("patch path mismatch")
        post = apply_exact(preimages[path], section)
        if digest(post.encode()) != contract["runtime_postimages"][path]:
            raise ValueError("runtime postimage drift")
        if apply_exact(post, section, reverse=True) != preimages[path]:
            raise ValueError("inverse did not recover the exact parent")
        name = Path(path).name
        alias = "go_shim.py" if name == "go_application_handler.py" else name
        before, after = functions(preimages[path]), functions(post)
        if not set(before) <= set(after):
            raise ValueError("an incumbent function was removed")
        changes = {"changed": [key for key in before if before[key] != after[key]],
                   "added": sorted(set(after) - set(before)),
                   "preserved_count": sum(before[key] == after[key] for key in before)}
        if changes != contract["function_changes"][alias]:
            raise ValueError("function-level composition changed")
        for key in contract["critical_functions"].get(alias, []):
            if key not in before or before[key] != after[key]:
                raise ValueError("provider or quota function changed")
        compile(post, path, "exec")
        (candidate / alias).write_text(post)
        results[path] = digest(post.encode())
    if set(results) != set(contract["runtime_postimages"]):
        raise ValueError("incomplete runtime composition")
    for section_name in ("source_fixture_blobs", "shared_source_blobs"):
        for path, expected in contract[section_name].items():
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_frozen(source_root / path, blob=expected))
    old_patch = read_frozen(
        PACKAGE.parent / "provider_preserving_application/application-provider-latency.patch",
        sha256=contract["historical_fixture_patch_sha256"]).decode()
    for path, expected in contract["embedded_fixture_blobs"].items():
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(extract_fixture(old_patch, path, expected))
    (package / "tests/test_hermes_application_h2_latency_interaction.py").write_bytes(
        read_frozen(PACKAGE / "latency_physical_account.py.source",
                    blob=contract["interaction_fixture_git_blob"]))
    (package / "source/model_tier.py").write_bytes((candidate / "model_tier.py").read_bytes())
    return package, results


def run_tests(work, package, output, contract):
    import yaml  # Existing test dependency, loaded before the fixture I/O boundary.

    os.chdir(work)
    sys.path[:0] = [str(package / "candidate"), str(package / "source"),
                   str(package / "tests"), str(work / "tests"), str(work)]
    os.environ.update({"HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "",
                       "http_proxy": "", "https_proxy": "", "all_proxy": "",
                       "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
    denied = []
    loopback = {"connect": 0, "bind": 0, "dns": 0}

    def audit(event, args):
        if event in {"socket.connect", "socket.bind"}:
            address = args[1]
            if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                denied.append("external_network")
                raise RuntimeError("qualification denied external network")
            loopback["connect" if event == "socket.connect" else "bind"] += 1
        elif event == "socket.getaddrinfo":
            if args[0] != "127.0.0.1":
                denied.append("external_dns")
                raise RuntimeError("qualification denied external DNS")
            loopback["dns"] += 1
        elif event == "subprocess.Popen":
            denied.append("subprocess")
            raise RuntimeError("qualification denied subprocess")
        elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.path.abspath(os.fsdecode(args[0]))
            home = str(Path.home()) + os.sep
            if (path.startswith(home) or path.startswith("/root/")
                    or any("/" + name + "/" in path for name in
                           (".glm", ".minimax", ".bailian", ".qwen",
                            ".anthropic", ".codex", ".claude"))):
                denied.append("production_home_open")
                raise RuntimeError("qualification denied production home access")

    sys.addaudithook(audit)
    names = [
        "test_application_turn_admission", "test_application_turn_pick",
        "test_application_turn_pick_go_composition", "test_application_turn_selection_admission",
        "test_go_application_handler_composition", "test_application_auto_request",
        "test_application_cross_pool_auto", "test_application_registered_pool_selection",
        "test_application_registered_pool_composition",
        "test_hermes_application_latency_qualification",
        "test_hermes_provider_preserving_application_join",
        "test_hermes_application_h2_latency_interaction",
    ]
    suite = unittest.TestSuite()
    counts = {}
    for name in names:
        module = importlib.import_module(name)
        tests = unittest.defaultTestLoader.loadTestsFromModule(module)
        counts[name] = tests.countTestCases()
        suite.addTests(tests)
    h2 = importlib.import_module("test_native_fabric_glm_reset_recovery")

    class EmittedGlmResetBrokerJourney(h2.GlmResetBrokerJourney):
        def runtime_sources(self):
            return {name: package / "candidate" / name for name in
                    ("quota_remote.py", "quota_circuit.py", "lease_broker.py", "pick.py")}

    tests = unittest.defaultTestLoader.loadTestsFromTestCase(EmittedGlmResetBrokerJourney)
    counts["emitted_existing_h2"] = tests.countTestCases()
    suite.addTests(tests)
    if suite.countTestCases() != contract["expected_test_cases"]:
        raise ValueError("qualification test inventory drift")
    with (output / "tests.log").open("w") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {"tests": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": len(result.skipped),
            "successful": result.wasSuccessful(), "module_counts": counts,
            "unexpected_effect_attempts": denied, "numeric_loopback_operations": loopback,
            "test_dependency": {"module": "yaml", "version": yaml.__version__},
            "log_sha256": digest((output / "tests.log").read_bytes())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-root", required=True, type=Path,
                        help="Existing original-owner stage with native-manifest.json")
    parser.add_argument("--source-root", required=True, type=Path,
                        help="Source checkout containing the exact incumbent public fixtures")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New isolated directory for bounded source-qualification evidence")
    args = parser.parse_args(argv)
    contract = json.loads(CONTRACT.read_text())
    stage, source, output = (p.resolve() for p in
                             (args.stage_root, args.source_root, args.output_dir))
    qualifier_sha256 = digest(Path(__file__).read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="hermes-provider-h2-latency-") as temporary:
        work = Path(temporary).resolve()
        package, postimages = materialize(stage, source, work, contract)
        result = run_tests(work, package, output, contract)
        receipt = {"schema": "mastermind.hermes_provider_h2_latency_qualification/v1",
                   "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
                   "qualifier_sha256": qualifier_sha256, "python_version": sys.version.split()[0],
                   "stage_manifest_sha256": contract["stage_manifest_sha256"],
                   "patch_sha256": contract["patch_sha256"], "postimages": postimages,
                   "public_stage_members_verified": len(contract["public_stage_members"]),
                   "full_stage_bytes_verified": False, "held_source_bodies_read": False,
                   "provider_h2_functions_preserved": True, "exact_inverse_roundtrip": True,
                   "source_ref": contract["source_parent"],
                   "runtime_selected_or_installed": False, "provider_request": False,
                   "live_acceptance": False, **result}
        (output / "qualification.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))
        return 0 if result["successful"] and not result["unexpected_effect_attempts"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
