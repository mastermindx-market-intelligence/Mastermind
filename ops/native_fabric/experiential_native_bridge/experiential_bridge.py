#!/usr/bin/env python3
"""experiential_bridge.py — MANUAL-only consumer hook for the Experiential Labs pool.

This module is composed INTO a disposable native-runtime overlay by
``compose_overlay.py`` (see ``ops/native_fabric/experiential_native_bridge/``).
It is the ONLY execution route the overlay wires for pool ``experiential`` /
model ``glm-5.3-uncensored``. It owns no scheduler, no queue, no ledger, no
credential and no provider capacity, and it never manufactures admission:

* The owner pin law (``experiential53.experiential_pin``) and the owner
  transport (``experiential53.experiential_transport``) are loaded ONLY from
  trusted host-owned locations relative to the installed runtime root — never
  from environment variables, never from caller-supplied paths, never from
  raw config files.
* The host-owned admission inputs (registry entry, platform-funded
  entitlement, account, authenticated quota readback, attested gateway route)
  come ONLY from the host adapter's ``experiential53/experiential_host_context.py``
  accessor. When that accessor is missing, every effect refuses typed
  (``EXPERIENTIAL_HOST_CONTEXT_UNAVAILABLE``); nothing is invented.
* Unknown cap is a hard refusal: an absent or unauthenticated quota readback
  is not capacity (``QUOTA_READBACK_UNAUTHENTICATED``), and Account A's
  original HTTP 403 denial is preserved, never retried or bypassed.
* Unqualified route → no lease, no host acquisition, no provider effect:
  the overlay runs this bridge's preflight BEFORE any lease/broker/host step.
* At most ONE admitted opt-in inference request per run per process
  (``EXPERIENTIAL_DUPLICATE_LAUNCH_REFUSED`` guards duplicates in-process;
  the owner transport owns the one-POST contract itself).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

# Direct source CLI and flat native releases use the same policy source.
from pathlib import Path as _PolicyPath
import sys as _policy_sys
_policy_source_root = _PolicyPath(__file__).resolve().parents[3]
if (_policy_source_root / "control_plane" / "experiential_plan_policy.py").is_file():
    _policy_sys.path.insert(0, str(_policy_source_root))

try:
    from control_plane.experiential_plan_policy import (
        PLAN_MODELS, FREE_NATIVE_MODELS, PlanRequestRefused, admit_plan_account,
        plan_policy_digest, route_policy_generation, select_plan_model,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {"control_plane", "control_plane.experiential_plan_policy"}:
        raise
    from experiential_plan_policy import (
        PLAN_MODELS, FREE_NATIVE_MODELS, PlanRequestRefused, admit_plan_account,
        plan_policy_digest, route_policy_generation, select_plan_model,
    )

#: Exact slugs. No alias folds into either and nothing folds out of them.
POOL = "experiential"
MODEL = "glm-5.3-uncensored"

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PACKET_ROOT_RE = re.compile(r"^(?:/[A-Za-z0-9][A-Za-z0-9_./:-]{0,1022}|[A-Za-z0-9][A-Za-z0-9_./:-]{0,254})$")
_CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_ADAPTER_FILE_BYTES = 4 * 1024 * 1024
_PROMPT_FILE_BYTES = 8 * 1024 * 1024

#: In-process, non-persistent duplicate-launch guard. This is NOT a ledger,
#: queue or state plane: the incumbent remote_sub/ledger owners keep their
#: roles, and the owner transport keeps the actual one-POST contract.
_LAUNCH_BOUND: dict[tuple[str, str], dict[str, Any]] = {}


class ExperientialBridgeRefused(RuntimeError):
    """Typed, fail-closed refusal with a stable upper-snake ``reason``."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason + (f": {detail}" if detail else ""))
        self.reason = reason
        self.detail = detail


def _refuse(reason: str, detail: str = "") -> None:
    raise ExperientialBridgeRefused(reason, detail)


def _validate_run_id(value: Any, *, code: str = "EXPERIENTIAL_RUN_ID_INVALID") -> str:
    if type(value) is not str or not _RUN_ID_RE.fullmatch(value.strip() or ""):
        _refuse(code, "run id must match the incumbent native run-id law")
    return value.strip()


