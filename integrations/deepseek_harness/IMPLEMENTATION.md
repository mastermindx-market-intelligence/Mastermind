# DeepSeek and Mastermind OS chat delivery

Operation: `deepseek-mastermind-chat-20261106-c2`.
Chairman assignment: finish DeepSeek integration, the Mastermind OS UI, and usable chat.
Source base: `af18454f0cd2086c7976e55e16fee1d8dd70f405`.
Branch: `sol/web-deepseek-mastermind-chat-20261106-c2`.

This is the implementation continuation of #687/#1037/#1142 and the merged full-application
pilot #1717; it does not replace their product requirements or the existing
`docs/superpowers/plans/2026-09-27-selective-harness-reuse.md` task tree.
The current integration contract is `integrations/deepseek_harness/README.md`.

## Product acceptance

An authenticated user opens the accepted Noir Atelier interface, chooses the correct
project/conversation, sends an explicit message once, reads a useful response, continues
the same conversation, and can recover the original conversation after navigation or
reconnection. Permission loss clears protected content. Unknown effects retain their
original request; no blind resend, alternate provider or synthetic target is introduced.
Retain the full DeepSeek app's native session/stream/render/plugin capabilities beneath
Mastermind's existing company authority and capability owners.

Paper design: file `01M3NRCX55B452A12819WNE1RH`, canonical page `p-D-0`,
conversation page `p-C-0`; CH1 `IZB-0`, CH6 `K5X-0`, CH91 `KDN-0`,
CV01 `SD8-0`. Existing app tokens and approved source design contracts remain controlling.

## Current blocking facts

- Full donor pilot #1717 and governed MCP proof #1790 are merged; do not rebuild them.
- The current attended fresh-conversation flow intentionally permits only one follow-up.
  Its service waiter, immutable request/reply records and UI all encode that ceiling.
  Removing UI text alone cannot implement multi-turn chat.
- The current Executive V3 session target read returned an empty list. This is a current
  target-availability observation, not permission to create target identities.
- Studio Paper inspect/catalog/exact-file reads returned INVALID_ARGUMENT; the independent
  Paper read carrier's inspect/catalog returned the same technical error. No Paper edit
  was attempted. Use preserved accepted design contracts until exact live reads recover.
- The original donor checkout is clean at `687f282e8625c6b8d11ff58211a90524be2e4317`.
  Keep that checkout intact; owned integration source belongs in this repository.

## Delivery nodes

| Node | Work | Acceptance |
| --- | --- | --- |
| CHAT-1 | Complete the existing conversation UI and continuation composition | Real mounted message/response/continuation journey; draft and unknown-request recovery preserved |
| CHAT-2 | Complete the donor app's company integration seam using its supported plugin boundaries | Actual pinned donor registration and UI mount, existing project/session owners, no parallel auth/session/company lifecycle |
| CHAT-3 | Connect eligible existing runtime and provider routes | Actual admitted original request, useful response, same-conversation follow-up and settled resources |
| CHAT-4 | Publish and release through the existing protected path | Exact source/CI, installed build identity, signed-in desktop and mobile user-path proof |

Every node retains its source versus runtime proof ceiling. Deliver useful code slices,
consume short validation in this session, and advance the next safe node without another
Chairman approval. Do not waive actual source-writer, permission, unknown-effect or
protected release controls.

## Execution ownership

The attended principal owns architecture, integration and product acceptance.
An existing native reasoning child supplies cross-system architectural judgment only.
Use admitted economical Fabric for independently bounded implementation where it improves
the completion cycle. Parent direct integration is justified by PRINCIPAL_JUDGMENT and
CRITICAL_PATH_SHORTCUT while interfaces are being resolved, not as a substitute native
labor pool. Preserve one modifying carrier per operation and disjoint worker paths.

## Verification and durable return

Run focused tests that discriminate changed message/continuation, auth invalidation,
duplicate-send and recovery behavior; build the actual app; inspect desktop/mobile and
dark/light layouts. Required hosted checks remain release gates. Record exact changed
source, commands/results, provider/runtime observations and remaining original-scope
obligations here at material milestones. An isolated fixture or merged source alone is
not production completion.

