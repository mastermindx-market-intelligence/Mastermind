"""Fleet CI slot pool (ops/fleet_ci/, docs/FLEET_CI_POOL.md).

The slot loop and unit run as root on fleet hosts and are not executed here; these
tests pin admission decisions on fixture /proc text, the sizing rule, the router, the
composite action's output per mode, parity with the Fabric host placer's gate
semantics, and the static invariants that keep the JIT config out of argv and logs.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
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
ACTION = ROOT / ".github" / "actions" / "fleet-route" / "action.yml"
DOC = ROOT / "docs" / "FLEET_CI_POOL.md"
HOST_PICK = ROOT / "ops" / "native_fabric" / "quota_continuity" / "source" / "host_pick.py"

sys.path.insert(0, str(FLEET))
import fleet_gate  # noqa: E402
import fleet_route  # noqa: E402

capacity_mod = SourceFileLoader("fleet_capacity_under_test", str(CAPACITY)).load_module()


def code_lines(path: Path) -> str:
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                     if not l.lstrip().startswith("#"))


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


def conf(**over) -> dict:
    c = fleet_gate.parse_conf(CONF.read_text(encoding="utf-8"))
    c["RUNNER_GROUP_ID"] = "7"
    c.update({k: str(v) for k, v in over.items()})
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
    assert {g["gate"] for g in gates} == {"fresh", "pressure", "memory", "load"}


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


def test_stale_observation_and_invalid_policy_fail_closed(tmp_path):
    obs = fleet_gate.observe(str(make_proc(tmp_path)), cores=32)
    obs["observed_at"] = time.time() - 60
    ok, gates = fleet_gate.evaluate_admission(obs, fleet_gate.policy_from_conf(conf()), 0)
    assert not ok and gate_of(gates, "fresh")["result"] == "FAIL"
    obs["observed_at"] = time.time()
    pol = fleet_gate.policy_from_conf(conf())
    pol["mem_psi_max"] = 0.5  # outside 1..100, as host_pick's policy_valid
    ok, gates = fleet_gate.evaluate_admission(obs, pol, 0)
    assert not ok and gate_of(gates, "pressure")["detail"] == "invalid-pressure-policy"


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
    cf.write_text("FLEET_CLASS=std\nRUNNER_GROUP_ID=7\nMEM_PSI_MAX=0\n")
    r = subprocess.run(base + ["get", "FLEET_CLASS"], capture_output=True, text=True)
    assert r.returncode == fleet_gate.EX_USAGE


def test_conf_refuses_unknown_keys():
    with pytest.raises(ValueError):
        fleet_gate.parse_conf("SLOTS=2\nEVIL=$(rm -rf /)\n")


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


# --- capacity + router ------------------------------------------------------------------

def runner(name, cls, status="online", busy=False, extra=()):
    labels = ["self-hosted", "Linux", "X64", "fleet", f"fleet-{cls}", *extra]
    return {"name": name, "status": status, "busy": busy, "labels": [{"name": l} for l in labels]}


def test_capacity_summary(tmp_path):
    runners = [runner("a", "std"), runner("b", "std"), runner("c", "std", busy=True),
               runner("d", "heavy"), runner("e", "std", status="offline"),
               {"name": "x", "status": "online", "busy": False, "labels": [{"name": "self-hosted"}]},
               runner("f", "std", busy=None)]
    s = capacity_mod.summarize(runners)
    assert s["per_class"]["std"] == {"idle": 2, "busy": 1, "online": 4}
    assert s["per_class"]["heavy"] == {"idle": 1, "busy": 0, "online": 1}
    assert (s["idle_slots"], s["busy_slots"], s["online_slots"]) == (3, 1, 5)
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"runners": runners}))
    r = subprocess.run([sys.executable, str(CAPACITY), "--input", str(f)], capture_output=True, text=True)
    assert json.loads(r.stdout)["idle_slots"] == 3


def test_capacity_without_token_is_soft_failure():
    env = {k: v for k, v in os.environ.items() if k != "FLEET_ROUTE_TOKEN"}
    r = subprocess.run([sys.executable, str(CAPACITY), "--soft"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is False


CAP = {"ok": True, "per_class": {"std": {"idle": 3, "busy": 1, "online": 4},
                                 "heavy": {"idle": 0, "busy": 2, "online": 2}}}
FLEET_STD = ["self-hosted", "Linux", "X64", "fleet", "fleet-std"]


@pytest.mark.parametrize("mode,cls,jobs,cap,ratio,expected", [
    ("off", "std", 1, CAP, 1.0, "ubuntu-24.04"),
    ("", "std", 1, CAP, 1.0, "ubuntu-24.04"),
    ("bogus", "std", 1, CAP, 1.0, "ubuntu-24.04"),
    ("fleet-only", "std", 9, None, 1.0, FLEET_STD),
    ("hybrid", "std", 3, CAP, 1.0, FLEET_STD),
    ("hybrid", "std", 4, CAP, 1.0, "ubuntu-24.04"),
    ("hybrid", "std", 4, CAP, 0.5, FLEET_STD),        # spill 3/4 >= 0.5
    ("hybrid", "std", 8, CAP, 0.5, "ubuntu-24.04"),   # 3/8 < 0.5
    ("hybrid", "heavy", 1, CAP, 0.1, "ubuntu-24.04"), # no idle heavy slot
    ("hybrid", "std", 1, None, 1.0, "ubuntu-24.04"),
    ("hybrid", "std", 1, {"ok": False}, 1.0, "ubuntu-24.04"),
    ("hybrid", "std", 1, {"ok": True, "per_class": {"std": {"idle": "3"}}}, 1.0, "ubuntu-24.04"),
])
def test_router_decisions(mode, cls, jobs, cap, ratio, expected):
    assert fleet_route.decide(mode, cls, jobs, cap, ratio)["runner"] == expected


def run_action_step(tmp_path, mode, token="", cap_runners=None, jobs="1", cls="std"):
    """Execute the composite action's bash step as Actions would, with a stub
    fleet-capacity when a token is given (no network)."""
    doc = ACTION.read_text()
    m = re.search(r"\n      run: \|\n((?:        .*\n|\n)+)", doc)
    script = "\n".join(l[8:] for l in m.group(1).splitlines())
    fleet_dir = tmp_path / "fleet"
    fleet_dir.mkdir()
    (fleet_dir / "fleet_route.py").write_text((FLEET / "fleet_route.py").read_text())
    stub = ("import json,sys\nprint(json.dumps({'ok': True, 'per_class': "
            + repr(capacity_mod.summarize(cap_runners or [])["per_class"]) + "}))\n")
    (fleet_dir / "fleet-capacity").write_text(stub)
    out = tmp_path / "out"
    out.write_text("")
    env = dict(os.environ, FLEET_MODE=mode, FLEET_CLASS_IN=cls, FLEET_JOBS=jobs,
               FLEET_ROUTE_TOKEN=token, FLEET_RUNNER_GROUP_ID="7", FLEET_SPILL_RATIO="1.0",
               FLEET_DIR=str(fleet_dir), GITHUB_OUTPUT=str(out))
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


def test_action_contract():
    doc = ACTION.read_text()
    assert "using: composite" in doc
    for key in ("mode:", "class:", "jobs_needed:", "token:", "outputs:", "runner:"):
        assert key in doc
    assert 'default: "off"' in doc
    # inputs reach the script only via env, never interpolated into the script body
    run_body = doc.split("run: |", 1)[1]
    assert "${{" not in run_body


# --- static security invariants (mirrors the Terminal lane tests) ------------------------

@pytest.mark.parametrize("script", [SLOT])
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
    assert "sudo -u fleetmint /usr/local/bin/fleet-mint mint" in code


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
    assert code.count("hold \"") >= 2 and '[ ! -e "$HOLD" ]' in code


def test_unit_and_slice_carry_the_hardening():
    unit = UNIT.read_text(encoding="utf-8")
    for line in ("ExecStart=/usr/local/sbin/fleet-slot %i", "Slice=fleet_ci.slice",
                 "PrivateTmp=yes", "PrivateIPC=yes", "ProtectProc=invisible",
                 "Delegate=yes", "KillMode=control-group", "LimitCORE=0",
                 "Restart=always", "MemoryMax=8G", "CPUQuota=400%",
                 "ReadOnlyPaths=-/var/crash -/var/metrics -/var/lib/BrlAPI"):
        assert f"\n{line}\n" in unit, line
    assert "StartLimitBurst=" in unit
    assert "/sys/fs/cgroup/fleet_ci.slice/fleet-slot@$N.service" in SLOT.read_text()
    assert "hidepid=invisible" in SLOT.read_text()
    assert "\nMemoryMax=" in SLICE.read_text()


def test_public_repo_carries_no_real_host_identity():
    for path in (DOC, CONF, UNIT, SLOT, ACTION):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text), path
        assert not re.search(r"\bubuntu[0-9]\b", text), path
        assert "/Users/" not in text, path