def _consent_token(value: Any, *, code: str) -> bool:
    if value is True or value is False:
        return value
    if type(value) is not str:
        _refuse("EXPERIENTIAL_CONSENT_INVALID", code)
    token = value.strip().lower()
    if token in {"1", "true", "yes"}:
        return True
    if token in {"0", "false", "no", ""}:
        return False
    _refuse("EXPERIENTIAL_CONSENT_INVALID", code)
    return False  # unreachable


def _runtime_root(runtime_root: str | Path | None) -> Path:
    """Resolve the installed runtime root from the bridge's own location.

    The bridge is composed next to the runtime it qualifies. Deriving the
    root from ``__file__`` keeps the adapter search host-owned and
    deterministic; callers cannot point it at arbitrary paths.
    """
    base = Path(__file__ if runtime_root is None else runtime_root).resolve()
    if base.name == "experiential_bridge.py":
        base = base.parent
    if base.name == "experiential_native_bridge":
        base = base.parent
    return base


def _load_host_module(path: Path, name: str) -> Any:
    try:
        info = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        return None
    if info.st_mode & 0o002 or info.st_size > _ADAPTER_FILE_BYTES:
        return None
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # dataclasses (including the real experiential_transport module) use
        # sys.modules[cls.__module__] while defining fields/annotations.
        # A raw exec_module without registering its module silently breaks
        # this owner-owned transport and incorrectly reports it as missing.
        prior = sys.modules.get(name)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
            raise
        return module
    except Exception:
        return None


class HostAdapter:
    """The trusted host-owned pin/transport/context accessor bundle."""

    def __init__(self, pin: Any, transport: Any, context: Any, source: Path) -> None:
        self.pin = pin
        self.transport = transport
        self.context = context
        self.source = source


def resolve_host_adapter(runtime_root: str | Path | None = None) -> HostAdapter:
    """Load the owner modules ONLY from host-owned runtime-relative locations.

    Search order is fixed and finite: ``<runtime>/experiential53/`` then
    ``<runtime>/ops/native_fabric/experiential53/``. Regular files only, no
    symlinks, size-bounded, never environment variables, never caller paths.
    Returns a typed refusal condition by raising when absent.
    """
    root = _runtime_root(runtime_root)
    for base in (root / "experiential53", root / "ops" / "native_fabric" / "experiential53"):
        pin = _load_host_module(base / "experiential_pin.py", "experiential_bridge_pin_host")
        if pin is None:
            continue
        transport = _load_host_module(
            base / "experiential_transport.py", "experiential_bridge_transport_host")
        context = _load_host_module(
            base / "experiential_host_context.py", "experiential_bridge_context_host")
        return HostAdapter(pin=pin, transport=transport, context=context, source=base)
    # The incumbent Mac native-generation publisher admits only flat ext/*.py
    # source files. This last fixed location is still the bridge's own
    # host-owned runtime root; no env/caller path or symlink is consulted.
    pin = _load_host_module(root / "experiential_pin.py", "experiential_bridge_pin_host")
    if pin is not None:
        transport = _load_host_module(
            root / "experiential_transport.py", "experiential_bridge_transport_host")
        context = _load_host_module(
            root / "experiential_host_context.py", "experiential_bridge_context_host")
        return HostAdapter(pin=pin, transport=transport, context=context, source=root)
    _refuse(
        "EXPERIENTIAL_HOST_ADAPTER_MISSING",
        "no host-owned experiential53 adapter is installed beside this "
        "runtime; the owner pin/transport modules are never imported from "
        "env vars, caller paths or untrusted locations")


def _host_context(adapter: HostAdapter) -> dict[str, Any]:
    if adapter.context is None or not hasattr(adapter.context, "host_owned_context"):
        _refuse(
            "EXPERIENTIAL_HOST_CONTEXT_UNAVAILABLE",
            "the host adapter does not expose an owned context accessor; "
            "registry, entitlement, account, quota readback and gateway route "
            "are never fabricated by the bridge or asserted by the caller")
    try:
        context = adapter.context.host_owned_context()
    except Exception as exc:  # noqa: BLE001 - typed fail-closed surface
        _refuse("EXPERIENTIAL_HOST_CONTEXT_UNAVAILABLE", f"accessor refused: {exc}")
    if type(context) is not dict:
        _refuse("EXPERIENTIAL_HOST_CONTEXT_UNAVAILABLE", "context is not a mapping")
    return context


