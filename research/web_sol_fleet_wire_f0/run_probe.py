"""Pinned, offline research: real census producer -> real native frame codec.

Run from a checkout containing both pinned Git objects. Redirect stdout to a
NEW evidence file; shell redirection truncates an older file before execution.
No browser, socket, provider, account, installed host, or runtime is accessed.
The compact table is an experiment, NOT an admitted production wire protocol.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = "4fe4d6bc93d9543f77320f68342a10c5af4d4f49"
CENSUS = "a6dc03dc8ac241af7690101626a465c44e352c7a"
CORE = "integrations/chairman_surfaces/web_sol_extension/census_core.js"
ROW_FIELDS = (
    "slot", "conversation_fingerprint", "identity_evidence", "document_binding",
    "status", "generation_cue", "selected_in_window", "discarded", "frozen",
    "visibility", "auth_required", "provider_error_present", "duplicate_count",
    "duplicate_cue_disagreement", "observed_at", "selected_model",
    "selected_effort", "served_model", "model_evidence",
)
PINNED_MODULES = (
    "integrations/chairman_surfaces/_web_sol_native_host_impl.py",
    "integrations/chairman_surfaces/web_sol_native_host.py",
    "integrations/chairman_surfaces/web_sol_protocol.py",
    "integrations/chairman_surfaces/web_sol_instance.py",
    "integrations/chairman_surfaces/web_sol_client.py",
    "control_plane/surface_bindings.py",
)


def git_bytes(ref: str, path: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
                          capture_output=True, check=True, timeout=15).stdout


def git_blob(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def compact(snapshot: dict) -> dict:
    rows = snapshot["rows"]
    if any(set(row) != set(ROW_FIELDS) for row in rows):
        raise ValueError("row_field_mismatch")
    return {"schema": "mastermind.web_sol_compact_experiment.v0",
            "columns": list(ROW_FIELDS),
            "snapshot": {k: v for k, v in snapshot.items() if k != "rows"},
            "rows": [[row[key] for key in ROW_FIELDS] for row in rows]}


def expand(table: dict) -> dict:
    if (set(table) != {"schema", "columns", "snapshot", "rows"}
            or table["schema"] != "mastermind.web_sol_compact_experiment.v0"
            or table["columns"] != list(ROW_FIELDS)
            or len(table["rows"]) > 128
            or "rows" in table["snapshot"]
            or any(len(row) != len(ROW_FIELDS) for row in table["rows"])):
        raise ValueError("compact_shape_invalid")
    return {**table["snapshot"], "rows": [
        dict(zip(ROW_FIELDS, row, strict=True)) for row in table["rows"]]}


def main() -> dict:
    import inspect
    identities = {}
    for path in PINNED_MODULES:
        payload = git_bytes(BASE, path)
        if (ROOT / path).read_bytes() != payload:
            raise ValueError("protected_module_bytes_changed")
        identities[path] = {"git_blob": git_blob(payload),
                            "sha256": hashlib.sha256(payload).hexdigest()}
    core = git_bytes(CENSUS, CORE)
    expected_blob = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", f"{CENSUS}:{CORE}"],
        capture_output=True, check=True, timeout=15).stdout.decode().strip()
    if git_blob(core) != expected_blob:
        raise ValueError("census_source_identity_mismatch")
    sys.path.insert(0, str(ROOT))
    from integrations.chairman_surfaces import _web_sol_native_host_impl as native
    from integrations.chairman_surfaces import web_sol_protocol as protocol
    from integrations.chairman_surfaces import web_sol_client as client
    with tempfile.TemporaryDirectory(prefix="wsx-f0-") as temporary:
        core_path = Path(temporary) / "census_core.cjs"
        core_path.write_bytes(core)
        completed = subprocess.run(["node", str(HERE / "probe.cjs"), str(core_path)],
                                   capture_output=True, check=True, timeout=30)
    if len(completed.stdout) > 1024 * 1024:
        raise ValueError("fixture_output_limit")
    fixtures = json.loads(completed.stdout)
    results = []
    for fixture in fixtures["cases"]:
        snapshot = fixture["snapshot"]
        table = compact(snapshot)
        assert expand(table) == snapshot
        payload_size = len(json.dumps(snapshot, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8"))
        raw_status = "ACCEPTED"
        try:
            framed = native.encode_frame(snapshot)
            assert native.read_frame(io.BytesIO(framed)) == snapshot
        except native.NativeHostError as error:
            raw_status = error.code
        encoded = native.encode_frame(table)
        decoded = native.read_frame(io.BytesIO(encoded))
        assert expand(decoded) == snapshot
        assert len(encoded) - 4 < 60 * 1024
        results.append({"fixture_tab_count": fixture["fixture_tab_count"],
            "mode": fixture["mode"], "probe_calls": fixture["probe_calls"],
            "retained_rows": len(snapshot["rows"]),
            "omitted_tab_count": snapshot["omitted_tab_count"],
            "inventory_coverage": snapshot["inventory_coverage"],
            "probe_coverage": snapshot["probe_coverage"],
            "raw_json_bytes": payload_size, "raw_native_status": raw_status,
            "compact_frame_payload_bytes": len(encoded) - 4,
            "compact_round_trip_exact": True})
    request = {"schema": protocol.ACTION_SCHEMA,
        "binding_id": "00000000-0000-4000-8000-000000000001",
        "conversation_fingerprint": "a" * 64, "binding_fingerprint": "b" * 64,
        "action": "INSPECT", "operation_key": "web-sol-wire-f0-fixture",
        "issued_at": "2026-09-06T00:00:00Z", "expires_at": "2026-09-06T00:00:30Z",
        "nonce": "fixture-nonce-000000000001"}
    protocol.validate_request(request)
    rejected = False
    try:
        protocol.validate_request({**request, "action": "CENSUS"})
    except protocol.WebSolProtocolError:
        rejected = True
    assert rejected, "legacy_schema_must_not_admit_census"
    negative_controls = 0
    for broken in [{**table, "columns": list(reversed(ROW_FIELDS))},
                   {**table, "rows": [table["rows"][0][:-1]]},
                   {**table, "unexpected": True}]:
        try:
            expand(broken)
        except ValueError:
            negative_controls += 1
        else:
            raise AssertionError("malformed_experiment_not_rejected")
    empty_padding_bytes = len(json.dumps({"pad": ""}, separators=(",", ":")).encode())
    boundary = {"pad": "x" * (native.MAX_MESSAGE_BYTES - empty_padding_bytes)}
    assert native.read_frame(io.BytesIO(native.encode_frame(boundary))) == boundary
    over_limit_refused = False
    try:
        native.encode_frame({"pad": boundary["pad"] + "x"})
    except native.NativeHostError as failure:
        over_limit_refused = failure.code == "frame_too_large"
    assert over_limit_refused
    maximum = next(row for row in results if row["fixture_tab_count"] == 128
                   and row["mode"] == "ordinary")
    assert maximum["raw_native_status"] != "ACCEPTED"
    sweep_ms = int(re.search(rb"const SWEEP_MS = ([0-9]+);", core).group(1))
    host_seconds = inspect.signature(native.run_native_host).parameters[
        "action_timeout_seconds"].default
    return {"schema": "mastermind.web_sol_fleet_wire_research.v1", "completed": True,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "native_source_commit": BASE, "census_source_commit": CENSUS,
        "census_git_blob": expected_blob,
        "census_sha256": hashlib.sha256(core).hexdigest(),
        "pinned_modules": identities, "python_version": platform.python_version(),
        "node_version": subprocess.run(["node", "--version"], capture_output=True,
            check=True, text=True, timeout=10).stdout.strip(),
        "native_payload_limit_bytes": native.MAX_MESSAGE_BYTES,
        "collector_max_tabs": fixtures["max_tabs"], "cases": results,
        "malformed_experiment_controls": negative_controls,
        "native_exact_limit_round_trip": True, "native_over_limit_refused": over_limit_refused,
        "legacy_inspect_request_valid": True, "legacy_census_request_refused": rejected,
        "static_deadline_comparison": {"collector_sweep_ms": sweep_ms,
            "client_total_seconds": client.SOCKET_TIMEOUT_SECONDS,
            "native_default_total_seconds": host_seconds,
            "measured_latency_claim": False},
        "proof_ceiling": "OFFLINE_SYNTHETIC_COLLECTOR_AND_FRAME_CODEC_ONLY",
        "census_native_action_implemented": False, "browser_used": False,
        "provider_used": False, "installation_performed": False}


if __name__ == "__main__":
    try:
        document = main()
    except Exception as failure:
        print(json.dumps({"completed": False,
            "failure_class": type(failure).__name__,
            "proof_ceiling": "NO_SUCCESSFUL_CURRENT_RESEARCH_RECEIPT"}))
        raise SystemExit(1) from None
    print(json.dumps(document, indent=2, sort_keys=True, allow_nan=False))
