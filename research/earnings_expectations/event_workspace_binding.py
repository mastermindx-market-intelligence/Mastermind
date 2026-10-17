"""Read-only binding from research events to the *existing* Earnings OS event owner.

The canonical owner is Macro's read_event_workspace() reader, which verifies
marker -> immutable generation -> object bytes. This adapter takes its returned
receipt and validates *identity agreement*, not the external bytes or authority.
It never publishes a new event, writes a crosswalk or grants prediction rights.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

SCHEMA = "earnings.research_native_event_binding.v1"
_EVENT_RE = re.compile(r"^evt_cik[0-9]{10}_[0-9]{4}q[1-4]_results$")
_GEN_RE = re.compile(r"^[0-9a-f]{24,64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CIK_RE = re.compile(r"^CIK:([0-9]{1,10})$")
_PERIOD_RE = re.compile(r"^(?:FY)?([0-9]{4})Q([1-4])$")
_PROPHET_DENIED = {
    "may_rank": False, "may_size": False, "may_gate": False,
    "prophet_authority": False,
}


class NativeEventBindingError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def candidate_identity(packet: dict) -> dict:
    """Derive a *candidate*, never an independently admitted event identity."""
    if not isinstance(packet, dict) or not isinstance(packet.get("event"), dict):
        raise NativeEventBindingError("RESEARCH_EVENT_REQUIRED")
    event = packet["event"]
    if not isinstance(event.get("event_ref"), str) or not event["event_ref"].strip():
        raise NativeEventBindingError("RESEARCH_EVENT_ID_REQUIRED")
    cik_raw, target = event.get("issuer_ref"), event.get("fiscal_target")
    issuer = _CIK_RE.fullmatch(cik_raw) if isinstance(cik_raw, str) else None
    period = _PERIOD_RE.fullmatch(target) if isinstance(target, str) else None
    if issuer is None or period is None:
        raise NativeEventBindingError("CIK_AND_EXPLICIT_FISCAL_QUARTER_REQUIRED")
    cik = issuer.group(1).zfill(10)
    year, quarter = int(period.group(1)), int(period.group(2))
    if year < 2000 or year > 2100:
        raise NativeEventBindingError("FISCAL_YEAR_OUT_OF_RANGE")
    prices = packet.get("price_series")
    issuer_prices = prices.get("issuer") if isinstance(prices, dict) else None
    ticker = issuer_prices.get("ticker") if isinstance(issuer_prices, dict) else None
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9.\-]{1,15}", ticker):
        raise NativeEventBindingError("EXPLICIT_RESEARCH_SECURITY_TICKER_REQUIRED")
    return {
        "candidate_event_id": f"evt_cik{cik}_{year}q{quarter}_results",
        "issuer_company_id": f"cik:{cik}",
        "fiscal_year": year,
        "fiscal_quarter": quarter,
        "research_security_ticker": ticker,
        "research_event_ref": event["event_ref"],
    }


def _url(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        raise NativeEventBindingError("IMMUTABLE_OWNER_RECEIPT_URL_REQUIRED")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or ".." in parsed.path.split("/")):
        raise NativeEventBindingError("IMMUTABLE_OWNER_RECEIPT_URL_REQUIRED")
    return f"https://{parsed.netloc}", parsed.path


def bind_native_event(packet: dict, native_read: dict) -> dict:
    candidate = candidate_identity(packet)
    if not _EVENT_RE.fullmatch(candidate["candidate_event_id"]):
        raise NativeEventBindingError("INVALID_CANONICAL_EVENT_CANDIDATE")
    cutoff = packet.get("evaluated_asof_utc")
    research_asof = None
    if cutoff is not None:
        if not isinstance(cutoff, str):
            raise NativeEventBindingError("RESEARCH_ASOF_UTC_INVALID")
        try:
            research_asof = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
        except ValueError as exc:
            raise NativeEventBindingError("RESEARCH_ASOF_UTC_INVALID") from exc
        if research_asof.tzinfo is None or research_asof.utcoffset() is None:
            raise NativeEventBindingError("RESEARCH_ASOF_UTC_INVALID")
        research_asof = research_asof.astimezone(timezone.utc)
    if not isinstance(native_read, dict):
        raise NativeEventBindingError("NATIVE_OWNER_READER_ENVELOPE_REQUIRED")
    if native_read.get("available") is False:
        return {
            "schema": SCHEMA, "status": "OWNER_EVENT_UNAVAILABLE",
            "candidate_event_id": candidate["candidate_event_id"],
            "research_event_ref": candidate["research_event_ref"],
            "owner_verified_by_this_helper": False,
            "source_owner_identity_admitted": False,
            "historical_event_availability_verified": False,
            "owner_generation_postdates_research_asof": None,
            "authority": "RESEARCH_DISPLAY_ONLY_NO_TRADING",
        }
    if (native_read.get("available") is not True
            or native_read.get("is_context_only") is not True
            or native_read.get("display_only") is not True
            or native_read.get("untrusted_source_data") is not True
            or native_read.get("authority") != "context_only"):
        raise NativeEventBindingError("NATIVE_OWNER_READER_CONTEXT_ENVELOPE_REQUIRED")
    workspace = native_read.get("workspace")
    receipt = native_read.get("receipt")
    if not isinstance(workspace, dict) or not isinstance(receipt, dict):
        raise NativeEventBindingError("NATIVE_WORKSPACE_AND_RECEIPT_REQUIRED")
    if workspace.get("schema") != "event_workspace.v1":
        raise NativeEventBindingError("NATIVE_WORKSPACE_SCHEMA_UNSUPPORTED")
    if (workspace.get("event_id") != candidate["candidate_event_id"]
            or native_read.get("event_id") != candidate["candidate_event_id"]):
        raise NativeEventBindingError("NATIVE_EVENT_IDENTITY_MISMATCH")
    issuer = workspace.get("issuer")
    period = workspace.get("fiscal_period")
    if not isinstance(issuer, dict) or not isinstance(period, dict):
        raise NativeEventBindingError("NATIVE_ISSUER_PERIOD_REQUIRED")
    if issuer.get("company_id") != candidate["issuer_company_id"]:
        raise NativeEventBindingError("NATIVE_ISSUER_IDENTITY_MISMATCH")
    if (type(period.get("year")) is not int or type(period.get("quarter")) is not int
            or period["year"] != candidate["fiscal_year"]
            or period["quarter"] != candidate["fiscal_quarter"]):
        raise NativeEventBindingError("NATIVE_FISCAL_TARGET_MISMATCH")
    listings = issuer.get("listings")
    if (not isinstance(listings, list)
            or candidate["research_security_ticker"] not in {
                row.get("ticker") for row in listings if isinstance(row, dict)
            }):
        raise NativeEventBindingError("NATIVE_LISTING_ALIAS_MISMATCH")
    if (workspace.get("authority") != "context_only"
            or workspace.get("prophet_flags") != _PROPHET_DENIED):
        raise NativeEventBindingError("NATIVE_EVENT_AUTHORITY_NOT_CONTEXT_ONLY")
    if (not isinstance(workspace.get("generated_at"), str)
            or not workspace["generated_at"].strip()):
        raise NativeEventBindingError("NATIVE_GENERATION_CLOCK_REQUIRED")
    try:
        clock = datetime.fromisoformat(workspace["generated_at"].replace("Z", "+00:00"))
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise NativeEventBindingError("NATIVE_GENERATION_CLOCK_REQUIRED")
    except ValueError as exc:
        raise NativeEventBindingError("NATIVE_GENERATION_CLOCK_REQUIRED") from exc
    generation = workspace.get("generation_id")
    if (not isinstance(generation, str) or not _GEN_RE.fullmatch(generation)
            or receipt.get("generation_id") != generation):
        raise NativeEventBindingError("NATIVE_GENERATION_RECEIPT_MISMATCH")
    for key in ("workspace_sha256", "marker_sha256"):
        value = receipt.get(key)
        if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
            raise NativeEventBindingError("NATIVE_IMMUTABLE_HASH_RECEIPT_REQUIRED")
    bases_and_paths = [_url(receipt.get(name)) for name in (
        "marker_url", "immutable_manifest_url", "workspace_url"
    )]
    if len({base for base, _ in bases_and_paths}) != 1:
        raise NativeEventBindingError("NATIVE_IMMUTABLE_RECEIPT_ORIGIN_MISMATCH")
    marker_path, manifest_path, workspace_path = [path for _, path in bases_and_paths]
    nest = "/event_workspaces"
    if (not marker_path.endswith(nest + "/manifest.json")
            or not manifest_path.endswith(
                nest + f"/generations/{generation}/manifest.json")
            or not workspace_path.endswith(
                nest + f"/generations/{generation}/workspaces/"
                + candidate["candidate_event_id"] + ".json")):
        raise NativeEventBindingError("NATIVE_IMMUTABLE_RECEIPT_PATH_MISMATCH")
    return {
        "schema": SCHEMA,
        "status": "IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED",
        "candidate_event_id": candidate["candidate_event_id"],
        "research_event_ref": candidate["research_event_ref"],
        "research_security_ticker": candidate["research_security_ticker"],
        "owner_generation_id": generation,
        "owner_workspace_sha256": receipt["workspace_sha256"],
        "owner_marker_sha256": receipt["marker_sha256"],
        "owner_verified_by_this_helper": False,
        "source_owner_identity_admitted": False,
        "historical_event_availability_verified": False,
        "owner_generation_postdates_research_asof": (
            clock.astimezone(timezone.utc) > research_asof
            if research_asof is not None else None
        ),
        "provenance_note": (
            "Reader envelope claims canonical marker/hash verification, but this "
            "offline adapter cannot independently re-fetch or verify the bytes."
        ),
        "authority": "RESEARCH_DISPLAY_ONLY_NO_TRADING",
    }
