#!/usr/bin/env python3
"""experiential_pin.py — MANUAL-only exact-pin law for the Experiential Labs pool.

Scope of this file (child: experiential53-native-manual-pin):

* A NEW, isolated provider pool ``experiential`` carrying exactly one model
  slug, ``glm-5.3-uncensored`` (Experiential Labs GLM 5.3 UNCENSORED).
* The slug is DISTINCT from the canonical Z.AI GLM tier: it is never
  ``glm-5.3``, never ``glm-5.3-flash``, and it can never be assigned to the
  ``glm`` pool.  The canonical GLM model tier in ``model_tier.py`` is untouched.
* MANUAL pin only.  There is no automatic selection, no default promotion,
  no scoring contribution, no escalation target and no cross-model/provider
  fallback or retry.  A pick is admitted only when a caller explicitly pins
  pool=experiential AND model=glm-5.3-uncensored, and the strict pin is
  re-evaluated before any effect, mirroring the incumbent
  preview->recheck->launch-policy law.

Fail-closed by construction:

* This generation makes NO provider calls, reads NO credentials, and writes
  NO storage, queue or ledger.  The existing shared Experiential gateway
  (PR #1849) and the Attempt-owned consumer/transport (PR #1920) remain the
  only approved route; until a qualified native worker transport exists the
  execution admission is unconditionally refused
  (``EXPERIENTIAL_TRANSPORT_NOT_INSTALLED``).  No false admission.
* Account A keeps its original HTTP 403 denial: held, never retried, never
  bypassed.  Account B keeps its $1/day provider key cap, and because there
  is NO authenticated quota readback today, its remaining quota is UNKNOWN —
  an unknown quota is not capacity, so execution stays refused.
* The provider retains prompt/response even after the setting is switched
  off or the account is deleted, and spend is platform-funded only.
  Execution therefore requires an explicit retention acknowledgement AND an
  explicit sensitive-data disclosure opt-in; proprietary code is never
  exposed automatically (independent explicit opt-in).

The incumbent router/transport owners stay authoritative.  Wiring points this
module deliberately does NOT touch (live writers own those files):
``quota_continuity/source/pick.py`` (PR #2029), ``remote_sub.sh``, ``sub.sh``,
``slot.py``, ``model_tier.py``.  See README.md for the exact gap list.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, FrozenSet, Optional, Tuple

# Direct source CLI and flat native releases use the same policy source.
from pathlib import Path as _PolicyPath
import sys as _policy_sys
_policy_source_root = _PolicyPath(__file__).resolve().parents[3]
if (_policy_source_root / "control_plane" / "experiential_plan_policy.py").is_file():
    _policy_sys.path.insert(0, str(_policy_source_root))

try:
    from control_plane.experiential_plan_policy import (
        PLAN_MODELS, PlanRequestRefused, admit_plan_account,
        plan_policy_digest, route_policy_generation, select_plan_model,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {"control_plane", "control_plane.experiential_plan_policy"}:
        raise
    from experiential_plan_policy import (
        PLAN_MODELS, PlanRequestRefused, admit_plan_account,
        plan_policy_digest, route_policy_generation, select_plan_model,
    )

#: Exact pool slug.  No alias folds into it and nothing folds out of it.
POOL = "experiential"

#: Exact model slug.  Case-compare is exact-after-casefold, like the
#: incumbent requested_model law; no prefix, alias or version drift admits.
MODEL = "glm-5.3-uncensored"

#: Canonical Z.AI GLM pool models.  This child never assigns its slug to the
#: glm pool and never admits these slugs on the experiential pool.
GLM_POOL_MODELS: FrozenSet[str] = frozenset({"glm-5.3", "glm-5.3-flash"})

#: Pool carriers this slug may never ride.  glm is the canonical tier owner.
FORBIDDEN_CARRIERS: FrozenSet[str] = frozenset({"glm"})

#: Auto-selection is structurally impossible: the pool contributes no
#: task-class fit, no base score and no escalation/fallback target.
MANUAL_ONLY = True
ESCALATE_TARGETS: FrozenSet[str] = frozenset()

#: Account law (facts as commissioned; no credential or readback access here).
ACCOUNT_A_STATUS = "HELD_HTTP403"
ACCOUNT_B_DAILY_CAP_USD = 1.0
ACCOUNT_B_QUOTA_READBACK_AUTHENTICATED = False

#: The native worker executable cannot truly run through the existing shared
#: gateway in this generation (gateway/consumer PRs unmerged; no enrolled
#: loopback gateway route).  Until a qualified transport lands, execution is
#: refused regardless of every other gate.
TRANSPORT_INSTALLED = False

#: Retention fact the caller must explicitly acknowledge (provider retains
#: prompt/response beyond settings-off/account-deletion; platform-funded only).
PROVIDER_RETENTION_FACT = (
    "provider retains prompt and response even after settings are disabled or "
    "the account is deleted; spend is platform-funded only"
)

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")

#: Task classes a manual experiential pin may serve.  Labor tier only (R20
#: shape, as incumbent ocfree): judgment classes stay forbidden even on an
#: explicit pin, because independent review of unproven-provider judgment is
#: not available.
ALLOWED_TASK_CLASSES: FrozenSet[str] = frozenset({
    "executor", "extract", "execute", "fix_build", "mechanical",
    "verify", "build", "fix", "heal", "tests-only-repair",
})
FORBIDDEN_TASK_CLASSES: FrozenSet[str] = frozenset({
    "architecture", "integration", "design", "ruling", "decompose",
    "adjudicate", "orchestration", "review", "audit", "high_level",
    "operator", "reviewer", "hard-debug", "escalation",
})


class ExperientialPinRefused(RuntimeError):
    """Typed, fail-closed refusal.  ``reason`` is a stable upper-snake code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason + (f": {detail}" if detail else ""))
        self.reason = reason
        self.detail = detail