## 2026-11-07 implementation milestone

Implemented source on this branch:

- Full DeepSeek application consumer under the existing Conversations destination,
  with preserved Project conversations, keyboard tabs, EN/ZH presentation, existing
  guarded project navigation and authentication-generation remount.
- Original Cordis company plugin using the pinned donor's actual module loader,
  snapshot store and supported slots. Searchable projects, shared locale/theme and
  Noir tokens; native chat/session/workspace owners remain intact.
- Exact-origin/source/nonce/generation company presentation bridge, including
  revocation and reload behavior. No token, provider grant or command is forwarded.
- One sealed-index build input for both the frame URL and exact Executive CSP.
  A missing qualified install retains the existing journey. Configured native
  builds explicitly refuse the unqualified web host.
- Closed 12/14-file release profiles for the current OS sign-in image, repairing
  the previously unsealable actual 12-file production build.

Observed verification:

| Check | Result |
| --- | --- |
| OS typecheck | Passed |
| Targeted OS integration and bridge suite | 14 passed |
| Final frame/native-copy/source-link component check | 4 passed |
| Production OS build, default and configured fixture | Passed |
| Current actual build through closed asset manifest | 12 files; sign-in image included |
| Python embedding and asset-layout suite | 74 passed |
| Compiled plugin through actual pinned Cordis SlotRegistry and renderer | 1 passed; project rendering, appearance and revocation |
| Full pinned donor web boot with compiled plugin | Authenticated local HTTP 200; plugin and native boot present |
| Local donor after preview | Clean at accepted pin; owned preview stopped; original port closed |

The configured origin in tests is a fixture, not a live installation. Native
rendering uses the actual donor renderer with explicit test theme/locale services.
The local app boot uses the existing credential-clearing launcher and no provider.
The observed deployed browser remains the previous signed-out build; no
production upgrade, signed-in acceptance or useful provider reply is claimed.

Current live blockers are specific. Executive V3 session targets returned an
empty list, and the installed Executive reader returned backend_unavailable on
2026-11-07. Control, Codex worker and MCP launchd services are running against
release `b4a5a8925c6c1412dac67ba296cf65ee81c4d4c8`; that release still declares
ACP `implemented=False`. The currently accepted paid GLM profile is one sealed
model-only worker request with `stream=false`. That restriction governs paid
worker execution; it is not a prerequisite for ordinary attended native chat.
The complete donor already contains native DeepSeek account/API-key providers,
streaming, history and model settings. Preserve those owners. The current-donor
Agent/ACP adapter is separately qualified below; no worker route is enabled.

Original paid Fabric operation `deepseek-mmos-multiturn-20261106-c2-r1` (root
`deepseek-mastermind-chat-20261106-c2`, controller PID 27072) had no verified
START while waiting. At 04:43 UTC its original controller became VERIFIED_TERMINAL with rc=1.
The exact retained response reports `unrecognized_model` for `MiniMax-M3` during
`generate_session_title`, followed by `PROVIDER_TERMINAL kind=permission rc=1`.
No accepted source result was returned; retry remains false and execution
absence is not established by the projection. Do not replay that provider action
on another model/carrier or treat it as an accepted implementation. Its separately
assigned fresh-conversation paths remain outside this source tranche.
This does not qualify as durable execution running or as completed DSH chat.

This UI tranche is published in PR #2177. The continuation adds the persistent
native package and current-donor runtime compatibility below. Final acceptance
still requires a useful provider response, same-conversation follow-up,
stop/reconnect behavior and the signed-in deployed desktop/mobile journey.

## 2026-11-07 native runtime and attended package milestone

The full-app source at donor `687f282e8625c6b8d11ff58211a90524be2e4317`
now has reproducible, hash-bound compatibility patches outside the clean donor.
Strict dispatch retains native staged scheduling and original result ownership;
governed MCP generations retire before replacement, refuse stale/rich results
before materialization, and disable the SDK schema retry. The known fixed Python
ACP reader uses explicit legacy negotiation without a speculative sibling.

