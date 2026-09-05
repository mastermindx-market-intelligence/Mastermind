# Personal-Pro Executive canonical read-plane architecture freeze

**Date:** 2026-09-05  
**Parent study:** `research/MASTERMIND_PERSONAL_PRO_EXECUTIVE_CONVERGENCE_2026-09-05.md`  
**Program:** MAS-48 / Personal-Pro Mastermind Executive Surface Convergence  
**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`  
**Capability:** the program remains `PARTIAL`; Personal-Pro production reads, control and parity are not accepted.

## 0. Decision, authority and supersession

This amendment corrects parent study §2.3 and freezes the smallest coherent production read architecture from current protected source.

At protected Mastermind `c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36`:

1. the current readonly `ExecutiveMcpGateway` has no independent lifecycle-read root and binds all four reads to `repo_root` outside fixture mode;
2. the accepted Executive service configuration intentionally separates `runtime_root` from `proof_source_repository` and `proof_workspace_root`;
3. the current direct gateway therefore cannot be the canonical production lifecycle reader merely by selecting the service's proof-source checkout;
4. the production read plane should preserve the existing external five-tool MCP contract and Secure MCP Tunnel, but replace direct production filesystem/SQLite reads with one dedicated read-only port inside the existing `ExecutiveControlService` process;
5. CeoIngress remains the narrow submit/status/hot-state boundary and is **not** widened into a general Job/Inbox API;
6. Steward/Secretary remains a separate organizational cockpit and is not merged into an Executive “super-MCP.”

This amendment supersedes:

- the parent’s weaker statement that `runtime_root` merely **defaults** to `repo_root`;
- this amendment’s earlier unresolved Path-1/Path-2 choice;
- the possibility of accepting the current repo-local gateway unchanged as the intended production lifecycle reader;
- any implication that a host-only census is required before the source architecture can recognize the intended split-root topology.

It does **not** supersede:

- the unchanged-manifest Personal-account A/B/C/D canary;
- PR #99’s Personal-Pro shell architecture;
- the transport-neutral hot-state / `MMX/SOL_STATE_V1` contract;
- C1’s original effect-unknown operation and RuntimeBinding;
- S0-R1, B2 or C2 gates;
- the authenticated Executive app, Steward, W3C, Runtime Continuity or Executive service owners;
- the requirement for current native host, account, tunnel and production proof before activation.

No implementation, configuration, Runtime, account, tunnel, credential, service, Job, Attempt, Worker, Wake or provider effect is created by this records-only freeze.

## 1. Current-source findings

### 1.1 The existing MCP gateway has one combined root

`integrations/executive_mcp/adapter.py` defines `GatewayConfig` with `repo_root` and no separately configurable readonly lifecycle root. Outside fixture mode:

```python
@property
def runtime_root(self) -> Path:
    if self.fixture is not None:
        return Path(self.fixture.runtime_root)
    return self.repo_root
```

The config parser accepts no `runtime_read_root`. The gateway currently:

- builds `executive_state` and `executive_inbox` against `config.repo_root`;
- opens `executive_job` and `ceo_intent_status` through `config.runtime_root`;
- therefore derives all four lifecycle reads from the same root in readonly mode.

`control_plane/executive_inbox.py` independently resolves `data/control_plane/executive.sqlite3` below its one supplied `repo_root` and uses `Runtime.at(root, create=False)`.

The authenticated `integrations/mastermind_executive_app` read gateway constructs the same readonly configuration from one repository root. Its dedicated CeoIngress client changes the write path, not this read coupling.

### 1.2 The accepted production service has intentionally split roots

Protected `ops/executive_os/control.json.template` binds different canonical coordinates:

```text
runtime_root:
  /var/db/mastermind-executive/control/db

proof_source_repository:
  /var/db/mastermind-executive/control/admin-checkout/<protected-sha>

proof_workspace_root:
  /var/db/mastermind-executive/jobs/workspaces
