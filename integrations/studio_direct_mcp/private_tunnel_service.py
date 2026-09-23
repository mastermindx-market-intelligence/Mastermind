#!/usr/bin/env python3
"""Per-account LaunchAgent owner for Studio Direct private tunnel-client.

Official `runtimes connect` (0.0.14) rewrites the generated profile, drops
mcp.connection_max_ttl / max_concurrent_requests, forwards only key-env refs,
requires target+tunnelID each connect, and supervises via tmux — not login.
This helper is the single runtime owner: launchd runs the pinned official
binary with explicit TTL/concurrency flags. It does not create tunnels, apps,
or keys, and it does not stop or delete the old managed alias.

Label: com.mastermind.studio-direct-tunnel.<account>
Gateway label stays com.mastermind.studio-direct-private.<account>.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import private_service as gw

RESERVED_FUNNEL_PORT = gw.RESERVED_FUNNEL_PORT

PINNED_TUNNEL_CLIENT = (
    "/opt/homebrew/Cellar/tunnel-client/0.0.14/libexec/tunnel-client"
)
TRANSPORT_TTL = "5h"
STARTUP_WAIT = "30s"
MAX_CONCURRENT_REQUESTS = 4
CONTROL_PLANE_BASE_URL = "https://api.openai.com"

# Known loopback mapping. Other safe accounts take port from the gateway manifest.
ACCOUNT_PORTS = {"chatgpt1": 45018}

TUNNEL_ID_RE = re.compile(r"^tunnel_[0-9a-f]{32}$")
ORGANIZATION_ID_RE = re.compile(r"^org-[A-Za-z0-9]+$")
TUNNEL_LABEL_PREFIX = "com.mastermind.studio-direct-tunnel."
GATEWAY_LABEL_PREFIX = "com.mastermind.studio-direct-private."
MANAGED_ALIAS_PREFIX = "studio-direct-private-"

MANIFEST_KEYS = (
    "version",
    "account",
    "label",
    "tunnelId",
    "gatewayPort",
    "healthPort",
    "profile",
    "profileHash",
    "plistHash",
    "runtimeKeyRef",
    "tunnelClient",
    "gatewayLabel",
    "managedAlias",
    "transportTTL",
    "maxConcurrentRequests",
)

_run = gw._run
_sha256_file = gw._sha256_file
_sha256_hex = gw._sha256_hex
_user_root = gw._user_root
_assert_no_symlink_ancestors = gw._assert_no_symlink_ancestors
_atomic_write_text = gw._atomic_write_text
_assert_dest_safe = gw._assert_dest_safe
_ensure_secure_dir = gw._ensure_secure_dir
_validate_account_label = gw._validate_account_label
_write_plist = gw._write_plist
_load_plist = gw._load_plist
_info_is_running = gw._info_is_running


def _tunnel_label(account: str) -> str:
    return f"{TUNNEL_LABEL_PREFIX}{account}"


def _gateway_label(account: str) -> str:
    return f"{GATEWAY_LABEL_PREFIX}{account}"


def _managed_alias(account: str) -> str:
    return f"{MANAGED_ALIAS_PREFIX}{account}"


def _build_tunnel_roots(account: str) -> dict:
    user_root = _user_root()
    base = user_root / ".local" / "share" / "studio-direct-mcp" / "private" / account
    profile_dir = user_root / ".config" / "tunnel-client" / "studio-direct-private"
    return {
        "base": base,
        "state": base / "state",
        "logs": base / "logs",
        "manifest": base / "state" / "tunnel-manifest.json",
        "plist": (
            user_root
            / "Library"
            / "LaunchAgents"
            / f"{_tunnel_label(account)}.plist"
        ),
        "profile": profile_dir / f"studio-direct-private-{account}.yaml",
        "profile_dir": profile_dir,
        "out_log": base / "logs" / "tunnel-out.log",
        "err_log": base / "logs" / "tunnel-err.log",
        "gateway_manifest": base / "manifest.json",
        "gateway_config": base / "config.json",
    }


def _health_port(gateway_port: int) -> int:
    port = gateway_port + 1
    if port == RESERVED_FUNNEL_PORT or port == gateway_port:
        raise SystemExit("health port collides with a reserved or gateway port")
    if not (1024 <= port <= 65535):
        raise SystemExit("health port must be between 1024 and 65535")
    return port


def _health_listen_addr(health_port: int) -> str:
    return f"127.0.0.1:{health_port}"


def _mcp_target(gateway_port: int) -> str:
    return f"http://127.0.0.1:{gateway_port}/mcp"


def _validate_tunnel_id(tunnel_id: str) -> None:
    if not TUNNEL_ID_RE.fullmatch(tunnel_id):
        raise SystemExit(
            "tunnel id must match tunnel_<32 lowercase hex> "
            f"(got {tunnel_id!r})"
        )


def _validate_organization_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or ORGANIZATION_ID_RE.fullmatch(value) is None:
        raise SystemExit("organization id must match org-<alphanumeric>")
    return value


def _parse_file_ref(value: str) -> Path:
    if not isinstance(value, str) or not value.startswith("file:"):
        raise SystemExit("runtime key ref must be a file: reference")
    raw = value[5:]
    if not os.path.isabs(raw):
        raise SystemExit("runtime key ref path must be absolute")
    path = Path(raw)
    home = _user_root()
    if not home.is_absolute():
        raise SystemExit("HOME must be absolute")
    try:
        home_info = os.lstat(home)
    except OSError:
        raise SystemExit("HOME is unavailable")
    if stat.S_ISLNK(home_info.st_mode) or not stat.S_ISDIR(home_info.st_mode):
        raise SystemExit("HOME must be a non-symlink directory")
    if home_info.st_uid != os.getuid():
        raise SystemExit("HOME owner mismatch")
    if stat.S_IMODE(home_info.st_mode) & 0o022:
        raise SystemExit("HOME permissions must deny group/other writes")
    _assert_no_symlink_ancestors(path)
    try:
        info = os.lstat(path)
    except OSError:
        raise SystemExit("runtime key ref not found")
    if stat.S_ISLNK(info.st_mode):
        raise SystemExit("runtime key ref must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit("runtime key ref must be a regular file")
    if info.st_uid != os.getuid():
        raise SystemExit("runtime key ref owner mismatch")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise SystemExit("runtime key ref permissions must deny group/other access")
    parent = path.parent
    while parent != home:
        try:
            parent_info = os.lstat(parent)
        except OSError:
            raise SystemExit("runtime key ref parent missing")
        if not stat.S_ISDIR(parent_info.st_mode):
            raise SystemExit("runtime key ref parent must be a directory")
        if parent_info.st_uid != os.getuid():
            raise SystemExit("runtime key ref parent owner mismatch")
        if stat.S_IMODE(parent_info.st_mode) & 0o022:
            raise SystemExit(
                "runtime key ref parent permissions must deny group/other writes"
            )
        parent = parent.parent
    return path


def _resolve_tunnel_client(value: str) -> Path:
    if value != PINNED_TUNNEL_CLIENT:
        raise SystemExit(f"--tunnel-client must be the pinned path {PINNED_TUNNEL_CLIENT}")
    return gw._resolve_abs("--tunnel-client", PINNED_TUNNEL_CLIENT)


def _canonical_profile(account: str) -> Path:
    return _build_tunnel_roots(account)["profile"]


def _validate_profile_arg(account: str, value: str) -> Path:
    if not os.path.isabs(value):
        raise SystemExit("--profile must be absolute")
    path = Path(value)
    if path.is_symlink():
        raise SystemExit("--profile must not be a symlink")
    expected = _canonical_profile(account)
    if os.path.normpath(str(path)) != os.path.normpath(str(expected)):
        raise SystemExit(
            f"--profile must be the owned path {expected}"
        )
    return expected


def _expected_argv(
    tunnel_client: Path,
    profile: Path,
    health_port: int,
) -> list[str]:
    return [
        str(tunnel_client),
        "run",
        "--profile-file",
        str(profile),
        "--mcp.connection-max-ttl",
        TRANSPORT_TTL,
        "--mcp.max-concurrent-requests",
        str(MAX_CONCURRENT_REQUESTS),
        "--mcp.startup-wait-timeout",
        STARTUP_WAIT,
        "--health.listen-addr",
        _health_listen_addr(health_port),
    ]


def _build_profile(
    tunnel_id: str,
    runtime_key_ref: str,
    gateway_port: int,
    health_port: int,
    organization_id: str | None = None,
) -> dict:
    control_plane = {
        "api_key": runtime_key_ref,
        "base_url": CONTROL_PLANE_BASE_URL,
        "tunnel_id": tunnel_id,
    }
    if organization_id is not None:
        control_plane["organization_id"] = organization_id
    return {
        "admin_ui": {"open_browser": False},
        "config_version": 1,
        "control_plane": control_plane,
        "health": {"listen_addr": _health_listen_addr(health_port)},
        "log": {"format": "json", "level": "info"},
        "mcp": {
            "server_urls": [
                {"channel": "main", "url": _mcp_target(gateway_port)},
            ]
        },
    }


def _build_plist(
    tunnel_client: Path,
    profile: Path,
    health_port: int,
    user_root: Path,
    label: str,
    logs: Path,
) -> dict:
    return {
        "Label": label,
        "ProgramArguments": _expected_argv(tunnel_client, profile, health_port),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(user_root),
        },
        "ProcessType": "Interactive",
        "Umask": 0o077,
        "ExitTimeOut": 25,
        "WorkingDirectory": str(user_root),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(logs / "tunnel-out.log"),
        "StandardErrorPath": str(logs / "tunnel-err.log"),
        "StandardInPath": "/dev/null",
    }


def _argv_transport_ttl(argv: list[str]) -> str | None:
    try:
        return argv[argv.index("--mcp.connection-max-ttl") + 1]
    except (ValueError, IndexError):
        return None


def _argv_max_concurrent(argv: list[str]) -> int | None:
    try:
        return int(argv[argv.index("--mcp.max-concurrent-requests") + 1])
    except (ValueError, IndexError):
        return None


def _launchd_inspect(label: str) -> dict | None:
    res = _run(["launchctl", "print", gw._launchd_target(label)], check=False)
    if res.returncode != 0:
        return None
    parsed = gw._parse_launchd_print(res.stdout)
    if parsed["state"] is None and parsed["pid"] is None:
        return None
    return parsed


def _alias_is_running(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("process_running") is True or payload.get("running") is True:
        return True
    tmux = payload.get("tmux")
    if isinstance(tmux, dict) and tmux.get("running") is True:
        return True
    local = payload.get("local")
    if isinstance(local, dict):
        if local.get("process_running") is True:
            return True
        local_tmux = local.get("tmux")
        if isinstance(local_tmux, dict) and local_tmux.get("running") is True:
            return True
    return False


def _managed_alias_running(tunnel_client: Path, account: str) -> bool:
    alias = _managed_alias(account)
    res = _run(
        [str(tunnel_client), "runtimes", "status", alias, "--json"],
        check=False,
    )
    if res.returncode != 0:
        # A missing local alias is expected after migration. Other errors do
        # not establish that the old supervisor stopped.
        expected = f"alias {alias} is not known; run create or connect first"
        if (res.stderr or "").strip() == expected:
            return False
        raise SystemExit("refusing: managed alias state could not be established")
    try:
        payload = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise SystemExit("refusing: managed alias status is not JSON")
    return _alias_is_running(payload)


def _refuse_if_alias_running(tunnel_client: Path, account: str) -> None:
    if _managed_alias_running(tunnel_client, account):
        raise SystemExit(
            f"refusing: managed alias {_managed_alias(account)} is running; "
            "parent must stop that exact alias first"
        )


def _read_json_file(path: Path, *, name: str) -> dict:
    if path.is_symlink():
        raise SystemExit(f"refusing symlink {name}")
    if not path.is_file():
        raise SystemExit(f"not staged: {name} missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit(f"corrupt {name}")
    if not isinstance(data, dict):
        raise SystemExit(f"corrupt {name}")
    return data


def _load_gateway(account: str) -> tuple[dict, dict, int]:
    gw_roots = gw._build_runtime_roots(account)
    label = _gateway_label(account)
    manifest = gw._read_manifest(gw_roots["manifest"], account, label, required=True)
    config = _read_json_file(gw_roots["config"], name="gateway config")
    port = manifest.get("port")
    if config.get("accountLabel") != account:
        raise SystemExit("gateway config account mismatch")
    if config.get("host") != "127.0.0.1":
        raise SystemExit("gateway host must be 127.0.0.1")
    if config.get("port") != port:
        raise SystemExit("gateway config/manifest port mismatch")
    if not isinstance(port, int):
        raise SystemExit("gateway manifest port missing")
    gw._validate_port(port)
    expected = ACCOUNT_PORTS.get(account)
    if expected is not None and port != expected:
        raise SystemExit(
            f"account {account} must use loopback port {expected}"
        )
    return manifest, config, port


def _valid_manifest(data, account: str, label: str) -> bool:
    if not isinstance(data, dict):
        return False
    if any(k not in data for k in MANIFEST_KEYS):
        return False
    if data.get("account") != account or data.get("label") != label:
        return False
    if data.get("gatewayLabel") != _gateway_label(account):
        return False
    if data.get("managedAlias") != _managed_alias(account):
        return False
    if data.get("transportTTL") != TRANSPORT_TTL:
        return False
    if data.get("maxConcurrentRequests") != MAX_CONCURRENT_REQUESTS:
        return False
    if data.get("tunnelClient") != PINNED_TUNNEL_CLIENT:
        return False
    organization_id = data.get("organizationId")
    if organization_id is not None and (
        not isinstance(organization_id, str)
        or ORGANIZATION_ID_RE.fullmatch(organization_id) is None
    ):
        return False
    if not _sha256_hex(data.get("profileHash")):
        return False
    if not _sha256_hex(data.get("plistHash")):
        return False
    return True


def _read_manifest(
    manifest_path: Path,
    account: str,
    label: str,
    *,
    required: bool = False,
) -> dict | None:
    if manifest_path.is_symlink():
        raise SystemExit("refusing symlink tunnel manifest")
    if not manifest_path.exists():
        if required:
            raise SystemExit("not staged: tunnel manifest missing")
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("corrupt tunnel manifest")
    if not _valid_manifest(data, account, label):
        raise SystemExit("corrupt tunnel manifest")
    return data


def _stage_dest_files(roots: dict) -> list[Path]:
    return [roots["profile"], roots["plist"], roots["manifest"]]


def _assert_first_install_clean(roots: dict) -> None:
    for path in _stage_dest_files(roots):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing overwrite of unmanifested destination: {path}")


def _profile_matches(
    profile_path: Path,
    tunnel_id: str,
    runtime_key_ref: str,
    gateway_port: int,
    health_port: int,
    organization_id: str | None,
) -> None:
    data = _read_json_file(profile_path, name="profile")
    plane = data.get("control_plane")
    if not isinstance(plane, dict):
        raise SystemExit("owned profile missing control_plane")
    if plane.get("tunnel_id") != tunnel_id:
        raise SystemExit("owned profile tunnel id mismatch")
    if plane.get("api_key") != runtime_key_ref:
        raise SystemExit("owned profile runtime key ref mismatch")
    if plane.get("organization_id") != organization_id:
        raise SystemExit("owned profile organization id mismatch")
    urls = (data.get("mcp") or {}).get("server_urls")
    if not isinstance(urls, list) or not urls:
        raise SystemExit("owned profile mcp target missing")
    if urls[0].get("url") != _mcp_target(gateway_port):
        raise SystemExit("owned profile mcp target mismatch")
    listen = (data.get("health") or {}).get("listen_addr")
    if listen != _health_listen_addr(health_port):
        raise SystemExit("owned profile health listen mismatch")


def _verify_prior_install(
    prior: dict,
    account: str,
    label: str,
    tunnel_id: str,
    runtime_key_ref: str,
    tunnel_client: Path,
    gateway_port: int,
    health_port: int,
    organization_id: str | None,
    allow_runtime_key_rotation: bool,
    roots: dict,
) -> None:
    prior_organization_id = prior.get("organizationId")
    prior_runtime_key_ref = prior.get("runtimeKeyRef")
    runtime_key_rotation = prior_runtime_key_ref != runtime_key_ref
    organization_enrichment = (
        prior_organization_id is None and organization_id is not None
    )
    if (
        prior.get("tunnelId") != tunnel_id
        or (runtime_key_rotation and not allow_runtime_key_rotation)
        or prior.get("tunnelClient") != str(tunnel_client)
        or prior.get("gatewayPort") != gateway_port
        or prior.get("healthPort") != health_port
        or (
            prior_organization_id != organization_id
            and not organization_enrichment
        )
        or prior.get("profile") != str(roots["profile"])
        or prior.get("account") != account
        or prior.get("label") != label
    ):
        raise SystemExit(
            "refusing restage: existing tunnel manifest diverges; "
            "runtime key changes require --rotate-runtime-key and only "
            "one-way addition of a previously missing organization id is permitted"
        )
    if roots["profile"].is_symlink() or not roots["profile"].is_file():
        raise SystemExit("refusing restage: existing profile missing")
    if _sha256_file(roots["profile"]) != prior.get("profileHash"):
        raise SystemExit("refusing restage: existing profile hash diverges")
    _profile_matches(
        roots["profile"],
        tunnel_id,
        prior_runtime_key_ref,
        gateway_port,
        health_port,
        prior_organization_id,
    )
    if roots["plist"].is_symlink() or not roots["plist"].is_file():
        raise SystemExit("refusing restage: existing plist missing")
    if _sha256_file(roots["plist"]) != prior.get("plistHash"):
        raise SystemExit("refusing restage: existing plist hash diverges")
    plist = _load_plist(roots["plist"])
    if plist is None or plist.get("Label") != label:
        raise SystemExit("refusing restage: existing plist diverges")
    expected = _expected_argv(tunnel_client, roots["profile"], health_port)
    if list(plist.get("ProgramArguments") or []) != expected:
        raise SystemExit("refusing restage: existing argv diverges")


def _verify_staged_install(account: str, label: str, roots: dict) -> dict:
    manifest = _read_manifest(roots["manifest"], account, label, required=True)
    for name, path, key in (
        ("profile", roots["profile"], "profileHash"),
        ("plist", roots["plist"], "plistHash"),
    ):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"not staged: {name} missing")
        if _sha256_file(path) != manifest[key]:
            raise SystemExit(f"not staged: {name} hash mismatch")
    tunnel_client = Path(manifest["tunnelClient"])
    if tunnel_client.is_symlink() or not tunnel_client.is_file():
        raise SystemExit("not staged: tunnel-client missing")
    plist = _load_plist(roots["plist"])
    if plist is None or plist.get("Label") != label:
        raise SystemExit("plist is not our exact install")
    expected = _expected_argv(
        tunnel_client, roots["profile"], int(manifest["healthPort"])
    )
    if list(plist.get("ProgramArguments") or []) != expected:
        raise SystemExit("plist is not our exact install")
    _profile_matches(
        roots["profile"],
        manifest["tunnelId"],
        manifest["runtimeKeyRef"],
        int(manifest["gatewayPort"]),
        int(manifest["healthPort"]),
        manifest.get("organizationId"),
    )
    _parse_file_ref(manifest["runtimeKeyRef"])
    return manifest


def _probe_loopback(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        return {"ok": False, "status": 0, "error": "non-loopback"}
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            status = int(getattr(resp, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"ok": False, "status": 0, "error": "unreachable"}
    return {"ok": 200 <= status < 300, "status": status}


def _strict_tunnel_health(
    tunnel_client: Path,
    health_port: int,
) -> tuple[bool, bool, bool]:
    result = _run(
        [
            str(tunnel_client),
            "health",
            "--port",
            str(health_port),
            "--require-control-plane-poll",
            "--json",
        ],
        check=False,
        timeout=5.0,
    )
    if result.returncode != 0:
        return False, False, False
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return False, False, False
    if not isinstance(payload, dict):
        return False, False, False
    healthz = payload.get("healthz")
    readyz = payload.get("readyz")
    poll = payload.get("control_plane_poll")
    healthy = isinstance(healthz, dict) and healthz.get("ok") is True
    local_ready = isinstance(readyz, dict) and readyz.get("ok") is True
    poll_ready = isinstance(poll, dict) and poll.get("ok") is True
    return healthy, local_ready and poll_ready, poll_ready


def _gateway_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=2.0) as response:
            state = json.loads(response.read(8192))
        return state.get("ready") is True and state.get("accepting") is True
    except (ValueError, AttributeError, urllib.error.URLError, TimeoutError, OSError):
        return False


def cmd_stage(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = _tunnel_label(account)
    _validate_tunnel_id(args.tunnel_id)
    runtime_key_ref = args.runtime_key_ref
    _parse_file_ref(runtime_key_ref)
    organization_id = _validate_organization_id(args.organization_id)
    roots = _build_tunnel_roots(account)
    profile = _validate_profile_arg(account, args.profile)
    tunnel_client = _resolve_tunnel_client(args.tunnel_client)
    _, _, gateway_port = _load_gateway(account)
    health_port = _health_port(gateway_port)

    _assert_no_symlink_ancestors(roots["base"])
    _assert_no_symlink_ancestors(roots["plist"])
    _assert_no_symlink_ancestors(profile)
    prior = _read_manifest(roots["manifest"], account, label)
    if prior is not None:
        _verify_prior_install(
            prior,
            account,
            label,
            args.tunnel_id,
            runtime_key_ref,
            tunnel_client,
            gateway_port,
            health_port,
            organization_id,
            bool(getattr(args, "rotate_runtime_key", False)),
            roots,
        )
    else:
        _assert_first_install_clean(roots)
    info = _launchd_inspect(label)
    if info is not None:
        raise SystemExit("refusing restage while tunnel service is running; stop first")
    _refuse_if_alias_running(tunnel_client, account)
    for path in _stage_dest_files(roots):
        _assert_dest_safe(path)

    user_root = _user_root()
    _ensure_secure_dir(roots["base"])
    _ensure_secure_dir(roots["state"])
    _ensure_secure_dir(roots["logs"])
    _ensure_secure_dir(roots["profile_dir"])
    (user_root / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_ancestors(user_root / "Library" / "LaunchAgents")

    _atomic_write_text(
        profile,
        json.dumps(
            _build_profile(
                args.tunnel_id,
                runtime_key_ref,
                gateway_port,
                health_port,
                organization_id,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    plist = _build_plist(
        tunnel_client, profile, health_port, user_root, label, roots["logs"]
    )
    _write_plist(roots["plist"], plist)
    manifest = {
        "version": 1,
        "account": account,
        "label": label,
        "tunnelId": args.tunnel_id,
        "gatewayPort": gateway_port,
        "healthPort": health_port,
        "profile": str(profile),
        "profileHash": _sha256_file(profile),
        "plistHash": _sha256_file(roots["plist"]),
        "runtimeKeyRef": runtime_key_ref,
        "organizationId": organization_id,
        "tunnelClient": str(tunnel_client),
        "gatewayLabel": _gateway_label(account),
        "managedAlias": _managed_alias(account),
        "transportTTL": TRANSPORT_TTL,
        "maxConcurrentRequests": MAX_CONCURRENT_REQUESTS,
    }
    _atomic_write_text(
        roots["manifest"],
        json.dumps(manifest, indent=2, sort_keys=True),
    )
    print(
        json.dumps(
            {
                "staged": True,
                "account": account,
                "label": label,
                "profile": str(profile),
                "plist": str(roots["plist"]),
                "manifest": str(roots["manifest"]),
                "tunnelId": args.tunnel_id,
                "gatewayPort": gateway_port,
                "healthPort": health_port,
                "organizationId": organization_id,
                "runtimeKeyRotated": bool(
                    prior is not None
                    and prior.get("runtimeKeyRef") != runtime_key_ref
                ),
                "transportTTL": TRANSPORT_TTL,
                "maxConcurrentRequests": MAX_CONCURRENT_REQUESTS,
            }
        )
    )
    return 0


def cmd_start(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = _tunnel_label(account)
    roots = _build_tunnel_roots(account)
    manifest = _verify_staged_install(account, label, roots)
    _load_gateway(account)
    _refuse_if_alias_running(Path(manifest["tunnelClient"]), account)

    info = _launchd_inspect(label)
    if info is not None:
        path = info.get("path")
        if path and path != str(roots["plist"]):
            raise SystemExit("loaded job is not our exact install")
        if not _info_is_running(info):
            _run(["launchctl", "kickstart", gw._launchd_target(label)])
        print(json.dumps({"started": True, "already": True, "loaded": True}))
        return 0

    _run(["launchctl", "bootstrap", gw._launchd_domain(), str(roots["plist"])])
    print(json.dumps({"started": True, "account": account}))
    return 0


def cmd_status(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = _tunnel_label(account)
    roots = _build_tunnel_roots(account)
    info = _launchd_inspect(label)
    loaded = info is not None
    running = bool(info) and _info_is_running(info)
    pid = info.get("pid") if info and running else None

    manifest = _read_manifest(roots["manifest"], account, label)
    plist = _load_plist(roots["plist"])
    argv = list((plist or {}).get("ProgramArguments") or [])
    transport_ttl = _argv_transport_ttl(argv)
    max_concurrent = _argv_max_concurrent(argv)
    health_port = manifest.get("healthPort") if manifest else None
    healthy = False
    tunnel_ready = False
    control_plane_poll_ready = False
    gateway_ready = False
    if running and isinstance(health_port, int) and manifest:
        tunnel_client = Path(manifest["tunnelClient"])
        healthy, tunnel_ready, control_plane_poll_ready = _strict_tunnel_health(
            tunnel_client, health_port
        )
        gateway_port = manifest.get("gatewayPort")
        if isinstance(gateway_port, int):
            gateway_ready = _gateway_ready(gateway_port)

    alias_running = False
    if manifest and manifest.get("tunnelClient"):
        alias_running = _managed_alias_running(
            Path(manifest["tunnelClient"]), account
        )

    print(
        json.dumps(
            {
                "account": account,
                "label": label,
                "loaded": loaded,
                "running": running,
                "pid": pid,
                "healthy": healthy,
                "ready": tunnel_ready and gateway_ready,
                "tunnelReady": tunnel_ready,
                "controlPlanePollReady": control_plane_poll_ready,
                "gatewayReady": gateway_ready,
                "transportTTL": transport_ttl,
                "maxConcurrentRequests": max_concurrent,
                "gatewayPort": manifest.get("gatewayPort") if manifest else None,
                "healthPort": health_port,
                "tunnelId": manifest.get("tunnelId") if manifest else None,
                "organizationId": manifest.get("organizationId") if manifest else None,
                "managedAlias": _managed_alias(account),
                "managedAliasRunning": alias_running,
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_stop(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = _tunnel_label(account)
    roots = _build_tunnel_roots(account)
    info = _launchd_inspect(label)
    if info is None:
        print(json.dumps({"stopped": True, "already": True, "account": account}))
        return 0

    _verify_staged_install(account, label, roots)
    if info.get("path") != str(roots["plist"]):
        raise SystemExit("loaded job is not our exact install")

    res = _run(["launchctl", "bootout", gw._launchd_target(label)], check=False)
    if res.returncode != 0:
        print(
            json.dumps(
                {"stopped": False, "reason": "bootout failed", "stderr": res.stderr}
            )
        )
        return 1

    deadline = time.monotonic() + 10
    while _launchd_inspect(label) is not None:
        if time.monotonic() >= deadline:
            print(json.dumps({"stopped": False, "reason": "still loaded"}))
            return 1
        time.sleep(0.2)
    print(json.dumps({"stopped": True, "account": account}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="private_tunnel_service")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stage")
    s.add_argument("--account", required=True)
    s.add_argument("--tunnel-id", required=True)
    s.add_argument("--profile", required=True)
    s.add_argument("--runtime-key-ref", required=True)
    s.add_argument("--organization-id")
    s.add_argument(
        "--rotate-runtime-key",
        action="store_true",
        help=(
            "allow an explicit runtime-key file-reference change for the same "
            "stopped account/tunnel; current owned artifacts must verify exactly"
        ),
    )
    s.add_argument("--tunnel-client", default=PINNED_TUNNEL_CLIENT)
    s.set_defaults(func=cmd_stage)

    for name in ("start", "status", "stop"):
        sp = sub.add_parser(name)
        sp.add_argument("--account", required=True)
        sp.set_defaults(func=globals()[f"cmd_{name}"])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
