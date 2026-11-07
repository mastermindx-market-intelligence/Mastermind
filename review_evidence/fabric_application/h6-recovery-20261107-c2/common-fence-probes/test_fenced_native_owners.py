"""Actual native owner concurrency, source-currentness and recovery probes."""
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest

from test_current_selection_reader import ROOT, G, S
from test_common_admission_fence import read_event, finish, stop_if_running

WORKER = Path(__file__).with_name("fence_owner_worker.py")
SELECTOR_WORKER = Path(__file__).with_name("test_common_admission_fence.py")

def send(child, text):
    child.stdin.write(text + "\n")
    child.stdin.flush()

def start_owner(fixture, action, payload=None, *, generation=None):
    child = subprocess.Popen(
        [sys.executable, "-B", str(WORKER), str(ROOT), str(fixture["store"]),
         generation or fixture["first"].name, action, json.dumps(payload or {})],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
    try:
        assert read_event(child) == {"phase": "ready"}
        return child
    except BaseException:
        stop_if_running(child)
        raise

def run_owner(fixture, action, payload=None, *, generation=None):
    child = start_owner(fixture, action, payload, generation=generation)
    try:
        send(child, "go")
        assert read_event(child) == {"phase": "attempt", "action": action}
        result = read_event(child)
        finish(child)
        return result
    finally:
        stop_if_running(child)

def value(event):
    assert event["phase"] == "result", event
    return event["result"]

@pytest.fixture
def native_owner(tmp_path):
    base = tmp_path.resolve()
    stable = base / "kit/ext"
    for relative in ("active", "broker", "lanes", "slots", "state"):
        (stable / relative).mkdir(parents=True, mode=0o700)
    (stable.parent / "orch/fabric").mkdir(parents=True, mode=0o700)
    policy = base / "policy.json"
    policy.write_text(json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {}}}}}))
    S.ensure_policy(policy, stable, hashlib.sha256(policy.read_bytes()).hexdigest())
    grant = dict(grant_id="fixture-service-grant", purpose="APPLICATION", enabled=True,
        principal_id="fixture-principal", credential_ref="FIXTURE_APPLICATION_CREDENTIAL",
        admission_root="service:fixture", caller_hosts=["fixture-host"],
        workloads=["site_interactive"], pool="go", accounts=["fixture-account"],
        models=["fixture-model"], route="/v1/chat/completions", stream=False,
        expires_at=2000, max_turn_seconds=300, max_steps=2,
        qualification_ref="fixture:offline-owner-concurrency",
        application_permission_ref="fixture:offline-only")
    document = {"schema": "mastermind.provider_accounts.v1",
        "providers": {"go": {"enabled": True,
            "accounts": [{"name": "fixture-account", "per_account_cap": 1}]}},
        "application_grants": [grant]}
    accounts = stable.parent / "orch/fabric/accounts.yaml"
    accounts.write_text(json.dumps(document))
    accounts.chmod(0o600)
    (stable.parent / "orch/fabric/status.json").write_text('{"pools":{}}\n')
    (stable / "hosts.json").write_text('{"hosts":{}}\n')
    (stable / "quota_cache.json").write_text("{}\n")
    names = [name for name in json.loads((ROOT.parent / "preparation.json").read_text())["baseline_hashes"]
             if name == "pool" or name.startswith("ext/")]
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    first = G.publish(ROOT, stable, files)
    store = G.store_path(stable)
    selected = G.select(store, first.name, None)
    fixture = dict(base=base, stable=stable, accounts=accounts, document=document,
                   first=first, store=store, selected=selected, names=names)
    assert value(run_owner(fixture, "init")) == {"initialized": True}
    return fixture

def successor(fixture, *, original_broker=False, original_quota=False):
    source = Path(tempfile.mkdtemp(prefix="successor-source-", dir=fixture["base"]))
    (source / "ext").mkdir()
    for name in fixture["names"]:
        shutil.copyfile(ROOT / name, source / name)
    with (source / "pool").open("ab") as handle:
        handle.write(b"\n# offline common-fence successor\n")
    if original_broker:
        shutil.copyfile(ROOT.parent / "pre-fence/ext/lease_broker.py",
                        source / "ext/lease_broker.py")
    if original_quota:
        shutil.copyfile(ROOT.parent / "before-custody-correction/ext/quota_remote.py",
                        source / "ext/quota_remote.py")
    files = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
             for name in fixture["names"]}
    return G.publish(source, fixture["stable"], files)

