# Mastermind auction display — actual browser verification harness

This is a separate verification artifact. It does not change the frozen consumer,
the existing HTML/CSS, a canonical repository, a production app, provider jobs or
publication settings. Run it in the already available Mac Playwright/Chromium
environment after applying the accepted consumer source.

## Files to copy together

- `mastermind_loopback_harness.py`
- `verify_mastermind_ui.cjs`
- `README_mastermind_ui.md`

The source-preparation receipt under `prepared_only/` records only the local
fixture check. It is optional evidence, not a browser result. Do not copy Python
cache directories. No extra UI, CSS, package, browser installation, secret or
external network service is supplied by this harness.

## What runs

The Python child reads the real captured Treasury observations through the exact
local W1 producer and validates them using the exact Mastermind consumer. It
cross-checks the three genuine upcoming Bills against the shared fixture's
episode IDs, classes, amounts, dates and competitive deadlines. At the fixed
2026-10-08T23:00:00Z cutoff, the supplied capture gives 43 observed results,
three announced auctions and 28 tentative observations.

A fresh FastAPI instance registers only the **existing** `/market_view`,
`/theme.css` and `/api/market_view` GET routes. It never imports `app.main` and
Uvicorn lifespan is off. Additional local assets can be read only from contained
paths in the existing static tree. The actual API handler reads temporary
fixture directories through the actual local reader with an explicitly injected
clock. Its original background Market View is the literal `frozen_view()` fixture
from the native API test. Every scenario is preflighted through the actual
handler, checking original stored bytes, unchanged non-auction fields, and exact
validated sibling output before the server starts.

This tests a real browser and a real HTTP route in a **declared fixture harness**.
It does not test production authentication, middleware/lifespan, deployment,
publication transport, live availability, predictive validity or real portfolio
state. The three failure/unknown cases are explicit synthetic controls; their
receipts and labels identify that fact.

The server binds only an ephemeral `127.0.0.1` port. Python connections and DNS
outside loopback are rejected. Browser page requests outside that exact local
origin are aborted; Chromium background networking is disabled. If the real
theme attempts an external font/resource, the request is recorded as blocked and
the result requires review rather than silently claiming equivalent fonts. No
official source link is clicked. The runner terminates only its own Python child
and browser when it finishes.

## Run in the existing Mac environments

Use the same Python interpreter that passed root's native Mastermind API tests.
It also needs the repository's existing `uvicorn` dependency. Use the Terminal
workspace's already installed `@playwright/test` and Chromium. No dependency
installation is part of this script.

The three source paths below are the current operation workspaces. The helper
files themselves can be copied to a separate `/tmp/sovereign-auction-ui-tools/`
directory. Choose a new output directory for every execution so earlier evidence
is preserved.

```sh
AUCTION_MM_SOURCE='/Volumes/Mastermind/agent-workspaces/web/sovereign-auction-context-20261008-sol-mm-001'
AUCTION_MACRO_SOURCE='/Volumes/Mastermind/agent-workspaces/macro/web/sovereign-auction-pressure-20261008-sol-001'
AUCTION_TERMINAL_SOURCE='/Volumes/Mastermind/agent-workspaces/terminal/web/sovereign-auction-context-20261008-sol-terminal-001'
AUCTION_MM_PYTHON='/absolute/path/to/the/native-test-python'

node /tmp/sovereign-auction-ui-tools/verify_mastermind_ui.cjs \
  --python "$AUCTION_MM_PYTHON" \
  --mastermind-root "$AUCTION_MM_SOURCE" \
  --macro-root "$AUCTION_MACRO_SOURCE" \
  --capture-data-root "$AUCTION_MACRO_SOURCE/research/sovereign_auction_pressure/source_audit/forward_capture_primary" \
  --playwright-root "$AUCTION_TERMINAL_SOURCE/terminal/node_modules" \
  --out-dir /tmp/sovereign-auction-mastermind-ui-proof-01
```

Optional arguments are `--fixture-feed /absolute/path/to/event_calendar.json`,
`--cutoff 2026-10-08T23:00:00Z`, and `--chromium-executable /absolute/path/to/chromium`.
The default fixture is the accepted consumer's shared fixture. Do not advance the
cutoff or replace the real observations just to make a failing visual check pass.
Every output directory must be outside both source repositories. Python bytecode
writes are disabled to keep imports from modifying the source tree.

## Matrix and assertions

The runner executes 48 bounded cases: `1440×900`, `820×1180` and `390×844`, each
in EN/ZH and light/dark, for each of the following states:

| Case | Evidence |
|---|---|
| `observed` | Real four-source capture, 74 observed episodes |
| `unavailable` | Explicit synthetic missing nested publication |
| `source_failure` | Synthetic later transport failure with original valid rows/clocks retained |
| `awaiting_unknown` | Synthetic elapsed auction with unknown deadline, unknown amount and no observed result |

Assertions use the actual HTTP response and rendered DOM. They check exact
preflight response hashes, no-cache headers, unchanged fields, EN/ZH copy and
theme selection, scheduled/awaiting/tentative priority over past results, counts,
the three visible future auctions, exact decimal amounts and microsecond clock
text, unavailable and degraded states, and explicit unknowns.

Geometry checks require no **document-level** horizontal overflow and no visible
auction content outside its panel or clipped by hidden/clip overflow. The
existing planes table's contained horizontal scroll is an intentional existing
control and is not itself a failure. The observed case opens each native group
expander, checks geometry again, and captures the expanded content. If expanded
cards shrink below 75% of their own group's initially visible card width, the
receipt marks `review_required`: inspect that screenshot for a genuine layout
issue before accepting it. This does not modify the source or suppress the issue.

Screenshots are viewport images of the original page, auction section, failure
evidence and opened expanders. The script does not inject replacement styles or
hide original page sections. It retains screenshots even when a check fails.
Human inspection of representative desktop/tablet/mobile EN/ZH light/dark images
is still needed; a DOM geometry pass alone is not visual acceptance.

## Receipts and exit codes

- `harness_manifest.json`: exact source and captured-input hashes, scenario
  provenance, expected groups, actual-handler response hashes, reader clock and
  safe route scope.
- `browser_receipt.json`: browser version, each matrix result, errors/warnings,
  geometry, external-resource blocks and screenshot hashes. Written after each
  case so a partial run remains explicit.
- `harness_process.log`: the isolated Python child's actual output.
- `screenshots/*.png`: inspectable viewport evidence.

Exit `0` means all scripted checks passed without review warnings. Exit `2`
means review is required. Exit `1` means failed or blocked; it is not a pass.
The final receipt distinguishes completed, failed, review-required and blocked
execution. The runner starts no watcher and does not continue after it exits.

## Local checks completed when authored

`python3 -m py_compile mastermind_loopback_harness.py` and
`node --check verify_mastermind_ui.cjs` passed. The exact `--prepare-only` path
also passed against the frozen consumer, final W1 module and original actual
capture. It produced the expected 74-row real case and all three separately
labeled controls through the real validator. **No HTTP server or browser was run
in scratch**, which lacks the full Mastermind/FastAPI/static asset environment.
Canonical source, native dependencies and actual browser results remain for the
root-owned Mac execution.
