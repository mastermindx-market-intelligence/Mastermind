# Mastermind OS product reference

This directory is a bounded **offline product-contract reference**, not the OS backend, a runtime snapshot service, a new organizational record store, or an installed application.

Open `reference_workspace.html` directly in a browser. All navigation is local. The recorded checkpoint is explicitly dated; the other scenarios are synthetic failure/correction rehearsals. It does not show live workers or real provider conversation, and sends no instruction.

The accepted direction is one integrated Mastermind OS product over existing canonical owners. The complete scope and production acceptance gates are in the paired specification. This reference is a design/interaction candidate. It does not yet close its browser acceptance gate.

## Test

In a validation environment with pytest, Playwright and its Chromium browser already available:

```sh
python -m pytest research/mastermind_os/test_reference_workspace.py -q
```

To select an already-installed compatible Chromium explicitly, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its executable path. Do not change managed browser policies to make a test pass. The test fixture exposes only this authored document at a temporary loopback origin and closes that origin after the test session.

The test suite fails rather than silently declaring browser proof when the browser dependency is absent. It serves the exact file bytes and uses real browser interactions; there is no mocked application renderer or production network.

## Safety boundary

- Content Security Policy denies network connections and form submission.
- No cookies, credentials, private conversations, host paths, raw provider output or runtime database access.
- No persistent state, analytics, timers, service worker or background execution.
- Changing a view, selecting a scenario or opening an inspector changes only local presentation.
- Delivery, current execution, returned result, parent consumption, release and acceptance are deliberately different concepts.
- Graph relationships are design/record links, not admitted runtime dependencies.
- The Figma pause and existing source-writer boundaries are unchanged.

## Integration

Operation: `mastermind-os-rollout-contract-20260916-sol-001`.
Source/procedure pin: `8ba7deedde164c90298d3e88785d98e02fa5e2d2`.
Product home: existing `WS:CHAIRMAN-CONTROL-ROOM`.
Execution principal: existing Fabric Fable on Claude8; no new root or child is launched here.

Next: consume the existing producer owner's exact authorized mission/content/history contract and the current CCR/DF1 consumer before admitting one authenticated real mission-workspace implementation. The earlier recorded-workspace artifact and #595 design must be reconciled as reusable evidence, not overwritten.

`reference_acceptance.json` records this artifact's exact validation only. It contains no canonical company state and confers no permission.

## Current verification boundary

At the original checkpoint, two source-only checks and embedded JavaScript syntax passed. The installed sandbox Chromium refuses navigation with `ERR_BLOCKED_BY_ADMINISTRATOR` for both direct-file and loopback-preview URLs. Browser behavior, responsive geometry, visual quality and accessibility are therefore **NOT_VERIFIED**, not passed or skipped. No browser policy was changed, and the blocked browser campaign was not moved to another host.

The original Connections/focus findings are addressed in the source-only repair below; browser behavior remains unverified. Keep Draft/HOLD until a permitted browser campaign can test the exact candidate.

## Source-only relationship and focus repair — 2026-09-16

The shared inline presentation module now supplies six nodes and seven typed, source-linked design relationships. Both the SVG diagram and its equivalent list consume that same module. These are architecture relationships, never runtime admission or acceptance facts. Narrow screens select the readable equivalent list instead of scaling the diagram text down.

The source repair also preserves the current route when the skip link is used, preserves a stable search input as the dialog return target, and restores focus to the replacement graph/list control after re-render. Native dialog, keyboard, screen-reader and actual focus behavior are still browser acceptance cases, not established by a pure helper test.

No DOM emulator or browser workaround was used. Source checks execute the exact pure inline module in Node's isolated JavaScript context. Their boundary excludes DOM events, rendering, layout, browser security policy enforcement and accessibility. The original managed browser refusal remains unchanged; this repair does not retry it on another host.

Run only these independently useful source checks:

```sh
python -m pytest research/mastermind_os/test_reference_workspace.py -q \
  -k 'presentation_model or test_reference_exists or test_csp_is_content_bound'
```

Result for this source candidate after independent-review repair: **15 passed**. The new model's intended RED was **11 failed** before implementation, and the later review regressions failed **2/2** before their fixes. Three targeted mutations were killed: duplicate relationship acceptance, disconnected focus-target selection, and removal of all edges. Both actual inline scripts pass Node syntax checking. Full collection is **54 cases: 15 source-only and 39 browser-dependent**. Browser cases remain unrun on this repaired candidate; no screenshots or visual acceptance.

## Real R2 integration, separate from this reference

The incumbent records freeze is Mastermind #704, initially `8b94141106200f0c48b6d033cca19a8007ef0031`. Sol review `5228415542` requires repair before implementation. The new mission-route query decision is resolved, but the contract must preserve exact identity/authorization, historical roots after DISARM, separate execution/transport/product acceptance, and the approved authorized hot-window reader. A local CSRF nonce is not authenticated-user proof. The existing Program/detail drawer and live-reader work must be reused, not duplicated.

Claude8 confirmed consumption and relayed the review to the existing #704 native records writer at Slack `1789593485.305139`. That is coordination/ownership evidence, not proof the repair or real OS implementation is complete. The current live content reader's own artifact and binding still need exact recovery before any source integration.

## Native continuation recovery — 2026-09-16 22:09 UTC

The same managed Studio workspace recovered with all six prepared file hashes intact and no remaining source-test/help process. The original 13 source-only tests were rerun successfully (exit 0) with native Python 3.14.7 / Node v26.5.0. After the independent review, two additional regressions verify current-vs-historical environment qualification and centralized connected-target focus; the current source-only envelope is 15 tests. Both exact inline scripts also passed native Node syntax checking. The earlier native timeouts remain historical failed attempts; their outcome was not silently promoted. No browser-dependent case was selected or retried.

Current procedure pin is `5ee11ab1e993616f3568cfca4069cb21fa61fd8f`; required procedure blobs are unchanged. The existing #704 writer returned `c09672fc50a5895e7552936d3e585455424d85ae`; follow-through review `5228672592` still requires total/currentness-safe posture, no submission availability from a raw arm bit, and a genuinely bounded existing-owner reader. The reference is not that live implementation and remains Draft/HOLD.
