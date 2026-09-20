#!/usr/bin/env python3
"""Read-only ChatGPT surface health through existing exact owners.

This is an SCF-OPS1 consumer. It does not own account membership, service or
Tunnel lifecycle, retries, credentials, installation, or routing.
"""
from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Direct operator invocation sets sys.path[0] to scripts/. Bootstrap the
# repository root before importing Mastermind packages so the documented
# python3 scripts/... entrypoint has no hidden PYTHONPATH dependency.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.sol_ops_health import (
    OpsHealthEnvelope,
    ServiceFact,
    TunnelFact,
    project_ops_health,
)

PERSONAL_ACCOUNTS = ("chatgpt1", "chatgpt2", "chatgpt3", "chatgpt4")
TUNNEL_RE = re.compile(r"^tunnel_[0-9a-f]{32}$")
CONTROL_ROOT = Path.home() / ".local" / "share" / "studio-direct-mcp" / "control"

BUSINESS_SERVICES = (
    {
        "name": "executive",
        "service_ref": "mastermind-executive.business",
        "service_kind": "executive_mcp",
        "owner_ref": "executive-mcp",
        "profile": Path.home() / ".config/tunnel-client/mastermind-executive-production.yaml",
        "health": Path.home() / "Library/Application Support/tunnel-client/health/mastermind-executive-production.url",
    },
    {
        "name": "workbench",
        "service_ref": "mastermind-workbench.business",
        "service_kind": "workbench",
        "owner_ref": "workbench",
        "profile": Path.home() / ".config/tunnel-client/workbench-astra-business/mastermind-workbench-astra-business.yaml",
        "health": Path.home() / "Library/Application Support/tunnel-client/health/mastermind-workbench-astra-business.url",
    },
)


@dataclasses.dataclass(frozen=True)
class BusinessFacts:
    service: ServiceFact
    tunnel: TunnelFact | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_json(argv: list[str]) -> dict[str, object]:
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip().splitlines()[-1:] or ["owner status failed"]
        raise RuntimeError(message[0][:160])
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("owner status did not return an object")
    return value


def read_personal_status(account: str) -> dict[str, object]:
    if account not in PERSONAL_ACCOUNTS:
        raise ValueError("account is outside the closed Personal seat allowlist")
    helper = CONTROL_ROOT / "studio_direct_control.py"
    return _run_json(
        [sys.executable, str(helper), "status", "--account", account]
    )


def _bool_or_none(value: object) -> bool | None:
    return value if type(value) is bool else None


def personal_facts(
    account: str,
    status: dict[str, object],
    observed_at: str,
) -> tuple[ServiceFact, TunnelFact | None]:
    if account not in PERSONAL_ACCOUNTS:
        raise ValueError("account is outside the closed Personal seat allowlist")
    gateway = status.get("gateway") if isinstance(status.get("gateway"), dict) else {}
    tunnel = status.get("tunnel") if isinstance(status.get("tunnel"), dict) else {}
    issues: list[str] = []
    if gateway.get("configurationDrift") is True:
        issues.append("CONFIGURATION_DRIFT")

    runtime_version = gateway.get("runtimeVersion")
    if not isinstance(runtime_version, str):
        runtime_version = None

    service = ServiceFact(
        service_ref=f"studio-direct.{account}",
        service_kind="studio_direct_gateway",
        scope="personal_account",
        owner_ref="studio-direct",
        observed_at=observed_at,
        live=_bool_or_none(gateway.get("running")),
        ready=_bool_or_none(gateway.get("runtimeReady")),
        runtime_version=runtime_version,
        deployment_ref=(
            f"gateway-{runtime_version}" if runtime_version is not None else None
        ),
        source_refs=(f"studio-direct:{account}",),
        issues=tuple(issues),
    )

    tunnel_id = tunnel.get("tunnelId")
    if not isinstance(tunnel_id, str) or TUNNEL_RE.fullmatch(tunnel_id) is None:
        return service, None
    tunnel_issues: list[str] = []
    if tunnel.get("managedAliasRunning") is True:
        tunnel_issues.append("FOREIGN_MANAGED_ALIAS_RUNNING")
    tunnel_fact = TunnelFact(
        tunnel_ref=tunnel_id,
        service_ref=service.service_ref,
        owner_ref="studio-direct",
        observed_at=observed_at,
        live=_bool_or_none(tunnel.get("healthy")),
        ready=_bool_or_none(tunnel.get("ready")),
        source_refs=(f"studio-direct:{account}",),
        issues=tuple(tunnel_issues),
    )
    return service, tunnel_fact


