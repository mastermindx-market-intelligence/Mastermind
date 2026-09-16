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

The two source-only checks pass and the embedded JavaScript passes Node syntax checking. The installed sandbox Chromium refuses navigation with `ERR_BLOCKED_BY_ADMINISTRATOR` for both direct-file and loopback-preview URLs. Browser behavior, responsive geometry, visual quality and accessibility are therefore **NOT_VERIFIED**, not passed or skipped. No browser policy was changed, and the blocked browser campaign was not moved to another host.

Source-review follow-ups before browser acceptance include the Connections edge presentation and search/skip-link focus restoration. These are recorded review risks, not repaired or proven behavior. Keep Draft/HOLD until an independently permitted browser campaign can test the reference on its exact source.
