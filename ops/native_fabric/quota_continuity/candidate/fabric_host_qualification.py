"""Explicit first-worker qualification through the incumbent adapter, not enrollment."""
from __future__ import annotations
from copy import deepcopy
import host_pick
import pick


def qualification_route(host, *, task_class, complexity, reason, subject_pool=None,
                        root=None, parent=None, registry=None, state_dir=None, now=None,
                        pool="grok"):
    # The sole added first-worker lane is MiniMax on the named held hosts.
    # Preserve the existing Grok qualification scope and every other host gate.
    authorized = {"grok": {"mb": "darwin", "m1": "darwin"},
                  "minimax": {"m1": "darwin", "ubuntu4": "linux"}}
    platform = authorized.get(pool, {}).get(host)
    if platform is None or not root or not parent:
        raise ValueError("QUALIFICATION_SCOPE_REFUSED")
    registry = host_pick.load_registry() if registry is None else registry
    entry = registry.get(host)
    if not isinstance(entry, dict) or entry.get("local") is True or entry.get("platform") != platform:
        raise ValueError("QUALIFICATION_HOST_REFUSED")
    held = entry.get("qualification_only_modes")
    if type(held) is not list or pool not in held or len(set(held)) != len(held):
        raise ValueError("QUALIFICATION_NOT_PENDING")
    # Remove only the explicit-canary hold in this transient view. Every other
    # host gate, canonical provider selection and actual LaneLease still applies.
    view = deepcopy(registry)
    view[host]["qualification_only_modes"] = [x for x in held if x != pool]
    rows = host_pick.evaluate_hosts(view, state_dir or host_pick.HOSTS_STATE_DIR,
        pool, max_age=30, excluded=set(view)-{host}, now=now)
    row = next((r for r in rows if r["host"] == host), None)
    if not row or not row["eligible"]:
        fails = [] if not row else [g["gate"] for g in row["gates"] if g["result"] != "PASS"]
        raise ValueError("QUALIFICATION_PREREQUISITE_REFUSED:" + ",".join(fails))
    line = pick.format_pick(task_class, pool=pool, task_complexity=complexity,
        escalation_reason=reason, subject_pool=subject_pool)
    if not line.startswith("POOL=" + pool + " "):
        raise ValueError("QUALIFICATION_PROVIDER_REFUSED")
    return line + " HOST=" + host + " MODE=" + pool