def _strict_manual_preview(adapter: HostAdapter, run_id: str, task_class: str, model: str = MODEL) -> dict[str, Any]:
    """Preview -> recheck law, delegating class/pool/model law to the owner pin."""
    if not hasattr(adapter.pin, "preview"):
        _refuse("EXPERIENTIAL_HOST_ADAPTER_INCOMPLETE", "owner pin has no preview law")
    try:
        selected = adapter.pin.preview(run_id, task_class, pool=POOL, model=model)
        rechecked = adapter.pin.preview(run_id, str(selected.get("task_class", task_class)),
                                        pool=str(selected.get("pool", POOL)),
                                        model=str(selected.get("model", model)))
    except Exception as exc:
        reason = getattr(exc, "reason", None)
        _refuse(reason if type(reason) is str and reason else "EXPERIENTIAL_PIN_LAW_REFUSED",
                str(exc))
    if (selected.get("pool") != POOL or selected.get("model") != model
            or rechecked.get("pool") != POOL or rechecked.get("model") != model
            or selected.get("task_class") != rechecked.get("task_class")):
        _refuse("EXPERIENTIAL_STRICT_RECHECK_MISMATCH",
                "preview and recheck disagree; no route is qualified")
    return {"preview": selected, "recheck": rechecked}


def _selected_route(context, model):
    endpoint = FREE_NATIVE_MODELS.get(model)
    route = context.get("routes", {}).get(endpoint) if endpoint else context.get("route")
    if type(route) is not dict:
        _refuse("EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED")
    return route


def _transport_gates(adapter: HostAdapter, context=None, model: str = MODEL) -> dict[str, Any]:
    if adapter.transport is None:
        _refuse("EXPERIENTIAL_TRANSPORT_MODULE_MISSING",
                "the owner transport module is not installed on this host")
    if model in PLAN_MODELS:
        try:
            route = adapter.transport.GatewayRoute(**_selected_route(context, model))
            adapter.transport.require_plan_route_qualified(route, model)
        except Exception as exc:
            _refuse(getattr(exc, "reason", "PLAN_GATEWAY_ROUTE_UNQUALIFIED"))
        return {"transport_installed": True, "route_qualified": True}
    installed = getattr(adapter.pin, "TRANSPORT_INSTALLED", False)
    if installed is not True:
        _refuse("EXPERIENTIAL_TRANSPORT_NOT_INSTALLED",
                "owner pin attests no qualified native worker transport in "
                "this generation; module constants are owner attestations, "
                "never caller assertions")
    if hasattr(adapter.transport, "require_route_qualified"):
        try:
            adapter.transport.require_route_qualified()
        except Exception as exc:
            reason = getattr(exc, "reason", None)
            _refuse(reason if type(reason) is str and reason else "EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED",
                    str(exc))
    elif getattr(adapter.transport, "ROUTE_QUALIFIED", False) is not True:
        _refuse("EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED",
                "transport attests no qualified route in this generation")
    return {"transport_installed": True, "route_qualified": True}


