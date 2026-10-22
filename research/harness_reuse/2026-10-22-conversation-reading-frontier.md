# DeepSeek-derived conversation reading — continuation frontier

MISSION_COMPLETE: false. This is a tested application-source contribution, not an installed conversation service or production acceptance.

## Mission and exact source

Chris's continuing mandate is the full Mastermind OS / Agent OS harness upgrade, including useful project conversations and sessions. Preserve the existing programme, ACP integration and Session Bridge; do not substitute a second chat runtime.

Procedure pin: Mastermind protected `d31aade92b969e8897513d8634ecd59dba00e1e3`, Skillpack1.0.1/bootstrap1. Protected movement inspected through `b95385f6c455411e76bffbb9fcdcbec7a6fe0eae` is disjoint from this client and governing source. Existing first slice: PR1723 at `0cdb2360992918c06aaf5a4b1bebd3458fea29cf`.

This continuation's registered operation is `deepseek-conversation-reading-20261022-web-001`, branch `sol/web-deepseek-conversation-reading-20261022-web-001`, workspace `/Volumes/Mastermind/agent-workspaces/web/deepseek-conversation-reading-20261022-web-001`, acquired from that exact first-slice head. Keep this dependency explicit until PR1723 lands; do not duplicate or overwrite it.

## Capability delta

Before: the actual ConversationWindow rendered each owner-visible response as a plain paragraph with no window search, copy control or reader-follow policy.

After: its qualified, bounded visible window is connected to ObservedTranscript. It searches only the supplied visible responses, optionally formats them with the existing inert Markdown renderer, copies exact supplied text only on explicit action, and preserves reader position when content grows. A deliberate jump returns to the latest observed response. Partial/completed labels remain source data, not inferred worker lifecycle.

The new scroll controller is copied byte-for-byte from DeepSeek commit `687f282e8625c6b8d11ff58211a90524be2e4317`, path `packages/client/ui-chat/src/client/chat/use-scroll-follow.ts`, SHA256 `fd0734320e326292e614991476c1ffe492a40b90e44534b47a0368528a9415f0`. It is the third pinned client module, with the existing MIT license/distribution closure. No new runtime dependency was added.

## Boundaries enforced

- Full conversation history and exact session identity are not inferred from an observed window. Search explicitly describes that scope.
- Withheld content is neither searched nor copied, including contradictory display props. Withheld rows retain source order.
- Missing/foreign/auth-changed source still withdraws the reader through existing qualification. Search and formatting cannot send, change notes, invoke a result read, load remote images, navigate links or create browser persistence.
- Authoritative window epoch/source/Job/Attempt changes reset transient reader state. Passive same-source updates preserve the query. The original continuation slot remains outside that lifetime.
- Copy feedback is bound to the exact text instance; denial is reported and old asynchronous completion cannot affect changed source.
- The upstream controller owns view-follow intent only. It does not implement sessions, events, retries, lifecycle or history.
- The existing #1362 consumer patch was checked in an isolated temporary index against exact `dd9f1bbc61a5413b09d98edea7ff81f0f72427b1`. Import context was separated from its held imports; final check passes without changing its branch/workspace. This is patch compatibility, not approval of that bridge.

## Executed evidence

Full frontend campaign: 1,745 passed, one existing skipped, 79 files; 41 new cases compared with the first slice. The first focused run passed 80 cases; the added actual-ConversationWindow integration cases are included in the full run. TypeScript and production Vite build pass. Existing provenance checks pass with the closed third-module allowlist.

Compiled Chromium fixture: desktop1440x1100 and mobile390x844; dark/light plus Chinese-mobile capture; real ConversationWindow, real qualification/reader components, synthetic source only. Reading scrollTop remains200 after appended content; explicit jump reaches the measured bottom and focuses the region. Search leaves unsent notes intact, source epoch clears the query, and withheld source withdraws the reader. No document overflow, page errors, external requests, real SEND/provider execution or parent-consumption claim.

Evidence is under `research/harness_reuse/evidence/2026-10-22-conversation/`. Reproduction uses `vite.conversation-proof.config.ts` to compile an isolated fixture, then `tools/qualify_conversation_reading.py` against a dedicated loopback origin. The normal production build remains `index.html`; fixture artifacts are separately ignored and must remain excluded from delivery.

