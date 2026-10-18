#!/usr/bin/env python3
"""Controller-only GLM worker capability issuer.

The GLM provider credential stays inside the controller shim. This helper reads
only the shim controller bearer, requests one broker-bound worker capability,
validates the returned scope, and writes a short-lived capsule mode 0600.
No secret is accepted on argv or printed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
DEFAULT_TOKEN = HERE / "glm_shim" / ".token"
DEFAULT_URL = "http://127.0.0.1:4141"
EXPECTED_RESPONSE = {
    "token",
    "expires_at",
    "account",
    "lease_id",
    "model",
    "run_id",
    "host",
    "root",
}


class CapabilityIssueError(RuntimeError):
    pass


def private_read(path: Path, limit: int = 8192) -> str:
    try:
        st = path.lstat()
    except OSError as exc:
        raise CapabilityIssueError("controller credential unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(st.st_mode):
        raise CapabilityIssueError("controller credential refused")
    if stat.S_IMODE(st.st_mode) != 0o600 or st.st_uid != os.getuid():
        raise CapabilityIssueError("controller credential refused")
    if st.st_size < 1 or st.st_size > limit:
        raise CapabilityIssueError("controller credential refused")
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CapabilityIssueError("controller credential unavailable") from exc
    if not value or "\n" in value or "\r" in value:
        raise CapabilityIssueError("controller credential refused")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CapabilityIssueError("invalid capability response")
        result[key] = value
    return result


def _constant(_value):
    raise CapabilityIssueError("invalid capability response")


def parse_object(raw: bytes) -> Dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except CapabilityIssueError:
        raise
    except Exception as exc:
        raise CapabilityIssueError("invalid capability response") from exc
    if not isinstance(value, dict):
        raise CapabilityIssueError("invalid capability response")
    return value


def validate_response(
    value: Dict[str, Any],
    *,
    lease_id: str,
    root: str,
    account: str,
    model: str,
    run_id: str,
    host: str,
    now: float,
) -> Dict[str, Any]:
    if set(value) != EXPECTED_RESPONSE:
        raise CapabilityIssueError("invalid capability response")
    expected = {
        "lease_id": lease_id,
        "root": root,
        "account": account,
        "model": model,
        "run_id": run_id,
        "host": host,
    }
    if any(not wanted or value.get(key) != wanted for key, wanted in expected.items()):
        raise CapabilityIssueError("capability scope mismatch")
    token = value.get("token")
    expiry = value.get("expires_at")
    if not isinstance(token, str) or not token.startswith("v1.") or len(token) > 4096:
        raise CapabilityIssueError("invalid capability response")
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
        raise CapabilityIssueError("invalid capability response")
    expiry = float(expiry)
    if not math.isfinite(expiry) or expiry <= now + 5:
        raise CapabilityIssueError("invalid capability response")
    return dict(value)


def issue(
    *,
    controller_url: str,
    controller_token: str,
    lease_id: str,
    root: str,
    account: str,
    model: str,
    run_id: str,
    host: str,
    ttl: int,
    now_fn=time.time,
) -> Dict[str, Any]:
    if not controller_url.startswith("http://127.0.0.1:"):
        raise CapabilityIssueError("controller URL refused")
    if type(ttl) is not int or not 1 <= ttl <= 7500:
        raise CapabilityIssueError("invalid ttl")
    payload = {
        "lease_id": lease_id,
        "root": root,
        "model": model,
        "run_id": run_id,
        "host": host,
        "ttl": ttl,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = Request(
        controller_url.rstrip("/") + "/worker-capabilities",
        data=body,
        headers={
            "Authorization": "Bearer " + controller_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "mastermind-glm-controller/1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise CapabilityIssueError("capability issue refused")
            cache_control = response.headers.get("Cache-Control", "")
            if "no-store" not in cache_control.lower():
                raise CapabilityIssueError("capability response cache policy refused")
            raw = response.read(16385)
            if len(raw) > 16384:
                raise CapabilityIssueError("capability response too large")
    except CapabilityIssueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CapabilityIssueError("capability issue unavailable") from exc
    return validate_response(
        parse_object(raw),
        lease_id=lease_id,
        root=root,
        account=account,
        model=model,
        run_id=run_id,
        host=host,
        now=float(now_fn()),
    )


def atomic_private_write(path: Path, value: Dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            json.dump(value, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease-id", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--ttl", required=True, type=int)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    token_path = Path(os.environ.get("GLM_SHIM_TOKEN_FILE") or DEFAULT_TOKEN)
    controller_url = os.environ.get("GLM_SHIM_CONTROLLER_URL") or DEFAULT_URL
    try:
        controller_token = private_read(token_path)
        value = issue(
            controller_url=controller_url,
            controller_token=controller_token,
            lease_id=args.lease_id,
            root=args.root,
            account=args.account,
            model=args.model,
            run_id=args.run_id,
            host=args.host,
            ttl=args.ttl,
        )
        atomic_private_write(Path(args.out), value)
    except CapabilityIssueError as exc:
        print("glm_remote_capability: %s" % exc, file=sys.stderr)
        return 78
    print("capability-issued")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