```

`control_plane.executive_service.ServiceConfig` carries those separate fields and the control service opens the authoritative `Runtime` at `runtime_root` while using the proof-source checkout for source/grounding law.

This is enough to establish the intended production topology at the source-contract layer:

```text
SOURCE_CONTRACT_ROOT_CASE = SPLIT_ROOTS_PROVEN
```

It does not prove that the current Chairman host has installed, loaded or exposed the latest service generation. Current installed-host state remains independently unverified.

### 1.3 A tunnel/client success cannot collapse the split

The Personal account can prove whether the server scans, which tools are visible, whether reads invoke, whether a native confirmation appears and whether the modifying tool is blocked. It cannot prove merely from `tools/list`, `ok=true`, `generated_at`, mode, a fixture Job or an HTTP 200 that lifecycle data came from the authoritative production `Runtime`.

The correct production proof joins:

```text
Personal account / tunnel / MCP invocation
+
server generation and tool-schema identity
+
canonical Executive service/runtime generation
+
source-grounding identity and freshness
+
independent owner-native read agreement
```

No single component may synthesize the others.

## 2. Alternatives considered and disposition

### Alternative A — keep direct repo-local reads in production

**Rejected for production.** The accepted service topology separates proof source and Runtime. Pointing the surface at the proof checkout reads the wrong lifecycle root; pointing it at the Runtime root loses the reviewed source/Agent OS/Git grounding expected by the rich tools and grants the surface direct database-tree access.

The existing path remains useful for fixture/local-development proof and the client-behavior canary. It must never be silently promoted or used as an automatic production fallback.

### Alternative B — add a `runtime_read_root` filesystem argument to the tunnel-facing process

**Rejected as the selected production architecture.** It would give an Internet-adjacent/tunnel-facing surface principal direct access to the authoritative Runtime database tree, reproduce service-side read semantics outside the service process, and make root/path permission configuration part of the product boundary. `create=False` prevents database creation but does not make direct database access the least-privilege architecture.

A path split may remain a valid test seam inside hermetic fixtures, but it is not the production trust boundary.

### Alternative C — widen CeoIngress into a rich read API

**Rejected.** `control_plane.executive_ceo_ingress` is deliberately a narrow submit/status plus diagnostic-hot-state boundary. Existing source law says it never opens its own Runtime and excludes the broad Operator protocol. Adding Inbox/Job/general organization reads would blur the modification authority and read surface, expand the UID-452 principal, and weaken an accepted boundary.

CeoIngress remains the single canonical CEO-admission sink. Its status/hot-state implementations may be reused as pure logic, but its wire surface is not turned into the rich Executive MCP backend.

### Alternative D — use the general Executive Operator socket

**Rejected.** The broad control protocol carries lifecycle and operational commands. Exposing it to a plugin/app principal would violate least privilege and create a generic Operator ingress from ChatGPT.

### Alternative E — use Steward/Secretary as the complete Executive read plane

**Rejected as complete, preserved as complementary.** Protected Secretary schemas provide a useful six-tool organizational contract, and current Steward PR #463 is an independently useful authenticated read-only slice. Current Sol product ruling `5553996467` explicitly classifies four of its fact families as truthful `PARTIAL / DEGRADED`: responsibility objective, requested action, current Runtime binding/continuation and surface review/health are not supplied by current owners.

Steward remains the organizational/responsibility cockpit. It must not fabricate missing Runtime facts or absorb the Executive read plane. Future producer-to-real-Steward-consumer waves remain separate.

### Alternative F — dedicated read-only service port behind the existing MCP contract

**Selected.** Extend the already-running canonical `ExecutiveControlService` composition with one bounded read-only port that receives the already-open authoritative `Runtime` and trusted proof-source grounding. Connect the existing MCP gateway to that port in production mode. This preserves one external tool contract and one lifecycle owner while removing direct production SQLite access from the surface.

This follows the accepted architectural pattern already used by `executive_dialogue_observation`: a narrow local AF_UNIX listener inside the existing Executive service, exact peer identity, closed schemas, no new daemon, no lifecycle ownership, one request per connection, bounded bytes/time and fail-closed socket hygiene.

## 3. Frozen production architecture

```text
Personal-Pro Sol
  |
  | existing private Secure MCP Tunnel
  v
existing mastermind-executive MCP server
  |  same five tool names and same input contracts
  |  READONLY: submit_ceo_intent refuses before any write client
  |
  +--> source/orientation reader
  |      repo_root + optional Macro source
  |      protected Git / Agent OS context only
  |      no Runtime SQLite
  |
  +--> new ExecutiveReadClient (read-only local AF_UNIX)
         |
         v
      dedicated Executive Read listener
      inside existing ExecutiveControlService
         |
         +--> already-open canonical Runtime
         +--> trusted proof-source grounding provider
         +--> existing Executive Inbox / Job / intent-status logic
         +--> existing hot-state logic where applicable
         |
         X no submit / dispatch / claim / lease / requeue / recovery

CeoIngress (separate UID/socket)
  -> submit/status/hot-state only
  -> canonical CEO admission

