# Thin native Hermes in Mastermind OS

## Scope and source
Chairman-directed continuation of `meta-ceo-open-harness-convergence-20261024-sol-001`.
Source operation: `hermes-thin-os-integration-20261106-c1-01`; base/procedure
`609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1`.
Recovery: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6693932749.

**Outcome:** a signed-in native Mastermind OS user can connect to the same operating-system
user's already-running Hermes gateway, start a text conversation, submit once, reopen
native history, and inspect the original admission. This first release must not depend on
finishing the advanced Linux/Executive/Fabric stack. The remote web app is not a local
operator and gets no loopback proxy or credential. Native-first is a release slice, not
completion of the remote or always-on company-orchestration outcome.

## Architecture ruling
Use the actual `hermes-gateway-v1` session authority, not the unauthenticated dashboard.
Hermes owns sessions, admissions, event replay and execution. The native OS host owns
signed-in visibility and same-user attachment; a small replaceable adapter projects only
bounded conversation data. The UI consumes a versioned `mastermind.hermes_native_view.v1`
port. Later qualified role gateways can implement that same port. Neither advertised
capabilities nor chat text grant Executive/Capacity/Fabric authority.

The adapter is embedded in the Tauri binary and executes once per operation using the
existing Hermes Python environment. It uses the upstream private control client and an
explicit already-discovered endpoint; it never calls ensure/start/restart. It creates no
listener, database, task queue, retry engine, credential store or provider client. Private
session tickets never cross into the renderer or logs. In this first port, newly created
sessions request an empty toolset, disable hooks and preserve the existing model route.
Installed Hermes also exposes its existing read-only Capacity MCP through three scoped
discovery wrappers. The adapter qualifies that exact installed bridge and scope before
allowing sends, and the UI explicitly labels CAPACITY_READ_ONLY. Unqualified tool scopes
remain read-only. It does not grant the local agent company execution tools. Native user requests remain
exact, and the served model is not inferred from a configured model label.

Only status/list/create/read/send/receipt and exact original-request recovery are exposed. No arbitrary RPC, endpoint, profile,
model, key, cwd, shell, role grant, approval, cancellation or restart arguments. Role labels
are conversation purposes, not two installed role authorities. Host auth generation is
checked before invocation and before releasing its result. Mutations also require the
generation observed before durable reservation. Sign-out discards private UI results,
while the existing pending-pointer store retains the original request lookup. Unexpected
modifying outcomes remain unknown and are never automatically replayed.

## Verified input, not product acceptance
M2 upstream is clean at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (0.23.0).
Actual private identify answered runtime protocol 1, ready, session-authority-v1,
durable-admission-v1 and event-replay-v1. The gateway is distinct from dashboard9119.
The installed Capacity MCP only catalogs and previews; native worker dispatch is not enabled.
Preserve #2134 C35 unpublished C64/C65 and original effects, #2147 and all H24 owned paths.
The original new-workspace acquisition returned uncertain, then its same-carrier status
and exact worktree record proved the clean pinned branch; no second acquisition occurred.
A read-only Fabric child `hermes-thin-os-map-20261106-c1-01` was refused before launch
(EXECUTION_NOT_ELIGIBLE, controller exit75, no result). No replay/native child substitution.
Direct bounded implementation uses NO_ELIGIBLE_PRE_EFFECT_WORKER; principal retains acceptance.

## Task tree and acceptance
- THIN-1: native transport and projection. Closed requests, compatible live identity,
  bounded history, no secrets/authority fields, genuine refusal versus unknown effects,
  and no ensure/retry. Python contract/negative tests plus a real native canary using the qualified limited scope.
- THIN-2 (depends THIN-1): authenticated native host command and Office component.
  Scope generation/expiry tests, text preservation, accessible empty/loading/error states,
  original-admission status, read-only recovery, no automatic duplicate sends. Browser-only
  build has no local connection. Keep remote/advanced configuration independent.
- THIN-3 (depends THIN-2): focused tests, actual native compilation, protected publication,
  signed-in native user roundtrip and reconnect. No deployment/always-on claim before proof.
- ADV-1 (after THIN-3): compose accepted #2134/#2147/H24 capabilities through existing
  Executive/Capacity/Fabric/Agent OS contracts; no migration of native history by title.
- ADV-2: authenticated remote-host adapter, genuine role enrollment and event-driven
  Secretary/Meta-CEO continuity; actual start/result/parent-consumption and recovery proof.

## Required review cases
Wrong/missing native identity; missing protocol/capability; credential-bearing or remote
origin; extra caller authority; malformed/oversized frame; another session's receipt;
logout during IO; timeout after send; malformed history; no-tool baseline; upgrade mismatch.

## Current recovery and source qualification

