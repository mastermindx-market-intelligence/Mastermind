# Mastermind autonomous Executive + agent CLI capability freeze

**Date:** 2026-08-24

**Status:** G0 merged in `ceebc82`; G1 service composition implemented on a production-unarmed carrier; host/runtime requalification and later arming remain separate gates

**G0 freeze base:** `12117ca576cec2c4f054664dd62c4e0809f27e75`

**G1 carrier base:** `ceebc82f74b3101c36f67ca2fa5767a2a9d7453f`

**Lifecycle authority:** Mastermind Executive OS Runtime only

**Knowledge authority:** Macro Agent OS read-only records

**Implementation truth:** protected GitHub history and exact reviewed commits

## 1. Chairman outcome

The operating objective is not “run more CLIs.” It is to remove the Chairman
from routine work transportation:

1. Chairman intent is admitted once as a typed CEO intent.
2. Sol/Fable turns it into one bounded orchestration root.
3. Executive OS creates, claims, supervises, reconciles, reviews, repairs and
   aggregates child Jobs without the Chairman carrying prompts between sessions.
4. Each worker session receives only the exact model, auth realm, MCP servers,
   plugins, skills, native-helper ceiling, filesystem grant and network policy
   that its claimed Job names.
5. Failures become durable Executive events and exception attention. They do
   not become blind retries, duplicate sessions or requests for the Chairman to
   reconstruct state from chat history.

The 10/10 product is an executive workforce, not a bag of logged-in terminals.

## 2. Current capability ledger

| Plane | Current state | Honest ruling |
|---|---|---|
| Agent OS | `PROVEN_LIVE` as durable workstream/decision/discovery/handoff knowledge | It is not a dispatcher, Job store, lease table or session registry. |
| Executive Runtime | `BUILT_NOT_PROVEN / HOST_DISABLED` | SQLite Job/Attempt/Worker/Event authority, broker, supervisor, backup, canary and launchd packaging exist. The installed host points at stale release `b5e45be...`; its formal acceptance is `SPENT_FAILED`, and both services remain deliberately disabled. |
| Phase 1F-C COO hierarchy | `BUILT_NOT_PROVEN / SERVICE_COMPOSED_UNARMED` | Schema v4 and deterministic planner/work/review/repair/aggregation transitions merged in `db0bac5...`. G1 now composes one exact-root action with the existing supervisor and a bounded in-process tick, but checked-in host configuration keeps the arm false and no current host release is installed/requalified. |
| Codex sealed worker | `BUILT_NOT_PROVEN` | One-shot `codex exec --json` with isolated worktree, exact binary and auth home, no MCP/plugins/apps/subagents/network, supervisor-owned validation. The host has not been requalified on current master. |
| Operator Harness / Codex App Server | `BUILT_NOT_PROVEN / DEVELOPMENT_UNARMED` | Durable session epochs, process generations, provider session IDs, turns, crash reconciliation, capability attestation and read-only Codex adapter merged in `4f672b8...`. No production adapter registration/composition exists. |
| Agent OAuth/auth realm | `PARTIAL` | Dedicated worker auth provisioning, metadata checks, account identity probe and one bounded inference readiness receipt exist. Current host receipt is root-private and not currently verified. No copying of the Chairman's default `auth.json` is permitted. |
| MCP/plugin capability control | `PARTIAL` after G0 | Operator Harness can observe skills/MCP/plugins and fail closed. G0 now binds a reviewed execution-profile ID/digest through route, capacity and atomic claim. No production profile grants MCP/plugin tools yet. |
| Native subagents/forks | `SPEC_ONLY / FORBIDDEN_ON_WRITE` | The OHF contract distinguishes native helpers from Executive child Jobs and requires a proven capability ceiling. Current Codex operator adapter truthfully reports no such ceiling. |
| Wake Fabric | `BUILT_NOT_PROVEN / GLOBALLY_UNARMED` | Obligation, route, binding and reconciliation contracts exist. No production Codex App Server transport, scheduler or automatic acknowledgement is armed. |
| Executive MCP | `BUILT_NOT_PROVEN / READONLY_OR_FIXTURE_ONLY` | Five-tool gateway exists; production write admission remains unarmed and must not become the worker/session control plane. |
| Multilogin P0B | `CANARY_FAILED_SAFELY / CREDENTIAL_BLOCKED` | Disposable-only repair merged. Cloud search returned 501/non-JSON and the authenticated launcher returned 401 for the stored bearer. A fresh native secret-boundary automation token is required before read-only revalidation. |

## 3. Canonical architecture

