# Mastermind OS production app/source census
Read-only census, 2026-10-05. Protected baseline: `7eac3ec252475600147ec9a376b8ca16403ac4c5`. Incumbent product candidate: PR #1225, `e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4`. No source edits, tests, runtime calls, installation or messages to external people were performed. The report distinguishes observed code from author-reported validation.

## Executive finding

Preserve and continue the existing React/TypeScript/Tauri application and #1225. Migrate the daily shell to the approved Atelier route hierarchy incrementally; retain existing qualified readers, command controller, fixed transport, publication owner, auth generations, exact selectors and original-operation recovery. Do not replace the frontend or use #702/#704 as the current implementation starting point. Their design/freeze records remain historical contract inputs; #1225 is materially newer working source.

#1046 merged at 2026-10-05T01:20:16Z, merge `92b85604061202a3d82889952ff940e6d140ffc8`. #1150 merged at 02:46:57Z, merge `d25d2adf892804cdfd1f1cb6acac8d2e8d5207eb`. Their old Draft/HOLD prose is stale as release status. GitHub PR metadata is primary for merged state.

- [PR1046](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1046)
- [PR1150](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1150)
- [Current product PR1225](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1225)
- [Canonical design carrier PR1010](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1010), `29cf30d21e61901c7025a2e53d7d3a63d10a974f`, documentation/design only.

## Incumbent source and current owner

#1225 is open Draft, branch `codex/mastermind-os-noir-convergence-20261003`, base exactly the protected baseline. GitHub reports 115 changed files, 55 commits. The original PR author is `mastermindxryan`; that is authorship evidence, not current writer assignment.