`dsh_native_agent.mjs` mounts the admitted tools into the actual existing native
Agent. The original inherited-FD v2 ACK completes before model work. Agent-owned
restrictions remain after MCP revocation. It creates no second Agent, provider,
session, retry, execution, result or process owner.

Verification at this milestone:

| Check | Result |
| --- | --- |
| Current-donor dispatch/MCP compatibility | 42 passed |
| Real current native Agent → ACP v2 → source workspace reader → common result | Read and observed-query search passed; three deterministic model rounds, actual returned bytes |
| Revocation and owner abort | Second call refused; inherited sentinel stayed hidden and unexecutable |
| Cancellation | Original native child and adapter tasks settled |
| Wrong tool contract | Refused before model work; conservative adapter classification preserved; child cleanup proved |
| Native process suite | 5 passed |
| Persistent attended package | Staged 116,144 file/link entries; complete native app rebuilt with Mastermind title and company plugin |
| Package identity check | Passed with exact Node and internal dependency closure |
| Generated public Caddy candidate | Adapted and validated by installed Caddy 2.11.4; no route installed |

The native fixture uses a deterministic provider and explicit ephemeral test
persistence, with a synthetic registry projection. It does not qualify a paid
provider, durable native JSONL persistence, the missing fixed installed MCP
launcher, dedicated UID containment, or installed ACP activation. The attended
package instead retains the complete app's actual native persistence, credential
and provider implementation.

Staged release:
`/Users/chriswong/Library/Application Support/Mastermind/DeepSeek/releases/dsh-687f282e-company-20261107-c2`.
Persistent state:
`/Users/chriswong/Library/Application Support/Mastermind/DeepSeek/state-20261107-c2`.
Package manifest SHA-256:
`6de31eb746e98b32c6f0a7af3f94cff22befd6e6d93f7dcc1a19f7ee4d075448`.

The package provides a native launcher, launchd definition, public-edge candidate,
and matching sealed OS build input. Its immutable company CLI overlay is separate
from editable native profiles, so normal model/settings changes survive restart.
The package has not been installed into launchd or connected to public ingress.
The candidate `chat.mastermind-x.com` had no DNS address in the observed lookup.
A separate DSH listener grant must use the incumbent transport/publication owners,
rather than reusing the closed OS or Fabric application slots.

The first hosted PR run passed ordinary build/test/native checks, but CodeQL
identified a URL substring assertion in the CSP test. The assertion now compares
parsed directive tokens exactly. No check suppression or rule change is used.

The owned package then completed all seven native artifact-build stages using
pnpm 11.28.5, with 325 client artifacts and the supported `DSH_CLIENT_TITLE`
value `Mastermind`. The native package manager relinked the copied dependency
tree from its unchanged lockfile before building. The original donor was not
rebuilt or edited. The company hero now uses its supported brand-mark slot.
Company client SHA-256:
`9434bc422db55f45f028f874fe5cd791f472999a83c6167203c99a112bf454d3`.
Native client build record SHA-256:
`c7c7f3b387231d72e42b0d9addbbc7b6ed00f1752405c9c04dc177fb4d829439`.

A real local Chromium visit to the packaged app proved the native launch-token
exchange, clean redirected URL, unauthenticated 401, authenticated 200, loaded
Mastermind company plugin, native session composer/workspaces/model controls,
and no page exceptions. Desktop and mobile screenshots were captured privately.
The original app process stopped with exit 130. This is local browser evidence;
it makes no claim about public DNS/TLS, a provider response or installed service.

The branded rebuild was visited again in Chromium at desktop 1440×1000 and
mobile 390×844. Its document title is `Mastermind`, both native branding slots
are mounted, the preview acknowledgement saved through native settings, and the
actual provider setup UI offers `Add API Key` and `Sign in`. No account was
signed in and no provider request was sent. The new process again settled at 130.
The final company-plugin native-render test passed after the hero-slot addition.

A further native process restart preserved the saved preview acknowledgement
(`firstRunNotice=false`) with the same persistent state, reauthenticated cleanly,
rendered the Mastermind title without page exceptions, and stopped at exit 130.
Provider setup remained explicitly unconfigured; no successful answer is inferred.

