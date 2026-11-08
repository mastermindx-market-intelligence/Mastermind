# Fluid conversations in Mastermind OS

Current Chairman commission: replace the form-like Hermes/DeepSeek experience with an integrated, responsive live chat client. This is product completion under WS:CHAIRMAN-CONTROL-ROOM; it does not replace either native session/runtime owner.

Operation: os-fluid-chat-20261107-c2. Procedure pin: Mastermind 58ac65ae47824750cae32c5ab85b58b6f38e6d5e, compatible Sol skillpack1.0.1. Design pin: macro ca54d30bf62d72b9381f0c4d60edede6e12a32c7. Source base: published #2180 at 486ec0275b74d8c508ca96dbe40173054b246978. This dependent source branch preserves the original #2180 and #2177 branches, active workspaces, package/UI lane and all original uncertain requests. It creates no replacement runtime, provider, message store, queue or admission.

## Diagnosis and decisions

The current Hermes panel is a vertically stacked administrative card: connection controls, purpose selector and large two-column history precede the actual transcript and composer. The transcript is capped at420px within a separately scrolling page. Send is click-only; all IO disables the composer. The adapter exposes status/list/create/read/send/receipt/recover, with a two-second receipt check; it has no incremental event view. Hermes itself already owns session event replay. DeepSeek's accepted complete native client is embedded by #2177, whose staged bundle and current consumer work are not a proven installed chat service.

Retain both native session/history/provider owners. Make Hermes a full-height conversation workspace with an anchored auto-growing composer, keyboard send with IME-safe newline behavior, compact searchable history, stable scroll anchoring, lightweight transcript rows and accessible response state. Reuse existing OS tokens and markdown renderer. Advanced connection/admission details belong in disclosure. Native observation must bind the exact session/auth generation/replay epoch and never manufacture completion or resend a prompt. Stop consumes the existing #2180 scoped original-request patch; do not independently rewrite cancellation.

## Task tree

- CHAT-1 — Reconcile exact source and preserve current writers. Read #2180/#2177 and their scoped returns. Current originals remain with their live publishers. This branch holds the separately commissioned UX extension and exact integration delta.
- CHAT-2 (CHAT-1) — Build the native conversation layout and interaction in the existing panel/view boundary. Keep permission, original-request, auth-revocation and history semantics. Verify keyboard/IME, immediate pending presentation, draft persistence during reads, scroll intent, long messages, narrow windows and EN/ZH/light/dark.
- CHAT-3 (CHAT-1) — Project real incremental native events through the existing thin port/bridge, consuming upstream replay and exact generation checks. No provider client, fake token timer, second durable store or automatic mutation retry. Verify partial response before terminal completion, duplicate/gap/replay reset behavior and logout.
- CHAT-4 (CHAT-2/3) — Compose original Stop return and DeepSeek full-client entry through their incumbent consumers. Preserve complete native DeepSeek composer/model/workspace and auth-generation cleanup.
- CHAT-5 (CHAT-4) — Focused checks and rendered desktop/narrow/theme evidence. Publish one dependent PR with current exact head and known limitations; normal protected release and original installed app lane remain distinct.
- CHAT-6 (CHAT-5) — Source-bound native package/real-path proof through the current package owner: useful reply plus follow-ups, Stop, reopen/logout/interruption. The mission stays incomplete until that actual journey is demonstrated.

## Custody and economics

Principal retains UX and cross-native integration judgment (PRINCIPAL_JUDGMENT). Native advisor is bounded read-only interaction architecture, not routine labor or a formal approval. Bounded eligible protocol work uses existing paid Fabric with the actual native original root01a1b4ca-88f6-7008-aeaf-1e6ee09320e3; no invented root, model/account pin or reviewer requirement. WHY NOT FABLE: frozen leaf contracts need no separate scarce principal.

## Completion ruler

Opening chat presents one conversation canvas and visible composer without scrolling past controls. Typing is responsive while read-only observations occur. Sending displays one original pending message immediately, then real provider text as it arrives where the native owner supports it. Reading older content does not jump to bottom. Enter sends once, Shift+Enter inserts a newline, IME composition never sends. Stop reflects the exact original owner's receipt. Switching/reopening/sign-out preserves authority and uncertainty and does not replay work. DeepSeek uses its full native client rather than a recreated message form. Test/render/source/installation/production evidence are reported separately.

Current state: source extension in progress; no installation, new native conversation, model call, cancellation, service change or production acceptance.


## Implementation checkpoint 1 — source candidate, not installed acceptance

Implemented a full-height Hermes conversation canvas, anchored multiline composer,
searchable history drawer, demand-driven Markdown, follow-at-bottom scrolling,
IME-safe Enter/Shift+Enter, editable next-message drafts, and original-admission Stop.
The Company workspace remains accessible in a separate tab, retaining its original
workflow. Native chat stays mounted when company context changes.

