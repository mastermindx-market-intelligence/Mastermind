"""Exact-preimage native generation-26 integration of Grok catalog preflight.

Reads the already selected immutable M2 source, prepares a standalone staged
successor, and verifies it in a disposable native publisher. It never installs
or selects into the live native-code-releases store. Any incumbent drift REFUSES.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from ops.native_fabric.quota_continuity.rollout import native_generation as gen

PREVIOUS = "9eec6f73903fabfdd6d15bfe6f815f652f0946b5838cef6d40e96ca5b7e7f185"
BASE = "8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a"
ACCEPTED_DELTA = {
    "ext/fabric_task.py": "ca091b1e21f5b9d3349e7ce31ae46dff6173d27b5f36d432179418415f03eb88",
    "ext/pick.py": "747a55a50fb1ae579d18ae4decc6e3b077eb4b927a3968b61abaeeeb6292f132",
}
REVIEWED_PREIMAGES = {
    "ext/native_remote.py": "388c412ee5803ac54356275323eba5fb0ee57519a8810490f81fe13977459f9e",
    "ext/remote_sub_exec.py": "5880bad86fc4bc65a8460baf6156b46333a0ce33c24ef6742c905aa7db55ce2d",
}
CRITICAL_CONTRACT = {
    "ext/lane_runtime.py": "61350902dcf90ac65800f81e20acf473092c45738bbbef9b582548777e4e0329",
    "ext/remote_sub.sh": "7da97d3b99a0b9bc7f8aa15f7b405a099f22d8954feb9fb9ec24acf2c3092e92",
    "ext/fabric_client_projection.py": "39a138f88f6a3e4fb9b60f4365620ca05903e9f15783f95495627a54a13402e6",
    "ext/fabric_operator_client.py": "fcb79e9dc4b873832e18e1fde16f0ba900374a08d62d0fc8b9b624a40ec1cd17",
    "ext/fabric_operator_contract.py": "e642e36ef99d2c40b1254975b9ad3cc218fb9ef81c4ce87f3c7b6e7be0808c6a",
    "ext/commission_deadline.py": "9ae2b59f51902ae1f8f0cef459fad2b5f2ac10445ccabd17b33f995a26d70097",
    **REVIEWED_PREIMAGES,
}
ADDED = {"ext/fabric_model_readiness.py", "ext/native_catalog_guard.py"}
ROOT = Path(__file__).resolve().parents[3]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("NATIVE_CATALOG_PATCH_PREIMAGE_MISMATCH")
    return source.replace(old, new, 1)


def apply_native_remote(original: bytes) -> bytes:
    value = original.decode("utf-8")
    value = _replace_once(
        value,
        "def terminal(here, key, mode, model, env, started, rc, *, timing=None, output_binding=None):",
        "def terminal(here, key, mode, model, env, started, rc, *, timing=None, output_binding=None, catalog_unsettled=False):",
    )
    value = _replace_once(
        value,
        "                 cleanup_proven=not started or cleanup_receipt_is_proven(cleanup or {}))",
        "                 cleanup_proven=(not started or cleanup_receipt_is_proven(cleanup or {})) and not catalog_unsettled)\n"
        '    value["catalog_utility_unsettled"] = bool(catalog_unsettled)',
    )
    return value.encode("utf-8")


def apply_remote_executor(original: bytes) -> bytes:
    value = original.decode("utf-8")
    value = _replace_once(
        value,
        "        with lease, ExitStack() as artifact_stack:\n",
        "        with lease, ExitStack() as artifact_stack:\n"
        "            # Cover the catalog utility before the ordinary worker fuse.\n"
        "            install_signal_cleanup(on_unproven=lease.hold_for_reconciliation)\n",
    )
    value = _replace_once(
        value,
        "            if mode in native_remote.MODES:\n"
        "                child_env = native_remote.environment(mode, model, key, here, child_env)\n",
        "            if mode in native_remote.MODES:\n"
        "                child_env = native_remote.environment(mode, model, key, here, child_env)\n"
        "            if mode == 'grok':\n"
        "                # One actual, bounded model-list observation under this\n"
        "                # ORIGINAL physical + broker lease, before worker START.\n"
        "                from native_catalog_guard import (\n"
        "                    GrokCatalogRefused, GrokCatalogUnsettled,\n"
        "                    qualify_custodied_grok_worker,\n"
        "                )\n"
        "                try:\n"
        "                    command = qualify_custodied_grok_worker(\n"
        "                        state=state, lease=lease,\n"
        "                        key=key, model=model, here=here, cwd=cwd,\n"
        "                        env=child_env, command=command, timeout=timeout,\n"
        "                        nice=config.nice, runner=run_owned_process,\n"
        "                    )\n"
        "                except GrokCatalogRefused:\n"
        "                    return _fail('GROK_CATALOG_REFUSED before_worker=1', 78)\n"
        "                except GrokCatalogUnsettled:\n"
        "                    # The custody wrapper already held the original lease\n"
        "                    # and marked terminal cleanup unproven.\n"
        "                    return _fail('GROK_CATALOG_UNSETTLED before_worker=1', 76)\n"
        "                # The native lease clock is not reset by catalog lookup.\n"
        "                remaining_native = float(os.environ['NATIVE_LEASE_DEADLINE']) - time.time()\n"
        "                if remaining_native <= 0.05:\n"
        "                    return _fail('GROK_CATALOG_NATIVE_LEASE_EXPIRED before_worker=1', 78)\n"
        "                timeout = min(timeout, remaining_native)\n",
    )
    value = _replace_once(
        value,
        'state["started"], rc, timing=state.get("timing"), output_binding=state.get("output_binding"))',
        'state["started"], rc, timing=state.get("timing"), output_binding=state.get("output_binding"), catalog_unsettled=bool(state.get("catalog_unsettled", False)))',
    )
    return value.encode("utf-8")


def verify_accepted_delta(previous: dict[str, str], current: dict[str, str]) -> None:
    """Preserve the incumbent diagnostics and refuse unknown source movement."""
    if set(previous) != set(current):
        raise ValueError("NATIVE_CATALOG_INCUMBENT_CLOSURE_CHANGED")
    observed = {path: current[path] for path in current if current[path] != previous[path]}
    if observed != ACCEPTED_DELTA:
        raise ValueError("NATIVE_CATALOG_INCUMBENT_DELTA_UNREVIEWED")


def verify_compatible_selected(reference: dict[str, str], selected: dict[str, str]) -> None:
    """Allow unrelated newer native generation movement, never contract drift."""
    if set(reference) != set(selected):
        raise ValueError("NATIVE_CATALOG_NEW_GENERATION_FILESET_CHANGED")
    for path, wanted in CRITICAL_CONTRACT.items():
        if reference.get(path) != wanted or selected.get(path) != wanted:
            raise ValueError("NATIVE_CATALOG_NEW_GENERATION_CONTRACT_DRIFT")


def qualify(store: Path, release_stage: Path | None = None) -> dict:
    store = store.resolve(strict=True)
    pointer_before = (store / "CURRENT.json").read_bytes()
    pointer = gen.current(store)
    if (pointer is None or type(pointer.get("sequence")) is not int
            or pointer["sequence"] < 27):
        raise ValueError("NATIVE_CATALOG_CURRENT_GENERATION_UNQUALIFIED")
    source_root, manifest = gen.verify(store, pointer["generation"])
    _, baseline = gen.verify(store, BASE)
    _, previous = gen.verify(store, PREVIOUS)
    verify_accepted_delta(previous["files"], baseline["files"])
    verify_compatible_selected(baseline["files"], manifest["files"])
    if any(manifest["files"].get(path) != hash_ for path, hash_ in REVIEWED_PREIMAGES.items()):
        raise ValueError("NATIVE_CATALOG_REVIEWED_PREIMAGE_DRIFT")
    if ADDED.intersection(manifest["files"]):
        raise ValueError("NATIVE_CATALOG_FILE_ALREADY_OWNED")
    if release_stage is not None:
        release_stage = release_stage.absolute()
        if (release_stage.exists() or release_stage.is_symlink()
                or release_stage.parent.resolve(strict=True) != ROOT.parent.resolve(strict=True)):
            raise ValueError("NATIVE_CATALOG_STAGE_ROOT_REFUSED")
    with tempfile.TemporaryDirectory(prefix="native-catalog-qualification-") as td:
        target = Path(td).resolve(strict=True)
        source = target / "source"
        stable = target / "fake-owner" / "ext"
        source.mkdir()
        stable.mkdir(parents=True)
        new_hashes: dict[str, str] = {}
        for path, current_hash in manifest["files"].items():
            original = (source_root / path).read_bytes()
            if _sha(original) != current_hash:
                raise ValueError("NATIVE_CATALOG_SOURCE_CHANGED")
            new_bytes = (
                apply_native_remote(original) if path == "ext/native_remote.py" else
                apply_remote_executor(original) if path == "ext/remote_sub_exec.py" else original
            )
            dest = source / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new_bytes)
            new_hashes[path] = _sha(new_bytes)
        candidates = {
            "ext/fabric_model_readiness.py": ROOT / "control_plane" / "fabric_model_readiness.py",
            "ext/native_catalog_guard.py": Path(__file__).with_name("native_catalog_guard.py"),
        }
        for path, src in candidates.items():
            data = src.read_bytes()
            dest = source / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            new_hashes[path] = _sha(data)
        # Qualify only a disposable copy of the original native publication
        # owner. This is not a live selection or permission to launch workers.
        prior = gen.publish(source_root, stable, manifest["files"])
        scratch_store = stable.parent / "native-code-releases"
        gen.select(scratch_store, prior.name, None)
        successor = gen.publish(source, stable, new_hashes)
        clone, verified = gen.verify(scratch_store, successor.name)
        if verified["files"] != new_hashes:
            raise ValueError("NATIVE_CATALOG_MANIFEST_MISMATCH")
        gen.select(scratch_store, successor.name, prior.name)
        try:
            gen.select(scratch_store, prior.name, prior.name)
        except ValueError:
            pass
        else:
            raise ValueError("NATIVE_CATALOG_STALE_CAS_ACCEPTED")
        script = (
            "import json, native_remote, remote_sub_exec, native_catalog_guard, fabric_model_readiness;"
            "from pathlib import Path;"
            "assert hasattr(native_catalog_guard, 'qualify_custodied_grok_worker');"
            "assert native_remote.MODELS['grok']=={'grok-4.6','grok-4.7'};"
            "p=Path('catalog-canary');"
            "(p/'lanes'/'run.grok').mkdir(parents=True);"
            "scope={'POOL_ORCHESTRATOR_ID':'root','POOL_LEASE_ID':'lease','POOL_ACCOUNT':'default',"
            "'LANE_REMOTE_HOST':'ubuntu3','REMOTE_SUB_RUN_ID':'run'};"
            "native_remote.terminal(p,'run','grok','grok-4.7',scope,False,76,catalog_unsettled=True);"
            "rec=json.loads((p/'lanes'/'run.native-terminal.json').read_text());"
            "assert rec['cleanup_proven'] is False;"
            "assert rec['catalog_utility_unsettled'] is True;"
            "assert (p/'lanes'/'run.grok').exists();"
            "print('CATALOG_NATIVE_IMPORT_PASS')"
        )
        process = subprocess.run(
            [sys.executable, "-c", script],
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(clone/"ext"),
                 "PYTHONDONTWRITEBYTECODE": "1"},
            cwd=target, timeout=15, text=True, capture_output=True,
        )
        if process.returncode or process.stdout.strip() != "CATALOG_NATIVE_IMPORT_PASS":
            raise ValueError("NATIVE_CATALOG_ISOLATED_IMPORT_REFUSED " + process.stderr[-500:])
        report = {
            "state": "QUALIFIED_ISOLATED_NOT_INSTALLED",
            "base_generation": pointer["generation"],
            "base_sequence": pointer["sequence"],
            "verified_minimum_generation": BASE,
            "previous_accepted_generation": PREVIOUS,
            "accepted_incumbent_diagnostics": sorted(ACCEPTED_DELTA),
            "source_files": len(new_hashes),
            "patches": sorted(REVIEWED_PREIMAGES),
            "new_files": sorted(ADDED),
            "code_manifest_sha256": _sha(gen.canonical(new_hashes)),
            "isolated_publish_verified": True,
            "isolated_CAS_verified": True,
            "no_worker_launched": True,
        }
        if release_stage is not None:
            pending = Path(tempfile.mkdtemp(prefix=".native-catalog-", dir=release_stage.parent))
            try:
                shutil.copytree(source, pending / "source")
                (pending/"manifest.json").write_text(
                    json.dumps(new_hashes, sort_keys=True)+"\n"
                )
                (pending/"qualification.json").write_text(
                    json.dumps(report, sort_keys=True)+"\n"
                )
                pending.rename(release_stage)
            finally:
                if pending.exists():
                    shutil.rmtree(pending)
            report["release_stage"] = str(release_stage)
    if (store / "CURRENT.json").read_bytes() != pointer_before:
        raise ValueError("NATIVE_CATALOG_CURRENT_MOVED_DURING_QUALIFICATION")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--installed-store", type=Path, required=True)
    ap.add_argument("--release-stage", type=Path, default=None)
    options = ap.parse_args()
    print(json.dumps(qualify(options.installed_store, options.release_stage), sort_keys=True))


if __name__ == "__main__":
    main()
