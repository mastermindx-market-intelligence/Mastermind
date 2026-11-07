"""Isolated release-entry import ordering with explicit custody/effect doubles.

The child interpreter, stdlib-only structural validation, actual release entry,
held first-party importer and semantic publication validator are real. The
Linux held-descriptor/root-identity facts and effect boundaries are doubles.
"""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.hermes_runtime.tests.test_native_meta_enrollment import installation

ROOT = Path(__file__).resolve().parents[1]

ISOLATED = r"""
import json, os, pathlib, runpy, sys, types
payload = json.load(sys.stdin)
source_root = pathlib.Path(payload["source"])
loaded = runpy.run_path(str(source_root / "ops/executive_os/release_manifest.py"),
                        run_name="mastermind_release_bootstrap_fixture")
ns = loaded["_hermes_runtime"].__globals__
document = payload["document"]
first_party = ns["_FIRST_PARTY"]
def preloaded():
    return sorted(name for name in sys.modules
                  if any(name == root or name.startswith(root + ".") for root in first_party))
assert not preloaded(), preloaded()
staged = ns["validate_hermes_runtime_installation"](document, _defer_consumer=True)
assert not preloaded(), preloaded()
if payload["case"] == "vendor_shadow":
    assert "dataclasses" not in sys.modules and "asyncio" not in sys.modules
entries = {}
for root_name in first_party:
    base = source_root / root_name
    entries[root_name] = {"type": "directory"}
    for path in base.rglob("*.py"):
        relative = path.relative_to(source_root)
        entries[relative.as_posix()] = {"type": "file"}
        for directory in relative.parents:
            if directory.as_posix() != ".":
                entries[directory.as_posix()] = {"type": "directory"}
state = {"reads": [], "changed": False, "closed": False}
sha = "a" * 40
tree = "b" * 40
release_parent = pathlib.Path("/tmp/mastermind-c57-isolated-release")
release_root = release_parent / sha

class Owner:
    def __init__(self, root):
        assert root == release_root
        self.root = root
        self.entries = entries
        self.hermes_runtime = ns["validate_hermes_runtime_installation"](
            document, _defer_consumer=True)
    def check(self):
        if state["changed"]:
            raise RuntimeError("C57_HELD_SOURCE_CHANGED")
    def source(self, relative):
        self.check()
        state["reads"].append(relative)
        if relative == "integrations/hermes_harness/native_executive_consumer.py" and payload["case"] == "source_drift":
            state["changed"] = True
        if relative == "ops/executive_os/native_gateway_sources.py":
            if payload["case"] == "derived_prepare":
                return b'prepared = False\ndef prepare_vendor_derivation(owner, recipe, acl):\n    global prepared\n    assert recipe["vendor_derivation"]["kind"] == "computer_env_guard"\n    prepared = True\ndef prepare_inventory(owner, recipe, acl):\n    assert prepared\n    raise RuntimeError("DERIVATION_BEFORE_INVENTORY")\n'
            return b'class NativeSourceClosure:\n    def __init__(self, *args, **kwargs):\n        raise RuntimeError("C57_QUALIFIED_BEFORE_EFFECT")\ndef prepare_vendor_derivation(owner, recipe, acl):\n    assert recipe["vendor_derivation"]["kind"] == "diagnostic_privacy"\ndef prepare_inventory(*args, **kwargs):\n    raise RuntimeError("C57_QUALIFIED_BEFORE_EFFECT")\n'
        return (source_root / relative).read_bytes()
    def directory(self, relative):
        assert entries[relative]["type"] == "directory"
        self.check()
    def read(self, path, maximum):
        assert path == self.root / ns["MANIFEST_NAME"]
        self.check()
        return json.dumps({"tree_sha": tree}).encode()
    def hermes_runtime_input(self, *, _defer_consumer=False):
        self.check()
        return ns["validate_hermes_runtime_installation"](
            self.hermes_runtime, _defer_consumer=_defer_consumer)
    def close(self):
        state["closed"] = True

role_row = next(row for row in document["roles"] if "native_gateway" in row)
class OsIdentity:
    def __getattr__(self, name):
        return getattr(os, name)
    def getuid(self):
        return 0 if payload["mode"] == "prepare" else role_row["uid"]
    geteuid = getuid
    def getgid(self):
        return 0 if payload["mode"] == "prepare" else role_row["gid"]
    getegid = getgid

ns["os"] = OsIdentity()
ns["__file__"] = str(release_root / "ops/executive_os/release_manifest.py")
ns["_LINUX_RELEASES"] = release_parent
ns["_HeldReleaseSources"] = Owner
ns["_HERMES_EARLY_NO_SITE"] = True
ns["_hermes_recipe_is_qualified"] = lambda: True
for name in ns["_HERMES_SITE_NAMES"]:
    sys.modules[name] = None
try:
    if payload["mode"] == "prepare":
        ns["_prepare_hermes_dependencies"]([
            "--root", str(release_root), "--commit-sha", sha, "--tree-sha", tree,
            "--hermes-runtime-json", json.dumps(document)])
    else:
        command = "enroll-meta-session" if role_row["role"] == "mmmeta" else "enroll-secretary-session"
        ns["_hermes_runtime"]([command])
    outcome = "UNEXPECTED_EFFECT_RETURN"
except Exception as error:
    outcome = type(error).__name__ + ":" + str(error)
print(json.dumps({"outcome": outcome, "closed": state["closed"],
                  "consumer_loaded": "integrations/hermes_harness/native_executive_consumer.py" in state["reads"],
                  "effect_boundary_loaded": "ops/executive_os/native_gateway_sources.py" in state["reads"],
                  "first_party_after": preloaded()}))
"""


