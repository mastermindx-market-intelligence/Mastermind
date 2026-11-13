"""Fleet CI slot pool (ops/fleet_ci/, docs/FLEET_CI_POOL.md).

The slot loop and unit run as root on fleet hosts and are not executed here; these
tests pin admission decisions on fixture /proc text, the sizing rule, the router and
its trusted-source guard, the composite action's output per mode, parity with the
Fabric host placer's gate semantics AND between the action's pinned script copies and
ops/fleet_ci, the generated nftables egress rules, the hold/cron-at/sudoers bash logic
(extracted into harnesses), the capacity queued-job subtraction, the canary isolation
harness's static contract, and the invariants that keep the JIT config out of argv
and logs.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "ops" / "fleet_ci"
SLOT = FLEET / "fleet-slot"
UNIT = FLEET / "fleet-slot@.service"
SLICE = FLEET / "fleet_ci.slice"
MINT = FLEET / "fleet-mint"
CAPACITY = FLEET / "fleet-capacity"
CONF = FLEET / "fleet.conf.example"
CANARY = FLEET / "canary-isolation-check"
ACTION_DIR = ROOT / ".github" / "actions" / "fleet-route"
ACTION = ACTION_DIR / "action.yml"
DOC = ROOT / "docs" / "FLEET_CI_POOL.md"
HOST_PICK = ROOT / "ops" / "native_fabric" / "quota_continuity" / "source" / "host_pick.py"

sys.path.insert(0, str(FLEET))
import fleet_gate  # noqa: E402
import fleet_route  # noqa: E402

capacity_mod = SourceFileLoader("fleet_capacity_under_test", str(CAPACITY)).load_module()
mint_mod = SourceFileLoader("fleet_mint_under_test", str(MINT)).load_module()


def code_lines(path: Path) -> str:
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                     if not l.lstrip().startswith("#"))


def extract(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.DOTALL)
    assert m, f"pattern not found: {pattern}"
    return m.group(0)


# --- fixture /proc ----------------------------------------------------------------------

def psi(some10: float) -> str:
    return (f"some avg10={some10:.2f} avg60=0.50 avg300=0.10 total=12345\n"
            "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")


def make_proc(tmp_path: Path, mem=1.0, io=1.0, cpu=5.0, avail_gb=40.0, total_gb=62.0,
              load1=4.0) -> Path:
    proc = tmp_path / "proc"
    (proc / "pressure").mkdir(parents=True)
    (proc / "pressure" / "memory").write_text(psi(mem))
    (proc / "pressure" / "io").write_text(psi(io))
    (proc / "pressure" / "cpu").write_text(psi(cpu))
    (proc / "meminfo").write_text(
        f"MemTotal:       {int(total_gb * 1048576)} kB\n"
        f"MemFree:         1000 kB\n"
        f"MemAvailable:   {int(avail_gb * 1048576)} kB\n")
    (proc / "loadavg").write_text(f"{load1:.2f} 3.00 2.00 2/1000 12345\n")
    return proc


def raw_conf(**over) -> dict:
    c = fleet_gate.parse_conf(CONF.read_text(encoding="utf-8"))
    c["RUNNER_GROUP_ID"] = "7"
    c.update({k: str(v) for k, v in over.items()})
    return c


def conf(**over) -> dict:
    c = raw_conf(**over)
    assert fleet_gate.validate_conf(c) == []
    return c


def gate_of(gates, name):
    return next(g for g in gates if g["gate"] == name)


def evaluate(tmp_path, busy=0, cores=32, **proc_kw):
    obs = fleet_gate.observe(str(make_proc(tmp_path, **proc_kw)), cores=cores)
    return fleet_gate.evaluate_admission(obs, fleet_gate.policy_from_conf(conf()), busy)


# --- admission --------------------------------------------------------------------------

def test_parse_psi_and_meminfo():
    p = fleet_gate.parse_psi(psi(12.5))
    assert p["some"]["avg10"] == 12.5 and p["full"]["avg10"] == 0.0
    m = fleet_gate.parse_meminfo("MemTotal: 2048 kB\nMemAvailable: 1024 kB\n")
    assert m == {"MemTotal": 2048, "MemAvailable": 1024}
    assert fleet_gate.parse_loadavg("3.50 1 1 1/1 1") == 3.5


def test_quiet_host_is_admitted(tmp_path):
    ok, gates = evaluate(tmp_path)
    assert ok, gates
    # No freshness gate: the observation is live in the same call (tautological).
    assert {g["gate"] for g in gates} == {"pressure", "memory", "load"}


@pytest.mark.parametrize("kw,gate", [
    ({"mem": 10.0}, "pressure"),          # == ceiling refuses (host_pick uses >=)
    ({"mem": 30.0}, "pressure"),
    ({"io": 20.0}, "pressure"),
    ({"load1": 32 * 0.85}, "load"),       # load1/cores == LOAD_MAX refuses
])
def test_pressure_and_load_ceilings_refuse_at_threshold(tmp_path, kw, gate):
    ok, gates = evaluate(tmp_path, **kw)
    assert not ok and gate_of(gates, gate)["result"] == "FAIL"


def test_just_below_ceilings_admits(tmp_path):
    ok, _ = evaluate(tmp_path, mem=9.99, io=19.99, load1=32 * 0.84)
    assert ok


def test_memory_floor_scales_with_busy_slots(tmp_path):
    # floor 6 GB: 3 busy -> need 24 GB
    ok, gates = evaluate(tmp_path, busy=3, avail_gb=24.0)
    assert ok, gates
    ok, gates = evaluate(tmp_path / "b", busy=3, avail_gb=23.9)
    assert not ok and gate_of(gates, "memory")["result"] == "FAIL"


def test_missing_procfs_fails_closed(tmp_path):
    proc = make_proc(tmp_path)
    (proc / "pressure" / "io").unlink()
    (proc / "meminfo").write_text("garbage\n")
    obs = fleet_gate.observe(str(proc), cores=32)
    ok, gates = fleet_gate.evaluate_admission(obs, fleet_gate.policy_from_conf(conf()), 0)
    assert not ok
    assert gate_of(gates, "pressure")["detail"] == "pressure-unavailable-or-stale"
    assert gate_of(gates, "memory")["detail"] == "missing_or_invalid"


def test_invalid_policy_fails_closed(tmp_path):
    obs = fleet_gate.observe(str(make_proc(tmp_path)), cores=32)
    pol = fleet_gate.policy_from_conf(conf())
    pol["mem_psi_max"] = 0.5  # outside 1..100, as host_pick's policy_valid
    ok, gates = fleet_gate.evaluate_admission(obs, pol, 0)
    assert not ok and gate_of(gates, "pressure")["detail"] == "invalid-pressure-policy"


def test_freshness_gate_removed_and_documented():
    assert not hasattr(fleet_gate, "_valid_timestamp")
    assert "tautological" in DOC.read_text()
    assert "No freshness gate" in DOC.read_text()


def test_admit_records_claim_and_counts_it_as_busy(tmp_path):
    status = tmp_path / "run"
    proc = make_proc(tmp_path, avail_gb=13.0)  # floor 6: room for 2 slots
    c = conf()
    ok1, rec1 = fleet_gate.admit(c, 1, str(status), str(proc), cores=32)
    ok2, rec2 = fleet_gate.admit(c, 2, str(status), str(proc), cores=32)
    ok3, rec3 = fleet_gate.admit(c, 3, str(status), str(proc), cores=32)
    assert (ok1, ok2, ok3) == (True, True, False)
    assert rec1["state"] == "claimed" and rec3["state"] == "refused"
    assert rec3["detail"]["busy_slots"] == 2
    on_disk = json.loads((status / "slot-3.json").read_text())
    assert on_disk["schema"] == fleet_gate.SCHEMA and on_disk["port_base"] == 20300
    # a slot that finished its job frees the headroom
    fleet_gate.write_status(str(status), 1, "exited", "std")
    assert fleet_gate.admit(c, 3, str(status), str(proc), cores=32)[0]


def test_unreadable_status_file_counts_as_busy(tmp_path):
    (tmp_path / "slot-4.json").write_text("{not json")
    (tmp_path / "slot-5.json").write_text(json.dumps({"state": "wiping"}))
    assert fleet_gate.count_busy(str(tmp_path), exclude_slot=1) == 1


def _age_claim(status_dir, slot, state, age_s, now):
    rec = fleet_gate.write_status(str(status_dir), slot, state, "std")
    rec["ts"] = now - age_s
    Path(fleet_gate.status_path(str(status_dir), slot)).write_text(json.dumps(rec))


def test_stale_claim_ignored_and_reported(tmp_path):
    status = tmp_path / "run"
    now = 1_000_000.0
    _age_claim(status, 2, "claimed", 0, now)        # fresh claim still holds capacity
    _age_claim(status, 3, "claimed", 7 * 3600, now)  # 7h old claim -> stale, ignored
    _age_claim(status, 4, "registered", 7 * 3600, now)  # other busy states count regardless of age
    busy, stale = fleet_gate._scan_status(str(status), 1, 21600.0, now)
    assert busy == 2 and stale == [3]
    assert fleet_gate.count_busy(str(status), 1, 21600.0, now) == 2


def test_stale_claim_max_age_configurable(tmp_path):
    status = tmp_path / "run"
    now = 1_000_000.0
    _age_claim(status, 2, "claimed", 100, now)
    busy, stale = fleet_gate._scan_status(str(status), 1, 200.0, now)
    assert busy == 1 and stale == []
    busy, stale = fleet_gate._scan_status(str(status), 1, 50.0, now)
    assert busy == 0 and stale == [2]


def test_status_cli_reports_stale_claims(tmp_path):
    cf = tmp_path / "fleet.conf"
    cf.write_text(CONF.read_text().replace("RUNNER_GROUP_ID=0", "RUNNER_GROUP_ID=7"))
    status = tmp_path / "run"
    _age_claim(status, 5, "claimed", 7 * 3600, time.time())
    r = subprocess.run([sys.executable, str(FLEET / "fleet_gate.py"), "--conf", str(cf),
                        "--status-dir", str(status), "status", "--slot", "1", "--state", "starting"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert json.loads(r.stdout)["stale_claims"] == [5]


def test_admit_detail_reports_stale_claims(tmp_path):
    status = tmp_path / "run"
    _age_claim(status, 9, "claimed", 7 * 3600, time.time())
    proc = make_proc(tmp_path, avail_gb=40.0)
    ok, rec = fleet_gate.admit(conf(), 1, str(status), str(proc), cores=32)
    assert ok and rec["detail"]["stale_claims"] == [9]
    # the stale slot 9 does not consume headroom
    assert rec["detail"]["busy_slots"] == 0


def test_conf_stale_claim_validation():
    assert fleet_gate.DEFAULTS["STALE_CLAIM_S"] == "21600"
    assert any("STALE_CLAIM_S" in e for e in fleet_gate.validate_conf(raw_conf(STALE_CLAIM_S="0")))
    assert any("STALE_CLAIM_S" in e for e in fleet_gate.validate_conf(raw_conf(STALE_CLAIM_S="abc")))
    assert fleet_gate.validate_conf(raw_conf(STALE_CLAIM_S="3600")) == []
    assert "STALE_CLAIM_S=21600" in CONF.read_text()


def test_gate_cli_exit_codes(tmp_path):
    cf = tmp_path / "fleet.conf"
    cf.write_text(CONF.read_text().replace("RUNNER_GROUP_ID=0", "RUNNER_GROUP_ID=7"))
    proc = make_proc(tmp_path, mem=50.0)
    base = [sys.executable, str(FLEET / "fleet_gate.py"), "--conf", str(cf),
            "--status-dir", str(tmp_path / "run"), "--proc-root", str(proc)]
    r = subprocess.run(base + ["admit", "--slot", "1"], capture_output=True, text=True)
    assert r.returncode == fleet_gate.EX_REFUSED and json.loads(r.stdout)["state"] == "refused"
    r = subprocess.run(base + ["get", "FLEET_CLASS"], capture_output=True, text=True)
    assert r.stdout.strip() == "std"
    for bad_slot in ("0", "33"):
        r = subprocess.run(base + ["admit", "--slot", bad_slot], capture_output=True, text=True)
        assert r.returncode == fleet_gate.EX_USAGE
    cf.write_text("FLEET_CLASS=std\nRUNNER_GROUP_ID=7\nMEM_PSI_MAX=0\n")
    r = subprocess.run(base + ["get", "FLEET_CLASS"], capture_output=True, text=True)
    assert r.returncode == fleet_gate.EX_USAGE


def test_conf_refuses_unknown_keys():
    with pytest.raises(ValueError):
        fleet_gate.parse_conf("SLOTS=2\nEVIL=$(rm -rf /)\n")


def test_conf_requires_tarball_pin_and_positive_group_id():
    assert any("RUNNER_TARBALL_SHA256" in e for e in fleet_gate.validate_conf(raw_conf(RUNNER_TARBALL_SHA256="")))
    assert any("RUNNER_TARBALL_SHA256" in e for e in fleet_gate.validate_conf(raw_conf(RUNNER_TARBALL_SHA256="abc123")))
    assert any("RUNNER_TARBALL_SHA256" in e for e in fleet_gate.validate_conf(raw_conf(RUNNER_TARBALL_SHA256="A" * 64)))
    assert fleet_gate.validate_conf(raw_conf(RUNNER_TARBALL_SHA256="a" * 64)) == []
    assert any("RUNNER_GROUP_ID" in e for e in fleet_gate.validate_conf(raw_conf(RUNNER_GROUP_ID="0")))
    assert "RUNNER_TARBALL_SHA256=" in CONF.read_text()


def test_gate_semantics_match_host_pick():
    """The copied helpers behave like host_pick's on the same inputs."""
    hp_dir = str(HOST_PICK.parent)
    sys.path.insert(0, hp_dir)
    try:
        host_pick = SourceFileLoader("host_pick_parity", str(HOST_PICK)).load_module()
    finally:
        sys.path.remove(hp_dir)
    for v in (None, True, "x", "-1", -1, 0, "3.5", float("inf"), float("nan"), 7):
        assert fleet_gate._finite_nonnegative(v) == host_pick._finite_nonnegative(v) or (
            v != v)  # nan compares unequal to itself; both return None anyway
    src = HOST_PICK.read_text()
    # host_pick refuses at or above the PSI ceiling and requires the policy within 1..100.
    assert "io >= max_io" in src and "memory_psi >= max_mem" in src
    assert "1 <= max_io <= 100" in src and "1 <= max_mem <= 100" in src
    gate_src = (FLEET / "fleet_gate.py").read_text()
    for frag in ("io >= max_io", "mem_psi >= max_mem", "1 <= max_io <= 100",
                 "1 <= max_mem <= 100", "pressure-unavailable-or-stale", "invalid-pressure-policy"):
        assert frag in gate_src, frag


