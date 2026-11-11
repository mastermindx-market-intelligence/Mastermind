"""Hermetic CI coverage for the incumbent Studio fleet preflight diagnostics.

This test runs through Mastermind's existing discovery-first pytest gate. It
uses the real source function bytes, a local Node interpreter and no MCP
network, authentication, fleet host, provider or installed Studio service.
The full SDK-backed gateway tests remain separate acceptance evidence.
"""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "integrations" / "studio_direct_mcp"


def _node(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


def test_diagnostic_source_and_integration_regression_are_valid_javascript():
    for name in (
        "fleet-routing.mjs",
        "fleet-routing.test.mjs",
        "gateway.mjs",
        "gateway.test.mjs",
        "gateway-git-publish.test.mjs",
    ):
        _node("--check", str(STUDIO / name))


def test_real_fleet_reason_classifier_is_closed_and_redacts_unknown_errors():
    source = (STUDIO / "fleet-routing.mjs").read_text(encoding="utf-8")
    start = source.index("const PUBLIC_PREFLIGHT_REASONS = new Set([")
    end = source.index("]);", start) + len("]);")
    name = "export function fleetPreflightReason(error) {"
    fn_start = source.index(name)
    fn_end = source.index("\n}", fn_start) + len("\n}")
    real_code = source[start:end] + "\n" + source[fn_start:fn_end].replace("export ", "", 1)

    assertions = """
const assert = require('node:assert/strict');
assert.equal(fleetPreflightReason(new Error('FLEET_ROUTE_HOST_NOT_CONFIGURED')),
             'FLEET_ROUTE_HOST_NOT_CONFIGURED');
const wrapped = new Error('FLEET_ROUTE_PREFLIGHT_REFUSED');
wrapped.cause = new Error('FLEET_ROUTE_CONTRACT_MISMATCH');
assert.equal(fleetPreflightReason(wrapped), 'FLEET_ROUTE_CONTRACT_MISMATCH');
const privateError = new Error('FLEET_ROUTE_PREFLIGHT_REFUSED');
privateError.cause = new Error('https://private.ts.net/mcp Bearer SECRET');
assert.equal(fleetPreflightReason(privateError),
             'FLEET_ROUTE_TRANSPORT_OR_BACKEND_UNAVAILABLE');
assert.equal(fleetPreflightReason(new Error('Authorization: Bearer SECRET')),
             'FLEET_ROUTE_TRANSPORT_OR_BACKEND_UNAVAILABLE');
assert.equal(fleetPreflightReason(null),
             'FLEET_ROUTE_TRANSPORT_OR_BACKEND_UNAVAILABLE');
"""
    _node("--input-type=commonjs", "-e", real_code + assertions)

    gateway = (STUDIO / "gateway.mjs").read_text(encoding="utf-8")
    assert "reason_code: fleetPreflightReason(error)" in gateway
    assert "code: 'FLEET_ROUTE_PREFLIGHT_REFUSED'" in gateway
    assert "effect_state: 'NOT_APPLIED'" in gateway