def read_tunnel_id(profile: Path) -> str:
    value = json.loads(profile.read_text())
    if not isinstance(value, dict):
        raise ValueError("tunnel profile must be an object")
    control_plane = value.get("control_plane")
    if not isinstance(control_plane, dict):
        raise ValueError("tunnel profile has no control_plane object")
    tunnel_id = control_plane.get("tunnel_id")
    if not isinstance(tunnel_id, str) or TUNNEL_RE.fullmatch(tunnel_id) is None:
        raise ValueError("tunnel profile has no valid control_plane.tunnel_id")
    return tunnel_id


def _http_get(url: str) -> int:
    with urllib.request.urlopen(url, timeout=2) as response:
        response.read(512)
        return int(response.status)


def probe_health_ref(
    path: Path,
    http_get: Callable[[str], int] = _http_get,
) -> tuple[bool | None, bool | None, tuple[str, ...]]:
    try:
        raw = path.read_text().strip()
    except OSError:
        return None, None, ("HEALTH_REF_UNAVAILABLE",)
    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except ValueError:
        return None, None, ("HEALTH_REF_INVALID",)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or not isinstance(port, int)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None, None, ("HEALTH_REF_NOT_LOOPBACK",)

    base = f"http://127.0.0.1:{port}"
    results: list[bool | None] = []
    issues: list[str] = []
    for suffix, issue in (("/healthz", "HEALTH_PROBE_FAILED"), ("/readyz", "READY_PROBE_FAILED")):
        try:
            results.append(http_get(base + suffix) == 200)
        except Exception:
            results.append(None)
            issues.append(issue)
    return results[0], results[1], tuple(issues)


def business_facts(definition: dict[str, object], observed_at: str) -> BusinessFacts:
    name = str(definition["name"])
    issues: list[str] = []
    try:
        tunnel_id = read_tunnel_id(Path(definition["profile"]))
    except (OSError, ValueError, json.JSONDecodeError):
        tunnel_id = None
        issues.append("TUNNEL_PROFILE_UNAVAILABLE")

    live, ready, health_issues = probe_health_ref(Path(definition["health"]))
    issues.extend(health_issues)
    source_ref = f"business-service:{name}"
    service = ServiceFact(
        service_ref=str(definition["service_ref"]),
        service_kind=str(definition["service_kind"]),
        scope="business_workspace",
        owner_ref=str(definition["owner_ref"]),
        observed_at=observed_at,
        live=live,
        ready=ready,
        runtime_version=None,
        deployment_ref=None,
        source_refs=(source_ref,),
        issues=tuple(sorted(set(issues))),
    )
    tunnel = None
    if tunnel_id is not None:
        tunnel = TunnelFact(
            tunnel_ref=tunnel_id,
            service_ref=service.service_ref,
            owner_ref=service.owner_ref,
            observed_at=observed_at,
            live=live,
            ready=ready,
            source_refs=(source_ref,),
            issues=health_issues,
        )
    return BusinessFacts(service, tunnel)


def build_snapshot(*, observed_at: str | None = None) -> OpsHealthEnvelope:
    observed = observed_at or _now()
    services: list[ServiceFact] = []
    tunnels: list[TunnelFact] = []

    for account in PERSONAL_ACCOUNTS:
        try:
            status = read_personal_status(account)
            service, tunnel = personal_facts(account, status, observed)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
            service = ServiceFact(
                service_ref=f"studio-direct.{account}",
                service_kind="studio_direct_gateway",
                scope="personal_account",
                owner_ref="studio-direct",
                observed_at=observed,
                live=None,
                ready=None,
                runtime_version=None,
                deployment_ref=None,
                source_refs=(f"studio-direct:{account}",),
                issues=("OWNER_STATUS_UNAVAILABLE",),
            )
            tunnel = None
        services.append(service)
        if tunnel is not None:
            tunnels.append(tunnel)

    for definition in BUSINESS_SERVICES:
        facts = business_facts(definition, observed)
        services.append(facts.service)
        if facts.tunnel is not None:
            tunnels.append(facts.tunnel)

    return project_ops_health(
        tuple(services),
        tuple(tunnels),
        observed_at=observed,
        generation="scf-ops1",
    )


def main() -> int:
    snapshot = build_snapshot()
    print(json.dumps(snapshot.to_dict(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
