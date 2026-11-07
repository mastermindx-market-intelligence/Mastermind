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