The existing S1 Stop patch from PR #2180 comment 6703525951 was applied exactly to
its qualified base. Patch SHA-256:
`b7b4f54bc8900de512f5c035082f713e850d55ef5ed5b1534aa1361195c0697b`.

### Live projection decision

The native adapter now reads the existing `session.events.since` ring on one finite,
foreground connection and sends projected snapshots over a Tauri Channel. It never
calls session.resume/attach, starts a service, stores cursors, resubmits a prompt,
or owns a native session. The view pipe is capped at 600 seconds, 256 KiB displayed
text, 300 KiB per frame and 16 MiB host traffic. Disposal kills only the read helper.
Original prompt cancellation remains exclusively the existing Stop operation.
The read pipe does not acquire the foreground send/Stop mutex.

Native receipt, authority epoch, execution generation, replay epoch, event sequence,
turn/segment and UTF-16 offset qualify displayed text. Gaps stop projection; the UI
retains original-request recovery. Raw reasoning, tool arguments and results do not
cross this projection. Sign-in is checked before spawn and every frame release.
A terminal stream notification never clears the durable pointer: the incumbent
recovery/receipt path must reconcile it, then canonical history replaces the preview.
Frames are rendered at most once per animation frame. No artificial token animation.

Paid Fabric audit `os-fluid-chat-stream-contract-20261107-c2-01`, rooted at
`01a1b4ca-88f6-7008-aeaf-1e6ee09320e3`, returned RC 0 with exact response SHA-256
`69ec914d6c2bc6b6e78ba2d3f99f447d65843b4831ddc1c601d762e3a7243b19`.
Its association, bounded output, auth and reader-position constraints were applied.
Its recommendation to spawn Python for every batch was not adopted: inspected
upstream `gateway/session_controls.py::events_since` requires only `session:read`,
not a resumed attachment. A disposable finite read pipe is not a session/service
owner and avoids repeated Python startup and send/Stop contention. This is principal
implementation judgment, not a formal GitHub review. Fabric acceptance recording
encountered request-validation errors; no accepted receipt is claimed yet.

### Verification recorded at this checkpoint

- TypeScript typecheck passed before the final small rendering refinements.
- Existing Hermes UI/native-port suites: 50/50 passed.
- Live-frame and channel-boundary suites: 14/14 passed.
- Combined controller/live suites after added draft/IME cases: 36/36 passed.
- Bridge and native event projection suites: 51/51 passed.
- No packaged Mac compile, real provider streaming, installation, browser visual
  acceptance, or production acceptance is claimed by this checkpoint.

### DeepSeek native composition finding

PR #2177 is active at `6d40c628678ebb086d67677511eb8c4ee4588f3c` (previously
`0f01a4e3dfe3bcd1510feda46e1da711bc5d0f4f`). Its full-app iframe intentionally
rejects native mode and pins the real company HTTPS parent. Do not partially copy
or weaken that integration. The minimal native addition is a separate fixed-origin
`deepseek-chat` WebviewWindow using the complete incumbent client. It requires
explicit AppManifest command permissions, local-main-only grants, navigation/popup
fences, OS signout cleanup, and remote-command denial proof before release. The
existing deployment must supply its private launch authentication without a new
credential store. The public route and listener were staged, not proven installed.

### Exact next steps

Compile this source candidate in an isolated admitted Mac workspace; verify the
actual view at desktop/narrow widths, both themes, history and scroll behavior;
implement the bounded DeepSeek native entry without weakening iframe/auth guards;
then compose only pinned upstream commits for installed real-path proof. Preserve
active #2180 packaging/UI and #2177 native-reader writers. No merge, deployment,
provider call, or replacement of their installed candidate is authorized by a test
pass alone. The Chairman's requested product outcome remains open.


## Checkpoint 2 qualification in progress

The admitted Mac source workspace is `/Volumes/Mastermind 2/agent-workspaces/web/os-fluid-chat-20261107-c2`, created by the incumbent workspace helper at f2da65acbf6955430bd2aea2f9ca55297b0d32f7. Initial acquire failed before application because its Git source lacked the new commit; fetching the exact published commit resolved this. No original writer checkout or running app was changed.

`cargo check --locked` passed at f2da65ac (53.81 seconds, 14 existing warnings), using a compile-only identity. No app was launched. Current entire Hermes frontend suite: 75 tests passed. Current native bridge/stream suites: 51 tests passed. Subsequent changes below need their own final check.

A refreshed #2180 source head ad3487fab3b16c8ed9c6a221a8160fdfc0cbbf79 identified a material S1 Stop race: another view can settle A and admit B in the same session before a stale button is clicked. This candidate now binds Stop to the displayed request/session tuple before atomic cancellation reservation. A changed durable target is refused without invoking or reserving cancellation. New regression coverage proves B remains untouched. This is required before consuming the older S1 patch; its earlier test results alone do not establish safety.