def run_isolated(document, *, mode="runtime", case="valid"):
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", ISOLATED],
        input=json.dumps({"source": str(ROOT), "document": document, "mode": mode, "case": case}),
        text=True, capture_output=True, timeout=30, cwd=ROOT.parent)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("mode", ["runtime", "prepare"])
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
@pytest.mark.parametrize("version", [1, 2, 3])
def test_isolated_entry_qualifies_through_held_source_before_effect(mode, role, version):
    document = installation(role, consumer=version == 3)
    row = next(item for item in document["roles"] if item["role"] == role)
    if version == 1:
        row["native_gateway"]["schema"] = "mastermind.hermes_native_gateway_installation/v1"
        row["native_gateway"].pop("session_enrollment")
    result = run_isolated(document, mode=mode)
    assert result["outcome"] == "RuntimeError:C57_QUALIFIED_BEFORE_EFFECT"
    assert result["closed"] and result["effect_boundary_loaded"]
    assert result["consumer_loaded"] is (version == 3)
    assert result["first_party_after"] == []


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_held_root_recipe_prepares_selected_derivation_before_inventory(role):
    document = installation(role)
    recipe = next(item["native_gateway"] for item in document["roles"] if item["role"] == role)
    recipe["vendor_derivation"] = {
        "kind": "computer_env_guard", "base_sha": "1c0cd667746d3395fe9e1b6c74f8f85952486f18",
        "patch_sha256": "d17af87e60a1f92a52ef446ad393ce2841c876a28e2ae0580bc7e6db09d6721f",
        "source_root": "/opt/hermes/pristine-source"}
    result = run_isolated(document, mode="prepare", case="derived_prepare")
    assert result["outcome"] == "RuntimeError:DERIVATION_BEFORE_INVENTORY"
    assert result["consumer_loaded"] and result["effect_boundary_loaded"] and result["closed"]
    assert result["first_party_after"] == []


@pytest.mark.parametrize("mode", ["runtime", "prepare"])
@pytest.mark.parametrize("case", ["foreign_role", "foreign_request", "malformed", "source_drift"])
def test_opaque_or_changed_input_never_reaches_effect_boundary(mode, case):
    document = installation("mmmeta")
    recipe = document["roles"][0]["native_gateway"]
    if case == "foreign_role":
        recipe["executive_consumer"]["session"]["role"] = "mmsecretary"
    elif case == "foreign_request":
        recipe["executive_consumer"]["session"]["request_id"] = "foreign-request"
    elif case == "malformed":
        recipe["executive_consumer"] = {"unqualified": True}
    result = run_isolated(document, mode=mode, case=case)
    assert result["closed"] and result["consumer_loaded"]
    assert not result["effect_boundary_loaded"]
    assert "C57_QUALIFIED_BEFORE_EFFECT" not in result["outcome"]
    assert result["first_party_after"] == []

@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_unqualified_vendor_cannot_supply_semantic_validator_imports(tmp_path, role):
    document = installation(role)
    recipe = next(row["native_gateway"] for row in document["roles"] if row["role"] == role)
    shadow = tmp_path / "unqualified-vendor"
    shadow.mkdir()
    marker = tmp_path / "vendor-imported"
    for module in ("dataclasses", "asyncio"):
        (shadow / (module + ".py")).write_text(
            "from pathlib import Path\n"
            + "Path(" + repr(str(marker)) + ").write_text('executed')\n"
            + "raise RuntimeError('C57_UNQUALIFIED_VENDOR_IMPORT')\n",
            encoding="utf-8")
    recipe["vendor_root"] = str(shadow)
    recipe["import_roots"][0] = str(shadow)
    result = run_isolated(document, case="vendor_shadow")
    assert not marker.exists()
    assert result["outcome"] == "RuntimeError:C57_QUALIFIED_BEFORE_EFFECT"
    assert result["consumer_loaded"] and result["effect_boundary_loaded"]
    assert result["closed"] and result["first_party_after"] == []
