"""Finite offline worker for actual sealed source, SQLite and file-lock tests."""
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import types

sys.dont_write_bytecode = True

def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value

def main():
    source, store, generation, action, raw_payload = sys.argv[1:]
    source, store = Path(source), Path(store)
    payload = json.loads(raw_payload)
    G = load("h6_worker_native_generation", source / "rollout/native_generation.py")
    root, meta = G.verify(store, generation)
    here = root / "ext"
    stable = Path(meta["stable_ext"])
    if action == "strict-cache-path":
        # Reproduce actual import-time realpath capture through a transient
        # physical cache symlink, then restore the authenticated canonical file.
        cache_path = stable / "quota_cache.json"
        poison = stable / "state/retained-wrong-cache.json"
        poison.write_text('{"cache_owner":"retained-wrong-target"}\n')
        poison.chmod(0o600)
        cache_path.unlink()
        cache_path.symlink_to(poison)
    sys.path.insert(0, str(here))
    entry = load("native_go_entry", here / "native_go_entry.py")
    if action == "foreign-helper":
        sys.modules["support_bundle"] = types.ModuleType("support_bundle")
    names = ("native_runtime_bindings", "support_bundle", "commission_deadline",
             "go_lease_capability", "provider_outcome", "quota_remote",
             "quota_circuit", "lease_broker", "paid_yaml_runtime")
    for name in names:
        path = here / (name + ".py")
        wanted = meta["files"]["ext/" + path.name]
        entry._load(name, path, entry._regular(path, mode=0o555, expected=wanted), wanted)
    B, Q, S, Y = (sys.modules[name] for name in
                  ("lease_broker", "quota_remote", "support_bundle", "paid_yaml_runtime"))
    if action == "strict-cache-path":
        assert Q.CACHE_PATH == str(poison), Q.CACHE_PATH
        cache_path.unlink()
        cache_path.write_text('{"cache_owner":"canonical-current-owner"}\n')
        cache_path.chmod(0o600)
    broker = None
    def source_check():
        G.verify(store, generation)
    with Y.held_yaml((here / "paid_pyyaml_6_0_3.zip").read_bytes(),
                     (here / "paid_pyyaml_provenance.json").read_bytes(),
                     source_check):
        if action not in {"quota", "foreign-helper"}:
            broker = B.Broker(
                db_path=str(stable / "broker/leases.sqlite"),
                lock_path=str(stable / "broker/leases.lock"),
                accounts_path=str(stable.parent / "orch/fabric/accounts.yaml"),
                now_fn=lambda: 1000.0, check_pid=False, external_gates=False,
                this_host="fixture-host",
                status_json=str(stable.parent / "orch/fabric/status.json"),
                hosts_path=str(stable / "hosts.json"),
                grok_marker=str(stable / "GROK_EXHAUSTED"))
        emit({"phase": "ready"})
        if sys.stdin.readline().strip() != "go":
            raise ValueError("fixture start barrier missing")
        emit({"phase": "attempt", "action": action})
        if payload.get("hold_before_commit"):
            original = broker._try_acquire_in_transaction
            def barrier(*args, **kwargs):
                result = original(*args, **kwargs)
                if result[0].ok:
                    emit({"phase": "claim-before-commit", "lease_id": result[0].lease_id})
                    if sys.stdin.readline().strip() != "commit":
                        raise ValueError("fixture commit barrier missing")
                return result
            broker._try_acquire_in_transaction = barrier
        if action == "init":
            result = {"initialized": True}
        elif action == "worker":
            result = asdict(broker.acquire(
                payload.get("orchestrator_id", "fixture-worker"), "go",
                task_class="build", host="fixture-host", pid=os.getpid(),
                wait=0, model="fixture-model"))
        elif action == "begin":
            result = broker.begin_application_turn(
                principal_id="fixture-principal", caller_host="fixture-host",
                workload="site_interactive", turn_id=payload.get("turn_id", "original-turn"),
                pool="go", model="fixture-model")
        elif action == "prepare":
            result = broker.prepare_application_request(
                principal_id="fixture-principal", turn_id="original-turn",
                request_id=payload.get("request_id", "original-request"),
                request_digest=payload.get("request_digest", "a" * 64))
        elif action == "recover":
            result = broker.recover_application_request(
                principal_id="fixture-principal", turn_id="original-turn",
                request_id=payload.get("request_id", "original-request"),
                request_digest=payload.get("request_digest", "a" * 64))
        elif action == "unknown":
            result = broker.mark_application_request_unknown(
                dispatch_id=payload["dispatch_id"], reason="fixture_original_observation_missing")
        elif action == "complete":
            result = broker.complete_application_request(
                dispatch_id=payload["dispatch_id"], terminal_receipt=payload["receipt"])
        elif action == "close":
            result = broker.close_application_turn(
                principal_id="fixture-principal", turn_id="original-turn")
        elif action == "strict-cache-path":
            with broker._physical_admission_scope() as held:
                document, digest = Q.read_account_admission_cache()
                held()
            result = {"document": document, "sha256": digest,
                      "retained_path_differs": Q.CACHE_PATH != str(cache_path)}
        elif action == "quota":
            def update(cache):
                cache["fixture_publications"] = cache.get("fixture_publications", 0) + 1
                return True, {"publications": cache["fixture_publications"]}
            result = Q._update_cache(str(stable / "quota_cache.json"), update)
        elif action == "snapshot":
            projection = types.ModuleType("pool_status")
            def build_status():
                # Instrument only the advisory projection. The cache owner,
                # admission flock and tested Broker lock are the real owners.
                def update(cache):
                    check = subprocess.run([sys.executable, "-c",
                        "import fcntl,sys; f=open(sys.argv[1],'r+'); "
                        "fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)",
                        str(stable / "broker/leases.lock")],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
                    if check.returncode != 0:
                        raise RuntimeError("projection still holds Broker during admission")
                    cache["snapshot_publications"] = cache.get("snapshot_publications", 0) + 1
                    return True, None
                Q._update_cache(str(stable / "quota_cache.json"), update)
                return {"offpeak": {"fixture": True},
                        "pools": {"go": {"offpeak": True, "keys": ["fixture-key-name"],
                                         "cap": 999}}}
            projection.build_status = build_status
            sys.modules["pool_status"] = projection
            result = broker.snapshot()
        elif action == "counts":
            with sqlite3.connect(stable / "broker/leases.sqlite") as conn:
                conn.row_factory = sqlite3.Row
                result = {table: [dict(row) for row in conn.execute("SELECT * FROM " + table)]
                          for table in ("leases", "application_turns", "application_requests")}
        else:
            raise ValueError("unknown finite fixture operation")
        emit({"phase": "result", "result": result})

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit({"phase": "error", "error_type": type(exc).__name__, "message": str(exc)})