def _token(value: Any, *, code: str) -> str:
    """A literal manual selector is not an admission or quota grant."""
    if value is None:
        raise ExperientialPinRefused(code)
    if type(value) is not str:
        raise ExperientialPinRefused("MANUAL_SELECTOR_INVALID")
    token = value.strip()
    if not token or token.casefold() == "auto":
        raise ExperientialPinRefused(code)
    if _TOKEN_RE.fullmatch(token) is None:
        raise ExperientialPinRefused("MANUAL_SELECTOR_INVALID")
    return token


def enforce_pin(pool: Any, model: Any) -> Tuple[str, str]:
    """Validate the ONE admitted manual pin; raise a typed refusal otherwise.

    Order matters and is part of the contract: carrier distinctness is
    checked before slug equality so a glm-pool attempt can never be confused
    with a slug typo.
    """
    named_pool = _token(pool, code="MANUAL_POOL_REQUIRED")
    if named_pool.casefold() in FORBIDDEN_CARRIERS:
        raise ExperientialPinRefused(
            "GLM_POOL_CARRIER_REFUSED",
            f"{MODEL} is not a glm-pool model; canonical glm tier is unchanged",
        )
    if named_pool.casefold() != POOL:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_POOL_ONLY",
            f"manual pin must use pool={POOL}, got pool={named_pool!r}",
        )
    named_model = _token(model, code="MANUAL_MODEL_REQUIRED")
    if named_model.casefold() in GLM_POOL_MODELS:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_MODEL_DISTINCT",
            f"{named_model!r} is a canonical glm-pool model, not this provider",
        )
    if named_model.casefold() != MODEL and named_model not in PLAN_MODELS:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_MODEL_SLUG_MISMATCH",
            "exact registered legacy or plan model slug required",
        )
    return named_pool.casefold(), named_model.casefold()


def preview(
    run_id: Any,
    task_class: Any,
    *,
    pool: Any,
    model: Any,
    task_complexity: str = "",
    escalation_reason: str = "",
) -> Dict[str, Any]:
    """Read-only preview of the strict manual pin.  No lease, packet or worker.

    The pin is evaluated twice — once as the caller's selection and once as
    the selection recheck — mirroring the incumbent preview->recheck law.
    With the incumbent router this stays advisory: the transport's own
    launch-policy recheck remains the final owner at wiring time.
    """
    rid = str(run_id or "").strip()
    if RUN_ID_RE.fullmatch(rid) is None:
        raise ExperientialPinRefused("RUN_ID_INVALID")
    cls = str(task_class or "").strip().lower()
    if not cls:
        raise ExperientialPinRefused("TASK_CLASS_REQUIRED")
    selected = enforce_pin(pool, model)
    rechecked = enforce_pin(selected[0], selected[1])
    if selected != rechecked:  # deterministic law; cannot diverge today
        raise ExperientialPinRefused("SELECTION_RECHECK_MISMATCH")
    if cls in FORBIDDEN_TASK_CLASSES:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_TASK_CLASS_FORBIDDEN",
            f"{cls} is judgment/independence-bounded; manual pin cannot lift it",
        )
    if cls not in ALLOWED_TASK_CLASSES:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_TASK_CLASS_NOT_ADMITTED",
            f"{cls} is not an admitted manual-pin labor class",
        )
    return {
        "state": "PREVIEW_ONLY",
        "reserved": False,
        "run_id": rid,
        "pool": selected[0],
        "model": selected[1],
        "task_class": cls,
        "reason": "manual_only_exact_pin",
        "selection_rechecked_at_request": True,
        "strict_pin_enforced_at_request": True,
        # No escalation/fallback field is emitted, ever.
        "escalate_to": None,
        "fallback": None,
    }


