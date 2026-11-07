"""Explicit first-worker qualification through the incumbent adapter, not enrollment."""
from __future__ import annotations
from copy import deepcopy
import host_pick
import pick


# Pool identity and executor mode are separate: central GLM uses glm-codex.
QUALIFICATION_MODES = {"grok": "grok", "minimax": "minimax", "glm": "glm-codex"}


def qualification_route(host, *, task_class, complexity, reason, subject_pool=None,
                        root=None, parent=None, registry=None, state_dir=None, now=None,
                        pool="grok"):
    # Ubuntu4 may explicitly qualify Grok, MiniMax or central GLM-Codex only as a first worker.
    # Normal routing remains held until a real provider START, settled result,
    # and original-parent acceptance. Preserve all other host/provider gates.
    authorized = {"grok": {"mb": "darwin", "m1": "darwin", "ubuntu4": "linux"},
                  "minimax": {"m1": "darwin", "ubuntu4": "linux"},
                  "glm": {"ubuntu4": "linux"}}
    mode = QUALIFICATION_MODES.get(pool)
    platform = authorized.get(pool, {}).get(host)
    if platform is None or mode is None or not root or not parent:
        raise ValueError("QUALIFICATION_SCOPE_REFUSED")
    registry = host_pick.load_registry() if registry is None else registry
    entry = registry.get(host)
    if not isinstance(entry, dict) or entry.get("local") is True or entry.get("platform") != platform:
        raise ValueError("QUALIFICATION_HOST_REFUSED")
    held = entry.get("qualification_only_modes")
    if (type(held) is not list or any(type(item) is not str for item in held)
            or mode not in held or len(set(held)) != len(held)):
        raise ValueError("QUALIFICATION_NOT_PENDING")
    # Remove only the explicit-canary hold in this transient view. Every other
    # host gate, canonical provider selection and actual LaneLease still applies.
    view = deepcopy(registry)
    view[host]["qualification_only_modes"] = [x for x in held if x != mode]
    def observe_host():
        rows = host_pick.evaluate_hosts(view, state_dir or host_pick.HOSTS_STATE_DIR,
            mode, max_age=30, excluded=set(view)-{host}, now=now)
        return next((r for r in rows if r["host"] == host), None)

    row = observe_host()
    if (row is not None and not row["eligible"]
            and any(g.get("gate") == "fresh" and g.get("result") == "FAIL"
                    for g in row.get("gates", []))):
        # The original collector runs every 60 seconds while qualification
        # needs a <=30-second observation. Use its existing bounded one-host
        # probe once; never weaken thermals, pressure, leases or provider gates.
        if not host_pick.refresh_stale([host]):
            raise ValueError("QUALIFICATION_TELEMETRY_REFRESH_FAILED")
        row = observe_host()
    if not row or not row["eligible"]:
        fails = [] if not row else [g["gate"] for g in row["gates"] if g["result"] != "PASS"]
        raise ValueError("QUALIFICATION_PREREQUISITE_REFUSED:" + ",".join(fails))
    line = pick.format_pick(task_class, pool=pool, task_complexity=complexity,
        escalation_reason=reason, subject_pool=subject_pool)
    if not line.startswith("POOL=" + pool + " "):
        raise ValueError("QUALIFICATION_PROVIDER_REFUSED")
    return line + " HOST=" + host + " MODE=" + mode