## 2026-11-07 complete ingress source milestone

The native attended app now has its own closed Chisel purpose through the existing
application transport owner: VPS loopback 4181 to native M2 loopback 4180,
identity mastermind-deepseek-app, and its own config, credential, journal and
launchd label. The OS and Fabric targets retain their original identities and
ports. Both application purposes take the same authfile lock before their own
operation lock. An unresolved peer operation blocks a new grant mutation;
read-only reconciliation of the original operation remains available. A settled
grant can be observed after an additive peer update without rewriting its
historical receipt or claiming a server reload.

The exact chat.mastermind-x.com site is added as a sibling of the existing OS
site by a pure planner. It preserves the complete existing configuration and
refuses ambiguous hosts or TLS authority. The existing Caddy publisher now owns
the DSH stage through the same durable intent, full-config ETag, conditional POST,
readback and receipt transaction. No parallel publisher, DNS owner or restart
owner was introduced. Lost acknowledgement remains a reconciliation condition.

The bounded app export reads attended-build.json from protected source, verifies
its pinned complete package manifest, reads the full closure with file/link/
directory identity checks, and captures the actual native script and stylesheet.
It carries only bounded root-owned snapshot evidence to the edge. It does not
attest that the user application has been installed or that provider auth exists.

Focused evidence:
- Isolated Linux root transport fixture: 162 passed, zero skipped.
- Existing OS plus new native publication suite: 80 passed. Subsequent TLS and
  protected-build refinements: 17 native publication tests passed.
- Bounded package export: 3 passed, including forged local-manifest rejection and
  non-asset drift during capture.
- The installed Caddy 2.11.4 binary accepted the exact native candidate JSON.
- Current full-app native Agent/ACP and fresh-process JSONL history proof:
  7 passed. The native platform addon is verified and copied into the fixture;
  a second native writer is refused while the original writer is retained.
- Legacy profile compatibility repair: 19 positive cases and 4 mutation controls
  passed. The original native profile artifact builds successfully. These repair
  hosted failures caused by a scope-only dependency and a stale mutation target.
- All ordinary hosted pytest shards, frontend, native-macos and CodeQL passed
  on d2a41e2cc78ad247e42efdfcfa7be740a9f7e017. The repaired specialized MCP jobs
  still require hosted results on the next source head.

Actual access observation: the existing default SSH identity for 146.190.142.17
was refused with Permission denied (publickey). No alternate user, key, carrier
or retry was attempted. No production ingress, DNS, launchd or provider effect
is claimed. The earlier Fabric multiturn operation is terminal with a provider
permission refusal and has no accepted implementation return.

The real packaged native app also passed the new ingress probe on its own M2
listener: unauthenticated root 401/no-store, exact packaged JavaScript and CSS
200 with matching hashes and MIME types, and original child exit 130. This
caught and corrected relative index asset URLs in the exporter. It sent no
provider request and did not traverse the VPS/public route.


## 2026-11-07 sequential project-conversation milestone

The separate Executive project-conversation consumer no longer closes after one
follow-up. It retains its existing admitted native writer, original root/child,
Attempt, initial seal and consumption receipt. Each next message gets its own
immutable request and native turn; the latest settled request/reply pair is bound
into preview and rechecked inside reservation. Duplicate keys read the original
outcome, changed content conflicts, and unresolved or explicitly unknown turns
cannot admit another send.

The existing service rearms its continuation before waking the HTTP caller. Its
fresh-conversation branch is selected from original admission, so ordinary Wake
ACKs cannot be replayed into that waiter. Idle expiry completes even initial-only
conversations through ordinary cleanup, with 120 seconds reserved from the
current lease for cleanup. Only a newly qualified request extends the lease.
Shutdown closes admission before cleanup and wakes a reserved request through
its original journal, including cancellation before execution or just after a
reply commit; delivery failure never invents a provider-unknown marker.

The original history reader now serves v2 bounded pages on its existing
fresh_read route. Cursors are separate from immutable reference identity. The
initial page always retains the complete initial envelope for Keep recovery;
older pages retain its validated digest and complete reply envelopes. Pages use
the actual compact UTF-8 byte budget, exclusive descending event cursors, at most
eight rows and the existing 28,000-byte source limit. Legacy v1 UI/transport
readback remains accepted. Native DSH JSONL storage remains its separate original
owner; this Executive projection creates no new transcript or session store.