# --- sizing -----------------------------------------------------------------------------

@pytest.mark.parametrize("cores,mem,expected", [
    (24, 30, 2), (32, 62, 6), (32, 128, 8), (8, 62, 2), (3, 62, 0), (32, 15, 0), (32, 16, 1),
])
def test_slots_for_host(cores, mem, expected):
    assert fleet_gate.slots_for_host(cores, mem, reserve_gb=8, slot_mem_gb=8) == expected


def test_render_limits_from_conf():
    out = fleet_gate.render_limits(conf(SLOT_MEMORY_MAX="12G", SLOT_CPU_QUOTA="600%"))
    assert "\nMemoryMax=12G\n" in out and "\nCPUQuota=600%\n" in out


# --- nftables egress (P1b) ---------------------------------------------------------------

def test_render_nft_rules():
    out = fleet_gate.render_nft(conf(), 2)
    assert "table inet fleet_ci {" in out
    assert "type filter hook output priority 0; policy accept;" in out
    # idempotent apply: create-if-missing, delete, recreate
    assert out.index("table inet fleet_ci {}") < out.index("delete table inet fleet_ci")
    for n, lo, hi in ((1, 20100, 20199), (2, 20200, 20299)):
        u = f'meta skuid "ghrunner-{n}"'
        assert u in out
        # loopback exception for the slot's own range, tcp AND udp, before the drops
        assert f'{u} ip daddr 127.0.0.0/8 meta l4proto {{ tcp, udp }} th dport {lo}-{hi} accept' in out
        assert f'{u} ip6 daddr ::1/128 meta l4proto {{ tcp, udp }} th dport {lo}-{hi} accept' in out
        # DNS to the resolved stub only, also before the loopback drop
        dns = f'{u} ip daddr 127.0.0.53 meta l4proto {{ tcp, udp }} th dport 53 accept'
        assert dns in out
        v4drop = (f"{u} ip daddr {{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10, "
                  f"169.254.0.0/16, 0.0.0.0/8, 224.0.0.0/4, 240.0.0.0/4, 127.0.0.0/8 }} drop")
        v6drop = f"{u} ip6 daddr {{ fc00::/7, fe80::/10, ::ffff:0:0/96, ff00::/8, ::1/128 }} drop"
        assert v4drop in out
        assert v6drop in out
        # ordering: own-range accept AND DNS accept both precede the loopback drops
        assert out.index(f"th dport {lo}-{hi} accept") < out.index(v4drop)
        assert out.index(dns) < out.index(v4drop)
        assert out.index(dns) < out.index(v6drop)
    assert "ghrunner-3" not in out
    with pytest.raises(ValueError):
        fleet_gate.render_nft(conf(), 33)


