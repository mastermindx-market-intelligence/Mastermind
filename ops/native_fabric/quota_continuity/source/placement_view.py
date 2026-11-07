#!/usr/bin/env python3
"""Read-only placement composition for CEO pool callers.

This tool composes existing host eligibility, an optional already-observed
provider plan, and the route-proof boundary. It is not an admission,
scheduling, registry, or reservation mechanism.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import host_pick


RoutePlan = {
    "go-codex": "go",
    "qwen": "bailian",
    "glm": "glm",
    "glm-codex": "glm",
    "minimax": "minimax",
    "minimax-codex": "minimax",
    "cursor": "cursor",
    "grok": "grok",
    "codex-native": "codex-native", "claude-native": "claude-native", "oc-free": "ocfree",
}
SUPPORTED_MODES = tuple(sorted(RoutePlan))
NUMERIC_TELEMETRY_FIELDS = (
    "ts",
    "load1",
    "load5",
    "ncpu",
    "mem_free_gb",
    "disk_free_gb",
    "active_lanes",
    "process_active_lanes",
)
LANE_OCCUPANCY_FIELDS = ("active", "locked", "legacy", "unlocked")
PLAN_ROW_INTEGER_FIELDS = (
    "grant_now",
    "fair_share",
    "held_by_me",
    "cluster_active",
    "cap",
    "need",
)
NO_HOST_RC = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _default_read_bytes(path: str) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1048576:
            raise OSError("observation must be a bounded regular file")
        data = handle.read(1048577)
        if len(data) > 1048576:
            raise OSError("observation exceeds size limit")
        return data


def _telemetry_snapshot(
    name: str,
    state_dir: str,
    now: datetime,
    reader: Callable[[str], bytes],
) -> Dict[str, Any]:
    path = os.path.join(state_dir, f"{name}.json")
    result: Dict[str, Any] = {
        "source": path,
        "status": "VALID",
        "timestamp": None,
        "observed_at": None,
        "age": None,
        "invalid_fields": [],
        "_document": None,
    }
    try:
        raw = reader(path)
    except FileNotFoundError:
        result["status"] = "MISSING"
        return result
    except OSError:
        result["status"] = "UNREADABLE"
        return result
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        result["status"] = "MALFORMED"
        return result
    if not isinstance(document, dict):
        result["status"] = "MALFORMED"
        return result

    result["_document"] = document

    timestamp = _finite_float(document.get("ts"))
    if timestamp is None or timestamp <= 0:
        result["status"] = "INVALID_TIME"
        result["invalid_fields"].append("ts")
        result["timestamp_raw"] = repr(document.get("ts"))
    elif timestamp > now.timestamp() + 1.0:
        result["status"] = "FUTURE_TIME"
        result["invalid_fields"].append("ts")
        result["timestamp"] = timestamp
        try:
            result["observed_at"] = _iso_timestamp(timestamp)
        except (ValueError, OverflowError, OSError):
            result["status"] = "INVALID_TIME"
    else:
        result["timestamp"] = timestamp
        result["observed_at"] = _iso_timestamp(timestamp)
        result["age"] = max(0, int(now.timestamp() - timestamp))

    for field in NUMERIC_TELEMETRY_FIELDS[1:]:
        value = document.get(field)
        if value is None:
            continue
        number = _finite_float(value)
        integer_field = field in ("ncpu", "active_lanes", "process_active_lanes")
        if number is None or number < 0 or (integer_field and type(value) is not int) or (field == "ncpu" and number == 0):
            result["invalid_fields"].append(field)
    occupancy = document.get("lane_occupancy")
    if occupancy is not None:
        if not isinstance(occupancy, Mapping):
            result["invalid_fields"].append("lane_occupancy")
        else:
            for field in LANE_OCCUPANCY_FIELDS:
                value = occupancy.get(field)
                if value is not None and (type(value) is not int or value < 0):
                    result["invalid_fields"].append(f"lane_occupancy.{field}")
    result["invalid_fields"] = sorted(set(result["invalid_fields"]))
    if result["status"] == "VALID" and result["invalid_fields"]:
        result["status"] = "INVALID_NUMERIC"
    return result


def _synthetic_invalid_host(name: str, telemetry: Dict[str, Any]) -> Dict[str, Any]:
    detail = ",".join(telemetry["invalid_fields"]) or telemetry["status"]
    return {
        "host": name,
        "eligible": False,
        "seat": False,
        "ssh_alias": None,
        "score": None,
        "age": telemetry.get("age"),
        "gates": [
            {
                "host": name,
                "gate": "telemetry-source",
                "result": "FAIL",
                "detail": detail,
            }
        ],
    }


def _evaluate_hosts_safely(
    registry: Dict[str, Dict[str, Any]],
    state_dir: str,
    mode: str,
    telemetry: Dict[str, Dict[str, Any]],
    *,
    required_tools: Optional[Iterable[str]],
    max_age: int,
    excluded: Iterable[str],
    now: datetime,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name in sorted(registry):
        source = telemetry[name]
        if source["status"] != "VALID":
            rows.append(_synthetic_invalid_host(name, source))
            continue
        try:
            row = host_pick.evaluate_hosts(
                {name: registry[name]},
                state_dir,
                mode,
                required_tools=required_tools,
                max_age=max_age,
                excluded=excluded,
                now=now,
                states={name: source["_document"]},
            )[0]
        except (OSError, ValueError, OverflowError, TypeError):
            row = _synthetic_invalid_host(name, source)
        rows.append(row)
    return rows


def _identity_findings(
    registry: Mapping[str, Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    owners: Dict[Tuple[str, str], List[str]] = {}
    for name, entry in registry.items():
        for label in ("ssh_alias", "hostnames"):
            values = entry.get(label)
            if values is None:
                continue
            if not isinstance(values, list):
                values = [values]
            for value in values:
                if value is not None:
                    owners.setdefault((label, str(value)), []).append(name)
    findings: List[Dict[str, Any]] = []
    shadowed: Dict[str, bool] = {}
    for label, value in sorted(owners):
        names = sorted(set(owners[(label, value)]))
        if len(names) < 2:
            continue
        findings.append(
            {
                "value": value,
                "registry_hosts": names,
                "kind": label,
                "conclusion": "SHARED_LABEL_NOT_PHYSICAL_IDENTITY",
                "physical_identity_proof": False,
            }
        )
        # Display hostnames are not identity. For an identical SSH alias,
        # retain the primary lanes entry and suppress only duplicate routes.
        if label == "ssh_alias":
            lanes = [n for n in names if "lanes" in (registry[n].get("roles") or [])]
            for name in lanes[1:]:
                shadowed[name] = True
    return findings, shadowed


def _plan_status(
    path: Optional[str],
    pool: str,
    need: int,
    max_age: int,
    now: datetime,
    reader: Callable[[str], bytes],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "input": os.fspath(path) if path is not None else None,
        "pool": pool,
        "status": "NOT_SUPPLIED",
        "timestamp": None,
        "observed_at": None,
        "age": None,
        "reasons": [],
        "row": None,
        "rows_observed": None,
        "requested_need": need,
        "allows_requested_need": None,
        "reservation": "NONE",
    }
    if path is None:
        result["reasons"].append("broker-plan-input-not-supplied")
        return result
    try:
        raw = reader(path)
    except FileNotFoundError:
        result["status"] = "MISSING"
        result["reasons"].append("broker-plan-input-missing")
        return result
    except OSError:
        result["status"] = "UNREADABLE"
        result["reasons"].append("broker-plan-input-unreadable")
        return result
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        result["status"] = "MALFORMED"
        result["reasons"].append("broker-plan-input-not-json")
        return result
    if isinstance(document, list):
        rows = document
    elif isinstance(document, dict):
        rows = document.get("rows")
    else:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        result["status"] = "MALFORMED"
        result["reasons"].append("broker-plan-rows-malformed")
        return result
    result["rows_observed"] = len(rows)
    timestamp: Optional[float] = None
    if isinstance(document, dict):
        timestamp = _finite_float(document.get("generated_at"))
    if timestamp is None or timestamp <= 0:
        result["status"] = "MALFORMED"
        result["reasons"].append("broker-plan-generated-at-invalid")
        return result
    result["timestamp"] = timestamp
    try:
        result["observed_at"] = _iso_timestamp(timestamp)
    except (ValueError, OverflowError, OSError):
        result["status"] = "MALFORMED"
        result["reasons"].append("broker-plan-generated-at-out-of-range")
        return result
    if timestamp > now.timestamp() + 1.0:
        result["status"] = "FUTURE_TIME"
        result["reasons"].append("broker-plan-generated-at-future")
        return result
    # Preserve sub-second precision for admission freshness. Flooring before
    # comparison previously labeled plans older than max_age as VALID_CURRENT.
    elapsed_seconds = max(0.0, now.timestamp() - timestamp)
    result["age"] = int(elapsed_seconds)
    if elapsed_seconds > max_age:
        result["status"] = "STALE"
        result["reasons"].append("broker-plan-older-than-max-age")
        return result

    matches = [row for row in rows if row.get("pool") == pool]
    if not matches:
        result["status"] = "POOL_MISSING"
        result["reasons"].append("selected-provider-row-missing")
        return result
    if len(matches) > 1:
        result["status"] = "POOL_AMBIGUOUS"
        result["reasons"].append("selected-provider-row-duplicated")
        return result
    row = matches[0]
    malformed = [
        field
        for field in PLAN_ROW_INTEGER_FIELDS
        if _integer(row.get(field)) is None or int(row[field]) < 0
    ]
    if malformed:
        result["status"] = "MALFORMED"
        result["reasons"].append("broker-plan-row-fields-invalid:" + ",".join(malformed))
        return result
    if row["grant_now"] > min(row["need"], max(0, row["cap"] - row["cluster_active"])):
        result["status"] = "MALFORMED"
        result["reasons"].append("broker-plan-grant-exceeds-observed-capacity")
        return result
    result["row"] = {"pool": pool, **{field: row[field] for field in PLAN_ROW_INTEGER_FIELDS}}
    if int(row["need"]) < need:
        result["status"] = "NEED_MISMATCH"
        result["reasons"].append("observed-plan-need-less-than-requested-need")
        return result
    result["allows_requested_need"] = int(row["grant_now"]) >= need
    result["status"] = "VALID_CURRENT"
    return result


def _candidate_exclusions(
    registry: Mapping[str, Mapping[str, Any]],
    mode: str,
) -> List[Dict[str, Any]]:
    exclusions: List[Dict[str, Any]] = []
    for name in sorted(registry):
        entry = registry[name]
        roles = entry.get("roles") or []
        reasons: List[str] = []
        if "candidate" in roles or "lanes" not in roles:
            reasons.append("role-not-admitted-for-lanes")
        allowed = entry.get("allowed_modes")
        if allowed is None and mode in {"qwen", "go-codex", "grok", "cursor", "codex-native", "claude-native", "oc-free"}:
            reasons.append("explicit-mode-qualification-required")
        qualification = entry.get("qualification_only_modes", [])
        if not isinstance(qualification, list):
            reasons.append("invalid-qualification-policy")
        elif mode in qualification:
            reasons.append("explicit-canary-only")
        if allowed is not None:
            if not isinstance(allowed, list) or mode not in allowed:
                reasons.append("mode-not-authorized")
        if reasons:
            exclusions.append({"host": name, "reasons": sorted(set(reasons))})
    return exclusions


def build_placement_view(
    registry: Dict[str, Dict[str, Any]],
    state_dir: str,
    mode: str,
    *,
    need: int = 1,
    max_age: int = 600,
    excluded: Optional[Iterable[str]] = None,
    plan_path: Optional[str] = None,
    plan_max_age: Optional[int] = None,
    now: Optional[datetime] = None,
    state_reader: Callable[[str], bytes] = _default_read_bytes,
    plan_reader: Callable[[str], bytes] = _default_read_bytes,
    selection_key: Optional[str] = None,
    evaluator: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    chooser: Callable[..., Optional[Dict[str, Any]]] = host_pick.choose_host,
) -> Dict[str, Any]:
    """Compose a finite, read-only placement view from supplied observations."""
    if mode not in RoutePlan:
        raise ValueError(f"unsupported mode: {mode}")
    if type(need) is not int or need <= 0:
        raise ValueError("need must be a positive integer")
    if max_age < 0 or (plan_max_age is not None and plan_max_age < 0):
        raise ValueError("max ages must be non-negative")
    observed_at = now or _utc_now()
    if observed_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    excluded_hosts = set(excluded or ())
    telemetry = {
        name: _telemetry_snapshot(name, state_dir, observed_at, state_reader)
        for name in registry
    }
    evaluate = evaluator or _evaluate_hosts_safely
    rows = evaluate(
        registry,
        state_dir,
        mode,
        telemetry,
        required_tools=None,
        max_age=max_age,
        excluded=excluded_hosts,
        now=observed_at,
    )
    exclusions = _candidate_exclusions(registry, mode)
    excluded_names = {item["host"] for item in exclusions}
    identity_findings, shadowed = _identity_findings(registry)
    for name in shadowed:
        if name not in excluded_names:
            excluded_names.add(name)
            exclusions.append(
                {"host": name, "reasons": ["duplicate-ssh-route"]}
            )

    host_by_name = {row.get("host"): row for row in rows}
    for name, row in host_by_name.items():
        row["candidate_excluded"] = name in excluded_names
        row["identity_shadowed"] = shadowed.get(name, False)
        row["telemetry_source"] = {k: v for k, v in telemetry[name].items() if k != "_document"}

    eligible_for_choice = [
        row for row in rows if not row.get("candidate_excluded", False)
    ]
    host_choice = (
        chooser(eligible_for_choice, prefer_remote=True)
        if selection_key is None else
        chooser(eligible_for_choice, prefer_remote=True, placement_key=selection_key)
    )
    plan = _plan_status(
        plan_path,
        RoutePlan[mode],
        need,
        plan_max_age if plan_max_age is not None else max_age,
        observed_at,
        plan_reader,
    )
    route_qualification = {
        "status": "UNPROVEN",
        "reason": "supplied-sources-define-no-route-qualification-receipt",
        "physical_identity_proof": False,
    }
    if host_choice is None:
        view_status = "NO_HOST_ELIGIBLE"
        advisory_host = None
    elif plan["allows_requested_need"] is False:
        view_status = "HOST_ELIGIBLE_PROVIDER_PLAN_INSUFFICIENT"
        advisory_host = None
    elif plan["status"] == "VALID_CURRENT":
        view_status = "ADVISORY_HOST"
        advisory_host = host_choice["host"]
    else:
        view_status = "HOST_CHOICE_WITH_PROVIDER_OBSERVATION_UNAVAILABLE"
        advisory_host = host_choice["host"]

    return {
        "schema": "placement-view.private-candidate.v1",
        "generated_at": _iso_timestamp(observed_at.timestamp()),
        "mode": mode,
        "provider_pool_selected_by_existing_pool_pick": RoutePlan[mode],
        "requested_need": need,
        "view_status": view_status,
        "advisory_host": advisory_host,
        "host_choice": None if host_choice is None else host_choice["host"],
        "ceiling": {
            "advisory_only": True,
            "may_start_process": False,
            "may_reserve_provider": False,
            "claims_provider_usable": False,
            "claims_route_authorized": False,
            "existing_admission_authoritative": True,
        },
        "host_eligibility": {
            "status": "ELIGIBLE" if host_choice is not None else "NO_ELIGIBLE_HOST",
            "selected_by_existing_host_pick": None if host_choice is None else host_choice["host"],
            "max_age": max_age,
            "hosts": rows,
        },
        "provider_slots": plan,
        "route_qualification": route_qualification,
        "candidate_exclusions": exclusions,
        "identity_findings": identity_findings,
        "reservation": "NONE",
        "runnable_slot_total": None,
        "runnable_slot_total_reason": "host-and-provider-eligibility-is-not-a-runnable-capacity-proof",
    }


def _format_gate(gate: Mapping[str, Any]) -> str:
    detail = f"({gate['detail']})" if gate.get("detail") else ""
    return f"{gate['gate']}={gate['result']}{detail}"


def render_text(view: Mapping[str, Any]) -> str:
    lines = [
        "PLACEMENT VIEW (ADVISORY ONLY: NO START, NO RESERVATION)",
        f"mode={view['mode']} need={view['requested_need']} generated_at={view['generated_at']}",
        f"view_status={view['view_status']} advisory_host={view['advisory_host'] or 'NONE'}",
        f"HOST_ELIGIBILITY status={view['host_eligibility']['status']} selected={view['host_choice'] or 'NONE'}",
    ]
    for row in view["host_eligibility"]["hosts"]:
        flags = []
        if row.get("candidate_excluded"):
            flags.append("CANDIDATE_EXCLUDED")
        if row.get("identity_shadowed"):
            flags.append("IDENTITY_SHADOWED")
        source = row.get("telemetry_source") or {}
        timestamp = source.get("observed_at") or "NA"
        status = source.get("status", "NA")
        score = "NA" if row.get("score") is None else f"{row['score']:.4f}"
        suffix = (" " + ",".join(flags)) if flags else ""
        lines.append(
            f"  {row['host']} {'ELIGIBLE' if row.get('eligible') else 'INELIGIBLE'} "
            f"score={score} source={timestamp}/{status} gates=" +
            ";".join(_format_gate(gate) for gate in row.get("gates", [])) +
            suffix
        )
    plan = view["provider_slots"]
    grant = "NA" if plan.get("row") is None else plan["row"].get("grant_now")
    lines.extend(
        [
            (
                f"PROVIDER_SLOTS status={plan['status']} pool={plan['pool']} "
                f"grant_now={grant} need={plan['requested_need']} "
                f"observed_at={plan.get('observed_at') or 'NA'} reservation=NONE"
            ),
            (
                f"ROUTE_QUALIFICATION status={view['route_qualification']['status']} "
                "proof=MISSING physical_identity=UNPROVEN"
            ),
        ]
    )
    for exclusion in view["candidate_exclusions"]:
        lines.append(
            f"  EXCLUDED host={exclusion['host']} reasons={','.join(exclusion['reasons'])}"
        )
    for finding in view["identity_findings"]:
        lines.append(
            "  IDENTITY_SHADOW value=" + str(finding["value"]) +
            " hosts=" + ",".join(finding["registry_hosts"]) +
            " physical_identity_proof=false"
        )
    lines.append("CEILING=no-start no-reservation no-usable-provider-claim existing-admission-authoritative")
    lines.append("TOTAL_RUNNABLE_SLOTS=NOT_CLAIMED")
    return "\n".join(lines)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=SUPPORTED_MODES)
    parser.add_argument("--need", type=int, default=1)
    parser.add_argument("--max-age", type=int, default=600)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--plan", help="already-observed broker plan JSON; never invoked")
    parser.add_argument("--plan-max-age", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--hosts", help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    hosts_path = args.hosts or os.environ.get(
        "PLACEMENT_VIEW_HOSTS", os.path.join(HERE, "hosts.json")
    )
    state_dir = args.state_dir or os.environ.get(
        "HOST_PICK_STATE_DIR", os.path.join(HERE, "state", "hosts")
    )
    try:
        registry = host_pick.load_registry(hosts_path)
        view = build_placement_view(
            registry,
            state_dir,
            args.mode,
            need=args.need,
            max_age=args.max_age,
            excluded=args.exclude,
            plan_path=args.plan,
            plan_max_age=args.plan_max_age,
        )
    except (OSError, ValueError, OverflowError):
        print("PLACEMENT_VIEW_ERROR", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(view, sort_keys=True, separators=(",", ":"), allow_nan=False))
    else:
        print(render_text(view))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