def rows(fixture, table):
    with sqlite3.connect(fixture["stable"] / "broker/leases.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM " + table)]

def test_real_claim_blocks_selection_and_quota_until_sqlite_commit(native_owner):
    f = native_owner
    second = successor(f)
    claimant = start_owner(f, "worker", {"hold_before_commit": True})
    quota = None
    selector = None
    try:
        send(claimant, "go")
        assert read_event(claimant)["phase"] == "attempt"
        assert read_event(claimant)["phase"] == "claim-before-commit"
        assert rows(f, "leases") == []
        selector = subprocess.Popen(
            [sys.executable, "-B", str(SELECTOR_WORKER), "select",
             str(f["store"]), second.name, f["first"].name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        assert read_event(selector) == {"phase": "publication-held"}
        quota = start_owner(f, "quota")
        send(quota, "go")
        assert read_event(quota)["phase"] == "attempt"
        assert select.select([selector.stdout, quota.stdout], [], [], 0.15)[0] == []
        assert G.current(f["store"]) == f["selected"]
        assert json.loads((f["stable"] / "quota_cache.json").read_text()) == {}
        send(claimant, "commit")
        assert value(read_event(claimant))["ok"] is True
        finish(claimant)
        selected = read_event(selector)
        assert selected["phase"] == "selected"
        assert selected["value"]["generation"] == second.name
        assert selected["value"]["sequence"] == 2
        assert value(read_event(quota)) == {"publications": 1}
        finish(selector)
        finish(quota)
        assert len(rows(f, "leases")) == 1
        assert json.loads((f["stable"] / "quota_cache.json").read_text())["fixture_publications"] == 1
    finally:
        for child in (claimant, quota, selector):
            if child is not None:
                stop_if_running(child)

def test_publication_first_refuses_stale_claim_and_allows_current_source(native_owner):
    f = native_owner
    second = successor(f)
    G.select(f["store"], second.name, f["first"].name)
    refused = run_owner(f, "worker")
    assert refused["phase"] == "error"
    assert "source_no_longer_eligible" in refused["message"]
    assert rows(f, "leases") == []
    admitted = value(run_owner(f, "worker", generation=second.name))
    assert admitted["ok"] is True
    assert len(rows(f, "leases")) == 1

def test_worker_and_application_share_last_capacity_across_processes(native_owner):
    f = native_owner
    children = [start_owner(f, "worker"), start_owner(f, "begin")]
    try:
        for child in children:
            send(child, "go")
        results = []
        for child in children:
            assert read_event(child)["phase"] == "attempt"
            results.append(value(read_event(child)))
            finish(child)
        assert sum(result["ok"] is True for result in results) == 1
        assert len(rows(f, "leases")) == 1
        assert len(rows(f, "application_turns")) <= 1
    finally:
        for child in children:
            stop_if_running(child)

def test_changed_owner_document_with_same_mtime_is_read_under_claim_scope(native_owner):
    f = native_owner
    before = f["accounts"].stat()
    f["document"]["providers"]["go"]["enabled"] = False
    with G.verified_admission_scope(f["store"], f["first"].name) as held:
        f["accounts"].write_text(json.dumps(f["document"]))
        os.utime(f["accounts"], ns=(before.st_atime_ns, before.st_mtime_ns))
        held()
    refused = value(run_owner(f, "worker"))
    assert refused["ok"] is False
    assert refused["reason"] == "provider_disabled"
    assert rows(f, "leases") == []

def test_advisory_status_refresh_releases_broker_before_quota_publication(native_owner):
    f = native_owner
    result = value(run_owner(f, "snapshot"))
    assert result["offpeak"] == {"fixture": True}
    assert result["pools"]["go"]["cap"] == 1
    assert result["pools"]["go"]["keys"] == ["fixture-key-name"]
    cache = json.loads((f["stable"] / "quota_cache.json").read_text())
    assert cache["snapshot_publications"] == 1

def test_original_snapshot_boundary_reproduces_broker_to_admission_inversion(native_owner):
    f = native_owner
    before = successor(f, original_broker=True)
    # This explicitly composed baseline is used only to observe the original
    # status boundary, not as an eligible runtime or claim cohort.
    result = value(run_owner(f, "snapshot", generation=before.name))
    assert result["offpeak"] is None
    assert "snapshot_publications" not in json.loads(
        (f["stable"] / "quota_cache.json").read_text())

def test_original_pending_unknown_terminal_and_close_survive_selection_change(native_owner):
    f = native_owner
    binding = value(run_owner(f, "begin"))
    assert binding["ok"] is True
    prepared = value(run_owner(f, "prepare"))
    assert prepared["dispatch_permitted"] is True
    second = successor(f)
    G.select(f["store"], second.name, f["first"].name)
    recovered = value(run_owner(f, "recover"))
    assert recovered["disposition"] == "pending"
    assert recovered["dispatch_permitted"] is False
    replay = value(run_owner(f, "prepare"))
    assert replay["dispatch_id"] == prepared["dispatch_id"]
    assert replay["dispatch_permitted"] is False
    value(run_owner(f, "unknown", {"dispatch_id": prepared["dispatch_id"]}))
    unknown = value(run_owner(f, "recover"))
    assert unknown["disposition"] == "effect_unknown"
    another = value(run_owner(f, "prepare", {"request_id": "another", "request_digest": "b" * 64}))
    assert another["disposition"] == "effect_unknown"
    request = rows(f, "application_requests")[0]
    turn = rows(f, "application_turns")[0]
    receipt = dict(dispatch_id=request["dispatch_id"], request_digest=request["request_digest"],
        lease_id=turn["lease_id"], account=turn["account"], model=turn["model"],
        response_digest=hashlib.sha256(b"fixture-response").hexdigest(), status_code=200,
        completed_at=1000.0, usage={"input_tokens": 2, "output_tokens": 1})
    value(run_owner(f, "complete", {"dispatch_id": prepared["dispatch_id"], "receipt": receipt}))
    terminal = value(run_owner(f, "recover"))
    assert terminal["disposition"] == "terminal"
    assert terminal["dispatch_permitted"] is False
    refused = run_owner(f, "prepare", {"request_id": "new-step", "request_digest": "c" * 64})
    assert refused["phase"] == "error"
    assert "source_no_longer_eligible" in refused["message"]
    value(run_owner(f, "close"))
    assert rows(f, "application_turns")[0]["state"] == "closed"
    assert len(rows(f, "application_requests")) == 1

def test_native_owned_loader_refuses_foreign_helper_before_claim(native_owner):
    f = native_owner
    p = subprocess.run(
        [sys.executable, "-B", str(WORKER), str(ROOT), str(f["store"]),
         f["first"].name, "foreign-helper", "{}"],
        input="go\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    event = json.loads(p.stdout.strip())
    assert event["phase"] == "error"
    assert "native Go module conflict: support_bundle" in event["message"]
    assert rows(f, "leases") == []

@pytest.mark.parametrize("original_quota", [False, True])
def test_strict_cache_reads_canonical_owner_despite_prior_alias_capture(native_owner, original_quota):
    f = native_owner
    generation = f["first"]
    if original_quota:
        generation = successor(f, original_quota=True)
        G.select(f["store"], generation.name, f["first"].name)
    result = value(run_owner(f, "strict-cache-path", generation=generation.name))
    assert result["retained_path_differs"] is True
    expected = "retained-wrong-target" if original_quota else "canonical-current-owner"
    assert result["document"] == {"cache_owner": expected}
    expected_raw = ('{"cache_owner":"' + expected + '"}\n').encode()
    assert result["sha256"] == hashlib.sha256(expected_raw).hexdigest()
    assert json.loads((f["stable"] / "quota_cache.json").read_text()) == {
        "cache_owner": "canonical-current-owner"}
    assert rows(f, "leases") == []
