"""Exercise the composed native/support artifact without a provider or host lease.

The donor cases use inert fixtures. The publication seam runs a committed benign
fixture helper through the real owned-process runner and stops before a provider
call. It does not execute the production Macro helper or prove a real worker.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import test_fabric_clean_linked_donor_20261017 as donor_contract

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
PRE_PAID_MODEL_COMPOSED_SHA = "5f01655f9066d4cb5c9daf7260867efa839ef5526a83578d7ca11e3c0e681fef"
PAID_MODEL_PATCH = ROOT / "tests/fixtures/fabric-native-paid-model-20261022.patch"
PAID_MODEL_PATCH_SHA = "e0d937b9afdcc864592a7ba44a65ed121fa9c983f53de7109b1628e2141314f1"
# Prior paid-model endpoint: kept pinned as the preimage of the Grok forward
# delta; the historical transformation chain is never repinned.
PRE_GROK_COMPOSED_SHA = "c14ec82af144a3c47599d628ef614c033e4c3f04852953d8c3b3699c602e2ee7"
GROK_FORWARD_PATCH = ROOT / "tests/fixtures/fabric-native-grok-forward-20261023.patch"
GROK_FORWARD_PATCH_SHA = "d0ae2b5337f7235695316d4148f2e4764aa0c75af6a239257ed13c830269b736"
COMPOSED_SHA = "6be6830dcd9c00dc46cf613a610ad0dc574ca13f50aa1cd5fbffb7e65e1649c1"
PRE_PHYSICAL_ROOT_COMPOSED_SHA = "82057bbcca163bdd4399aaaa9d2ab61548eb1656276167c98f1da40b90d7a4dc"
PHYSICAL_ROOT_PATCH = ROOT / "tests/fixtures/fabric-native-physical-root-20261021.patch"
PHYSICAL_ROOT_PATCH_SHA = "5582372f4de471f534838c2ea2a2c3928b698318a2cdde4a27cc53367addc26c"
PRE_DEADLINE_COMPOSED_SHA = "8fc268d94c66227dac66c259343c137da8256d7b4545b4f77591ebc4eb66c43d"
DEADLINE_PATCH = ROOT / "tests/fixtures/fabric-native-commission-deadline-20261018.patch"
DEADLINE_PATCH_SHA = "bed370872724e52363b7fb361fbb92841e12f3fb8608830b9353eeac8cef7447"
QUOTA_SHA = "f5ec893143e5bf43c37cc1d98ff1b67c0b36d9cc8674d4bf0b12ab6da0f7a29c"
# The 97-file closure composes protected #1720/#1729 with Qwen source feedback
# and request UTC narrowing, extended by the reviewed Grok forward delta. This
# candidate pin is a changed-risk review input, not reuse of an earlier review.
# The Grok delta's source risk was independently reviewed at 3d864/25efd; this
# comment records that review and invents no fresh approval.
# Executor/donor/preimage pins stay exact.
EXPECTED_NATIVE_FILES = 97
NATIVE_MANIFEST_SHA = "c905243533cbf51f0cc5d442a42d5876b9f746ab29e2488b98ef5147c08cfd1b"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _composition(directory):
    before = donor_contract.PREIMAGE.read_bytes()
    assert _sha(before) == donor_contract.PREIMAGE_SHA256
    assert _sha(donor_contract.PATCH.read_bytes()) == donor_contract.PATCH_SHA256
    target = directory / "remote_sub_exec.py"
    target.write_bytes(before)
    donor_contract._git(directory, "apply", "--check", str(donor_contract.PATCH))
    donor_contract._git(directory, "apply", str(donor_contract.PATCH))
    security = target.read_bytes()
    assert _sha(security) == donor_contract.POSTIMAGE_SHA256
    line = b'    child_env["POOL_USAGE_RUN_ID"] = key\n'
    outcome = b'    child_env["POOL_OUTCOME_FILE"] = str(lanes_dir / f"{key}.provider.json")\n'
    assert before.count(line) == 1
    quota = before.replace(line, line + outcome)
    assert _sha(quota) == QUOTA_SHA
    # Preserve the exact independently reviewed security-prefix/quota-tail
    # composition before applying the one reviewed deadline transformation.
    boundary = b"def _execute("
    prior = security[:security.index(boundary)] + quota[quota.index(boundary):]
    assert _sha(prior) == PRE_DEADLINE_COMPOSED_SHA
    assert prior[:prior.index(boundary)] == security[:security.index(boundary)]
    assert prior[prior.index(boundary):] == quota[quota.index(boundary):]
    target.write_bytes(prior)
    assert _sha(DEADLINE_PATCH.read_bytes()) == DEADLINE_PATCH_SHA
    donor_contract._git(directory, "apply", "--check", str(DEADLINE_PATCH))
    donor_contract._git(directory, "apply", str(DEADLINE_PATCH))
    assert _sha(target.read_bytes()) == PRE_PHYSICAL_ROOT_COMPOSED_SHA
    # Extend the exact deadline-qualified executor with the independently
    # reviewed physical-root change; do not repin the historical transformations.
    assert _sha(PHYSICAL_ROOT_PATCH.read_bytes()) == PHYSICAL_ROOT_PATCH_SHA
    donor_contract._git(directory, "apply", "--check", str(PHYSICAL_ROOT_PATCH))
    donor_contract._git(directory, "apply", str(PHYSICAL_ROOT_PATCH))
    assert _sha(target.read_bytes()) == PRE_PAID_MODEL_COMPOSED_SHA
    assert _sha(PAID_MODEL_PATCH.read_bytes()) == PAID_MODEL_PATCH_SHA
    donor_contract._git(directory, "apply", "--check", str(PAID_MODEL_PATCH))
    donor_contract._git(directory, "apply", str(PAID_MODEL_PATCH))
    assert _sha(target.read_bytes()) == PRE_GROK_COMPOSED_SHA
    # Extend the exact paid-model executor with the independently reviewed Grok
    # forward change; do not repin the historical transformations.
    assert _sha(GROK_FORWARD_PATCH.read_bytes()) == GROK_FORWARD_PATCH_SHA
    donor_contract._git(directory, "apply", "--check", str(GROK_FORWARD_PATCH))
    donor_contract._git(directory, "apply", str(GROK_FORWARD_PATCH))
    composed = (NATIVE / "candidate/remote_sub_exec.py").read_bytes()
    assert _sha(composed) == COMPOSED_SHA
    assert target.read_bytes() == composed
    return composed


@pytest.fixture(scope="session")
def applied(tmp_path_factory):
    """Compile the actual composed controller for the unchanged donor cases."""
    source = _composition(tmp_path_factory.mktemp("composed-source-identity"))
    parsed = ast.parse(source)
    selected = []
    for node in parsed.body:
        if isinstance(node, ast.ClassDef) and node.name == "SparseWorkspaceRefused":
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and (
                node.name.startswith("_sparse_") or node.name in {
                    "_qualify_sparse_donor", "_clean_linked_sparse_donor", "_new_macro_workspace"}):
            selected.append(node)
        elif isinstance(node, ast.Assign) and all(
                isinstance(t, ast.Name) and t.id.startswith(("_MACRO_", "_SPARSE_"))
                for t in node.targets):
            selected.append(node)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "_new_macro_workspace"
               for n in selected)
    return compile(ast.Module(body=selected, type_ignores=[]),
                   str(NATIVE / "candidate/remote_sub_exec.py"), "exec")


# Reuse the behavioral assertions and their fixture inputs without changing the
# original standalone patch test. Pytest injects this module's composed fixture.
module = donor_contract.module
repository = donor_contract.repository
for _name, _case in vars(donor_contract).items():
    if _name.startswith("test_") and callable(_case):
        globals()[_name] = _case


@pytest.fixture(scope="session")
def native_stage(tmp_path_factory):
    output = tmp_path_factory.mktemp("composed-native-stage")
    result = subprocess.run(
        [sys.executable, str(NATIVE / "rollout/build_review_stage.py"), "--output", str(output)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected = (NATIVE / "rollout/native-manifest.json").read_bytes()
    assert _sha(expected) == NATIVE_MANIFEST_SHA
    assert (output / "native-manifest.json").read_bytes() == expected
    assert (output / "native-source-inventory.json").read_bytes() == (
        NATIVE / "rollout/native-source-inventory.json").read_bytes()
    manifest = json.loads(expected)
    assert len(manifest) == EXPECTED_NATIVE_FILES
    for name, digest in manifest.items():
        assert _sha((output / "native-code-stage" / name).read_bytes()) == digest
    assert manifest["ext/remote_sub_exec.py"] == COMPOSED_SHA
    return output


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _seam(stage, base):
    """Fresh-process fixture; every mutable owner is below the supplied base."""
    initial_home = os.environ.get("HOME")
    owner = _load("composition_native_owner", NATIVE / "rollout/native_generation.py")
    native_ext = base / "native-kit/ext"
    remote_ext = base / "remote-kit/ext"
    policy = json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {}}}}}) + "\n"
    for ext in (native_ext, remote_ext):
        ext.mkdir(parents=True, mode=0o700)
        (ext / "active").mkdir(mode=0o700)
        (ext / "lanes").mkdir(mode=0o700)
        (ext.parent / "orch/fabric").mkdir(parents=True, mode=0o700)
        (ext.parent / "orch/fabric/pools.yaml").write_text(policy)
    (remote_ext.parent / "support-releases").mkdir(mode=0o700)
    files = json.loads((stage / "native-manifest.json").read_bytes())
    assert len(files) == EXPECTED_NATIVE_FILES and files["ext/remote_sub_exec.py"] == COMPOSED_SHA
    generation = owner.publish(stage / "native-code-stage", native_ext, files)
    store = native_ext.parent / owner.STORE_NAME
    owner.select(store, generation.name, None)
    selection = owner.current(store)
    selected, descriptor = owner.verify(store, selection["generation"])
    assert selected == generation and descriptor["files"] == files
    native_here = selected / "ext"
    assert _sha((native_here / "support_bundle.py").read_bytes()) == files["ext/support_bundle.py"]
    support = _load("composition_support_owner", native_here / "support_bundle.py")
    names = support.SOURCE_FILES
    shell_names = set(re.search(r"SUPPORT_FILES=\(\n(.*?)\n\)",
                               (native_here / "remote_sub.sh").read_text(), re.S).group(1).split())
    assert names == shell_names and len(names) == 37
    manifest_path = base / "run.support-manifest.json"
    metadata = subprocess.run(
        [sys.executable, "-B", str(native_here / "remote_sub_helpers.py"),
         "support-meta", str(native_here), str(manifest_path), *sorted(names)],
        capture_output=True, text=True, timeout=20)
    assert metadata.returncode == 0, metadata.stderr
    support_digest, policy_digest = metadata.stdout.strip().split()
    manifest = json.loads(manifest_path.read_bytes())
    assert set(manifest) == names and policy_digest == _sha(policy.encode())
    transfer = base / "transfer"
    transfer.mkdir(mode=0o700)
    for name in names:
        source = selected / "orch/fabric/pools.yaml" if name == "pools.yaml" else native_here / name
        raw = source.read_bytes()
        assert _sha(raw) == manifest[name]
        (transfer / name).write_bytes(raw)
    shutil.copyfile(native_here / "support_bundle.py", transfer / "support_bundle.py")
    # The copied publisher uses the exact selected policy module, with no
    # candidate/source fallback on the subsequent executor import path.
    sys.path.insert(0, str(transfer))
    shipped_publisher = _load("composition_transferred_publisher", transfer / "support_bundle.py")
    published = shipped_publisher.publish(transfer, remote_ext, manifest)
    assert published.parent.name == support_digest
    assert shipped_publisher.publish(transfer, remote_ext, manifest) == published
    for name in names:
        assert _sha((published / name).read_bytes()) == manifest[name]
        assert (published / name).stat().st_mode & 0o777 == 0o555
    assert _sha((published / "remote_sub_exec.py").read_bytes()) == COMPOSED_SHA
    assert (published / "lanes").resolve() == remote_ext / "lanes"
    assert (published / "active").resolve() == remote_ext / "active"
    assert published.stat().st_mode & 0o777 == 0o555
    assert published.parent.stat().st_mode & 0o777 == 0o555
    sys.path.remove(str(transfer))
    sys.path.insert(0, str(published))
    import remote_sub_exec as remote
    import lane_runtime
    import native_remote
    for loaded in (remote, lane_runtime, native_remote):
        assert Path(loaded.__file__).parent == published
    actual_runner = lane_runtime.run_owned_process
    home = base / "donor-home"
    home.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as patcher:
        fixture = donor_contract.repository.__wrapped__(home, patcher, vars(remote))
        helper = b'''import subprocess, sys
from pathlib import Path
assert len(sys.argv) == 4 and sys.argv[1] == "fabric-mint"
key, head = sys.argv[2:]
assert key == "fixture-new-mint"
donor = Path.cwd()
destination = donor.parents[2] / "lanes/wt" / key
destination.parent.mkdir(parents=True, exist_ok=True)
def git(where, *args):
    subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(where), *args], check=True, timeout=20)
git(donor, "worktree", "add", "-q", "--no-checkout", "-b", "lane/" + key, str(destination), head)
git(destination, "sparse-checkout", "set", "--cone", ".claude", ".codex", "config", "scripts", "docs")
git(destination, "read-tree", "-mu", "HEAD")
print("benign fixture workspace ready")
'''
        (fixture.alternate / "scripts/worktree_sparse.py").write_bytes(helper)
        donor_contract._git(fixture.alternate, "add", "scripts/worktree_sparse.py")
        donor_contract._git(fixture.alternate, "commit", "-qm", "benign owned-process mint fixture")
        head = donor_contract._git(fixture.alternate, "rev-parse", "HEAD")
        remote._MACRO_FABRIC_SPARSE_BLOB = donor_contract._blob(helper)
        remote._MACRO_PINNED_DONOR_COMMIT = head
        patcher.setenv("FABRIC_NEW_MACRO_COMMIT", head)
        patcher.setenv("POOL_OUTCOME_FILE", str(base / "wrong-fixture-outcome.json"))
        patcher.setenv("REMOTE_SUB_CHILD_TIMEOUT", "30")
        patcher.setenv("LANE_MAX_ACTIVE", "1")
        patcher.setenv("LANE_MAX_LOAD_RATIO", "1.5")
        patcher.setenv("LANE_NICE", "10")
        for name in ("FABRIC_OPERATOR_CAPSULE", "FABRIC_OPERATOR_CAPABILITY",
                     "FABRIC_CPU_SCOPE_QUOTA_PCT", "POOL_CAPACITY_PREFLIGHT"):
            patcher.delenv(name, raising=False)
        class FixtureLease:
            def __init__(self):
                self.holds, self.acquired, self.exited = [], [], False
            def acquire(self, *args, **kwargs):
                self.acquired.append((args, kwargs))
                return self
            def hold_for_reconciliation(self, reason):
                self.holds.append(reason)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.exited = True
            def release(self):
                pass
        lease = FixtureLease()
        patcher.setattr(remote, "LaneLease", lease)
        class ProviderBoundary(BaseException):
            pass
        calls = []
        mint_results = []
        def dispatch(argv, **kwargs):
            calls.append((argv, kwargs))
            if kwargs["label"] == fixture.key + ":workspace-mint":
                result = actual_runner(argv, **kwargs)
                mint_results.append(result)
                return result
            assert kwargs["label"] == fixture.key
            raise ProviderBoundary()
        patcher.setattr(remote, "run_owned_process", dispatch)
        packet = base / "inert.packet"
        packet.write_text("offline composition fixture; no provider may run\n")
        state = {"started": False}
        try:
            remote._execute([str(published / "remote_sub_exec.py"), fixture.key,
                             "glm", str(packet), str(fixture.original), "glm-5.3"], state)
        except ProviderBoundary:
            pass
        else:
            detail = [(r.returncode, r.cleanup_proven, r.stdout, r.stderr) for r in mint_results]
            raise AssertionError(("composed executor did not reach captured provider boundary", detail))
        assert len(calls) == 2 and len(mint_results) == 1
        mint, provider = calls
        assert mint[0] == [sys.executable, "-I", str(fixture.alternate / "scripts/worktree_sparse.py"),
                           "fabric-mint", fixture.key, head]
        assert mint_results[0].returncode == 0 and mint_results[0].cleanup_proven
        outcome = published / "lanes" / (fixture.key + ".provider.json")
        identity = ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_LEASE_ID",
                    "POOL_ACCOUNT", "REMOTE_SUB_RUN_ID")
        for _, options in calls:
            assert options["env"]["POOL_OUTCOME_FILE"] == str(outcome)
            for name in identity:
                assert options["env"][name] == os.environ[name]
        assert outcome.parent.resolve() == remote_ext / "lanes"
        target = home / "lanes/wt" / fixture.key
        assert provider[1]["cwd"] == str(target) and str(target) in provider[0]
        assert donor_contract._git(target, "rev-parse", "HEAD") == head
        assert donor_contract._git(target, "branch", "--show-current") == "lane/" + fixture.key
        assert donor_contract._git(target, "status", "--porcelain=v1", "-uall") == ""
        assert (target / "docs/keep.txt").is_file() and not (target / "data").exists()
        provider_env = provider[1]["env"]
        assert provider_env["FABRIC_WORKSPACE_READY"] == "1"
        assert provider_env["FABRIC_WORKSPACE_RUN_ID"] == fixture.key
        assert "FABRIC_NEW_MACRO_COMMIT" not in provider_env
        assert "MASTERMIND_FABRIC_SPARSE_NEW" not in provider_env
        receipt = remote_ext / "lanes" / (fixture.key + ".workspace-mint.process.jsonl")
        row = json.loads(receipt.read_text().splitlines()[-1])
        assert row["label"] == fixture.key + ":workspace-mint"
        assert lane_runtime.cleanup_receipt_is_proven(row["cleanup"])
        assert not outcome.exists()
        assert not (remote_ext / "lanes" / (fixture.key + ".process.jsonl")).exists()
        assert lease.exited and lease.holds == ["worker_cleanup_unproven"]
        assert (fixture.original / "preserve.txt").read_text() == "ORIGINAL UNCOMMITTED WORK\n"
        assert os.environ.get("HOME") == initial_home
    return {"status": "OFFLINE_COMPOSITION_SEAM_PASS", "native_files": len(files),
            "support_files": 37, "executor_sha256": COMPOSED_SHA,
            "fixture_native_digest": generation.name, "fixture_support_digest": support_digest,
            "mint_receipt_sha256": _sha(receipt.read_bytes()), "provider_started": False,
            "production_macro_helper_tested": False, "physical_lease_acquired": False}


def test_selected_native_support_executor_preserves_mint_and_outcome_binding(native_stage, tmp_path):
    result = subprocess.run([sys.executable, str(Path(__file__)), "--composition-seam",
                             str(native_stage), str(tmp_path)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["status"] == "OFFLINE_COMPOSITION_SEAM_PASS"
    assert proof["executor_sha256"] == COMPOSED_SHA
    assert proof["native_files"] == EXPECTED_NATIVE_FILES and proof["support_files"] == 37
    assert proof["provider_started"] is False
    assert proof["physical_lease_acquired"] is False
    assert proof["production_macro_helper_tested"] is False
    (tmp_path / "composition-seam-proof.json").write_text(json.dumps(proof, sort_keys=True) + "\n")


if __name__ == "__main__":
    assert len(sys.argv) == 4 and sys.argv[1] == "--composition-seam"
    stage, base = Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    try:
        print(json.dumps(_seam(stage, base), sort_keys=True))
    finally:
        # Only this disposable fixture's directories; never follow state links.
        for walked, _, _ in os.walk(base, followlinks=False):
            os.chmod(walked, 0o700)
