"""Read-only Tiingo materialization admission diagnostic, never a rights grant.

A cached EOD bar and a completed materialization are not PIT research admission.
This helper inspects the incumbent source-owner receipt only and never opens,
exports or stores vendor bars. Even all-true declared flags do not grant research
or redistribution permission without owner-side rights adjudication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

SCHEMA = "earnings.tiingo_materialization_inspection.research.v1"
SOURCE_SCHEMA = "mastermind.tiingo.materialized_receipt.v1"
EXPECTED_SOURCE_SCHEMA = "mastermind.tiingo.raw_receipt.v1"


class ManifestRefusal(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _utc(value: object) -> str:
    if not isinstance(value, str):
        raise ManifestRefusal("SOURCE_OBSERVATION_UTC_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestRefusal("SOURCE_OBSERVATION_UTC_REQUIRED") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ManifestRefusal("SOURCE_OBSERVATION_UTC_REQUIRED")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def inspect_tiingo_manifest(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        raise ManifestRefusal("SOURCE_RECEIPT_OBJECT_REQUIRED")
    if (receipt.get("schema") != SOURCE_SCHEMA
            or receipt.get("source_vendor") != "tiingo"
            or receipt.get("source_receipt_schema") != EXPECTED_SOURCE_SCHEMA):
        raise ManifestRefusal("UNSUPPORTED_MATERIALIZATION_OWNER")
    observed = _utc(receipt.get("source_observed_at_utc"))
    flags = ("pit_backtest_eligible", "redistribution_admitted", "dataos_identity_admitted")
    for flag in flags:
        if type(receipt.get(flag)) is not bool:
            raise ManifestRefusal("MATERIALIZATION_ADMISSION_FLAG_MISSING_OR_NOT_BOOLEAN")
    reasons = [flag.upper() + "_FALSE" for flag in flags if receipt[flag] is False]
    # There is no right for this *research helper* to independently authorize
    # another data owner's grants, even if all three flags are True.
    if not reasons:
        reasons.append("CANONICAL_SOURCE_OWNER_ACCEPTANCE_UNVERIFIED")
    if receipt.get("view_schema") != "mastermind.tiingo.research_views.v2":
        raise ManifestRefusal("UNSUPPORTED_MATERIALIZED_VIEW")
    if type(receipt.get("rows")) is not int or receipt["rows"] < 0:
        raise ManifestRefusal("INVALID_MATERIALIZATION_ROWS")
    return {
        "schema": SCHEMA,
        "source_schema": SOURCE_SCHEMA,
        "source_receipt_schema": EXPECTED_SOURCE_SCHEMA,
        "view_schema": receipt["view_schema"],
        "source_vendor": "tiingo",
        "source_observed_at_utc": observed,
        "source_rows_reported": receipt["rows"],
        "source_declared_flags": {name: receipt[name] for name in flags},
        "historical_price_admission": "NOT_ADMITTED",
        "export_or_backtest_permitted_by_this_helper": False,
        "reason_codes": reasons,
        "authority": "SOURCE_INSPECTION_ONLY_NO_TRADING",
    }


def inspect_file(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return inspect_tiingo_manifest(json.load(fh))