```text
Chairman intent
      |
      v
CEO ingress (typed, idempotent, no execution)
      |
      v
Executive Runtime root Job ---------------------------+
      |                                                |
      v                                                |
Phase 1F-C deterministic COO cycle                     |
planner -> work -> independent review -> repair -> handoff
      |                                                |
      v                                                |
atomic Job claim                                       |
  model route + exact capability-profile digest        |
  + worker slot + quota class + authority grant        |
      |                                                |
      +-------------------+----------------------------+
                          |
             +------------+-------------+
             |                          |
             v                          v
   sealed `codex exec`          Codex App Server OHF
   one-shot worker              semi-headless session
   no native helpers            epoch/generation/turn
             |                          |
             +------------+-------------+
                          v
            supervisor validation + typed result
                          |
                          v
             Executive event / exception / Wake
```

There is one Job/Attempt/Worker/Event authority. Agent OS remains a knowledge
projection. App Server thread IDs live in the existing OHF epoch/generation
lineage, not in Git config, Agent OS, Slack, another database or a “Session OS.”

## 4. Authentication and OAuth law

OpenAI's current Codex surfaces support browser ChatGPT login, device-code
login, API keys, Enterprise access tokens and workload identity. The normal
automation choice is not to remote-control a human login page forever:

- one dedicated provider home per independently claimable worker realm;
- company service-account/Enterprise credential where the plan and workspace
  support it;
- finite expiry, rotation owner and readiness receipt;
- device auth only as an explicit native fallback;
- OS keyring or private worker-owned credential storage;
- no credential bytes in Job constraints, Agent OS, events, MCP, plugins,
  model-visible output, environment inheritance or cross-worker copies;
- no import of the Chairman's default `~/.codex/auth.json`.

`account/read`, login status and auth-file presence are observations. Readiness
requires the existing composite identity + inference canary receipt. A Job may
select only an already-ready worker slot; it may never trigger interactive login.

## 5. Capability-grant law

G0 introduces `mastermind.executive_agent_capabilities/v1` and no new durable
store. The checked-in policy is secret-free and `production_armed=false`.

Every newly routed Job carries:

- `execution_profile_id`;
- `execution_profile_digest`;
- `capability_policy_version`; and
- `capability_policy_digest`.

Every eligible worker quota class must carry the same four values. The existing
claim transaction rejects mismatches and records the selected values in the
existing `JOB_CLAIMED` event. A fallback model list must share one execution
profile; model fallback cannot silently change tool authority.

The profile vocabulary includes execution surface, auth realm, sandbox,
approval, network, write capability, native-helper policy, required skills,
required MCP servers, required plugins and forbidden capability names.

G0 supplies a deterministic compiler from the profile into the existing OHF
`CapabilityManifest`, bound to an exact harness binary digest. G2 must wire that
compiler into Attempt profile sealing and compare the App Server's observed
attestation with the sealed manifest before the first work turn. Until that
integration is proven, App Server profiles remain unlaunchable. Missing,
forbidden, unclassified or wrong-precision capabilities must refuse launch.

No current production profile grants MCP, plugins or native helpers. This is a
truthful readiness seam, not a disguised arm.

## 6. Session and subagent law

An Executive child Job is organizational work. A Codex native subagent/fork is
a subordinate provider handle inside one Attempt. They are not interchangeable:

- native helper output never counts as independent review;
- a write-capable parent cannot enable helpers until the adapter proves a
  machine-enforced child capability ceiling;
- native fork/thread IDs remain subordinate to one OHF epoch;
- a new worker/provider/account/model/auth realm/authority profile consumes a
  new Attempt;
- disconnect/timeout after dispatch is `EFFECT_UNKNOWN`, not permission to
  spawn another session or fail over providers;
- Executive OS, not the model, allocates epoch/generation/turn identities and
  commits intent before provider effects.

The first production semi-headless lane should therefore be a read-only COO
operator session with helpers disabled. Write-capable App Server and native
subagents follow only after exact capability-ceiling proof.

## 7. MCP and plugin law

MCP servers and plugins are capability packages, not authority grants.

1. A profile names exact allowed server/plugin identities.
2. The Attempt binds the profile and harness digest.
3. App Server reports effective config, MCP status and plugins.
4. Unrequested ambient capability refuses a write profile.
5. MCP server OAuth happens through the server's supported OAuth flow and is
   stored in the worker realm, never in Job/Event/Agent OS content.
6. MCP tool calls retain normal approval/authority rules; MCP descriptions and
   results are untrusted data.
7. Production does not depend on App Server's in-development plugin-install RPC.
   Plugins are provisioned and reviewed before a worker slot becomes READY.

