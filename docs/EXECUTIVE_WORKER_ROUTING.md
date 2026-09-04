# Executive worker routing — stage 4

**Status:** R1 shadow evidence and Phase 1F-B are accepted. Phase 1F-C schema-v4
and the explicit bounded COO `run-once` path merged in `db0bac5`. G0 capability
identity merged in `ceebc82`; G1 exact-root service composition merged in
`8602686`; G2 read-only planner composition merged in `c76d55b`; and G3 exact
OpenAI Docs MCP composition merged in `5f58907`. All remain undeployed,
unscheduled, production-unarmed, and unaccepted as live capability. G4 adds one
shrink-only read-only native-helper ceiling to that same planner lane. It does
not arm an App Server, MCP server, plugin, helper, OAuth login or production
worker merely by merging.

This stage makes economical-worker-first execution real without creating a
second queue, teaching Chris tmux, or widening Executive OS or MCP authority.

```text
frontier lead
  plans / judges / escalates
          |
          v
typed bounded work request
          |
          v
deterministic model router (no LLM, no durable state)
          |
          v
Executive OS Job -> atomic worker/quota claim -> existing supervisor
          |                                      |
          v                                      v
read-only planner                       work / review / repair
Codex App Server                        sealed `codex exec --json`
same broker + worker UID                isolated worktree + validation
```

Executive OS SQLite remains the only owner of Jobs, Attempts, Workers, leases,
process identity, results, and events. The router returns suitability decisions
and compatibility constraints. It does not create a queue, hold a lease, launch
a process, poll, retry, or mark work complete.

## 1. Audit findings

| Surface | Current implementation | Stage-1 decision |
|---|---|---|
| tmux | No Mastermind Executive OS tmux launcher exists on `origin/master`. The durable worker path launches a structured, ephemeral `codex exec --json` process. Phase 1C-A uses launchd plus private AF_UNIX control/worker sockets. | Do not add tmux. It remains a possible later PTY transport, never lifecycle truth. |
| Executive OS runtime | `control_plane/executive_runtime.py` already persists workers, quota classes, exact model/effort/cost metadata, Jobs, Attempts, leases, and events. | Reuse it. Add only logical-alias selection and claim evidence. |
| worker launch | `CodexWorkerAdapter` already enforces exact-SHA workspaces, bounded authorities, no network, no MCP, structured output, artifact hashing, and supervisor-owned validation. | Keep it as the first adapter implementation. Generalize the supervisor type boundary, not its safety policy. |
| Codex delegation | `.codex/config.toml` enables bounded native agents; read-only supporting profiles use Terra, while the deep reasoning profile keeps Sol. | Preserve those portfolio-analysis fences. Write-capable implementation remains an Executive Job in its own worktree. |
| `config/agents.yml` | Portfolio reasoning roles still resolve to Sol/xhigh on the Codex production path. | Do not silently downgrade portfolio judgment. Point Executive worker labor to the separate routing policy. |
| Phase 1F | Phase 1F-B supplies the accepted hierarchy baseline. Merged Phase 1F-C additively supplies immutable orchestration placement/principal/grant lineage, closed role results, result seals, deterministic run-once transitions, TX-9 continuity, and schema-v4 migration tooling. | Keep SQLite Runtime as the sole lifecycle authority. The merge is still production-unarmed; no live G0-G7 claim follows from fixture acceptance. |
| execution capability | `config/executive_agent_capabilities.json` plus `control_plane/executive_agent_capabilities.py` defines a secret-free, production-unarmed profile registry. | Route fallback aliases share one profile. Job constraints and worker capacity must match exact profile/policy digests before atomic claim. Provider-process attestation remains a later gate. |
| EXEC-MCP-A | Exactly five tools exist. READONLY refuses the modifying tool; FIXTURE writes only to a temporary service and refuses production paths. No production-write server mode exists. | Make no MCP surface, mode, identity, socket, or peer-UID change. |

## 2. Policy and aliases