def _syntax_gate(
    *,
    run_id: Any,
    task_class: Any,
    model: Any,
    strict_manual_pin: Any,
    retention_acknowledged: Any,
    sensitive_data_opt_in: Any,
    proprietary_code: Any,
    code_exposure_opt_in: Any,
    enforce_strict_pin_flag: bool = True,
    enforce_consents: bool = True,
) -> dict[str, Any]:
    rid = _validate_run_id(run_id)
    strict_pin = _consent_token(strict_manual_pin, code="strict_manual_pin") is True
    if not strict_pin and enforce_strict_pin_flag:
        _refuse("EXPERIENTIAL_STRICT_PIN_REQUIRED",
                "the sole admitted shape is --pool experiential "
                "--model glm-5.3-uncensored --strict-manual-pin with all four consents")
    if type(model) is not str or (model != MODEL and model not in PLAN_MODELS):
        _refuse("EXPERIENTIAL_MODEL_SLUG_REFUSED",
                f"the experiential pool admits exactly {MODEL!r}")
    # All four consents are mandatory and must be true for the experiential
    # pool (and only for it). The owner pin law re-checks them at admission;
    # this gate refuses earlier — before any route, lease or host effect.
    # Read-only previews collect nothing and expose nothing, so they never
    # require caller consents.
    retention = _consent_token(retention_acknowledged, code="retention_acknowledged")
    sensitive = _consent_token(sensitive_data_opt_in, code="sensitive_data_opt_in")
    proprietary = _consent_token(proprietary_code, code="proprietary_code")
    exposure = _consent_token(code_exposure_opt_in, code="code_exposure_opt_in")
    if enforce_consents:
        if retention is not True:
            _refuse("RETENTION_UNVERIFIED",
                    "explicit acknowledgement required: the provider retains "
                    "prompt and response even after settings are disabled or the "
                    "account is deleted; spend is platform-funded only")
        if sensitive is not True:
            _refuse("SENSITIVE_DATA_DISCLOSURE_REQUIRED",
                    "explicit opt-in required before any prompt/response reaches "
                    "a retaining provider")
        if proprietary is not True and model == MODEL:
            _refuse("EXPERIENTIAL_PROPRIETARY_CODE_UNDECLARED",
                    "declare whether proprietary code may be present; it is "
                    "never exposed automatically")
        if exposure is not True and (model == MODEL or proprietary):
            _refuse("PROPRIETARY_CODE_EXPOSURE_REFUSED",
                    "explicit code-exposure opt-in required for this pool")
    if type(task_class) is not str or not _CLASS_TOKEN_RE.fullmatch(task_class.strip() or ""):
        _refuse("EXPERIENTIAL_TASK_CLASS_INVALID",
                "an explicit bounded task class token is required")
    return {
        "run_id": rid,
        "model": model,
        "task_class": task_class.strip(),
        "consents": {
            "retention_acknowledged": retention,
            "sensitive_data_opt_in": sensitive,
            "proprietary_code": proprietary,
            "code_exposure_opt_in": exposure,
        },
    }


def request_gate(
    *,
    run_id: Any,
    task_class: Any,
    pool: Any,
    model: Any,
    root_id: Any = None,
    parent_run_id: Any = None,
    runtime_root: str | Path | None = None,
    strict_manual_pin: Any = False,
    retention_acknowledged: Any = False,
    sensitive_data_opt_in: Any = False,
    proprietary_code: Any = False,
    code_exposure_opt_in: Any = False,
) -> dict[str, Any]:
    """The overlay fabric_task request-path gate. Raises typed refusals."""
    if type(pool) is not str or pool != POOL:
        _refuse("EXPERIENTIAL_POOL_REQUIRED", "manual pin requires pool=experiential")
    return preflight(
        run_id=run_id, task_class=task_class, model=model, root=root_id,
        parent=parent_run_id, runtime_root=runtime_root,
        strict_manual_pin=strict_manual_pin,
        retention_acknowledged=retention_acknowledged,
        sensitive_data_opt_in=sensitive_data_opt_in,
        proprietary_code=proprietary_code,
        code_exposure_opt_in=code_exposure_opt_in,
        phase="request",
    )


