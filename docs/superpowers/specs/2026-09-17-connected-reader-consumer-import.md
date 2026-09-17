# Connected Reader Consumer Import

## Scope

Imported the Connected Reader consumer candidate at uncontested paths under
`integrations/mastermind_window_reader/`, including its six source artifacts,
the ten candidate tests, and `tools/verify_window_browser.py` as
`scripts/verify_window_browser.py`. Imports now use the real Mastermind modules
(`control_plane.visible_turn_projection` and
`integrations.business_mcp_auth.*`) rather than `vendor_snapshot/` or
candidate-relative `src/` paths. Static browser assets moved under `static/`;
the candidate's recorded capture fixture moved with its tests.

Source archive digest:
`6b67fd3158c32e35dc711317dc23e36ade41dbe3d12b7b3ce6a8c6348228310e`
(subset receipt `0b259180…`). This import does not copy or import the archive's
`vendor_snapshot/**`.

Added `broker_window_source.py`, a pure in-process adapter that rehydrates the
exact `_ohf_observe_turn` JSON wire into a typed `ReadResult`. It requires the
broker's `truncated` and `gap` item keys, validates the complete top-level and
nested schemas, checks `retained_scope` when supplied, preserves reported gaps,
and never imports or calls the broker, sockets, network, or I/O.

## Verification

- Imported candidate tests: 72 passed, 47 skipped (`rc=0`) because Playwright /
  Chromium and PyJWT are unavailable on this host; no dependency was installed.
- Adapter RED: module missing; adapter GREEN: 12 passed (`rc=0`).
- Static fences and the mandated baseline/full suites passed (`rc=0`).
- Gap mutant failed (`rc=1`) and was restored; `git diff --exit-code` passed.
- `WindowReader` still fails closed with `CONTENT_DECISION_REQUIRED` when an
  owner-supplied `ContentDecision` is absent.

## Not Done

- G1 safe-content classifier (owner: Steward #599 lineage per Sol R83 item 2).
- G2 registration, mount, client registration, auth-scope change, provider or
  browser canary, Slack/GitHub publication, Ready/merge/install.
- Real registered-client or live-provider source-to-browser proof.

The reader remains **BUILT_NOT_PROVEN**.
