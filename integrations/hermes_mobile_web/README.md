# Mastermind mobile integration for Hermes

An opt-in plugin for the **existing Hermes Desktop and Webapp**, not another chat client or agent runtime. It adds a responsive team page, source-correct conversation navigation and mobile home-screen metadata. The native Hermes renderer retains Markdown, code, tables, tool activity, streaming, history, stop and reconnect.

Operation: `hermes-mobile-web-20261107`, existing PR #2245.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`.
Cumulative deployment record: `research/mastermind_os_production_fasttrack_2026-11-07/MOBILE_WEB_DELIVERY.md`.
Executed proof, known native behavior and remaining acceptance: [QUALIFICATION.md](QUALIFICATION.md).

## Current scope

The Chairman directed this continuation to advance other elements and integrations without interrupting the M2 gateway. This package is implemented and qualified in isolated environments, including a passing real-Hermes renderer/gateway journey with a synthetic local provider. It has **not** been installed or enabled in production. The previously configured Web Access/OAuth/private HTTPS activation and real-phone acceptance remain separate.

Existing Mastermind OS/DeepSeek PR #2177, the `omh` plugin, production profiles, provider settings and active conversations are not modified. No new scheduler, memory store, identity service, queue, gateway daemon or offline send mechanism is introduced.

## What it does

Open **Mastermind** from the native sidebar or command palette. Select Meta-CEO, Secretary, Chief of Staff or a specialist from the real gateway profile inventory. The source connection remains part of the selection, so identically named profiles cannot silently exchange conversations.

**Open Bot Chat** resolves the selected profile's existing hidden canonical chat through Hermes's indexed title registry and opens its current compression-lineage tip when reported. A failed, missing or ambiguous lookup never creates a replacement. **New separate chat** creates only an explicit native draft; it does not submit a message or replace Bot Chat. Saved conversations open with their original route and profile. Normal opens use native in-place navigation so the custom page route cannot remain the conversation target.

The browser half optionally attaches a same-origin, authenticated web-app manifest and home-screen shortcuts. Apple standalone metadata is added without replacing unrelated head elements. Install support depends on the browser and authenticated deployment; this is not an App Store application. Chats require connectivity. No service worker or transcript cache is added.

## Ownership and package contents

| Surface | Owner |
|---|---|
| Agent/profile inventory and current source | Native Hermes profile-route SDK |
| Canonical Bot Chat identity and lineage | Native Hermes session registry |
| Composer, rendering, tools and history | Native Hermes Desktop/Webapp |
| OAuth, cookies, tickets and plugin API access | Existing Hermes authentication |
| Plugin discovery, enable/disable and removal | Existing Hermes unified-package mechanisms |
| Team page and static install metadata | This narrow plugin |

`desktop/plugin.js` is unbundled ESM importing only the supported Hermes SDK and shared React runtime. `dashboard/plugin_api.py` supplies static metadata and generated original icons through the existing authenticated plugin namespace. The Python entrypoint registers no tools or hooks. Both plugin halves remain opt-in.

Qualified donor: MIT-licensed `NousResearch/hermes-agent` at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (v0.23.0). The runtime and renderer are reused in place, not copied into a second app. Native test patterns are adapted with attribution in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is a Mastermind integration, not an official Nous mobile product. Treat incompatible SDK changes as qualification changes, not permission to guess APIs or recreate Hermes state.

## Adoption after source qualification

Use the accepted exact source revision and existing installation owner; preserve current writers and production work. A PR or this README is not activation authority. Inspect any pre-existing package with this name before installation.

Hermes supports a monorepo subdirectory and immutable commit selection:

```sh
hermes plugins install \
  mastermindx-market-intelligence/Mastermind/integrations/hermes_mobile_web \
  --ref <accepted-40-character-commit> --no-deps --no-enable
```

The first install is deliberately disabled. No Python dependency is added beyond Hermes's existing FastAPI stack. Use the normal Plugins/Capabilities controls for the agent/API and desktop halves when adoption is authorized, then verify **Mastermind** appears in the intended gateway's browser. Do not hand-edit the generated Webapp bundle or overwrite another plugin. Disabled installation, enabled contribution, activated listener, login and accepted phone workflow are distinct receipts.

Private-network access, Nous login and Web Access settings remain owned by the cumulative deployment record. Do not expose the loopback port publicly or disable TLS, origin, cookie or permission checks. Production gateway interruption is currently deferred by the Chairman.

## Reproducible qualification

Use a disposable copy of the pinned donor and this exact source revision. The donor's Node/test toolchain can be linked into the disposable package; never run `npm ci` over the live Desktop dependency tree. Do not copy production profiles, credentials, databases, browser profiles or `.env` files into a test home.

**Component behavior:** from the staged package, run the donor's Vitest executable with `vitest.config.mjs`. `tests/launcher.test.jsx` checks exact routes, canonical-chat refusal behavior, stale replies, lifecycle, disconnection, HTML-safe titles and metadata ownership.

**Native Python/auth:** copy the package into `<qualification-source>/tests/mastermind_mobile/`, then use the donor's canonical runner:

```sh
HERMES_TEST_FILE_RETRIES=0 scripts/run_tests.sh \
  tests/mastermind_mobile/tests/test_install_metadata.py -j 1
```

**Actual SDK loader:** copy `tests/native-sdk.contract.test.ts` into the disposable donor's `apps/desktop/src/contrib/mastermind-mobile.contract.test.ts`; set `MOBILE_PLUGIN_SOURCE` to the staged `desktop/plugin.js`, then run the donor's UI Vitest project. It loads unmodified ESM through the native runtime loader and verifies opt-in registration and teardown.

**Browser matrix:** run `tests/browser-proof.mjs` with `HERMES_ROOT` pointing to the donor toolchain and `MOBILE_PROOF_OUTPUT` to private evidence. Matching Playwright Chromium/WebKit engines must exist; `PLAYWRIGHT_BROWSERS_PATH` isolates them from production. The matrix is explicitly labelled SDK/test data, not a live agent conversation.

**Native application journey:** run `tests/native-browser-proof.mjs` with these explicit paths:

- `MOBILE_QUALIFICATION_ROOT`: disposable donor source outside the live Hermes installation.
- `MOBILE_TEST_PYTHON`: the donor's qualified test interpreter.
- `MOBILE_DONOR_BUNDLE`: the already-built native Webapp renderer, read only.
- `MOBILE_NATIVE_PROOF_OUTPUT`: a fresh private test/evidence directory.

It creates its own home, synthetic profiles and local scripted provider, launches only its owned test gateway, obtains a one-use browser link without logging it, and cleans up its processes. It tests native streaming/formatting, completed-history reload, the existing canonical Bot Chat, disconnect without resubmission, native Stop and a harmless terminal-tool continuation. It does not establish real OAuth, model intelligence, Desktop cross-control or physical-phone acceptance.

Qualification explicitly preserves two native observations: already-emitted in-progress text may not repaint before another native update after disconnection, and cold contribution loading can produce transient session-route/timeline 404 reads. The successful journey does not certify those observations resolved. Preserve failures and terminal receipts before rerunning changed cases.

## Rollback

Disable the exact plugin through the native owner and verify its route/sidebar/metadata disappear. Uninstall only this package when authorized. Do not delete native conversations or profiles, reset Tailscale Serve, replace OAuth clients or stop the gateway merely to remove this contribution.

Direct implementation rationale: `LOWER_TOTAL_OVERHEAD` and `UNIQUE_APPROVED_ACCESS` for bounded SDK integration and donor qualification. No delegated worker or post-turn executor is claimed.