The source of routing policy is
`config/executive_worker_routes.json`. It is JSON so the sealed Executive
control-plane runtime can read and validate it with the Python standard library;
it does not acquire a PyYAML dependency.

The source of extension/tool authority is separately
`config/executive_agent_capabilities.json`. The router resolves a logical model
alias to one exact execution-profile ID and digest; model fallback may not change
the profile. This file contains no credential, account ID, native session handle,
MCP OAuth token, plugin state or mutable worker readiness.

The loader fails closed unless:

- `lifecycle_authority` is exactly `executive_os`;
- `production_armed` is exactly `false`;
- every live provider uses an implemented adapter;
- every worker alias belongs to an enabled, autonomous-allowed provider;
- every route's aliases have the declared task capabilities.

### RF1 — provider-neutral suitability tiers

`config/executive_worker_routes.json` is now
`mastermind.executive_worker_routes/v2`. Every worker route/risk is a non-empty
ordered list of exact objects:

```json
{
  "tier_id": "implementation.routine.primary",
  "model_aliases": ["fast.engineering", "standard.engineering"]
}
```

The loader refuses unknown route or tier keys, malformed or duplicate tier IDs,
empty tiers, duplicate aliases inside or across tiers, aliases that are unknown
or not worker-eligible, and aliases that do not meet the route capability
contract. Aliases within one tier must share one execution profile; they are an
equivalence set for suitability, while their declared order remains the existing
compatibility/placement preference inside that tier.

`RoutingDecision.suitability_tiers` is the structured decision. Its
`preferred_model_aliases` property deliberately projects *only the first tier*
for the existing Job constraint schema. `to_dict()` emits both forms, but
`job_constraints()` keeps its pre-RF1 key set so this source wave does not widen
persisted Job bindings. CF2-I is the later, separately reviewed consumer of the
structured tiers.

The selection law is fixed:

```text
authority / Job constraints
        -> required capabilities and independence exclusions
        -> first lawful Model Router suitability tier
        -> Capacity Fabric ranks only candidates inside that tier
        -> Executive OS atomically claims one Worker
```

Capacity, provider health, account availability, host placement, quota and cost
are outside this router. They may rank candidates only inside the first lawful
tier with an eligible candidate; they cannot promote a lower tier, re-admit an
excluded worker, or waive a capability/authority refusal.

The v1-to-v2 migration preserves every current Codex outcome with exactly one
first tier per route: implementation/mechanical/tests routine use
`fast.engineering`, `standard.engineering`; their elevated routes use
`standard.engineering`; research routine uses `fast.research`,
`standard.research`; elevated research uses `standard.research`; and routine or
elevated review uses `standard.review`. No provider, model binding, cost class,
profile, capability, worker eligibility, or production-arm value changes in this
migration.

Current logical aliases:

| Alias | Initial binding | Use |
|---|---|---|
| `frontier.orchestrator` | Sol / xhigh | planning, judgment, escalation; never worker-claimable |
| `coo.operator.readonly` | Sol / xhigh | one bounded read-only COO planner through App Server; worker-claimable only under the exact operator profile and dedicated quota |
| `fast.engineering` | Luna / high | routine bounded implementation, mechanical edits, tests |
| `standard.engineering` | Terra / high | elevated implementation and Luna fallback |
| `fast.research` | Luna / medium | bounded extraction and research |
| `standard.research` | Terra / high | elevated research and Luna fallback |
| `standard.review` | Terra / high | independent review, with builder worker exclusion when supplied |

`qwen`, `glm`, and `xai` are provider aliases only. Their
`openai-compatible` adapter descriptor is deliberately unimplemented and all
three providers are disabled. No model slug, credential, endpoint, quota, or
production capability has been invented for them.

A Codex runtime may later serve a `ceo`-seat technical-staff commission under a
separate authority grant. The router never grants that seat, any executive role,
review independence, merge/deploy rights, retry authority, or security authority
from a provider or model alias. In particular, `frontier.orchestrator` remains a
non-worker `frontier_lead` outcome even though it names a Codex/Sol model.

