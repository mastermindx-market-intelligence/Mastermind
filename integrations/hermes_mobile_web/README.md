# Mastermind mobile integration for Hermes

A small, opt-in plugin for the **existing Hermes Desktop and Webapp**, not another chat client or agent runtime. It adds a responsive team page, source-correct conversation navigation and mobile home-screen metadata. The native Hermes renderer retains Markdown, code, tables, tool activity, streaming, history, stop and reconnect.

Operation: `hermes-mobile-web-20261107`, existing PR #2245.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`.
Cumulative deployment record: `research/mastermind_os_production_fasttrack_2026-11-07/MOBILE_WEB_DELIVERY.md`.
Proof and limitations: [QUALIFICATION.md](QUALIFICATION.md).

## Current scope

The Chairman directed this continuation to advance other elements and integrations without interrupting the M2 gateway. This package has been developed and tested in isolated qualification environments. It has **not** been enabled in the production Hermes installation. The previously configured Web Access/OAuth/private HTTPS activation and real-phone acceptance remain separate.

Existing Mastermind OS/DeepSeek PR #2177, the `omh` plugin, production profiles, provider settings and active conversations are not modified. No new scheduler, memory store, identity service, queue, gateway daemon or offline send mechanism is introduced.

## What it does

Open **Mastermind** from the native sidebar or command palette. Select Meta-CEO, Secretary, Chief of Staff or a specialist from the real gateway profile inventory. The source connection remains part of the selection, so identically named profiles cannot silently exchange conversations.

**Open Bot Chat** resolves the selected profile's existing hidden canonical chat through Hermes's indexed title registry. It opens the current compression-lineage tip when reported. A failed, missing or ambiguous lookup never creates a replacement. **New separate chat** creates only an explicit native draft; it does not submit a message or replace Bot Chat. Ordinary saved conversations open with their original route and profile.

The browser half optionally attaches a same-origin, authenticated web-app manifest and home-screen shortcuts. Apple standalone metadata is added without replacing unrelated head elements. Install support depends on the browser and authenticated deployment; this is not an App Store application. Chats require connectivity. No service worker or transcript cache is added.

## Ownership and package contents

| Surface | Owner |
|---|---|
| Agent/profile inventory and current source | Native Hermes profile-route SDK |
| Canonical Bot Chat identity and lineage | Native Hermes session registry |
| Composer, rendering, tools and conversation history | Native Hermes Desktop/Webapp |
| OAuth, cookies, tickets and plugin API access | Existing Hermes authentication |
| Plugin discovery, enable/disable and removal | Existing Hermes unified-package mechanisms |
| Team page and static install metadata | This narrow plugin |

`desktop/plugin.js` is unbundled ESM importing only the supported Hermes SDK and shared React runtime. `dashboard/plugin_api.py` supplies static metadata and generated original icons through the existing authenticated plugin namespace. The Python entrypoint registers no tools or hooks. Both plugin halves remain opt-in.

Qualified donor: MIT-licensed `NousResearch/hermes-agent` at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (v0.23.0). No upstream source or branding is copied into this package. The existing native SDK and renderer are reused in place. Treat an incompatible SDK update as a qualification change, not permission to guess APIs or reimplement Hermes state.

## Adoption after source qualification

Do not activate this package merely because this README or a PR exists. Use the accepted exact source revision and existing installation owner; preserve current writers and production work. Inspect any pre-existing package with this name before installation.

Hermes supports a monorepo subdirectory and immutable commit selection:

```sh
hermes plugins install \
  mastermindx-market-intelligence/Mastermind/integrations/hermes_mobile_web \
  --ref <accepted-40-character-commit> --no-deps --no-enable
```

The first install is deliberately disabled. The package adds no Python dependency beyond Hermes's existing FastAPI stack. Use Hermes's normal Plugins/Capabilities controls for its agent/API and desktop halves when adoption is authorized, then verify that **Mastermind** appears in the intended native gateway's browser. Do not hand-edit the generated Webapp bundle or overwrite a different user's desktop plugin. A disabled install, enabled contribution, activated listener, successful login and accepted phone workflow are different receipts.

The private-network connection, supported Nous login and existing Web Access settings remain owned by the deployment record. Do not expose the loopback port publicly or disable TLS, origin, cookie or permission checks. Production gateway interruption is currently deferred by the Chairman.

## Reproducible tests

Use a disposable copy of the pinned donor and this exact source revision. The donor's existing Node/test toolchain can be linked into the disposable package; never run `npm ci` over the live Desktop dependency tree. Do not copy production profiles, auth stores, databases, browser profiles or `.env` files into a test home.

**Component behavior:** from the staged package, use the donor's Vitest installation with `vitest.config.mjs`. `tests/launcher.test.jsx` checks exact routes, canonical-chat refusal behavior, stale replies, React lifecycle, disconnection, HTML-safe titles and metadata ownership.

**Native Python/auth:** copy the package into `<qualification-source>/tests/mastermind_mobile/`, then use the donor's canonical runner:

```sh
HERMES_TEST_FILE_RETRIES=0 scripts/run_tests.sh \
  tests/mastermind_mobile/tests/test_install_metadata.py -j 1
```

**Actual SDK loader:** copy `tests/native-sdk.contract.test.ts` into the disposable donor's `apps/desktop/src/contrib/mastermind-mobile.contract.test.ts`, set `MOBILE_PLUGIN_SOURCE` to the staged `desktop/plugin.js`, then run the donor's UI Vitest project. The test loads the unmodified ESM through the native runtime loader, checks opt-in registration and verifies teardown.

**Browser matrix:** run `tests/browser-proof.mjs` with `HERMES_ROOT` pointing to the donor toolchain and `MOBILE_PROOF_OUTPUT` to a private evidence directory. Matching Playwright Chromium/WebKit engines must exist; `PLAYWRIGHT_BROWSERS_PATH` can isolate them from production. This is an explicitly labelled SDK/test-data preview, not a live conversation.

**Native application journey:** run `tests/native-browser-proof.mjs` with all four explicit paths:

- `MOBILE_QUALIFICATION_ROOT`: disposable donor source, outside the live Hermes installation.
- `MOBILE_TEST_PYTHON`: the donor's qualified test interpreter.
- `MOBILE_DONOR_BUNDLE`: the already-built native Webapp renderer, read only.
- `MOBILE_NATIVE_PROOF_OUTPUT`: a fresh private test/evidence directory.

It creates its own isolated home, fixture profiles and local scripted provider, launches only its owned test gateway, obtains a native one-use browser link without logging it, and cleans up its own processes. It tests real native rendering and continuity, not real Nous OAuth or model intelligence. Its browser denies unrelated network requests, including optional external font fetches. Preserve failures and read terminal receipts before rerunning a changed case.

## Rollback

Disable this plugin through the same native owner and verify its route/sidebar/metadata become unavailable. Uninstall only this exact package when authorized. Do not delete native conversations or profiles, reset Tailscale Serve, replace OAuth clients or stop the gateway merely to remove this UI contribution.

Direct implementation rationale: `LOWER_TOTAL_OVERHEAD` for this bounded SDK integration and `UNIQUE_APPROVED_ACCESS` for donor qualification. No delegated worker or post-turn executor is claimed.
