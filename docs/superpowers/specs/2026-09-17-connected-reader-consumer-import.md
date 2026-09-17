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

- **G1 — safe-content classifier:** NOT DONE. Production reads require an
  owner-supplied `ContentDecision`; no default classifier is provided. Grantor:
  Sol. (owner ruled by Sol R83 item 2, root ts 1789607891.352309; no
  edit/start/merge authority on #599 is implied).
- **G2 — viewer-specific registered client:** NOT DONE. The Connected Reader viewer surface needs its own registered client; registration of another client (for example the Codex-Astra dynamic client registration) does not automatically cover this viewer. The owner must name the intended viewer surface, its existing registered client reference, issuer/resource/audience, the exact approved content scope, the source-permission owner, and the enrollment receipt or its absence. Grantor: the source-permission owner through the viewer's own enrollment (Sol source-boundary clarification, root ts 1789610946.339469).
- **G3 — production scope enrollment:** NOT DONE. Production requires the
  workspace content-read scope, which is mutually exclusive with the current
  Steward read scope. Grantor: Sol, through a new enrolled scope or an owner
  change to the Steward app by its #599 writer.
- **G4 — installed content service / broker read:** NOT DONE. The broker
  observation endpoint is reachable only through its configured Unix-domain
  socket and control-UID boundary. Grantor: S1/S3 owner (#623/#675/#678 lane)
  plus the host operator.
- **G5 — application mount:** NOT DONE. The reader requires a same-origin
  `https` resource at an allowed origin; no production route is mounted.
  Grantor: S7 owner (#599 writer).
- **G6 — provider canary / live proof:** NOT DONE. Terminal acceptance requires
  an observed live upstream response; autonomous production deployment remains
  prohibited. Grantor: Sol, after G1–G5.
- **G7 — publication:** NOT DONE. Authority boundaries prohibit opening,
  merging, and pushing a branch. Grantor: the seat, per the custody packet's
  §3 RELEASE.

The reader remains **BUILT_NOT_PROVEN**.