def preflight(
    *,
    run_id: Any,
    task_class: Any,
    model: Any,
    root: Any = None,
    parent: Any = None,
    host: Any = None,
    runtime_root: str | Path | None = None,
    strict_manual_pin: Any = False,
    retention_acknowledged: Any = False,
    sensitive_data_opt_in: Any = False,
    proprietary_code: Any = False,
    code_exposure_opt_in: Any = False,
    enforce_strict_pin_flag: bool = True,
    enforce_consents: bool = True,
    phase: str = "preflight",
) -> dict[str, Any]:
    """Full fail-closed qualification. NO lease, host, packet or provider effect."""
    syntax = _syntax_gate(
        run_id=run_id, task_class=task_class, model=model,
        strict_manual_pin=strict_manual_pin,
        retention_acknowledged=retention_acknowledged,
        sensitive_data_opt_in=sensitive_data_opt_in,
        proprietary_code=proprietary_code,
        code_exposure_opt_in=code_exposure_opt_in,
        enforce_strict_pin_flag=enforce_strict_pin_flag,
        enforce_consents=enforce_consents,
    )
    if root is not None and type(root) is str and root.strip():
        _validate_run_id(root, code="EXPERIENTIAL_ROOT_INVALID")
    if parent is not None and type(parent) is str and parent.strip():
        _validate_run_id(parent, code="EXPERIENTIAL_PARENT_INVALID")
    adapter = resolve_host_adapter(runtime_root)
    previews = _strict_manual_preview(adapter, syntax["run_id"], syntax["task_class"], model)
    context = _host_context(adapter) if model in PLAN_MODELS else None
    transports = _transport_gates(adapter, context, model)
    context = context if context is not None else _host_context(adapter)
    route_host = context.get("route_host")
    if type(route_host) is not str or not route_host.strip():
        _refuse("EXPERIENTIAL_ROUTE_HOST_UNQUALIFIED",
                "the host context does not attest a qualified route host")
    if host is not None and type(host) is str and host.strip() and host.strip() != route_host:
        _refuse("EXPERIENTIAL_ROUTE_HOST_MISMATCH",
                "requested host does not match the host-attested route host")
    if phase == "request":
        # This is the LAST side-effect-free boundary before fabric_task
        # acquires a host, lease or packet. The owner pin law, not a local
        # copy of its flags, must validate the true account/entitlement/cap.
        # The exec boundary repeats this same gate against fresh owner state.
        try:
            adapter.pin.admit_execution(
                pool=POOL, model=model, task_class=syntax["task_class"],
                registry_entry=context.get("registry_entry"),
                entitlement=context.get("entitlement"),
                retention_acknowledged=syntax["consents"]["retention_acknowledged"],
                sensitive_data_opt_in=syntax["consents"]["sensitive_data_opt_in"],
                proprietary_code=syntax["consents"]["proprietary_code"],
                code_exposure_opt_in=syntax["consents"]["code_exposure_opt_in"],
                account=context.get("account"),
                quota_readback=context.get("quota_readback"),
            )
        except Exception as exc:
            reason = getattr(exc, "reason", None)
            _refuse(reason if type(reason) is str and reason else
                    "EXPERIENTIAL_ADMISSION_REFUSED", str(exc))
    return {
        "state": f"{phase.upper()}_QUALIFIED",
        "run_id": syntax["run_id"],
        "pool": POOL,
        "model": model,
        "task_class": syntax["task_class"],
        "host": route_host,
        "root": root,
        "parent": parent,
        "consents": syntax["consents"],
        "witnesses": {
            "adapter_source": str(adapter.source),
            "pin_preview": previews["preview"],
            "pin_recheck": previews["recheck"],
            "transport_installed": transports["transport_installed"],
            "route_qualified": transports["route_qualified"],
            "host_context_source": str(adapter.source / "experiential_host_context.py"),
            "effects_performed": 0,
        },
    }


def qualified_route(
    *, run_id: Any, task_class: Any, runtime_root: str | Path | None = None,
    model: Any = MODEL, plan_lane: str = "free",
) -> dict[str, str]:
    """Resolve once for a new selection, then preserve that exact model pin."""
    if model is None or model in PLAN_MODELS:
        adapter = resolve_host_adapter(runtime_root)
        context = _host_context(adapter)
        try:
            if model is None:
                model = select_plan_model(plan_lane, context.get("quota_readback", {}).get("available_models"))
            # Funding is an eligibility gate before AUTO can select this route.
            # Request and send boundaries still re-read the original owner.
            admit_plan_account(model=model, account=context.get("account"),
                registration=context.get("registry_entry", {}).get("plan"),
                observation=context.get("quota_readback"))
        except PlanRequestRefused as exc:
            _refuse(exc.reason)
    witness = preflight(run_id=run_id, task_class=task_class, model=model,
                        runtime_root=runtime_root,
                        enforce_strict_pin_flag=False, enforce_consents=False)
    return {"POOL": POOL, "MODEL": witness["model"], "HOST": str(witness["host"]),
            "MODE": POOL}


