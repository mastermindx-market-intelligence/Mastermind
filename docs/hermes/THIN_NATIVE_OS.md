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
  the original session; only `session.resume` is called. A missing session stays held.
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
