#!/usr/bin/python3 -I
"""Fleet CI slot pool: load-aware admission, slot status and host sizing (stdlib only).

Installed on each fleet host as /usr/local/lib/fleet-ci/fleet_gate.py and called by
`fleet-slot` (docs/FLEET_CI_POOL.md). Never handles a credential or a JIT config.

  admit  --slot N                  evaluate the gates under the host admission lock; on
                                   PASS record this slot as `claimed` (exit 0), on FAIL
                                   record `refused` (exit 10). Prints one JSON line.
  status --slot N --state S [--detail D]
                                   atomically replace the slot status file; print it.
  get KEY                          print one validated config value (for the bash loop).
  slots                            print the slots_for_host() sizing for this host.
  render-limits                    print the systemd drop-in carrying MemoryMax/CPUQuota.
  render-nft [--slots N]           print the per-slot nftables egress ruleset.

Gate semantics vs the Fabric host placer
(ops/native_fabric/quota_continuity/source/host_pick.py, evaluate_hosts): the number
coercion (_as_float/_finite_nonnegative), the pressure policy validity (each PSI
ceiling within 1..100 percent), "at or above a PSI ceiling refuses", "available memory
at or above the floor passes" and "missing/unparsable fails closed" are copied; the
host placer is not importable on fleet hosts, so the small pure functions are copied
and tests/test_fleet_ci_pool.py checks parity. Deliberate differences: the fleet
memory floor scales with busy slots (floor x (busy+1)); the fleet load gate is
per-core (load1/cores < LOAD_MAX) where host_pick uses absolute load1 < load_gate;
and there is NO freshness gate — host_pick's fresh gate guards stored probe state
(max_age), while the fleet observes live in the same call, so a freshness check here
would be tautological. See docs/FLEET_CI_POOL.md.

Exit codes: 0 admitted / ok; 10 refused by a gate; 2 bad config or usage.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "mastermind.fleet_slot_status.v1"
EX_REFUSED = 10
EX_USAGE = 2
CLASSES = ("std", "heavy")
# Slot states. `claimed`/`minting`/`registered` hold host capacity: they count as busy
# for the next slot's memory floor. A slot registered with GitHub waits for exactly one
# job, so an idle registration is reserved capacity, not free capacity.
BUSY_STATES = frozenset({"claimed", "minting", "registered"})
STATES = BUSY_STATES | frozenset({"starting", "refused", "exited", "wiping", "stopped"})
MAX_SLOTS = 32
PORT_BASE = 20000
PORT_SPAN = 100

DEFAULTS: Dict[str, str] = {
    "FLEET_CLASS": "std",
    "RUNNER_GROUP_ID": "",
    "SLOTS": "auto",
    "SLOT_MEM_GB": "8",
    "RESERVE_GB": "8",
    "SLOT_MEM_FLOOR_GB": "6",
    "MEM_PSI_MAX": "10",
    "IO_PSI_MAX": "20",
    "LOAD_MAX": "0.85",
    "SLOT_MEMORY_HIGH": "7G",
    "SLOT_MEMORY_MAX": "8G",
    "SLOT_CPU_QUOTA": "400%",
    # SHA-256 of the pinned runner tarball. Empty/invalid = no pin = the slot refuses
    # to start; the example conf ships an all-zero placeholder that matches nothing.
    "RUNNER_TARBALL_SHA256": "",
    # A `claimed` status file older than this many seconds no longer holds capacity:
    # the slot died between admitting and minting. Default 6h matches the GitHub job
    # timeout. Stale claims are ignored by count_busy and reported in status output.
    "STALE_CLAIM_S": "21600",
}


# --- copied from host_pick.py (keep identical semantics) ---------------------------------

def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _finite_nonnegative(value: Any) -> Optional[float]:
    number = _as_float(value)
    return number if number is not None and number >= 0 and math.isfinite(number) else None


def _gate(name: str, ok: bool, label: str, detail: str = "") -> Dict[str, str]:
    return {"host": name, "gate": label, "result": "PASS" if ok else "FAIL", "detail": detail}


# --- procfs parsing ----------------------------------------------------------------------

def parse_psi(text: str) -> Dict[str, Dict[str, float]]:
    """`some avg10=1.00 avg60=...` lines -> {"some": {"avg10": 1.0, ...}, "full": {...}}."""
    out: Dict[str, Dict[str, float]] = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts or parts[0] not in ("some", "full"):
            continue
        fields: Dict[str, float] = {}
        for kv in parts[1:]:
            key, sep, raw = kv.partition("=")
            num = _finite_nonnegative(raw) if sep else None
            if num is not None:
                fields[key] = num
        out[parts[0]] = fields
    return out


def parse_meminfo(text: str) -> Dict[str, int]:
    """/proc/meminfo -> {field: kB}."""
    out: Dict[str, int] = {}
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        tok = rest.split()
        if tok and tok[0].isdigit():
            out[key.strip()] = int(tok[0])
    return out


def parse_loadavg(text: str) -> Optional[float]:
    tok = text.split()
    return _finite_nonnegative(tok[0]) if tok else None


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="ascii", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def observe(proc_root: str = "/proc", cores: Optional[int] = None) -> Dict[str, Any]:
    """One live observation of the host. Missing pieces stay None and fail closed."""
    obs: Dict[str, Any] = {"observed_at": time.time()}
    for res in ("memory", "io", "cpu"):
        text = _read(os.path.join(proc_root, "pressure", res))
        psi = parse_psi(text) if text is not None else {}
        obs[f"{res}_psi_some10"] = psi.get("some", {}).get("avg10")
    mem_text = _read(os.path.join(proc_root, "meminfo"))
    mem = parse_meminfo(mem_text) if mem_text is not None else {}
    obs["mem_available_gb"] = mem["MemAvailable"] / 1048576 if "MemAvailable" in mem else None
    obs["mem_total_gb"] = mem["MemTotal"] / 1048576 if "MemTotal" in mem else None
    load_text = _read(os.path.join(proc_root, "loadavg"))
    obs["load1"] = parse_loadavg(load_text) if load_text is not None else None
    obs["cores"] = cores if cores is not None else os.cpu_count()
    return obs


# --- config ------------------------------------------------------------------------------

def parse_conf(text: str) -> Dict[str, str]:
    """KEY=VALUE lines; `#` comments; no shell expansion (the file is never sourced)."""
    conf = dict(DEFAULTS)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or key not in DEFAULTS:
            raise ValueError(f"unknown or malformed config line: {key or line[:20]}")
        conf[key] = value.strip().strip('"')
    return conf


def policy_from_conf(conf: Dict[str, str]) -> Dict[str, Any]:
    return {
        "mem_psi_max": _finite_nonnegative(conf.get("MEM_PSI_MAX")),
        "io_psi_max": _finite_nonnegative(conf.get("IO_PSI_MAX")),
        "slot_mem_floor_gb": _finite_nonnegative(conf.get("SLOT_MEM_FLOOR_GB")),
        "load_max": _finite_nonnegative(conf.get("LOAD_MAX")),
    }


def validate_conf(conf: Dict[str, str]) -> List[str]:
    errors = []
    if conf.get("FLEET_CLASS") not in CLASSES:
        errors.append("FLEET_CLASS must be std or heavy")
    gid = conf.get("RUNNER_GROUP_ID", "")
    if not gid.isdigit() or int(gid) <= 0:
        errors.append("RUNNER_GROUP_ID must be a positive integer (0 is refused)")
    if not re.fullmatch(r"[0-9a-f]{64}", conf.get("RUNNER_TARBALL_SHA256", "")):
        errors.append("RUNNER_TARBALL_SHA256 must be the pinned tarball's 64-hex-digit SHA-256; no pin = refuse")
    stale = _finite_nonnegative(conf.get("STALE_CLAIM_S"))
    if stale is None or stale <= 0:
        errors.append("STALE_CLAIM_S must be a positive number of seconds")
    slots = conf.get("SLOTS", "")
    if slots != "auto" and not (slots.isdigit() and 0 <= int(slots) <= MAX_SLOTS):
        errors.append(f"SLOTS must be auto or 0..{MAX_SLOTS}")
    for key in ("SLOT_MEM_GB", "RESERVE_GB"):
        if _finite_nonnegative(conf.get(key)) is None:
            errors.append(f"{key} must be a nonnegative number")
    if not (_finite_nonnegative(conf.get("SLOT_MEM_GB")) or 0) > 0:
        errors.append("SLOT_MEM_GB must be positive")
    pol = policy_from_conf(conf)
    for key in ("mem_psi_max", "io_psi_max"):
        if pol[key] is None or not 1 <= pol[key] <= 100:
            errors.append(f"{key.upper()} must be within 1..100 (host_pick pressure policy)")
    if pol["slot_mem_floor_gb"] is None:
        errors.append("SLOT_MEM_FLOOR_GB must be a nonnegative number")
    if pol["load_max"] is None or pol["load_max"] <= 0:
        errors.append("LOAD_MAX must be a positive number")
    for key in ("SLOT_MEMORY_HIGH", "SLOT_MEMORY_MAX"):
        v = conf.get(key, "")
        if not (v[:-1].isdigit() and v[-1:] in ("M", "G")):
            errors.append(f"{key} must look like 7G or 7168M")
    q = conf.get("SLOT_CPU_QUOTA", "")
    if not (q.endswith("%") and q[:-1].isdigit() and int(q[:-1]) > 0):
        errors.append("SLOT_CPU_QUOTA must look like 400%")
    return errors


# --- sizing ------------------------------------------------------------------------------

def slots_for_host(cores: int, mem_total_gb: float, reserve_gb: float, slot_mem_gb: float) -> int:
    """min(cores // 4, (MemTotal_GB - reserve_GB) // SLOT_MEM_GB), never below 0.

    Four cores per slot keeps a typical test job (pytest -n auto inside a 400% CPU quota)
    from oversubscribing the host; the reserve keeps headroom for the host's other
    services. A host too small for one slot gets 0 (it does not join the pool).
    """
    if cores <= 0 or slot_mem_gb <= 0:
        return 0
    by_cpu = cores // 4
    by_mem = int(max(0.0, mem_total_gb - reserve_gb) // slot_mem_gb)
    return max(0, min(by_cpu, by_mem, MAX_SLOTS))


# --- admission ---------------------------------------------------------------------------

def evaluate_admission(obs: Dict[str, Any], policy: Dict[str, Any], busy_slots: int,
                       host: str = "localhost") -> Tuple[bool, List[Dict[str, str]]]:
    """All gates for registering ONE more runner on this host. Every gate must PASS.

    No freshness gate: observe() runs in this same call, so an age check would be
    tautological (host_pick's fresh gate guards stored probe state, not live reads).
    """
    gates: List[Dict[str, str]] = []
    max_io, max_mem = policy.get("io_psi_max"), policy.get("mem_psi_max")
    policy_valid = (max_io is not None and 1 <= max_io <= 100
                    and max_mem is not None and 1 <= max_mem <= 100)
    io = _finite_nonnegative(obs.get("io_psi_some10"))
    mem_psi = _finite_nonnegative(obs.get("memory_psi_some10"))
    if not policy_valid:
        ok, why = False, "invalid-pressure-policy"
    elif io is None or mem_psi is None:
        ok, why = False, "pressure-unavailable-or-stale"
    elif io >= max_io:
        ok, why = False, f"io_psi_some10={io:g}>={max_io:g}%"
    elif mem_psi >= max_mem:
        ok, why = False, f"memory_psi_some10={mem_psi:g}>={max_mem:g}%"
    else:
        ok, why = True, f"io_psi={io:g}<{max_io:g}%,mem_psi={mem_psi:g}<{max_mem:g}%"
    gates.append(_gate(host, ok, "pressure", why))

    floor = policy.get("slot_mem_floor_gb")
    avail = _finite_nonnegative(obs.get("mem_available_gb"))
    busy = busy_slots if isinstance(busy_slots, int) and busy_slots >= 0 else None
    if floor is None or avail is None or busy is None:
        gates.append(_gate(host, False, "memory", "missing_or_invalid"))
    else:
        need = floor * (busy + 1)
        gates.append(_gate(host, avail >= need, "memory",
                           f"{avail:.1f}>={need:g} (floor={floor:g}x{busy + 1})"
                           if avail >= need else f"{avail:.1f}<{need:g} (floor={floor:g}x{busy + 1})"))

    load_max = policy.get("load_max")
    load1 = _finite_nonnegative(obs.get("load1"))
    cores = obs.get("cores")
    cores = cores if isinstance(cores, int) and not isinstance(cores, bool) and cores > 0 else None
    if load_max is None or load_max <= 0 or load1 is None or cores is None:
        gates.append(_gate(host, False, "load", "missing_or_invalid"))
    else:
        per_core = load1 / cores
        gates.append(_gate(host, per_core < load_max, "load",
                           f"load1/cores={per_core:.2f}{'<' if per_core < load_max else '>='}{load_max:g}"))
    return all(g["result"] == "PASS" for g in gates), gates


# --- slot status files -------------------------------------------------------------------

def status_path(status_dir: str, slot: int) -> str:
    return os.path.join(status_dir, f"slot-{slot}.json")


def write_status(status_dir: str, slot: int, state: str, cls: str, detail: Any = "") -> Dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"unknown state {state}")
    record = {"schema": SCHEMA, "slot": slot, "class": cls, "state": state,
              "ts": round(time.time(), 3), "port_base": PORT_BASE + slot * PORT_SPAN,
              "pid": os.getpid(), "detail": detail}
    os.makedirs(status_dir, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=status_dir, prefix=f".slot-{slot}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        os.chmod(tmp, 0o644)  # not secret: the router and T3 read slot state
        os.replace(tmp, status_path(status_dir, slot))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return record


def _claim_age(ts: Any, path: str, now: float) -> Optional[float]:
    """Age of a status record in seconds: its `ts` field, else the file mtime. None when
    neither is usable (the caller then keeps counting the slot as busy, fail closed)."""
    t = _finite_nonnegative(ts)
    if t is None:
        try:
            t = os.path.getmtime(path)
        except OSError:
            return None
    return now - t


def _scan_status(status_dir: str, exclude_slot: int, max_age_s: float,
                 now: Optional[float] = None) -> Tuple[int, List[int]]:
    """(busy count, stale claimed slots). A `claimed` file older than max_age_s no longer
    holds capacity (the slot died between admitting and minting) and is reported stale;
    every other busy state still counts regardless of age. Unreadable/malformed = busy."""
    now = time.time() if now is None else now
    busy = 0
    stale: List[int] = []
    try:
        names = os.listdir(status_dir)
    except FileNotFoundError:
        return 0, []
    for name in names:
        if not (name.startswith("slot-") and name.endswith(".json")):
            continue
        num = name[5:-5]
        if not num.isdigit():
            continue
        slot = int(num)
        path = os.path.join(status_dir, name)
        try:
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
            state = rec.get("state") if isinstance(rec, dict) else None
            ts = rec.get("ts") if isinstance(rec, dict) else None
        except (OSError, ValueError):
            state, ts = None, None
        if state == "claimed":
            age = _claim_age(ts, path, now)
            if age is not None and age > max_age_s:
                stale.append(slot)
                continue
        if slot == exclude_slot:
            continue
        if state is None or state not in STATES or state in BUSY_STATES:
            busy += 1
    return busy, sorted(stale)


def count_busy(status_dir: str, exclude_slot: int, max_age_s: float = 21600.0,
               now: Optional[float] = None) -> int:
    """Other slots holding capacity, ignoring stale `claimed` files (default max age 6h,
    the GitHub job timeout). An unreadable or malformed file counts as busy."""
    busy, _ = _scan_status(status_dir, exclude_slot, max_age_s, now)
    return busy


def admit(conf: Dict[str, str], slot: int, status_dir: str, proc_root: str,
          cores: Optional[int] = None) -> Tuple[bool, Dict[str, Any]]:
    """Evaluate and record under one host-wide lock, so two slots cannot both claim the
    same headroom between reading the busy count and writing `claimed`."""
    os.makedirs(status_dir, mode=0o755, exist_ok=True)
    max_age = _finite_nonnegative(conf.get("STALE_CLAIM_S")) or 21600.0
    with open(os.path.join(status_dir, ".admit.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        busy, stale = _scan_status(status_dir, slot, max_age)
        obs = observe(proc_root, cores)
        ok, gates = evaluate_admission(obs, policy_from_conf(conf), busy)
        detail = {"busy_slots": busy, "stale_claims": stale,
                  "cpu_psi_some10": obs.get("cpu_psi_some10"),
                  "gates": [{k: g[k] for k in ("gate", "result", "detail")} for g in gates]}
        rec = write_status(status_dir, slot, "claimed" if ok else "refused", conf["FLEET_CLASS"], detail)
    return ok, rec


def render_limits(conf: Dict[str, str]) -> str:
    return ("# Generated by fleet_gate.py render-limits from /etc/fleet-ci/fleet.conf\n"
            "[Service]\n"
            f"MemoryHigh={conf['SLOT_MEMORY_HIGH']}\n"
            f"MemoryMax={conf['SLOT_MEMORY_MAX']}\n"
            f"CPUQuota={conf['SLOT_CPU_QUOTA']}\n")


# --- per-slot egress (nftables) -----------------------------------------------------------
# Denied destinations for every slot uid: RFC1918/LAN, link-local, CGNAT, this-network
# (0/8), multicast (224/4) and reserved (240/4); IPv6 ULA, link-local, IPv4-mapped
# (::ffff:0:0/96) and multicast (ff00::/8); plus the host's loopback services. Two
# loopback exceptions, both placed BEFORE the loopback drop: the slot's own port range
# (PORT_BASE + N*PORT_SPAN .. +PORT_SPAN-1) so a job can reach the servers it starts
# itself, and DNS to the systemd-resolved stub (127.0.0.53:53, udp+tcp) only. Everything
# else (the internet) is accepted by the chain policy. These are public address ranges,
# not host identity. `meta skuid` matches the socket owner, so the rules bind to the slot
# account regardless of which process or port it uses; nft resolves the user names at
# load time, so provisioning must create the accounts before applying the ruleset.

DENY_V4 = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
           "169.254.0.0/16", "0.0.0.0/8", "224.0.0.0/4", "240.0.0.0/4")
DENY_V6 = ("fc00::/7", "fe80::/10", "::ffff:0:0/96", "ff00::/8")
LOOPBACK_V4 = "127.0.0.0/8"
LOOPBACK_V6 = "::1/128"
# systemd-resolved stub listener; the only non-own-range loopback destination allowed.
DNS_RESOLVER_V4 = "127.0.0.53"


def render_nft(conf: Dict[str, str], slots: int) -> str:
    """Idempotent nftables ruleset for slots 1..`slots` (create/delete/recreate table)."""
    if not 0 <= slots <= MAX_SLOTS:
        raise ValueError(f"slots must be 0..{MAX_SLOTS}")
    lines = [
        "# Generated by fleet_gate.py render-nft from /etc/fleet-ci/fleet.conf.",
        "# Apply with: nft -f <file>   (idempotent: rebuilds table inet fleet_ci).",
        "# Per-slot egress: internet allowed; RFC1918/LAN, link-local, CGNAT 100.64/10,",
        "# this-net 0/8, multicast 224/4, reserved 240/4, IPv6 ULA/link-local/mapped/mcast",
        "# and host loopback denied, except the slot's own port range and DNS to 127.0.0.53.",
        "table inet fleet_ci {}",
        "delete table inet fleet_ci",
        "table inet fleet_ci {",
        "    chain egress {",
        "        type filter hook output priority 0; policy accept;",
        # First rule: admit reply/established traffic of connections the per-slot rules
        # below already allowed. A slot's own in-range server replies (e.g. SYN-ACK) to
        # the client's ephemeral port, which is outside the slot range; without this the
        # loopback drop kills that reply. New connections are STILL filtered per slot:
        # their first packet is ct state new, so it falls through to the rules below and
        # a new connection to a denied range is dropped. This never admits a new outbound
        # connection to a denied range, only reply/established/related traffic.
        "        ct state established,related accept",
    ]
    for n in range(1, slots + 1):
        u = f"ghrunner-{n}"
        lo = PORT_BASE + n * PORT_SPAN
        hi = lo + PORT_SPAN - 1
        v4 = ", ".join(DENY_V4 + (LOOPBACK_V4,))
        v6 = ", ".join(DENY_V6 + (LOOPBACK_V6,))
        lines += [
            f"        # slot {n}: loopback only inside its own port range {lo}-{hi}, plus DNS",
            f'        meta skuid "{u}" ip daddr {LOOPBACK_V4} meta l4proto {{ tcp, udp }} th dport {lo}-{hi} accept',
            f'        meta skuid "{u}" ip6 daddr {LOOPBACK_V6} meta l4proto {{ tcp, udp }} th dport {lo}-{hi} accept',
            # DNS to the resolved stub only; MUST precede the loopback drop below.
            f'        meta skuid "{u}" ip daddr {DNS_RESOLVER_V4} meta l4proto {{ tcp, udp }} th dport 53 accept',
            f'        meta skuid "{u}" ip daddr {{ {v4} }} drop',
            f'        meta skuid "{u}" ip6 daddr {{ {v6} }} drop',
        ]
    lines += ["    }", "}", ""]
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------------------

def _load(path: str) -> Dict[str, str]:
    text = _read(path)
    if text is None:
        raise ValueError(f"config {path} unreadable")
    conf = parse_conf(text)
    errors = validate_conf(conf)
    if errors:
        raise ValueError("; ".join(errors))
    return conf


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="fleet_gate")
    p.add_argument("--conf", default=os.environ.get("FLEET_CONF", "/etc/fleet-ci/fleet.conf"))
    p.add_argument("--status-dir", default=os.environ.get("FLEET_STATUS_DIR", "/run/fleet-ci"))
    p.add_argument("--proc-root", default=os.environ.get("FLEET_PROC_ROOT", "/proc"))
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("admit"); a.add_argument("--slot", type=int, required=True)
    s = sub.add_parser("status"); s.add_argument("--slot", type=int, required=True)
    s.add_argument("--state", required=True); s.add_argument("--detail", default="")
    g = sub.add_parser("get"); g.add_argument("key")
    sub.add_parser("slots")
    sub.add_parser("render-limits")
    rn = sub.add_parser("render-nft")
    rn.add_argument("--slots", type=int, default=None,
                    help="render for exactly this many slots (default: the `slots` sizing)")
    args = p.parse_args(argv)
    try:
        conf = _load(args.conf)
    except ValueError as err:
        print(f"fleet_gate: {err}", file=sys.stderr)
        return EX_USAGE
    if args.cmd in ("admit", "status") and not 1 <= args.slot <= MAX_SLOTS:
        print(f"fleet_gate: slot must be 1..{MAX_SLOTS}", file=sys.stderr)
        return EX_USAGE
    if args.cmd == "admit":
        ok, rec = admit(conf, args.slot, args.status_dir, args.proc_root)
        print(json.dumps(rec, sort_keys=True))
        return 0 if ok else EX_REFUSED
    if args.cmd == "status":
        try:
            rec = write_status(args.status_dir, args.slot, args.state, conf["FLEET_CLASS"], args.detail)
        except ValueError as err:
            print(f"fleet_gate: {err}", file=sys.stderr)
            return EX_USAGE
        max_age = _finite_nonnegative(conf.get("STALE_CLAIM_S")) or 21600.0
        _, stale = _scan_status(args.status_dir, 0, max_age)
        print(json.dumps({**rec, "stale_claims": stale}, sort_keys=True))
        return 0
    if args.cmd == "get":
        if args.key not in DEFAULTS:
            print("fleet_gate: unknown key", file=sys.stderr)
            return EX_USAGE
        print(conf[args.key])
        return 0
    if args.cmd in ("slots", "render-nft"):
        obs = observe(args.proc_root)
        auto = slots_for_host(obs["cores"] or 0, obs["mem_total_gb"] or 0.0,
                              float(conf["RESERVE_GB"]), float(conf["SLOT_MEM_GB"]))
        n = auto if conf["SLOTS"] == "auto" else min(int(conf["SLOTS"]), auto)
        if args.cmd == "slots":
            print(json.dumps({"slots": n, "sizing_rule": auto, "configured": conf["SLOTS"],
                              "cores": obs["cores"], "mem_total_gb": obs["mem_total_gb"]}, sort_keys=True))
            return 0
        if args.slots is not None:
            if not 0 <= args.slots <= MAX_SLOTS:
                print(f"fleet_gate: --slots must be 0..{MAX_SLOTS}", file=sys.stderr)
                return EX_USAGE
            n = args.slots
        print(render_nft(conf, n), end="")
        return 0
    print(render_limits(conf), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
