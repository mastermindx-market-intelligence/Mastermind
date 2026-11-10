"""Versioned closed schemas for the public-observation profile, not legacy tools."""
from __future__ import annotations

import hashlib
import json

from .contracts import BODY_LIMITS, ENDPOINTS, MAX_SYMBOLS, SCHEMA, SYMBOL_PATTERN
from .projections import (BANDS, CAUSE_BASES, MARKET_STATES, OVERLAY_REASONS,
                          OWNER_REASON_CODES, RISK_REASONS, SESSION_STATES,
                          SOURCE_BASES, UNKNOWN_OWNER_REASON, UNKNOWN_STATES)
from .reader import CHECKS, COUNTS

SERVER_VERSION = "1.3.0"
SCOPE = "product.observe"


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


NUMBER = nullable({"type": "number"})
COUNT = nullable({"type": "integer", "minimum": 0, "maximum": 2**53 - 1})
REVISION = nullable({"type": "string", "pattern": "^[0-9a-f]{7,40}$"})
STAMP = obj({"value": nullable({"type": "string", "format": "date-time", "maxLength": 64}),
             "status": {"enum": ["unknown", "invalid", "future", "observed"]}, "age_seconds": NUMBER})
HEALTH = obj({"reported_status": {"const": "ok"}, "process_revision": REVISION, "checkout_revision": REVISION,
              "checkout_drift": {"type": ["boolean", "null"]}, "exact_deployment_verified": {"const": False}})
CHECK_COUNTS = obj({k: COUNT for k in COUNTS})
CHECK = obj({"state": {"enum": ["missing", "unavailable", "invalid", "ok", "observed", "stale", "partial", "unknown"]},
             "source_time": STAMP, "file_age_minutes": nullable({"type": "number", "minimum": 0}),
             "commit": REVISION, "counts": {"$ref": "#/$defs/check_counts"}})
# Breadth's source usability is an existing producer adjudication, never inferred
# from a recently copied artifact. All output fields remain closed.
BREADTH_SEMANTICS = obj({
    "usable": nullable({"type": "boolean"}),
    "usable_status": {"enum": ["observed", "unknown", "invalid"]},
    "feed_status": {"enum": ["ok", "not_authorized", "error", "no_response", "offline",
                            "no_key", "no_thresholds", "unknown", "invalid", "other"]},
    "source_asof": STAMP,
    "source_age_minutes": NUMBER,
    "source_age_status": {"enum": ["observed", "unknown", "invalid"]},
    "omitted_known_field_count": {"type": "integer", "minimum": 0, "maximum": 32},
    "unrecognized_field_count": {"type": "integer", "minimum": 0, "maximum": 2**53 - 1},
})
BREADTH_CHECK = obj({**CHECK["properties"], "producer_semantics": BREADTH_SEMANTICS})

STATUS = obj({"reported_status": {"enum": ["ok", "unknown"]}, "process_revision": REVISION,
              "checks": {"type": "object", "properties": {k: {"$ref": "#/$defs/breadth_check" if k == "breadth" else "#/$defs/check"} for k in sorted(CHECKS)}, "additionalProperties": False},
              "omitted_check_count": {"type": "integer", "minimum": 0, "maximum": 64},
              "freshness_policy": {"const": "unknown; source timestamps and file age are observations, not currentness proof"}})
ITEM = obj({"symbol": {"type": "string", "pattern": "^" + SYMBOL_PATTERN + "$"},
            "price": {"type": "number", "exclusiveMinimum": 0}, "change_abs": NUMBER, "change_pct": NUMBER,
            "currency": nullable({"type": "string", "pattern": "^[A-Z]{3}$"}),
            "session": {"enum": ["regular", "closed"]}, "owner_freshness": {"enum": ["live", "delayed", "stale"]},
            "regular_session_date": nullable({"type": "string", "format": "date"}),
            "revision": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
            "observed_at": STAMP, "received_at": STAMP, "published_at": STAMP, "timestamp_qualified": {"type": "boolean"}})
PULSE = obj({"snapshot_id": {"type": "string", "pattern": "^[0-9a-f]{16}$"}, "generated_at": STAMP,
             "owner_state": obj({"availability": {"enum": ["available", "unavailable"]},
                                  "freshness": {"enum": ["live", "delayed", "stale"]},
                                  "session": {"enum": ["regular", "closed", "mixed"]}, "coverage": {"enum": ["complete", "partial"]}}),
             "coverage": obj({k: {"type": "integer", "minimum": 0, "maximum": MAX_SYMBOLS}
                              for k in ("requested", "resolved", "live", "delayed", "stale", "missing")}),
             "items": {"type": "array", "maxItems": MAX_SYMBOLS, "items": ITEM},
             "errors": {"type": "array", "maxItems": MAX_SYMBOLS, "items": obj({
                 "symbol": {"type": "string", "pattern": "^" + SYMBOL_PATTERN + "$"}, "code": {"const": "quote_unavailable"}})},
             "source_view": {"const": "regular"}})


