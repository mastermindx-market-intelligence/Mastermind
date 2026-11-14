#!/usr/bin/env python3
"""Exec a GLM Claude worker with ONLY its incumbent broker-assigned account.

No new capacity authority. The caller must already be inside slot.py or its
existing LANE_LEASED remote transport. No credential is printed or put on argv.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

HERE = Path(__file__).resolve().parent

class BindingRefused(ValueError):
    pass

def _text(env, key):
    value = env.get(key, "")
    if not isinstance(value, str) or not value or len(value) > 128:
        raise BindingRefused("binding missing")
    return value

def validate_local_lease(env, model, db_path=None, now=None):
    """Read an exact lease without opening a broker writer or changing capacity."""
    account = _text(env, "POOL_ACCOUNT")
    lease_id = _text(env, "POOL_LEASE_ID")
    root = _text(env, "POOL_ORCHESTRATOR_ID")
    if env.get("LANE_LEASED") == "1":
        # The incumbent controller's authenticated remote launch injects these
        # names; remote hosts do not own the controller SQLite lease DB.
        _text(env, "REMOTE_SUB_RUN_ID")
        _text(env, "LANE_REMOTE_HOST")
        return account

    if db_path is None:
        import lease_broker
        db_path = lease_broker.DEFAULT_DB
    path = Path(db_path).absolute()
    if path.is_symlink() or not path.is_file():
        raise BindingRefused("lease unavailable")
    try:
        connection = sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=.25)
        try:
            result = connection.execute(
                "SELECT account,pool,model,orchestrator_id,state,last_heartbeat,ttl,"
                "granted_at,renewable FROM leases WHERE id=? LIMIT 1", (lease_id,)
            ).fetchone()
        finally:
            connection.close()
    except (OSError,sqlite3.Error) as exc:
        raise BindingRefused("lease unavailable") from exc
    if result is None:
        raise BindingRefused("lease unavailable")
    found_account,pool,found_model,found_root,state,heartbeat,ttl,granted,renewable=result
    now = float(time.time() if now is None else now)
    if (
        found_account != account or pool != "glm" or found_model.lower() != model.lower()
        or found_root != root or state not in ("held","rented")
        or not isinstance(heartbeat, (int,float)) or heartbeat <= 0
        or not isinstance(ttl,(int,float)) or ttl <= 0
        or not heartbeat <= now < heartbeat + ttl
        or not isinstance(granted, (int,float)) or granted > heartbeat
        or renewable not in (0,1)
        or (renewable == 0 and now >= granted + ttl)
    ):
        raise BindingRefused("lease mismatch")
    return account

def make_command(cwd, model, prompt, system_prompt, mcp_config, turns, *, prompt_from_stdin=False):
    if model not in ("glm-5.3", "glm-5.3-flash"):
        raise BindingRefused("model refused")
    if not cwd or not Path(cwd).is_dir():
        raise BindingRefused("workdir refused")
    if not turns.isdigit() or not 1 <= int(turns) <= 500:
        raise BindingRefused("turn bound refused")
    argv=["claude","-p"] if prompt_from_stdin else ["claude","-p",prompt]
    if system_prompt:
        argv.extend(["--append-system-prompt",system_prompt])
    argv.extend([
        "--output-format","stream-json","--verbose","--dangerously-skip-permissions",
        "--max-turns",turns,"--model",model,
        "--strict-mcp-config","--mcp-config",mcp_config,
    ])
    return argv

def launch(cwd,model,prompt,system_prompt,mcp_config,turns,*,environ=None,accounts=None,db_path=None,now=None,exec_fn=None,prompt_file=False):
    environ=dict(os.environ if environ is None else environ)
    argv=make_command(cwd,model,prompt,system_prompt,mcp_config,turns,prompt_from_stdin=prompt_file)
    descriptor=None
    try:
        if prompt_file:
            descriptor=os.open(prompt,os.O_RDONLY | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_CLOEXEC",0) | getattr(os,"O_NONBLOCK",0))
            metadata=os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size == 0:
                raise BindingRefused("prompt file refused")
        account=validate_local_lease(environ,model,db_path=db_path,now=now)
        if accounts is None:
            import glm_keys
            accounts=glm_keys.accounts()
        from glm_keys import selected_account_key
        try:
            key=selected_account_key(account,accounts)
        except (ValueError,TypeError) as exc:
            raise BindingRefused("account credential unavailable") from exc
        if environ.get('FABRIC_OPERATOR_CAPABILITY'):
            from fabric_operator_client import prepare_claude_hook
            argv.extend(prepare_claude_hook(HERE, environ))
        scoped=dict(environ)
        scoped["ANTHROPIC_AUTH_TOKEN"]=key
        # Claude Code validates custom --model IDs against its own model catalog,
        # even when the Anthropic-compatible endpoint and native Fabric picker
        # already allow the model. Register only the exact broker-bound model;
        # never silently substitute a Claude alias or another provider model.
        scoped["ANTHROPIC_CUSTOM_MODEL_OPTION"]=model
        scoped["ANTHROPIC_MODEL"]=model
        scoped["ANTHROPIC_DEFAULT_MODEL"]=model
        for alias in (
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "ANTHROPIC_DEFAULT_FABLE_MODEL",
            "CLAUDE_CODE_SUBAGENT_MODEL",
        ):
            scoped[alias]=model
        scoped.pop("GLM_SHIM_TOKEN",None)
        if exec_fn is None:
            import capacity_preflight
            rejected=capacity_preflight.check(scoped,"glm",model,Path(__file__))
            if rejected is not None:
                return capacity_preflight.stop_before_task(rejected,scoped)
            capacity_preflight.reserve_task_start(scoped)
        if exec_fn is not None:
            return exec_fn(argv,scoped)
        os.chdir(cwd)
        if descriptor is not None:
            os.dup2(descriptor,0,inheritable=True)
            os.set_inheritable(0,True)
        os.execvpe("claude",argv,scoped)
    finally:
        if descriptor is not None:
            os.close(descriptor)

def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    prompt_file=bool(args and args[0]=="--prompt-file")
    if prompt_file:
        args=args[1:]
    if len(args)!=6:
        print("glm_bound_claude: argument contract refused",file=sys.stderr)
        return 78
    try:
        return int(launch(*args,prompt_file=prompt_file) or 0)
    except BindingRefused as exc:
        allowed = {"binding missing", "lease unavailable", "lease mismatch", "model refused", "workdir refused", "turn bound refused", "prompt file refused", "account credential unavailable"}
        reason = str(exc) if str(exc) in allowed else "binding refused"
        print("glm_bound_claude: broker account binding refused reason=" + reason.replace(" ", "_"), file=sys.stderr)
        return 78
    except (OSError,ValueError,TypeError,sqlite3.Error):
        print("glm_bound_claude: broker account binding refused reason=local_contract_error",file=sys.stderr)
        return 78
    return 0

if __name__=="__main__":
    raise SystemExit(main())
