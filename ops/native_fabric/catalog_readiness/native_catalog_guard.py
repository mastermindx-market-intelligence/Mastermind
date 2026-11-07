"""Incumbent native Fabric host's bounded Grok catalog pre-worker verifier.

Never called from an unowned preview. The native remote executor has already
verified its original process/host/account scope and acquired its LaneLease.
This module owns no lease, provider credential, retry, transport or release.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

from lane_runtime import OwnedProcessStartError
from fabric_model_readiness import (
    ModelWitness,
    parse_grok_models_output,
    qualify_grok_native_route,
)


class GrokCatalogRefused(ValueError):
    """Catalog was unavailable or unqualified; no worker may be started."""


class GrokCatalogUnsettled(RuntimeError):
    """A utility process may remain; the native lease requires reconciliation."""


def _owned_binary(env: dict[str, str]) -> tuple[Path, tuple[int, ...]]:
    selected = shutil.which("grok", path=env.get("PATH"))
    if selected is None:
        raise GrokCatalogRefused("GROK_CATALOG_BINARY_MISSING")
    try:
        resolved = Path(selected).resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise GrokCatalogRefused("GROK_CATALOG_BINARY_UNAVAILABLE") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or not os.access(resolved, os.X_OK)
        or info.st_uid not in (0, os.getuid())
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise GrokCatalogRefused("GROK_CATALOG_BINARY_UNQUALIFIED")
    return resolved, (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
                      info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _auth_identity(env: dict[str, str], here: Path, key: str) -> tuple[int, ...]:
    home = here / "lanes" / (key + ".grok")
    config = home / "config.toml"
    auth_name = env.get("GROK_AUTH_PATH")
    if not auth_name or env.get("GROK_HOME") != str(home):
        raise GrokCatalogRefused("GROK_CATALOG_NATIVE_CONFIG_UNBOUND")
    try:
        home_stat = home.lstat()
        config_stat = config.lstat()
        auth = Path(auth_name)
        auth_stat = auth.lstat()
    except OSError as exc:
        raise GrokCatalogRefused("GROK_CATALOG_AUTH_UNAVAILABLE") from exc
    if (
        not stat.S_ISDIR(home_stat.st_mode)
        or stat.S_ISLNK(home_stat.st_mode)
        or home_stat.st_uid != os.getuid()
        or not stat.S_ISREG(config_stat.st_mode)
        or stat.S_ISLNK(config_stat.st_mode)
        or config_stat.st_uid != os.getuid()
        or not stat.S_ISREG(auth_stat.st_mode)
        or stat.S_ISLNK(auth_stat.st_mode)
        or auth_stat.st_uid != os.getuid()
    ):
        raise GrokCatalogRefused("GROK_CATALOG_AUTH_IDENTITY_INVALID")
    return (config_stat.st_dev, config_stat.st_ino, config_stat.st_mtime_ns,
            auth_stat.st_dev, auth_stat.st_ino, auth_stat.st_mtime_ns)


def _receipt_proven(path: Path, run_label: str, result) -> bool:
    try:
        raw = path.read_bytes()
        if len(raw) > 32768 or len(raw.splitlines()) != 1:
            return False
        record = json.loads(raw)
        output = result.stdout.encode("utf-8")
        return (
            record.get("schema") == "mastermind.local_owned_process_receipt.v1"
            and record.get("label") == run_label
            and record.get("returncode") == 0
            and record.get("timed_out") is False
            and record.get("stdout_truncated") is False
            and record.get("stderr_truncated") is False
            and record.get("stdout_bytes") == len(output)
            and record.get("stdout_sha256") == hashlib.sha256(output).hexdigest()
            and record.get("cleanup", {}).get("identity_verified") is True
            and record.get("cleanup", {}).get("census_proven") is True
            and record.get("cleanup", {}).get("residual_count") == 0
            and record.get("cleanup", {}).get("status") in ("not_needed", "terminated")
        )
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


def qualify_owned_grok_worker(
    *,
    key: str,
    model: str,
    here: Path,
    cwd: str,
    env: dict[str, str],
    command: list[str],
    timeout: float,
    nice: int | None,
    runner,
) -> list[str]:
    """One original-host utility under an existing broker+physical lane lease.

    The returned command uses the same resolved launcher that produced the
    current catalog. Only the native executor may call this after validating
    scope and before the first worker start. A passing result still grants no
    new lease, retry or other admission authority.
    """
    if (
        env.get("LANE_LEASED") != "1"
        or env.get("REMOTE_SUB_RUN_ID") != key
        or env.get("POOL_ACCOUNT") != "default"
        or env.get("LANE_REMOTE_HOST") is None
        or env.get("POOL_LEASE_ID") is None
        or not command
        or command[0] != "grok"
    ):
        raise GrokCatalogRefused("GROK_CATALOG_NATIVE_SCOPE_UNQUALIFIED")
    lanes = here / "lanes"
    receipt = lanes / (key + ".model-catalog.process.jsonl")
    if any(
        path.exists() or path.is_symlink()
        for path in (
            receipt, lanes / (key + ".native-terminal.json"),
            lanes / (key + ".process.jsonl"),
        )
    ):
        raise GrokCatalogRefused("GROK_CATALOG_PRIOR_RUN_EXISTS")
    binary, before = _owned_binary(env)
    auth_before = _auth_identity(env, here, key)
    label = key + "-models"
    if timeout <= 1:
        raise GrokCatalogRefused("GROK_CATALOG_DEADLINE_EXHAUSTED")
    try:
        result = runner(
            [str(binary), "models"], cwd=cwd, env=env,
            timeout=min(15.0, timeout - 0.5), nice=nice,
            label=label, receipt_path=receipt, capture_limit_bytes=8192,
        )
    except OwnedProcessStartError as exc:
        # The incumbent owned-process primitive proves Popen did not return.
        raise GrokCatalogRefused("GROK_CATALOG_EXEC_NOT_STARTED") from exc
    except Exception as exc:
        # A process could have been created before a failed result/receipt.
        # An original-owner start-error may be proved separately; do not
        # infer no effect from a Python exception or missing output.
        raise GrokCatalogUnsettled("GROK_CATALOG_UTILITY_EFFECT_UNKNOWN") from exc
    if not result.cleanup_proven:
        raise GrokCatalogUnsettled("GROK_CATALOG_UTILITY_CLEANUP_UNPROVEN")
    if (
        result.returncode != 0
        or result.timed_out
        or result.stdout_truncated
        or result.stderr_truncated
        or not _receipt_proven(receipt, label, result)
    ):
        raise GrokCatalogRefused("GROK_CATALOG_UTILITY_UNQUALIFIED")
    try:
        parsed = parse_grok_models_output(result.stdout.encode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise GrokCatalogRefused("GROK_CATALOG_GRAMMAR_REFUSED") from exc
    if _owned_binary(env) != (binary, before) or _auth_identity(env, here, key) != auth_before:
        raise GrokCatalogRefused("GROK_CATALOG_NATIVE_IDENTITY_DRIFT")
    now = datetime.now(timezone.utc)
    lease_id = env["POOL_LEASE_ID"]
    witness = ModelWitness(
        provider="grok", host=env["LANE_REMOTE_HOST"],
        lease_id=lease_id, models=parsed.models, observed_at=now,
        complete=True, source_verified=True,
    )
    decision = qualify_grok_native_route(
        {"HOST":env["LANE_REMOTE_HOST"], "MODE":"grok", "POOL":"grok", "MODEL":model},
        witness, lease_id=lease_id, original_state="NEW_UNATTEMPTED", now=now,
    )
    if not decision.eligible or decision.code != "MODEL_ID_LISTED":
        raise GrokCatalogRefused(decision.code)
    if decision.dispatch_authorized or decision.retry_authorized:
        raise GrokCatalogRefused("GROK_CATALOG_UNEXPECTED_AUTHORITY")
    return [str(binary), *command[1:]]


def qualify_custodied_grok_worker(*, state: dict, lease, **worker_scope) -> list[str]:
    """Bind one pre-worker catalog utility to the incumbent LaneLease.

    Mark uncertainty BEFORE invoking the effect-bearing process. Any
    BaseException (including SystemExit, KeyboardInterrupt and signal-handler
    interruption) retains original lease custody and propagates unchanged.
    Only a qualified result or normal refusal with proven no-start/cleanup
    clears the flag. This is not a second admission, lease or retry owner.
    """
    state["catalog_unsettled"] = True
    try:
        qualified = qualify_owned_grok_worker(**worker_scope)
    except GrokCatalogRefused:
        # This refusal is reachable only before process START, after a
        # proven OwnedProcessStartError, or after a proven utility cleanup.
        state["catalog_unsettled"] = False
        raise
    except BaseException:
        # Sticky original-process custody. Never turn an interruption into
        # a fabricated "not started" cleanup_proven terminal outcome.
        lease.hold_for_reconciliation("grok_catalog_utility_unsettled")
        raise
    state["catalog_unsettled"] = False
    return qualified
