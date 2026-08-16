# Executive worker routing — stage 1

**Status:** implemented policy and adapter seam; fixture/local execution only by
explicit operator action; **no new production arming**.

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
          |
          v
Codex CLI adapter -> Luna or Terra -> isolated worktree -> validation
```

Executive OS SQLite remains the only owner of Jobs, Attempts, Workers, leases,
process identity, results, and events. The router returns constraints and a
ranked logical alias list. It does not create a queue, hold a lease, launch a
process, poll, retry, or mark work complete.

## 1. Audit findings

| Surface | Current implementation | Stage-1 decision |
|---|---|---|
| tmux | No Mastermind Executive OS tmux launcher exists on `origin/master`. The durable worker path launches a structured, ephemeral `codex exec --json` process. Phase 1C-A uses launchd plus private AF_UNIX control/worker sockets. | Do not add tmux. It remains a possible later PTY transport, never lifecycle truth. |
| Executive OS runtime | `control_plane/executive_runtime.py` already persists workers, quota classes, exact model/effort/cost metadata, Jobs, Attempts, leases, and events. | Reuse it. Add only logical-alias selection and claim evidence. |
| worker launch | `CodexWorkerAdapter` already enforces exact-SHA workspaces, bounded authorities, no network, no MCP, structured output, artifact hashing, and supervisor-owned validation. | Keep it as the first adapter implementation. Generalize the supervisor type boundary, not its safety policy. |
| Codex delegation | `.codex/config.toml` enables bounded native agents; read-only supporting profiles use Terra, while the deep reasoning profile keeps Sol. | Preserve those portfolio-analysis fences. Write-capable implementation remains an Executive Job in its own worktree. |
| `config/agents.yml` | Portfolio reasoning roles still resolve to Sol/xhigh on the Codex production path. | Do not silently downgrade portfolio judgment. Point Executive worker labor to the separate routing policy. |
| Phase 1F | The merged contract designs hierarchical children, independent review, and the run-once COO cycle, but 1F-B/1F-C are not implemented on `origin/master`. | Stage 1 routes existing bounded Jobs. It does not pretend the full parent/child cycle already exists. |
| EXEC-MCP-A | Exactly five tools exist. READONLY refuses the modifying tool; FIXTURE writes only to a temporary service and refuses production paths. No production-write server mode exists. | Make no MCP surface, mode, identity, socket, or peer-UID change. |

## 2. Policy and aliases

The source of routing policy is
`config/executive_worker_routes.json`. It is JSON so the sealed Executive
control-plane runtime can read and validate it with the Python standard library;
it does not acquire a PyYAML dependency.

The loader fails closed unless:

- `lifecycle_authority` is exactly `executive_os`;
- `production_armed` is exactly `false`;
- every live provider uses an implemented adapter;
- every worker alias belongs to an enabled, autonomous-allowed provider;
- every route's aliases have the declared task capabilities.

Current logical aliases:

| Alias | Initial binding | Use |
|---|---|---|
| `frontier.orchestrator` | Sol / xhigh | planning, judgment, escalation; never worker-claimable |
| `fast.engineering` | Luna / high | routine bounded implementation, mechanical edits, tests |
| `standard.engineering` | Terra / high | elevated implementation and Luna fallback |
| `fast.research` | Luna / medium | bounded extraction and research |
| `standard.research` | Terra / high | elevated research and Luna fallback |
| `standard.review` | Terra / high | independent review, with builder worker exclusion when supplied |

`qwen`, `glm`, and `xai` are provider aliases only. Their
`openai-compatible` adapter descriptor is deliberately unimplemented and all
three providers are disabled. No model slug, credential, endpoint, quota, or
production capability has been invented for them.

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
2. Routine implementation/tests/mechanical work prefers Luna and falls back to
   Terra.
3. Routine research prefers Luna and falls back to Terra.
4. Elevated implementation/research goes directly to Terra.
5. Review goes to the Terra review alias. A supplied builder worker ID is
   excluded before the atomic claim.
6. Within the same logical alias, Executive OS keeps its stable worker-ID and
   quota-class tie-break. Later accounts/providers can therefore be added under
   the alias without changing Job semantics.
7. A routed Job can only claim quota capacity registered under the same routing
   policy version. Stale alias registrations fail closed instead of silently
   inheriting a changed binding.

The claim transaction records the policy version, ranked aliases, selected
alias, and reason codes in the existing `JOB_CLAIMED` event. There is no router
ledger.

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

The existing explicit `run-once` path launches it through the attested Codex
adapter. It does not open or attach a tmux session. Production Phase 1C-A remains
proof-job-only in this stage, so none of the commands above arms the installed
service.

## 6. Migration and rollout

### Wave R0 — merged policy seam (this change)

- Land the unarmed policy, router, alias-aware claim ordering, adapter protocol,
  tests, and this guide.
- Preserve all legacy Jobs: a Job without `preferred_model_aliases` keeps the
  previous stable worker/quota ordering.
- Keep EXEC-MCP-A READONLY/FIXTURE only.

### Wave R1 — fixture and shadow evidence

- Register separate fixture workers for Luna and Terra through reviewed Codex
  homes.
- Run representative implementation, research, tests, and review Jobs.
- Compare completion quality, validation pass rate, repair rate, latency, and
  usage against the former all-Sol baseline.
- Shadow every proposed production placement before any live worker-slot
  registration change.

### Wave R2 — hierarchical orchestration

- Implement and independently review Phase 1F-B first: parent/child schema,
  aggregation refusals, review verdicts, and inbox evidence.
- Implement Phase 1F-C second: bounded, subtree-scoped, run-once COO cycle.
- The cycle calls this router while creating child Jobs; it does not get another
  queue or state store.

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
