#!/usr/bin/env python3
"""Loopback-only browser fixture harness; never import the production app lifespan.

The fresh FastAPI instance exposes only the existing read-only page, theme, and
Market View API routes plus contained static assets and a harness manifest. Its
actual API handler reads temporary fixture files through the actual reader at a
declared fixed clock. Production authentication, publication, jobs and lifecycle
are deliberately outside this browser proof.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import importlib.util
import ipaddress
import json
import socket
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load exact local source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_view_from_native_test(path):
    """Read the existing native API test's literal background fixture."""
    tree = ast.parse(Path(path).read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "frozen_view"]
    if len(functions) != 1 or len(functions[0].body) != 1 or not isinstance(functions[0].body[0], ast.Return):
        raise RuntimeError("Native frozen_view fixture changed; review harness binding")
    value = ast.literal_eval(functions[0].body[0].value)
    if not isinstance(value, dict):
        raise RuntimeError("Native background fixture is not an object")
    return value


def prepare(args):
    root = Path(args.mastermind_root).resolve()
    macro_root = Path(args.macro_root).resolve()
    data_root = Path(args.capture_data_root).resolve()
    fixture = Path(args.fixture_feed).resolve() if args.fixture_feed else root / "tests/fixtures/sovereign_auction_context/event_calendar.json"
    cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise RuntimeError("An aware fixed cutoff is required")
    cutoff_text = cutoff.isoformat()
    producer_path = macro_root / "engine/treasury_auction_lifecycle.py"
    consumer_path = root / "brain/sovereign_auction_context.py"
    native_fixture_path = root / "tests/test_sovereign_auction_api.py"
    producer = load_module("_ui_exact_auction_producer", producer_path)
    reader = load_module("_ui_exact_auction_reader", consumer_path)
    observations = sorted((data_root / "treasury_auctions/observations").glob("*.json"))
    if not observations or len(observations) > 128:
        raise RuntimeError("This bounded proof requires 1–128 captured receipt files")
    observed = producer.snapshot(data_dir=data_root, as_of=cutoff_text, horizon_days=30)
    projected = reader.validate_context(observed, now=cutoff_text)
    states = Counter(row["physical_state"] for row in projected["events"])
    if not projected["available"] or states["ANNOUNCED"] < 1 or states["RESULT_OBSERVED"] < 1:
        raise RuntimeError("Actual capture must contain both scheduled auctions and past observed results")
    shared = json.loads(fixture.read_text())["sovereign_auction_context"]
    by_id = {row["episode_id"]: row for row in projected["events"]}
    for row in shared["events"]:
        actual = by_id.get(row["episode_id"])
        if actual is None:
            raise RuntimeError(f"Shared fixture episode absent from actual capture: {row['episode_id']}")
        for key in ("normalized_class", "auction_date", "issue_date", "offering_amount_usd", "competitive_deadline_utc"):
            if actual[key] != row[key]:
                raise RuntimeError(f"Current capture differs from shared fixture in {key}; adjudicate before UI proof")

    # Explicit synthetic negative states, separate from the actual capture case.
    failure = copy.deepcopy(observed)
    failure["status"] = "degraded"
    source = next((s for s in failure["source_health"] if s["source_kind"] == "quarterly_tentative_xml"), failure["source_health"][0])
    source.update({"latest_attempt_at": cutoff_text, "latest_attempt_status": "unavailable",
                   "latest_attempt_states": ["unavailable"], "latest_failure_at": cutoff_text,
                   "latest_failure_reasons": ["UI_HARNESS_SYNTHETIC_TIMEOUT"]})
    failure["source_states"].append({"source_kind": source["source_kind"], "source_url": source["source_url"],
                                    "observed_at": cutoff_text, "status": "unavailable",
                                    "receipt_status": "unavailable", "reason": "UI_HARNESS_SYNTHETIC_TIMEOUT"})

    unknown = copy.deepcopy(observed)
    row = copy.deepcopy(next(r for r in observed["events"] if r["physical_state"] == "ANNOUNCED"))
    yesterday = cutoff.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)
    row.update({"episode_id": "ui-harness:awaiting-result", "label": "UI HARNESS — awaiting-result control",
                "date": yesterday.isoformat(), "auction_date": yesterday.isoformat(),
                "announcement_date": (yesterday - timedelta(days=2)).isoformat(),
                "source_state": "ANNOUNCED", "physical_state": "AWAITING_RESULT",
                "competitive_deadline_utc": None, "competitive_deadline_raw": None, "time_et": None,
                "offering_amount_usd": None, "result": None, "result_evidence_fields": [],
                "observation_versions": [],
                "null_reasons": ["UI_HARNESS_SYNTHETIC_MISSING_DEADLINE", "UI_HARNESS_SYNTHETIC_UNKNOWN_OFFERING"]})
    unknown["events"] = [row]
    unknown["episodes"] = [copy.deepcopy(row)]
    unknown["coverage"].update({"known_upcoming_count": 0, "recently_resulted_or_issue_future_count": 0,
                                 "unresolved_tentative_count": 0, "awaiting_result_count": 1})
    cases = {
        "observed": {"wrapper": {"sovereign_auction_context": observed}, "provenance": "Actual four-source captured observations, processed by the exact local W1 producer."},
        "unavailable": {"wrapper": {}, "provenance": "Synthetic missing-publication control: no nested auction context."},
        "source_failure": {"wrapper": {"sovereign_auction_context": failure}, "provenance": "Synthetic later failure layered onto real observations; clocks and rows retain their valid evidence."},
        "awaiting_unknown": {"wrapper": {"sovereign_auction_context": unknown}, "provenance": "Synthetic missing-result/deadline/amount control, clearly labeled UI HARNESS."},
    }
    for name, case in cases.items():
        context = case["wrapper"].get("sovereign_auction_context")
        case["projected"] = reader.validate_context(context, now=cutoff_text) if context else reader.unavailable("sovereign_auction_context_not_published")
    base = frozen_view_from_native_test(native_fixture_path)
    manifest = {
        "schema_version": "mastermind_auction_ui_harness_v1",
        "status": "PREPARED_ONLY",
        "fixed_reader_clock": cutoff_text,
        "harness": "Fresh read-only FastAPI routes; actual page/theme/API endpoint functions; temporary fixture files; no production app, lifespan, authentication or publication claim.",
        "source_files": [{"path": str(p), "sha256": sha(p)} for p in (producer_path, consumer_path, root / "app/web.py", root / "app/static/market_view.html", native_fixture_path, fixture)],
        "input_receipts": [{"path": str(p), "sha256": sha(p)} for p in observations],
        "base_view_sha256": hashlib.sha256(json.dumps(base, indent=2).encode()).hexdigest(),
        "cases": {},
    }
    for name, case in cases.items():
        context = case["projected"]
        manifest["cases"][name] = {
            "provenance": case["provenance"], "available": context["available"],
            "note": context.get("note"), "status": context.get("status"),
            "source_observed_at": context.get("source_observed_at"), "decision_cutoff_utc": context.get("decision_cutoff_utc"),
            "group_counts": dict(Counter(row["physical_state"] for row in context.get("events", []))),
            "scheduled_rows": [{key: row[key] for key in ("episode_id", "label", "offering_amount_usd", "competitive_deadline_utc", "known_at")}
                               for row in context.get("events", []) if row["physical_state"] == "ANNOUNCED"],
            "wrapper_sha256": hashlib.sha256(json.dumps(case["wrapper"], sort_keys=True).encode()).hexdigest(),
        }
    return root, cutoff_text, base, cases, manifest