def observation(endpoint, data):
    schema = obj({"endpoint": {"const": endpoint}, "url": {"const": ENDPOINTS[endpoint]},
        "source_owner": {"const": "terminal-market-data" if endpoint == "market_pulse" else "macro-api"},
        "environment": {"const": "production"}, "access_class": {"const": "public"},
        "observed_at": {"type": "string", "format": "date-time", "maxLength": 64},
        "http_status": nullable({"type": "integer", "minimum": 100, "maximum": 599}),
        "sha256": nullable({"type": "string", "pattern": "^[0-9a-f]{64}$"}),
        "state": {"enum": ["observed", "unavailable", "invalid", "missing", "unauthorized"]}, "data": nullable(data)})
    schema["allOf"] = [{"if": {"properties": {"state": {"const": "observed"}}},
                        "then": {"properties": {"data": {"type": "object"}, "http_status": {"const": 200},
                                                "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}},
                        "else": {"properties": {"data": {"type": "null"}, "sha256": {"type": "null"}}}}]
    return schema


def output(tool, rows):
    schema = obj({"schema": {"const": SCHEMA}, "tool": {"const": tool},
        "observations": {"type": "array", "prefixItems": rows, "items": False, "minItems": len(rows), "maxItems": len(rows)},
        "limitations": {"const": ["public observations only; not a product-user session",
                                   "source-reported freshness is not recomputed or guaranteed current",
                                   "exact deployment and preview revisions are not verified"]}})
    if tool == "product_diagnostics":
        schema["$defs"] = {"check": CHECK, "breadth_check": BREADTH_CHECK, "check_counts": CHECK_COUNTS}
    return schema


# Additive schemas: the two existing tool schemas above remain byte-equivalent.
DATE = nullable({"type": "string", "format": "date"})
BOOLEAN = nullable({"type": "boolean"})
SOURCE_REASONS = obj({
    "codes": {"type": "array", "maxItems": len(OWNER_REASON_CODES) + 1, "uniqueItems": True,
              "items": {"enum": [*OWNER_REASON_CODES, UNKNOWN_OWNER_REASON]}},
    "count": COUNT, "valid": {"type": "boolean"},
})
OVERLAY_FRESHNESS = obj({
    "state": {"const": "partial"}, "qualified": {"const": False},
    "reasons": {"type": "array", "minItems": 2, "maxItems": len(OVERLAY_REASONS),
                "uniqueItems": True, "items": {"enum": list(OVERLAY_REASONS)}},
})
RISK_FRESHNESS = obj({
    "state": {"enum": ["qualified", "partial", "stale"]}, "qualified": {"type": "boolean"},
    "reasons": {"type": "array", "maxItems": len(RISK_REASONS), "uniqueItems": True,
                "items": {"enum": list(RISK_REASONS)}},
})
RISK_FRESHNESS["allOf"] = [{
    "if": {"properties": {"qualified": {"const": True}}},
    "then": {"properties": {"state": {"const": "qualified"}, "reasons": {"maxItems": 0}}},
    "else": {"properties": {"state": {"enum": ["partial", "stale"]}, "reasons": {"minItems": 1}}},
}]
MARKET_CONTEXT = obj({
    "stale": BOOLEAN, "band": {"enum": [*BANDS, *UNKNOWN_STATES]},
    "data_state": {"enum": [*MARKET_STATES, *UNKNOWN_STATES]}, "data_frozen": BOOLEAN,
    "data_through": DATE, "session_state": {"enum": [*SESSION_STATES, *UNKNOWN_STATES]},
})
SESSION_CONTEXT = obj({
    "state": {"enum": [*SESSION_STATES, *UNKNOWN_STATES]}, "calendar_verified": BOOLEAN,
    "data_frozen": BOOLEAN, "expected_session": DATE,
})
OVERLAY = obj({
    "schema": {"const": "live.overlay.v2"}, "built": {"$ref": "#/$defs/stamp"},
    "quote_ts_max": {"$ref": "#/$defs/stamp"},
    **{key: {"type": "integer", "minimum": 0, "maximum": 500} for key in ("n", "n_fresh", "n_quotes")},
    "delayed_min": {"type": "integer", "minimum": 0, "maximum": 1440}, "reported_realtime": {"type": "boolean"},
    "market": {"type": "object", "properties": {key: {"$ref": "#/$defs/market_context"} for key in ("SPY", "QQQ", "VIX")},
               "additionalProperties": False},
    "sessions": {"type": "object", "properties": {key: {"$ref": "#/$defs/session_context"} for key in ("us", "cn", "hk", "ca")},
                 "additionalProperties": False},
    "freshness": OVERLAY_FRESHNESS,
})
RISK = obj({
    "schema": {"const": "market_risk/v1"}, "verdict": {"enum": ["RISK_ON", "MIXED", "RISK_OFF"]},
    "score": nullable({"type": "number", "minimum": 0, "maximum": 100}),
    "asof": {"type": "string", "format": "date"}, "is_display_only": {"const": True}, "stale": BOOLEAN,
    **{key: {"$ref": "#/$defs/stamp"} for key in ("built", "source_event_time", "stale_after")},
    "source_basis": {"enum": [*SOURCE_BASES, *UNKNOWN_STATES]},
    "cause_basis": {"enum": [*CAUSE_BASES, *UNKNOWN_STATES]},
    "owner_freshness": obj({"qualified": BOOLEAN, "reasons": {"$ref": "#/$defs/source_reasons"}}),
    "stale_reasons": {"$ref": "#/$defs/source_reasons"}, "freshness": RISK_FRESHNESS,
})


def projection_observation(endpoint, data):
    # Complete invalid bodies retain honest evidence. Older tool contracts keep
    # their historical null-digest rule on every non-observed result.
    row = obj({
        "endpoint": {"const": endpoint}, "url": {"const": ENDPOINTS[endpoint]},
        "source_owner": {"const": "terminal-market-data" if endpoint == "market_risk" else "macro-api"},
        "environment": {"const": "production"}, "access_class": {"const": "public"},
        "observed_at": {"type": "string", "format": "date-time", "maxLength": 64},
        "http_status": nullable({"type": "integer", "minimum": 100, "maximum": 599}),
        "sha256": nullable({"type": "string", "pattern": "^[0-9a-f]{64}$"}),
        "state": {"enum": ["observed", "unavailable", "invalid", "missing", "unauthorized"]},
        "data": nullable(data), "representation": {"enum": ["complete", "not_observed"]},
        "body_bytes": nullable({"type": "integer", "minimum": 0, "maximum": BODY_LIMITS[endpoint]}),
    })
    row["allOf"] = [
        {"if": {"properties": {"representation": {"const": "complete"}}},
         "then": {"properties": {"http_status": {"const": 200},
                                 "state": {"enum": ["observed", "invalid"]},
                                 "body_bytes": {"type": "integer"},
                                 "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}},
         "else": {"properties": {"body_bytes": {"type": "null"}, "sha256": {"type": "null"}}}},
        {"if": {"properties": {"state": {"const": "observed"}}},
         "then": {"properties": {"data": {"type": "object"}, "representation": {"const": "complete"},
                                 "body_bytes": {"type": "integer", "minimum": 1}}},
         "else": {"properties": {"data": {"type": "null"}}}},
        {"if": {"properties": {"body_bytes": {"const": 0}}},
         "then": {"properties": {"state": {"const": "invalid"},
                                 "sha256": {"const": hashlib.sha256(b"").hexdigest()}}}},
    ]
    return row


def projection_output(tool, endpoint, data):
    schema = output(tool, [projection_observation(endpoint, data)])
    schema["$defs"] = {"stamp": STAMP}
    if endpoint == "macro_overlay":
        schema["$defs"].update(market_context=MARKET_CONTEXT, session_context=SESSION_CONTEXT)
    else:
        schema["$defs"]["source_reasons"] = SOURCE_REASONS
    return schema


TOOL_SPECS = (
    {"name": "product_diagnostics", "description": "Observe public Macro backend build/checkout and publication diagnostics. No private account, refresh or admin access.",
     "inputSchema": obj({}), "outputSchema": output("product_diagnostics", [observation("health", HEALTH), observation("status", STATUS)])},
    {"name": "product_market_pulse", "description": "Observe at most 12 regular-session quotes from the existing public Terminal market-data projection. Preserve source freshness and partial coverage; no trades.",
     "inputSchema": obj({"symbols": {"type": "array", "minItems": 1, "maxItems": MAX_SYMBOLS, "uniqueItems": True,
                                    "items": {"type": "string", "pattern": "^" + SYMBOL_PATTERN + "$"}}}),
     "outputSchema": output("product_market_pulse", [observation("market_pulse", PULSE)])},
    {"name": "product_macro_overlay", "description": "Observe fixed public Macro overlay counts, source clocks and session context without quote prices. Delayed display evidence stays unqualified for current regime or trades.",
     "inputSchema": obj({}), "outputSchema": projection_output("product_macro_overlay", "macro_overlay", OVERLAY)},
    {"name": "product_market_risk", "description": "Observe the fixed public Terminal display-only risk headline. Preserve owner verdict, optional score, session and freshness refusals; no trade or private-account authority.",
     "inputSchema": obj({}), "outputSchema": projection_output("product_market_risk", "market_risk", RISK)},
)
for spec in TOOL_SPECS:
    spec["annotations"] = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    # Per-tool top-level securitySchemes is necessary for ChatGPT OAuth linking.
    # A nested _meta.securitySchemes field is not an equivalent SDK wire contract.
    spec["securitySchemes"] = [{"type": "oauth2", "scopes": [SCOPE]}]
SCHEMA_SNAPSHOT_SHA256 = hashlib.sha256(json.dumps({"server_version": SERVER_VERSION, "tools": TOOL_SPECS},
    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