def test_render_nft_cli(tmp_path):
    cf = tmp_path / "fleet.conf"
    cf.write_text(CONF.read_text().replace("RUNNER_GROUP_ID=0", "RUNNER_GROUP_ID=7"))
    base = [sys.executable, str(FLEET / "fleet_gate.py"), "--conf", str(cf),
            "--proc-root", str(make_proc(tmp_path))]
    r = subprocess.run(base + ["render-nft", "--slots", "2"], capture_output=True, text=True)
    assert r.returncode == 0 and 'meta skuid "ghrunner-2"' in r.stdout
    r = subprocess.run(base + ["render-nft", "--slots", "0"], capture_output=True, text=True)
    assert r.returncode == 0 and "skuid" not in r.stdout
    r = subprocess.run(base + ["render-nft", "--slots", "33"], capture_output=True, text=True)
    assert r.returncode == fleet_gate.EX_USAGE


def test_bake_list_has_no_database_or_docker():
    doc = DOC.read_text()
    # the bake list excludes both explicitly (they are named only to exclude them)
    assert "**No PostgreSQL, no Docker**" in doc
    assert "no PostgreSQL and no Docker" in doc
    assert "Docker for the `heavy` class is an open item, not implemented" in doc


# --- capacity + router ------------------------------------------------------------------

def runner(name, cls, status="online", busy=False, extra=()):
    labels = ["self-hosted", "Linux", "X64", "fleet", f"fleet-{cls}", *extra]
    return {"name": name, "status": status, "busy": busy, "labels": [{"name": l} for l in labels]}


def job(status="queued", labels=("self-hosted", "Linux", "X64", "fleet", "fleet-std")):
    return {"status": status, "labels": list(labels) if labels is not None else None}