The assigned continuation retains PR [#2180](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2180),
branch `sol/web-hermes-thin-os-integration-20261106-c1-01` and workspace
`/Volumes/Mastermind 2/agent-workspaces/web/hermes-thin-os-integration-20261106-c1-01`.
The prior crash capsule is retained at
[567fa69575fd1702b1972a214a9c95458f84c12d](https://github.com/mastermindx-market-intelligence/Mastermind/blob/567fa69575fd1702b1972a214a9c95458f84c12d/docs/hermes/THIN_NATIVE_OS.md).
It is historical evidence, not the present unfinished-action list.

- Governing continuation pin: `615146aac6a1b0c0933bc9b815517a2fd285ed4a`;
  INDEX and governing laws were retrieved at that same protected SHA.
- Fixture repair: [c0e9f73651d359e2fe8e669e7d611a5dae2cce34](https://github.com/mastermindx-market-intelligence/Mastermind/commit/c0e9f73651d359e2fe8e669e7d611a5dae2cce34).
  Node `fileURLToPath` converts the URL, including spaces, `#`, `%` and Unicode.
  The regression copies and consumes the exact committed producer fixtures without
  weakening their hash/runtime-identity assertions. 10 passed, 3 existing skips.
- Protected overlap composition: [b805a3ca2b7b458cc2f5f935894f977c89e1f5e8](https://github.com/mastermindx-market-intelligence/Mastermind/commit/b805a3ca2b7b458cc2f5f935894f977c89e1f5e8).
  Preserved the newer Office/organization/selected-child shell and both native module
  registrations, including `control_room_read` and Hermes. Focused Office/Hermes
  composition: 243 passed, 9 existing skips.
- Subsequent protected movement through `0bf1d891e6e22a938f184e7df02481c52f3aa2a4`
  was inspected. New qualified role-request observations and Executive source-derivation
  work do not replace this same-OS-user attachment or require an installed upstream
  upgrade. No current owned source file overlap requires another ancestry-only merge.
- Later protected master `1e5f77a4e7aa5131ecbaef9bb00487882dec4d79` was composed
  for the real append/append masterplan conflict, retaining both the thin-native
  amendment and protected P3/P7 hardening continuation. No governing delta or native
  implementation overlap was present; the only upstream app path was the independent
  project-continuation test fixture. The qualified native implementation is unchanged.
- Four web-only App fixtures now explicitly mock `isTauri=false`. This repairs the
  actual frontend failure on b805a3ca without weakening the native platform check.

## Reopening an uncertain original request

The adapter reuses `indexeddb-pending-pointer-store.ts`, database
`mastermind-os-pending-v1`, object store `pointers`. Closed record variants 13/14
extend its incumbent conversation-create/turn kinds; no second database, lifecycle,
queue or retry owner is introduced. Atomic strict-durability reservation finishes
before the native command is invoked. A concurrent reservation cannot dispatch.

The record contains only the original request ID, a fixed create-target discriminator
or original send session ID, and the existing record kind/version. It contains no
prompt, transcript, role, credential, permission, execution state or retry instruction.
Its host-qualified scope hashes the native profile home and actual OS UID under a
fixed domain. That scope survives gateway/app reopening and auth-generation changes;
it is a same-OS-user storage namespace, not a cloud account or authority grant.
Every command still requires the current native sign-in.

Reconnecting reads the pointer before enabling mutation controls. Reopening never
creates, sends, or automatically recovers. The explicit **Check previous request**
uses the original tuple:

- Create: upstream `hermes_state_keys.local_identity(profile, uid, request_id)` locates
  the original session. `SessionDB(read_only=True)` must contain the exact committed
  creation receipt and qualified owned history; recovery does not call `session.resume`.
  Missing or mismatched receipt/history evidence leaves the original request held.
- Send: upstream `SessionDB(read_only=True)` and `find_session_admission` locate the
  exact original `(principal_id, target_session_id, request_id)` in Hermes's ledger.
  The adapter then reads that admission through the existing gateway's `prompt.receipt`
  and checks session/admission correlation. Transcript readability is independent: the
  UI reads history separately after observing the receipt. A history timeout preserves
  the known terminal result and keeps Send disabled until a fresh read qualifies it.
  It never calls `prompt.submit` in recovery.
- Missing/pruned rows, mismatched evidence, read failures, changed lookup source,
  malformed storage and auth changes after invocation retain the pointer. Empty
  history, `running=false`, or an absent pending admission are not absence proof.
- Only an exact opened create or canonical terminal original-send receipt settles
  the pointer through `clearIfEqual`. A positively classified before-dispatch failure
  may clear this invocation's reservation. Auth changes and malformed replies cannot.
  A failed clear remains fenced; it cannot erase a newer pointer.
- Foreground reads of an admitted original are bounded to 30. Recovery responses do
  not reset that bound. An explicit user check may start another bounded observation.
  Native running/admission/prompt state still blocks another send after settlement.

Private lookup helpers are qualified to upstream `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`
and exact source hashes. A compatible protocol upgrade can still expose ordinary
history, but changed recovery helpers hold the original until requalified. No upgrade,
restart, enrollment or tool-authority expansion is performed by this adapter.

## Verification during this continuation

These are actual local observations; they do not claim installed-app acceptance.

| Check | Result | Retained local receipt |
|---|---|---|
| Current native UI, durable pointer and existing store suites | 127 passed | `/tmp/hermes-thin-recovery-web-20261107-c4.log` |
| Current Hermes UI/port plus the four previously failing App suites, two workers | 163 passed | `/tmp/hermes-thin-recovery-focused-web-20261107-c2.log` |
| Python bridge, exact owner lookup and negative recovery cases | 25 passed | `/tmp/hermes-thin-recovery-python-20261107-c2.log` |
| Dependency-free native request/auth-generation guards | 6 passed | `/tmp/hermes-thin-recovery-rust-20261107-c1.log` |
| Full native Rust suites, no default features, locked dependencies | 257 passed, 8 existing skips | `/tmp/hermes-thin-recovery-native-all-20261107-c1.log` |
| Typecheck and packaged native frontend build | Passed; existing chunk/dynamic-import warnings retained | `/tmp/hermes-thin-recovery-typecheck-20261107-c5.log`, `/tmp/hermes-thin-recovery-build-20261107-c3.log` |

The first unconstrained full app run was stopped at its owned process after measured
host load exceeded 100 and multiple unrelated suites timed out. Its exit143 is not a
passing full-suite receipt. The two-worker focused rerun passed; required hosted full
checks remain to be consumed for the successor.

A read-only attempt against the preserved native canary returned `EFFECT_UNKNOWN`.
One bounded diagnostic confirmed dependency selection, live protocol/source identity,
connection and exact original ledger lookup, then observed a `TimeoutError` on
`session.resume`. High host contention was concurrent; causality is not established.
No create/send was issued. The original canary receipt hash remained unchanged.
Diagnostic: `/tmp/hermes-thin-os-recovery-diagnostic-20261107-c1.log`.
The adapter was then corrected to read the canonical receipt independently of history.
The changed recovery path returned the exact original terminal/completed admission,
sequence6, execution generation1, without any create/send. Receipt:
`/tmp/hermes-thin-os-original-recovery-20261107-c2.json`, SHA256
`23f7fbf5edacf856316f5df3b0e15ac6172367da07443188e0e1e1a366f0f7a2`.
The original canary file remains byte-for-byte unchanged. This proves actual native
request-ID-to-admission recovery; packaged UI sign-in/history remain separately owed.
Candidate bridge SHA256: `4f6eac9d057eb36c3afd94350cd98fd974a374bdd92ad71ecec76a9e941bc012`.

## Concurrent Pro continuation: failure-boundary repair

The Chairman explicitly authorized concurrent disjoint implementation after the
previous generic live-writer pause. The assigned Pro continuation retained this
operation/workspace and verified source law at
`d2f72b2d0d3066502adef103afa847904a70b18d`. Candidate
`ea7a1f0b52e8449ca68ed7622611821a0784480b` was already published by the
continuing writer; no replacement operation or workspace was created.

Hosted OS run [42341856573](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42341856573)
passed native-macos. Frontend had 6656 passing, 12 skipped and one failure:
`FreshConversationContinuation.test.tsx` observed its transport call before the
after-commit unresolved callback. The repair retains the exact reference,
source-witness, original-pointer and callback assertions, and awaits that effect.

Exact-source inspection also reproduced two ordinary no-send dead ends and an
operation-binding gap. The continuation now distinguishes native authentication
failure before dispatch from authentication loss after possible IO. Positive
no-dispatch evidence survives the final auth check without releasing private
results. Identity, connection, preflight history and runtime-initialization
failures before a modifying RPC return `NOT_SENT`; a dispatched or previously
uncertain original remains held. The port requires the matching public operation
before qualifying status or settling its exact reservation. Crossed/missing
operations cannot clear it. The panel hides private state on auth change, explains
a proven unsent request, retains an unsent draft and never automatically resends.

Actual repair checks:

| Check | Result | Retained receipt |
|---|---|---|
| Native port/panel/contract plus continuation regression | 40 passed after correcting the new test fixture's raw-host/port boundary | `/tmp/hermes-thin-boundaries-web-20261107-pro-03.log` |
| Python bridge including pre-dispatch and recovery negatives | 27 passed | `/tmp/hermes-thin-boundaries-python-20261107-pro-01.log` |
| Native host/auth-generation/release guards | 9 passed | `/tmp/hermes-thin-boundaries-native-20261107-pro-01.log` |
| Typecheck | Passed | `/tmp/hermes-thin-boundaries-typecheck-20261107-pro-01.log` |

The inspected running installed app exposes real native accessibility controls and
reports signed-in state, but still identifies the older fca92d5a source below.
This establishes the available UI path, not acceptance of this repaired candidate.
Its existing public native-client input was subsequently verified from the original
installation's retained build profile, rather than relying on binary extraction.
The successor preserves that identity and the existing public input derivations.
No native create/send, synthetic pending record, active service restart or release
replacement occurred during these repairs.

## Original-request settlement follow-through

The initial concurrent failure-boundary checkpoint is published at
`2c0386936a49ab214802aee093b714626642acf6`. The continuing source session took the
remaining bounded repair from its clean local/remote head, preserving the concurrent
native packaging lane. [Source custody and counterexamples](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2180#issuecomment-6702850319).

- Before-dispatch host failures now return a closed original-invocation proof with
  operation, request ID, send session and expected auth generation. A typed internal
  before/after-dispatch distinction prevents later IO failures acquiring that proof.
  Generic IPC strings cannot clear a durable reservation after invocation.
- Authentication-race promotion validates the complete nonprivate NOT_SENT envelope.
  Missing fields, crossed request/session IDs, unexpected receipt/runtime/private
  fields and malformed capabilities remain held. Compare-clear must succeed.
- Replies carry request ID and original send session, and the port validates them
  before settlement. It captures request primitives before awaiting storage.
- Successful create is checked against the upstream deterministic original identity.
  Successful direct send is checked against the incumbent read-only ledger's exact
  principal/session/request admission. A response echo alone is not the proof.
- The native dispatcher can return storage_unavailable after its admission commit:
  tracked_write invokes publication after write(), and dispatch catches sqlite errors
  across both. Storage/internal/unknown errors after modifying RPC now retain
  EFFECT_UNKNOWN. Only the narrow qualified explicit rejection set can clear.
- New mutations require the already-qualified recovery helper source before dispatch.
  A compatible upgrade can still serve ordinary reads; unqualified recovery semantics
  cannot silently strand new sends. A post-submit lookup failure retains the original.

Actual follow-through qualification (overlapping suites are not summed):

| Check | Result | Retained receipt |
|---|---|---|
| Native UI/port/contract plus existing pointer/controller suites | 215 passed | `/tmp/hermes-thin-original-binding-web-20261107-c2.log` |
| Python bridge, crossed success and post-admission failure cases | 31 passed | `/tmp/hermes-thin-original-binding-python-20261107-c1.log` |
| Native host/auth/request and complete no-send proof | 9 passed | `/tmp/hermes-thin-original-binding-native-20261107-c1.log` |
| TypeScript | Passed | `/tmp/hermes-thin-original-binding-typecheck-20261107-c1.log` |

The first composed UI run exposed a raw-host fixture missing the new correlation
fields (214 passed, one failed). The fixture now supplies those fields while retaining
the original unmount/reopen/no-replay assertions; the final 215-test run passed.

A real read-only recovery through the modified bridge returned the original canary
admission terminal/completed, sequence6, execution generation1, with the exact original
request/session binding. Receipt `/tmp/hermes-thin-original-binding-recovery-20261107-c1.json`,
SHA256 `cae3efac1bf3e43618728ac04713b06a256051dddb0078c12fc903a84b6d8c03`;
bridge SHA256 `c1d5135deea2f6f7e81166533f85a616d09f7c32898af83e75c374fa6da80534`.
The original canary file's SHA256 remained unchanged before and after. No create,
send, synthetic pending record, service restart or upstream upgrade occurred.
This is native original-request recovery proof, not signed-in packaged-app acceptance.

The original installed public profile was hash-verified at
`/Volumes/Mastermind 2/agent-workspaces/web/mmos-project-team-launch-20261105-sol-002/app/mastermind_os/src-tauri/target/mmos-project-teams-fca92d5a-20261106-sol-002/PUBLIC_BUILD_INPUTS.json`,
SHA256 `ddfeea5e9ef02c1780f97e54b987e58ea9e2e6aa9471c960e90f241e4946926d`.
Preserve its native-client identity, absent/disabled refresh setting, Executive
resource, launch catalogue and Terminal public-input derivation. Canonical
[original installation provenance](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1621#issuecomment-6670337891)
was read alongside its exact APP_UPDATE_RETURN record, SHA256
`5466cbbc5abfa43d654aae033b531c82960fb97a751df537cdb331d5349e7953`.
The continuing session's Browser initialization lacks its originating browser context;
no alternate browser-control route is permitted by that failure. Existing pending
sign-in must be reconciled before another sign-in or candidate replacement.

### Protected ModelArk catalog test reconciliation

The final native repair and protected composition were published at
`fcce6cfcc43f7ce5882719fa16a8112430951020`. Its hosted Hermes run
[42344633300](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42344633300)
failed on both Python versions because the loaded-router test still required
ModelArk aliases to be absent after protected #1824 added them. This was a stale
integration assertion; no provider activation or native binding failure occurred.

The corrected test requires the exact current aliases/models, disabled providers,
false worker eligibility, and unchanged provider enabled/autonomous flags. A
separate legacy fixture retains absent-catalog coverage. All 23 hermes_models
contract/failure/profile/secrets/turn tests pass in
`/tmp/hermes-thin-modelark-catalog-regression-20261107-c1.log`.
Only tests and this record change: the application subtree remains exactly
`4a4c0fdd06f2065b8a1abe176b092276738947c2`, identical to fcce6cfc. A compiled
fcce candidate must retain its actual identity; this test-only successor does not
require relabelling it or rebuilding identical application bytes. New-head CI and
protected source merge still need their own canonical receipts.

## Remaining acceptance and protected release

THIN-1/THIN-2 source candidates and reopened-request behavior are qualified by the
checks above. THIN-3 still owes a current candidate build, real signed-in native
attachment/history/reopening/logout proof and the protected source release result.
The original adapter canary below is preserved; it is not a packaged UI Send receipt.
Do not fabricate a pending record for this already-settled canary.

The observed installed bundle at `/Users/chriswong/Applications/Mastermind OS.app`
is an older source (`fca92d5a3cef710932b46082eef98a258079f806`, build
`mmos-project-teams-fca92d5a-20261106-sol-002`). It cannot prove this successor.
Its signature is ad hoc, with no TeamIdentifier; a read-only signing-identity check
reported zero valid identities. A Developer ID certificate/key and notarization
custodian are genuine signed-distribution inputs under the
[incumbent release runbook](../runbooks/mastermind-os-macos-release.md).
Source/functional qualification may continue without claiming a signed beta.
The current native public-client build input must come from the existing registration,
not a new identity or invented client. Candidate callback routing must name the actual
candidate process, retaining the prior installed bundle.

Protected GitHub release must use the existing exact-head workflow and squash merge
queue; required `test`/ALLGREEN and actual holds bind. A full branch-protection read
returned 403 from the integration and was not replayed through another carrier;
required review count is not inferred from an empty review list. No self-approval,
direct self-merge, bypass or duplicate auto-merge enrollment is authorized.

DO_NOT_REDO: upstream install, private-socket discovery, completed synthetic native
turn, incumbent dependency selection, source workspace acquisition or accepted sibling
work. No new native canary, worker dispatch or Secretary message has been issued.
ADV-1/ADV-2 remain outside this first native slice; no remote, always-on company
orchestration, paid-pool inference or Fabric execution is claimed.

## Original native result: do not recreate or resubmit

- Upstream runtime observed: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, protocol1,
  version0.23.0. No installed-runtime upgrade or restart was performed.
- Original session: `local-e8fb5ddbfda77657928449650b999e04e92db3e025422c6e3a9b0b662120dd6a`.
- Create request: `943d3e2ee6ea504cb3f38e78ca80297b`.
- Send request: `92e84d97bb2b5ec38377f1f217754b2f`.
- Admission: `bf54819d587c4d369536179f532c77ee`, sequence6, terminal,
  outcome `completed`, execution generation1.
- User input: `Reply exactly MASTERMIND_NATIVE_CANARY_OK. Do not call tools.`
- Recovered assistant text: `MASTERMIND_NATIVE_CANARY_OK`.
- The same-session read returned two messages, no pending admission, not running.
- Retained receipt: `/tmp/hermes-thin-os-canary-recovery-20261106-c1-01.json`, SHA256
  `4045491b7728e703d495d85328b20745b1ff11c4d5b9aaff964ac763ff2dd086`.
- Tested bridge SHA256: `e42fccd302ef7efb08e99b74b3fa30e19ba2718738f7d4b05d8f6189672510c0`.
  The displayed `qwen3:14b` is configured-model metadata, not served-model attestation.

Initial attempts failed before native admission: missing local dependency import,
then native invalid-parameter checks. The concrete repairs selected the incumbent
committed dependency generation, preserved the installed model route rather than a
safe-mode model-less request, and removed an unsupported surface/unattended flag.
The accepted original admission above is settled; do not replay earlier requests.

## Packaged history gap repaired in the continuing Pro lane

The signed-in local package at source `2c0386936a49ab214802aee093b714626642acf6`,
build `hermes-thin-native-2c0386936a49-20261107-pro-01`, connected through the
actual native host to Hermes 0.23.0. Its Local history UI omitted the original
OS conversation because the upstream live and stored picker feeds exclude
`source=tool`. The original canary was not repeated.

The repair continues from `d7d5bfdb4bc656473a7e940dee07d0b437aed40d` and preserves
7f6c0036's request binding, fcce6cfc's protected composition and the merged
Paperclip organization view:

- List and transcript reads use the incumbent `SessionDB(read_only=True)`,
  bounded native paging and display-history APIs. Each row is qualified against
  the existing profile, POSIX peer principal, canonical creation receipt,
  deterministic identity, pure native route/origin and validated physical lineage.
  No transcript mirror, owner, SQL index or migration is introduced.
- Original-create recovery now requires its committed exact creation receipt.
  A deterministic name without that receipt remains uncertain. List, read and
  create recovery first perform private-control runtime identification, then use
  read-only `SessionDB` access. They issue no session RPC and attach no viewer.
- Stored snapshots expose live running/prompt state as unobserved and no live
  tool permission. The explicit “Check and send message” action attaches to the
  same native owner with `session.resume(omit_messages=True)`, checks live
  policy/busy/prompt holds, and submits once with the original request identity.
  Source inspection corrected an initial hypothesis: `session.info` alone cannot
  send because the wire owner requires a connection subscription.
- The installed wire API always admits to its existing FIFO; `queued:false`
  does not supply an atomic no-queue guarantee against another writer racing
  after the snapshot. This client adds no lock/queue owner and makes no stronger
  claim. Positive busy/unknown/approval holds refuse before submission.
- Recovered receipts invalidate the prior conditional-send affordance until
  the original history refresh succeeds. No automatic resend is added.

Actual focused qualification:

| Check | Result | Retained receipt |
|---|---|---|
| Bridge, exact settlement, preflight and dedicated read-only history tests | 39 passed | `/tmp/hermes-thin-history-python-20261107-pro-01.log` |
| Contract, native port and panel | 41 passed across 3 files | `/tmp/hermes-thin-history-web-20261107-pro-01.log` |
| TypeScript | Passed | `/tmp/hermes-thin-history-typecheck-20261107-pro-01.log` |

An actual read-only execution of this modified bridge (SHA256
`7f1518b40be7f62add9d1981d810a7fda5e1b30eaecce93de75892774b063a92`,
Studio process88377) returned seven owned history rows, included the original
`local-e8fb5ddbfda77657928449650b999e04e92db3e025422c6e3a9b0b662120dd6a`
conversation, and recovered the exact assistant text
`MASTERMIND_NATIVE_CANARY_OK`, generation1. Native create/send calls: zero.
This is source-path proof; the ensuing source-bound package still needs its UI
journey and must not reuse the 2c package's identity for changed application bytes.

The concurrent composition test edit retains its exact protected blob assertion
and updates only the expected `codex_provider_realm.py` blob to
`a51e2bce8d9bb312107f975d503abd6541bd5000`, verified against the composed source.
It preserves the protected spec-only ModelArk catalog; no provider is enabled.

### Current native artifact custody

The 2c candidate is the sole observed running app, PID83624. The prior
fca92d5a installed bundle remains on disk; its app was signed out and gracefully
quit before 2c launch. LaunchServices callback lookup was read back to the 2c
candidate path, and the actual native Build details confirms the same public
native-client reference
`native-client:v1:47cabc2a4fe992f317c895bb619d0fcf64b49f1e03d9992781d1dca7c77cb423`.
Its source-bound build and launch/connect records are under
`/Volumes/Mastermind 2/agent-evidence/hermes-thin-os-integration-20261106-c1-01/candidate-2c0386936a49/`.
This reconciles the earlier pending-login observation for that candidate.
The other lane's interrupted d7 builder was terminated and never selected;
the next package is owned by this continuing installed-journey lane.

The successor build preserves the hash-verified original PUBLIC_BUILD_INPUTS,
including disabled refresh, Executive resource, launch catalogue and the same
Terminal public-key derivation. Apple Developer ID/notarization/updater and
broader remote-company acceptance remain separate holds. No active Hermes
service restart, original-canary replay or fabricated pending record is permitted.


## History consistency follow-up after e7b26baf

The clean published history checkpoint
`e7b26bafc24bb63a6078a930ac7a56360cbc1ce9` was consumed without changing its
completed package. Two bounded edge cases were reproduced in focused regressions:
concurrent appends shifted newest-relative offsets between autocommit history
pages, and a refresh using an old physical transcript ID failed after rotation.

The adapter now takes one bounded incumbent history read (at most 1,000 rows),
then filters and retains the latest 100 visible messages. It preserves owner,
profile, lineage and receipt checks. The panel refreshes the stable logical
session ID, preserving the port's strict target validation. The existing durable
uncertainty hold, request binding and explicit send preflight remain unchanged.
Neither fix creates a session, sends a prompt or introduces a state owner.

Both new regression tests failed against e7 before the fixes and passed after.
Their retained negative logs are
`/tmp/hermes-thin-history-append-red-20261107-c1.log` and
`/tmp/hermes-thin-history-rotation-red-20261107-c1.log`.

| Current combined check | Actual result | Retained receipt |
|---|---|---|
| Native bridge and read-only history | 40 passed; 25 subtests passed | `/tmp/hermes-thin-history-final-python-20261107-c1.log` |
| Contract, native port and panel | 42 passed across 3 files | `/tmp/hermes-thin-history-final-web-20261107-c1.log` |
| TypeScript | Passed | `/tmp/hermes-thin-history-final-typecheck-20261107-c1.log` |
| Exact paired translation composition, Macro f0375acf | 23 passed | `/tmp/hermes-thin-realm-fixture-composition-20261107-c1.log` |
| Commercial realm source boundaries | 16 passed | `/tmp/hermes-thin-commercial-realm-source-20261107-c1.log` |

The inherited composition-fixture pin repair in e7 retains every source guard;
only the reviewed protected #1824 realm blob changed. The separate broad local
Codex-realm suite produced eight passes and one installed-binary hash mismatch
before native Codex execution (`88133672…` versus pinned `16593cc2…`). That
unrelated installed-Codex qualification is not claimed or altered; the relevant
commercial-realm source checks and exact paired composition above pass.
The first disposable provider test invocation lacked `ops.executive_os`; its
collection error is retained separately from the subsequent complete-context run.

The e7 debug candidate build completed with its actual source and full existing
public profile at 06:29:22Z, under
`/Volumes/Mastermind 2/agent-evidence/hermes-thin-os-integration-20261106-c1-01/candidate-e7b26bafc24b/`.
It does not contain these later history edge-case fixes. The active native UI lane
retains that immutable artifact and original canary; final package equivalence,
installed acceptance and protected release must bind the subsequent exact source.
No new canary or synthetic pending pointer was created.


## Pro continuation: protected composition and installed journey, 2026-11-07

This section supersedes the historical artifact-custody paragraphs above. The
original operation/workspace/PR remain in use. Governing law was verified at
`d2f72b2d0d3066502adef103afa847904a70b18d`; the protected-source movement below
changes no governing procedure or native app file.

Source `2b7d65dddbef7a4cd245f23bc21f6072b7c582c4` repairs the D8 source-scan
failure by putting the owner identifier and the unchanged512-byte title bound
on separate dictionary lines. It preserves runtime behavior and every protected
D8 assertion. The committed-head D8 test plus native bridge/history suite passed
41 tests (`/tmp/hermes-thin-d8-history-2b7d65dd-20261107-pro.log`, exit0).
The protected composition through `ea0e7c08b95271228c50dc5cb2c00c21a80c7c5e`
resolves only the ModelArk test overlap: retain the full protected catalog
presence/eligibility matrix, the real-router legacy-absent case, and both mapping
and provider-flag nonmutation assertions. Seven focused tests pass, exit0
(`/tmp/hermes-thin-protected-model-contract-20261107-pro.log`). No provider is enabled.

The sole current native app is immutable candidate
`486ec0275b74d8c508ca96dbe40173054b246978`, build
`hermes-thin-native-486ec0275b74-20261107-pro-03`, PID27848. Its full original
public profile and native-client reference are retained. It was built at
06:46:39Z; the prior e7 app quit cleanly at07:02:43Z after verifying an empty draft
and no unresolved request. LaunchServices was moved to the486 bundle and its
actual Build details, signed-in state, Hermes0.23.0 connection and Organization
and goal lineage were observed at07:10:51Z. Artifact directory:
`/Volumes/Mastermind 2/agent-evidence/hermes-thin-os-integration-20261106-c1-01/candidate-486ec0275b74/`.
The package is local debug/ad-hoc; Apple distribution is not qualified.

In e7, the retained create request `4ce58a3ebc6f4c6799c9099a662932e3` was
reconciled by one actual Check previous request action at06:42:15Z; readback
opened its existing empty conversation and removed the hold. Its trigger remains
unattributed. The original canary prompt and exact retained answer were then
visible through Local history at06:44:59Z, without resend. Receipt
`candidate-e7b26bafc24b/uat-retained-canary-history.json` SHA256:
`3385a1560c890e7d0553c5a56f38dffaa57fe795a1e39a59664bcf649f634b73`.

At07:11:01Z, this continuation invoked the486 package's native New conversation
once to begin a useful release-note conversation. Its original request
`9fbc8f4abb944ab1a170b4990e59f729` is held as EFFECT_UNKNOWN; duplicate creation
and sending are disabled. One actual UI recovery at07:13:25Z remained unresolved.
A read-only exact-package diagnostic returned the same unknown result; a bounded
exception trace locates the recovery failure in private Identify's3-second
socket timeout, before original lookup or database reads. No deterministic
schema/identity defect or causal gateway scheduling defect has been proved.
Preserve that original pointer and target. No retry, pointer deletion, new
conversation, service restart or native provider change is authorized by this
uncertainty. Source work and the requested logout/reconnect journey continue
independently; this is not yet acceptance of a new useful Send.

Retained486 UI/source receipts: `uat-auth-build-confirmed.json`,
`uat-created-conversation.json`, and `uat-created-recovery-diagnostic.json`
(the last SHA256 `bf039e7fed407bcb29b221d39133b28ec36d633f666bf71530684feb46f80d7a`).
The root continuation has issued zero native Send calls. Original canary receipt,
source pin and admission remain unchanged.

The S1 Stop patch returned in PR comment6703525951 is an additive follow-up;
cancellation is outside this original thin-native slice. It has not been imported.
A source-derived stale same-session target race remains: public Stop must carry
the displayed original request/session tuple, validate it before pointer reservation,
and bind the displayed receipt to that same original. A stale A response/click
must not cancel newer requestB. This finding is not an observed cancellation.

Remaining qualification: resolve original9fbc through its native owner, useful
signed-in Send and original answer/history, logout/reconnect and process reopen,
current protected CI and normal protected publication. Signed/notarized/updater
release and broader remote-company orchestration remain separate production holds.
No duplicate canary, active-service restart, second session owner or automatic
merge/queue request has been performed by this continuation.

### Canonical creation reconciliation and current authentication control

At07:24:42Z, a bounded read-only query of the original canonical store, with the
installed identity/receipt source hashes and file owner/mode/inode checked, proved
that request `9fbc8f4abb944ab1a170b4990e59f729` committed to
`local-1fb461715a98699c3b536f523edff78784ebd84f6a5d131b4e2318ec38db02fb`.
The receipt's profile/principal/request/session identities match; the local row
and requested title match, and it has zero messages. This reconciles the creation
effect, not the interrupted UI recovery. The incumbent pending pointer was not
changed; the next signed-in UI action must recover that exact original, never
create a replacement. Evidence: [original-create-reconciliation.json](evidence/thin-native-os-20261107/original-create-reconciliation.json).

The actual486 Sign out action at07:19:09Z produced the signed-out welcome screen
with the private workspace hidden. One Sign in action at07:20:54Z entered
“Finish signing in / Waiting for browser,” observed at07:21:44Z. The Browser
connector returned “Browser access requires the originating browser context.”
That attempt later displayed “Sign-in could not complete.” at07:27:04Z;
its terminal screen exposes the existing Sign in control again. The Mac browser
flow was not replaced with a cloud browser, token injection or another auth owner.
The exact next user control is to click Sign in in the current486 Mastermind OS
app on the Mac and finish its browser flow. This is an observed connector/context
limitation, not a safety denial or an invented review requirement. No credentials
were read or requested in chat.

[Durable evidence bundle](evidence/thin-native-os-20261107/README.md) contains
source-bound actual AX observations, original recovery evidence, package hashes
and the source-equivalence record. The486 candidate and published8c application
source differ only by the D8 dictionary formatting; their Python ASTs match.
The running package retains its actual486 build identity. Current8c hosted
Hermes harness42350964042 is successful; OS42350964039 and CI42350964044 were
still running at this checkpoint. Subsequent head/CI readback belongs in the
existing PR continuation, not an all-green claim here.

## Native window reopen repair discovered during final acceptance

A later read found the same raw486 process, PID27848, alive and visible/frontmost
but with no accessible window. The earlier close/hide trigger is not attributed.
One exact-PID/path-guarded `open` of that existing bundle returned0; the same
process still exposed no window. This is separate from the native creation and
authentication effects above. No new app, model request or service was started.

Pinned Tauri2.11.6 source shows Builder.run delegates to App.run with an empty
callback, and the existing main.rs supplied no macOS Reopen handler. The repair
retains the one App, NativeAuth, TerminalSession, setup/deep-link registration
and complete invoke-handler list. On macOS Reopen with no visible windows, it
reuses the fixed main window if present or recreates that exact configured label,
then shows, unminimizes and focuses it. It never reruns auth restoration, changes
close-to-hide policy, prevents Quit, invents another label/owner or retries a
failed window creation. Only fixed local error codes can be logged.

The original9fbc pointer and canonical zero-message session remain the next
recovery target. A fresh source-bound package must prove window restoration
before the user is asked to complete sign-in; the prior request to use the
windowless486 screen is superseded. Current-ad frontend6671pass/12skip across
384files, default and opt-in native configurations258pass/8ignored each,
unsigned-package/locked-input verification and all four CodeQL analyses passed.
General CI42351563551 was still running when this repair began. Those results
are historical evidence forad, not claimed verification of the new window code.

The new window code compiled under the full incumbent public package profile.
That profile exposed an existing test-fixture dependency: the base two-resource
transaction test inherited compiled MM_EXECUTIVE_RESOURCE and expected no third
exchange. The test helper now explicitly constructs the base profile with no
Executive resource; every original assertion is retained, and existing explicit
Executive fixtures still cover the enabled chain. Production auth code is unchanged.
The original red log retains237passed/1failed/8ignored; the corrected full native
application suite passes238tests/8existing ignored, exit0, with the Executive
profile compiled and refresh disabled. Green log:
`/tmp/hermes-thin-window-reopen-native-20261107-pro-04-fixed.log`.
Verified source SHA256s: main.rs
`14be131790c3cb8f4e4e70c20af3c17e360926ba36d2e0725238809d576e0f4d`;
auth.rs `55844330ebbcd982692bdf867ed766c5ed9e909ee9f64ac8c7900e5e28f643d5`.


## Continued native acceptance:386 window, original recovery and scope composition

The current single local debug package is source
`386578f66392ae79a1759a0d216c102509277fba`, build
`hermes-thin-native-386578f66392-20261107-pro-04`, app tree
`f716e579e2ecea103faf610d79af48628c7fe94f`. Binary SHA256:
`9477afc7ea6aa96ee106931ce367aadc6943d4138344800218b53a57f03d2b16`;
build receipt SHA256:
`b9607de94be02b0e6c3cfa374ae7f5166662102344b4d57857b5f7c5de0a8301`.
The old486 process's AppleEvent quit timed out. After exact PID/UID/executable
and zero-window reconciliation, one guarded SIGTERM ended that UI before386
launched. This was not a clean graceful quit; no Hermes service was restarted.

Actual386 close exited PID10887; opening the same bundle restored one window in
PID31049. A subsequent minimize/open restored that same PID31049 with one
unminimized window and the callback routed to the exact386 bundle. The
absent-window reconstruction branch is not claimed exercised. At08:09:26Z the
app showed Signed in; no completion actor/cause is attributed. At08:11:20Z its
actual source/build/client, Signed in, Hermes0.23.0 and retained Organization and
goal lineage were observed. This supersedes the earlier human sign-in request.

At08:11:32Z, one Check previous request recovered the original9fbc creation.
Readback at08:11:40Z opened the same empty conversation and cleared its hold.
The original pointer was settled through its owner, not deleted or replaced.
No new conversation was created.

One actual Check and send message action at08:12:38Z submitted a drafted
four-bullet internal release-note request through the UI. Its first error/status
text was not captured; the UI returned to an enabled Send/draft and later reset
to Not connected while the sidebar stayed Signed in. A reconnect exposed no
pending pointer. A canonical read-only reconciliation at08:21:44Z found the
original session with zero messages and no admission rows. This is stored-state
evidence, not a standalone no-send proof or an accepted answer.

A live, identified preflight at08:24:37Z attached only to that existing original
session, without create, submit or cancel. It found running=false, pending=[],
no prompts, generation0, frozen source=tool / toolsets=[] / hooks=false /
follow_profile_config=false. The effective toolsets were
`["mastermind-fabric-capacity","mmx_omh"]`, with three deferred bridge schemas.
The existing adapter correctly classified that extra scope UNQUALIFIED.
Capacity source qualification was true. The added OMH tool is being traced to
its exact installed read-only source closure before any scope recognition;
three visible bridge functions alone do not prove capacity-only reachability.
Do not blindly replay the message or weaken scope checks. Current useful
Send/answer/history acceptance remains open.

All386 receipts above are in the
[existing evidence bundle](evidence/thin-native-os-20261107/README.md), with
original paths and exact hashes in its manifest. Current386 OS42353143020,
Hermes42353142768 and CodeQL42353140126 succeeded. OS frontend:384 files,
6671passed/12skipped. Native:258passed/8ignored in each default/opt-in rotating
refresh configuration, plus unsigned package/locked-input verification.
OS/Hermes checked synthetic merge4713daf6814aa0cc25aab3ddaeb7c1aa5aecbe96
of386 into protected5199647e89166d163392905574097b2cfa16ca5b.
General CI42353142892 shard5 exposed a stale exact-auth-source review record,
not a new identity defect: its three unchanged HTTP503 operands moved.

### Completed-transaction timer and exact review-fixture repair

Source inspection found that open_transaction's five-minute timer always emitted
an auth event, even after its transaction completed. Every such event advances the
frontend privacy epoch and can remount Hermes while the display still says Signed
in. This source defect matches the observed reset shape; the actual08:14 event
is not causally attributed without an event receipt.

The repair emits only when the exact pending transaction's generation and
deadline are current and due. Completed, consumed/exchanging, replaced and
logout-stale timers return without announcement. Genuine expiry still uses the
existing resource-specific failure path and notifies once. No frontend auth-event
deduplication, timer owner, token refresh or auth authority was added.

Four regressions exercise completed three-resource login, in-progress exchange,
replacement/logout fencing and one-time real expiry including Executive-resource
isolation. Full local application tests under the original public Executive
profile pass242tests/8existing ignored, exit0; refresh remains disabled.
Log: `/tmp/hermes-thin-auth-timer-native-20261107-pro-05.log`.
Verified auth.rs SHA256:
`2842f2dc712cb1b8718a2dfcba592bb390c153d4666b73c3a797f0d67380b499`.

The exact-source review registry now pins those bytes and only the unchanged
HTTP503 sites at3613/3618/3622 with their original columns and spellings. Scanner
and all existing positive/negative assertions are retained. The existing full
review-fixture test module passes, exit0:
`/tmp/hermes-thin-auth-review-fixture-20261107-pro-05.log`.
These source repairs are not relabelled as behavior of the still-running386 app.


## Exact installed OMH advisory scope composition

The runtime's resolved inventory adds enabled plugin toolsets even when the
frozen launch request has toolsets=[]. The existing mmx_omh entry is a real
deferred tool, not an empty label: tool_search/tool_describe/tool_call can reach
its closed handler. Ignoring it would incorrectly claim capacity-only access.

The adapter now recognizes the exact combined inventory
`["mastermind-fabric-capacity","mmx_omh"]` only after both source qualifications
pass, still requiring the same frozen launch policy, exact three bridge schemas,
and current no-running/no-pending/no-prompt holds. The resulting presentation
scope is ADVISORY_READ_ONLY: “Local planning advice and capacity previews.”
Unknown extra toolsets, changed inventory or missing qualification remain refused.
No grant, plugin registration/configuration, service restart or execution owner
was added. History and original-admission recovery do not depend on OMH
qualification and retain their original read-only paths.

Installed Mastermind OMH release58ac65ae47824750cae32c5ab85b58b6f38e6d5e
provides only status, detached-plan preparation, advisory recommendation, and an
existing Capacity/Fabric route preview requiring reserved=false and the exact
PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH proof. Its selected OMH4.0.6 helpers
perform strict chain-data parsing/overlay and skill-catalog scoring, not provider
calls, entitlement shaping, worker admission or memory-provider registration.

Qualification reads, without importing or invoking the plugin: exact handler and
manifest; complete descriptor and expected paths; all19 adapter source files and
no extra Python source; actual interpreter, pyvenv and distribution metadata;
all1240 OMH Python source files (26,923,696bytes); native deferred-tool dispatch
source; and the exact Homebrew startup customization. Unexpected .pth hooks,
startup overrides or extension-module shadows fail qualification. The Python
source-tree manifest SHA256 is
`5178ac807671d0218b7668ebc3cd5d24a2d8fc4459ec245142cabc149afc03e4`.
This is trusted installed-source qualification; it does not claim attestation
against a hostile interpreter or tampered executable bytecode cache.

The actual installed-source check returned true with zero plugin imports and
zero runtime calls. Receipt:
[omh-source-qualification-20261107-pro-05.json](evidence/thin-native-os-20261107/omh-source-qualification-20261107-pro-05.json),
SHA256 `bf77754e618adb8c76bcfeed5d535e7a0ccca32686fadd9b1ed9ac79d3ab1df4`.
The check binds working bridge SHA256
`9b267a5b9697bb1f327f4e2c1d8526b24694bda679b5d3bd5f83ed2dd0e786a8`.

Focused validation passes:46Python bridge/history tests (including changed-source,
startup-hook, extension-shadow and scope/no-double-submit regressions),44frontend
contract/port/panel tests across3files, and TypeScript. Existing assertions remain.
Logs: `/tmp/hermes-thin-omh-scope-python-20261107-pro-05.log`,
`/tmp/hermes-thin-omh-scope-frontend-20261107-pro-05.log`,
`/tmp/hermes-thin-omh-scope-typecheck-20261107-pro-05.log`.
These are source receipts. The next package must retain its own source/build
identity and continue the original1fb461 conversation's useful Send/answer,
history and reconnect journey, without an automatic replay.


## Protected547 composition and current internal package

Protected master advanced to 547a880894b0f3d28a6d5118ee2534287b3fc1c0.
The verified 615146aa governing source remains unchanged. Its only changed-path
overlap with this candidate is the paired Fabric translation test. The resolution
retains the protected historical realm-preimage pin that application_http_sources
actually consumes; it removes the unrelated current-realm guard and its obsolete
comment. Every other fixture pin and assertion remains. The resolved file is
exact protected blob b3e00e1c3d507dc276f0f24d40e0665448f1e18a.

At prepared merge tree 1972f1192d64680d8456b21937a934ed7a9e875a, the isolated
canonical paired fixture with Macro f0375acf4ba076718e7cb420ed28ab61fb0a4f26
passes 23 translation tests. The two existing historical-evidence/tampering cases
also pass from the complete source root. The initial paired archive omitted a
native-startup collection dependency; the complete-root run corrects that test
environment without installing dependencies or changing source. Exact logs and
hashes are in [the composition receipt](evidence/thin-native-os-20261107/547a880894b0-composition.json).

The application tree remains e3bd08a36c4ea2363a12b061bf47f70639dd3dbe, so the
already-built 1f431c6c4087656ae3dbdc683d96ee2572f061c9 candidate retains its actual
identity. A copy at candidate-1f431c6c4087/qualified/Mastermind OS.app passes
nested and deep strict ad-hoc signing verification. Its original entitlements,
full public profile, compiled source/build/client and Terminal input are retained;
the raw artifact remains unchanged. [Package receipt](evidence/thin-native-os-20261107/1f431c6c4087-package-receipt.json)
SHA256 eae1759c5706f0d975c0c08ac3e81b35d448d0dc9835ed6456a20dab4648efc8;
bundle SHA256 d35c59d3c298aa9c5129bfb0389db1c55d8af4f57afb7fcf35c24c18991d4bb9.
This copy is unselected and uninstalled, with no new auth or callback action.
It supplies no Apple DeveloperID/notarization/updater qualification.

The selected OMH recommendation path also reads shipped trigger-pack JSON and
user trigger-language packs, whose effective home can be selected by the profile
configuration. These are closed data-only skill/phrase mappings consumed by the
pinned scorer, not executable grants or dispatch. This is part of the stated
local-advisory read scope; it is not limited to model-chains.json. The existing
trusted-source versus executable-cache attestation limit above remains explicit.

The active native continuation retains the original conversation and sole UI
lane. A successful fresh READY hydration in the same durable scope can prove no
outstanding pointer; absence of database rows alone cannot prove NOT_SENT.
No historical refusal code or original request ID is fabricated. The completed
canary remains preserved and must never be recreated or resent. Final useful
native answer/history/reopen acceptance and the protected queue remain owed.

## Native original journey proven on 1f and presentation follow-up

This section supersedes the earlier “useful answer/history/reopen owed” frontier.
The original operation, managed M2 workspace, branch and one native UI carrier
remain in use. Protected composition 77d6eab59feb688e95caf203aa53e592189d1d1f
retains the 1f application tree e3bd08a36c4ea2363a12b061bf47f70639dd3dbe;
the running package is still truthfully identified as source
1f431c6c4087656ae3dbdc683d96ee2572f061c9, build
hermes-thin-native-1f431c6c4087-20261107-pro-05. Its raw binary SHA256 is
1e29d9c645207703feaea54b9281708a357f1728b43c7a9a5ecdf3c9a8db2d93.
[Build receipt](evidence/thin-native-os-20261107/1f431c6c4087-candidate-build-receipt.json)
SHA256 47a59f7a77c7ea9d6a246f61611db822ebe92608a032b3fe17ff315fc564e702.

The original creation 9fbc8f4abb944ab1a170b4990e59f729 was already recovered
through the real 386 app, without a replacement create. All work below uses its
same logical and stored session:
local-1fb461715a98699c3b536f523edff78784ebd84f6a5d131b4e2318ec38db02fb.

### Actual packaged path, 2026-11-07 UTC

| Time | Observed result |
| --- | --- |
| 08:55:03 | Source/build/native-client identity and Signed in confirmed in one 1f window, PID 80261. Authentication remained stable beyond the old 300-second timer. |
| 08:55:45–08:58:17 | Connect returned Hermes 0.23.0 with no held pointer. Local history opened the original empty conversation; qualified mode=ro metadata bound selected row 3 to the exact 9fbc receipt/session. |
| 08:59:13.851 | One explicit useful acceptance-checklist request was sent from the native composer. Exact draft and enabled action were read before dispatch. |
| 08:59:26 | The app displayed request 5226a1441f084477a0fc523796fbe55f, admission d901546607d64c1e9c7cd195e4ddf532, status started. It cleared that draft and held further sending. |
| 09:02:06–09:02:43 | A subsequent original-request observation displayed Outcome unknown and retained the same pointer/admission. One Check previous request at 09:02:17.551 recovered terminal/completed and rendered the original answer. No resend, replacement create or cancel occurred. The cause of the unresolved read is not attributed. |
| 09:03:29 | Canonical mode=ro corroboration matched request, admission, original create receipt and session: exactly one user message plus one assistant answer, no pending admissions, no transcript truncation. |
| 09:03:41–09:04:45 | Explicit Sign out removed the private conversation. Normal window close exited 80261; one normal reopen created PID 75264 with one signed-out window. No Hermes service was restarted. |
| 09:05:04–09:11:31 | One reconnect Sign in completed. Connect and Local history reopened both original messages, each exactly matching the canonical transcript; no held pointer and no additional submit/create/cancel. Credential-ceremony actor is not attributed. |
| 09:13:11 | The existing Organization and goal lineage disclosure opened the Paperclip Organization consumer. Its read-only/source-not-qualified notice remains intact; absence of selected-mission qualification is not claimed as no team or no work. |

The new useful prompt is a requirements-to-checklist request, not a second canary
and not a replay of the earlier 386 draft. The earlier draft's unobserved refusal
code remains unclaimed. The accepted native canary and its source receipt are
unchanged.

### Exact evidence and effect disposition

All copied receipts and their SHA256s are indexed in
[the evidence manifest](evidence/thin-native-os-20261107/manifest.json).
Material links:

- [Started original request](evidence/thin-native-os-20261107/1f431c6c4087-uat-useful-started-projection.json):
  dbe12a5d23783bdcd50e032762da065a1ad0ee9ffb9be15a42e7dfb30d838a7d.
  This declared projection omits unrelated history-row titles and retains the
  original raw receipt SHA256 56ca2869e10c12a7149a50d032ca11b3871725ba3749fa6404f406ae551c142e.
- [Unknown-outcome UI](evidence/thin-native-os-20261107/1f431c6c4087-uat-useful-original-result.json):
  bff4790985a048d979267d018c90d8488f864d44136a816f345e76b7d4dff976.
- [Original recovery and answer](evidence/thin-native-os-20261107/1f431c6c4087-uat-original-recovery-result.json):
  30a5678d00fecee8ae2984654188e5dd29e770020f0922bba5c5b57170cfe03a.
- [Canonical original admission/transcript](evidence/thin-native-os-20261107/1f431c6c4087-uat-useful-canonical-answer.json):
  f128fe6d3cbd90cf0bbf1505d4dd2030d7f90d88d66224e47a3993c58ba92f51.
- [Logout cleared private content](evidence/thin-native-os-20261107/1f431c6c4087-uat-logout-cleared.json):
  472797caf3f9eea5bcb66391e9a3e8fe0d3835e4ae3136e691c54061ed08535a.
- [Reconnected exact original answer](evidence/thin-native-os-20261107/1f431c6c4087-uat-reconnect-original-answer.json):
  e004e3e8286029ed4a5b613002d4ff88b118cabbea7675b8a42c94e699ea81c0.
- [Preserved organization consumer](evidence/thin-native-os-20261107/1f431c6c4087-uat-organization-preserved.json):
  ac1545f7e8d0ad7c08592fc352492684661d0e7588c9acc2c7005ca03e6bb806.

Current original effect is terminal/completed, with its pointer settled by the
incumbent native port. The single 1f app remains PID 75264, signed in with the
original answer displayed. No new conversation/session owner, pointer deletion,
worker dispatch, accepted-canary replay or active-service restart was introduced.

### Two observed presentation repairs

The real logout correctly returned USER_SIGNED_OUT, but App's generic nonempty
reason handler displayed “Sign-in could not complete.” The presenter now excludes
only signed_out/USER_SIGNED_OUT from failure feedback. The native reason,
credential deletion, privacy epoch and genuine failure/expiry paths remain intact.

During an admitted original request, the retained historical session could still
have toolAccess=UNQUALIFIED after recovery cleared stale send eligibility.
The panel now says sending is paused until that same session's original outcome
is confirmed. A terminal original awaiting a successful history refresh says to
refresh before sending. These are display-only distinctions, bound to the
selected session; they neither infer qualified tools nor change send eligibility.

The existing logout and recovery assertions were preserved and extended.
App 107 tests pass, HermesNativePanel 19 tests pass, TypeScript noEmit passes.
The first combined run exposed one invalid newly added negative fixture
(null live-state flags without a history-check marker); the fixture was corrected
to a valid genuinely unqualified live session, and all 19 panel cases then passed.
[Exact test/source receipt](evidence/thin-native-os-20261107/ui-feedback-tests-20261107-pro-06.json)
records both runs, log hashes and the four changed-file hashes. No native bridge,
auth or ownership implementation changed in this presentation follow-up.

### Next permitted release milestone

Continue with one package of the presentation follow-up source, retain its own
identity, and verify the changed installed feedback without replaying accepted
model work. Consume exact-current-head trusted required CI, then the permitted
normal protected squash queue and actual merged-source qualification before the
incumbent app-only installation. Do not relabel the 1f proof as execution of the
later package or treat source tests/green CI/queue admission as installation.

Apple DeveloperID signing, notarization and updater distribution remain
unqualified. The unimported S1 Stop patch and advanced remote/worker scopes remain
separate holds. The mounted organization consumer has no new selected-mission
source qualification. Retained installed fca, backend 09b/call 5913 and all accepted
canary evidence remain untouched.

## Final candidate qualification and existing release lane

The presentation follow-up is built and observed as compiled source
`6e59cfeb6b00e1508eae51ec0a9dc5c03b8c193a`, build
`hermes-thin-native-6e59cfeb6b00-20261107-pro-06`, application tree
`d27925e195d5649ca1fd0cf723cda54b756a0dd7`.
The build completed at 09:16:50Z with unchanged source and the original public
profile, client and Terminal input. Raw build receipt SHA256:
`d105373a3a37875034e4eb2f795f2847a7a843be6c6eeaf673fef0df8629b3d7`;
raw binary:
`a43bd5cde4bc45950ae9fb6781c4e03b0da239a8ea91a4894c9aa1a26ee3b20e`.

C1 completed its existing finite internal qualification of a copy.
[Exact 6e package receipt](evidence/thin-native-os-20261107/6e59cfeb6b00-package-receipt.json)
SHA256 is `d28ab41f39c02fc1fabde8d06271036090845b98da72c4fdfe52ee03c2d76472`;
qualified bundle is
`b2b5f4c2755869e9a45288a427623ebace1f4fc78b7eaf4dd59edcff8db7ebb6`.
Nested/main/deep strict checks pass, original entitlements and public inputs are
preserved, and the raw artifact is unchanged. This copy remains unselected and
uninstalled; it has not performed authentication or any runtime operation.

Root normally closed the settled 1f app and launched raw 6e once at 09:21:28Z.
The single app is PID 23348. At 09:23:59Z, actual UI readback confirmed Signed in,
exact 6e source/build and the original native-client reference. Connect and Local
history reopened both original messages at 09:25:49Z, each matching the retained
canonical transcript. No additional create, submit or cancel occurred.

The changed logout presentation is now proven in the actual 6e package.
One Sign out at 09:25:59Z produced Welcome back/Sign in at 09:26:12Z, removed all
private conversation content, and **did not display the false sign-in failure**.
The app is left signed out, with no pending auth or original-request effect.
The changed unresolved-send wording is qualified by the current 19-case panel
regression and compiled package; no live model effect was manufactured to repeat
the accepted request.

[Final candidate acceptance](evidence/thin-native-os-20261107/native-ui-acceptance-6e59cfeb6b00.json),
SHA256 `0c31d66063205603bd76b8b1224a3a288778525b501c75b3b95fe10befbd6d40`,
explicitly separates:

- original creation recovery on 386 and full functional journey on 1f;
- the four changed frontend/presentation/test files;
- eight byte-identical auth, native host/bridge, contract, port and pointer-owner
  bindings between 1f and 6e;
- actual 6e authenticated identity, retained history and corrected logout proof.

[Current original-history readback](evidence/thin-native-os-20261107/6e59cfeb6b00-uat-retained-original-answer.json)
SHA256 is `8feae160775054128860488ebd5296c73bb87d8405b89bf3052bd8b0c5331043`.
[Corrected logout readback](evidence/thin-native-os-20261107/6e59cfeb6b00-uat-corrected-logout.json)
SHA256 is `4a943c121a39c20e6752a1ed93df76d2264f17900bcce0835ed8d3fd237637e8`.
All raw source paths and copied-file hashes are in the existing manifest.

The next action belongs to the **existing C1 protected queue/app-only installation
lane**, whose custody was recorded in PR comment 6702850319. Root retains the sole
native UI cutover and installed-path proof. There must be no parallel queue
request, signer, installer, app controller or service restart. C1 consumes the
final published evidence head, rechecks both native queue fields, preserves any
existing effect, and uses the normal head-leased protected request when qualified.
The prepared installer must bind actual successful head/integrated checks and
the protected merged tree; its compiled application tree must match in full.
Retain the compiled 6e identity separately from the eventual merge SHA.

At the 6e qualification boundary, OS 42359029013, Hermes 42359029011 and
CodeQL 42359025742 succeeded; general CI 42359029152 was running with no observed
failed step. These results are exact 6e evidence, not a claim about a later
documentation head or integrated queue candidate. The pending release still needs
canonical queue/merge/install receipts. Candidate acceptance does not itself
establish installation, Developer ID, notarization or updater qualification.
