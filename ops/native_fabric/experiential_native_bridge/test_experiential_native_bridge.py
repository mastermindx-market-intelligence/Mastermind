#!/usr/bin/env python3
"""Hermetic tests for the Experiential Labs native bridge composition + hook.

Everything runs in disposable temp directories: the pinned release tree is
never mutated, no worker starts, no provider is contacted, and the only
"POST" is a mock transport recording into a sandbox file. The mock sandbox
implements the SAME typed contract as the owner modules (experiential53
pin/transport/host-context accessors, PRs #2031/#2035) without importing or
weakening them.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent


def _find_repo_root() -> Path:
    """Walk up to the checkout containing the pinned release tree (works both
    beside the release and from a staging directory with a repo/ clone)."""
    probe = MODULE_DIR
    for _ in range(8):
        for candidate in (probe, probe / "repo"):
            if (candidate / "ops" / "native_fabric" / "quota_continuity" / "source").is_dir():
                return candidate
        probe = probe.parent
    raise RuntimeError("pinned release tree not found above the module directory")


REPO_ROOT = _find_repo_root()
RELEASE_ROOT = REPO_ROOT / "ops" / "native_fabric" / "quota_continuity" / "source"
COMPOSER = MODULE_DIR / "compose_overlay.py"
MANIFEST = MODULE_DIR / "release_manifest.json"
PATCH_DIR = MODULE_DIR / "overlay_patches"
BRIDGE_SOURCE = MODULE_DIR / "experiential_bridge.py"

RUN_ID = "explabsbridgeprobe20261103"
ROOT_ID = "explabsbridgeroot20261103"
ALL_CONSENTS = [
    "--experiential-retention-acknowledged",
    "--experiential-sensitive-data-opt-in",
    "--experiential-proprietary-code",
    "--experiential-code-exposure-opt-in",
]
CONSENT_KWARGS = dict(
    retention_acknowledged=True, sensitive_data_opt_in=True,
    proprietary_code=True, code_exposure_opt_in=True, strict_manual_pin=True,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bridge(root: Path, name: str = "experiential_bridge_under_test"):
    """Import a PRIVATE copy of the bridge from the sandbox (isolates guards)."""
    bridge_copy = root / "experiential_bridge.py"
    if not bridge_copy.exists():
        shutil.copyfile(BRIDGE_SOURCE, bridge_copy)
        bridge_copy.chmod(0o600)
    spec = importlib.util.spec_from_file_location(name, str(bridge_copy))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Mock host adapter sandbox (same typed contract as the owner modules).
# --------------------------------------------------------------------------

MOCK_PIN_TEMPLATE = textwrap.dedent("""
    import json
    from pathlib import Path
    HERE = Path(__file__).resolve().parent
    POOL = "experiential"
    MODEL = "glm-5.3-uncensored"
    TRANSPORT_INSTALLED = {transport_installed}
    ALLOWED_TASK_CLASSES = frozenset({allowed})
    FORBIDDEN_TASK_CLASSES = frozenset({forbidden})

    class ExperientialPinRefused(RuntimeError):
        def __init__(self, reason, detail=""):
            super().__init__(reason + (": " + detail if detail else ""))
            self.reason = reason
            self.detail = detail

    def preview(run_id, task_class, pool=None, model=None, **kwargs):
        if pool != POOL or model != MODEL:
            raise ExperientialPinRefused("EXPERIENTIAL_MODEL_SLUG_REFUSED", "strict manual pin")
        cls = str(task_class or "").strip().lower()
        if cls in FORBIDDEN_TASK_CLASSES:
            raise ExperientialPinRefused("EXPERIENTIAL_TASK_CLASS_FORBIDDEN", cls)
        if cls not in ALLOWED_TASK_CLASSES:
            raise ExperientialPinRefused("EXPERIENTIAL_TASK_CLASS_NOT_ADMITTED", cls)
        return {{"state": "PREVIEW_ONLY", "pool": POOL, "model": MODEL,
                 "task_class": cls, "reserved": False, "reason": "mock_pin"}}

    def admit_execution(*, pool, model, task_class, registry_entry=None,
                        entitlement=None, retention_acknowledged=False,
                        sensitive_data_opt_in=False, proprietary_code=False,
                        code_exposure_opt_in=False, account=None,
                        quota_readback=None):
        cls = str(task_class or "").strip().lower()
        if cls in FORBIDDEN_TASK_CLASSES:
            raise ExperientialPinRefused("EXPERIENTIAL_TASK_CLASS_FORBIDDEN", cls)
        if cls not in ALLOWED_TASK_CLASSES:
            raise ExperientialPinRefused("EXPERIENTIAL_TASK_CLASS_NOT_ADMITTED", cls)
        if not isinstance(registry_entry, dict) or registry_entry.get("enabled") is not True:
            raise ExperientialPinRefused("PROVIDER_DISABLED")
        if not isinstance(entitlement, dict) or entitlement.get("verified") is not True:
            raise ExperientialPinRefused("ENTITLEMENT_UNVERIFIED")
        if retention_acknowledged is not True:
            raise ExperientialPinRefused("RETENTION_UNVERIFIED", "provider retains prompt/response")
        if sensitive_data_opt_in is not True:
            raise ExperientialPinRefused("SENSITIVE_DATA_DISCLOSURE_REQUIRED")
        if proprietary_code is True and code_exposure_opt_in is not True:
            raise ExperientialPinRefused("PROPRIETARY_CODE_EXPOSURE_REFUSED")
        name = str(account or "").strip().lower()
        if not name:
            raise ExperientialPinRefused("ACCOUNT_UNRESOLVED")
        if name in {{"a", "account-a", "account_a"}}:
            raise ExperientialPinRefused("ACCOUNT_A_HELD_HTTP403", "original denial stands; never retried or bypassed")
        if name not in {{"b", "account-b", "account_b"}}:
            raise ExperientialPinRefused("ACCOUNT_UNKNOWN")
        if quota_readback != "authenticated":
            raise ExperientialPinRefused("QUOTA_READBACK_UNAUTHENTICATED",
                                         "unknown quota is not capacity")
        if TRANSPORT_INSTALLED is not True:
            raise ExperientialPinRefused("EXPERIENTIAL_TRANSPORT_NOT_INSTALLED")
        return {{"state": "ADMITTED", "pool": pool, "model": model,
                 "task_class": cls, "escalate_to": None, "fallback": None}}
