# Hermes-backed mobile web delivery

Operation: `hermes-mobile-web-20261107`.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`; supplement to this directory's README and HANDOFFS, not a new task/runtime registry.
Assignment: secure mobile access to the existing M2 Hermes Meta-CEO, Secretary and other profiles, preserving Mac-style streaming, formatting, history and tools.
Procedure pin: Mastermind `4fb0d3825b5b4b4439e65e7382660112b7c2ef8c`, Skillpack 1.0.1/bootstrap 1. The observed later relevant-path comparison changed BOOTSTRAP_KERNEL only; its continuation emphasis was compatible.
Source carrier: existing GitHub branch `sol/hermes-mobile-web-20261107`, PR #2245. Installed-host work and isolated tests use the original authorized Studio Direct local M2 carrier. No live writer or started job has been transferred.

## Current Chairman direction and outcome

After the earlier activation request, the Chairman directed: **continue working on other elements and integrations first**. Production interruption is therefore deferred, not a question to repeat or permission to force a restart. This continuation left the running gateway, installed plugin folders, provider settings and active conversations unchanged.

The non-disruptive source slice now implements a native mobile team interface and install metadata, with a passing actual-Hermes browser/gateway fixture journey. **The production phone product is still not activated or accepted.** Current read-only `hermes webapp --status` still says the gateway started before Webapp was enabled and needs a restart. Both production `plugins/mastermind-mobile` and `desktop-plugins/mastermind-mobile` directories remain absent.

Parent completion still requires: reach the M2 from a phone, authenticate with the supported intended account, select Meta-CEO/Secretary, receive a real formatted provider stream, reopen the original conversation, reconnect without duplicate sends, and preserve native Desktop operation. Test fixtures and phone-sized browsers do not prove physical-phone or live-provider acceptance.

## Reuse architecture

Use the installed MIT-licensed Hermes **actual Desktop renderer compiled for the browser**, its native gateway, profiles, sessions, memory, tools and OAuth. A narrow unified package in `integrations/hermes_mobile_web/` adds the Mastermind team page and install metadata through the existing SDK/API extension points. No replacement chat framework, DeepSeek-to-Hermes translator, identity service, scheduler, transcript store, offline mutation queue or agent runtime was added.

The broader Mastermind OS shell, DeepSeek PR #2177 and existing `omh` plugin retain their live integration work; their source files were not edited. This usable-first slice does not claim completion of the wider OS or company-execution programme.

## Previously installed effects — do not repeat

### Native browser renderer

`hermes webapp --build-only`, original process 805 / exit 0, built the installed donor's `apps/desktop/dist-webapp`.

- Hermes v0.23.0, source `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.
- Build source hash `1faeb5281c0b84c0d235e64dcebf8709a497e48dcb573181b46b2e959f27b0ca`.
- Output hash `a9fd70c59c30de37a4fb9fbc7077dc28f35df2d5c530df79cb45cf6197e25d16`.
- Upstream receipt: Darwin/arm64, production mode, Node 26.12.1.
- Upstream isolated build workspace avoided pruning native Desktop dependencies. No generated bundle was hand-edited.

### OAuth and configuration

Dedicated native Nous Web Access registration succeeded through the existing signed-in account, process 18955 / exit 0. It is separate from the dashboard client; registration is retained in the owner-only `webapp/sign-in-registration.json`. No token, account credential or client secret is published here.

Saved Web Access is enabled with its dedicated HTTPS public URL. Effective listener remains 127.0.0.1:9120. Preservation checks found zero changes to preexisting non-webapp settings. This continuation did not change those settings or role/model/provider selections.

### Private HTTPS

Original process 28220 installed `tailscale serve --bg --https=8443 http://127.0.0.1:9120`. Every preexisting Serve route was read back unchanged; public Funnel remained off. The exact private operating URL remains in the private host receipts and Chairman chat, not a public service.

The earlier correct-host/SNI request with an explicit mapping to the observed Tailscale IP returned curl exit 0, TLS verification 0 and HTTP 502. That proved the certificate/transport, not an available app. M2 default hostname lookup failed with `CorpDNS: false`; its global DNS setting was preserved. Phone DNS/reachability remains unverified. No new public forwarding or insecure auth/TLS/origin override was introduced.

### Earlier component qualification

The earlier 189 passing checks remain valid for their exact scope: 42 UI, 47 streaming/continuation and 100 native access checks. An initial canonical Python campaign had 89 passes, 3 failures and 8 setup errors caused by test bootstrap entering the real Hermes home and an incomplete isolated environment. The subsequent source snapshot outside the live home passed all six selected files in two batches of 40 + 60, without weakening guards or patching production code. Do not repeat these unchanged campaigns just to create activity.

## New non-disruptive integration

Implementation: `integrations/hermes_mobile_web/`.
Detailed reproduction/adoption: its README.md.
Exact proof and limits: its QUALIFICATION.md.
Shipping JavaScript: `36ae2b56b3904c35af638c31f79c21919a83c4fd`, blob `32b63e4fd9d2153d52b592ada09c840bc58ce1d0`.

