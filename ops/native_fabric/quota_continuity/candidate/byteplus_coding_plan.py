"""BytePlus personal Coding Plan binding in the incumbent native Fabric.

The existing Broker owns leases and quota cooldowns. BytePlus owns all five-hour,
weekly and subscription-month allowance enforcement. This adapter runs supported
Claude Code exactly once; it never sends a standalone inference request, retries,
falls through to PAYG, creates quota, or acquires its own lease.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

POOL = "byteplus"
BINDING_ID = "byteplus-coding-plan-personal.claude-code-anthropic"
BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/coding"
MODELS = frozenset({"deepseek-v4.1-flash", "glm-5.3-flash"})
CODING_TASK_CLASSES = frozenset({"mechanical", "fix_build", "build", "fix", "execute", "executor", "tests-only-repair"})
ACCOUNT_SCHEMA = "mastermind.byteplus_coding_plan_account/v1"
SUBSCRIPTION_REF = re.compile(r"^subscription-[0-9a-f]{64}$")
HERE = Path(__file__).resolve().parent


class BytePlusBindingRefused(ValueError):
    pass


def _closed_account(row, *, now=None):
    """Source-bound enrollment; operator slots are not provider quota counts."""
    if type(row) is not dict or row.get("enabled") is not True:
        raise BytePlusBindingRefused("BYTEPLUS_ACCOUNT_DISABLED")
    plan = row.get("coding_plan")
    if type(plan) is not dict or plan.get("schema") != ACCOUNT_SCHEMA:
        raise BytePlusBindingRefused("BYTEPLUS_PLAN_NOT_ENROLLED")
    scope = plan.get("subscription_ref")
    if type(scope) is not str or SUBSCRIPTION_REF.fullmatch(scope) is None:
        raise BytePlusBindingRefused("BYTEPLUS_SUBSCRIPTION_SCOPE_REQUIRED")
    if (row.get("quota_scope") != "byteplus:" + scope
            or plan.get("binding_id") != BINDING_ID
            or plan.get("base_url") != BASE_URL
            or plan.get("models") != sorted(MODELS)
            or plan.get("scope") != "individual_supported_coding_tools"
            or plan.get("quota_enforcement") != "provider_hard_stop_no_payg"
            or plan.get("entitlement_source") != "chairman_declared_plan"
            or plan.get("plan_price_usd_per_month") != 50):
        raise BytePlusBindingRefused("BYTEPLUS_PLAN_ENROLLMENT_MISMATCH")
    if (type(row.get("per_account_cap")) is not int
            or not 1 <= row["per_account_cap"] <= 32
            or plan.get("concurrency_source") != "operator_limit_not_provider_entitlement"):
        raise BytePlusBindingRefused("BYTEPLUS_OPERATOR_CAP_INVALID")
    expected_source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if plan.get("launcher_sha256") != expected_source:
        raise BytePlusBindingRefused("BYTEPLUS_LAUNCHER_GENERATION_MISMATCH")
    if plan.get("credential_ref") != "provider-home:" + row.get("name", ""):
        raise BytePlusBindingRefused("BYTEPLUS_CREDENTIAL_REFERENCE_MISMATCH")
    quota = quota_observation(plan.get("quota_observation"), scope, now=now)
    if quota["state"] == "EXHAUSTED":
        raise BytePlusBindingRefused("BYTEPLUS_PLAN_WINDOW_EXHAUSTED")
    return plan, quota


def quota_observation(observation, subscription_ref, *, now=None):
    """Preserve UNKNOWN while allowing the source-qualified provider boundary.

    No public request estimates or guessed resets become local capacity. An
    observed exhausted window remains held until a fresh authenticated readback
    replaces it; a generic transport success cannot clear the hold.
    """
    unknown = {"state": "UNKNOWN", "windows": None, "remaining_requests": None,
               "enforced_by": "provider", "admission_basis": "bounded_attempt_under_provider_enforcement"}
    if observation is None:
        return unknown
    if (type(observation) is not dict
            or observation.get("schema") != "mastermind.byteplus_personal_plan_readback_projection/v1"
            or observation.get("subscription_ref") != subscription_ref
            or observation.get("acquisition_source") != "authenticated_arkcli"):
        raise BytePlusBindingRefused("BYTEPLUS_QUOTA_OBSERVATION_INVALID")
    windows = observation.get("windows")
    if type(windows) is not dict or set(windows) != {"session", "weekly", "monthly"}:
        raise BytePlusBindingRefused("BYTEPLUS_QUOTA_WINDOWS_INVALID")
    for name, window in windows.items():
        if type(window) is not dict or type(window.get("used_percent_rounded")) is not int or not 0 <= window["used_percent_rounded"] <= 100:
            raise BytePlusBindingRefused("BYTEPLUS_QUOTA_WINDOWS_INVALID")
    if any(window["used_percent_rounded"] == 100 for window in windows.values()):
        return {**unknown, "state": "EXHAUSTED", "windows": windows}
    observed = observation.get("usage_observed_at_unix")
    current = time.time() if now is None else now
    if (type(observed) is not int or type(current) not in (int, float)
            or not math.isfinite(current) or not 0 <= current - observed <= 300):
        return {**unknown, "windows": windows}
    for name in ("weekly", "monthly"):
        try:
            reset = datetime.fromisoformat(windows[name]["reset_at"])
            if reset.tzinfo is None or reset.timestamp() <= current:
                return {**unknown, "windows": windows}
        except (TypeError, ValueError, KeyError, OverflowError):
            raise BytePlusBindingRefused("BYTEPLUS_QUOTA_RESET_INVALID") from None
    if windows["session"].get("reset_at") is not None:
        raise BytePlusBindingRefused("BYTEPLUS_QUOTA_RESET_INVALID")
    return {**unknown, "state": "NOT_EXHAUSTED_ROUNDED", "windows": windows}


def account_eligible(row, *, now=None):
    try:
        _closed_account(row, now=now)
        return True
    except (BytePlusBindingRefused, OSError, TypeError, ValueError):
        return False


def registered_provider(*, accounts_path=None):
    """Read the incumbent owner registry without credential discovery."""
    import lease_broker
    import yaml

    target = Path(lease_broker.DEFAULT_ACCOUNTS if accounts_path is None else accounts_path)
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o022 or not 0 < info.st_size <= 1024 * 1024):
            raise BytePlusBindingRefused("BYTEPLUS_ACCOUNTS_REGISTRY_INVALID")
        raw = os.read(fd, 1024 * 1024 + 1)
    finally:
        os.close(fd)
    document = yaml.safe_load(raw)
    if type(document) is not dict or document.get("schema") != "mastermind.provider_accounts.v1":
        raise BytePlusBindingRefused("BYTEPLUS_ACCOUNTS_REGISTRY_INVALID")
    provider = document.get("providers", {}).get(POOL)
    if type(provider) is not dict or provider.get("enabled") is not True:
        raise BytePlusBindingRefused("BYTEPLUS_PROVIDER_DISABLED")
    rows = provider.get("accounts")
    if type(rows) is not list:
        raise BytePlusBindingRefused("BYTEPLUS_ACCOUNTS_REGISTRY_INVALID")
    refs = [row.get("coding_plan", {}).get("subscription_ref") for row in rows if type(row) is dict]
    if len(refs) != len(rows) or None in refs or len(set(refs)) != len(refs):
        raise BytePlusBindingRefused("BYTEPLUS_DUPLICATE_SUBSCRIPTION_SCOPE")
    return provider


def selected_account(account, *, accounts_path=None):
    """Read only the Broker-selected row; never choose another account."""
    provider = registered_provider(accounts_path=accounts_path)
    rows = [row for row in provider.get("accounts", []) if type(row) is dict and row.get("name") == account]
    if len(rows) != 1:
        raise BytePlusBindingRefused("BYTEPLUS_SELECTED_ACCOUNT_UNAVAILABLE")
    return rows[0]


def native_route(*, task_class, model=None, accounts_path=None):
    model = "glm-5.3-flash" if model is None else model
    if task_class not in CODING_TASK_CLASSES or model not in MODELS:
        raise BytePlusBindingRefused("BYTEPLUS_SUPPORTED_CODING_SCOPE_REQUIRED")
    provider = registered_provider(accounts_path=accounts_path)
    if not any(account_eligible(row) for row in provider["accounts"]):
        raise BytePlusBindingRefused("BYTEPLUS_NO_ENROLLED_ACCOUNT")
    host = provider.get("native_host")
    if type(host) is not str or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", host):
        raise BytePlusBindingRefused("BYTEPLUS_NATIVE_HOST_UNENROLLED")
    return {"POOL": POOL, "MODEL": model, "HOST": host, "MODE": POOL,
            "quota_remaining": None, "admission_basis": "bounded_attempt_under_provider_enforcement"}


def launch(cwd, model, prompt_file, turns, *, environ=None, accounts_path=None,
           db_path=None, now=None, exec_fn=None, credential_loader=None):
    if model not in MODELS or not Path(cwd).is_dir():
        raise BytePlusBindingRefused("BYTEPLUS_MODEL_OR_WORKDIR_REFUSED")
    if not str(turns).isdigit() or not 1 <= int(turns) <= 64:
        raise BytePlusBindingRefused("BYTEPLUS_TURN_BOUND_REFUSED")
    env = dict(os.environ if environ is None else environ)
    if env.get("LANE_LEASED") == "1":
        raise BytePlusBindingRefused("BYTEPLUS_LOCAL_PROVIDER_LEASE_REQUIRED")
    if env.get("POOL_TASK_CLASS") not in CODING_TASK_CLASSES:
        raise BytePlusBindingRefused("BYTEPLUS_SUPPORTED_CODING_SCOPE_REQUIRED")
    from native_plan_worker import validate_plan_lease
    account = validate_plan_lease(env, model, db_path=db_path, now=now, expected_pool=POOL)
    row = selected_account(account, accounts_path=accounts_path)
    plan, _ = _closed_account(row, now=now)
    provider_home = Path(plan.get("provider_home", ""))
    if not provider_home.is_absolute() or any(type(plan.get(field)) is not int for field in ("owner_uid", "owner_gid")):
        raise BytePlusBindingRefused("BYTEPLUS_PROVIDER_HOME_INVALID")
    fd = os.open(prompt_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 1024 * 1024:
            raise BytePlusBindingRefused("BYTEPLUS_PROMPT_FILE_INVALID")
        if credential_loader is None:
            try:
                from control_plane.codex_provider_realm import load_private_provider_credential
            except ModuleNotFoundError as exc:
                if exc.name not in {"control_plane", "control_plane.codex_provider_realm"}:
                    raise
                from codex_provider_realm import load_private_provider_credential
            credential_loader = load_private_provider_credential
        credential = credential_loader(provider_home, expected_uid=plan["owner_uid"], expected_gid=plan["owner_gid"])
        # Clear alternative authentication/provider controls before setting the
        # one reviewed subscription endpoint. No native-login or PAYG fallback.
        for key in tuple(env):
            if key.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDE_CODE_SUBAGENT_")) or key in {"OPENAI_API_KEY", "ARK_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_API_KEY"}:
                env.pop(key, None)
        env.update(ANTHROPIC_BASE_URL=BASE_URL, ANTHROPIC_AUTH_TOKEN=credential,
                   ANTHROPIC_MODEL=model, CLAUDE_CODE_SUBAGENT_MODEL=model,
                   ANTHROPIC_DEFAULT_SONNET_MODEL=model, ANTHROPIC_DEFAULT_HAIKU_MODEL=model,
                   ANTHROPIC_DEFAULT_OPUS_MODEL=model, CLAUDE_CONFIG_DIR=str(provider_home / "claude"),
                   DISABLE_NON_ESSENTIAL_MODEL_CALLS="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        argv = ["claude", "-p", "--output-format", "stream-json", "--verbose",
                "--max-turns", str(turns), "--model", model,
                "--strict-mcp-config", "--mcp-config", "{\"mcpServers\":{}}"]
        # The parent worker remains responsible for its ordinary tool and
        # filesystem authorization; this adapter does not loosen permissions.
        if exec_fn is None:
            from native_plan_worker import original_request
            original_request(POOL, model, cwd, prompt_file, env, reserve=True)
            os.dup2(fd, 0)
            os.chdir(cwd)
            os.execvpe(argv[0], argv, env)
        return exec_fn(argv, env)
    finally:
        os.close(fd)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 3 and args[0] == "policy-check":
        if args[1] not in CODING_TASK_CLASSES or args[2] not in MODELS:
            raise BytePlusBindingRefused("BYTEPLUS_SUPPORTED_CODING_SCOPE_REQUIRED")
        print(json.dumps({"allowed": True, "provider": POOL, "model": args[2],
                          "quota_remaining": None, "quota_enforcement": "provider_hard_stop_no_payg"}))
        return 0
    if len(args) != 4:
        raise BytePlusBindingRefused("BYTEPLUS_LAUNCH_ARGUMENTS_INVALID")
    return launch(*args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Credential objects and provider-home contents never enter diagnostics.
        print("BYTEPLUS_BOUND_LAUNCH_REFUSED", file=sys.stderr)
        raise SystemExit(78)
