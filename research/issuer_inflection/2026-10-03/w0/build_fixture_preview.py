#!/usr/bin/env python3
"""Render verified retained I3 evidence as a network-free development preview.

Not a Terminal/Macro route, publisher, entitlement system, new financial owner,
model context builder or trial writer. All four inputs must pass the existing
verified reader before any HTML is returned. No financial calculation occurs.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
from verified_baseline_reader import CASES, CAPTURE_COMMIT, ReaderRefusal, load_verified

ROOT = Path(__file__).resolve().parent
MAX_HTML_BYTES = 250_000

def _script_json(value: object) -> str:
    # Inert JSON must not terminate its script element or create HTML markup.
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    for before, after in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(before, after)
    return text

def build_preview(*, evidence_dir: Path | None = None) -> bytes:
    """Return a complete HTML view only after verification of every fixed case."""
    cases = {case: load_verified(case, evidence_dir) for case in CASES}
    css = (ROOT / 'fixture_preview.css').read_text(encoding='utf-8')
    js = (ROOT / 'fixture_preview.js').read_text(encoding='utf-8')
    if '</style' in css.lower() or '</script' in js.lower():
        raise ReaderRefusal('invalid_trusted_preview_asset')
    def csp_hash(value: str) -> str:
        return base64.b64encode(hashlib.sha256(value.encode('utf-8')).digest()).decode('ascii')
    policy = "default-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'; connect-src 'none'; img-src 'none'; font-src 'none'; style-src 'sha256-"+csp_hash(css)+"'; script-src 'sha256-"+csp_hash(js)+"'"
    dataset = _script_json({'purpose':'offline_development_fixture_preview','capture_commit':CAPTURE_COMMIT,'cases':cases})
    html = '''<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="'''+policy+'''">
<title>AAPL · Evidence changes · I3 development preview</title>
<style>'''+css+'''</style></head><body>
<a class="skip" href="#main">Skip to evidence changes</a>
<header class="topbar"><div class="brand">MASTERMIND<span>ISSUER INTELLIGENCE</span></div>
<div class="toolbar"><span class="pill">Offline fixture</span><button id="theme" type="button" aria-label="Switch to light theme">Light theme</button></div></header>
<div class="scope-banner" role="note"><strong>Development preview</strong> · Historical evidence replay. Not a live issuer service, economic signal, or trading recommendation.</div>
<main id="main" tabindex="-1"><section class="heading"><div><div class="eyebrow">WHAT CHANGED</div><h1>AAPL <span>Evidence changes</span></h1><p class="subtitle">See what the available evidence supports—and what it no longer supports.</p></div>
<label class="scenario-label" for="scenario">Replay scenario<select id="scenario">
<option value="later_admission_refusal">Later filing becomes available</option>
<option value="first_admission">First system admission</option>
<option value="source_cutoff_refusal">Public-source cutoff changes</option>
<option value="identical_cutoff">Same cutoff replayed</option>
</select></label></section>
<section class="summary" aria-labelledby="summary-title"><div class="signal-mark" aria-hidden="true">↔</div><div><div class="eyebrow" id="summary-kicker">EVIDENCE STATE</div><h2 id="summary-title"></h2><p id="summary-copy"></p></div><div class="coverage"><strong id="coverage"></strong><span>requested slots retained</span></div></section>
<section class="clock-grid" aria-label="Comparison cutoffs"><div><h3>Public-source cutoff</h3><div class="clock-pair"><span id="source-before"></span><span class="arrow" aria-hidden="true">→</span><span id="source-after"></span></div></div><div><h3>System-admission cutoff</h3><div class="clock-pair"><span id="system-before"></span><span class="arrow" aria-hidden="true">→</span><span id="system-after"></span></div></div></section>
<section aria-labelledby="variables-title"><div class="section-heading"><h2 id="variables-title">Complete baseline &amp; target</h2><span id="denominator"></span></div><div id="variables"></div></section>
<section class="interpretation" aria-label="Interpretation boundary"><strong>Evidence change ≠ business change</strong><p>Newly available information is not economic improvement. A comparison refusal is not deterioration. Missing values and unchanged variables stay visible; no economic interpretation is emitted.</p></section>
<footer class="identity"><div><span class="eyebrow">SAME IDENTITY FOR HUMAN &amp; MACHINE READS</span><code id="artifact-id"></code></div><button type="button" id="machine">Inspect machine record</button></footer>
<p class="limits">One issuer · four requested slots · committed golden inputs · no live publication, trial registration, model exposure, alerts, or decision authority.</p>
<div id="announcement" class="sr-only" role="status" aria-live="polite"></div></main>
<dialog id="evidence-dialog" aria-labelledby="dialog-title"><div class="dialog-heading"><div><div class="eyebrow">VERIFIED RETAINED EVIDENCE</div><h2 id="dialog-title"></h2></div><button type="button" id="close-dialog" aria-label="Close evidence">Close</button></div><p id="dialog-note"></p><pre id="evidence-record" tabindex="0" aria-label="Exact evidence record"></pre></dialog>
<noscript>This preview requires JavaScript to display the verified embedded records. No external service is contacted.</noscript>
<script type="application/json" id="fixture-data">'''+dataset+'''</script><script>'''+js+'''</script></body></html>
'''
    result = html.encode('utf-8')
    if len(result) > MAX_HTML_BYTES:
        raise ReaderRefusal('preview_payload_bound')
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path)
    args = parser.parse_args()
    try:
        result = build_preview(evidence_dir=args.evidence_dir)
    except (ReaderRefusal, OSError, ValueError):
        print('PREVIEW_REFUSED: verified fixture unavailable', file=sys.stderr)
        return 2
    sys.stdout.buffer.write(result)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