The package supplies:
- Responsive native Mastermind page, sidebar and command-palette entry.
- Real route-aware leadership/specialist selection; duplicate names on different connections stay distinct.
- Original canonical **Bot Chat** lookup and compression-tip navigation, with no replacement creation on ambiguity or failure.
- Saved conversations and explicit separate-chat drafts through native Hermes actions.
- Authenticated same-origin home-screen manifest, shortcuts and original icons; no offline transcript cache or service worker.

Both halves are opt-in. The package registers no agent tools or hooks and has not been installed or enabled in production.

### New qualification results

| Layer | Result |
|---|---|
| React/launcher behavior | 29 passed, rerun after navigation repair |
| Native auth/plugin boundary | 19 passed; actual auth, mounting and disable gates |
| Native SDK loader | 1 passed, rerun after navigation repair |
| Browser matrix | 12 passed on corrected source; Chromium/WebKit, light/dark, 320/390/1280px |
| Full native application fixture | Passed, process 5593 / exit 0; real renderer/gateway/SessionDB with a scripted local provider |

The expanded native fixture proved incremental rendering before provider completion, bold/code/table formatting, completed-history reload with no duplicate request, cold shortcut entry into an existing hidden Secretary Bot Chat, reconnect with one original submission, native Stop cancelling the original stream, and a subsequent harmless native `printf MOBILE_TOOL_OK` tool/result continuation on that same canonical chat. DB verification found one canonical title row and one user submission for the interrupted marker. The native screenshot shows the actual Hermes tool row, not a recreated chat component.

This is **native integration proof with synthetic profiles/provider**, not real Nous OAuth, real model intelligence, live Desktop cross-control or physical-phone proof.

### Defect repaired and remaining native observations

A real full-app failure exposed an incorrect `tab` navigation intent from the custom full-page route. The shipping plugin now uses native **in-place** navigation for normal saved and canonical chat opens. The unchanged native scenario then reached the correct canonical ID, reconnect, Stop and tool continuation.

The already-emitted prefix of a deliberately held in-progress stream did not repaint immediately after an offline reload. Running-turn identity and Stop did return; the interrupted text appeared after the terminal update. Completed-history reload passed. Do not claim seamless partial-prefix replay or add a second transcript cache to hide it.

Cold plugin registration produced transient `/api/sessions/mastermind` 404 reads before the route settled; a reconnect timeline read also returned 404. They remain disclosed in the detailed receipt. The final journey had zero JavaScript page errors; expected offline-document and blocked external-font failures are retained separately.

## Preservation and evidence

All production tracked donor changes remain byte-identical: combined patch SHA-256 `3cae368c9ca1369184e9ff0e7afae06a57c43cc12f5483ebfec68f93a77177af`, rechecked after the new native proof. Other writers' fallback/session changes and untracked tests were not reset, stashed or overwritten. Current read-only observation confirms the new plugin is absent from both production plugin locations.

Private evidence root: `~/.local/state/mastermind/hermes-mobile-web-20261107/`. Keep configuration backups private. New key receipts are `integration-ui-tests-v3`, `integration-native-auth-tests-v2`, `integration-native-sdk-v4`, `integration-browser-proof-v3`, `browser-proof-v3/browser-results.json` and `native-browser-proof-v6/native-browser-result.json`, with logs, exit files and screenshots. Source identities are retained in `integration-source/source-receipt.json`.

All fixture processes have terminal receipts. The latest cleanup census found no remaining fixture processes. Only the fixture gateway process group was terminated; the production gateway was not interrupted. No uncertain modifying effect, autonomous worker or background activation watcher is claimed.

## Exact continuation

1. Complete qualification/protected source release on the original PR #2245. The PR/merge receipt, not this editorial document, owns source release state. Source release does not activate the package.
2. Keep production interruption deferred under the current Chairman direction. Do not repeatedly ask for restart permission or redo the existing build, OAuth registration or Tailscale route.
3. At a permitted activation opportunity, reconcile current gateway/work/profile/source state, adopt the exact accepted plugin through native mechanisms, and activate the already-configured listener without displacing active work.
4. Verify intended-account OAuth and unauthorized access rejection over private HTTPS; real Meta-CEO/Secretary streams; saved/canonical history; stop/reconnect; native Desktop continuity; then physical-phone network, installation, keyboard and layout behavior. Retain the partial-prefix limitation until resolved and observed.

`MISSION_COMPLETE: false`. Source integration is implemented and qualified; production capability remains `BUILT_NOT_PROVEN` / partial installed composition. The current user-directed activation deferral is not an invented all-mission permission failure. The original activation-boundary question is superseded by the instruction to advance non-disruptive work first.

Direct execution reasons: `UNIQUE_APPROVED_ACCESS` and `LOWER_TOTAL_OVERHEAD`. No Fabric child or separate lifecycle owner was created. Agent OS projection remains `PLAN_NOT_ORG_LINKED`; this source evidence is not organizational completion or runtime admission.

## Rollback

Use the native plugin disable/uninstall owner for this exact package; never delete profiles or conversations. Remove only this operation's Serve route with `tailscale serve --https=8443 off`, not a global reset. Disable only `webapp.enabled` and restart safely when authorized; never restore an old whole config over concurrent changes. Revoke only the dedicated Web Access client when authorized, preserving dashboard/provider identities. Keep renderer maintenance on the upstream build/update path.
