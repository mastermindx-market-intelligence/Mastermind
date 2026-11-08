"""Fresh plan facts from the incumbent account registry and scoped gateway.

The native bridge calls this host-owned accessor. It owns no credential store,
quota ledger, scheduler or retry. The upstream provider key stays in the gateway.
The existing accounts.yaml owns enrollment; provider metadata owns observations.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
import urllib.error
import urllib.request

# Direct source CLI and flat native releases use the same policy source.
from pathlib import Path as _PolicyPath
import sys as _policy_sys
_policy_source_root = _PolicyPath(__file__).resolve().parents[3]
if (_policy_source_root / "control_plane" / "experiential_plan_policy.py").is_file():
    _policy_sys.path.insert(0, str(_policy_source_root))

try:
    from control_plane.experiential_plan_policy import (
        PLAN_ACCOUNT_SCHEMA, PLAN_OBSERVATION_SCHEMA, PLAN_ACCOUNT_PREFIX,
        PLAN_MODELS, FREE_NATIVE_MODELS, plan_policy_digest, route_policy_generation,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {"control_plane", "control_plane.experiential_plan_policy"}:
        raise
    from experiential_plan_policy import (
        PLAN_ACCOUNT_SCHEMA, PLAN_OBSERVATION_SCHEMA, PLAN_ACCOUNT_PREFIX,
        PLAN_MODELS, FREE_NATIVE_MODELS, plan_policy_digest, route_policy_generation,
    )


class HostContextRefused(RuntimeError):
    pass


def _private_regular(path: Path, *, limit: int, private: bool = False) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        forbidden_mode = 0o077 if private else 0o022
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & forbidden_mode or not 0 < info.st_size <= limit):
            raise HostContextRefused("PLAN_OWNER_FILE_INVALID")
        raw = os.read(descriptor, limit + 1)
        after = os.fstat(descriptor)
        if (len(raw) != info.st_size or len(raw) > limit
                or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise HostContextRefused("PLAN_OWNER_FILE_CHANGED")
        return raw
    finally:
        os.close(descriptor)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise HostContextRefused("PLAN_METADATA_REDIRECT_REFUSED")


def _gateway_reader(gateway: dict):
    if (type(gateway) is not dict or gateway.get("host") != "127.0.0.1"
            or type(gateway.get("port")) is not int
            or not 1 <= gateway["port"] <= 65535):
        raise HostContextRefused("PLAN_GATEWAY_REGISTRATION_INVALID")
    token_path = Path(gateway.get("proxy_token_file", ""))
    if not token_path.is_absolute():
        raise HostContextRefused("PLAN_PROXY_TOKEN_REFERENCE_INVALID")
    token = _private_regular(token_path, limit=512, private=True).decode().strip()
    if not 24 <= len(token) <= 256 or token.startswith("xpl_") or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise HostContextRefused("PLAN_PROXY_TOKEN_INVALID")
    base = f"http://127.0.0.1:{gateway['port']}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def read(path: str):
        if path not in {"/statusz", "/api/whoami", "/api/v1/credits", "/v1/models"}:
            raise HostContextRefused("PLAN_METADATA_PATH_REFUSED")
        request = urllib.request.Request(base + path, headers={"Authorization": "Bearer " + token})
        try:
            with opener.open(request, timeout=10) as response:
                if response.status != 200:
                    raise HostContextRefused("PLAN_METADATA_HTTP_REFUSED")
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise HostContextRefused("PLAN_METADATA_TOO_LARGE")
                value = json.loads(raw)
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            raise HostContextRefused("PLAN_METADATA_UNAVAILABLE") from exc
        if type(value) is not dict:
            raise HostContextRefused("PLAN_METADATA_INVALID")
        return value

    return read, token, base


def _observed_context(provider: dict, *, read, token: str, base: str, now=None):
    """Pure composition after the actual host owner reads its registered route."""
    if type(provider) is not dict or provider.get("enabled") is not True:
        raise HostContextRefused("PLAN_PROVIDER_DISABLED")
    gateway = provider.get("plan_gateway")
    rows = provider.get("accounts")
    if type(gateway) is not dict or type(rows) is not list:
        raise HostContextRefused("PLAN_ACCOUNT_NOT_ENROLLED")
    matches = [row for row in rows if type(row) is dict and row.get("name") == gateway.get("account")]
    if len(matches) != 1 or matches[0].get("enabled") is not True:
        raise HostContextRefused("PLAN_ACCOUNT_NOT_ENROLLED")
    row = matches[0]
    registration = row.get("plan")
    if type(registration) is not dict or registration.get("schema") != PLAN_ACCOUNT_SCHEMA:
        raise HostContextRefused("PLAN_ACCOUNT_NOT_ENROLLED")
    mode = registration.get("plan_policy")
    if mode not in {"free_only", "free_and_uncensored"}:
        raise HostContextRefused("PLAN_POLICY_NOT_ENROLLED")
    digest = plan_policy_digest(mode)
    status = read("/statusz")
    if (status.get("plan_policy") != mode or status.get("plan_policy_digest") != digest
            or status.get("account_metadata_enabled") is not True):
        raise HostContextRefused("PLAN_GATEWAY_POLICY_MISMATCH")
    who = read("/api/whoami")
    org_id = who.get("org_id")
    if type(org_id) is not str or not org_id:
        raise HostContextRefused("PLAN_ORGANIZATION_UNOBSERVED")
    organization = hashlib.sha256(org_id.encode()).hexdigest()
    account = PLAN_ACCOUNT_PREFIX + organization
    if (row.get("name") != account or registration.get("account") != account
            or registration.get("organization_sha256") != organization):
        raise HostContextRefused("PLAN_ORGANIZATION_MISMATCH")
    credits = read("/api/v1/credits").get("data")
    if type(credits) is not dict:
        raise HostContextRefused("PLAN_WALLET_UNOBSERVED")
    total, used = credits.get("total_credits"), credits.get("total_usage")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in (total, used)):
        raise HostContextRefused("PLAN_WALLET_INVALID")
    catalog = read("/v1/models").get("data")
    if type(catalog) is not list:
        raise HostContextRefused("PLAN_CATALOG_UNOBSERVED")
    catalog_ids = {row.get("id") for row in catalog if type(row) is dict}
    # Max included models use their exact plain catalog IDs. A catalog row
    # does not establish either a promotional grant or the Max funding guard.
    models = sorted(model for model in PLAN_MODELS if model in catalog_ids)
    if not models:
        raise HostContextRefused("PLAN_MODELS_UNAVAILABLE")
    route_host = gateway.get("route_host")
    if type(route_host) is not str or not route_host:
        raise HostContextRefused("PLAN_NATIVE_HOST_UNENROLLED")
    route_base = base + "/v1"
    return {
        "registry_entry": {"enabled": True, "plan": registration},
        "entitlement": {"verified": True, "source": "authenticated_catalog_only"},
        "account": account,
        "quota_readback": {
            "schema": PLAN_OBSERVATION_SCHEMA, "source": "authenticated_gateway_metadata",
            "account": account, "organization_sha256": organization,
            "policy_digest": digest, "observed_at_unix": time.time() if now is None else now,
            "wallet_balance_usd": total - used, "available_models": models,
            # No supported account endpoint has supplied these facts. Do not
            # manufacture them from the chairman's plan declaration or wallet.
            "included_funding": None,
        },
        "route_host": route_host,
        "routes": {endpoint: {
            "host": "127.0.0.1", "port": gateway["port"], "proxy_token": token,
            "route_id": gateway["route_id"], "endpoint": endpoint,
            "route_generation": route_policy_generation(route_base, endpoint, mode),
            "plan_policy": mode,
        } for endpoint in set(FREE_NATIVE_MODELS.values())},
        "route": {"host": "127.0.0.1", "port": gateway["port"],
                  "proxy_token": token, "route_id": gateway["route_id"],
                  "route_generation": route_policy_generation(route_base, "chat/completions", mode),
                  "plan_policy": mode},
    }


def host_owned_context():
    """Read the incumbent registry; never accept request-selected credentials."""
    import lease_broker
    import yaml

    raw = _private_regular(Path(lease_broker.DEFAULT_ACCOUNTS), limit=1024 * 1024)
    document = yaml.safe_load(raw)
    if type(document) is not dict or document.get("schema") != "mastermind.provider_accounts.v1":
        raise HostContextRefused("PLAN_ACCOUNTS_REGISTRY_INVALID")
    provider = document.get("providers", {}).get("experiential")
    if type(provider) is not dict:
        raise HostContextRefused("PLAN_PROVIDER_NOT_ENROLLED")
    read, token, base = _gateway_reader(provider.get("plan_gateway"))
    return _observed_context(provider, read=read, token=token, base=base)