## 3. Deterministic rules

The request vocabulary is intentionally small:

- `task_kind`: `implementation`, `mechanical`, `tests`, `research`, `review`,
  `planning`, `judgment`, or `escalation`;
- `risk`: `routine`, `elevated`, or `critical`;
- `ambiguity`: `low`, `medium`, or `high`;
- additional required capabilities;
- worker IDs to exclude, primarily for review separation.

Routing law:

1. Planning, judgment, escalation, critical work, or high-ambiguity work returns
   `frontier_lead`. It cannot be converted into worker Job constraints.
2. Routine implementation/tests/mechanical work returns one current-equivalence
   primary tier containing Luna then Terra.
3. Routine research returns one current-equivalence primary tier containing Luna
   then Terra.
4. Elevated implementation/research returns one Terra primary tier.
5. Review returns one Terra review primary tier. A supplied builder worker ID is
   excluded before the atomic claim.
6. Within the selected suitability tier, Executive OS keeps its stable worker-ID
   and quota-class tie-break after the compatibility projection. Later
   accounts/providers require their own reviewed suitability/capacity wave; they
   cannot change Job semantics merely by appearing in a provider dictionary.
7. A routed Job can only claim quota capacity registered under the same routing
   policy version. Stale alias registrations fail closed instead of silently
   inheriting a changed binding.

The claim transaction records the policy version, first-tier compatibility
aliases, selected alias, and reason codes in the existing `JOB_CLAIMED` event.
There is no router ledger, capacity claim, provider enablement, or production
effect in RF1.

## 4. Adapter layer

`control_plane.worker_adapter.WorkerExecutionAdapter` defines the minimum
provider-neutral interface the existing supervisor consumes:

```text
start
collect_result
cancel
run_validation_argv
process inspector
```

The existing `CodexWorkerAdapter` and remote broker adapter already satisfy that
shape. Optional stronger evidence—launch attestation, whole-UID sweep receipt,
and unbound-run cleanup—remains feature-detected and may be required by the host
policy.

Adding a provider later requires a reviewed adapter implementation. Changing a
provider alias in JSON cannot make an unimplemented adapter runnable.

## 5. Operator proof without tmux

These commands are an operator/CI proof surface. They are not chores Chris must
perform for every objective.

Preview a route without opening or modifying Executive OS state:

```bash
python -m scripts.executive_os_phase1b route implementation
python -m scripts.executive_os_phase1b route research --risk elevated
python -m scripts.executive_os_phase1b route judgment
```

Register one fixture/local Codex worker from a reviewed logical alias. The
provider, exact model, effort, cost class, capabilities, and adapter are policy
derived; raw values cannot be mixed with `--model-alias`:

```bash
python -m scripts.executive_os_phase1b --root /absolute/fixture-root \
  register-worker luna-01 \
  --account-label codex-worker-account-01 \
  --model-alias fast.engineering
```

Create one bounded routed Job in the same Executive OS database:

```bash
python -m scripts.executive_os_phase1b --root /absolute/fixture-root \
  create-job "Implement the bounded parser change" \
  --task-kind implementation \
  --authority READ \
  --authority WRITE_BRANCH \
  --allowed-write-path control_plane/parser.py
```

Frontier leads can create bounded children through the same router-backed command
by adding `--parent-job-id`. Review-required children and sibling review jobs use
`--review-required` and `--reviews-job-id`; the durable runtime refuses parent
claims while children are living and refuses parent completion without an
independent completed `approve` verdict. `business_impact` is display/audit
metadata only and never becomes a priority key.

The existing explicit `run-once` path launches it through the attested Codex
adapter. It does not open or attach a tmux session. Production Phase 1C-A remains
proof-job-only in this stage, so none of the commands above arms the installed
service.

The Phase 1F-C caller is separate and names one already-created strict-v2 root:

```bash
python -m scripts.executive_os_coo_cycle --root /absolute/fixture-root \
  run-once --parent JOB-nnn
```

