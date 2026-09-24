# Mastermind autonomous Executive + agent CLI capability freeze

**Date:** 2026-08-24

**Status:** G0-G3 merged through exact protected master
`5f58907a5bf51fa77559a87f6028ffcc8490adb8`; G4 native-helper ceiling is
implemented on a production-unarmed carrier based on that exact commit. Host
installation, worker readiness, formal acceptance, real parent/helper proof and
production arming remain separate gates.

**G0 freeze base:** `12117ca576cec2c4f054664dd62c4e0809f27e75`

**G1 carrier base:** `ceebc82f74b3101c36f67ca2fa5767a2a9d7453f`

**G2 merge:** `c76d55b526eb69505ddf41a942e8d2cd663ab3a4`

**G3 merge / G4 carrier base:** `5f58907a5bf51fa77559a87f6028ffcc8490adb8`

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
| Operator Harness / Codex App Server | `BUILT_NOT_PROVEN / SERVICE_COMPOSED_UNARMED` | Durable session epochs, process generations, provider session IDs, turns, crash reconciliation, capability attestation and the read-only Codex adapter are composed into the G2 planner path. G3 adds exact Docs MCP attestation and G4 adds exact native-child event/tree reconciliation. No current host release is installed, armed or accepted. |
| Agent OAuth/auth realm | `PARTIAL / NATIVE_GATE_REQUIRED` | Dedicated worker auth provisioning, metadata checks, account identity probe and one bounded inference readiness receipt exist. A Job can select only an already-ready slot and never logs in. Current host receipt is root-private and not currently verified. No copying of the Chairman's default `auth.json` is permitted. |
| MCP/plugin capability control | `BUILT_NOT_PROVEN / PLUGINS_EMPTY` | G3 binds the exact unauthenticated OpenAI Docs MCP server, version, two-tool allow-list and normalized schema through route, capacity, claim and App Server attestation. Plugin grants remain empty because exact installed-bundle attestation does not yet exist. |
| Native subagents/forks | `BUILT_NOT_PROVEN / READ_ONLY_G4_UNARMED` | G4 pins Multi-Agent V2 to inherited parent capability, hidden per-spawn metadata, one helper, depth one and 60 seconds; it reconciles redacted collaboration events with exact App Server child lineage before result collection. Write-capable helpers remain forbidden and native output is not independent review. |
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

G0 introduced the capability registry; G4 advances its closed schema to
`mastermind.executive_agent_capabilities/v3` without adding a durable store.
The checked-in policy remains secret-free and `production_armed=false`.

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

The registry supplies a deterministic compiler from the profile into the
existing OHF `CapabilityManifest`, bound to an exact harness binary digest. G2
wired it into Attempt profile sealing and App Server pre-turn comparison; G3
added exact MCP/config attestation; G4 adds the exact native-helper grant and
requires the observed helper ceiling to be `VERIFIED`. Missing, forbidden,
unclassified or wrong-precision capabilities refuse launch.

The selected read-only planner profile now grants the exact Docs MCP capability
and one inherited native helper. Checked-in service and capability arming remain
false, every write profile remains extension/helper-free, and plugin grants
remain empty. This is a truthful composition seam, not a live claim.

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

The first production semi-headless lane remains the read-only COO operator. G4
allows at most one subordinate helper only because the parent launch pins the
same read-only sandbox, disabled shell network, exact Docs MCP surface, empty
plugin/skill surface, hidden role/model/effort overrides, depth one and a
60-second runtime. The child census and lineage are audited before candidate
collection. Write-capable App Server helpers remain forbidden.

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

### G0 — exact capability identity at route and claim — merged

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

### G1 — production COO composition — merged, production-unarmed

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

### G2 — read-only semi-headless COO session — merged, production-unarmed

- Compose the merged OHF runtime port + Codex App Server adapter for one
  dedicated, READY worker slot.
- Use `operator.appserver.readonly.v1`, helpers disabled, network disabled,
  approval never and no MCP/plugins.
- Prove start, turn, stop, process-group cleanup, crash recovery, resume and
  no cross-Attempt session reuse through the real installed path.

### G3 — one bounded MCP vertical — merged, production-unarmed

- Add one real, independently useful read-only MCP server or plugin profile.
- Pin identity/schema/version where the provider can prove it.
- Prove absence from other profiles, refusal on drift and exact tool-call/event
  attribution through one real session.
- Install-time provisioning only; no production dependency on experimental
  plugin-install methods.

### G4 — native subagent ceiling — implemented on this carrier

- `coo.operator.readonly` alone selects
  `operator.appserver.readonly.docs-mcp.native-helper.v1`.
- The exact profile digest is
  `536853fb01d69ae8deca9a028b55c90aea0d1529f1fc80d83bb20d5d54f2cc44`,
  policy digest is
  `b8fbfd9065764206b03f835f7fbc09910326f806584a8185229474aff59008b7`,
  helper-grant digest is
  `2d5929ea453f368e7b3284b8509fd6e70d5ac16409642c216217c8fb78908c40`,
  and security-config digest is
  `89612a1d7a64a77b9b42fab1522cab3465a7a763ba5be696f8a952ba7eaa366f`.
- Launch pins `gpt-5.6-sol` / `xhigh`, read-only / approval-never / network
  disabled, exact inherited capabilities, hidden spawn metadata, one helper,
  depth one and 60 seconds. Any unknown or changed ceiling refuses before work.
- Collaboration event prompts are discarded; only bounded redacted state and
  subordinate IDs are retained. Candidate collection requires exact
  event-to-`thread/list`/`thread/read` reconciliation of parent, session tree,
  workspace, role, source and depth.
- The native helper remains inside one Attempt/OHF epoch and never satisfies
  independent review. Every write profile keeps helpers disabled.
- Jobs never perform login. Only an already-ready dedicated worker realm may be
  selected; enrollment, rotation and device authorization remain explicit
  native administrator actions.

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

G4 code is complete only when focused adapter/runtime/router/COO tests and the
full repository discovery-first gate pass and the exact reviewed head merges.
That still does not claim H0/G5-G6, production service availability, provider
readiness, successful Multilogin canary or an armed semi-headless session. Live
acceptance additionally requires current-master host install, formal acceptance
and one real typed Chairman intent with exact parent/helper/MCP lineage receipts.

## 10. Primary technical references

- OpenAI Codex authentication: <https://learn.chatgpt.com/docs/auth.md>
- Codex non-interactive mode: <https://learn.chatgpt.com/docs/non-interactive-mode.md>
- Codex SDK: <https://learn.chatgpt.com/docs/codex-sdk.md>
- Codex App Server: <https://learn.chatgpt.com/docs/app-server.md>
- Codex MCP configuration and OAuth: <https://learn.chatgpt.com/docs/extend/mcp.md>
- Codex subagent configuration: <https://learn.chatgpt.com/docs/agent-configuration/subagents.md>