The UI retains confirmed replies above the next-message composer, clears only
the exact confirmed sent draft, mints a new key for the next reviewed message,
and keeps unresolved requests on their existing recovery controls. Project
history loads earlier messages without retiring the issued initial witness.
After a settled send, the open original refreshes in place. Full initial replies
that occupy a page trigger one recent history-page read as part of that same
Open/Send gesture, so the latest complete response remains visible.

Observed evidence:

- Signed HTTP/Runtime focused continuation cases: 25 passed across the final
  24-case result and the corrected consumption fixture rerun. The latter allows
  60 seconds for fixture Create under the observed busy M2 host, while exercising
  the unchanged production admission and independently shortened test idle wait.
- Initial response plus three consecutive follow-ups: two Jobs, one Attempt,
  one native start and four native turns. Duplicate sends add no Events or I/O;
  stale-tab preview is refused. The initial seal stays unchanged.
- Near-16-KB Unicode envelopes survive complete paged history and post-cleanup
  reads, and consume_status still recovers the original receipt.
- Early reader closure, pending-key concurrency, expiry, source/writer changes,
  lost returns, initial-only idle completion and cancellation around reply commit
  retain their original recovery identity.
- UI continuation, original-window, history, decoder and panel suites: 72 passed,
  including three successive messages, draft reset, all replies retained,
  issued-cursor enforcement and late authorization withdrawal.
- OS full TypeScript project build and production Vite build: passed.
- On published predecessor 0506ed5, both previously failing specialized MCP
  workflows passed, together with hosted frontend/native and CodeQL checks.

These proofs use explicit inert provider/host seams where stated. They do not
claim an installed Executive upgrade, signed-in production chat or a useful live
provider answer. The exact VPS SSH refusal and unconfigured native provider
remain deployment/account gates; no alternate SSH identity or paid-worker replay
was attempted.

## Native history and command admission follow-on

Commit `d5d1232ebdfbe048d5f4403ceeb04832b8d3330c` adds a private company
history reader over the donor's actual Connection/Gateway and original
projection/page services. Six native cases qualified cold recovery under an
existing writer lease, exact-session refusal, authority retirement, caller
cancellation and unchanged stored bytes. The compiled company client remains
`9434bc422db55f45f028f874fe5cd791f472999a83c6167203c99a112bf454d3`.

The additional pinned native session patch propagates operation cancellation
through the original controllers, shared resume map and supported creation-only
factory signal. It checks prompt admission before the original inbox write,
Stop on the actual Gateway service view, and follow before cold-writer promotion.
Eight focused native cases passed, including both regressions reproduced against
the unchanged donor. The donor-strict host TypeScript program plus company
reader reported zero diagnostics. No original donor checkout was edited.

The existing attended packager now applies that patch in its owned app copy
before the upstream build and binds its receipt, manifest and compiled private
host reader. Eleven focused real-file packaging/export cases passed, covering
partial effects, redirected paths, exact protected source and stale host output.
The package qualification at this phase remained tied to its earlier staged
bytes. The later independently qualified package is recorded below and in the
[exact join frontier](NATIVE_COMPANY_JOIN_FRONTIER.md).

## Exact-original recovery and bounded presentation

The follow-on UI repair uses the exact committed original read and a fresh read
of the incumbent pending-operation store. An idle controller after remount may
release the composer without being changed to accepted. Unknown controller
state, failed hint reads, and any newer pending pointer remain held. The current
App draft's submitted key precedes remembered display state after an actual
pending pointer has been reconciled, so recovering a later turn cannot strand
an earlier still-unsettled App submission. No automatic resend or pointer clear
was added.

Canonical history navigation displays one complete page while retaining the
original continuation witness. Return to latest uses the existing reader.
Confirmed local presentation retains at most eight complete entries and 65,536
UTF-8 bytes; older replies remain with the canonical history owner.