One invocation recomputes canonical runtime state, commits at most one top-level
cycle action under a deterministic command ID, and exits. Import and help are
read-only. The command does not create or migrate a database, select a parent,
loop, schedule, contact a provider, install a host service, or arm production.
The separate offline v3-to-v4 migration CLI is the only supported upgrade path.

## 6. Migration and rollout

### Wave R0 — merged policy seam (this change)

- Land the unarmed policy, router, alias-aware claim ordering, adapter protocol,
  tests, and this guide.
- Preserve all legacy Jobs: a Job without `preferred_model_aliases` keeps the
  previous stable worker/quota ordering.
- Keep EXEC-MCP-A READONLY/FIXTURE only.

### Wave R1 — fixture and shadow evidence — accepted

- The deterministic fixture harness registers dedicated Luna/Terra logical
  capacity and runs representative implementation, research, tests, and review
  Jobs.
- Evidence and limitations are recorded in
  `research/EXECUTIVE_OS_R1_SHADOW_EVIDENCE_2026-08-16.md`.
- No provider, MCP, live worker slot, or write-capable adapter is invoked.

### Wave Phase 1F-B — durable hierarchy — accepted

- Durable parent/child schema, immutable hierarchy, bounded depth, seat/impact
  fields, fail-closed verdicts, independent-review evidence, aggregation
  refusals, and inbox v2 projection are implemented and tested.
- Phase 1F-C remains a separate run-once COO cycle and introduces no queue or
  state store.

### Wave Phase 1F-C — inert COO cycle — merged, production-unarmed

- Schema v4, closed typed orchestration evidence, command-aware exact-ID cycle
  transitions, offline migration, and deterministic acceptance merged in
  `db0bac5`.
- No provider capacity, host database, service, scheduler, external adapter,
  credential, or production flag is changed.
- Merge is not deployment, host acceptance, scheduling or production arming;
  G0-G7 remain distinct later proof/arming gates.

### Wave G0 — capability identity at route/claim — production-unarmed

- New routed Jobs carry exact execution-profile and capability-policy identity.
- Model aliases in one fallback route must share one profile.
- Worker quota metadata must match all profile/policy identity fields before
  selection or claim.
- `JOB_CLAIMED` records the selected profile/policy identity.
- Default worker profiles remain extension-free; no MCP/plugin/native-helper
  capability is production-granted by this wave.

### Wave G1 — exact-root COO service composition — production-unarmed

- The existing control service can run one deterministic action for one
  host-bound strict-v2 root through the existing supervisor.
- A reviewed `coo.sealed` alias supplies exact model/profile identity; the CEO
  envelope cannot choose provider, model, profile, credential realm or quota.
- One existing worker identity receives serialized `small` and `default` COO
  quota classes so plan-selected cost class does not create an implicit fallback.
- A bounded in-process tick considers no more than 64 roots, advances at most
  one root/action per interval, and creates no queue, scheduler table, session
  registry or second lifecycle authority.
- Checked-in host configuration keeps `coo_autonomy_armed=false`; merge is not
  host install, provider readiness, service activation or production proof.

### Wave G2 — read-only semi-headless planner composition — production-unarmed

- One `plan` role may select only `coo.operator.readonly`, whose exact profile
  is `operator.appserver.readonly.v1`: read-only sandbox, approval `never`,
  network disabled, and no skills, MCP servers, plugins/apps, native helper or
  subagent ceiling.
- App Server is not a daemon beside Executive OS. The worker broker starts it
  as one generation under the existing dedicated worker UID, while Executive
  Runtime remains sole owner of Job, Attempt, lease, Worker, epoch, generation,
  operation and terminal-result truth.
- Control startup attests the broker's exact installed Codex binary digest,
  version and arm state before an armed service can become ready. Claim again
  binds the exact capability-policy/profile digest, model, effort, cost class,
  harness digest and harness version.
- A normal planner Attempt starts one provider session, starts and collects one
  turn, seals the typed role result, proves the entire worker generation dead
  and its provider writer released, abandons the epoch, and only then completes
  the Attempt and releases quota.
