"""Versioned closed schemas for the public-observation profile, not legacy tools."""
from __future__ import annotations

import hashlib
import json

from .contracts import ENDPOINTS, MAX_SYMBOLS, SCHEMA, SYMBOL_PATTERN
from .reader import CHECKS, COUNTS

SERVER_VERSION = "1.0.0"
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
CHECK = obj({"state": {"enum": ["missing", "unavailable", "invalid", "ok", "observed", "stale", "partial", "unknown"]},
             "source_time": STAMP, "file_age_minutes": nullable({"type": "number", "minimum": 0}),
             "commit": REVISION, "counts": obj({k: COUNT for k in COUNTS})})
STATUS = obj({"reported_status": {"enum": ["ok", "unknown"]}, "process_revision": REVISION,
              "checks": {"type": "object", "properties": {k: {"$ref": "#/$defs/check"} for k in sorted(CHECKS)}, "additionalProperties": False},
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
        schema["$defs"] = {"check": CHECK}
    return schema


TOOL_SPECS = (
    {"name": "product_diagnostics", "description": "Observe public Macro backend build/checkout and publication diagnostics. No private account, refresh or admin access.",
     "inputSchema": obj({}), "outputSchema": output("product_diagnostics", [observation("health", HEALTH), observation("status", STATUS)])},
    {"name": "product_market_pulse", "description": "Observe at most 12 regular-session quotes from the existing public Terminal market-data projection. Preserve source freshness and partial coverage; no trades.",
     "inputSchema": obj({"symbols": {"type": "array", "minItems": 1, "maxItems": MAX_SYMBOLS, "uniqueItems": True,
                                    "items": {"type": "string", "pattern": "^" + SYMBOL_PATTERN + "$"}}}),
     "outputSchema": output("product_market_pulse", [observation("market_pulse", PULSE)])},
)
for spec in TOOL_SPECS:
    spec["annotations"] = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    spec["_meta"] = {"securitySchemes": [{"type": "oauth2", "scopes": [SCOPE]}]}
SCHEMA_SNAPSHOT_SHA256 = hashlib.sha256(json.dumps({"server_version": SERVER_VERSION, "tools": TOOL_SPECS},
    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