def launch_policy_witness(mode: Any, task_class: Any, model: Any) -> dict[str, Any]:
    """Strict static economic-shape witness (the bridge owns this pool's law;
    pick.py's own pool law stays byte-untouched for every other pool)."""
    if type(mode) is not str or mode != POOL:
        _refuse("EXPERIENTIAL_MODE_MISMATCH", "launch witness covers mode=experiential only")
    if type(model) is not str or (model != MODEL and model not in PLAN_MODELS):
        _refuse("EXPERIENTIAL_MODEL_SLUG_REFUSED", f"exactly {MODEL!r} is admitted")
    if type(task_class) is not str or not _CLASS_TOKEN_RE.fullmatch(task_class.strip() or ""):
        _refuse("EXPERIENTIAL_TASK_CLASS_INVALID", "explicit class token required")
    return {"allowed": True, "policy_source": "experiential_bridge_static_law",
            "escalate_to": None, "fallback": None, "auto_promotion": False}


def preview_command(
    *,
    run_id: Any,
    task_class: Any,
    pool: Any = None,
    model: Any = None,
    runtime_root: str | Path | None = None,
) -> dict[str, Any]:
    """JSON PREVIEW_ONLY witness — only when every owner gate genuinely passes."""
    if pool != POOL:
        _refuse("EXPERIENTIAL_POOL_REQUIRED", "preview requires exact pool=experiential")
    if model is None or model in {"free", "uncensored"}:
        selected = qualified_route(run_id=run_id, task_class=task_class,
            runtime_root=runtime_root, model=None,
            plan_lane="paid_uncensored" if model == "uncensored" else "free")
        model = selected["MODEL"]
    witness = preflight(run_id=run_id, task_class=task_class, model=model,
                        runtime_root=runtime_root, phase="preview",
                        enforce_strict_pin_flag=False, enforce_consents=False)
    return {
        "state": "PREVIEW_ONLY",
        "reserved": False,
        "run_id": witness["run_id"],
        "pool": witness["pool"],
        "model": witness["model"],
        "host": witness["host"],
        "mode": POOL,
        "task_class": witness["task_class"],
        "reason": "owner pin/route/cap gates qualified this manual preview",
        "selection_rechecked_at_request": True,
        "strict_pin_enforced_at_request": True,
        "witnesses": witness["witnesses"],
    }


def _read_prompt_file(path_value: Any) -> str:
    if type(path_value) is not str or not path_value.strip():
        _refuse("EXPERIENTIAL_PROMPT_FILE_REQUIRED", "exec requires --prompt-file")
    path = Path(path_value)
    try:
        info = path.lstat()
    except OSError as exc:
        _refuse("EXPERIENTIAL_PROMPT_FILE_INVALID", str(exc))
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_size > _PROMPT_FILE_BYTES:
        _refuse("EXPERIENTIAL_PROMPT_FILE_INVALID",
                "must be a regular, non-symlink, bounded file")
    data = path.read_bytes()
    if len(data) != info.st_size:
        _refuse("EXPERIENTIAL_PROMPT_FILE_INVALID", "changed during read")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        _refuse("EXPERIENTIAL_PROMPT_FILE_INVALID", f"not utf-8: {exc}")


def _reserve_native_send(context, model, run_id, root, packet_root, prompt_file):
    """Bind the sole send to the original native lease and durable run."""
    import os
    from native_plan_worker import original_request, validate_plan_lease
    env = dict(os.environ)
    if (env.get("LANE_LEASED") == "1" or env.get("POOL_RUN_ID") != run_id
            or env.get("POOL_ORCHESTRATOR_ID") != root):
        _refuse("PLAN_ORIGINAL_IDENTITY_MISMATCH")
    try:
        account = validate_plan_lease(env, model, expected_pool=POOL)
        if account != context.get("account"):
            _refuse("PLAN_SELECTED_ACCOUNT_MISMATCH")
        original_request(POOL, model, packet_root, prompt_file, env, reserve=True)
    except ExperientialBridgeRefused:
        raise
    except Exception:
        _refuse("PLAN_ORIGINAL_LEASE_OR_SEND_RESERVATION_REFUSED")