- On control restart, a still-live G1 is reconnected without a second
  generation; if its first turn was not yet issued, that same G1 may issue it.
  A G1 proven dead and writer-released may resume the same provider session as
  exactly G2 only from the frozen pre-candidate state with one exact
  acknowledged G1 turn. No G3 and no cross-Attempt session reuse are allowed.
  A dead pre-turn G1 and all ambiguous identity/effect evidence remain fenced
  and quarantined rather than widening the frozen recovery predicate.
- If the typed role result was already durably sealed before the crash,
  recovery never recollects or resumes provider work. It stops a live writer or
  accepts an exact dead/released observation, abandons the epoch, and completes
  from the hash-checked existing seal.
- Durable cancellation wins recovery. Before-session cancellation releases
  without constructing an adapter; a live generation is cancelled; an absent
  generation is accepted only with `PROVEN_DEAD / RELEASED`; in all cases the
  epoch is abandoned before Runtime marks the Job cancelled and releases its
  slot. Cancellation never collects or resumes work.
- Checked-in control and worker configs keep both COO autonomy and Operator
  Harness arming false. Unit/integration proof is therefore
  `BUILT_NOT_PROVEN / SERVICE_COMPOSED_UNARMED`, not host installation, provider
  readiness, service activation, or live planner proof.
- MCP/plugin grants, native helpers, subagents, dynamic plugin installation and
  OAuth enrollment remain later, separately reviewed capability waves.

### Wave G3 — governed read-only MCP composition — production-unarmed

- Only `coo.operator.readonly` moves to
  `operator.appserver.readonly.docs-mcp.v1`. Frontier planning and every sealed
  CLI worker remain extension-free. The granted remote endpoint is exactly
  `https://developers.openai.com/mcp`; its expected server identity/version are
  `openai-docs-mcp` / `1.0.0`, auth status is `unsupported`, and its only tools
  are `fetch_openai_doc` and `search_openai_docs`.
- Before launch, the broker clears ambient MCP servers, plugins, configured
  skills, apps and native-agent features. It then supplies only the reviewed
  MCP URL, required-startup bit, exact tool allow-list and automatic approval
  mode. `--strict-config` makes an unknown override a launch refusal.
- App Server attestation binds the security-relevant `config/read` projection,
  effective skills/plugins/MCP census, server identity, version, auth status,
  and normalized tool-schema digest to the requested Attempt. Missing or extra
  capability, a changed URL, feature flag, tool, annotation, schema, server
  identity/version/auth status, or config digest refuses work before the turn.
- `network_policy=disabled` still governs model shell/tool network access. The
  separately named remote MCP grant is the only reviewed outbound knowledge
  capability in this profile; it has read-only/non-destructive tool annotations
  sealed into the tool-schema digest.
- A secret-free developer-host probe against installed Codex `0.147.0` resolved
  the expected server and two tools. The normalized tool-schema digest is
  `9c6e56942336e507f7fb8e3cb781288c40028b2284c2b2d629e262521d66f8e7`; the
  security-config digest is
  `75ceb3e6e26ee770084d0d87923aa048b46415c11f1aac93d234559c61173629`.
  This proves protocol composition, not a worker-authenticated turn or installed
  service acceptance.
- Plugin grants remain empty. App Server plugin install/uninstall RPCs are not a
  production dependency. OAuth enrollment and native helpers/subagents remain
  separately reviewed gates. Checked-in arming remains false, so G3 is
  `BUILT_NOT_PROVEN / SERVICE_COMPOSED_UNARMED` until host install, dedicated
  worker authentication and a real attributed planner/tool-call receipt pass.

### Wave G4 — shrink-only native helper composition — production-unarmed

- Only `coo.operator.readonly` moves to
  `operator.appserver.readonly.docs-mcp.native-helper.v1`. The parent remains
  `gpt-5.6-sol` / `xhigh`, read-only, approval `never`, shell/tool network
  disabled, and limited to the exact OpenAI Docs MCP grant. Every sealed CLI
  worker and every write-capable profile keeps native helpers disabled.