An earlier browser attempt observed a stale Vite-transformed fixture despite corrected filesystem source. This was not accepted proof. The final successful campaign uses freshly compiled fixture bytes and separately validates the coherent source revision. No production qualification guard was weakened.

## First-slice release and original holds

The original PR1723 CI observer PID67383 completed exit0; all11 exact-head checks passed. Its clean original workspace was preserved. Normal fenced queue entry succeeded: `MQE_lQDOTotz3c8AAAABJ_RyVc4ABAiKzgNrDPw`, position1/QUEUED at observation, head unchanged. Queue entry is not merge, deployment or acceptance. Source assessment is recorded in PR1723 comment6338306873.

#1196 remains the original ACP source carrier, including its unpublished dirty files and retained tested proposal. The missing Task2B materialization consumer is still a real blocker. The read-only custody probe initially lacked its required authentication environment. A subsequent credential-bearing probe was blocked by platform safety checks before dispatch; no alternate tool, credential route or replay was attempted, no current gate success is claimed, and no ACP source was changed. Preserve the earlier RCH/technical-writer holds rather than treat old author labels as proof of current availability.

#1362 original review/admission restriction, #1515 occupied/refused source, and the installed host/Content-publication/canary constraints stay on their existing carriers. This source slice grants none of them. No worker was dispatched or replaced. Direct implementation used the current authorized host/source surface; no eligible paid-Fabric submission action was exposed in the connected tool catalog, and the existing Executive admission remains separately governed.

## Exact next actions

1. Consume PR1723's actual protected queue outcome, preserving the original head and required integrated checks. Do not bypass or manufacture a release.
2. Publish/review this exact registered continuation, bind its hosted checks, and integrate the first-slice squash only when an actual semantic ancestry conflict requires it. Preserve the tested postimage rather than copying another branch over it.
3. Deliver this bounded source result to the existing ecosystem programme and Agent OS. Publication is not receiver pickup or runtime consumption.
4. Resolve the existing bridge, Content producer/publication and ACP custody/materialization gates on their original carriers. Then prove the authenticated project/session -> single governed send -> native work -> original reply -> evidence -> original-parent consumption/reload journey. More presentation cannot substitute for that proof.

## Capacity and current-design qualification amendment

A maximum-sized synthetic window exposed a real eager-formatting amplification: 256 rows,
1,025,757 source bytes, and 255,510 formatted descendant elements. The observed all-response
format/render time was3.331seconds. This is a local measurement, not a production SLA.

The same original PR1727 now defers each response's rich parser until its actual scrollport
intersection or deliberate per-response request. Exact raw source remains readable, searchable
and copyable before formatting. Browsers without IntersectionObserver use explicit per-response
demand rather than eagerly parsing every row. Source withdrawal disconnects old observers.
This is lazy display admission, not a new history store or network/source permission.

The repaired compiled fixture initially renders two rich responses/2,004 descendant elements,
leaving253 response previews deferred. An offscreen response formats on actual scroll; returning
to exact-source mode restores all1,025,757 original bytes. Timings and exact final counts are in
capacity-proof.json; they measure first-visible rich content, not all-response completion, so
never report an equivalent-work universal speedup. Full source suite:1754PASS/one existingSKIP,
80files; nine new demand-driven tests. TypeScript, final normal build and compiled desktop/mobile
browser proof pass. Visual inspection also found and repaired the deferred wrapper's grid
minimum-width issue; browser qualification now asserts both document AND internal transcript
horizontal-overflow absence. Tables/code retain their own deliberately scrollable containers.

Current Paper reference was recovered through the direct read-only Paper app, not an unrelated
open market file: Mastermind OS file01M3NRCX55B452A12819WNE1RH, Chat Atelier pagep-C-0,
CH1desktopIZB-0 and CH6mobileK5X-0. Both real screenshots were inspected; tokensf3c5ac93 and
catalog1b9afff4c9bcf6f11f5ca2db301bf25ccdc442025344e2ec402459cedcd6a2db were observed.
The implementation retains the existing Noir/Manrope/Inter theme and44px controls. This source
reader is not the complete designed conversation directory, authenticated sender or native-send
experience. No Paper content or focus mutation occurred, and prior KD01/UX09 unknown edits were
not replayed or declared reconciled. Full recipient/session and source-origin actions still need
the original runtime qualifications before the complete CH1/CH6 journey can be claimed.