def exec_command(
    *,
    run_id: Any,
    task_class: Any,
    model: Any,
    packet_root: Any,
    prompt_file: Any,
    root: Any = None,
    parent: Any = None,
    runtime_root: str | Path | None = None,
    strict_manual_pin: Any = False,
    retention_acknowledged: Any = False,
    sensitive_data_opt_in: Any = False,
    proprietary_code: Any = False,
    code_exposure_opt_in: Any = False,
) -> dict[str, Any]:
    """Admit (owner law, host-owned context) then the ONE opt-in request."""
    witness = preflight(
        run_id=run_id, task_class=task_class, model=model, root=root,
        parent=parent, runtime_root=runtime_root, phase="exec",
        strict_manual_pin=strict_manual_pin,
        retention_acknowledged=retention_acknowledged,
        sensitive_data_opt_in=sensitive_data_opt_in,
        proprietary_code=proprietary_code,
        code_exposure_opt_in=code_exposure_opt_in,
    )
    prompt = _read_prompt_file(prompt_file)
    if type(packet_root) is not str or not _PACKET_ROOT_RE.fullmatch(packet_root.strip() or ""):
        _refuse("EXPERIENTIAL_PACKET_ROOT_INVALID", "packet root must be a bounded path token")
    packet_root = packet_root.strip()
    rid = witness["run_id"]
    bound_root = root if type(root) is str and root.strip() else "(controller)"
    key = (bound_root, rid)
    previous = _LAUNCH_BOUND.get(key)
    if previous is not None:
        _refuse("EXPERIENTIAL_DUPLICATE_LAUNCH_REFUSED",
                f"run {rid} is already bound in this process; no second worker "
                "effect is created and reconciliation stays with the original owner")
    adapter = resolve_host_adapter(runtime_root)
    context = _host_context(adapter)
    route = _selected_route(context, witness["model"])
    if type(route) is not dict:
        _refuse("EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED",
                "host context carries no attested gateway route")
    try:
        admitted = adapter.pin.admit_execution(
            pool=POOL, model=witness["model"], task_class=witness["task_class"],
            registry_entry=context.get("registry_entry"),
            entitlement=context.get("entitlement"),
            retention_acknowledged=witness["consents"]["retention_acknowledged"],
            sensitive_data_opt_in=witness["consents"]["sensitive_data_opt_in"],
            proprietary_code=witness["consents"]["proprietary_code"],
            code_exposure_opt_in=witness["consents"]["code_exposure_opt_in"],
            account=context.get("account"),
            quota_readback=context.get("quota_readback"),
        )
    except Exception as exc:
        reason = getattr(exc, "reason", None)
        _refuse(reason if type(reason) is str and reason else "EXPERIENTIAL_ADMISSION_REFUSED",
                str(exc))
    if not hasattr(adapter.transport, "run_opt_in_inference"):
        _refuse("EXPERIENTIAL_TRANSPORT_MODULE_MISSING",
                "owner transport exposes no admitted inference entry point")
    if witness["model"] in FREE_NATIVE_MODELS:
        try:
            adapter.transport.validate_native_packet(prompt, witness["model"])
        except Exception as exc:
            _refuse(getattr(exc, "reason", "PLAN_NATIVE_PACKET_INVALID"))
    # Reserve BEFORE the effect so a lost call cannot be silently re-posted in
    # this process; the transport's own law owns cross-process uniqueness.
    if witness["model"] in PLAN_MODELS:
        _reserve_native_send(context, witness["model"], rid, root, packet_root, prompt_file)
    _LAUNCH_BOUND[key] = {"run_id": rid, "root": bound_root, "admission": admitted}
    try:
        outcome = adapter.transport.run_opt_in_inference(
            run_id=rid, packet_root=packet_root,
            task_class=witness["task_class"], pool=POOL, model=witness["model"],
            registry_entry=context.get("registry_entry"),
            entitlement=context.get("entitlement"),
            retention_acknowledged=witness["consents"]["retention_acknowledged"],
            sensitive_data_opt_in=witness["consents"]["sensitive_data_opt_in"],
            proprietary_code=witness["consents"]["proprietary_code"],
            code_exposure_opt_in=witness["consents"]["code_exposure_opt_in"],
            account=context.get("account"),
            quota_readback=context.get("quota_readback"),
            route=(adapter.transport.GatewayRoute(**route)
                   if hasattr(adapter.transport, "GatewayRoute") else route), prompt=prompt,
        )
    except Exception as exc:
        # The binding is KEPT: after any transport failure the effect state is
        # the transport owner's to reconcile; this process never re-posts.
        reason = getattr(exc, "reason", None)
        _refuse(reason if type(reason) is str and reason else "EXPERIENTIAL_EXECUTION_REFUSED",
                str(exc))
    payload = outcome if isinstance(outcome, dict) else getattr(outcome, "__dict__", {"outcome": repr(outcome)})
    return {"state": "EXECUTED", "run_id": rid, "pool": POOL, "model": witness["model"],
            "root": bound_root, "admission": admitted, "outcome": payload,
            "witnesses": {**witness["witnesses"], "effects_performed": 1}}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_gate_args(p, *, with_run_id: bool, prompt: bool = False) -> None:
        if with_run_id:
            p.add_argument("--run-id", required=True)
        p.add_argument("--host")
        p.add_argument("--model", default=MODEL)
        p.add_argument("--task-class", default="")
        p.add_argument("--cwd", dest="packet_root")
        p.add_argument("--root")
        p.add_argument("--parent")
        p.add_argument("--retention-acknowledged", default="0")
        p.add_argument("--sensitive-data-opt-in", default="0")
        p.add_argument("--proprietary-code", default="0")
        p.add_argument("--code-exposure-opt-in", default="0")
        p.add_argument("--strict-manual-pin", default="0")
        if prompt:
            p.add_argument("--prompt-file", required=True)

    p = sub.add_parser("policy-check", help="static experiential economic shape (no adapter effects)")
    p.add_argument("--mode", required=True)
    p.add_argument("--class", dest="task_class", default="")
    p.add_argument("--model", required=True)
    p.add_argument("--task-complexity", default="")
    p.add_argument("--escalation-reason", default="")

    p = sub.add_parser("launch-preflight")
    add_gate_args(p, with_run_id=True)
    p = sub.add_parser("exec-preflight")
    add_gate_args(p, with_run_id=True)
    p = sub.add_parser("exec")
    add_gate_args(p, with_run_id=True, prompt=True)
    p = sub.add_parser("preview")
    p.add_argument("--id", required=True)
    p.add_argument("--class", dest="task_class", required=True)
    p.add_argument("--pool")
    p.add_argument("--model")
    p = sub.add_parser("qualify-route")
    p.add_argument("--run-id", required=True)
    p.add_argument("--class", dest="task_class", required=True)
    return parser