Steward/Secretary (separate app/product)
  -> responsibility/attention/blocker/surface organization
  -> truthful PARTIAL until owner-native fact families exist
```

### 3.1 External contract

Preserve the public five-tool registry:

```text
executive_state       READ
executive_inbox       READ
executive_job         READ
ceo_intent_status     READ
submit_ceo_intent     MODIFY
```

Tool names and input schemas stay stable. A reviewed server/schema version bump is allowed only for explicit response-grounding fields or production-backend configuration; it does not create another public API.

In Personal-Pro READONLY operation, `submit_ceo_intent` remains `production_write_disabled` and no CeoIngress client, socket or credential is required by the surface process.

If controlled Personal-account evidence proves the mixed manifest rejects the whole server, expose the smallest four-read projection of the **same** registry, gateway and ExecutiveReadClient. That is a client-compatibility projection, not another backend or policy.

### 3.2 Source/orientation versus lifecycle truth

The production gateway keeps source and lifecycle facts separate:

- the surface’s reviewed `repo_root` supplies protected source identity and rich orientation material;
- the canonical service supplies lifecycle data from its already-open Runtime;
- the service’s trusted grounding provider supplies the accepted proof-source SHA/generation;
- runtime payload is returned only when the surface’s expected protected source and the service’s current proof-source grounding are compatible under current law;
- Macro/Agent OS source may be read through its existing bounded source coordinate or appear as an explicit degraded section; it never changes Runtime authority.

A source mismatch produces `grounding_changed` or a typed unavailable result before lifecycle payload is treated as current. The gateway must not copy old Runtime data into a newly generated source wrapper.

### 3.3 Internal Executive Read port

The internal port owns exactly four read operations corresponding to the existing read tools. It owns no public semantic surface beyond those projections.

Minimum request material:

```text
schema
operation
request_id
expected_mastermind_sha
optional exact job_id or intent_id for the matching operation
```

The caller cannot supply:

```text
runtime root
proof source path
workspace path
mode
peer UID
authority
Job/Attempt/Worker status
freshness
backend result
```

Those are service-derived facts.

The listener:

- is composed inside the existing `ExecutiveControlService`, not a second daemon;
- receives the already-open Runtime and injected trusted source-grounding provider;
- has its own default-disabled all-or-none config and AF_UNIX socket;
- accepts one dedicated least-privilege read principal selected by the existing host owner;
- must not reuse `_mastermind_exec` UID 450, CeoIngress/Relay UID 452 or Agent Relay UID 457 merely for convenience;
- exposes no general Operator command, SQL, filesystem path, submit, dispatch, claim, lease, heartbeat, requeue, retry, recovery or service-control operation;
- performs no `Runtime.at(...)` in the surface process and no direct SQLite read outside the canonical service;
- bounds requests, responses, connection count and wall-clock time;
- rejects unsupported peer credentials, symlinked parents/sockets, foreign stale inodes, partial config and unknown schemas;
- removes only the socket inode created by the current service generation on shutdown.

The exact UID/GID and paths are installation facts, not hardcoded by this architecture record. They require the current host collision/principal census.

### 3.4 Tool semantics

#### `executive_state`

Compose:

- protected source/boot orientation from the reviewed source root;
- canonical in-process diagnostic hot state;
- bounded lifecycle summary from the same Runtime observation;
- independent source and Runtime generation/freshness receipts;
- explicit degradation for Agent OS/Macro, service, grounding or transport gaps.

It is rich orientation, not a write admission token. `do_not_submit` and diagnostic readiness retain their accepted semantics.

#### `executive_inbox`

Refactor the existing `control_plane.executive_inbox` producer rather than copy it. It must accept the canonical already-open Runtime or closed service-derived facts separately from the source root. Preserve current prioritization, provenance and strict-v2 behavior, including any accepted changes from PR #492.

Missing Runtime or missing organizational source remains explicit degradation; it is never interpreted as an empty inbox.

#### `executive_job`

Return one exact Job projection for a caller-supplied validated Job ID from the already-open Runtime. No list-all/search/dispatch capability is added. Unknown Job is `not_found`; unavailable Runtime is `backend_unavailable`; neither becomes a null success.

#### `ceo_intent_status`

Reuse the same canonical intent-resolution logic as CeoIngress status against the in-process Runtime, with parity tests proving equivalent identity, duplicate/conflict and receipt semantics. Do not grant the read principal access to the CeoIngress write socket merely to obtain status.

### 3.5 Existing authenticated Executive app

The Business/HTTP Executive app may consume the same ExecutiveReadClient after the canonical read port exists. It must not retain a semantically independent direct-root production reader. Authentication/HTTP packaging remains under BSC owners.

For Personal Pro, prefer the current stdio MCP server through Secure MCP Tunnel because it is the smallest client path and does not make Business authentication a predecessor of the no-code canary. The HTTP app remains reusable for Business, administration, approved-app packaging and fallback evaluation—not a second Executive API.

## 4. Response, time, null and correction contract

Every production read must let the consumer distinguish at least:

```text
client observation time
MCP server source/version/schema
surface source SHA and observation time
Executive service generation
canonical Runtime observation time/high-water
proof-source grounding SHA/generation
backend kind = canonical_service_read
freshness/degradation
```

Absolute host paths, usernames, tokens, raw config, SQL text, private provider/session material and tracebacks never cross the boundary.

Time semantics:

- `generated_at` is when the response wrapper was made, not backend freshness;
- source freshness and Runtime freshness are measured separately;
- service restart creates a new service generation and invalidates old ready claims;
- stale data may be displayed as stale evidence but cannot authorize a write;
- clock uncertainty is explicit and never clamped to zero.

Null/missing semantics:

- unavailable source != empty source;
- unavailable Runtime != zero Jobs;
- no matching Job/intent != backend unavailable;
- an empty canonical Runtime, when positively established, is distinct from an unreadable or absent database;
- missing Agent OS context degrades organizational orientation without fabricating lifecycle facts;
- Job/intent canary tests remain `NOT_EXERCISED` when no legitimate identifier exists.

Correction semantics:

- source or Runtime disagreement is appended as a new receipt; historical evidence is not rewritten into current truth;
- same operation/same payload remains duplicate reconciliation;
- same operation/changed payload remains conflict;
- a lost modifying response reconciles through the original carrier/status owner and never fails over through this read port.

## 5. Failure behavior

| Failure | Required visible result |
|---|---|
| Tunnel disconnected or wrong workspace association | client/transport unavailable; no local fallback masquerading as production |
| Mixed manifest rejected | client Case C only after auth/tunnel/schema causes are excluded; smallest four-read projection permitted |
| Read listener disabled, absent or peer denied | typed backend unavailable/refused; no broad control-socket fallback |
| Service generation changes during a call | refuse or retry the read within the bounded read-only policy; never combine generations |
| Surface source SHA differs from service proof source | `grounding_changed`; no current lifecycle payload accepted |
| Runtime unavailable/unreadable | explicit backend unavailable; no zero counts or empty inbox |
| Agent OS/Macro unavailable | organizational section degraded; Runtime facts remain separately attributed |
| Job/intent not found | typed `not_found`; do not fabricate an ID or create a record |
| Response oversized | existing bounded replacement receipt; never silent truncation |
| Socket timeout/partial response | read-only typed timeout; no switch to direct SQLite or broad Operator |
| CeoIngress unavailable | modification path unavailable; read plane does not submit on its behalf |
| Receipt-post failure after a write | canonical status reconciliation on the original write carrier; no resubmit through MCP |
| C1/SOL_STATE stale or ambiguous | diagnostic write preflight remains non-ready; rich read does not override it |

Production mode must not automatically fall back to repo-local lifecycle reads. A fallback that changes the truth owner is worse than an explicit outage.

## 6. Target role of direct MCP and `SOL_STATE`

The target role is now frozen, but activation remains evidence-gated:

```text
Direct Executive MCP over canonical service read port
  = primary rich Executive orientation in normal Personal-Pro sessions