The existing Executive MCP gateway remains the Chairman/CEO admission and read
surface. Worker MCP servers are Attempt-scoped execution capabilities. Neither
becomes a generic shell or a second scheduler.

## 8. Frozen rollout sequence

### G0 — exact capability identity at route and claim (this carrier)

- Add the secret-free capability registry and closed loader.
- Bind profiles to logical model aliases.
- Persist profile/policy identity in new routed Job constraints and worker
  capacity metadata.
- Require an exact match during atomic selection/claim and record it in
  `JOB_CLAIMED`.
- Keep production arming false and default profiles extension-free.

### H0 — current exact-master host requalification

- Do not start stale installed release `b5e45be...`.
- From a fresh exact protected-master release, re-run provider readiness, Gate B,
  install and formal acceptance under the existing administrator runbook.
- Preserve the spent failed attempt and archived evidence.
- Requires a native administrator credential and, if the existing worker auth
  is not current, workspace-admin credential action.

### G1 — production COO composition

- Add one installed control-service operation that runs one exact-root
  `CooCycle` action with the existing supervisor as dispatcher.
- Remove the fixed-proof-Job restriction only for command-bound strict-v2
  orchestration Jobs with exact reviewed capability profiles.
- Reconcile active Attempt identity before any new claim.
- Add a bounded service-owned tick over existing eligible roots; no second
  scheduler/table/queue and no fleet-wide blind loop.

G1 implementation binds the host-selected `coo.sealed` alias to the existing
G0 profile/policy identity and two serialized logical cost capacities on the
same dedicated worker identity. `submit-ceo-intent` may add that binding only to
strict v2; the caller still cannot name provider, model, profile or credential
realm. `run-coo-cycle` and the background tick both require
`coo_autonomy_armed=true`, while the checked-in install/template default remains
`false`. A tick selects at most one of 64 bounded strict roots, performs exactly
one deterministic action, and persists a secret-free refusal event when the
autonomous action cannot safely proceed.

### G2 — read-only semi-headless COO session

- Compose the merged OHF runtime port + Codex App Server adapter for one
  dedicated, READY worker slot.
- Use `operator.appserver.readonly.v1`, helpers disabled, network disabled,
  approval never and no MCP/plugins.
- Prove start, turn, stop, process-group cleanup, crash recovery, resume and
  no cross-Attempt session reuse through the real installed path.

### G3 — one bounded MCP/plugin vertical

- Add one real, independently useful read-only MCP server or plugin profile.
- Pin identity/schema/version where the provider can prove it.
- Prove absence from other profiles, refusal on drift and exact tool-call/event
  attribution through one real session.
- Install-time provisioning only; no production dependency on experimental
  plugin-install methods.

### G4 — native subagent ceiling

- Prove the Codex parent can enforce a shrink-only tool/sandbox/network ceiling
  on every native helper.
- Only then allow a read-only native-helper profile.
- Executive independent review remains a different worker/Attempt.

### G5 — exception wake and Control Room projection

- Bind runtime session identity through existing Wake `RuntimeBinding` law.
- Deliver only exception/continuation obligations after G1/G2 are proven.
- Project current Job/Attempt/session/capability/readiness state in the Control
  Room without giving the UI lifecycle ownership.

### G6 — Multilogin disposable revalidation

- Through the native masked API-token control, enroll one current automation
  token without exposing it.
- Prove authenticated launcher status and bounded complete cloud census first.
- Only after a new explicit lifecycle release, run one disposable non-seat
  canary. Chairman seats remain outside the wave.

## 9. Acceptance boundary

“Chairman out of the loop” is proven only when one real typed intent travels the
installed current-release path through planner, worker, independent review,
repair/null outcome as applicable, aggregation and exception projection without
manual prompt carriage, while every Job/Attempt/session/capability join is
receipt-backed.

G0 is complete when focused runtime/router/COO tests and full repository CI pass
and the exact reviewed head merges. It does not claim H0-G6, production service
availability, provider readiness, successful Multilogin canary or an armed
semi-headless session.

## 10. Primary technical references

- OpenAI Codex authentication: <https://learn.chatgpt.com/docs/auth.md>
- Codex non-interactive mode: <https://learn.chatgpt.com/docs/non-interactive-mode.md>
- Codex SDK: <https://learn.chatgpt.com/docs/codex-sdk.md>
- Codex App Server: <https://learn.chatgpt.com/docs/app-server.md>
- Codex MCP configuration and OAuth: <https://learn.chatgpt.com/docs/extend/mcp.md>
- Codex subagent configuration: <https://learn.chatgpt.com/docs/agent-configuration/subagents.md>
