"""Prepare an exact, disposable Macro source proposal for qualification only.

The original checkout is read-only. This utility neither installs the proposal
nor grants runtime eligibility; the existing APPLICATION source owner consumes
the published patch through its own carrier and release rules.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import xml.etree.ElementTree as ET


OWNER_COMMIT = "a577dbbf605474f97bbafa4ceeb0daf841292421"
CURRENT_OWNER_COMMIT = "12efe39a6b6e2f6d19f3a9893f978c55d4656681"
COMPOSED_OWNER_COMMIT = "fff0025e10de394c6a297c7878518513f1dbe633"
CHANGED = frozenset({
    "engine/provider_production_modes.py",
    "tests/test_hermes_primary_fabric_identity.py",
    "tests/test_hermes_attended_fabric_identity.py",
    "tests/test_hermes_application_source_support.py",
})
TESTS = (
    "tests/test_hermes_application_source_support.py",
    "tests/test_hermes_primary_fabric_identity.py",
    "tests/test_hermes_attended_fabric_identity.py",
    "tests/test_fabric_service_identity.py",
    "tests/test_fabric_application_binding.py",
    "tests/test_fabric_application_inspection.py",
    "tests/test_hermes_primary_fabric_endpoint.py",
)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *arguments, input_data=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
               GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    stream = {"stdin": subprocess.DEVNULL} if input_data is None else {"input": input_data}
    try:
        return subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-C", str(root), *arguments],
            env=env, capture_output=True, timeout=60, check=True, **stream).stdout
    except subprocess.CalledProcessError as error:
        diagnostic = error.stderr.decode("utf-8", errors="replace")
        diagnostic = re.sub(r"(?:https?|ssh)://[^\s]+", "[remote]", diagnostic)
        diagnostic = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+", "[credential]", diagnostic)
        diagnostic = " ".join(diagnostic.split())[:1000]
        raise RuntimeError("Source fixture git " + arguments[0] + " failed ("
                           + str(error.returncode) + "): " + diagnostic) from None


def export_committed(original, destination, commit, selected):
    """Export only locally present, regular committed blobs; never fetch or copy HEAD's worktree."""
    records = git(original, "ls-tree", "-r", "-z", "--full-tree", commit, "--", *selected)
    entries, seen = [], set()
    for record in records.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split()
        name = raw_path.decode("utf-8")
        relative = PurePosixPath(name)
        if (mode not in {"100644", "100755"} or kind != "blob"
                or re.fullmatch(r"[0-9a-f]{40}", oid) is None
                or relative.is_absolute() or ".." in relative.parts
                or name in seen or str(relative) != name
                or not any(name == path or name.startswith(path + "/") for path in selected)):
            raise RuntimeError("Source fixture has an unsafe committed member")
        seen.add(name)
        entries.append((name, mode, oid))
    if not entries or any(not any(name == path or name.startswith(path + "/")
            for name in seen) for path in selected):
        raise RuntimeError("Source fixture lacks a selected committed path")
    object_ids = sorted({oid for _, _, oid in entries})
    checks = git(original, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                 input_data=("\n".join(object_ids) + "\n").encode("ascii")).decode("ascii").splitlines()
    sizes = {}
    if len(checks) != len(object_ids):
        raise RuntimeError("Source fixture object inventory is incomplete")
    for oid, line in zip(object_ids, checks):
        fields = line.split()
        if len(fields) != 3 or fields[:2] != [oid, "blob"] or not fields[2].isdigit():
            raise RuntimeError("Source fixture committed blob is not locally available: " + oid)
        sizes[oid] = int(fields[2])
    for name, mode, oid in entries:
        raw = git(original, "cat-file", "blob", oid)
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw,
                              usedforsecurity=False).hexdigest()
        if len(raw) != sizes[oid] or actual != oid:
            raise RuntimeError("Source fixture committed blob differs: " + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(raw)
        target.chmod(int(mode[-3:], 8))
    return {"method": "verified_local_committed_blobs", "files": len(entries),
            "unique_blobs": len(object_ids), "bytes": sum(sizes[oid] for _, _, oid in entries),
            "lazy_fetch_permitted": False, "worktree_content_used": False}


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("Source fixture has a non-regular member")
        files[str(path.relative_to(root))] = sha256(path.read_bytes())
    return files


def _support_contract(adapter):
    package = adapter / "integrations/hermes_application_fabric/qualification/application_owner_support"
    raw_contract = (package / "contract.json").read_bytes()
    contract = json.loads(raw_contract)
    patch = package / "a577-hermes-source-support.patch"
    if (contract.get("schema") != "mastermind.hermes_owner_source_support.v1"
            or contract.get("owner_commit") != OWNER_COMMIT
            or set(contract.get("preimages", {})) != CHANGED
            or set(contract.get("postimages", {})) != CHANGED
            or contract.get("patch_sha256") != sha256(patch.read_bytes())
            or contract.get("source_only") is not True
            or contract.get("operational_enrollment") is not False):
        raise RuntimeError("Source support proposal contract changed")
    return raw_contract, contract, patch


def prepare(original, adapter, destination):
    original = Path(original).resolve(strict=True)
    adapter = Path(adapter).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.is_relative_to(original) or destination.is_relative_to(adapter):
        raise RuntimeError("Proposal fixture must be outside the source checkouts")
    if destination.exists():
        raise RuntimeError("Proposal fixture must be new")
    raw_contract, contract, patch = _support_contract(adapter)
    if git(original, "rev-parse", "HEAD").decode().strip() != OWNER_COMMIT:
        raise RuntimeError("Original Macro source is not the proposal parent")
    git(original, "diff", "--exit-code", "HEAD", "--")
    destination.mkdir()
    selected_tests = [path for path in TESTS if path not in CHANGED or contract["preimages"][path] is not None]
    materialization = export_committed(original, destination, OWNER_COMMIT,
        ("engine", "lib", "config", "tests/__init__.py", *selected_tests))
    before = inventory(destination)
    for path, expected in contract["preimages"].items():
        if before.get(path) != expected:
            raise RuntimeError("Proposal preimage mismatch: " + path)
    for path, expected in contract["unchanged_inputs"].items():
        raw = (destination / path).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw,
                            usedforsecurity=False).hexdigest()
        if blob != expected:
            raise RuntimeError("Unchanged owner input differs: " + path)
    git(destination, "apply", "--check", str(patch))
    git(destination, "apply", str(patch))
    after = inventory(destination)
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    if changed != CHANGED or any(after[path] != expected for path, expected in contract["postimages"].items()):
        raise RuntimeError("Proposal application changed an undeclared member")
    if git(original, "rev-parse", "HEAD").decode().strip() != OWNER_COMMIT:
        raise RuntimeError("Original source changed during fixture preparation")
    git(original, "diff", "--exit-code", "HEAD", "--")
    return {"original_owner_commit": OWNER_COMMIT,
        "contract_sha256": sha256(raw_contract), "patch_sha256": contract["patch_sha256"],
        "postimages": contract["postimages"], "fixture_files": len(after),
        "source_materialization": materialization,
        "original_source_unchanged": True, "runtime_enrollment": False}