The DeepSeek native delta opens/focuses only the fixed complete application in `deepseek-chat`, with an explicit local-main caller check. It enumerates every application command under the Tauri AppManifest ACL; only the local main webview receives the application permission set. Remote views receive no capabilities. Navigation stays on the exact HTTPS chat origin, popups are denied, and the existing auth owner closes the private view when generation/sign-in changes. The existing local CSP and #2177 native iframe rejection remain intact. Generated-resolver tests and Mac compile remain required before release.

DeepSeek window creation is not connection/provider proof. The public route is still a candidate and the existing app must issue its private launch authentication into that webview's origin. No token is embedded, copied into source, logged, or stored by this native entry; no alternate auth broker or provider client was added. Source remains unaccepted for production until that existing deployment/login path is qualified.

The original #2180 packaged UI now has an exact interactive sign-in gate: candidate486 signed out, and its next browser sign-in did not complete. Original new-conversation request9fbc8f4abb944ab1a170b4990e59f729 committed to its native session but its UI recovery remains held. Do not alter its pending pointer or replay its creation. The current commission has made no provider send or stop call and has not replaced that running app.


### Source checkpoint 2 verification update

- Production TypeScript/Vite build passed after the native entry and Stop-target fixes.
- All native Python OS suites passed: 59 tests (bridge, history, stream).
- Command inventory/capability tests passed: 2 tests.
- The shared dev fixture renders the actual Hermes panel with explicit fixture event controls, never a fake provider or production entry point. `dev/hermes-chat.html` is not included in the production build.
- Visual verification remains open: the connected browser extension lacks its originating browser context; the separate cloud browser cannot reach the scratch loopback server. A shared-file preview was rejected by the cloud browser URL security policy (only HTTP/HTTPS permitted). That action was stopped; no bypass or alternate file-protocol route was used. No rendered acceptance or smoothness measurement is claimed.
- The source-only DeepSeek native view and generated ACL tests still require their next exact-head Mac compile/test. The public app installation and its existing private launch/sign-in path remain separate, unproven dependencies.

The company workspace key now retains the incumbent auth/selection/session/binding lifecycle and excludes routine source revision changes. A focused render regression passed: drafts survive tab changes and source refresh, company drafts reset on selection change, and native drafts clear on auth change. DeepSeek auth withdrawal hides and force-destroys its view; failed destruction retains the original generation fence and cannot refocus/reuse it under new authority. This closes an ignored-close-result privacy gap before qualification.

The latest inspected DeepSeek source is b4bb540aa8248ae1408daa6dc4ff6af749659797. Its native read port provides bounded read projections over an already-owned socket pair, not a private-launch/authentication capability. The accepted deployment owns the private launch cookie ceremony; this branch will not scrape private service logs, add a broker, or repurpose that read port.


## 2026-11-08 recovery and released-base composition

The interrupted source-tree construction did not advance the original branch: GitHub and the admitted Mac workspace both read back 91459b44b0560f22894594f1ef38a506649ea38f. No commit/ref publication or installation from that interrupted construction is claimed. A possible unattached immutable tree object has no source-release receipt and was not replayed. Scratch expired; all published source and the admitted Mac checkout remained intact.

PR #2180 is now protected-merged as 72eee6155c8e6c3c7e9c4e82a1e28f2d3ca392c7. Its installed source6e package, normal sign-in, original request reconciliation and exact original answer are accepted in that PR's canonical receipts. The earlier login/pointer hold in this document is historical and resolved. Do not repeat that acceptance or reinstall its package. New live-stream, Stop, layout and two-window acceptance remain owed by this commission.

Protected master b230c2b07db4c895dcccb16a3b0f0822eefc3a6b is the current composition and law pin. INDEX remains compatible1.0.1/bootstrap1. The only changed applicable procedure file since58ac is BOOTSTRAP_KERNEL; it was read at this same pin. The remaining previously read applicable laws are byte-identical.

This composition retains current master’s exact completed-login timer repair, singleton main-window reopening, qualified ADVISORY_READ_ONLY Hermes adapter/interpreter checks, captured Company work/journal/priorities readers, PLAN source recovery and current CI/archive gates. It adds read_company_priorities to the local-main command inventory. Explicit Dock Reopen restores main even when the DeepSeek window remains visible.

The incumbent pointer store now discriminates both published v15 formats by kind and closed key grammar: native reserved Stop and PLAN source publication. No record renumbering or replacement store is introduced. A regression exercises persisted reopening of both formats, cross-kind rejection, principal binding and refusal to reserve Stop for a PLAN pointer.

Native cargo check --locked passed on91459b44 (8.07 seconds,14 existing warnings). Its first ACL test compile exposed duplicate macOS Info.plist embedding from two generate_context! expansions. The composition uses one shared generic application_context function for production and the actual generated ACL fixture; next exact-head compilation/execution will qualify this repair.

DeepSeek #2177 remains open at b6692a5ced2c66c735ab51a15df424cac2a0be9a. Its full client and native provider setup have extensive fixture/browser evidence, but public ingress and actual provider sign-in/production acceptance remain open. The native setup entry does not claim those effects or repurpose the read-only C4 port.
