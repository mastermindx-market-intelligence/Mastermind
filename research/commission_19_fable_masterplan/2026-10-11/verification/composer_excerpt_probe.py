"""Isolated synthetic probes of two inspected source excerpts.

This is NOT the complete imported application, a production test, or a repair.
The two function bodies were transcribed from GitHub connector reads of
macro@50a7771721618e373eeb6e91b92c5f07860ee9f4/app/integrated_answer.py.
Connector-reported full-file Git blob: fee6c1876e8d488a60be9e06493ba4b18d63caab.
The full file could not be downloaded to this container; no local full-file hash
verification is claimed. All owner calls are replaced with synthetic suppliers.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import hashlib
import json

STALE_DAYS = 4

def _normalize_clock(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T00:00:00Z"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")

# Source-equivalent composition logic, omitting only the output's fixed
# bilingual stance/footer/coverage copy. These omitted strings have no bearing
# on clock selection or staleness classification. No dynamic eval or imports.
def composition_clock_projection(legs: list[dict], composed_at: str) -> dict:
    legs = copy.deepcopy(legs)
    surfaced = [item for item in legs if item["status"] in {"ok", "stale"}]
    if surfaced:
        page_as_of = max(item["ref"]["as_of"] for item in surfaced if item.get("ref"))
    else:
        page_as_of = composed_at
    cutoff = datetime.fromisoformat(page_as_of.replace("Z", "+00:00"))
    stale_before = cutoff - timedelta(days=STALE_DAYS)
    for item in legs:
        if item["leg"] == "event_workspace":
            continue
        if item["status"] not in {"ok", "stale"}:
            continue
        ref = item.get("ref")
        if not ref:
            continue
        leg_clock = datetime.fromisoformat(ref["as_of"].replace("Z", "+00:00"))
        if leg_clock < stale_before:
            item["status"] = "stale"
            item["degraded_reason"] = "older_than_page_stamp"
    return {"as_of": page_as_of, "composed_at": composed_at, "legs": legs}

def leg(name: str, timestamp: str) -> dict:
    return {"leg": name, "status": "ok", "ref": {"as_of": timestamp}}

def main() -> None:
    now = "2026-10-11T06:40:00Z"
    old = "2026-09-01T00:00:00Z"
    future = "2026-11-01T00:00:00Z"
    cases = []
    def record(name: str, actual: object, expected: object, limitation: str) -> None:
        assert actual == expected, (name, actual, expected)
        cases.append({"id": name, "observed": actual, "expected_source_behavior": expected,
                      "source_behavior_reproduced": True, "interpretation": limitation})
    record("P01_DATE_ONLY", _normalize_clock("2026-10-10"), "2026-10-10T00:00:00Z",
           "Display normalization loses date precision; not valid evidence of intraday availability.")
    record("P02_INVALID_DATE", _normalize_clock("2026-99-99"), "2026-99-99T00:00:00Z",
           "Length/separator branch accepts an invalid calendar date; reachability in actual owner inputs not tested.")
    record("P03_NAIVE_TIME", _normalize_clock("2026-10-10T10:00:00"), "2026-10-10T10:00:00Z",
           "Naive timestamps are assigned UTC without source timezone evidence.")
    record("P04_OFFSET_CONTROL", _normalize_clock("2026-10-10T10:00:00-04:00"), "2026-10-10T14:00:00Z",
           "Positive control: explicit offsets convert correctly.")
    old_result = composition_clock_projection([leg("financial_facts", old), leg("theme_tape", old)], now)
    record("P05_ALL_OLD", [x["status"] for x in old_result["legs"]], ["ok", "ok"],
           "All equally old legs remain ok because the comparison clock is the newest old source, not request time.")
    future_result = composition_clock_projection([leg("theme_tape", future)], now)
    record("P06_FUTURE_CLOCK", {"as_of": future_result["as_of"], "status": future_result["legs"][0]["status"]},
           {"as_of": future, "status": "ok"},
           "This composition step does not itself refuse a future source clock; upstream validation not tested.")
    event_result = composition_clock_projection([leg("event_workspace", old), leg("theme_tape", now)], now)
    record("P07_EVENT_EXEMPT", event_result["legs"][0]["status"], "ok",
           "Event workspace is deliberately exempt from the generic stale pass; current-alias is not freshness evidence.")
    mixed_result = composition_clock_projection([leg("financial_facts", old), leg("theme_tape", now)], now)
    record("P08_MIXED_AGE_CONTROL", [x["status"] for x in mixed_result["legs"]], ["stale", "ok"],
           "Positive control: relative-age staleness logic works when another source is current.")
    report = {"classification": "synthetic_transcribed_source_excerpt_logic_probe",
              "source_repository": "mastermindx-market-intelligence/macro",
              "source_commit": "50a7771721618e373eeb6e91b92c5f07860ee9f4",
              "source_path": "app/integrated_answer.py",
              "connector_reported_git_blob": "fee6c1876e8d488a60be9e06493ba4b18d63caab",
              "full_file_hash_verified_locally": False,
              "full_application_imported": False,
              "real_producer_or_browser_tested": False,
              "code_repaired": False,
              "cases": cases, "case_count": len(cases), "assertions_passed": True,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    target = Path(__file__).with_name("composer_excerpt_probe_result.json")
    target.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"cases": len(cases), "assertions_passed": True,
                      "scope": report["classification"], "output": str(target)}))

if __name__ == "__main__":
    main()