MMX/SOL_STATE_V1 / executive_hot_state
  = compact admission and transport-health signal,
    write preflight input,
    and outage/fallback telemetry

Slack
  = transport and hot-state visibility,
    not the lifecycle or rich state database
```

Current law remains unchanged until the canonical read port and real Personal-account journey are proven and a protected amendment explicitly updates any predecessor. A successful rich read alone does not retire C1, remove `SOL_STATE` from write preflight or release B2/C2.

C1 may later cease being the primary **rich** read plane; it still has a distinct diagnostic/health job. Its original effect-unknown operation must be reconciled even if its long-term product role narrows.

## 7. Collision and no-start ruling

No implementation wave is released by this freeze because active owners overlap likely implementation paths:

- PR #491 / `runtime-continuity-r2-wake-ack-source-20260905-001` owns `control_plane/executive_service.py` and related dialogue-observation/service tests on a STARTed, nonterminal carrier;
- PR #492 owns `control_plane/executive_inbox.py` plus its tests/docs for strict-v2 provenance;
- PR #463 owns the current Steward app/projection and has a controlling truthful-PARTIAL product disposition;
- PR #469 owns separate BSC resource-metadata work;
- the existing W3C host operation owns native service/install/root observation.

Do not create a competing branch, edit one of those active paths, or ask a new worker to reconcile another owner’s dirty/local state. Before implementation, obtain exact terminal/release receipts or a jointly authorized path transfer and repeat the complete PR/worktree/process collision census.

## 8. Bounded execution DAG after collisions clear

Wave labels are planning identities, not Executive Jobs or worker assignments.

### READ-V0 — current native/runtime census

One existing owner-native receipt binds installed service generation, current control config, read-port absence/presence, Runtime root, proof-source generation, tunnel process and effects. Read only. No new installer or administrator request.

### READ-V1 — canonical read vertical

One independently useful source PR implements the dedicated read listener/client and all four existing read tools end to end under one external MCP contract. It includes the smallest refactor of existing Inbox/status logic, exact principal/config/install defaults and real consumer tests. No HTTP/public packaging and no account effect.

A single coherent vertical is preferred over four infrastructure-only PRs because a production gateway with only some lifecycle reads canonical and others repo-local would be dangerously misleading. Unsupported operations must be explicitly unavailable until the whole vertical is coherent.

### READ-V2 — default-disarmed host installation

The existing host owner installs/reconciles the exact reviewed release, creates only the reviewed read principal/socket configuration, proves every write/control surface remains disarmed and returns current source/service/root receipts. No provider turn or Personal account connection.

### READ-V3 — Personal-account unchanged-tool canary

Using the owner-approved tunnel and actual Personal account:

1. scan the unchanged five-tool server;
2. record visible/enabled tools and native confirmation behavior;
3. call state and inbox;
4. call Job/intent only with legitimate observed identifiers;
5. compare every canonical result with an independent owner-native service read;
6. classify client A/B/C/D and backend READY/MISMATCH/UNAVAILABLE;
7. exercise tunnel/service restart and stale-source failures without writes.

### READ-V4 — architecture activation ruling

On proof, protect the direct-MCP-primary-rich-read / SOL_STATE-hot-health role amendment. On failure, repair only the demonstrated layer. Do not release a production write carrier from read success.

### Existing independent write DAG

C1 original effect reconciliation -> S0-R1 grant/verifier/final proof -> one selected write carrier -> harmless canonical admission -> actual worker return/continue/stop journey. No automatic dual armed paths.

## 9. Acceptance standard

The canonical read plane reaches `PROVEN_LIVE` only after all of these hold on one immutable release/generation:

1. current exact-head repository/security checks and independent review;
2. active-owner/path reconciliation and no duplicate service/API/store;
3. default-disabled installation under a dedicated read principal;
4. actual Personal account and correct tunnel/workspace association;
5. all four read tools exercise the canonical service or are truthfully `NOT_EXERCISED` only for absent legitimate IDs;
6. source SHA, proof-source grounding and Runtime generation agree;
7. independent owner-native read comparison matches;
8. missing/unreadable/stale/mismatched/restart/timeout/oversize cases are visible and fail closed;
9. no Runtime, Job, Attempt, Worker, Event, Wake, Agent OS or credential mutation from reads;
10. no access to broad Operator, CeoIngress submit or direct SQLite by the surface principal;
11. source/server/service/tunnel/account receipts return to the same CEO workflow;
12. latency is measured by layer rather than called instantaneous.

A merged implementation without the real account/service journey is `BUILT_NOT_PROVEN`. A connected tunnel using repo-local data is not production acceptance.

## 10. Current capability ledger

| Capability | State | Current truth |
|---|---|---|
| Existing five-tool MCP contract | `BUILT_NOT_PROVEN` | source exists; prior Personal production read not proved |
| Repo-local readonly gateway | `BUILT_NOT_PROVEN` | useful local/fixture path; rejected as canonical production lifecycle reader |
| Canonical Executive service split-root contract | `PROVEN_LIVE` | protected source/config explicitly separates Runtime and proof source; installed current host still unverified |
| Dedicated canonical Executive Read port | `NOT_BUILT` | architecture frozen here; implementation held on active path owners |
| Personal-Pro client behavior | `DARK_OR_DISCONNECTED` | no actual account A/B/C/D result |
| Canonical installed host/tunnel read binding | `DARK_OR_DISCONNECTED` | owner-native census not returned to this program |
| Steward authenticated organizational slice | `BUILT_NOT_PROVEN` | PR #463 is draft and truthful PARTIAL; not full Executive cockpit |
| C1 production proof | `BUILT_NOT_PROVEN` | original Step-D effect unknown |
| S0-R1 | `NOT_BUILT` | final framed proof not run; installed grant blocker remains |
| B2 / C2 | `NOT_BUILT` | held behind current gates and route decision |
| Routine Personal-Pro CEO workflow | `PARTIAL` | SaaS GitHub/Slack work exists; canonical Executive read/write/return proof absent |
| Second backend, copied Runtime or new state store | `REJECTED_BY_DESIGN` | prohibited by this freeze |

## 11. Current effect and exact next action

This architecture is now frozen strongly enough to prevent a wrong production implementation, but no source build is commissioned while active owners overlap.

The exact next action is:

> obtain current-head integrated validation and independent review of this linked records candidate, while the existing W3C/Integration owner returns the already-owed native service/root receipt; after both, reconcile path ownership and commission one canonical Executive Read vertical only if no equivalent accepted owner has already landed it.

The no-code Personal-account manifest test may still occur earlier against the owner-approved existing target for client behavior, but it cannot be called production read proof until the canonical service backend is present and joined.

## 12. Reproducible source manifest

Current protected source and procedure:

- Mastermind `c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36`, tree `95e00ca4e342648796a0e81950052d36b07bf3ef`;
- `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1.

