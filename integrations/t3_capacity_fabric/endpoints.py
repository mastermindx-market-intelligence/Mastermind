"""Discovery of the installed Capacity Fabric local serving endpoints.

Each endpoint is a loopback gateway owned by the fabric (launchd services
``ai.mastermind.anthropic-gateway`` and ``ai.mastermind.experiential-gateway``).
The proxy token never leaves the host: it is read from the gateway's own
600-mode env file at call time and written only into T3's secret store.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_HOME = Path.home() / ".local" / "share" / "mastermind"


@dataclass(frozen=True)
class FabricEndpoint:
    endpoint_id: str
    instance_id: str
    display_name: str
    base_url: str
    env_file: Path
    driver: str = "claudeAgent"
    accent_color: str = "violet"
    preferred_fast_model: str | None = None
    catalogue_env: str | None = None


def default_endpoints(home: Path = _DEFAULT_HOME) -> tuple[FabricEndpoint, ...]:
    """The installed fabric serving endpoints, in stable registration order."""
    return (
        FabricEndpoint(
            endpoint_id="anthropic_oauth",
            instance_id="fabric_claude",
            display_name="Capacity Fabric Claude",
            base_url="http://127.0.0.1:8312",
            env_file=home / "anthropic-gateway" / "gateway.env",
            preferred_fast_model="claude-haiku-5-5",
        ),
        FabricEndpoint(
            endpoint_id="experiential",
            instance_id="fabric_experiential",
            display_name="Capacity Fabric Labs",
            base_url="http://127.0.0.1:8311",
            env_file=home / "experiential-gateway" / "gateway.env",
            accent_color="cyan",
            preferred_fast_model=None,
            # The vendor catalogue at /v1/models is far wider than the fabric's
            # admitted Anthropic surface; the deployed policy list is the truth.
            catalogue_env="EXPLABS_ANTHROPIC_MODELS",
        ),
    )


def read_env_value(env_file: Path, name: str) -> str | None:
    """Read one KEY=VALUE from a gateway env file; None when absent."""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip()
    return None


def load_proxy_token(env_file: Path) -> str:
    """Read FABRIC_PROXY_TOKEN from a gateway env file; no other values."""
    token = read_env_value(env_file, "FABRIC_PROXY_TOKEN") or ""
    if not token:
        raise ValueError(f"FABRIC_PROXY_TOKEN missing in {env_file}")
    return token


def admitted_catalogue(endpoint: FabricEndpoint) -> tuple[str, ...] | None:
    """The operator-deployed admitted catalogue, when the endpoint declares one."""
    if endpoint.catalogue_env is None:
        return None
    raw = read_env_value(endpoint.env_file, endpoint.catalogue_env) or ""
    models = tuple(slug.strip() for slug in raw.split(",") if slug.strip())
    return models or None


def _request_json(url: str, token: str | None, *, timeout_s: float) -> object:
    request = urllib.request.Request(url, method="GET")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def gateway_health(endpoint: FabricEndpoint, *, timeout_s: float = 3.0) -> dict:
    """Unauthenticated liveness read; never raises for a reachable refusal."""
    try:
        payload = _request_json(f"{endpoint.base_url}/healthz", None, timeout_s=timeout_s)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"endpoint_id": endpoint.endpoint_id, "ok": False, "reason": str(exc)}
    ok = isinstance(payload, dict) and payload.get("ok") is True
    return {"endpoint_id": endpoint.endpoint_id, "ok": ok,
            "reason": None if ok else "unhealthy"}


def fetch_catalog(endpoint: FabricEndpoint, token: str, *, timeout_s: float = 5.0) -> tuple[str, ...]:
    """The gateway's authenticated model catalogue, in the gateway's order."""
    payload = _request_json(f"{endpoint.base_url}/v1/models", token, timeout_s=timeout_s)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError(f"invalid catalogue from {endpoint.endpoint_id}")
    models = []
    for item in payload["data"]:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            models.append(item["id"])
    if not models:
        raise ValueError(f"empty catalogue from {endpoint.endpoint_id}")
    return tuple(models)