[Explicit ACK/START, comment5985886957](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1225#issuecomment-5985886957), by `chriswong6031-creator`, states the Chairman assigned the continuation to active lean replacement CEO root `01a10935-3e46-7b50-8e81-fe459e3a9319`, and that retired product root `01a104e6-58f8-76d3-8d99-1302a1cca072` is not resumed. Original `/Volumes/Mastermind/agent-workspaces/codex/3426/Mastermind` remains unchanged; seven unpublished files were byte-snapshotted before recovery. Exact source remains in the sole current custody workspace; no second product modifier or replacement PR.

[Integration return5987092993](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1225#issuecomment-5987092993), [continuation5987708979](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1225#issuecomment-5987708979), and [latest return5988489972](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1225#issuecomment-5988489972) retain this root's continuation and original history. They explicitly report MISSION_COMPLETE:false. Latest return says current source workspace clean and same product PR remains the delivery carrier.

A #1150 current-owner record names `/Volumes/Mastermind/agent-workspaces/web/lean-mastermind-owner-20261004`, operation `lean-owner-20261004-launch-release-001`, procedural writer custody receipt `91e4fd2168d7f5c6ba34ff4f751a1b8204140766be60bb9aa104184c2f55da42`, RULES_ABSENT. This is concrete custody evidence for the lean release operation; do not assume from it that every future #1225 write is automatically held by that filesystem location. Current native root/workspace liveness needs its existing delivery mechanism, not attribution from a GitHub login.

The earlier [#1046 RCH1 terminal closure5978253045](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1046#issuecomment-5978253045) releases the bounded maintenance writer and records no active modifier on #1046. Original source builders are terminal/released, while root product integration continues on #1225. Older root pickup records are superseded by the explicit lean replacement ACK.

Posting to PR1225 is a source/organizational delivery record. Earlier comments expressly state this was not native consumption, ACK, START or writer transfer; only the subsequent explicit ACK supports pickup. No independently verified current native session delivery or present source-writer liveness was tested in this census. Preserve independently assigned Web enhancement owner on issue1056; parent is reconciling that carrier.

## Package/runtime/test estate

[Baseline package.json](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/app/mastermind_os/package.json) and [candidate package.json](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/package.json):

| Dependency | Manifest version |
|---|---|
| App | 0.1.0, private ES module |
| React/react-dom | 19.3.0 |
| Vite | 8.3.0 |
| React Vite plugin | 6.1.1 |
| TypeScript | 7.0.2 |
| Vitest | 5.0.1 |
| Tauri JS API / CLI | ^2.11.1 / ^2.11.5 |
| Testing Library React / user-event | ^16.3.3 / ^14.6.7 |
| jsdom | ^30.1.0 |
| fake-indexeddb | 6.2.5, added by #1225 |

Cargo manifest: app0.1.0, Rust edition2021, Tauri/Tauri-build2, serde1, serde_json1, base640.22, rand0.8, sha20.10, url2, reqwest0.12 (rustls/json; default features disabled), tokio1/time, Tauri deep-link/opener2. These are manifest constraints, not all resolved lock versions.

Fixed shared frontend has separate native/web host choice, no React router package. App owns view state and exact Mission selection; host decodes closed DTOs. [vite.config.ts:4](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/app/mastermind_os/vite.config.ts#L4) selects native relative base or web `/os/`. Tauri config uses product Mastermind OS, identifier `com.mastermind.os`, 1200x820 window (minimum390x600), native-mode frontend build and custom deep link. Rust retains native bearer; fixed invoke handlers include executive auth/context/submit/status at candidate `src-tauri/src/main.rs:73–85`.

[CI workflow](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/.github/workflows/mastermind-os.yml) runs npm ci, TypeScript, Vitest and web build on Node22.14.0, PR/merge-group/protected push, 15-minute timeout. It does not itself run Rust/native installation/browser acceptance.

Latest owner records report 1,037 frontend PASS + one inherited skip, TypeScript/web/native frontend builds, 27 Rust tests, standalone native build; later publication integration 458 Python +31 repair tests, 266 Node +49 inspection/service tests. Those are author-reported scoped proofs, not newly run census validation. Latest #1225 note reports OS hosted37266323699 success, backend37266323724 and CodeQL pending at publication; present terminal CI was not re-polled.

## Exact implemented versus target boundary

### Protected baseline

[main.tsx:13–18](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/app/mastermind_os/src/main.tsx#L13-L18) creates native/web client, then `bindMissionHost(client)` with no command binding. Conditional App commands exist but baseline bootstrap cannot activate them. [host.ts:111–141,249](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/app/mastermind_os/src/host.ts#L111-L141) preserves optional complete command binding, auth invalidation and typed read decoding. Current protected README still describes older read-only direction and #702/#704; do not treat that as candidate architecture.

### Candidate #1225

- [main.tsx:17–29](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/main.tsx#L17-L29) calls composeMissionHost and owns pagehide/HMR disposal.
- [compose-mission-host.ts:7–22](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/compose-mission-host.ts#L7-L22) builds Executive only when immutable launch config and client.executive exist; composes IndexedDB store; passes binding to bindMissionHost.
- [os-executive-host.ts:29–38,60–125,149–157](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/orchestration/os-executive-host.ts#L29-L38) requires closed verified context1 with web_ceo_v3/1.4.0 and expiry; context/submit/status are auth-epoch fenced; getSession returns null. SEND/STOP have no qualified producer.
- [launch-config.ts:22–56](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/launch-config.ts#L22-L56) validates/freeze closed `VITE_MM_LAUNCH_CONFIG` v1, original workstream, priority, projects/profiles, optional bounded write/validation; no caller URL or catalog fallback.
- [indexeddb-pending-pointer-store.ts:15–19,140,224–225](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/orchestration/indexeddb-pending-pointer-store.ts#L15-L19) owns DB `mastermind-os-pending-v1`, version1, pointers store, atomic reserve/compare-clear; durable pointer is distinct from draft text.
- [App.tsx:63–95](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/App.tsx#L63-L95) implements Today/Projects/Inbox/Conversations/Knowledge PLUS Work/Programs/Fleet & Capacity company items and five legacy mission items. It is not the canonical five-only shell.
- [App.tsx:2154–2181](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/App.tsx#L2154-L2181) actually mounts all five daily components. Leaf README claims Inbox/Knowledge not registered are stale. Projects opens legacy exact Mission workspace through `open`; no Overview/Plan/Work/Evidence/More project workspace exists here. Knowledge gets no source-navigation callback.
- [Projects.tsx:27–48,96–118](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/projects/Projects.tsx#L27-L48) supports qualified supplied collection/search and exact resolved roots; owner not supplied. New project commands, active/archive semantics, project owner/detail remain gaps.
- [ConversationWindow.tsx:86–103](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/conversations/ConversationWindow.tsx#L86-L103) has unaddressed unsent draft and disabled Send, evidence/context inspection and focus return. [useObservedConversation.ts:15–17](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/conversations/useObservedConversation.ts#L15-L17) supplies null sessionRef/bindingGeneration. It is a bounded observed Window, not the exact conversation directory or full transcript.
- [drafts.ts:3–26](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/app/mastermind_os/src/conversations/drafts.ts#L3-L26) preserves ephemeral text across route detours by work/root/session/binding and auth generation; sign-out epoch clears. It does not supply durable drafts, source append/Undo, recipient or messaging.
- Meta-CEO uses existing decorative `atelier-office.jpg` plus scoped Noir CSS; typography directory contains real Inter/Manrope assets/licenses. Product sample names/counts are not live records. Static design similarity is not real browser/mobile/IME/a11y acceptance.

## Correct plan/contract starting point and migration

Current integration contracts are candidate:
1. `research/MASTERMIND_OS_COMMAND_BINDING_SPEC_V1.md:3–12` explicitly dates #1225 continuation and supersedes historical unchanged-controller/synchronous-store/stacked restrictions. E1 launch port compatibility exactly1.2.0/1.4.0.
2. `research/MASTERMIND_OS_EXECUTIVE_TRANSPORT_V1.md:3–43,57–88` documents fixed default-off v3 context/submit/status routes, owner1 context, original-operation uncertainty and actual host/auth/store composition.
3. `docs/runbooks/mastermind-os-public-launch.md` is current installation procedure: publication before strict-v2 admission, independent Studio verification/sealed principal-form grant, exact commission source publish/readback, public edge, Auth0/view owners, installed acceptance.

Historical `research/MASTERMIND_OS_LAUNCHPAD_CONTINUATION_HANDOFF_2026_09_26.md` remains useful for the original full journey and owner boundaries, but lines9/29–58 have stale production-binding/auth/install observations. Its source carrier #1007 and native root are historical. Add dated reconciliation, not automatic reassignment. #702/#704 remain open draft offline/freeze references, not an implementation-ready end-to-end plan.

Preserve app substrate/source/contracts/publication ownership. Migrate shell and product detail toward #1010 approved Atelier contract; move legacy access through deliberate More/advanced compatibility mapping only after source/access parity is proved. Preserve runtime lifecycle/review/transport/acceptance/source freshness as separate facts. Replace stale documentation statements with dated verified code observations after owner intake; do not replace canonical owner APIs.

## Installed blockers and safe disjoint Web phase

[Latest return5988489972](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1225#issuecomment-5988489972) reports publication + public-edge source ready; no production credential/route/service/DNS/Auth0 registration created. Remaining: authenticated DNSPod/Auth0 admin; real SPA/native clients/subjects/exact permissions; immutable launch/view binding + publication grant; exact reviewed-source install; fixed reverse-port transport credential; public DNS/TLS; authorized app launch and original-pointer lost-response/reopen. #633 original registration EFFECT_UNKNOWN remains; JOB-013 cannot be borrowed as app evidence.

[Runbook:130–141](https://github.com/mastermindx-market-intelligence/Mastermind/blob/e6f8c7ee51a886c953baa84ffbbc39e643d9b1d4/docs/runbooks/mastermind-os-public-launch.md#L130-L141) requires release/config/runtime hashes, live authenticated context/views, original pointer, exact remote commission hash/one Job/original work_ref, response loss/reopen status-only, no second publication/submit/Job, same-PR receipts.

A useful independent Web first phase is a new production plan and acceptance contract outside #1225's changed path set: proposed `docs/design/MASTERMIND_OS_PRODUCTION_PLAN.md` and a new versioned fixture/acceptance matrix in `research/mastermind_os_production_acceptance/`. Treat these as new proposed filenames, not current repo files. Map the fifteen canonical daily-flow scenarios to current code, required owner inputs, source/runtime/browser/installed proof and exact release pins; add five-nav/project-tab/context-return/entry/source-append fixtures with honest unavailable contracts. These are review artifacts, not more app implementation or runtime owners. Have #1225 owner consume the plan/matrix on its existing delivery carrier; preserve issue1056 Web enhancement owner and #1010 design writer.

Do not independently modify app/mastermind_os/**, integrations/**, ops/**, the existing public-launch runbook, the two current command/transport contracts, or tests already occupied by #1225. The complete changed-path collision list follows.

## Occupied #1225 changed paths

- `app/mastermind_os/package-lock.json`
- `app/mastermind_os/package.json`
- `app/mastermind_os/public/licenses/fonts/Inter-OFL.txt`
- `app/mastermind_os/public/licenses/fonts/Manrope-FONTLOG.txt`
- `app/mastermind_os/public/licenses/fonts/Manrope-OFL.txt`
- `app/mastermind_os/src-tauri/build.rs`
- `app/mastermind_os/src-tauri/src/auth.rs`
- `app/mastermind_os/src-tauri/src/main.rs`
- `app/mastermind_os/src/App.daily-routes.test.tsx`
- `app/mastermind_os/src/App.owner-projection.test.tsx`
- `app/mastermind_os/src/App.projects.test.tsx`
- `app/mastermind_os/src/App.test.tsx`
- `app/mastermind_os/src/App.tsx`
- `app/mastermind_os/src/compose-mission-host.test.ts`
- `app/mastermind_os/src/compose-mission-host.ts`
- `app/mastermind_os/src/conversations/ConversationWindow.test.tsx`
- `app/mastermind_os/src/conversations/ConversationWindow.tsx`
- `app/mastermind_os/src/conversations/README.md`
- `app/mastermind_os/src/conversations/conversation.css`
- `app/mastermind_os/src/conversations/drafts.test.ts`
- `app/mastermind_os/src/conversations/drafts.ts`
- `app/mastermind_os/src/conversations/observation-adapter.test.ts`
- `app/mastermind_os/src/conversations/observation-adapter.ts`
- `app/mastermind_os/src/conversations/useObservedConversation.ts`
- `app/mastermind_os/src/host.native-cancellation.test.ts`
- `app/mastermind_os/src/host.programs-observation.test.ts`
- `app/mastermind_os/src/host.test.ts`
- `app/mastermind_os/src/host.ts`
- `app/mastermind_os/src/inbox/Inbox.test.tsx`
- `app/mastermind_os/src/inbox/Inbox.tsx`
- `app/mastermind_os/src/inbox/README.md`
- `app/mastermind_os/src/inbox/inbox.css`
- `app/mastermind_os/src/knowledge/Knowledge.test.tsx`
- `app/mastermind_os/src/knowledge/Knowledge.tsx`
- `app/mastermind_os/src/knowledge/README.md`
- `app/mastermind_os/src/knowledge/knowledge.css`
- `app/mastermind_os/src/launch-config.test.ts`
- `app/mastermind_os/src/launch-config.ts`
- `app/mastermind_os/src/main.tsx`
- `app/mastermind_os/src/meta-ceo/MetaCeoOffice.test.tsx`
- `app/mastermind_os/src/meta-ceo/MetaCeoOffice.tsx`
- `app/mastermind_os/src/meta-ceo/README.md`
- `app/mastermind_os/src/meta-ceo/atelier-office.jpg`
- `app/mastermind_os/src/meta-ceo/mission-adapter.test.ts`
- `app/mastermind_os/src/meta-ceo/mission-adapter.ts`
- `app/mastermind_os/src/meta-ceo/office.css`
- `app/mastermind_os/src/meta-ceo/preview.test.ts`
- `app/mastermind_os/src/meta-ceo/preview.ts`
- `app/mastermind_os/src/meta-ceo/programs-adapter.test.ts`
- `app/mastermind_os/src/meta-ceo/programs-adapter.ts`
- `app/mastermind_os/src/meta-ceo/projection.test.ts`
- `app/mastermind_os/src/meta-ceo/projection.ts`
- `app/mastermind_os/src/meta-ceo/useOfficeProjection.ts`
- `app/mastermind_os/src/native-executive-transport.test.ts`
- `app/mastermind_os/src/native-executive-transport.ts`
- `app/mastermind_os/src/orchestration/executive-launch-command-port.test.ts`
- `app/mastermind_os/src/orchestration/host-command-bindings.test.ts`
- `app/mastermind_os/src/orchestration/host-command-bindings.ts`
- `app/mastermind_os/src/orchestration/indexeddb-pending-pointer-store.test.ts`
- `app/mastermind_os/src/orchestration/indexeddb-pending-pointer-store.ts`
- `app/mastermind_os/src/orchestration/operation-controller-recovery.test.ts`
- `app/mastermind_os/src/orchestration/operation-controller.test.ts`
- `app/mastermind_os/src/orchestration/operation-controller.ts`
- `app/mastermind_os/src/orchestration/operation-durability-integration.test.ts`
- `app/mastermind_os/src/orchestration/os-executive-host.test.ts`
- `app/mastermind_os/src/orchestration/os-executive-host.ts`
- `app/mastermind_os/src/programs-observation.test.ts`
- `app/mastermind_os/src/programs-observation.ts`
- `app/mastermind_os/src/projects/Projects.test.tsx`
- `app/mastermind_os/src/projects/Projects.tsx`
- `app/mastermind_os/src/projects/README.md`
- `app/mastermind_os/src/projects/projects.css`
- `app/mastermind_os/src/public-config.ts`
- `app/mastermind_os/src/typography/Inter-Variable.woff2`
- `app/mastermind_os/src/typography/Manrope-Variable.ttf`
- `app/mastermind_os/src/typography/README.md`
- `app/mastermind_os/src/typography/fonts.css`
- `app/mastermind_os/src/web-auth.test.ts`
- `app/mastermind_os/src/web-auth.ts`
- `docs/runbooks/mastermind-os-public-launch.md`
- `integrations/executive_mcp/server.py`
- `integrations/mastermind_executive_app/os_assets.py`
- `integrations/mastermind_executive_app/os_commission_client.py`
- `integrations/mastermind_executive_app/os_publication_auth.py`
- `integrations/mastermind_executive_app/os_transport.py`
- `integrations/studio_direct_mcp/commission-prepare.mjs`
- `integrations/studio_direct_mcp/commission-prepare.test.mjs`
- `integrations/studio_direct_mcp/commission-service.mjs`
- `integrations/studio_direct_mcp/commission-service.test.mjs`
- `integrations/studio_direct_mcp/commission_file.py`
- `integrations/studio_direct_mcp/commit-commission.test.mjs`
- `integrations/studio_direct_mcp/gateway.mjs`
- `integrations/studio_direct_mcp/git-publish.mjs`
- `integrations/studio_direct_mcp/private_service.py`
- `integrations/studio_direct_mcp/private_service_commission_test.py`
- `integrations/studio_direct_mcp/private_service_test.py`
- `integrations/studio_direct_mcp/private_service_workspaces_test.py`
- `integrations/studio_direct_mcp/workspace-access.mjs`
- `integrations/studio_direct_mcp/workspace-access.test.mjs`
- `ops/executive_os/executive_mcp_entry.py`
- `ops/executive_os/os_commission_auth_entry.py`
- `ops/executive_os/os_public_edge.caddy.template`
- `ops/executive_os/os_public_edge.py`
- `ops/executive_os/os_tunnel_entry.py`
- `research/MASTERMIND_OS_COMMAND_BINDING_SPEC_V1.md`
- `research/MASTERMIND_OS_EXECUTIVE_TRANSPORT_V1.md`
- `tests/test_executive_mcp_entry.py`
- `tests/test_executive_workspace_mount.py`
- `tests/test_mastermind_os_executive_transport.py`
- `tests/test_os_commission_auth_entry.py`
- `tests/test_os_commission_client.py`
- `tests/test_os_public_edge.py`
- `tests/test_os_publication_auth.py`
- `tests/test_os_tunnel_entry.py`
- `tests/test_studio_commission_file.py`