def deny_nonloopback_network():
    """Prevent incidental Python network connections outside loopback."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def allowed(address):
        if not isinstance(address, tuple):
            return False
        host = address[0]
        try:
            return ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            return host == "localhost"

    def connect(sock, address):
        if not allowed(address):
            raise OSError("UI harness rejects non-loopback network connection")
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if not allowed(address):
            raise OSError("UI harness rejects non-loopback network connection")
        return original_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None and not allowed((host, 0)):
            raise OSError("UI harness rejects non-loopback DNS resolution")
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo


def serve(args, prepared):
    root, cutoff, base, cases, manifest = prepared
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse, Response
    from app import web
    from brain import sovereign_auction_context as reader
    import uvicorn

    theme = root / "app/static/theme.css"
    if not theme.is_file():
        raise RuntimeError("The real repository theme.css is required; no substitute theme is supplied")
    manifest["source_files"].append({"path": str(theme), "sha256": sha(theme)})
    original_reader = reader.read_context
    reader.read_context = lambda path=None, **kwargs: original_reader(path, now=cutoff)
    original_root = web._PROJECT_ROOT
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    wanted = {"/market_view", "/theme.css", "/api/market_view"}
    selected = [route for route in web.router.routes if getattr(route, "path", None) in wanted]
    if len(selected) != len(wanted) or any(getattr(route, "methods", set()) != {"GET"} for route in selected):
        raise RuntimeError("Expected exactly three existing read-only GET routes")
    application.router.routes.extend(selected)
    gate = asyncio.Lock()

    with tempfile.TemporaryDirectory(prefix="mastermind-auction-ui-") as temporary:
        scenario_roots = {}
        base_bytes = json.dumps(base, indent=2).encode()
        for name, case in cases.items():
            folder = Path(temporary) / name
            stored = folder / "data/market_view/latest.json"
            feed = folder / "vendor/macro/site/feeds/event_calendar.json"
            stored.parent.mkdir(parents=True); feed.parent.mkdir(parents=True)
            stored.write_bytes(base_bytes)
            feed.write_text(json.dumps(case["wrapper"]))
            scenario_roots[name] = folder
            web._PROJECT_ROOT = folder
            response = web.api_market_view()
            if response.status_code != 200:
                raise RuntimeError(f"Actual API preflight failed for {name}: HTTP {response.status_code}")
            body = json.loads(response.body)
            sibling = body.pop("sovereign_auction_context", None)
            if body != base or sibling != case["projected"] or stored.read_bytes() != base_bytes:
                raise RuntimeError(f"Actual API projection or stored-byte invariance failed for {name}")
            manifest["cases"][name]["actual_api_response_sha256"] = hashlib.sha256(response.body).hexdigest()
        web._PROJECT_ROOT = original_root

        @application.middleware("http")
        async def fixture_binding(request, call_next):
            if request.url.path != "/api/market_view":
                return await call_next(request)
            case = request.headers.get("X-Sovereign-UI-Case", "observed")
            if case not in scenario_roots:
                return JSONResponse({"error": "unknown_harness_case"}, status_code=400)
            async with gate:
                web._PROJECT_ROOT = scenario_roots[case]
                try:
                    return await call_next(request)
                finally:
                    web._PROJECT_ROOT = original_root

        @application.get("/__harness__/manifest")
        def harness_manifest():
            return manifest

        @application.get("/{asset_path:path}")
        def contained_static_asset(asset_path: str):
            if asset_path == "favicon.ico":
                return Response(status_code=204)
            static_root = (root / "app/static").resolve()
            path = (static_root / asset_path).resolve()
            if not path.is_relative_to(static_root) or not path.is_file() or path.suffix.lower() not in {".css", ".js", ".woff2", ".woff", ".ttf", ".otf", ".svg", ".png", ".ico", ".webp"}:
                raise HTTPException(status_code=404)
            return FileResponse(path)

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        manifest.update({"status": "ACTUAL_HANDLER_PREFLIGHT_PASSED", "origin": f"http://127.0.0.1:{port}",
                         "served_routes": sorted(wanted), "app_lifespan": "off", "external_python_connections": "denied"})
        (out / "harness_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print("HARNESS_READY " + json.dumps({"origin": manifest["origin"], "manifest": str(out / "harness_manifest.json")}), flush=True)
        try:
            config = uvicorn.Config(application, host="127.0.0.1", port=port, lifespan="off", access_log=False, log_level="warning")
            uvicorn.Server(config).run(sockets=[listener])
        finally:
            web._PROJECT_ROOT = original_root
            reader.read_context = original_reader
            listener.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mastermind-root", required=True)
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--capture-data-root", required=True)
    parser.add_argument("--fixture-feed")
    parser.add_argument("--cutoff", default="2026-10-08T23:00:00Z")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--prepare-only", action="store_true", help="Validate only source fixtures; does not start HTTP or constitute browser proof")
    args = parser.parse_args()
    out = Path(args.out_dir).resolve()
    if any(out.is_relative_to(Path(source).resolve()) for source in (args.mastermind_root, args.macro_root)):
        raise RuntimeError("Harness output must be outside source repositories")
    deny_nonloopback_network()
    prepared = prepare(args)
    if args.prepare_only:
        out = Path(args.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
        (out / "prepared_fixture_manifest.json").write_text(json.dumps(prepared[-1], indent=2) + "\n")
        print(json.dumps({"status": "PREPARED_ONLY", "cases": {k: v["group_counts"] for k, v in prepared[-1]["cases"].items()}}, indent=2))
    else:
        serve(args, prepared)


if __name__ == "__main__":
    main()
