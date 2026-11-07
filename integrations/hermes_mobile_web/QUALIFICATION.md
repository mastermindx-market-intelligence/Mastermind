# Mobile integration qualification

Operation `hermes-mobile-web-20261107`, PR #2245. The Chairman's current direction is to continue other integrations without interrupting the existing gateway. This source slice follows that direction. It does not activate production Web Access or claim physical-phone acceptance.

## Implemented capability

- Opt-in native Hermes page at `#/mastermind`, sidebar entry and command-palette navigation.
- Leadership and specialist selection from real profile-route descriptors. Equal names on different connections stay distinct; an ambiguous shortcut never silently chooses a source.
- Exact-route saved-conversation navigation with source-change and asynchronous-result fencing.
- Existing persistent **Bot Chat** lookup through Hermes's own registry, including hidden canonical rows and compression-lineage tips. Missing, failed or ambiguous lookup never creates a replacement or sends a message.
- Explicit separate-chat draft action. Hermes retains its composer, stream renderer, tools, session persistence, stop and reconnect owners.
- Optional same-origin install manifest, original icons and home-screen shortcuts through the existing authenticated plugin API. No service worker, transcript store, credential store, public listener, offline-send queue or new runtime.

## Qualified source

Production JavaScript: commit `36ae2b56b3904c35af638c31f79c21919a83c4fd`, blob `32b63e4fd9d2153d52b592ada09c840bc58ce1d0`.
Native metadata source: introduced at `8563f6a0bc37875c02f07c6d4c7d84133bfd14dd`, unchanged by the navigation repair.
Final expanded native test driver and continuity module: staged revision `58be12261489bd0590bd97002471094a22fd6d46`.

Hermes donor: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, v0.23.0, including the previously byte-verified local tracked deltas. The frozen qualification copy is outside the production Hermes home. No existing donor source or active writer was replaced. Attribution for adapted native test patterns is in THIRD_PARTY_NOTICES.md.

## Executed verification

| Proof layer | Observed result | Scope |
|---|---|---|
| Launcher behavior and React component tests | 29 passed | Exact route, stale replies, canonical identity, safe titles, lifecycle and install metadata; SDK fixtures |
| Native HTTP/plugin boundary | 19 passed | Actual Hermes authentication, dynamic mount and enable/disable gates in isolated homes |
| Native runtime SDK loader | 1 passed | Unmodified ESM import, opt-in registration of route/sidebar/palette and complete teardown through the actual SDK |
| Browser matrix | 12 passed | Chromium and WebKit; light/dark; widths 320, 390 and 1280; explicit SDK/test-data fixture |
| Full native application journey | Passed, original process 5593 / exit 0 | Actual built native renderer, actual isolated gateway, actual SessionDB and upstream scripted local provider |

The 29 UI and 1 native SDK checks were rerun after the `in-place` navigation repair. The 12-browser matrix was also rerun on that corrected shipping JavaScript. The unchanged Python API retains its 19 passing native boundary tests. These are separate campaigns, not a production-readiness percentage.

### Native application journey: what it actually proved

The test used a fresh home with only explicit synthetic profiles and the local scripted provider. It loaded the production browser-build artifact read-only, discovered this package through Hermes's own plugin mechanism and used a native one-use launch link without publishing the credential.

1. Native initial boot became interactive without force-clicking or bypassing its overlay.
2. The shipping plugin opened a Secretary draft through the real SDK. A uniquely marked request reached the local provider exactly once.
3. The native browser displayed a Markdown heading while the provider was deliberately held before completion. After release, bold text had computed weight 600, the code sample used the native monospace font, and a real table rendered.
4. A reload retained the original completed conversation and did not dispatch the marked turn again.
5. A cold home-screen-style shortcut opened the pre-existing, hidden Secretary **Bot Chat**. The native SessionDB contained one canonical title row; no replacement chat was created.
6. During a second held stream, the browser lost network connectivity and reloaded. Reconnection returned to the same canonical session and recovered the native Stop control. Stop cancelled the original provider stream before its final chunk; it did not start a replacement. Read-only DB verification found exactly one user submission for that marker.
7. The same canonical conversation subsequently executed the harmless native command `printf MOBILE_TOOL_OK`, rendered its native tool row and completed the result continuation. There was one terminal tool request and two expected provider completions: tool request and post-tool result.