def test_capacity_summary(tmp_path):
    runners = [runner("a", "std"), runner("b", "std"), runner("c", "std", busy=True),
               runner("d", "heavy"), runner("e", "std", status="offline"),
               {"name": "x", "status": "online", "busy": False, "labels": [{"name": "self-hosted"}]},
               runner("f", "std", busy=None)]
    s = capacity_mod.summarize(runners)
    assert s["per_class"]["std"] == {"idle": 2, "busy": 1, "online": 4, "queued": 0}
    assert s["per_class"]["heavy"] == {"idle": 1, "busy": 0, "online": 1, "queued": 0}
    assert (s["idle_slots"], s["busy_slots"], s["online_slots"]) == (3, 1, 5)
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"runners": runners}))
    r = subprocess.run([sys.executable, str(CAPACITY), "--input", str(f)], capture_output=True, text=True)
    assert json.loads(r.stdout)["idle_slots"] == 3


def test_queued_fleet_counts():
    jobs = [job(), job(status="waiting"), job(status="in_progress"),  # in_progress: runner already busy
            job(labels=("fleet", "fleet-heavy")), job(labels=("self-hosted",)),
            job(labels=None), "garbage", {"status": "queued"}]
    assert capacity_mod.queued_fleet_counts(jobs) == {"std": 2, "heavy": 1}


def test_capacity_subtracts_queued_from_idle():
    runners = [runner("a", "std"), runner("b", "std"), runner("d", "heavy")]
    s = capacity_mod.summarize(runners, {"std": 1, "heavy": 0})
    assert s["per_class"]["std"]["idle"] == 1 and s["per_class"]["std"]["queued"] == 1
    assert s["idle_slots"] == 2 and s["queued_fleet_jobs"] == 1
    # clamp at zero: more queued than idle never goes negative
    s = capacity_mod.summarize(runners, {"std": 5, "heavy": 2})
    assert s["per_class"]["std"]["idle"] == 0 and s["per_class"]["heavy"]["idle"] == 0
    assert s["idle_slots"] == 0


def test_capacity_input_with_queued_jobs(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"runners": [runner("a", "std"), runner("b", "std")],
                             "queued_jobs": [job(), job(status="waiting")]}))
    r = subprocess.run([sys.executable, str(CAPACITY), "--input", str(f)], capture_output=True, text=True)
    out = json.loads(r.stdout)
    assert out["ok"] is True and out["idle_slots"] == 0 and out["queued_fleet_jobs"] == 2


def test_capacity_queued_read_failure_is_soft_failure(monkeypatch):
    monkeypatch.setenv("FLEET_ROUTE_TOKEN", "t")

    def fake_get(path, token):
        if "runner-groups" in path:
            return {"runners": [runner("a", "std")], "total_count": 1}
        raise urllib.error.HTTPError("https://api.github.com", 403, "Forbidden", {}, None)

    monkeypatch.setattr(capacity_mod, "_get", fake_get)
    assert capacity_mod.main(["--soft", "--group-id", "7"]) == 0
    # any queued-read failure must fail the WHOLE result (router -> hosted)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        capacity_mod.main(["--soft", "--group-id", "7"])
    assert json.loads(buf.getvalue())["ok"] is False


def test_fetch_queued_jobs_one_page_and_validated(monkeypatch):
    calls = []

    def fake_get(path, token):
        calls.append(path)
        if "/actions/runs?" in path:
            return {"workflow_runs": [{"id": 11, "repository": {"full_name": "org/repo"}}]}
        return {"jobs": [job()]}

    monkeypatch.setattr(capacity_mod, "_get", fake_get)
    jobs = capacity_mod.fetch_queued_fleet_jobs("org", "t")
    assert len(jobs) == 1
    assert all("page=1" in c for c in calls) and len(calls) == 2

    def bad_shape(path, token):
        return {"workflow_runs": [{"id": 11, "repository": {"full_name": "not a full name"}}]}

    monkeypatch.setattr(capacity_mod, "_get", bad_shape)
    with pytest.raises(ValueError):
        capacity_mod.fetch_queued_fleet_jobs("org", "t")


def _runs_page(n):
    return {"workflow_runs": [{"id": i + 1, "repository": {"full_name": "org/repo"}}
                              for i in range(n)]}


def test_queued_saturation_and_job_detail_cap(monkeypatch):
    # a full runs page (100) is saturated -> fail closed
    monkeypatch.setattr(capacity_mod, "_get",
                        lambda p, t: _runs_page(100) if "/actions/runs?" in p else {"jobs": []})
    with pytest.raises(ValueError, match="saturated"):
        capacity_mod.fetch_queued_fleet_jobs("org", "t")
    # more than 20 queued runs hits the job-detail cap -> fail closed
    monkeypatch.setattr(capacity_mod, "_get",
                        lambda p, t: _runs_page(21) if "/actions/runs?" in p else {"jobs": []})
    with pytest.raises(ValueError, match="cap"):
        capacity_mod.fetch_queued_fleet_jobs("org", "t")
    # exactly 20 runs is allowed: 20 job-detail calls, no more
    calls = []

    def get20(path, token):
        calls.append(path)
        return _runs_page(20) if "/actions/runs?" in path else {"jobs": [job()]}

    monkeypatch.setattr(capacity_mod, "_get", get20)
    jobs = capacity_mod.fetch_queued_fleet_jobs("org", "t")
    assert len(jobs) == 20
    assert sum("/jobs?" in c for c in calls) == 20


def test_capacity_saturation_is_soft_failure(monkeypatch):
    monkeypatch.setenv("FLEET_ROUTE_TOKEN", "t")

    def fake_get(path, token):
        if "runner-groups" in path:
            return {"runners": [runner("a", "std")], "total_count": 1}
        return _runs_page(100)

    monkeypatch.setattr(capacity_mod, "_get", fake_get)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = capacity_mod.main(["--soft", "--group-id", "7"])
    assert rc == 0 and json.loads(buf.getvalue())["ok"] is False