- Codex Multi-Agent V2 is pinned with hidden per-spawn role/model/effort
  metadata, one spawned helper per session, total root-plus-helper concurrency
  two, depth one, and a 60-second helper runtime. The child inherits the
  parent's model, reasoning effort, sandbox, network, skills, MCP and plugin
  surface; the model cannot select a broader role or model at spawn time.
- The security-config digest is
  `89612a1d7a64a77b9b42fab1522cab3465a7a763ba5be696f8a952ba7eaa366f`;
  the capability-policy digest is
  `b8fbfd9065764206b03f835f7fbc09910326f806584a8185229474aff59008b7`;
  and the exact profile digest is
  `536853fb01d69ae8deca9a028b55c90aea0d1529f1fc80d83bb20d5d54f2cc44`.
- Work cannot begin unless `config/read` matches the sealed helper ceiling and
  the adapter reports `VERIFIED`, not `UNKNOWN` or a constructor assertion.
  Turn completion is insufficient: before candidate collection the adapter
  reconciles redacted `collabAgentToolCall` / `subAgentActivity` events against
  a bounded `thread/list` census and exact `thread/read` parent, session-tree,
  workspace, depth, role and source lineage. Missing, duplicate, hidden,
  over-depth, per-spawn-override or extra children become effect-unknown config
  drift.
- A native helper is a subordinate handle inside the same Attempt and OHF
  epoch. Its output never satisfies independent review, never creates an
  Executive child Job, and never owns retry/failover. A different worker,
  account, model, auth realm, authority profile or independent reviewer remains
  a new Executive Attempt.
- Authentication is not performed by a Job. The broker may select only a
  dedicated worker realm already covered by the current composite
  provider-readiness receipt. Login, service-token enrollment, rotation and
  device authorization remain native administrator actions outside Job/model
  content, and the Chairman's default provider home is never imported.
- Plugin grants remain exactly empty until installed-bundle identity and tool
  attestation exist. Dynamic plugin install/uninstall RPCs remain outside the
  production path. G4 therefore remains
  `BUILT_NOT_PROVEN / SERVICE_COMPOSED_UNARMED` until exact-master host install,
  worker readiness, formal acceptance and one real attributed parent/helper
  turn pass.

### Wave R3 — reviewed Codex capacity composition

- Prove one dedicated OS principal and provider home per concurrently claimable
  worker slot.
- Add the slots to the existing host configuration and SQLite worker registry.
- Preserve the current authority set, exact-SHA workspace, UID isolation,
  attestation, validation, and reconciliation gates.
- Activation is a separate host review and acceptance event; merging R0 does not
  activate R3.

### Wave R4 — one external provider at a time

- Implement one adapter and its typed failure mapping.
- Verify provider terms, credential isolation, structured output, session
  identity, cancellation, checkpoint/handoff, and quota evidence.
- Enable a provider alias only after fixture acceptance and fresh security
  review. Qwen/GLM/xAI remain disabled until their own wave passes.

### Wave R5 — CEO production write arm (separate program)

- EXEC-MCP-B remains independent from worker routing.
- Do not add raw worker selection, tmux, shell, provider credentials, or adapter
  tools to the CEO MCP surface.
- A future production submission still creates a bounded parent intent in the
  same Executive OS; routing happens below it.

## 7. Rollback

Rollback is configuration- and code-safe:

1. stop creating Jobs with `preferred_model_aliases`;
2. drain any newly registered fixture worker slots through the existing worker
   status path;
3. legacy Jobs continue to use the pre-existing provider/model/quota filters and
   stable tie-break;
4. no database migration, new queue, MCP tool, production socket, or credential
   store needs to be removed.

The stop conditions are simple: unexpected authority expansion, unexplained
placement, lower-quality workers consuming more frontier repair/review capacity
than they save, or any need for a second lifecycle authority.