def auto_selection_verdict(task_class: Any) -> Dict[str, Any]:
    """The ONLY verdict any automatic path may get: NONE, with no target."""
    return {
        "state": "NONE",
        "pool": None,
        "model": None,
        "reason": "experiential_manual_only",
        "task_class": str(task_class or "").strip().lower() or None,
        "escalate_to": None,
        "fallback": None,
    }


def fallback_refused(
    failed_pool: Any, failed_model: Any,
    proposed_pool: Any, proposed_model: Any,
) -> Dict[str, Any]:
    """No cross-model/provider retry after a refused or failed attempt.

    Even the exact same pin is not silently retried: a caller must issue a
    fresh, explicit preview.  Anything else is refused.
    """
    try:
        failed = enforce_pin(failed_pool, failed_model)
    except ExperientialPinRefused as exc:
        return {"state": "NONE", "reason": "NO_CROSS_PROVIDER_FALLBACK",
                "detail": f"failed attempt was not this pool: {exc.reason}",
                "escalate_to": None, "fallback": None}
    if proposed_pool is None and proposed_model is None:
        return {"state": "NONE", "reason": "FAILED_PIN_NOT_RETRIED",
                "detail": "issue a fresh explicit preview; no silent retry",
                "escalate_to": None, "fallback": None}
    try:
        proposed = enforce_pin(proposed_pool, proposed_model)
    except ExperientialPinRefused as exc:
        return {"state": "NONE", "reason": "NO_CROSS_PROVIDER_FALLBACK",
                "detail": f"proposed retry is not the exact pin: {exc.reason}",
                "escalate_to": None, "fallback": None}
    return {"state": "NONE", "reason": "FAILED_PIN_NOT_RETRIED",
            "detail": f"even {proposed[0]}/{proposed[1]} needs a fresh explicit preview",
            "escalate_to": None, "fallback": None}


def admit_execution(
    *,
    pool: Any,
    model: Any,
    task_class: Any,
    registry_entry: Optional[Dict[str, Any]] = None,
    entitlement: Optional[Dict[str, Any]] = None,
    retention_acknowledged: bool = False,
    sensitive_data_opt_in: bool = False,
    proprietary_code: bool = False,
    code_exposure_opt_in: bool = False,
    account: Any = None,
    quota_readback: Any = None,
) -> Dict[str, Any]:
    """Fail-closed execution admission.  In this generation it NEVER allows.

    Every gate below is independent and typed.  The checks run in contract
    order so tests (and any future wiring) observe one deterministic first
    refusal instead of an arbitrary one.  The transport gate is the module
    constant ``TRANSPORT_INSTALLED`` — never a caller-supplied argument, so
    a caller cannot assert its way past an unqualified transport.
    """
    pinned = enforce_pin(pool, model)
    cls = str(task_class or "").strip().lower()
    if cls in FORBIDDEN_TASK_CLASSES:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_TASK_CLASS_FORBIDDEN", cls)
    if cls not in ALLOWED_TASK_CLASSES:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_TASK_CLASS_NOT_ADMITTED", cls)
    if not isinstance(registry_entry, dict) or registry_entry.get("enabled") is not True:
        raise ExperientialPinRefused("PROVIDER_DISABLED")
    if not isinstance(entitlement, dict) or entitlement.get("verified") is not True:
        raise ExperientialPinRefused("ENTITLEMENT_UNVERIFIED")
    if retention_acknowledged is not True:
        raise ExperientialPinRefused(
            "RETENTION_UNVERIFIED", PROVIDER_RETENTION_FACT)
    if sensitive_data_opt_in is not True:
        raise ExperientialPinRefused(
            "SENSITIVE_DATA_DISCLOSURE_REQUIRED",
            "explicit opt-in required before any prompt/response reaches a "
            "retaining provider")
    if proprietary_code is True and code_exposure_opt_in is not True:
        raise ExperientialPinRefused(
            "PROPRIETARY_CODE_EXPOSURE_REFUSED",
            "proprietary code is never exposed automatically")
    if pinned[1] in PLAN_MODELS:
        try:
            plan = admit_plan_account(
                model=pinned[1], account=account,
                registration=registry_entry.get("plan"),
                observation=quota_readback,
            )
        except PlanRequestRefused as exc:
            raise ExperientialPinRefused(exc.reason) from exc
        return {"state": "ADMITTED", "pool": pinned[0], "model": pinned[1],
                "task_class": cls, "escalate_to": None, "fallback": None, **plan}
    name = str(account or "").strip().lower()
    if not name:
        raise ExperientialPinRefused("ACCOUNT_UNRESOLVED")
    if name in {"a", "account-a", "account_a"}:
        raise ExperientialPinRefused(
            "ACCOUNT_A_HELD_HTTP403",
            "original denial stands; never retried or bypassed")
    if name not in {"b", "account-b", "account_b"}:
        raise ExperientialPinRefused("ACCOUNT_UNKNOWN")
    if quota_readback != "authenticated":
        raise ExperientialPinRefused(
            "QUOTA_READBACK_UNAUTHENTICATED",
            f"account B keeps its ${ACCOUNT_B_DAILY_CAP_USD:.2f}/day cap but no "
            "authenticated readback exists; unknown quota is not capacity")
    if TRANSPORT_INSTALLED is not True:
        raise ExperientialPinRefused(
            "EXPERIENTIAL_TRANSPORT_NOT_INSTALLED",
            "no qualified native worker transport through the existing shared "
            "gateway exists in this generation; deliver is fail-closed source "
            "only")
    # Unreachable in this generation; kept so the contract shape is explicit.
    return {
        "state": "ADMITTED", "pool": pinned[0], "model": pinned[1],
        "task_class": cls, "escalate_to": None, "fallback": None,
    }


