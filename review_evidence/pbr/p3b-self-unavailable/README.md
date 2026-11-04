# PBR L-P3b: an unreadable Self-Directed book renders `unavailable`, never a funded $1,000,000 book

Truth violation (accepted by the seat for a wave-1 fix under PRODUCT authority): when the
self-directed account or its fill log could not be read, `/api/self_directed` returned a
fabricated fresh book (`nav == cash == starting_nav == 1,000,000`, no positions) and
`/api/self_directed/history` returned an empty blotter. The page then showed a fully funded,
100 %-cash book. The static hero seed was also a hard-coded `$1,000,000` before any load settled.
MASTERMIND masterplan §10.2: "A natural-language explanation cannot overrule the actual account";
an unknown value is not zero and not a default.

## What changed

- `app/web.py`: the two `except` branches now return `status: "unavailable"` with a
  `reason_code` (`self_directed_book_unreadable` / `self_directed_history_unreadable`). Every
  numeric field is `null`, the lists are empty, `allocation` is `null`, and `market` is kept when
  the market clock still answers (`null` when it fails too). The success path is unchanged. The
  `error` string is the pre-existing field; this change does not add new exposure.
- `app/static/index.html`, pure helpers `_selfBookState` / `_selfHistState` between the
  `PBR-SELF-UNAVAILABLE` markers, each returning `pending | unavailable | ok`:
  - The hero seed is a neutral `—`.
  - An unavailable book shows `unavailable` / `不可用` in the hero and all four tiles, plus a
    reason line. The allocation, positions and history hosts show unavailable empty states, not
    the "empty book" copy.
  - Buying power reads `unavailable`, and Buy/Sell are disabled while the book is unknown.
  - A missing market session reads "Market status unavailable" rather than "Closed".
  - Before any fetch settles, the shipped placeholders stay untouched (pending is not unavailable).
- Orchestrator repairs after browser inspection (reviewed as part of this change):
  - The hero `unavailable` word carries `data-availability="unavailable"` and is muted with the
    existing `var(--muted)` token. It no longer takes the numeral's full `--text` emphasis.
  - The hero's pulsing `--up` heartbeat (`#sd-hb`) is a health cue. It turns static and muted
    while the book is unreadable. A readable book clears both attributes.
  - No new colour, no new component.

## Tests (named suites; node present, so the vm render tests ran)

`tests/test_pbr_self_unavailable.py` (new, 18 tests) with `tests/test_portfolio_dashboard_ui.py`,
`tests/test_china_book.py` and `tests/test_self_directed.py`: **136 passed**.

The agreement tests feed the real `web.api_self_directed()` / `api_self_directed_history()`
JSON, with the book reader patched to raise, into the shipped renderers in a Node `vm`. The
rendered hero, tiles, hosts and attributes are asserted against it. Mutation checks, each failing
exactly 1 test:
- no `setAttribute` on the hero;
- no `removeAttribute` on the hero;
- the `1000000` fallback restored;
- no heartbeat set;
- no heartbeat clear.

## Local browser proof (synthetic fixture, never live data)

Proof ran on 127.0.0.1 against a **synthetic** self-directed fixture (invented tickers and round
numbers). An off-repo proof server patches the book paths and price feeds. Fault mode makes the
book and history readers raise, which exercises the real API `except` branches. The portfolio
switcher on those pages also shows other books' values, so screenshots, DOM dumps and API bodies
stay out of this public repository. They are in
`/Volumes/Mastermind/evidence/pbr/product-proof-p3b-self-unavailable-20261022T090419Z/`
(`SHA256SUMS` sha256 `32efc1ee13b5f680c4644ae8c3f3dd4b13adae64d3a84363153c454b0ad3d285`, 23 files,
including the fixture, the proof server and the candidate diff).

| state | 1280 (headless Chrome + browser pane) | 375 (browser pane viewport emulation) |
|---|---|---|
| unreadable | hero and four tiles `unavailable` (muted), reason line, static muted heartbeat, three unavailable empty states, Buy/Sell disabled, switcher pill `— · —`; scrollWidth 1280 = client | same, plus ZH `不可用` with the reason line; `document.scrollWidth == 375`; only the existing horizontal portfolio switcher scrolls |
| readable | the API NAV, cash and invested exactly; heartbeat pulses `--up`; no `data-availability` | same; scrollWidth 375 |

Headless Chrome's `--window-size=375` lays the page out wider than 375 px, so the 375 rows above
come from the browser pane (`pane/measurements.json`).

## Dependency (not fixed here)

ECON **E13**: `portfolio/self_directed.py` `_load_account()` still returns a fresh $1,000,000 book
on *any* exception or malformed file, so that path never reaches the API `except` branch fixed
here. The owner must distinguish "no account file yet" from "file present but unreadable".
**E12** (a NAV that includes cost-valued holdings) is also open.

## Production proof checklist (for the seat)

1. Confirm the deployed `app/static/index.html` and `app/web.py` blobs equal this PR's merge blobs
   (blob comparison, not `deploy_lag.json`).
2. On production `/self` with a readable book, the hero, tiles, allocation, positions and history
   match `/api/self_directed` and `/api/self_directed/history` exactly. There is no
   `data-availability` on `#sd-nav` or `#sd-hb`, and the heartbeat pulses.
3. Before the first fetch settles (throttled network) the hero shows `—`, never `$1,000,000`.
4. The unavailable state cannot be forced in production without touching live data: do **not**
   corrupt or move the account file. Its proof is the local fault-injection run above plus the
   agreement tests.
5. ZH toggle: a readable book is unchanged, and the reason-line keys exist in both languages.
6. At 375 px there is no page-level horizontal scroll on `/self`.
