# Mobile integration qualification

Operation `hermes-mobile-web-20261107`, PR #2245. The Chairman's current direction is to continue other integrations without interrupting the existing gateway. This source slice follows that direction; it does not activate the web listener or claim phone acceptance.

## Implemented

- Native Hermes contribution at `#/mastermind`, plus sidebar and command-palette navigation.
- Real route descriptors for leadership and specialist profiles. Equal names on different connections remain distinct; an ambiguous shortcut never silently chooses a source.
- Ordinary saved-session reads and exact-route native navigation, with asynchronous generation and source-change fencing.
- Explicit persistent **Bot Chat** lookup through the original Hermes registry, including hidden canonical history and compression-tip resolution. Missing, failed or ambiguous lookup never creates a replacement or submits a message.
- Explicit separate-chat draft action; native Hermes retains its composer, stream rendering, tool activity, history, stop and reconnect behavior.
- Optional same-origin home-screen manifest and original icons under the existing authenticated plugin namespace. No service worker, offline-send queue, transcript store, new auth service or public listener.
- Both halves remain opt-in through Hermes's existing enable mechanisms.

## Source identity

Implementation and tests are on the existing `sol/hermes-mobile-web-20261107` branch. Qualified frontier: `a2fb762a3c15ea508b46c30e1dad47f76eb37f2a`.

The shipping JavaScript has not changed since `971c6932e6165f0dcf85349a929d1569c78651d2`; blob `84e9ee2ca56a5d6d059f62b9936a3c4b25287f6a`. Native metadata source was added at `8563f6a0bc37875c02f07c6d4c7d84133bfd14dd`.

Hermes donor: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, v0.23.0. Source-level tests used the existing frozen qualification copy outside the production Hermes home. No existing donor modifications were replaced.

## Executed verification

| Proof layer | Observed result | Limits |
|---|---|---|
| Launcher behavior and React component tests | 29 passed | SDK behavior fixtures; not a live provider conversation |
| Native HTTP and plugin boundary | 19 passed | Actual Hermes web server, auth middleware and enable/disable gate in isolated test homes; not live Nous OAuth |
| Native runtime plugin loader | 1 passed | Actual Hermes SDK imports, unmodified ESM load, opt-in behavior, route/sidebar/palette registration and teardown; no production plugin installation |
| Browser scenarios | 12 passed | Chromium and WebKit; light/dark; 320px, 390px and 1280px; SDK/test-data fixture, not physical iPhone or full native-app acceptance |

The browser scenarios verify exact Secretary route and Bot Chat lineage-tip navigation, absence of automatic draft creation, specialist disclosure, keyboard focus, controls at least 44px, no horizontal overflow, controls reachable at reduced viewport height and disconnected-state disabling. Screenshots are explicitly labelled integration previews with test data. They do not fabricate live agent status or production conversation history.

Native boundary tests execute the real plugin mounting and runtime disable mechanisms. Anonymous metadata/icon/manifest requests return 401; the authenticated fixture owner receives 200; disabling a mounted plugin returns 404 to that owner, while anonymous callers still receive 401. The direct router has no POST handler; Hermes's namespace fallback returns 404 for unsupported POST. No auth middleware, consent check or test-home guard was weakened.

Toolchain: Vitest 4.1.12; Playwright 1.64.0. Its matching Chromium and WebKit engines were installed only in the operation's private test directory. Production browser profiles, source dependencies and service settings were not changed.

## Failures retained and resolved

The first launcher campaign exposed a table-driven fixture error: array cases were spread into positional callback arguments. The fixtures now carry named `rows` objects; the missing/ambiguous canonical-history assertions are unchanged. The native HTTP test initially expected the direct router's 405 at the full gateway; the observed native namespace fallback is 404. Both the direct no-POST assertion and native denial are now checked. The SDK proof initially used a nonexistent registry `get` helper; it now uses the actual `getArea` owner. Missing browser revisions were supplied in an isolated engine directory rather than altering the production runtime.

## Evidence location

Private M2 evidence remains under `~/.local/state/mastermind/hermes-mobile-web-20261107/`:
- `integration-source/source-receipt.json`: immutable source revision and per-file SHA-256s.
- `integration-ui-tests-v2.log` and `.exit`: 29 passes.
- `integration-native-auth-tests-v2.log` and `.exit`: 19 passes.
- `integration-native-sdk-v3.log` and `.exit`: 1 pass.
- `browser-proof/browser-results.json`, twelve PNGs, `integration-browser-proof-v2.log` and `.exit`: 12 passing browser scenarios.

Do not publish configuration backups, credentials, browser profiles or runtime state from adjacent evidence directories. No newly spawned provider or unattended worker is claimed.

## Remaining product proof

The saved production OAuth/Tailscale/webapp setup from the parent delivery document remains separate. No gateway restart, live plugin enable, real OAuth browser login, provider stream, desktop-to-phone session continuation or physical-phone test has occurred in this slice. Full native browser/provider acceptance remains owed. Broader Mastermind OS and DeepSeek integration paths were not edited.