def _emit(value: dict[str, Any]) -> int:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "policy-check":
            return _emit(launch_policy_witness(args.mode, args.task_class, args.model))
        if args.cmd in {"launch-preflight", "exec-preflight"}:
            return _emit(preflight(
                run_id=args.run_id, task_class=args.task_class, model=args.model,
                root=args.root, parent=args.parent, host=args.host,
                strict_manual_pin=args.strict_manual_pin,
                retention_acknowledged=args.retention_acknowledged,
                sensitive_data_opt_in=args.sensitive_data_opt_in,
                proprietary_code=args.proprietary_code,
                code_exposure_opt_in=args.code_exposure_opt_in,
                phase=args.cmd))
        if args.cmd == "exec":
            return _emit(exec_command(
                run_id=args.run_id, task_class=args.task_class, model=args.model,
                packet_root=args.packet_root or "", prompt_file=args.prompt_file,
                root=args.root, parent=args.parent,
                strict_manual_pin=args.strict_manual_pin,
                retention_acknowledged=args.retention_acknowledged,
                sensitive_data_opt_in=args.sensitive_data_opt_in,
                proprietary_code=args.proprietary_code,
                code_exposure_opt_in=args.code_exposure_opt_in))
        if args.cmd == "preview":
            return _emit(preview_command(
                run_id=args.id, task_class=args.task_class,
                pool=args.pool, model=args.model))
        if args.cmd == "qualify-route":
            return _emit(qualified_route(run_id=args.run_id, task_class=args.task_class))
    except ExperientialBridgeRefused as exc:
        print(str(exc), file=sys.stderr)
        return 78
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