def test_capacity_without_token_is_soft_failure():
    env = {k: v for k, v in os.environ.items() if k != "FLEET_ROUTE_TOKEN"}
    r = subprocess.run([sys.executable, str(CAPACITY), "--soft"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is False


CAP = {"ok": True, "per_class": {"std": {"idle": 3, "busy": 1, "online": 4},
                                 "heavy": {"idle": 0, "busy": 2, "online": 2}}}
FLEET_STD = ["self-hosted", "Linux", "X64", "fleet", "fleet-std"]


@pytest.mark.parametrize("mode,cls,jobs,cap,ratio,trusted,expected", [
    ("off", "std", 1, CAP, 1.0, True, "ubuntu-24.04"),
    ("", "std", 1, CAP, 1.0, True, "ubuntu-24.04"),
    ("bogus", "std", 1, CAP, 1.0, True, "ubuntu-24.04"),
    ("fleet-only", "std", 9, None, 1.0, True, FLEET_STD),
    ("hybrid", "std", 3, CAP, 1.0, True, FLEET_STD),
    ("hybrid", "std", 4, CAP, 1.0, True, "ubuntu-24.04"),
    ("hybrid", "std", 4, CAP, 0.5, True, FLEET_STD),        # spill 3/4 >= 0.5
    ("hybrid", "std", 8, CAP, 0.5, True, "ubuntu-24.04"),   # 3/8 < 0.5
    ("hybrid", "heavy", 1, CAP, 0.1, True, "ubuntu-24.04"), # no idle heavy slot
    ("hybrid", "std", 1, None, 1.0, True, "ubuntu-24.04"),
    ("hybrid", "std", 1, {"ok": False}, 1.0, True, "ubuntu-24.04"),
    ("hybrid", "std", 1, {"ok": True, "per_class": {"std": {"idle": "3"}}}, 1.0, True, "ubuntu-24.04"),
    # P0: untrusted source never gets fleet labels, in any mode
    ("fleet-only", "std", 1, CAP, 1.0, False, "ubuntu-24.04"),
    ("hybrid", "std", 1, CAP, 1.0, False, "ubuntu-24.04"),
    ("off", "std", 1, CAP, 1.0, False, "ubuntu-24.04"),
])
def test_router_decisions(mode, cls, jobs, cap, ratio, trusted, expected):
    d = fleet_route.decide(mode, cls, jobs, cap, ratio, trusted_source=trusted)
    assert d["runner"] == expected
    if not trusted and mode in ("hybrid", "fleet-only"):
        assert d["why"] == "untrusted-source"


def test_router_default_is_untrusted_and_repo_private_is_informational():
    # fail closed: no trusted_source argument -> hosted even in fleet-only
    assert fleet_route.decide("fleet-only", "std", 1, CAP)["runner"] == "ubuntu-24.04"
    d = fleet_route.decide("hybrid", "std", 1, CAP, trusted_source=True, repo_private=True)
    assert d["runner"] == FLEET_STD and d["repo_private"] is True and d["trusted_source"] is True


def run_action_step(tmp_path, mode, token="", cap_runners=None, jobs="1", cls="std",
                    trusted="true", queued=(), event_name="push", head_repo="",
                    base_repo="org/repo"):
    """Execute the composite action's bash step as Actions would, with the pinned
    fleet_route.py copy and a stub fleet-capacity when a token is given (no network)."""
    doc = ACTION.read_text()
    m = re.search(r"\n      run: \|\n((?:        .*\n|\n)+)", doc)
    script = "\n".join(l[8:] for l in m.group(1).splitlines())
    action_dir = tmp_path / "action"
    action_dir.mkdir()
    (action_dir / "fleet_route.py").write_text((ACTION_DIR / "fleet_route.py").read_text())
    summary = capacity_mod.summarize(cap_runners or [], capacity_mod.queued_fleet_counts(list(queued)))
    # emulate the real script's contract: no token -> ok=false (router falls back to hosted)
    stub = ("import json, os\n"
            f"summary = {summary!r}\n"
            "if not os.environ.get('FLEET_ROUTE_TOKEN'):\n"
            "    print(json.dumps({'schema': 'mastermind.fleet_capacity.v1', 'ok': False,\n"
            "                      'error': 'FLEET_ROUTE_TOKEN not set'}))\n"
            "else:\n"
            "    print(json.dumps(summary))\n")
    (action_dir / "fleet-capacity").write_text(stub)
    out = tmp_path / "out"
    out.write_text("")
    env = dict(os.environ, FLEET_MODE=mode, FLEET_CLASS_IN=cls, FLEET_JOBS=jobs,
               FLEET_ROUTE_TOKEN=token, FLEET_RUNNER_GROUP_ID="7", FLEET_SPILL_RATIO="1.0",
               FLEET_TRUSTED_SOURCE=trusted, FLEET_REPO_PRIVATE="false",
               FLEET_ACTION_DIR=str(action_dir), GITHUB_OUTPUT=str(out),
               FLEET_EVENT_NAME=event_name, FLEET_HEAD_REPO=head_repo, FLEET_BASE_REPO=base_repo)
    subprocess.run(["bash", "-c", script], check=True, env=env, capture_output=True)
    return dict(l.split("=", 1) for l in out.read_text().splitlines())


@pytest.mark.parametrize("mode,token,runners,expected_target", [
    ("off", "t", [runner("a", "std")], "hosted"),
    ("", "", [], "hosted"),
    ("fleet-only", "", [], "fleet"),
    ("hybrid", "", [runner("a", "std")], "hosted"),      # no token -> hosted
    ("hybrid", "t", [runner("a", "std")], "fleet"),
    ("hybrid", "t", [runner("a", "std", busy=True)], "hosted"),
    ("HYBRID", "t", [runner("a", "std"), runner("b", "std")], "fleet"),
])
def test_action_output_per_mode(tmp_path, mode, token, runners, expected_target):
    out = run_action_step(tmp_path, mode, token, runners)
    assert out["target"] == expected_target
    runs_on = json.loads(out["runner"])
    assert runs_on == ("ubuntu-24.04" if expected_target == "hosted" else FLEET_STD)


@pytest.mark.parametrize("mode,token", [("fleet-only", ""), ("hybrid", "t")])
def test_action_fork_pr_never_gets_fleet(tmp_path, mode, token):
    out = run_action_step(tmp_path, mode, token, [runner("a", "std")], trusted="false")
    assert out["target"] == "hosted" and json.loads(out["runner"]) == "ubuntu-24.04"


@pytest.mark.parametrize("mode,token,event,head,base,caller,expected", [
    # fork PR: caller lies true, the action recomputes false -> hosted (defense in depth)
    ("fleet-only", "", "pull_request", "fork/repo", "org/repo", "true", "hosted"),
    ("hybrid", "t", "pull_request", "fork/repo", "org/repo", "true", "hosted"),
    # same-repo PR: computed true AND caller true -> fleet
    ("fleet-only", "", "pull_request", "org/repo", "org/repo", "true", "fleet"),
    # push: computed true AND caller true -> fleet
    ("fleet-only", "", "push", "", "org/repo", "true", "fleet"),
    # caller false even when computed true -> hosted (AND, not override)
    ("fleet-only", "", "push", "", "org/repo", "false", "hosted"),
    # pull_request with an empty head repo -> fail closed hosted
    ("fleet-only", "", "pull_request", "", "org/repo", "true", "hosted"),
])
def test_action_recomputes_trust_and_ands_caller(tmp_path, mode, token, event, head, base,
                                                 caller, expected):
    out = run_action_step(tmp_path, mode, token, [runner("a", "std")], trusted=caller,
                          event_name=event, head_repo=head, base_repo=base)
    assert out["target"] == expected


def test_action_queued_jobs_reduce_idle(tmp_path):
    out = run_action_step(tmp_path, "hybrid", "t", [runner("a", "std")], queued=[job()])
    assert out["target"] == "hosted"  # 1 idle - 1 queued = 0


def test_action_contract():
    doc = ACTION.read_text()
    assert "using: composite" in doc
    for key in ("mode:", "class:", "jobs_needed:", "token:", "outputs:", "runner:",
                "is_trusted_source:", "repo_private:"):
        assert key in doc
    assert 'default: "off"' in doc
    assert doc.count('default: "false"') >= 2
    # the caller expression is documented on the input
    assert "github.event.pull_request.head.repo.full_name == github.repository" in doc
    assert "github.event.repository.private" in doc
    # the action ALSO recomputes trust from the event context (defense in depth)
    assert "github.event_name" in doc
    assert "github.event.pull_request.head.repo.full_name" in doc
    assert "github.repository" in doc
    # inputs reach the script only via env, never interpolated into the script body
    run_body = doc.split("run: |", 1)[1]
    assert "${{" not in run_body


def test_action_runs_pinned_code_only():
    doc = ACTION.read_text()
    assert "github.action_path" in doc
    assert "../../../" not in doc
    assert "ops/fleet_ci" not in doc.split("run: |", 1)[1]
    assert "mastermindx-market-intelligence/Mastermind/.github/actions/fleet-route@" in doc
    assert "never ./.github/actions/fleet-route" in doc
    run_body = doc.split("run: |", 1)[1]
    assert '"$FLEET_ACTION_DIR/fleet_route.py"' in run_body


def test_action_scripts_are_byte_identical_copies():
    for name in ("fleet_route.py", "fleet-capacity"):
        assert (ACTION_DIR / name).read_bytes() == (FLEET / name).read_bytes(), name


def test_fetch_capacity_uses_the_given_directory(tmp_path):
    (tmp_path / "fleet-capacity").write_text('import json\nprint(json.dumps({"ok": True, "marker": "pinned"}))\n')
    assert fleet_route.fetch_capacity(str(tmp_path))["marker"] == "pinned"
    (tmp_path / "fleet-capacity").write_text("raise SystemExit(1)\n")
    assert fleet_route.fetch_capacity(str(tmp_path)) is None
    assert fleet_route.fetch_capacity(str(tmp_path / "missing")) is None


# --- static security invariants (mirrors the Terminal lane tests) ------------------------

@pytest.mark.parametrize("script", [SLOT, CANARY])
def test_shell_script_parses_and_is_strict(script):
    subprocess.run(["bash", "-n", str(script)], check=True)
    assert "\nset -euo pipefail\n" in script.read_text(encoding="utf-8")


def test_jit_config_never_reaches_argv_or_output():
    code = code_lines(SLOT)
    assert "--jitconfig" not in code
    assert 'ACTIONS_RUNNER_INPUT_JITCONFIG="$jit"' in code
    assert "exec setpriv --reuid=" in code and "--init-groups" in code
    assert 'sudo -u "$u"' not in code and "sudo -H" not in code and "systemd-run" not in code
    assert not re.search(r"(echo|printf|logger|state|die|hold)[^\n]*\$\{?jit\b", code), \
        "the JIT config must never be printed or logged"
    assert code.count("unset jit") >= 3
    # the minter prints only the config and never the token
    mint = code_lines(MINT)
    assert 'sys.stdout.write(data["encoded_jit_config"])' in mint
    assert not re.search(r"print\([^\n]*(token|_token\(\))", mint)
    assert 'TOKEN_PATH = "/etc/fleet-ci/mint/token"' in mint
    # P1c: setpriv, not sudo (setuid refuses under NoNewPrivileges=yes)
    assert "setpriv --reuid=fleetmint --regid=fleetmint --init-groups /usr/local/bin/fleet-mint mint" in code
    assert "sudo -u fleetmint" not in code and "sudo -n -l" not in code


def test_slot_admits_before_minting_and_wipes_every_cycle():
    code = code_lines(SLOT)
    i_wipe = code.index('rm -rf "/home/$u" "$slot"')
    i_admit = code.index("admit --slot")
    i_mint = code.index("fleet-mint mint")
    i_run = code.index("exec setpriv")
    assert i_wipe < i_admit < i_mint < i_run
    assert 'cgroup.kill' in code and "ipcrm --all" in code
    assert "FLEET_PORT_BASE=\"$port_base\"" in code and "port_base=$((20000 + N * 100))" in code
    assert 'TMPDIR="/home/$u/tmp"' in code
    # refused: back off 15 -> 60 without registering
    assert "backoff * 2 > 60 ? 60" in code
    # uncertain registrations hold the slot instead of re-minting
    assert code.count("hold \"") >= 2
    assert '[ -e "$HOLD" ] || [ -e "$HOLD_FALLBACK" ]' in code


def test_slot_identity_spool_and_tarball_checks():
    code = code_lines(SLOT)
    # uid unique; private primary group; no /run/user/$uid before the job
    assert "uid $uid is shared with another account" in code
    assert "primary group is not private" in code
    assert "another account's primary group" in code
    assert '[ ! -e "/run/user/$uid" ]' in code
    # crontab spool must be gone after crontab -r
    assert "survived crontab -r" in code
    # tarball verified against the conf pin BEFORE extraction, every cycle
    assert 'get RUNNER_TARBALL_SHA256' in code
    i_sha = code.index("sha256sum \"$tarball\"")
    i_tar = code.index("tar xzf \"$tarball\"")
    assert i_sha < i_tar
    assert "does not match the fleet.conf pin" in code


def test_unit_and_slice_carry_the_hardening():
    unit = UNIT.read_text(encoding="utf-8")
    for line in ("ExecStart=/usr/local/sbin/fleet-slot %i", "Slice=fleet_ci.slice",
                 "PrivateTmp=yes", "PrivateIPC=yes", "ProtectProc=invisible",
                 "Delegate=yes", "KillMode=control-group", "LimitCORE=0",
                 "NoNewPrivileges=yes", "RestrictSUIDSGID=yes",
                 "Restart=on-failure", "RestartPreventExitStatus=78",
                 "MemoryMax=8G", "CPUQuota=400%",
                 "ReadOnlyPaths=-/var/crash -/var/metrics -/var/lib/BrlAPI"):
        assert f"\n{line}\n" in unit, line
    assert "Restart=always" not in unit
    assert "StartLimitBurst=" in unit
    assert "/sys/fs/cgroup/fleet_ci.slice/fleet-slot@$N.service" in SLOT.read_text()
    assert "hidepid=invisible" in SLOT.read_text()
    assert "\nMemoryMax=" in SLICE.read_text()


# --- hold(), cron/at and sudoers bash logic, extracted into harnesses ---------------------

def run_bash_harness(tmp_path, body: str, defs: str) -> subprocess.CompletedProcess:
    script = tmp_path / "harness.sh"
    script.write_text("#!/bin/bash\nset -euo pipefail\n" + defs + "\n" + body + "\n")
    return subprocess.run(["bash", str(script)], capture_output=True, text=True)


def test_hold_persists_syncs_reads_back_and_exits_78(tmp_path):
    fn = extract(SLOT.read_text(), r"hold\(\) \{.*?\n\}")
    assert "sync" in fn and 'cat "$HOLD"' in fn  # explicit persist + read-back
    lib = tmp_path / "lib"
    run = tmp_path / "run"
    defs = (f'N=1; name="t-fleet-std-1"; STATUS_DIR="{run}"; HOLD="{lib}/hold-1"; '
            f'HOLD_FALLBACK="$STATUS_DIR/hold-1"; HOLD_PERSIST_FALLBACK="{lib}/hold-fallback-1"; '
            f'HOLD_EXIT=78\nstate() {{ :; }}')
    body = fn.replace("/var/lib/fleet-ci", str(lib)) + '\nhold "uncertain registration"'
    r = run_bash_harness(tmp_path, body, defs)
    assert r.returncode == 78, r.stderr
    assert (lib / "hold-1").read_text() == "uncertain registration\n"
    assert not (run / "hold-1").exists()  # primary persisted: no fallback needed
    assert not (lib / "hold-fallback-1").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_hold_persistence_failure_still_stops_and_marks(tmp_path):
    fn = extract(SLOT.read_text(), r"hold\(\) \{.*?\n\}")
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    run = tmp_path / "run"
    defs = (f'N=1; name="t-fleet-std-1"; STATUS_DIR="{run}"; HOLD="{ro}/hold-1"; '
            f'HOLD_FALLBACK="$STATUS_DIR/hold-1"; HOLD_PERSIST_FALLBACK="{ro}/hold-fallback-1"; '
            f'HOLD_EXIT=78\nstate() {{ :; }}')
    body = fn.replace("/var/lib/fleet-ci", str(ro)) + '\nhold "uncertain registration"'
    r = run_bash_harness(tmp_path, body, defs)
    assert r.returncode == 78, r.stderr  # never restart, even without the primary hold
    assert (run / "hold-1").read_text() == "uncertain registration\n"
    assert "HOLD PERSISTENCE FAILED" in r.stderr
    assert "systemctl disable failed" in r.stderr  # disable failure still exits 78


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_hold_persistent_fallback_and_disable_failure(tmp_path):
    # primary hold unwritable, but the persistent /var/lib fallback succeeds; a failed
    # systemctl disable must still exit 78 with both fallback markers written.
    fn = extract(SLOT.read_text(), r"hold\(\) \{.*?\n\}")
    lib = tmp_path / "lib"
    lib.mkdir()
    ro = lib / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    run = tmp_path / "run"
    defs = (f'N=1; name="t-fleet-std-1"; STATUS_DIR="{run}"; HOLD="{ro}/hold-1"; '
            f'HOLD_FALLBACK="$STATUS_DIR/hold-1"; HOLD_PERSIST_FALLBACK="{lib}/hold-fallback-1"; '
            f'HOLD_EXIT=78\nstate() {{ :; }}\nsystemctl() {{ return 1; }}')
    body = fn.replace("/var/lib/fleet-ci", str(lib)) + '\nhold "uncertain registration"'
    r = run_bash_harness(tmp_path, body, defs)
    assert r.returncode == 78, r.stderr
    assert (run / "hold-1").read_text() == "uncertain registration\n"          # /run fallback
    assert (lib / "hold-fallback-1").read_text() == "uncertain registration\n"  # persistent fallback
    assert "systemctl disable failed" in r.stderr


@pytest.mark.parametrize("which", ["primary", "run", "persist"])
def test_startup_hold_check_exits_78(tmp_path, which):
    block = extract(SLOT.read_text(),
                    r'if \[ -e "\$HOLD" \] \|\| \[ -e "\$HOLD_FALLBACK" \] \|\| '
                    r'\[ -e "\$HOLD_PERSIST_FALLBACK" \]; then\n.*?\nfi')
    hold = tmp_path / "hold-1"
    fb = tmp_path / "run-hold-1"
    pf = tmp_path / "persist-hold-1"
    {"primary": hold, "run": fb, "persist": pf}[which].write_text("reconcile me\n")
    defs = (f'N=1; name="t-fleet-std-1"; HOLD="{hold}"; HOLD_FALLBACK="{fb}"; '
            f'HOLD_PERSIST_FALLBACK="{pf}"; HOLD_EXIT=78')
    r = run_bash_harness(tmp_path, block, defs)
    assert r.returncode == 78 and "reconcile" in r.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_cron_at_allow_files_fail_closed(tmp_path):
    loop = extract(SLOT.read_text(), r"for tool in cron at; do\n.*?\ndone")
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "cron.deny").write_text("ghrunner-1\n")
    (etc / "at.deny").write_text("ghrunner-1\n")
    defs = f'u="ghrunner-1"; TEST_ETC="{etc}"\ndie() {{ echo "DIE: $*" >&2; exit 1; }}'
    body = loop.replace("/etc/", "$TEST_ETC/")
    # deny-listed, no allow files -> ok
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # allow file exists but does not list the user -> ok (allow semantics deny them)
    (etc / "cron.allow").write_text("someoneelse\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # allow file lists the user -> refuse
    (etc / "cron.allow").write_text("ghrunner-1\n")
    r = run_bash_harness(tmp_path, body, defs)
    assert r.returncode == 1 and "allow-listed" in r.stderr
    (etc / "cron.allow").unlink()
    (etc / "at.allow").write_text("ghrunner-1\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 1
    (etc / "at.allow").write_text("someoneelse\n")
    (etc / "at.allow").chmod(0o000)
    assert run_bash_harness(tmp_path, body, defs).returncode == 1  # unreadable fails closed
    (etc / "at.allow").chmod(0o644)
    (etc / "cron.deny").unlink()
    assert run_bash_harness(tmp_path, body, defs).returncode == 1  # missing deny fails closed


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_sudoers_check_is_nnp_safe_and_word_bounded(tmp_path):
    loop = extract(SLOT.read_text(), r"for f in /etc/sudoers /etc/sudoers\.d/\*; do\n.*?\ndone")
    etc = tmp_path / "etc"
    etc.mkdir()
    defs = (f'u="ghrunner-1"; uid=1001; ugid=1002; TEST_ETC="{etc}"\n'
            f'die() {{ echo "DIE: $*" >&2; exit 1; }}')
    body = loop.replace("/etc/", "$TEST_ETC/")
    # no sudoers at all (sudo not installed) -> ok
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # a mention of the user refuses
    (etc / "sudoers").write_text("ghrunner-1 ALL=(ALL) NOPASSWD: ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 1
    # the private group form refuses too
    (etc / "sudoers").write_text("%ghrunner-1 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 1
    # a different slot (ghrunner-10) is NOT a mention of ghrunner-1
    (etc / "sudoers").write_text("ghrunner-10 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # numeric uid grant refuses
    (etc / "sudoers").write_text("#1001 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 1
    # numeric gid grant (%#gid) refuses
    (etc / "sudoers").write_text("%#1002 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 1
    # a different numeric uid is word-bounded, not a mention of 1001
    (etc / "sudoers").write_text("#10010 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    (etc / "sudoers").write_text("%#10020 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # a bare numeric gid that is not our uid is not a mention
    (etc / "sudoers").write_text("#1002 ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # unrelated content -> ok
    (etc / "sudoers").write_text("root ALL=(ALL) ALL\n%sudo ALL=(ALL) ALL\n")
    assert run_bash_harness(tmp_path, body, defs).returncode == 0
    # unreadable policy fails closed
    (etc / "sudoers").chmod(0o000)
    assert run_bash_harness(tmp_path, body, defs).returncode == 1


# --- slot range 1-32 and group id ---------------------------------------------------------

def test_slot_number_range_is_1_32_everywhere():
    case_line = extract(SLOT.read_text(), r'case "\$N" in [^\n]+')
    for n in range(0, 40):
        body = f'N={n}\n{case_line}\necho ok'
        r = subprocess.run(["bash", "-c", body], capture_output=True, text=True)
        assert (r.returncode == 0) == (1 <= n <= 32), n
    for name, ok in (("h-fleet-std-1", True), ("h-fleet-std-32", True), ("h-fleet-heavy-9", True),
                     ("h-fleet-std-0", False), ("h-fleet-std-33", False), ("h-fleet-std-99", False)):
        assert bool(mint_mod.NAME_RE.match(name)) is ok, name
    assert fleet_gate.MAX_SLOTS == 32


def test_runner_group_zero_refused():
    r = subprocess.run([sys.executable, str(MINT), "mint", "h-fleet-std-1",
                        "self-hosted,Linux,X64,fleet,fleet-std", "0"], capture_output=True, text=True)
    assert r.returncode == 2
    assert any("RUNNER_GROUP_ID" in e for e in fleet_gate.validate_conf(raw_conf(RUNNER_GROUP_ID="0")))


# --- docs runbooks ------------------------------------------------------------------------

def test_docs_hold_reconciliation_runbook():
    doc = DOC.read_text()
    assert "GET /orgs/{org}/actions/runners?name=<name>" in doc
    assert "DELETE /orgs/{org}/actions/runners/{id}" in doc
    assert "offline" in doc
    assert "rm /var/lib/fleet-ci/hold-N /run/fleet-ci/hold-N" in doc
    assert "RestartPreventExitStatus=78" in doc


def test_docs_jit_env_handoff_canary_item():
    doc = DOC.read_text()
    assert "ACTIONS_RUNNER_INPUT_JITCONFIG" in doc
    assert "unsets the variable" in doc or "unsetting the variable" in doc
    assert "Canary checklist" in doc
    assert "pinned runner version" in doc


def test_docs_trusted_source_and_pinned_ref():
    doc = DOC.read_text()
    assert "github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository" in doc
    assert "private" in doc and "no outside forks" in doc
    assert "never from the caller's checkout" in doc or "never from\nthe caller's checkout" in doc
    assert "byte-identical copies" in doc


# --- canary isolation harness (M2) ---------------------------------------------------------

CANARY_CHECKS = ["proc-cross-read", "shm-cross-read", "home-cross-read", "port-range-egress",
                 "lan-egress-denied", "internet-egress-allowed", "sudo-denied", "wipe-residue"]


def test_canary_list_checks():
    r = subprocess.run([str(CANARY), "--list-checks"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.split() == CANARY_CHECKS


def test_canary_harness_static_contract():
    code = CANARY.read_text()
    assert '[ "$(id -u)" = 0 ]' in code                     # root only
    assert "nft list table inet fleet_ci" in code           # rules must be loaded
    assert "setpriv --reuid=" in code                       # probes run as the slot users
    assert "hidepid=invisible" in code                      # /proc isolation precondition
    assert 'echo "PASS: $1"' in code and 'echo "FAIL: $1' in code
    assert "exit 1" in code                                 # nonzero on any FAIL
    for frag in ("/dev/shm/fleet-canary-", "/home/$ub", "sudo -n true",
                 "pkill -KILL -u", "crontab -r -u", "/run/user/$uida",
                 'find "$d" -xdev -user "$ua" -delete'):
        assert frag in code, frag
    # slot range and distinct slots enforced
    assert "1-32" in code and "A and B must be different slots" in code
    # /proc cross-read never remounts the host: private namespace or WARN
    assert "unshare --mount --pid --fork" in code
    assert "mount -t proc -o hidepid=invisible proc /proc" in code
    assert "WARN: proc-cross-read" in code
    assert "mount -o remount" not in code   # no host /proc remount command remains
    assert "RESTORE_PROC" not in code       # no host-state restore machinery


# Protocol constants required by the nft egress rules: RFC1918 / loopback / CGNAT /
# multicast / reserved ranges and the systemd-resolved stub. These are public address
# ranges, not host identities; every other dotted-quad literal is refused.
ALLOWED_IP_LITERALS = {
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
    "169.254.0.0/16", "0.0.0.0/8", "224.0.0.0/4", "240.0.0.0/4",
    "127.0.0.0/8", "127.0.0.53",
}


def test_public_repo_carries_no_real_host_identity():
    for path in (DOC, CONF, UNIT, SLOT, ACTION, CANARY, MINT, CAPACITY,
                 FLEET / "fleet_gate.py", FLEET / "fleet_route.py",
                 ACTION_DIR / "fleet_route.py", ACTION_DIR / "fleet-capacity",
                 Path(__file__)):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b", text):
            assert m.group(0) in ALLOWED_IP_LITERALS, (path, m.group(0))
        assert not re.search(r"\bubuntu[0-9]\b", text), path
        # a real home path leaks a user name; the bare guard pattern below does not
        assert not re.search(r"/Users/[A-Za-z0-9_.-]+", text), path