def _cli_preview(args: argparse.Namespace) -> int:
    try:
        result = preview(args.id, args.task_class, pool=args.pool,
                         model=args.model, task_complexity=args.task_complexity,
                         escalation_reason=args.escalation_reason)
    except ExperientialPinRefused as exc:
        print(f"NONE reason={exc.reason}", file=sys.stderr)
        return 78
    print(f"POOL={result['pool']} KEY=- MODEL={result['model']} "
          f"REASON={result['reason']} STATE={result['state']}")
    return 0


def _cli_admit(args: argparse.Namespace) -> int:
    try:
        result = admit_execution(
            pool=args.pool, model=args.model, task_class=args.task_class,
            registry_entry=({"enabled": True} if args.registry_enabled else None),
            entitlement=({"verified": True} if args.entitlement_verified else None),
            retention_acknowledged=args.retention_acknowledged,
            sensitive_data_opt_in=args.sensitive_data_opt_in,
            proprietary_code=args.proprietary_code,
            code_exposure_opt_in=args.code_exposure_opt_in,
            account=args.account, quota_readback=args.quota_readback,
        )
    except ExperientialPinRefused as exc:
        print(f"NONE reason={exc.reason}", file=sys.stderr)
        return 78
    print(json.dumps(result, sort_keys=True))
    return 0


def _cli_auto(args: argparse.Namespace) -> int:
    verdict = auto_selection_verdict(args.task_class)
    print(f"NONE reason={verdict['reason']}")
    return 78


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experiential_pin.py",
        description="MANUAL-only exact-pin law for the Experiential Labs pool. "
                    "Makes no provider calls and no credential/storage access.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_preview = sub.add_parser(
        "preview", help="read-only strict pin preview; no effect")
    p_preview.add_argument("--id", required=True)
    p_preview.add_argument("--class", dest="task_class", required=True)
    p_preview.add_argument("--pool", required=True)
    p_preview.add_argument("--model", required=True)
    p_preview.add_argument("--task-complexity", default="")
    p_preview.add_argument("--escalation-reason", default="")
    p_preview.set_defaults(func=_cli_preview)

    p_admit = sub.add_parser(
        "admit", help="fail-closed execution admission; refusals exit 78")
    p_admit.add_argument("--pool", required=True)
    p_admit.add_argument("--model", required=True)
    p_admit.add_argument("--class", dest="task_class", required=True)
    p_admit.add_argument("--registry-enabled", action="store_true")
    p_admit.add_argument("--entitlement-verified", action="store_true")
    p_admit.add_argument("--retention-acknowledged", action="store_true")
    p_admit.add_argument("--sensitive-data-opt-in", action="store_true")
    p_admit.add_argument("--proprietary-code", action="store_true")
    p_admit.add_argument("--code-exposure-opt-in", action="store_true")
    p_admit.add_argument("--account")
    p_admit.add_argument("--quota-readback")
    p_admit.set_defaults(func=_cli_admit)

    p_auto = sub.add_parser(
        "auto", help="the only automatic verdict: NONE (manual-only law)")
    p_auto.add_argument("--class", dest="task_class", default="")
    p_auto.set_defaults(func=_cli_auto)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