The receipt recorded 256 received native WebSocket frames, zero JavaScript page errors, one first-turn provider request, zero reconnect resubmissions and one canonical Bot Chat row. Only the fixture's own process group was stopped during cleanup. Its SIGTERM exit code 1 is the donor's logged service-revival policy, not an unobserved production restart.

**This is real native integration with a synthetic local provider. It is not proof of a real cloud model reply, live Nous OAuth, access from another device, Mac Desktop/browser cross-control or physical iPhone use.**

### Explicit remaining native behavior

- The already-emitted prefix of a deliberately paused in-progress stream did **not** repaint immediately after the offline reload. The original running turn and Stop control did return, and its interrupted text was present after the terminal update. Completed-history reload passed. The receipt records `partialPrefixRehydratedBeforeNextDelta: false`; do not claim seamless partial-prefix replay. No second transcript cache was introduced to conceal this upstream behavior.
- Cold contribution loading produced transient native `/api/sessions/mastermind` 404 reads before the custom route settled. The corrected normal-open navigation no longer leaves the page route as the target conversation. One timeline read also returned 404 during the reconnect case. The successful user journey does not erase those native diagnostic observations.
- Optional external font requests were deliberately blocked by the fixture, and one document request failed during the intentionally offline reload. They are retained separately from the zero JavaScript error result.

### Component-browser scope

The 12 scenarios verify exact Secretary route and Bot Chat lineage-tip options, no automatic draft creation, specialist disclosure, keyboard focus, controls at least 44px, no horizontal overflow, controls reachable at reduced viewport height and disconnected-state disabling. Preview images explicitly identify isolated test data. Browser viewport reduction is not a physical mobile keyboard or Safari-device test.

### Native authentication scope

Anonymous metadata, icon and manifest requests return 401. The authenticated fixture owner receives 200. Disabling an already mounted plugin returns 404 to that owner while anonymous callers still receive 401. The direct router has no POST handler; the full native namespace fallback returns 404 for unsupported POST. Origin/prefix and malformed-icon cases are checked. No authentication middleware, consent check or real-home I/O guard was weakened.

## Defect found and fixed

The first expanded native Bot Chat run failed because this plugin requested native `intent: 'tab'` from its full-page route. That intent intentionally preserves the main route; Hermes then attempted to resume the literal `mastermind` path as a session. The plugin now uses the native normal-click **`in-place`** intent for saved and canonical conversation opens. The unchanged native scenario subsequently reached the original canonical row, reconnect, Stop and tool continuation. Component regressions pin that intent for both open paths.

Earlier fixture-only corrections remain recorded: the first parameterized canonical tests spread array cases into arguments; cases now use named rows. The HTTP test initially expected a direct-router 405 at the full native namespace, whose observed fallback is 404; both boundaries now have their own assertions. The SDK test used a nonexistent registry `get` helper and now uses native `getArea`. Native-browser readiness now follows the upstream interactive predicate; Markdown emphasis is checked by rendered weight rather than assuming a particular HTML tag. The offline error-page initializer is restricted to the exact fixture origin.

## Evidence and preservation

Private M2 root: `~/.local/state/mastermind/hermes-mobile-web-20261107/`.

- `integration-source/source-receipt.json`: staged source revisions and file hashes.
- `integration-ui-tests-v3.log` / `.exit`: 29 passes after navigation repair.
- `integration-native-auth-tests-v2.log` / `.exit`: 19 passes.
- `integration-native-sdk-v4.log` / `.exit`: 1 pass after navigation repair.
- `browser-proof-v3/browser-results.json`, twelve PNGs, `integration-browser-proof-v3.log` / `.exit`: 12 passes after navigation repair.
- `native-browser-proof-v6/native-browser-result.json`, native screenshots/logs and `native-browser-proof-v6.log` / `.exit`: passing expanded native journey, including explicit partial-prefix and transient-404 observations.

Earlier failing campaigns remain available; they were not relabelled green. Toolchain: Vitest 4.1.12 and Playwright 1.64.0. Matching browser engines were installed only in the operation's private testing directory. Production browser profiles, plugin folders, provider settings and service configuration were not changed. Never publish sensitive configuration backups from adjacent evidence directories.

## Product acceptance still owed

The prior production Web Access build, OAuth registration and private HTTPS route remain installed/configured but not activated by this continuation. No live plugin enable, gateway restart, real OAuth browser login, real provider canary, physical-phone test or full Mastermind OS completion is claimed. Broader OS/DeepSeek integration writers remain untouched. Source qualification and protected source release do not authorize the currently deferred production interruption.