The published preimages reproduced the remount failure and unbounded local/page
accumulation. The repaired four-file UI gate passed **63 tests**, including
accepted/remount recovery, recovery across another pending same-conversation
turn, foreign pending operation and unknown-controller negatives, complete-page
navigation and existing draft behavior. Process37339 completed at rc0;
the full OS TypeScript build also completed at rc0 with zero diagnostics.

These are source and fixture proofs. The published sequential project-chat
path uses its incumbent Executive/Codex owners. It does not by itself establish
an installed DeepSeek company session association or an authenticated private
carrier into the native application. The next native consumer must join the
existing SessionBridge/Runtime to the original native process with a trusted
installed association; Send/resume/Stop and governed tools still require their
original admission, operation and ACP owners. Provider sign-in, installed route,
production browser journey and production acceptance remain open.


## Finite native history consumer qualified; production join still open

The existing private SessionBridge/Runtime now has an optional exact native read
consumer. Actual original Runtime root/work evidence and current READ identity
are checked around an owned socket-pair read into the original native process.
The finite native port reuses Cordis scope, Gateway, non-owner Peer and cold
SessionController reads; it creates no session/writer, retry or new transcript.

The real cross-process source test recovered identical native snapshots and a
page with original UTF-8 and stream chunks while the original writer stayed held.
Original JSONL/zstd bytes did not change. Sixteen native port cases, thirty-one
Python native-read cases including the real process case, strict native typing,
thirteen package/export cases and three actual isolated App-peer/socket/factory
cases, plus the92-case installed/Runtime regression, are retained in [the exact join frontier](NATIVE_COMPANY_JOIN_FRONTIER.md).
The App-peer and native-process fixtures are separate evidence, not installed
OAuth or production acceptance.

The private host bundle now resolves the original packaged native scope module
through one fixed internal link. The original company client and company-peer
bundle stay byte-identical. New package staging requires both host exports;
historical qualification remains tied to its exact old export set. The 0f01
publication remains its original snapshot. A separate package from 6d40 source
qualified both exports and was published with the 81b0 source composition.

Default installed source is still unavailable. The original native launcher has
not supplied an endpoint/association handoff; stock browser-owner bypass,
authenticated native foreground/ACP admission, production sign-in and the full
Send/resume/Stop/restart/revocation journey remain open engineering and installed
acceptance work. Source publication or CI green does not close those requirements.


## Qualified attended package and exact native ACP Session observation

Published composition `81b0f5fe39251fb3f041fc18f9d5c95922f26747` preserves the
incumbent realm-pin repair and accepted protected source, including both the
DeepSeek history method and the new Hermes-family continuation behavior.
The composed bridge/Runtime/Hermes gate passed 118 cases; four actual App
integration suites passed 62 tests; the OS typecheck had zero diagnostics.

The separate attended build from 6d40 source passed all seven native build gates,
its complete 116,148-entry launcher closure check, and a compiled host-export
import using the original native scope. `attended-build.json` records the actual
new manifest `1e2248382dcd64e5c7b19eae709d0be8ee57e7525d3cd208290b52146b4357b5`.
The original company client and company-peer bytes are unchanged. The package
has not been installed or relabeled as a later ACP application composition.

The following source slice adds a closed, explicitly selected v3 observation to
the original ACP startup exchange. The actual Agent supplies its original
Session ID after governed discovery and rechecks its object identity/lifetime
around ACK. The parent requires that same ID from standard ACP before prompt.
Legacy v1/v2 packet identities are preserved; the actual-Agent entry requires a
v3 gate and has no downgrade fallback. Existing evidence-only current-authority
fields remain evidence-only.

The real native run found and reproduced an early normal-shutdown SIGTERM. The
incumbent owner now permits cooperative cleanup within the existing finish
deadline, while preserving original signal identity checks, explicit-cancel
behavior and nonzero-exit failure. Final qualification passed **126 parent,
startup and installed-source cases** and **nine real current-donor Agent/history
cases**. Exact retained receipts and remaining production work are in
[NATIVE_COMPANY_JOIN_FRONTIER.md](NATIVE_COMPANY_JOIN_FRONTIER.md).