""")

MOCK_TRANSPORT_TEMPLATE = textwrap.dedent("""
    import hashlib, json
    from pathlib import Path
    HERE = Path(__file__).resolve().parent
    ROUTE_QUALIFIED = {route_qualified}

    class ExperientialTransportRefused(RuntimeError):
        def __init__(self, reason, detail=""):
            super().__init__(reason + (": " + detail if detail else ""))
            self.reason = reason
            self.detail = detail

    def require_route_qualified():
        if ROUTE_QUALIFIED is not True:
            raise ExperientialTransportRefused("EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED",
                                               "mock transport route unattested")

    def run_opt_in_inference(*, run_id, packet_root, task_class, pool, model,
                             registry_entry, entitlement, retention_acknowledged,
                             sensitive_data_opt_in, proprietary_code,
                             code_exposure_opt_in, account, quota_readback,
                             route, prompt, limits=None, **kwargs):
        require_route_qualified()
        calls = HERE / "post_calls.json"
        records = json.loads(calls.read_text()) if calls.exists() else []
        records.append({{
            "run_id": run_id, "packet_root": packet_root,
            "task_class": task_class, "pool": pool, "model": model,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "route": route, "account": account, "quota_readback": quota_readback,
        }})
        calls.write_text(json.dumps(records))
        return {{"state": "EXECUTED", "status": 200, "run_id": run_id,
                 "output": "mock completion", "posts": len(records)}}
""")

MOCK_CONTEXT_SOURCE = textwrap.dedent("""
    import json
    from pathlib import Path
    HERE = Path(__file__).resolve().parent

    def host_owned_context():
        return json.loads((HERE / "host_context.json").read_text())
