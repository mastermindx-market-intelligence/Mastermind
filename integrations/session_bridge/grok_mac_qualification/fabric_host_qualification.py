"""Explicit first-worker qualification through the incumbent adapter, not enrollment."""
from __future__ import annotations
from copy import deepcopy
import host_pick
import pick


def qualification_route(host, *, task_class, complexity, reason, subject_pool=None,
                        root=None, parent=None, registry=None, state_dir=None, now=None):
    # Chairman requested these existing remote Macs; M2 and alias duplicates excluded.
    if host not in {"mb", "m1"} or not root or not parent:
        raise ValueError("QUALIFICATION_SCOPE_REFUSED")
    registry = host_pick.load_registry() if registry is None else registry
    entry = registry.get(host)
    if not isinstance(entry, dict) or entry.get("local") is True or entry.get("platform") != "darwin":
        raise ValueError("QUALIFICATION_HOST_REFUSED")
    held = entry.get("qualification_only_modes")
    if type(held) is not list or "grok" not in held or len(set(held)) != len(held):
        raise ValueError("QUALIFICATION_NOT_PENDING")
    # Remove only the explicit-canary hold in this transient view. Every other
    # host gate, canonical provider selection and actual LaneLease still applies.
    view = deepcopy(registry)
    view[host]["qualification_only_modes"] = [x for x in held if x != "grok"]
    rows = host_pick.evaluate_hosts(view, state_dir or host_pick.HOSTS_STATE_DIR,
        "grok", max_age=30, excluded=set(view)-{host}, now=now)
    row = next((r for r in rows if r["host"] == host), None)
    if not row or not row["eligible"]:
        fails = [] if not row else [g["gate"] for g in row["gates"] if g["result"] != "PASS"]
        raise ValueError("QUALIFICATION_PREREQUISITE_REFUSED:" + ",".join(fails))
    line = pick.format_pick(task_class, pool="grok", task_complexity=complexity,
        escalation_reason=reason, subject_pool=subject_pool)
    if not line.startswith("POOL=grok "):
        raise ValueError("QUALIFICATION_PROVIDER_REFUSED")
    return line + " HOST=" + host + " MODE=grok"