Source files inspected at that exact commit:

- `integrations/executive_mcp/adapter.py`, blob `4c2a48ca15bd535fdc0b9503bb9e5295da16e791`;
- `integrations/executive_mcp/server.py`, blob `c762b2951e4bdad8956b646df58f6cd4609aaf8d`;
- `integrations/executive_mcp/schemas.py`;
- `integrations/mastermind_executive_app/gateway.py`, blob `a9a072f983b01132118a73bd47f5d0db6e5b09ed`;
- `integrations/mastermind_executive_app/admission.py`, blob `86eb14f43ed6eaf43886b885fa992c7d7536e0a7`;
- `control_plane/executive_inbox.py`, blob `f9c92ad181c0c0dda0b70780d8956e90459495a1`;
- `control_plane/executive_service.py`, blob `147b3bb2e5125355b3d35e27c019faf6dd465003`;
- `control_plane/executive_ceo_ingress.py`, blob `42218bf8d2ac07f8a8a98a2950b049f97d18a0f0`;
- `control_plane/executive_dialogue_observation.py`, blob `4861849d42bad5e03f5091c69a528c6588880863`;
- `control_plane/executive_hot_state.py`;
- `ops/executive_os/control.json.template`, blob `d382fbcbd74131de57327e5a514b4b639d9edf28`;
- `docs/EXECUTIVE_MCP.md`, blob `608e8cd18804d595ad069ce5203fb5c0e6db11fc`;
- `docs/CEO_INTENT_BRIDGE.md`, blob `4843320428764f43e249138de0289c4d4badb035`;
- `docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md`;
- `research/EXECUTIVE_OS_PERSONAL_PRO_RELAY_STATE_TRANSPORT_AMENDMENT_2026-08-20.md`, blob `be525a94be465abd220cc5a4a8651dd617e3b2f9`;
- `research/MASTERMIND_SOL_EXECUTIVE_SHELL_PRO_NATIVE_ARCHITECTURE_2026-08-20.md`, blob `88e295b5ec25be28e216bb734c0b068093529c45`.

Related current carriers/candidates:

- PR #491 head `7e6e48da371aeaa35ec65dd5afe89b4017567170` — active Runtime Continuity/service writer;
- PR #492 head `c56e80091c00fc3fce2c5bb130713a2ea30279a2` — Executive Inbox strict-v2 writer;
- PR #463 head `7ffc3821004ab4bf4a63d56f88d18cb5165424d6` — truthful-PARTIAL Steward candidate under product ruling `5553996467`;
- C1 `C0BSBM78V1N/1787889177.672699`;
- W3C host `C0BSBM78V1N/1788521402.466429`;
- Personal-Pro census `C0BSBM78V1N/1788605608.765019`;
- linked records review `C0BSBM78V1N/1788633533.339369`.

Action-time protected source, open PRs, local writers, host generation, account association and carrier state must be re-read before any implementation or production edge.