""")


def write_mock_adapter(root: Path, *, transport_installed=True, route_qualified=True,
                       registry_enabled=True, entitlement_verified=True,
                       quota_readback="authenticated", account="b",
                       allowed=frozenset({"fix_build", "mechanical", "executor"}),
                       forbidden=frozenset({"review", "architecture", "high_level"})):
    exp = root / "experiential53"
    exp.mkdir(parents=True, exist_ok=True)
    context = {
        "registry_entry": {"enabled": bool(registry_enabled)},
        "entitlement": {"verified": bool(entitlement_verified)},
        "account": account,
        "quota_readback": quota_readback,
        "route_host": "ubuntu1",
        "route": {"host": "127.0.0.1", "port": 8321, "path": "/v1/chat/completions"},
    }
    (exp / "host_context.json").write_text(json.dumps(context, indent=2) + "\n")
    (exp / "experiential_pin.py").write_text(MOCK_PIN_TEMPLATE.format(
        transport_installed=transport_installed, allowed=sorted(allowed),
        forbidden=sorted(forbidden)))
    (exp / "experiential_transport.py").write_text(MOCK_TRANSPORT_TEMPLATE.format(
        route_qualified=route_qualified))
    (exp / "experiential_host_context.py").write_text(MOCK_CONTEXT_SOURCE)
    for path in exp.iterdir():
        path.chmod(0o600)
    return exp


def sandbox_with_bridge(tmp_path: Path, _no_adapter: bool = False, **adapter_kwargs):
    """Overlay-shaped sandbox: bridge beside runtime root + mock adapter.
    ``_no_adapter=True`` installs no adapter (missing-adapter cases)."""
    shutil.copyfile(BRIDGE_SOURCE, tmp_path / "experiential_bridge.py")
    (tmp_path / "experiential_bridge.py").chmod(0o600)
    if not _no_adapter:
        write_mock_adapter(tmp_path, **adapter_kwargs)
    return load_bridge(tmp_path)


# --------------------------------------------------------------------------
# Composition (against the real pinned release).
# --------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def fixed_release_source(tmp_path_factory):
    """Reconstruct the original sealed 75-file parent from exact verified bytes.

    The working source also contains later preimages and a Go shim. They are
    not members of this historical release. Do not change its manifest seal
    or teach the production composer to ignore extra files.
    """
    global RELEASE_ROOT
    current = RELEASE_ROOT
    manifest = json.loads(MANIFEST.read_text())
    files = json.loads((MODULE_DIR / "fixtures" /
                       "legacy-release-source-9bbd4ca7.sha256.json").read_text())
    assert len(files) == manifest["release_tree_file_count"] == 75
    binding = hashlib.sha256(
        "".join(f"{name}:{files[name]}\n" for name in sorted(files)).encode()).hexdigest()
    assert binding == manifest["release_tree_manifest_sha256"]
    tree = tmp_path_factory.mktemp("sealed_legacy_release") / "source"
    tree.mkdir()
    for name, digest in files.items():
        assert Path(name).name == name and name not in {".", ".."}
        raw = (current / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, name
        (tree / name).write_bytes(raw)
        (tree / name).chmod((current / name).stat().st_mode & 0o777)
    RELEASE_ROOT = tree
    try:
        yield tree
    finally:
        RELEASE_ROOT = current


@pytest.fixture(scope="session")
def composed_overlay(tmp_path_factory, fixed_release_source):
    """Compose from a content-CAS-verified plain copy of the pinned release.

    The copy is bound to the shipped manifest's tree digest and preimages, so
    the composition still qualifies the EXACT pinned bytes while remaining
    independent of the working checkout's git head (the composer's stale-head
    law refuses a moved checkout; the refusal tests cover that gate).
    """
    base = tmp_path_factory.mktemp("overlay_out")
    tree = base / "release_copy" / "source"
    tree.parent.mkdir()
    shutil.copytree(RELEASE_ROOT, tree)
    for path in tree.rglob("*"):
        if path.is_dir() and path.name == ".git":
            shutil.rmtree(path)
    out = base / "ov"
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(tree),
         "--output", str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, f"composer refused: {proc.stderr}"
    return out


def run_overlay(overlay: Path, *argv: str):
    return subprocess.run(
        [sys.executable, str(overlay / "fabric_task.py"), *argv],
        capture_output=True, text=True, cwd=str(overlay))


def test_release_tree_is_pristine_and_bound():
    """The shipped manifest binds the exact pinned release; nothing drifted."""
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["expected_release_head_sha1"] == "9bbd4ca7f6d8859f28accf76e11d534478dc80e3"
    digests = {p.name: sha(p) for p in RELEASE_ROOT.iterdir() if p.is_file()}
    binding = hashlib.sha256(
        "".join(f"{n}:{digests[n]}\n" for n in sorted(digests)).encode()).hexdigest()
    assert binding == manifest["release_tree_manifest_sha256"]
    for name, digest in manifest["preimages_sha256"].items():
        assert digests[name] == digest, name
    # The bridge is NOT part of the protected release tree.
    assert not (RELEASE_ROOT / "experiential_bridge.py").exists()


def test_manifest_binds_exactly_the_four_runtime_files():
    manifest = json.loads(MANIFEST.read_text())
    assert set(manifest["preimages_sha256"]) == {
        "fabric_task.py", "remote_sub.sh", "sub.sh", "slot.py"}
    assert set(manifest["postimages_sha256"]) == set(manifest["preimages_sha256"])
    assert len(manifest["patches_sha256"]) == 4
    for name, digest in manifest["patches_sha256"].items():
        assert sha(PATCH_DIR / name) == digest, name


def test_compose_emits_disposable_overlay_with_receipt(composed_overlay):
    receipt = json.loads((composed_overlay / "OVERLAY_MANIFEST.json").read_text())
    assert receipt["status"] == "source_candidate_not_installed"
    assert receipt["admission_granted"] is False
    assert receipt["worker_started"] is False
    assert receipt["dry_run"] is True
    assert receipt["release_head_status"] == "not_a_git_checkout"
    for name, digest in receipt["postimages_sha256"].items():
        assert sha(composed_overlay / name) == digest, name
    assert sha(composed_overlay / "experiential_bridge.py") == \
        receipt["bridge"]["experiential_bridge.py"]


def test_compose_head_gate_names_the_moved_head(tmp_path):
    """A git checkout whose head differs from the manifest head refuses,
    even with byte-identical content — a moved checkout re-qualifies."""
    tree = tmp_path / "checkout" / "source"
    tree.parent.mkdir(parents=True)
    shutil.copytree(RELEASE_ROOT, tree)
    manifest = json.loads(MANIFEST.read_text())
    git = lambda *args: subprocess.run(
        ["git", "-C", str(tree.parent), "-c", "user.email=t@t",
         "-c", "user.name=t", *args], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", str(tree.parent)], check=True)
    git("add", "-A")
    git("commit", "-qm", "identical content, unrelated head")
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(tree),
         "--output", str(tmp_path / "ov"), "--manifest", str(MANIFEST),
         "--patch-dir", str(PATCH_DIR)],
        capture_output=True, text=True)
    assert proc.returncode == 78
    assert "STALE_RELEASE_HEAD_REFUSED" in proc.stderr
    assert manifest["expected_release_head_sha1"][:12] in proc.stderr


def test_compose_verify_only_writes_nothing(tmp_path):
    tree = tmp_path / "source"
    shutil.copytree(RELEASE_ROOT, tree)
    out = tmp_path / "never_created"
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(tree),
         "--output", str(out), "--verify-only"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert not out.exists()


def test_compose_refuses_tampered_release(tmp_path):
    tree = tmp_path / "source"
    shutil.copytree(RELEASE_ROOT, tree)
    target = tree / "pick.py"
    target.write_bytes(target.read_bytes() + b"\n# tampered\n")
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(tree),
         "--output", str(tmp_path / "ov"), "--manifest", str(MANIFEST),
         "--patch-dir", str(PATCH_DIR)],
        capture_output=True, text=True)
    assert proc.returncode == 78
    assert "RELEASE_TREE_MISMATCH" in proc.stderr


def test_compose_refuses_stale_head_even_when_content_matches(tmp_path):
    tree = tmp_path / "source"
    shutil.copytree(RELEASE_ROOT, tree)
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    subprocess.run(["git", "-C", str(tree), "-c", "user.email=t@t", "-c",
                    "user.name=t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tree), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "unrelated head"], check=True)
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(tree),
         "--output", str(tmp_path / "ov"), "--manifest", str(MANIFEST),
         "--patch-dir", str(PATCH_DIR)],
        capture_output=True, text=True)
    assert proc.returncode == 78
    assert "STALE_RELEASE_HEAD_REFUSED" in proc.stderr


def test_compose_refuses_tampered_patch(tmp_path):
    patches = tmp_path / "overlay_patches"
    shutil.copytree(PATCH_DIR, patches)
    victim = next(patches.glob("*_slot_*.patch"))
    victim.write_bytes(victim.read_bytes() + b"# extra\n")
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(RELEASE_ROOT),
         "--output", str(tmp_path / "ov"), "--manifest", str(MANIFEST),
         "--patch-dir", str(patches)],
        capture_output=True, text=True)
    assert proc.returncode == 78
    assert "PATCH_DIGEST_MISMATCH" in proc.stderr


def _qualified_owner_source_fixture(tmp_path):
    owner = tmp_path / "owner_modules"
    owner.mkdir()
    for name, data in {
        "experiential_pin.py": b"POOL = 'experiential'\nMODEL = 'glm-5.3-uncensored'\n",
        "experiential_transport.py": (
            b"from dataclasses import dataclass\n"
            b"@dataclass(frozen=True)\n"
            b"class GatewayRoute:\n"
            b"    route_id: str\n"
        ),
    }.items():
        (owner / name).write_bytes(data)
    manifest = json.loads(MANIFEST.read_text())
    manifest["owner_modules_sha256"] = {
        name: sha(owner / name) for name in (
            "experiential_pin.py", "experiential_transport.py")
    }
    manifest_file = tmp_path / "owner_manifest.json"
    manifest_file.write_text(json.dumps(manifest))
    source = tmp_path / "release_copy" / "source"
    source.parent.mkdir()
    shutil.copytree(RELEASE_ROOT, source)
    return owner, manifest_file, source


def _compose_with_owner_modules(tmp_path, *, verify_only=False):
    owner, manifest, source = _qualified_owner_source_fixture(tmp_path)
    out = tmp_path / "candidate"
    args = [sys.executable, str(COMPOSER), "--release-root", str(source),
            "--output", str(out), "--manifest", str(manifest),
            "--owner-modules-root", str(owner)]
    if verify_only:
        args.append("--verify-only")
    return owner, out, args


def test_source_owner_modules_are_staged_with_exact_digest_only(tmp_path):
    owner, out, args = _compose_with_owner_modules(tmp_path)
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    receipt = json.loads((out / "OVERLAY_MANIFEST.json").read_text())
    assert receipt["owner_modules"] == {
        name: sha(owner / name) for name in (
            "experiential_pin.py", "experiential_transport.py")
    }
    for name in receipt["owner_modules"]:
        assert (out / "experiential53" / name).read_bytes() == (owner / name).read_bytes()
    assert receipt["host_context_owner_required"] is True
    assert not (out / "experiential53" / "experiential_host_context.py").exists()
    assert receipt["admission_granted"] is False
    assert receipt["worker_started"] is False


def test_staged_owner_transport_with_dataclass_is_loadable(tmp_path):
    owner, out, args = _compose_with_owner_modules(tmp_path)
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    bridge = load_bridge(out)
    adapter = bridge.resolve_host_adapter(out)
    assert adapter.pin is not None
    assert adapter.transport is not None, "owner transport dataclass must load"
    assert hasattr(adapter.transport, "GatewayRoute")
    assert adapter.transport.GatewayRoute(route_id="sealed").route_id == "sealed"
    assert adapter.context is None, "no synthetic host entitlement or cap"


def test_owner_modules_verify_only_writes_no_overlay(tmp_path):
    _owner, out, args = _compose_with_owner_modules(tmp_path, verify_only=True)
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["owner_module_count"] == 2
    assert not out.exists()


def test_owner_module_tamper_fails_before_overlay_creation(tmp_path):
    owner, out, args = _compose_with_owner_modules(tmp_path)
    (owner / "experiential_transport.py").write_bytes(b"unsafe or stale module")
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 78
    assert "OWNER_MODULE_DIGEST_MISMATCH" in proc.stderr
    assert not out.exists()


def test_owner_module_symlink_fails_before_overlay_creation(tmp_path):
    owner, out, args = _compose_with_owner_modules(tmp_path)
    pin = owner / "experiential_pin.py"
    data = pin.read_bytes()
    pin.unlink()
    target = tmp_path / "elsewhere_pin.py"
    target.write_bytes(data)
    pin.symlink_to(target)
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 78
    assert "OWNER_MODULE_SOURCE_INVALID" in proc.stderr
    assert not out.exists()


def test_compose_refuses_output_inside_release(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(COMPOSER), "--release-root", str(RELEASE_ROOT),
         "--output", str(RELEASE_ROOT / "ov_nested")],
        capture_output=True, text=True)
    assert proc.returncode == 78
    assert "OUTPUT_OVERLAP_REFUSED" in proc.stderr


# --------------------------------------------------------------------------
# Overlay CLI contract (Web recognition + fail-closed before any worker).
# --------------------------------------------------------------------------

def test_request_help_lists_consent_flags(composed_overlay):
    proc = run_overlay(composed_overlay, "request", "--help")
    assert proc.returncode == 0
    for flag in ALL_CONSENTS + ["--strict-manual-pin"]:
        assert flag in proc.stdout, flag


def test_request_missing_consent_refused_before_any_worker(composed_overlay):
    packet = composed_overlay / "probe_packet.txt"
    packet.write_text("probe")
    argv = ["request", "--id", RUN_ID, "--class", "fix_build",
            "--pool", "experiential", "--model", "glm-5.3-uncensored",
            "--strict-manual-pin", *ALL_CONSENTS[:2],
            "--packet", str(packet)]
    proc = run_overlay(composed_overlay, *argv)
    assert proc.returncode == 75
    # Two of four consents is not admission: the first missing consent refuses
    # typed, before any route, lease, packet or worker effect.
    assert "EXPERIENTIAL_PROPRIETARY_CODE_UNDECLARED" in proc.stderr
    assert not (composed_overlay / "state").exists()
    assert not (composed_overlay / "lanes").exists()


def test_request_flags_refused_on_nonexperiential_pool(composed_overlay):
    packet = composed_overlay / "probe_packet.txt"
    packet.write_text("probe")
    base = ["request", "--id", RUN_ID, "--class", "fix_build",
            "--packet", str(packet)]
    proc = run_overlay(composed_overlay, *base, "--pool", "grok",
                       "--experiential-retention-acknowledged")
    assert proc.returncode == 75
    assert "EXPERIENTIAL_OPTIONS_REFUSED_NONEXPERIENTIAL_POOL" in proc.stderr
    # AUTO (no --pool) must refuse the flags equally: no AUTO promotion.
    proc = run_overlay(composed_overlay, *base, "--strict-manual-pin")
    assert proc.returncode == 75
    assert "EXPERIENTIAL_OPTIONS_REFUSED_NONEXPERIENTIAL_POOL" in proc.stderr


def test_request_strict_model_slug_enforced(composed_overlay):
    packet = composed_overlay / "probe_packet.txt"
    packet.write_text("probe")
    proc = run_overlay(composed_overlay, "request", "--id", RUN_ID,
                       "--class", "fix_build", "--pool", "experiential",
                       "--model", "glm-5.3", "--strict-manual-pin",
                       *ALL_CONSENTS, "--packet", str(packet))
    assert proc.returncode == 75
    assert "EXPERIENTIAL_MODEL_SLUG_REFUSED" in proc.stderr


def test_preview_refuses_without_adapter(composed_overlay):
    proc = run_overlay(composed_overlay, "preview", "--id", RUN_ID,
                       "--class", "fix_build", "--pool", "experiential",
                       "--model", "glm-5.3-uncensored")
    assert proc.returncode == 78
    assert "EXPERIENTIAL_HOST_ADAPTER_MISSING" in proc.stderr


def test_preview_emits_preview_only_when_owner_gates_qualify(composed_overlay):
    write_mock_adapter(composed_overlay)
    try:
        proc = run_overlay(composed_overlay, "preview", "--id", RUN_ID,
                           "--class", "fix_build", "--pool", "experiential",
                           "--model", "glm-5.3-uncensored")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["state"] == "PREVIEW_ONLY"
        assert payload["reserved"] is False
        assert payload["pool"] == "experiential"
        assert payload["model"] == "glm-5.3-uncensored"
        assert payload["host"] == "ubuntu1"
        assert payload["selection_rechecked_at_request"] is True
        assert payload["strict_pin_enforced_at_request"] is True
        assert payload["witnesses"]["route_qualified"] is True
        assert payload["witnesses"]["effects_performed"] == 0
    finally:
        shutil.rmtree(composed_overlay / "experiential53")


def test_overlay_request_full_wiring_shape_with_mock_adapter(composed_overlay, tmp_path):
    """Mock-qualified route reaches remote_sub.sh with the exact sole shape."""
    write_mock_adapter(composed_overlay)
    import_stack = []
    try:
        sys.path.insert(0, str(composed_overlay))
        for name in ("experiential_bridge",):
            if name in sys.modules:
                del sys.modules[name]
        spec = importlib.util.spec_from_file_location(
            "overlay_fabric_task", str(composed_overlay / "fabric_task.py"))
        ft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ft)
        calls = []

        def fake_run(argv, env=None, **kwargs):
            calls.append((list(argv), dict(env or {})))

            class Proc:
                returncode = 0
            return Proc()

        original_run = ft.subprocess.run
        ft.subprocess.run = fake_run
        packet = tmp_path / "pkt.txt"
        packet.write_text("probe")
        rc = ft.request(
            RUN_ID, "fix_build", cwd=str(tmp_path), packet=packet,
            stdin_bytes=None, pool="experiential",
            requested_model="glm-5.3-uncensored", root_id=ROOT_ID,
            parent_run_id=ROOT_ID,
            experiential_retention_acknowledged=True,
            experiential_sensitive_data_opt_in=True,
            experiential_proprietary_code=True,
            experiential_code_exposure_opt_in=True,
            strict_manual_pin=True)
        ft.subprocess.run = original_run
        assert rc == 0
        assert len(calls) == 1, "exactly one launch dispatch, no duplicate effect"
        argv, env = calls[0]
        assert argv[0] == "/bin/bash"
        assert argv[1].endswith("remote_sub.sh")
        assert argv[2] == "ubuntu1"          # host from the host-owned witness
        assert argv[3] == "experiential"     # MODE
        assert argv[6] == "glm-5.3-uncensored"
        assert argv[7:] == ["--run-id", RUN_ID]
        for key, value in (
            ("EXPERIENTIAL_RETENTION_ACKNOWLEDGED", "1"),
            ("EXPERIENTIAL_SENSITIVE_DATA_OPT_IN", "1"),
            ("EXPERIENTIAL_PROPRIETARY_CODE", "1"),
            ("EXPERIENTIAL_CODE_EXPOSURE_OPT_IN", "1"),
            ("EXPERIENTIAL_STRICT_MANUAL_PIN", "1"),
            ("POOL_RUN_ID", RUN_ID),
            ("POOL_ORCHESTRATOR_ID", ROOT_ID),
            ("POOL_PARENT_RUN_ID", ROOT_ID),
        ):
            assert env.get(key) == value, key
    finally:
        sys.path.remove(str(composed_overlay))
        shutil.rmtree(composed_overlay / "experiential53")


# --------------------------------------------------------------------------
# Consumer hook law (mock sandbox, in-process).
# --------------------------------------------------------------------------

def test_adapter_missing_refuses_typed(tmp_path):
    bridge = sandbox_with_bridge(tmp_path, _no_adapter=True)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.request_gate(run_id=RUN_ID, task_class="fix_build", pool="experiential",
                            model="glm-5.3-uncensored", runtime_root=tmp_path,
                            **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_HOST_ADAPTER_MISSING"


def test_env_or_caller_paths_never_supply_adapter(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    write_mock_adapter(elsewhere)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    shutil.copyfile(BRIDGE_SOURCE, runtime / "experiential_bridge.py")
    monkeypatch.setenv("EXPERIENTIAL_ADAPTER_PATH", str(elsewhere))
    monkeypatch.setenv("EXPERIENTIAL53_HOME", str(elsewhere))
    bridge = load_bridge(runtime)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.request_gate(run_id=RUN_ID, task_class="fix_build", pool="experiential",
                            model="glm-5.3-uncensored", runtime_root=runtime,
                            **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_HOST_ADAPTER_MISSING"


@pytest.mark.parametrize("pool,model", [
    ("EXPERIENTIAL", "glm-5.3-uncensored"),
    ("experiential ", "glm-5.3-uncensored"),
    ("experiential", "GLM-5.3-Uncensored"),
    ("experiential", "glm-5.3-uncensored "),
    ("experiential", "glm-5.3-flash"),
])
def test_native_direct_pin_requires_exact_pool_and_model(tmp_path, pool, model):
    bridge = sandbox_with_bridge(tmp_path)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.request_gate(
            run_id=RUN_ID, task_class="fix_build", pool=pool, model=model,
            root_id=ROOT_ID, parent_run_id=ROOT_ID, runtime_root=tmp_path,
            **CONSENT_KWARGS)
    assert exc.value.reason in {
        "EXPERIENTIAL_POOL_REQUIRED", "EXPERIENTIAL_MODEL_SLUG_REFUSED"}
    assert not (tmp_path / "experiential53" / "post_calls.json").exists()


@pytest.mark.parametrize("pool", [None, "EXPERIENTIAL", "experiential ", "glm"])
def test_native_preview_never_qualifies_a_different_pool(tmp_path, pool):
    bridge = sandbox_with_bridge(tmp_path)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.preview_command(
            run_id=RUN_ID, task_class="fix_build", pool=pool,
            model="glm-5.3-uncensored", runtime_root=tmp_path)
    assert exc.value.reason == "EXPERIENTIAL_POOL_REQUIRED"


@pytest.mark.parametrize("mode,model", [
    ("EXPERIENTIAL", "glm-5.3-uncensored"),
    ("experiential", "GLM-5.3-Uncensored"),
])
def test_native_economic_witness_never_normalizes_the_manual_pin(
    tmp_path, mode, model,
):
    bridge = sandbox_with_bridge(tmp_path)
    with pytest.raises(bridge.ExperientialBridgeRefused):
        bridge.launch_policy_witness(mode, "fix_build", model)


def test_class_law_delegates_to_owner_pin(tmp_path):
    bridge = sandbox_with_bridge(tmp_path)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.preflight(run_id=RUN_ID, task_class="review", model="glm-5.3-uncensored",
                         runtime_root=tmp_path, **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_TASK_CLASS_FORBIDDEN"
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.preflight(run_id=RUN_ID, task_class="architecture", model="glm-5.3-uncensored",
                         runtime_root=tmp_path, **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_TASK_CLASS_FORBIDDEN"


def test_unqualified_transport_refuses_before_any_host_effect(tmp_path):
    bridge = sandbox_with_bridge(tmp_path, transport_installed=False)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.preflight(run_id=RUN_ID, task_class="fix_build",
                         model="glm-5.3-uncensored", runtime_root=tmp_path,
                         **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_TRANSPORT_NOT_INSTALLED"
    # No lease/broker/host artifact was created by the refused route.
    assert not (tmp_path / "lease_broker.py").exists()
    assert not (tmp_path / "state").exists()


def test_unqualified_route_constant_refuses(tmp_path):
    bridge = sandbox_with_bridge(tmp_path, route_qualified=False)
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.preflight(run_id=RUN_ID, task_class="fix_build",
                         model="glm-5.3-uncensored", runtime_root=tmp_path,
                         **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED"


@pytest.mark.parametrize("owner_state,expected_reason", [
    ({"quota_readback": "cached_ui_value"}, "QUOTA_READBACK_UNAUTHENTICATED"),
    ({"account": "a"}, "ACCOUNT_A_HELD_HTTP403"),
    ({"entitlement_verified": False}, "ENTITLEMENT_UNVERIFIED"),
    ({"registry_enabled": False}, "PROVIDER_DISABLED"),
])
def test_request_gate_rechecks_owner_before_native_lease(
    tmp_path, owner_state, expected_reason,
):
    """A positive route preview cannot bypass the economic/admission owner."""
    bridge = sandbox_with_bridge(tmp_path, **owner_state)
    # This gate is invoked by the composed fabric_task request BEFORE routing,
    # lease acquisition and any transport call; the exec gate repeats it.
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.request_gate(
            run_id=RUN_ID, task_class="fix_build", pool="experiential",
            model="glm-5.3-uncensored", root_id=ROOT_ID,
            parent_run_id=ROOT_ID, runtime_root=tmp_path,
            **CONSENT_KWARGS)
    assert exc.value.reason == expected_reason
    assert not (tmp_path / "experiential53" / "post_calls.json").exists()
    assert not (tmp_path / "state").exists()


def test_unknown_quota_readback_hard_refusal_with_zero_posts(tmp_path):
    bridge = sandbox_with_bridge(tmp_path, quota_readback="cached_ui_value")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("probe prompt")
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.exec_command(
            run_id=RUN_ID, task_class="fix_build", model="glm-5.3-uncensored",
            packet_root="lanes/probe-root", prompt_file=str(prompt),
            root=ROOT_ID, parent=ROOT_ID, runtime_root=tmp_path, **CONSENT_KWARGS)
    assert exc.value.reason == "QUOTA_READBACK_UNAUTHENTICATED"
    calls = tmp_path / "experiential53" / "post_calls.json"
    assert not calls.exists(), "no provider POST may occur on unknown cap"


def test_account_a_held_denial_preserved_with_zero_posts(tmp_path):
    bridge = sandbox_with_bridge(tmp_path, account="a")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("probe prompt")
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.exec_command(
            run_id=RUN_ID, task_class="fix_build", model="glm-5.3-uncensored",
            packet_root="lanes/probe-root", prompt_file=str(prompt),
            root=ROOT_ID, parent=ROOT_ID, runtime_root=tmp_path, **CONSENT_KWARGS)
    assert exc.value.reason == "ACCOUNT_A_HELD_HTTP403"
    assert not (tmp_path / "experiential53" / "post_calls.json").exists()


def test_unauthenticated_entitlement_refuses(tmp_path):
    bridge = sandbox_with_bridge(tmp_path, entitlement_verified=False)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("probe")
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.exec_command(
            run_id=RUN_ID, task_class="fix_build", model="glm-5.3-uncensored",
            packet_root="lanes/probe-root", prompt_file=str(prompt),
            root=ROOT_ID, parent=ROOT_ID, runtime_root=tmp_path, **CONSENT_KWARGS)
    assert exc.value.reason == "ENTITLEMENT_UNVERIFIED"


def test_exec_one_post_duplicate_refused_single_root(tmp_path):
    bridge = sandbox_with_bridge(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("probe prompt body")
    outcome = bridge.exec_command(
        run_id=RUN_ID, task_class="fix_build", model="glm-5.3-uncensored",
        packet_root="lanes/probe-root", prompt_file=str(prompt),
        root=ROOT_ID, parent=ROOT_ID, runtime_root=tmp_path, **CONSENT_KWARGS)
    assert outcome["state"] == "EXECUTED"
    assert outcome["root"] == ROOT_ID, "the one original root is preserved verbatim"
    assert outcome["admission"]["state"] == "ADMITTED"
    records = json.loads(
        (tmp_path / "experiential53" / "post_calls.json").read_text())
    assert len(records) == 1, "exactly one POST in the mock transport"
    assert records[0]["run_id"] == RUN_ID
    assert records[0]["model"] == "glm-5.3-uncensored"
    # A duplicate worker effect is refused, not re-posted.
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.exec_command(
            run_id=RUN_ID, task_class="fix_build", model="glm-5.3-uncensored",
            packet_root="lanes/probe-root", prompt_file=str(prompt),
            root=ROOT_ID, parent=ROOT_ID, runtime_root=tmp_path, **CONSENT_KWARGS)
    assert exc.value.reason == "EXPERIENTIAL_DUPLICATE_LAUNCH_REFUSED"
    records = json.loads(
        (tmp_path / "experiential53" / "post_calls.json").read_text())
    assert len(records) == 1


def test_missing_consent_refuses_before_route(tmp_path):
    bridge = sandbox_with_bridge(tmp_path)
    incomplete = {k: v for k, v in CONSENT_KWARGS.items()
                  if k != "retention_acknowledged"}
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.request_gate(run_id=RUN_ID, task_class="fix_build",
                            pool="experiential", model="glm-5.3-uncensored",
                            runtime_root=tmp_path, **incomplete)
    assert exc.value.reason == "RETENTION_UNVERIFIED"


def test_strict_pin_flag_required_on_launch_path(tmp_path):
    bridge = sandbox_with_bridge(tmp_path)
    kwargs = dict(CONSENT_KWARGS)
    kwargs["strict_manual_pin"] = False
    with pytest.raises(bridge.ExperientialBridgeRefused) as exc:
        bridge.request_gate(run_id=RUN_ID, task_class="fix_build",
                            pool="experiential", model="glm-5.3-uncensored",
                            runtime_root=tmp_path, **kwargs)
    assert exc.value.reason == "EXPERIENTIAL_STRICT_PIN_REQUIRED"


# --------------------------------------------------------------------------
# Overlay shell + slot wiring (byte-semantic preservation of other modes).
# --------------------------------------------------------------------------

ORIGINAL_MODES = ["glm", "glm-codex", "minimax", "minimax-codex", "grok",
                  "cursor", "qwen", "go-codex", "codex-native", "claude-native",
                  "oc-free"]
SUB_POOLS = ["grok", "qwen", "minimax", "glm", "minimax-codex", "glm-codex",
             "go-codex", "go-claude", "oc-free", "cursor"]
ORIGINAL_CAPS = {"qwen": 8, "minimax": 7, "grok": None, "cursor": None,
                 "glm": 0, "glm-frontier": 0, "go": 9, "ocfree": 3}


def test_overlay_shells_parse_and_keep_every_original_mode(composed_overlay):
    for script in ("remote_sub.sh", "sub.sh"):
        proc = subprocess.run(["bash", "-n", str(composed_overlay / script)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    remote = (composed_overlay / "remote_sub.sh").read_text()
    for mode in ORIGINAL_MODES:
        assert mode in remote, mode
    assert "experiential" in remote
    sub = (composed_overlay / "sub.sh").read_text()
    for pool in SUB_POOLS:
        assert pool in sub, pool
    assert "experiential" in sub


def test_overlay_slot_caps_add_experiential_zero_only(composed_overlay):
    sys.path.insert(0, str(composed_overlay))
    try:
        for name in ("slot", "lane_runtime"):
            sys.modules.pop(name, None)
        import slot  # noqa: PLC0415 - the composed overlay's slot
        assert slot.CAPS["experiential"] == 0, "zero capacity until owner attestation"
        for pool, cap in ORIGINAL_CAPS.items():
            assert slot.CAPS[pool] == cap, pool
        assert set(slot.CAPS) == set(ORIGINAL_CAPS) | {"experiential"}
    finally:
        sys.path.remove(str(composed_overlay))
        sys.modules.pop("slot", None)


def test_other_pools_launch_argv_unchanged(composed_overlay, tmp_path):
    """A grok (and AUTO) request must take the incumbent path byte-semantically:
    same pick.format_pick call shape, same launch_policy guard, same argv,
    and no experiential gate, env, or dispatch difference."""
    sys.path.insert(0, str(composed_overlay))
    try:
        for name in ("experiential_bridge", "pick"):
            sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(
            "overlay_fabric_task_other", str(composed_overlay / "fabric_task.py"))
        ft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ft)

        gate_calls = []
        import experiential_bridge as overlay_bridge
        original_gate = overlay_bridge.request_gate
        overlay_bridge.request_gate = lambda **kw: gate_calls.append(kw)

        formatted = []
        original_format = ft.pick.format_pick
        def spy_format(*args, **kwargs):
            formatted.append((args, kwargs))
            return "POOL=grok MODEL=mock-model HOST=ubuntu1 MODE=grok"
        ft.pick.format_pick = spy_format
        original_policy = ft.pick.launch_policy
        ft.pick.launch_policy = lambda *a, **k: {"allowed": True}

        launched = []
        original_run = ft.subprocess.run
        def fake_run(argv, env=None, **kw):
            launched.append((list(argv), dict(env or {})))
            class P:
                returncode = 0
            return P()
        ft.subprocess.run = fake_run

        packet = tmp_path / "pkt.txt"
        packet.write_text("probe")
        rc = ft.request("otherscope20261103", "fix_build", cwd=str(tmp_path),
                        packet=packet, stdin_bytes=None, pool="grok")
        assert rc == 0
        assert gate_calls == [], "no experiential gate may run for other pools"
        assert len(launched) == 1
        argv, env = launched[0]
        assert argv[3] == "grok"
        assert not any(k.startswith("EXPERIENTIAL_") for k in env)
        assert "POOL_RUN_ID" not in env

        # AUTO (pool=None) keeps the identical incumbent selection call shape.
        rc = ft.request("otherscope20261103b", "fix_build", cwd=str(tmp_path),
                        packet=packet, stdin_bytes=None, pool=None)
        assert rc == 0
        assert formatted[1][1].get("pool") is None
        assert formatted[1][1].get("host") == "auto"
    finally:
        ft.subprocess.run = original_run
        ft.pick.format_pick = original_format
        ft.pick.launch_policy = original_policy
        overlay_bridge.request_gate = original_gate
        sys.path.remove(str(composed_overlay))
        sys.modules.pop("overlay_fabric_task_other", None)


def test_bridge_cli_refuses_without_adapter(composed_overlay):
    proc = subprocess.run(
        [sys.executable, str(composed_overlay / "experiential_bridge.py"),
         "launch-preflight", "--run-id", RUN_ID, "--host", "ubuntu1",
         "--model", "glm-5.3-uncensored", "--task-class", "fix_build",
         "--retention-acknowledged", "1", "--sensitive-data-opt-in", "1",
         "--proprietary-code", "1", "--code-exposure-opt-in", "1",
         "--strict-manual-pin", "1"],
        capture_output=True, text=True, cwd=str(composed_overlay))
    assert proc.returncode == 78
    assert "EXPERIENTIAL_HOST_ADAPTER_MISSING" in proc.stderr


def test_bridge_cli_policy_check_shape(composed_overlay):
    ok = subprocess.run(
        [sys.executable, str(composed_overlay / "experiential_bridge.py"),
         "policy-check", "--mode", "experiential", "--class", "fix_build",
         "--model", "glm-5.3-uncensored"],
        capture_output=True, text=True, cwd=str(composed_overlay))
    assert ok.returncode == 0
    assert json.loads(ok.stdout) == {
        "allowed": True, "policy_source": "experiential_bridge_static_law",
        "escalate_to": None, "fallback": None, "auto_promotion": False}
    bad = subprocess.run(
        [sys.executable, str(composed_overlay / "experiential_bridge.py"),
         "policy-check", "--mode", "glm", "--class", "fix_build",
         "--model", "glm-5.3"],
        capture_output=True, text=True, cwd=str(composed_overlay))
    assert bad.returncode == 78


def test_bridge_cli_exec_refuses_unconsented(composed_overlay, tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("probe")
    proc = subprocess.run(
        [sys.executable, str(composed_overlay / "experiential_bridge.py"),
         "exec", "--run-id", RUN_ID, "--model", "glm-5.3-uncensored",
         "--task-class", "fix_build", "--cwd", "lanes/probe-root",
         "--prompt-file", str(prompt),
         "--strict-manual-pin", "1", "--retention-acknowledged", "0"],
        capture_output=True, text=True, cwd=str(composed_overlay))
    assert proc.returncode == 78
    assert "RETENTION_UNVERIFIED" in proc.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