def prepare_current(original, adapter, destination, *, composed=False):
    """Qualify committed support without applying the historical proposal again."""
    original = Path(original).resolve(strict=True)
    adapter = Path(adapter).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.is_relative_to(original) or destination.is_relative_to(adapter):
        raise RuntimeError("Current-source fixture must be outside the source checkouts")
    if destination.exists():
        raise RuntimeError("Current-source fixture must be new")
    raw_contract, contract, _ = _support_contract(adapter)
    owner_commit = CURRENT_OWNER_COMMIT
    if composed:
        path = adapter / "integrations/hermes_application_fabric/qualification/application_owner_support/attended-auto-current.json"
        raw_composed = path.read_bytes()
        current = json.loads(raw_composed)
        keys = {"schema", "owner_commit", "previous_owner_commit", "historical_contract_sha256",
                "postimages", "unchanged_inputs", "source_only", "operational_enrollment"}
        if (type(current) is not dict or set(current) != keys
                or current["schema"] != "mastermind.hermes_owner_committed_support.v1"
                or current["owner_commit"] != COMPOSED_OWNER_COMMIT
                or current["previous_owner_commit"] != CURRENT_OWNER_COMMIT
                or current["historical_contract_sha256"] != sha256(raw_contract)
                or type(current["postimages"]) is not dict or set(current["postimages"]) != CHANGED
                or any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
                       for value in current["postimages"].values())
                or current["unchanged_inputs"] != contract["unchanged_inputs"]
                or current["source_only"] is not True
                or current["operational_enrollment"] is not False):
            raise RuntimeError("Composed current-source contract changed")
        owner_commit = COMPOSED_OWNER_COMMIT
        contract = {**contract, "postimages": current["postimages"]}
        raw_contract = raw_composed
    if git(original, "rev-parse", "HEAD").decode().strip() != owner_commit:
        raise RuntimeError("Current Macro source differs from the qualified owner")
    git(original, "diff", "--exit-code", "HEAD", "--")
    destination.mkdir()
    materialization = export_committed(original, destination, owner_commit,
        ("engine", "lib", "config", "tests/__init__.py", *TESTS))
    after = inventory(destination)
    for path, expected in contract["postimages"].items():
        if after.get(path) != expected:
            raise RuntimeError("Committed support postimage differs: " + path)
    for path, expected in contract["unchanged_inputs"].items():
        raw = (destination / path).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw,
                            usedforsecurity=False).hexdigest()
        if blob != expected:
            raise RuntimeError("Unchanged owner input differs: " + path)
    if git(original, "rev-parse", "HEAD").decode().strip() != owner_commit:
        raise RuntimeError("Current source changed during fixture preparation")
    git(original, "diff", "--exit-code", "HEAD", "--")
    return {"owner_commit": owner_commit,
        "contract_sha256": sha256(raw_contract),
        "source_context": "committed_attended_auto" if composed else "committed_current",
        ("historical_patch_sha256" if composed else "accepted_patch_sha256"): contract["patch_sha256"],
        "patch_applied": False, "postimages": contract["postimages"],
        "fixture_files": len(after), "source_materialization": materialization,
        "original_source_unchanged": True, "runtime_enrollment": False}


def qualify_unit(fixture, interpreter):
    report = Path(fixture).parent / "source-support-tests.xml"
    if report.exists():
        raise RuntimeError("Unit report already exists")
    env = {**os.environ, "PYTHONPATH": str(fixture), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    subprocess.run([str(interpreter), "-B", "-m", "pytest", "--noconftest", "-c", "/dev/null",
        "-q", "--tb=short", "--junitxml=" + str(report), *TESTS], cwd=fixture,
        env=env, stdin=subprocess.DEVNULL, timeout=120, check=True)
    suites = list(ET.parse(report).getroot().iter("testsuite"))
    counts = {key: sum(int(suite.get(key, "0")) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    if counts["tests"] != 383 or any(counts[key] for key in ("failures", "errors", "skipped")):
        raise RuntimeError("Source support unit qualification is incomplete")
    return {**counts, "junit_sha256": sha256(report.read_bytes()), "live_acceptance": False}
