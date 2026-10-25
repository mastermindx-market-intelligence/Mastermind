# Hermes vs DeepSeek Harness — real independent source and startup canaries

**Date:** 2026-10-25. **State:** bounded disposable technical proof only; Meta-CEO and Secretary product/production acceptance remain open. This records new evidence for [Hermes candidate PR #1865](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1865), existing [DSH Web incumbent #1845](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1845), and source-only stacked [browser-auth smoke repair #1870](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1870). Never treat this report as runtime/admission authority.

## Immutable external sources

- Hermes Agent MIT source: NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18, real CLI reported version git.1c0cd66. Source was checked out clean into new disposable Linux scratch and installed with an isolated pinned Python 3.14 environment using uv; provider environment empty.
- DeepSeek Harness MIT source: deepseek-ai/deepseek-harness@687f282e8625c6b8d11ff58211a90524be2e4317, checked out clean in a separate scratch workspace. Node 24.22.1, corepack pnpm 11.28.5 exactly matched its packageManager contract; frozen lockfile installed 1,400 packages with install lifecycle scripts disabled. All seven native/host/desktop/client/web artifact build gates PASSED in 50.98s. Build is not app acceptance.
- All known bearer tokens, credentials, profile secrets and session cookies were excluded from published records. All test app servers bound only to 127.0.0.1 at OS-selected ephemeral ports and were shut down. The tests did not contact a model endpoint, Mastermind Executive/Steward or Fabric.

## What was actually observed

| Area | Hermes Agent | DeepSeek Harness |
|---|---|---|
| Actual pinned source acquisition/build | Clean pin; Python 3.14 CLI dependencies installed; real CLI help/tools/serve usable | Clean pin; frozen pnpm lock; seven build stages passed, 325 client artifact files recorded |
| Real provider-free Web | Actual Hermes serve --host 127.0.0.1 --port 0 --skip-build --isolated: root and /api/health HTTP 200; 18-second startup sample peak RSS about 185 MiB; listener absent after bounded shutdown | Native DSH Web now PROVEN: token-aware browser handshake returned text/html HTTP 200, 37,511 bytes, root and script markers true, owned process reaped |
| Role profiles | Upstream 'profile create --no-skills --no-alias' created separate mmsecretary (GLM-5.3-Flash candidate) and mmmeta (GLM-5.3 candidate). Each actual CLI registry enabled only clarify with zero stderr, pinned role SOUL/config source readback | DSH profile/UI is built; actual coherent Meta-CEO identity, native chat and constrained tools for Mastermind not yet qualified |
| No-credential tests | 32 source-side regression tests including unique-key YAML, aliases, tool registry, secret fields and profile separation; Python 3.12/3.13 Actions PASS | Corrected DSH smoke has 13/13 hermetic synthetic Node/Git/HTTP negative tests PASS, plus real pinned application positive test |
| Real GLM/Flash tool/inference/vision | NOT TESTED | NOT TESTED |
| Authenticated Steward read + governed Fabric RESULT/parent consumption | NOT TESTED | NOT TESTED |
| Protected merge, fleet install, GUI/TCC, 24h/7d continuity, original Chairman journey | NOT PROVEN | NOT PROVEN |

**Important correction:** The original incumbent #1845 native smoke returned HTTP_NOT_READY even after a real DSH build because it threw away the printed short-lived `?token=` capability and fetched the unsigned origin. DSH explicitly requires the launch token to exchange for a signed browser cookie. A separate sanitized one-shot verified the original app could serve real HTML 200; the repaired exact source in stacked #1870 follows the token only in memory with a fresh ephemeral CookieJar and never stores/prints it in the receipt. It then passed the actual DSH Web app as NATIVE_WEB_SHELL_PASS with owned-process cleanup. No inference, native chat response, browser GUI interaction or external-provider egress observation was claimed. The original HTTP_NOT_READY was a test-contract defect, not evidence to reject DSH.

## Meaning for selection and hosting

**Do not elect a winning Meta-CEO merely from startup.** Hermes is simpler to configure for a light read-only Secretary and has proven no-credential two-profile separation at CLI. DSH remains the original native app/Meta-CEO incumbent and now has genuine authenticated Web shell startup. Neither has proven correct role-scoped tool calls, original-parent outcome closure, user-facing chat or security isolation. Compare one identical authenticated Chairman idea-to-reviewed-result journey on both, with each receiving exactly the same eligible read-only Steward context and admitted worker route. Apply original R2 falsifiers, not a vendor-feature score.

**Self-host qualification before managed subscription** is justified by successful real host proof and spare authorized fleet capacity. Prefer an existing eligible Linux headless host for the first provider-free/canary Hermes backend, and a separately isolated mini1 Mac worker only where governed native GUI/CUA is necessary and its TCC/credentials/access constraints are resolved. Mini1's initial inactive-page count was misleading; a later direct memory_pressure report said about 69% system-wide free at observation. Its 16 GiB RAM and existing other apps still require sustained high-water tests and service fencing before adding a permanent worker. Nous Medium at USD 0.56/day (USD 16.80 per 30 running days; provider and tool inference separate) is an optional managed fallback; FlyHermes at USD 49/month bundles undisclosed model-specific credit economics and cannot yet justify replacing owned compute. Do not subscribe or assume BYO Z.ai coding-plan quotas work through external hosting until provider terms and receipt-qualified tests confirm.

## Effect, security and independent-review boundaries

- These are **disposable/foreground** tests. No provider key, external paid inference, background daemon, scheduled watch, app auth, physical Mac control, Mastermind API grant, production deployment or Secretary cutover occurred.
- An earlier mini1 worker census returned a private OAuth access token in retained output and acknowledged an out-of-scope known-hosts change. This evidence remains **not accepted**; privately revoke/rotate via credential owner and reconcile the exact host effect. Never copy the credential into GitHub, this public report, a hosted AI provider or a worker packet.
- The separate Fabric independent-review request refused before launch. This is not an external acceptance receipt or a reason to retry the refused operation. GitHub non-author review is requested and remains pending for the applicable PR heads.
- Mastermind Executive status was unavailable via a 429; its runtime truth is UNKNOWN and cannot be replaced by repository prose, test fixture, or the Hermes client. The six existing read-only Steward MCP tools are the lawful next consumer, with mastermind.steward.read enforcement at receiving service.
- DSH #1845 is not displaced or secretly rewritten: fix #1870 is stacked against that incumbent's branch and requires its protected integration/review. Hermes #1865 remains its own disjoint source operation. No merges or self approvals.

## Exact next meaningful integration gate

1. Get independent review and exact-head CI on #1865 and #1870; preserve unmerged parent #1845 custody. The pure CI/source smoke outputs are not company acceptance.
2. With credential and auth owners' lawful permission, activate one **scoped read-only six-tool Steward MCP** in the selected temporary isolated Hermes profile, using real identity and service enforced audience; separately qualify exact GLM-5.3, GLM-5.3-Flash and DeepSeek vision provider route, cost, permitted entitlements and model tool behavior. No unqualified broad MCP, SSH, computer-use or cron.
3. Through incumbent Executive/Capacity/Fabric, prove one admitted child actually STARTS and returns, then the original parent demonstrably consumes its evidence and rules CONTINUE/STOP. Run identical DSH path and 30-50 fixed tasks (quality, latency, cost, negative permission/unknown-effect probes). Only after real user-path acceptance, shadow continuity and rollback may Grok Secretary's bridge be retired.
