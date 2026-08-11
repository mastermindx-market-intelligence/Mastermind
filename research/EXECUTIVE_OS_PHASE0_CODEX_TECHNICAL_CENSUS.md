# Mastermind Executive OS — Phase 0 Codex Technical Census

**Status:** reconnaissance and architecture recommendation only

**Census date:** 2026-08-11

**Mastermind source:** `origin/master@c8fac6b4bd8a95d56010c20b579875c1017289e5`

**External Macro evidence:** relevant producer files inspected at `80c527b96aeac957e5611baacd41c34918e4f301`; the local `origin/main` advanced to `84d1317619951c4ef290de4bad8cb40a5668107a` before this report closed, with no cited Metabolism, Prophet, Neural Web, or workflow files changed between those revisions

**Operating phase:** PRE-REVENUE MVP CONVERGENCE

## Executive verdict

Mastermind already has a real financial runtime and a useful portfolio control-plane substrate. It does **not** yet have an Executive OS.

The repository has scheduled portfolio jobs, same-host locks, start/end telemetry, authority documentation, typed research adapters, experiment ledgers, exact-SHA deployment, and several strong provenance patterns. It does not have a durable Job object, worker registry, transactional queue, lease/heartbeat, addressable process, generic retry, cancellation, restart reconciliation, dependency graph, structured cross-worker result, or runtime authorization engine.

The correct foundation is therefore:

1. extend the existing `control_plane` package rather than create a parallel orchestrator;
2. add a small transactional Executive state store on the canonical VPS data mount;
3. run a separate, non-root Executive supervisor and launch coding agents under a still-lower-privilege OS identity or container with an allowlisted environment;
4. absorb the useful envelope from `bridge/job_runner.py` and the invocation mechanics from the Codex and Claude bridges;
5. keep Mastermind's portfolio learning and Macro's Metabolism, Prophet, and Neural Web systems as domain services connected by typed artifact references; and
6. prove one Codex worker and one Claude worker before naming or provisioning a ten-worker fleet.

This is an extension of the current control plane, not a second control plane. APScheduler remains responsible for established financial cadence. The Executive OS becomes the source of truth only for objectives, jobs, attempts, workers, decisions, and result artifacts.

## Census boundary and evidence standard

The census covered the requested files plus their live call sites, deployment path, CI path, process model, external Macro ownership boundary, and current VPS topology. “Safe for Executive OS state” means a mechanism can survive restart, reject concurrent lost updates, preserve identity and lifecycle transitions, support reconciliation, and answer current state without inferring it from logs. Merely surviving on disk is not enough.

Important evidence caveats:

- [`data/census/latest.json`](../data/census/latest.json) is a generated snapshot from 2026-07-16 at `131290a`, not a current runtime inventory. It lists 22 jobs, including retired `daily_loop`, `heavyweight_daily`, and `etf_daily` jobs.
- Current source declares 19 APScheduler registrations. The authoritative VPS suppresses conditional `vps_state_sync`, so the live scheduler has 18 registered portfolio jobs.
- [`scripts/system_census.py`](../scripts/system_census.py) statically parses source. It cannot resolve environment-conditioned registration or middleware behavior and currently omits routes in `app/pfolio.py`.
- Live health at the census baseline reported Mastermind `c8fac6b4...`, paper-only mode, a healthy scheduler, and the Codex-first reasoning waterfall. The public Mastermind health surface is `https://bot.mastermind-x.com/health`; `mastermind-x.com/api/health` belongs to the Macro product.
- No secret values were read or recorded. The security census used service configuration and environment **names** only.

---

## 1. Existing Runtime Architecture

### 1.1 Primary portfolio runtime

The authoritative runtime is a single FastAPI/uvicorn process supervised by systemd. The process starts an in-process APScheduler and executes portfolio jobs as Python calls. It is a capable application runtime, but its task model is function-oriented rather than job-oriented.

```text
systemd start or restart
→ FastAPI startup (`app/main.py::_start_scheduler`)
→ APScheduler `BackgroundScheduler` (`app/scheduler.py::start`)
→ statically registered Python job wrapper
→ `control_plane.run_ledger.start_run()` + local `flock`
→ in-process portfolio / brain / data-layer function
→ JSON, JSONL, SQLite, or external artifact write
→ domain-specific validation / forward evaluation / guardrail
→ `end_run(ok|error)` and best-effort run event
→ next cron occurrence, special-case retry, or supervisor restart
```

Concrete surfaces:

| Stage | Current implementation | What actually happens |
|---|---|---|
| Trigger | `app/main.py:199-305`, `app/scheduler.py:1513-1657` | FastAPI startup creates the scheduler. Cron triggers register 19 source jobs; authoritative mode omits `vps_state_sync` for 18 live registrations. |
| Controller | `app/scheduler.py:1469-1676` | APScheduler starts paused, removes retired persisted jobs, runs a pending-target cutover preflight, then resumes. Production deliberately uses `MemoryJobStore`. |
| Task/run object | `control_plane/run_ledger.py:71-202` | A process-local `RunHandle` records `run_id`, job, book, trigger, and monotonic start. There is no persisted Job, assignment, or attempt object. |
| Execution | Job wrappers in `app/scheduler.py` | Most work is a direct Python function call in the web process. Some steps launch bounded subprocesses. Startup/manual runs may use anonymous daemon threads. |
| Concurrency | `control_plane/locks.py:113-186` | Nonblocking POSIX `flock` prevents a duplicate in the same lock namespace. A conflict is skipped and logged; there is no wait, lease, fencing token, or fleet owner. |
| State | `/opt/mastermind-live-data` bind-mounted to `/opt/mastermind/data` | Domain files persist across code deploys and process restarts on the one VPS. Scheduler registrations and retry counters do not. |
| Result | Domain-specific files and return values | Portfolio account/decision files, agenda, experiment records, ledgers, snapshots, and logs are written independently; there is no common `WorkerResult`. |
| Validation | Deterministic portfolio checks, packet gate, guardrails, forward evaluation, CI | Validation is strong inside some financial lanes but is not a generic job acceptance contract. |
| Completion/failure | `run_events.jsonl`, domain logs, wrapper exception handling | Start/end/step events are best-effort. A crash can leave an unmatched start forever. Some multi-step wrappers log child failure yet still end the parent run as `ok`. |

The active schedule is `macro_refresh`, `daily_mark`, three active autonomous book runs, two settlement jobs, two overnight watchers, intraday de-risking, Macro snapshot publication, weekly CIO and improvement agenda, daily loop maintenance and experiment maturity, two portfolio-risk jobs, and quote prewarming. `vps_state_sync` exists only outside authoritative mode. The old Flagship/Heavyweight/ETF scheduler entries are archived, although compatibility wrappers and health labels remain.

The boot contract is stronger than the job contract. FastAPI refuses to stay healthy if APScheduler cannot start (`app/main.py:239-261`), and a 60-second watchdog exits with code 70 if the scheduler thread dies (`app/main.py:263-279,636-668`) so systemd can restart the service. This recovers the process, not individual runs.

### 1.2 Manual and first-run execution

Manual autonomous endpoints provide a blocking `wait=true` path using `asyncio.to_thread`, but the default path creates an anonymous daemon thread and returns only `{"started": true}` (`app/main.py:331-549`). Startup first-runs use the same pattern (`app/scheduler.py:1777-1954`). These executions are not addressable after launch: the caller receives no run ID, PID, status resource, cancellation token, or durable resume handle.

This is acceptable for legacy compatibility but must not become the worker model. The Executive OS should wrap or replace anonymous launch paths with persisted runs while preserving the underlying portfolio functions.

### 1.3 Reasoning and external-process execution

There are three reusable invocation seams:

- [`brain/codex_bridge.py`](../brain/codex_bridge.py) launches `codex exec --json`, supplies input on stdin, parses JSONL events, applies a read-only permission profile, builds a minimal environment, records session/tools/usage, and enforces a wall-clock timeout. It is the strongest worker-adapter substrate.
- [`brain/cli_bridge.py`](../brain/cli_bridge.py) uses the Claude Agent SDK first and `claude -p --output-format json` as fallback. The SDK supports streamed messages and resume, but the bridge has no durable process handle or wall-clock timeout. The fallback yields only final JSON and also lacks timeout/cancel supervision.
- [`bridge/job_runner.py`](../bridge/job_runner.py) creates a file batch, invokes Claude reasoning, and expects `result.json`. This is the closest existing “job” envelope, but it is not a queue or lifecycle manager.

The current provider waterfall is a portfolio-reasoning policy, not a worker dispatcher. Keep its provider eligibility and no-replay-after-partial-tool-use rules; do not ask it to own jobs, workers, or worktrees.

### 1.4 Self-improvement execution

Mastermind's scheduled learning work is a set of domain loops, not company orchestration:

```text
APScheduler `loop_maintenance`
→ predictions / rejections / student / distillation
→ interim marks / shadow books / desk A-B
→ outcomes / outcome ledger / track record
→ calibration / attribution
→ Mastermind AI observational cycle
→ step events and domain files
```

`app/scheduler.py::_loop_maintenance_job` calls `_run_loop_maintenance_steps` (`app/scheduler.py:919-1070`). Each step catches and logs its own error. The outer wrapper currently ends `ok` even when one or more children failed, so a future Executive run must aggregate child status instead of trusting that terminal event.

The weekly Improvement Agenda (`brain/improvement_agenda.py`) ranks evidence into advisory work. Daily experiment maturity evaluates the domain registry. `brain/mastermind_ai.py` drafts observations, maintains sanitized request-only directives, and appends reviews. `brain/self_tune.py` is default-off, bounded, and has no non-test `propose`/`apply` caller. The `loop/` research harness is deliberate/manual and promotes only to paper. None of these is a general-purpose COO queue.

### 1.5 External Macro execution boundary

Macro owns three systems that Mastermind must consume, not recreate:

- **Code Metabolism:** GitHub Actions orchestrates agenda, propose, two-key adjudication, build, verify, audit, merge, immune, dream, garbage collection, and heartbeat workflows. It has pause-by-default controls, exact-head CI/audit gates, immutable-file fences, and a gated merge lane.
- **Neural Web hypothesis metabolism:** registration precedes evaluation, only post-registration evidence counts, hypothesis volume is budgeted, and promotion authority is fenced.
- **Prophet learning:** the nightly lane is the sole forward-ledger advancer; live Prophet is a provisional backstop. Point-in-time receipts, exact-output manifests, frozen grades, race detection, and checkpoint withholding protect provenance.

Concrete cross-repository surfaces:

| Macro-owned service | Trigger / executable surface | Durable domain state | Mastermind-side seam |
|---|---|---|---|
| Code Metabolism | `.github/workflows/metabolism-cycle.yml` dispatches agenda/propose/adjudicate/build/verify/audit/merge stages; core entry points include `engine/metabolism/agenda.py::build_agenda`, `engine/metabolism/propose.py::propose`, `engine/metabolism/adjudicate.py::resolve_two_key`, and `scripts/metabolism_merge.py::run_merge_lane` | `data/metabolism/journal/<cycle>.json`, budget ledger, insight bus, memory/lessons, branch/PR/CI/audit state | No Mastermind writer. `data_layer/macro_refresh.py` consumes the published Macro repository/artifacts; a future adapter should observe workflow/PR/result references only. |
| Neural Web hypothesis metabolism | `.github/workflows/daily.yml` invokes Cortex registration/evaluation; `engine/neuralweb/cortex.py::_tool_stake_hypothesis`, `engine/neuralweb/metabolism.py::register_hypothesis`, and `scripts/evaluate_cortex_hypotheses.py` enforce registration and maturation | `data/neuralweb/machine_registry.jsonl`, trial and governance ledgers, published context artifacts | `brain/neural_web_context.py` reads typed context; `bridge/nw_feedback.py` emits request/feedback artifacts without execution authority. |
| Prophet learning | `.github/workflows/daily.yml` runs `scripts/build_prophet.py::main` as sole nightly ledger advancer; VPS `macro-live-prophet` timer writes provisional live state; Arena, Stage Shadow, grades, and governor remain shadow/advisory | `site/prophet/index.json`, plans/states, `data/prophet/ledger.jsonl`, origination receipts, frozen grades, quarantine/Arena artifacts | `portfolio/prophet_feed.py` is a stale-gated, fail-inert, additive-only reader. |

Production declares `MASTERMIND_MACRO_MANAGED_EXTERNALLY=1`. The tracked `vendor/macro` link points to `vendor/macro_src`, which is intentionally absent from the fresh repository worktree and supplied only where needed. `brain/key_rotor.py` separately consumes Macro-owned **provider-capacity** artifacts; it is not a learning adapter. Phase 1 should store external run/artifact references and must never become a second writer to Macro's learning ledgers.

### 1.6 Deployment completion path

The repository's strongest existing transaction is release delivery:

```text
fresh origin/master worktree
→ scoped changes and tests
→ branch / pull request / required CI
→ squash merge
→ exact merged SHA archive
→ root-SSH rsync deployment with backup
→ service restart
→ exact-SHA health and scheduler/provider checks
→ rollback on failed verification
```

`scripts/deploy_from_git.sh` refuses a SHA that is not the current `origin/master`. `scripts/deploy_code_to_vps.sh` uses a clean archive, backup, service restart, exact health checks, and rollback. This transaction should remain a separate release executor. Ordinary coding workers must not inherit its root SSH or `rsync --delete` authority.

---

## 2. Existing State Stores

### 2.1 Persistence inventory

| Store | Current contents | Durability and failure behavior | Executive OS safety | KEEP / EXTEND / REPLACE verdict |
|---|---|---|---|---|
| Canonical VPS data mount: `/opt/mastermind-live-data` → `/opt/mastermind/data` | Ignored portfolio accounts, fills, decisions, ledgers, agenda, experiments, learning state, caches | Survives service restart and atomic code deploy on one VPS. No repository evidence of backup, replication, multi-node fencing, or disaster recovery. | Safe location, not a data model | **KEEP** location; **EXTEND** backup/ownership/monitoring |
| APScheduler `MemoryJobStore` | Next-run schedule reconstructed at boot | Intentionally non-durable in authoritative production. One-shot retries and counters vanish on restart. | No | **KEEP** for financial cadence only; never use for Executive jobs |
| Optional `data/scheduler.sqlite` | APScheduler registrations in nonproduction modes | Durable when writable, but production retired it after read-only database failures; code silently falls back to memory if SQLAlchemy is unavailable. | No | **KEEP** for local scheduler compatibility; **REPLACE** for any Executive-state use |
| `data/control_plane/run_events.jsonl` via `control_plane/run_events.py` | Start/end/skip/step/guardrail telemetry | Best-effort append, never raises, no fsync/index/rotation/tamper chain. Second-resolution event IDs can collide and are explicitly not keys. | Audit export only | **KEEP** compatibility export; **EXTEND** with correlation; **REPLACE** as lifecycle truth |
| Governance JSONL via `control_plane/governance.py` | Flag, doctrine, lifecycle, and governance observations | Best-effort mutable local JSONL; actor is a caller string, IDs can collide, no directive/approval/run foreign keys. | No | **KEEP** compatibility export; **EXTEND** correlation; **REPLACE** as decision/approval truth |
| `data/brain/runs/*.jsonl` via `brain/runlog.py` | Reasoning run steps and terminal records | Per-run files, process-local thread lock, no cross-process lifecycle or queue semantics. | Domain diagnostics only | **KEEP** and link by Executive `run_id` |
| Response logs, thinking logs, journald | Model responses, debugging, service output | Useful operator evidence; rotation/retention varies; not state transitions. | No | **KEEP** diagnostics; reference from artifacts |
| `data/brain/decision_provenance/<asof>.jsonl` | A decision row, flags hash, source metadata | Best-effort unlocked append; corrupt rows are skipped; currently called only in a legacy Flagship path, not every active book. | No | **KEEP/EXTEND** domain audit; **REPLACE** as OS decisions truth |
| Portfolio JSON/JSONL under `data/portfolio/*` | Paper accounts, pending targets, fills, decisions, NAV, evaluations | Persistent on canonical mount; writers and recovery semantics differ by file. Some are atomic, some append-only, some whole-file rewrites. | Domain state only | **KEEP**; Executive OS stores hashes/URIs, not copies |
| `data/portfolio_learning/*` | Active-book traces, applications, receipts, requests | Best local-file pattern: per-book `flock`, temp replace, flush/fsync, hash-bound receipts, immutable transitions, crash recovery. Still filesystem/fleet limited. | Pattern source, not OS store | **KEEP/EXTEND** domain system; reuse receipts and recovery ideas |
| `data/experiments/registry.json` via `brain/experiment_registry.py` | Hypotheses, gates, maturity, owner, status, artifact notes | Whole-file read/modify/write without lock/CAS; corruption reads as empty; concurrent updates can be lost. Some read-like calls mutate maturity. | No | **KEEP** the domain registry/evaluators; **EXTEND** through ID/hash links. Do not migrate or replace it in Phase 1; Executive experiment rows are links. |
| `data/mastermind_ai/*` | Settings, loop log, reviews, sanitized request directives, ack state | JSON/JSONL best-effort, no transaction. Directive queue is capped and request-only, with no DAG, lease, worker, retry, or cancellation. | No | **KEEP** portfolio observer; **EXTEND** with artifact adapters; **REPLACE** as any Executive queue |
| `data/self_tune/state.json` | Shadow proposals and kept/reverted intent | Whole-file, unlocked, human-editable; default-off and no live application caller. | No | **KEEP** dark research prototype |
| Journal files (`drafts.json`, `lessons.json`, `pins.json`) | Seat-local model memory and falsifiers | Temp-and-replace per file but no multi-file transaction or lock. Model-authored content is not authoritative fact. | No | **KEEP** bounded prompt memory; expose only as provenance-bearing artifacts |
| `data/nw_reflection/*` | Latest reflection, history, nudge state | Plain files; same-as-of history may be rewritten; no cross-file transaction. | No | **KEEP** observer output; link read-only |
| `data/metabolism/key_ledger.jsonl` | Provider key IDs, cooling and session events, no secret values | Unlocked best-effort append; corrupt records skipped; eligibility can degrade permissively. This is provider metabolism, not Macro code Metabolism. | No | **KEEP** capacity telemetry; never use as worker lease store |
| `data/bot.db` via `data_layer/store.py` | Thesis, position, track-record, run, trial, holdout, promotion tables | Local SQLite works. Contrary to the module header, `DATABASE_URL` raises `NotImplementedError`; no runtime Postgres adapter/migration exists. | Not without replacement/isolation | **KEEP** domain DB; do not reuse its tables as Executive state |
| `sql/0001_schema.sql`, doctrine SQL, Supabase position SQL | Intended Postgres domain DDL and personal-portfolio schema | Versioned DDL, but not evidence of a deployed Executive database. | No | **KEEP** domain history; new migrations belong under control plane |
| Supabase | Personal portfolio CRUD and selected external Macro/trade-memory data | Durable external database. Service-role use bypasses RLS; this is not an Executive queue. | No | **KEEP** domain integration; isolate credentials |
| Git YAML: doctrine, authority map, contracts, agent profiles | Versioned operator policy and static artifact contracts | Durable and reviewable through Git, immutable at runtime by design. Runtime enforcement is incomplete. | Configuration, not mutable lifecycle | **KEEP**; record exact hash/version in decisions and runs |
| Git branches, commits, PRs, CI checks | Code change provenance and release gates | Durable external audit. Mastermind has no general programmatic worktree/PR controller. | Code-delivery evidence only | **KEEP/EXTEND** through references |
| Generated census | Static source inventory | Stale unless regenerated; cannot observe dynamic truth. | No | **KEEP/EXTEND** as CI conformance artifact |
| Caches, sparse Macro checkout, generated snapshots/Parquet/site JSON | Rebuildable data and read models | May be stale, partially written, or externally refreshed. | Artifacts only | **KEEP** where useful; hash and classify freshness |
| Redis / Celery / RQ | None found | Not present | N/A | No existing store to classify; retain the absence for single-host Phase 1 |

### 2.2 Storage conclusion

No current file ledger or database is safe as the Executive OS source of truth. The smallest credible store is a dedicated SQLite database on the canonical runtime mount, owned by the new unprivileged Executive service, with:

- schema migrations and `PRAGMA foreign_keys=ON`;
- WAL mode and a deliberate busy timeout;
- explicit transactions for claim, lease, transition, and result commit;
- unique idempotency keys and attempt numbers;
- optimistic version columns for CEO/Fable updates;
- immutable event rows generated in the same transaction as state changes; and
- artifact files outside the database, recorded by URI, size, media type, and SHA-256.

This is not a resurrection of APScheduler's retired SQLite job store. It has a different owner, path, schema, failure policy, and purpose. Move to PostgreSQL only when multiple scheduler hosts or write contention make the operational cost worthwhile.

---

## 3. Existing Control Plane Assessment

### 3.1 Component dispositions

| Component | Classification | Current responsibility | Executive OS recommendation |
|---|---|---|---|
| `control_plane/__init__.py` | **REFACTOR** | Package marker whose “zero integration” description is now false | Make it the documented facade/version boundary for the existing and new control-plane APIs. |
| `control_plane/contracts.py` | **KEEP** | Cached, fail-open registry of static artifact contracts/freshness, consumed by Macro refresh | Keep as a **domain artifact-contract** registry. Return defensive copies and validate load errors later. Do not turn it into `JobSpec`. |
| `control_plane/decision_packet.py` | **REFACTOR** | Portfolio `DecisionPacket`, delta computation, validation, rejection ledger | Preserve the investment boundary. Tighten evidence/run/version validation and add job/run/artifact foreign references. Do not pretend it is a generic worker result. |
| `control_plane/flags.py` | **REFACTOR** | Hardcoded known environment flag registry | Generate or validate from one source. Fourteen live `MASTERMIND_*` reads are missing, including entry, stale-freeze, peer-sentinel, Prophet-feed, authoritative-VPS, job timeout, and shared-pool gates. |
| `control_plane/guardrail.py` | **KEEP** | Domain severity taxonomy and caller-enforced guardrail result | Keep the reporting vocabulary. Map portfolio `HARD_STOP`/`FREEZE` into run events without conflating risk state with job lifecycle. Add run/decision correlation. |
| `control_plane/locks.py` | **REFACTOR** | Nonblocking POSIX local lock and conflict telemetry | Keep for leaf critical sections. Replace as job ownership with transactional lease + heartbeat + fencing. Move lock namespace outside per-worktree repo roots. |
| `control_plane/run_events.py` | **REFACTOR** | Best-effort operational JSONL events | Put a validated immutable event table behind it and continue emitting the legacy JSONL projection. Event IDs must be collision-safe primary keys. |
| `control_plane/run_ledger.py` | **REFACTOR** | Start/end wrapper around run events | Evolve compatibility methods onto the durable Run FSM. Add job/worker/attempt/lease/result/error/artifact links and crash reconciliation. |
| `control_plane/governance.py` | **REFACTOR** | Authority-change observations and doctrine/flag drift JSONL | Turn it into pre-action policy/approval decisions plus durable audit. Keep the JSONL export. Fix current startup ordering before relying on flag drift. |
| `control_plane/packet_gate.py` | **REFACTOR** | Shadow/enforce portfolio packet gate | Preserve portfolio semantics; wire policy transitions to actual authorization/approval records instead of environment flag plus documentary map. |
| `config/authority_map.yml` | **ABSORB** | Portfolio A0–A7 classifications and expected governance events | Keep A0–A7 as domain-effect input, but add executable capabilities, scope, direction, approver, expiry, and grant/revoke semantics. Production currently never reads this file. |
| `config/doctrine.yml` | **KEEP** | Portfolio sizing, veto, lifecycle, and self-tune policy | Keep strictly domain-owned and Git-reviewed. Reference its hash; do not use it as mutable job state. |
| `research/MASTERMIND_CONTROL_PLANE_MASTERPLAN.md` | **DEPRECATE as current architecture; KEEP as history** | Historical delivery plan and incident/status record | Retain provenance, but do not derive current topology from it. Its “no remote” and old job/runtime statements are obsolete. |
| `research/MASTERMIND_CHARTER_V2.md` | **EXTEND** | Portfolio constitutional safety principles | Preserve shrink-only authority, executable lessons, one-source discipline, shadow-first promotion, and deploy proof. Amend the actor hierarchy explicitly for Sol CEO / Fable COO. |
| `bridge/job_runner.py` | **ABSORB, then DEPRECATE direct use** | Claude-only file-batch job helper | Preserve the input/schema/result artifact pattern inside the durable job service. Replace caller-controlled paths, timestamp IDs, and implicit lifecycle. |
| `brain/runlog.py` | **KEEP** | Detailed reasoning-step log | Complement, not duplicate, the Executive Run. Correlate by `run_id`; do not make it queue truth. |

There is no justified **DELETE** verdict in Phase 0. Retire obsolete compatibility paths only after consumer checks and migration evidence. A reconnaissance report should not convert stale code into an unreviewed removal campaign.

### 3.2 Capability support today

| Capability | Today | Assessment |
|---|---|---|
| Jobs | Labels around pre-existing function calls; file-batch helper | Missing durable Job record, payload schema, priority, idempotency, dependency, attempt policy |
| Workers | No registry; provider roles/profiles only | Missing identity, capability advertisement, availability, heartbeat, lease, version, current run |
| Authority | A0–A7 YAML plus retrospective events | Documentary/conformance only; no production authorization evaluator |
| Locking | Local `flock` | Good same-namespace mutex; unsafe across worktree-local lock roots and insufficient across a fleet |
| Retry | One special provider-reset retry with process-memory daily count | Missing generic persisted policy, backoff, attempt identity, and restart-safe ceiling |
| Lifecycle | `start`, `end`, `skip`, step events | Missing queued/claimed/starting/running/cancel requested/cancelled/timed out/lost/retrying states |
| DAG | Hardcoded sequential function chains | No persisted dependency graph, readiness evaluation, blocked reason, or fan-in aggregation |
| Results | Scattered return values, JSON/JSONL, artifact files | No universal result schema, artifact manifest, acceptance report, or result transaction |
| Auditability | Broad but fragmented ledgers | No shared foreign keys, consistent actor identity, tamper protection, current-state query, or event/state atomicity |

### 3.3 Confirmed control-plane defects to fix before trusting it

1. **Authority is not enforced.** `config/authority_map.yml` is read only by tests; production call sites do not consult it before effects.
2. **Startup flag drift self-compares.** `app/main.py:205-230` appends the current `app_started` flags and then calls `governance._last_startup_flags()`, whose reverse scan finds the row just written (`control_plane/governance.py:234-253`). The result is current versus current.
3. **Flag census is incomplete.** The hardcoded registry omits 14 live environment reads, so a green conformance test does not mean all gates are governed.
4. **Run IDs and event IDs are not durable identities.** A start-log failure collapses to `run_id="error"`; event IDs can collide by design; Git SHA is cached from process cwd rather than a declared repository.
5. **Lock roots follow worktrees.** The default path derives from the module's repository root, so two isolated worktrees can receive different lock files and both enter the same logical critical section.
6. **Failure severity conflicts.** The historical masterplan calls same-book lock conflict a `HARD_STOP`; runtime lock and scheduler events call it `ADVISORY_ONLY`.
7. **Child failure does not determine parent failure.** Loop-maintenance substeps can fail while the wrapper records a successful terminal run.
8. **Scheduler health confuses declared with active.** Static IDs are reported “active” even when conditional `vps_state_sync` is not registered.

### 3.4 Obsolete, overlapping, and deliberately separate systems

- The Mac LaunchAgent production narrative in `MAINTENANCE.md:133-170` and Mac-writer comments in `app/scheduler.py` are obsolete. The VPS/systemd service is authoritative; the old state-sync path should fail closed and be retired only after a consumer check.
- `daily_loop`, `heavyweight_daily`, and `etf_daily` are retired scheduler jobs. Their first-run/manual wrappers are compatibility surfaces, not active topology.
- The checked-in July system census and the historical control-plane masterplan are evidence of earlier states, not current runtime truth.
- `bridge/job_runner.py` overlaps the future job envelope and should be absorbed rather than allowed to become a second queue.
- `brain/mastermind_ai.py` “directives” are sanitized portfolio-learning requests to Macro/Neural Web, not CEO directives. Preserve the domain queue name and do not overload it.
- Mastermind provider “Metabolism” (`brain/key_rotor.py`) and Macro code Metabolism are different systems. The former records provider cooling/capacity; the latter governs code-improvement hypotheses and PRs.
- `brain/runlog.py` and `control_plane/run_ledger.py` are complementary detail and lifecycle layers, not duplicates; both should share a durable `run_id`.
- `.claude/agents/*`, `.codex/agents/*`, and `config/agents.yml` are parallel role-policy projections that can drift. Keep compatibility now and generate them from one reviewed policy later.
- `data_layer/store.py` claims a production PostgreSQL path that is not implemented. Treat the header and SQL files as intent, not an active database topology.
- No code uses GitHub Issues or PRs as a programmatic Executive queue today. PRs and CI are release evidence only.

---

## 4. Worker Integration Points

### 4.1 Clean integration seam

Add worker support **under the existing `control_plane` namespace**, initially as a small `control_plane/workers/` package:

```text
control_plane/
  jobs.py              # JobSpec validation and state service
  runs.py              # attempt FSM, leases, reconciliation
  workers/
    base.py             # protocol and shared result types
    codex.py            # adapts codex_bridge mechanics
    claude.py           # adapts cli_bridge mechanics with a safe env
  store.py              # migrations and transactions
```

Names such as `claude-01` through `claude-07` and `codex-01` through `codex-03` should be logical, persisted worker slots—not ten tmux panes and not ten immortal CLI processes. Phase 1 should register only `claude-01` and `codex-01`. A slot is available when its lease is absent/expired and its heartbeat is current.

`bridge/job_runner.py` should become a compatibility caller of this service, then be deprecated as a direct launch path. It currently permits raw job IDs and filenames in paths, can collide within one second, does not atomically create a job, does not locally validate result schema, treats an empty JSON object as failure, and has no worker/attempt/timeout/cancel/reconcile fields.

### 4.2 Minimum adapter contract

Keep the adapter responsible for provider-process mechanics and nothing else:

```python
class WorkerAdapter(Protocol):
    def capabilities(self) -> WorkerDescriptor: ...
    async def start(self, spec: LaunchSpec) -> ProcessRef: ...
    async def status(self, ref: ProcessRef) -> RunStatus: ...
    async def cancel(self, ref: ProcessRef, reason: str) -> CancelReceipt: ...
    async def collect_result(self, ref: ProcessRef) -> WorkerResult: ...
```

Phase 1 should omit a universal `send()` method. Both CLIs have session concepts, but Codex resume is currently discarded and interactive delivery introduces ordering, acknowledgement, and replay semantics. A follow-up can be a new job linked to the prior run until those semantics are deliberately designed.

Essential transport types:

```text
LaunchSpec
  run_id, worker_id, provider, workspace_path
  prompt_path, result_schema_path, artifact_dir
  timeout_seconds, granted_tools, authority_grant, env_profile

ProcessRef
  run_id, pid, process_start_identity, provider_session_id
  stdout_path, stderr_path, started_at

WorkerResult
  job_id, run_id, worker_id, status, summary
  structured_output, artifact_manifest, git_manifest
  acceptance_results, usage, started_at, finished_at
  error{class,message,retryable} | null
```

The adapter may translate authorized input into argv/stdin, start a new process group, stream stdout/stderr, parse provider events, validate final JSON Schema, terminate the process group, and produce a hashed result manifest. It must not decide authority, queue order, worktree lifecycle, Git push/PR/merge/deploy, retry eligibility, or objective completion. Those are control-plane responsibilities.

Worker capabilities and authority are deliberately orthogonal. Capabilities describe technical competence such as `repo_read`, `repo_edit`, `python`, `web_research`, or `document_review`. Authority describes allowed effect such as `READ`, `RESEARCH`, or `WRITE_BRANCH`. A technically capable worker is still ineligible when the persisted authority grant is absent or too narrow.

### 4.3 Registration, addressability, interruption, and recovery

The separate supervisor should:

1. register a stable worker ID, adapter/version, technical capabilities, and separate authority ceiling;
2. heartbeat while idle or busy;
3. transactionally claim one eligible queued job with a lease and fencing token;
4. persist `ProcessRef` before considering the run active;
5. update heartbeat and append output without making log text lifecycle truth;
6. honor a persisted `cancel_requested` state by terminating the process group;
7. validate and commit the structured result and terminal state in one transaction; and
8. on restart, compare recorded PID plus OS process-start identity, mark truly missing attempts `lost`, quarantine ambiguous processes/worktrees, and apply persisted retry policy.

A plain PID is insufficient because operating systems reuse PIDs. Store a process-start identity or supervisor-generated child token and verify it before signalling.

---

## 5. CLI Runtime Assessment

| Mechanism | Existing evidence | Phase 1 verdict |
|---|---|---|
| Codex CLI | Local `0.147.0-alpha.6.5`; stdin, JSONL, output schema, final-output file, session ID, sandbox/cwd; current bridge has minimal env and timeout | **Use first.** Extract/adapt invocation mechanics, add durable process reference, process group, streaming logs, local schema validation, external cancel, and reconcile. |
| Claude Code CLI / Agent SDK | Local `2.1.211`; SDK streams structured events and resumes; CLI supports JSON/stream JSON/schema/session/worktree options | **Use second, cautiously.** Build a new allowlisted environment and supervisor timeout. Do not launch coding work through current full-environment helper. |
| `asyncio.subprocess` | Already used by both bridges | **Use.** It is sufficient for one-host batch workers when wrapped by durable state and OS process groups. |
| systemd | Supervises current app with restart/kill policy | **Use** for a non-root Executive supervisor and sandboxed/per-worker transient units under a distinct execution identity. |
| tmux | Not installed on the census machine; Claude can optionally integrate | **Postpone.** At most an operator visibility/recovery/debug shell. Never identity, queue, heartbeat, message bus, result store, or cancellation truth. |
| stdin/stdout JSONL | Supported by Codex and Claude modes | **Preferred process protocol.** Persist raw streams as artifacts, parse events, and require a separate validated final result. |
| Result files | Existing bridge/job batch and both CLIs can support them | **Use** for schema, prompt, final result, manifests, and large artifacts; hash every committed artifact. |
| Local HTTP/RPC | FastAPI exists; no worker RPC exists | **Optional thin control API.** Prefer an authenticated Unix socket or loopback interface owned by the Executive service. Do not expose provider processes directly. |
| SQLite polling/claims | Not implemented for workers | **Use for Phase 1.** Transactional claims are simpler and more observable than adding a broker. |
| Redis/Celery/RQ | Absent | **Postpone.** Add only after a real multi-host throughput/availability requirement. |

The governing philosophy is exact:

```text
tmux = optional visibility / recovery / interactive debugging
Executive OS database + supervisor = source of truth
stdout/stderr = evidence, not state
```

The current Codex bridge already models the safer environment boundary. The current Claude `_subscription_env()` begins with nearly all of `os.environ` and removes only selected Anthropic variables. That is suitable only inside the current trusted portfolio service boundary; it is unsafe for a general coding worker.

---

## 6. Git / Worktree Model

### 6.1 Current practice

Mastermind has strong human delivery doctrine in `AGENTS.md` and `docs/DELIVERY_WORKFLOW.md`: fetch first, create a unique worktree and branch from `origin/master`, stage only scoped paths, test, commit, push, open a PR, wait for required CI, squash merge, deploy the exact merged SHA, and verify health. CI checks a pinned Macro engine slice, compilation, shell syntax, governance tests, and a focused Portfolio v2 suite.

What is missing is reusable code for worktree creation, inventory, recovery, quarantine, and safe cleanup. Claude's built-in `--worktree` is not a substitute because the Executive OS must own the base SHA, branch, path, lease, and recoverability record.

### 6.2 Safe autonomous flow

```text
authorized job
→ supervisor resolves and persists exact origin/master base SHA
→ supervisor creates `codex/job-<uuid>` in an isolated workspace
→ restricted worker principal writes only inside that workspace + its artifact directory
→ supervisor inspects changed paths and diff
→ acceptance commands run with bounded environment
→ supervisor stages explicit allowed paths and commits when authorized
→ separate PUSH_BRANCH / OPEN_PR action
→ critic/governor decision against exact head SHA
→ separate MERGE_LOW_RISK action
→ separate DEPLOY release executor and live proof
```

Rules:

1. Use a supervisor-owned root such as `/var/lib/mastermind-exec/workspaces/<job_uuid>`; never interpolate an objective title or caller-supplied ID into a path. For a coding worker, prefer a credential-free per-job clone owned by the restricted execution principal. Use a linked worktree only for trusted/read-only work or when an OS sandbox provably denies the child access to the common Git directory.
2. Persist repository, remote, immutable base SHA, branch, absolute path, owner, lease, and cleanup state before launch.
3. Never put two workers in one mutable workspace.
4. Run the model under a distinct OS principal or container. It receives no direct control-database, supervisor-admin-checkout, shared Git credential, or common Git-directory access. An allowlisted environment alone is not isolation when supervisor and child share a user.
5. `WRITE_BRANCH`, `OPEN_PR`, `MERGE_LOW_RISK`, and `DEPLOY` are distinct grants. The supervisor—not model prose—performs scoped stage/commit/push operations after policy checks.
6. Before cleanup, require a terminal attempt, no live PID/lease, clean tree or durable recovery branch, and no open PR/recovery dependency.
7. Use nonforced `git worktree remove` and then prune. Dirty or ambiguous trees move to quarantine; never auto-force-delete them.
8. Delete a branch only after merge or an explicit abandonment decision with a recovery attestation.

GitHub is a durable code review and CI surface, not the Executive approval database. Current protection requires the `test` check but zero human approvals, so possession of a sufficiently privileged merge credential can bypass the intended organizational separation. Coding workers must never hold that credential.

A linked worktree is concurrency isolation, not a hostile-code security boundary: its `.git` file points into shared repository metadata. The supervisor must broker privileged Git operations. If a per-job clone is used, it should contain no push credential; the supervisor imports the reviewed patch/commit into its administrative checkout before any push action.

---

## 7. Minimum Viable Executive State

Use seven domain objects plus an implementation-level dependency relation. Keep payloads versioned JSON where iteration is expected; keep identity, status, authority, timestamps, and foreign keys as typed columns.

### 7.1 Essential objects

| Object | Essential fields | Notes |
|---|---|---|
| `workers` | `id`, `adapter`, `adapter_version`, `status`, `capabilities_json`, `authority_ceiling`, `heartbeat_at`, `current_run_id`, `version` | Status: `offline`, `idle`, `busy`, `draining`. A worker is not available merely because its process exists. |
| `objectives` | `id`, `parent_id`, `source`, `title`, `desired_outcome`, `priority`, `status`, `constraints_json`, `acceptance_json`, `authority_ceiling`, `created_at`, `updated_at`, `version` | A CEO directive is an objective with `source="ceo"`; no separate directive table is needed initially. |
| `jobs` | `id`, `objective_id`, `plan_artifact_id`, `type`, `spec_version`, `payload_json`, `required_capabilities_json`, `authority_required`, `priority`, `status`, `attempt_limit`, `available_at`, `idempotency_key`, `created_at`, `updated_at`, `version` | Status: `draft`, `blocked`, `queued`, `running`, `succeeded`, `failed`, `cancelled`. A relation table `job_dependencies(job_id, depends_on_job_id)` represents DAG edges. Required capabilities are technical competencies; `authority_required` is the permitted effect. |
| `runs` | `id`, `job_id`, `worker_id`, `attempt`, `status`, `lease_token`, `lease_expires_at`, `heartbeat_at`, `base_sha`, `branch`, `worktree_path`, `pid`, `process_start_id`, `provider_session_id`, `started_at`, `finished_at`, `exit_code`, `error_json`, `result_artifact_id` | Attempt states: `claimed`, `starting`, `running`, `cancel_requested`, then `succeeded`, `failed`, `cancelled`, `timed_out`, or `lost`. Retry creates a new run; it never rewrites history. |
| `decisions` | `id`, `objective_id`, `job_id`, `run_id`, `actor_id`, `kind`, `outcome`, `reason`, `authority`, `policy_hash`, `created_at` | Holds approval/rejection/escalation/policy decisions. Actor identity must be authenticated, not a free-form label. |
| `experiments` | `id`, `objective_id`, `external_ref`, `hypothesis`, `gate_json`, `status`, `owner`, `review_due_at`, `evidence_refs_json`, `verdict`, `created_at`, `updated_at`, `version` | Link existing Mastermind/Macro experiment IDs first. Do not migrate or duplicate their evidence ledgers in Phase 1. |
| `artifacts` | `id`, nullable `objective_id`/`job_id`/`run_id`, `kind`, `schema_name`, `schema_version`, `uri`, `sha256`, `media_type`, `size_bytes`, nullable `supersedes_id`, `created_at` | Files, plans, logs, prompts, schemas, diffs, test reports, commits, PRs, and external ledgers are immutable references with content identity. A pre-run Fable plan is an objective artifact; its `plan_id` is the artifact ID. A revision creates a new artifact linked by `supersedes_id`. |

An immutable `events` table is an implementation necessity, not a new business object: `id`, `aggregate_type`, `aggregate_id`, `sequence`, `event_type`, `actor_id`, `payload_json`, `created_at`. State transitions and their event rows must commit together.

### 7.2 Minimum invariants

- One active lease per job attempt; one current run per worker.
- Unique `(job_id, attempt)` and `(aggregate_type, aggregate_id, sequence)`.
- A worker may claim only if required capabilities and authority fit its persisted grants.
- Fencing token required on heartbeat, transition, and result commit.
- A job becomes ready only after every dependency succeeds or an explicit dependency policy resolves it.
- A runnable job references the exact immutable plan artifact from which it was materialized.
- A result cannot become successful until its schema, artifact hashes, and acceptance commands pass.
- Terminal runs are immutable; retry is a new attempt.
- Objective completion is derived from persisted job/decision state and then explicitly decided, never inferred from a final chat sentence.

---

## 8. Fable Integration Surface

Fable should be a planner principal that consumes a versioned CEO directive and returns a versioned plan. It should not be a free-form terminal that silently launches work or elevates its own authority.

### 8.1 CEO directive contract

```json
{
  "schema": "mastermind.ceo_directive/v1",
  "objective_id": "obj_...",
  "desired_outcome": "Prove one isolated worker can complete and report a bounded repository task",
  "priority": "P0",
  "constraints": ["paper-only", "no production authority"],
  "acceptance_criteria": [{"kind": "artifact_exists", "value": "..."}],
  "context_refs": [{"uri": "...", "sha256": "..."}],
  "authority_ceiling": "WRITE_BRANCH",
  "due_at": null,
  "risk_class": "low"
}
```

### 8.2 Fable plan contract

```json
{
  "schema": "mastermind.execution_plan/v1",
  "plan_id": "plan_...",
  "objective_id": "obj_...",
  "version": 1,
  "summary": "...",
  "assumptions": ["..."],
  "jobs": [
    {
      "job_id": "job_a",
      "type": "research_task",
      "inputs": [{"artifact_id": "art_..."}],
      "expected_outputs": [{"kind": "research_brief", "schema": "mastermind.research_brief/v1"}],
      "required_capabilities": ["repo_read", "web_research"],
      "authority_required": "RESEARCH",
      "acceptance": [{"kind": "schema_valid"}],
      "timeout_seconds": 1800,
      "max_attempts": 1
    },
    {
      "job_id": "job_b",
      "type": "repo_task",
      "inputs": [{"job_id": "job_a", "output": "research_brief"}],
      "expected_outputs": [{"kind": "worker_result", "schema": "mastermind.worker_result/v1"}],
      "required_capabilities": ["repo_edit", "python"],
      "authority_required": "WRITE_BRANCH",
      "acceptance": [{"kind": "command", "argv": ["python3", "-m", "pytest", "..."]}],
      "timeout_seconds": 1800,
      "max_attempts": 1
    }
  ],
  "edges": [{"from": "job_a", "to": "job_b", "condition": "succeeded"}],
  "approval_points": [],
  "escalation_policy": {"on": ["blocked", "attempts_exhausted", "authority_denied"]},
  "status": "proposed"
}
```

The accepted plan is first written as an immutable objective artifact; `plan_id` is that artifact's ID, and every materialized job records `plan_artifact_id`. Before persistence as runnable jobs, the Executive OS validates schema version, declared edge endpoints, acyclicity, known job types, satisfiable technical capabilities, time/budget bounds, acceptance-command allowlist, and every job's authority against the CEO directive ceiling. Fable cannot expand that ceiling. A revised plan is a new artifact that supersedes the prior version; it never mutates jobs already running.

### 8.3 Completion and escalation contracts

```json
{
  "schema": "mastermind.plan_completion/v1",
  "plan_id": "plan_...",
  "objective_id": "obj_...",
  "status": "completed",
  "job_counts": {"succeeded": 2, "failed": 0, "blocked": 0},
  "artifacts": ["art_..."],
  "decisions": ["dec_..."],
  "escalations": [],
  "final_synthesis": "..."
}
```

```json
{
  "schema": "mastermind.escalation_request/v1",
  "escalation_id": "esc_...",
  "objective_id": "obj_...",
  "job_id": "job_b",
  "run_id": "run_...",
  "reason_code": "authority_denied",
  "evidence_artifact_ids": ["art_..."],
  "requested_change": "Open a pull request for exact head SHA ...",
  "requested_authority": "OPEN_PR",
  "safe_default": "leave_branch_unpushed",
  "expires_at": "2026-08-12T00:00:00Z"
}
```

Timeout, missing evidence, invalid plan, and absent authority all default to no new effect.

Fable may propose, decompose, reprioritize within granted bounds, and synthesize. Only the Executive policy layer may authorize dispatch or a stronger effect. Only the CEO or delegated approver may change the objective's authority ceiling.

---

## 9. CEO Integration Surface

Keep the CEO contract transport-neutral. A local authenticated HTTP API, Unix-socket service, CLI, or MCP wrapper can expose the same operations; the ChatGPT Mac app is not part of the architecture.

### 9.1 Read operations

```text
get_company_state()
get_objectives(status?, priority?)
get_objective(objective_id)
list_jobs(objective_id?, status?)
get_job(job_id)
get_run(run_id)
list_workers(status?)
get_experiment_result(experiment_id | external_ref)
get_artifact_manifest(run_id)
```

`get_company_state()` should be a compact projection: active objectives, runnable/blocked/running counts, stale workers, exhausted attempts, pending approvals/escalations, recent failures, and policy/runtime health. Every field should resolve to durable records, not scan terminal text.

### 9.2 Write operations

```text
create_directive(directive, idempotency_key)
approve_proposal(decision_target, expected_version, reason)
reject_proposal(decision_target, expected_version, reason)
update_priority(objective_id, priority, expected_version, reason)
request_cancel(job_id | run_id, expected_version, reason)
```

Each write authenticates the principal, checks authority and optimistic version, records an immutable decision, returns the affected ID and new version, and is idempotent. A CEO request does not directly shell out, touch a worktree, merge, deploy, mutate portfolio state, or execute capital.

Phase 1 does not need natural-language worker-to-worker chat, organizational email, a GUI, or a general plugin ecosystem. It needs trustworthy state inspection and five bounded mutations.

---

## 10. Security and Authority Boundaries

### 10.1 Highest-risk surfaces

| Surface | Evidence and failure mode | Required boundary |
|---|---|---|
| Root service and ambient credentials | Live `mastermind.service` runs as root and loads root-owned service environments. Environment names include provider, Supabase service-role, R2 read/write, Stripe, Codex, and other shared credentials. `brain/cli_bridge.py` copies almost the entire environment. | Never spawn coding workers from uvicorn/current Claude helper. Separate non-root service/user, dedicated auth home, explicit environment allowlist, no `/etc/macro*.env`, `/root/.ssh`, or live data mount. |
| Deployment | Root SSH, `rsync --delete`, systemd restart, backup/rollback in deploy scripts | Dedicated release principal and `DEPLOY` decision; no normal worker credential or executable access. |
| Git merge | Required CI exists but review count is zero; privileged token can merge after checks | Worker gets no merge credential. Critic/governor records exact-head decision; separate executor enforces it. |
| Shared worktree/repository metadata | Linked worktree points into shared `.git`; hostile commands can affect other branches | Restrict model filesystem; broker Git operations or use per-job clone/container for stronger isolation. |
| Scoped destructive Git refresh | `data_layer/macro_refresh.py` runs `git reset --hard origin/main` inside its dedicated sparse `vendor/macro_src` checkout and can remove a proven-stale `index.lock` after process checks | Keep this bounded external-refresh behavior, but never reuse it as general worker cleanup. Resolve and attest the exact allowed checkout path before any destructive Git operation. |
| Personal portfolio API | Supabase service-role CRUD, including hard delete; app middleware leaves GETs and canonical pfolio assumptions open while current edge happens to return 403 | Add explicit app-layer authentication before relying on topology. Worker receives no service-role key or pfolio access. |
| Destructive scripts | Position/book reset/removal scripts can erase ignored runtime data; some lack dry-run, confirmation, or real backup despite “git rollback” claims | `DATA_DELETE` denied. Require read-only preview, explicit target, backup/restore proof, and separate operator approval. |
| Cross-repo publication | `scripts/export_macro_snapshot.py` can commit and push Macro `main` from a scheduled job | Separate `CROSS_REPO_PUBLISH`; no ambient Macro push credential in coding worker. |
| Spend/billing | `brain/cost_guard.py` defaults off/unlimited and fails open; Codex reports no dollar cost. Ambient Stripe/provider secrets exist even without active billing code. | Hard pre-launch reservations and ceilings for wall time, concurrency, turns/tokens; fail closed for new launches if budget state fails. `BILLING` always denied. |
| Authority policy | A0–A7 map is not read by production and cannot express directional/scoped grants | Runtime policy evaluation before dispatch/effect; immutable grant/deny decision with policy hash. |
| Paper trading state | Repository is explicitly paper-only; deterministic engines own sizing and no active broker surface was found | Preserve. `CAPITAL_EXECUTION` is constitutionally denied, not merely absent from a worker profile. |

### 10.2 Capability model

Use the requested coarse levels at the CEO/Fable surface, backed by narrower executable grants:

| Executive capability | Meaning | Phase 1 default |
|---|---|---|
| `READ` | Read approved repository and artifact paths | Grant, path-scoped |
| `RESEARCH` | Use approved read-only tools/network sources and write research artifacts | Grant to research jobs, domain/tool scoped |
| `WRITE_BRANCH` | Modify only assigned worktree; supervisor may stage/commit allowed paths | Grant selectively after path/test policy |
| `OPEN_PR` | Push a recovery/task branch and open a PR | Deny to model process; optional supervisor action after successful result |
| `MERGE_LOW_RISK` | Merge an exact reviewed head satisfying policy | Deny in Phase 1; separate principal later |
| `DEPLOY` | Execute exact-SHA release transaction and live verification | Deny to workers and Fable |
| `CAPITAL_EXECUTION` | Place or route real-capital orders | Deny constitutionally; system remains paper-only |

Implementation scopes should separately represent `RUN_TESTS`, `PUSH_BRANCH`, `SERVICE_CONTROL`, `CROSS_REPO_PUBLISH`, `PAPER_STATE_MUTATION`, `DATA_DELETE`, `BILLING`, and `CREDENTIAL_ADMIN`. A higher-sounding organizational role does not imply these effects. `MERGE_LOW_RISK` does not imply `DEPLOY`; `WRITE_BRANCH` does not imply `OPEN_PR`.

Every grant needs principal, capability, repository/path/tool scope, maximum effect, issuer, issue/expiry time, and optional delegation flag. Every effect checks the grant **before** action and records requested versus granted authority. Missing/expired/ambiguous grants fail closed.

### 10.3 Service boundary

Run `mastermind-exec-control.service` as a dedicated non-root control principal. It owns the Executive database, administrative Git checkout, policy evaluator, and broker API. Launch each provider CLI in a transient systemd unit or container under a different `mastermind-worker` identity that can reach only its job workspace, artifact directory, and narrow result/cancel channel. The existing root FastAPI process may query or submit through an authenticated local socket but must not pass its environment through.

The control and worker units should add, at minimum, `NoNewPrivileges`, restrictive umasks, private temporary storage, explicit read/write paths, resource ceilings, and process-group termination. The worker necessarily receives its one provider credential unless inference is separately brokered; Phase 1 must state that exposure honestly and give it no other credential. Distinct OS principals or a container are required for the claim that the child cannot read the control database, administrative Git metadata, or supervisor environment.

---

## 11. Recommended Phase 1 Build

### 11.1 Smallest proof loop

```text
Sol submits `mastermind.ceo_directive/v1`
→ existing `control_plane` persists Objective + proposed Plan
→ Fable adapter returns `mastermind.execution_plan/v1`
→ policy validates DAG, bounds, and authority
→ one queued Job is transactionally leased to `codex-01` or `claude-01`
→ supervisor creates an isolated credential-free workspace and starts a restricted worker unit/process group
→ worker writes JSONL logs + schema-valid `WorkerResult` + artifacts
→ supervisor validates acceptance, hashes artifacts, and commits terminal Run
→ Objective projection updates
→ Sol reads `get_company_state()`, `get_run()`, and result manifest
```

The proof job should be deliberately low-risk: generate or update a research artifact in a disposable repository fixture or a dedicated worktree, run a narrow validation command, and return a structured manifest. Do not make the first proof a deploy, portfolio mutation, Macro writer, or self-modifying loop.

### 11.2 Build sequence

**Step 1 — durable Executive-only core in shadow**

- Add migrations and repository/service methods for the seven objects, dependency edges, immutable events, claim/lease/heartbeat, FSM validation, idempotency, cancellation requests, and restart reconciliation.
- Add new Executive-only entry points and a read-only/shadow importer for selected legacy events. Leave current scheduler, `start_run`/`end_run`, governance, and JSONL write paths untouched until the vertical proof is complete.
- Add runtime policy evaluation for worker capabilities; preserve portfolio A0–A7 as a separate effect taxonomy.
- Do not migrate portfolio/learning state.

Acceptance: transaction tests prove double-claim rejection, fencing, crash/lost reconciliation, immutable terminal attempts, retry as a new attempt, dependency readiness, and shadow import without changing a legacy file or scheduler call site.

**Step 2 — isolated supervisor plus one Codex and one Claude adapter**

- Add the non-root control service, distinct restricted worker identity/transient unit, and supervisor-owned data/workspace roots. Use a credential-free per-job clone for the coding proof.
- Extract Codex invocation into the minimum adapter, with process groups, streamed logs, durable `ProcessRef`, schema validation, cancel, and result manifest.
- Add Claude using an allowlisted environment and the same contract; do not reuse the current full environment. Each worker receives only its necessary provider credential.
- Register only `codex-01` and `claude-01`.

Acceptance: kill/restart/timeout tests leave no ambiguous successful run; a missing child becomes `lost`; cancellation terminates descendants; neither worker can read the control service environment/database, live data, root SSH, deploy credentials, or shared Git metadata. The expected provider credential exposure is documented and tested as the only injected secret.

**Step 3 — directive/plan/result vertical slice**

- Expose the minimal CEO read/write API and Fable contracts.
- Persist and validate one directive, one bounded plan/DAG, one isolated repository job, acceptance evidence, and one final synthesis.
- Add a small status view and operational alerts for stale worker, expired lease, blocked job, invalid result, and pending escalation.
- Exercise both adapters one at a time; no fleet scaling.

Acceptance: the complete proof loop survives a supervisor restart, is reconstructible only from durable records/artifacts, and requires no terminal scrollback or tmux pane state. Only after this proof should legacy run/event facades be migrated behind the durable store in a separate compatibility change.

### 11.3 Explicit postponements

- ten persistent workers;
- Redis, Celery, or distributed scheduling;
- universal interactive `send()` semantics;
- automatic merge or deployment;
- automated doctrine/self-tune changes;
- direct Executive writes to Macro Metabolism, Prophet, or Neural Web ledgers;
- production portfolio mutation, billing, deletion, or capital execution; and
- a GUI-specific CEO integration.

---

### Recommended Foundation

Extend the existing `control_plane` package with a transactional Executive state model and runtime authorization checks, initially in shadow without changing legacy scheduler or JSONL writers. Operate it through a non-root control supervisor on the canonical VPS data mount and distinct restricted worker units/containers. Use supervised one-shot CLI processes, structured JSON contracts, credential-free isolated workspaces, brokered Git operations, and content-addressed artifacts. Keep APScheduler as the existing financial cadence trigger; migrate compatibility projections only after the Executive vertical slice is proven.

### Reuse

- `control_plane` package namespace and current integration call sites;
- `run_ledger` and `run_events` APIs as compatibility facades;
- `GuardrailResult`, portfolio `DecisionPacket`, artifact contracts, and A0–A7 domain semantics;
- Codex bridge's minimal environment, JSONL parsing, read-only permission profile, timeout, and typed MCP boundary;
- Claude SDK/CLI streaming and session parsing, behind a new safe environment boundary;
- `bridge/job_runner.py` input/schema/result artifact-batch concept;
- `portfolio_learning` IDs, hashes, fsync receipts, and crash-recovery patterns;
- Mastermind experiment evaluators, agenda, journal falsifiers, and observational AI loop as domain inputs;
- Macro Metabolism's pause/two-key/exact-head gates, Neural Web registration discipline, and Prophet's point-in-time receipts and sole-writer model;
- Git worktree/PR/CI doctrine and exact-SHA deployment transaction; and
- systemd for service supervision.

### Missing Pieces

- durable Objective, Job, Run, Worker, Decision, Experiment-link, Artifact, dependency, and event records;
- transactional claim/lease/heartbeat/fencing and restart reconciliation;
- generic attempt/retry/cancel/timeout/lost-run lifecycle;
- schema-versioned `JobSpec`, `WorkerResult`, CEO directive, Fable plan, escalation, and completion contracts;
- runtime capability authorization with scoped, expiring grants and authenticated actors;
- a separate non-root control supervisor plus a distinct restricted worker identity/container, allowlisted environments, and process-group control;
- supervisor-owned isolated-workspace lifecycle, per-job credential-free clones, quarantine, safe Git brokerage, and artifact hashing;
- current-state APIs and honest scheduler/worker observability;
- hard launch budgets that fail closed; and
- tested backup/recovery for the Executive store and artifacts.

### First 3 Engineering Tasks

1. **Build the durable core inside `control_plane` in shadow:** migrations, seven-object schema, dependency edges, immutable events, FSM, claim/lease/fencing, reconciliation, and policy checks—without rewiring legacy scheduler/run-event writers yet.
2. **Build the isolated execution boundary:** non-root control supervisor, distinct restricted worker units, credential-free per-job clone broker, process groups, logs/artifacts, cancellation, restart recovery, then adapters for `codex-01` and `claude-01` using one result contract.
3. **Ship one vertical directive loop:** CEO directive → validated Fable plan → one isolated low-risk job → persisted result/acceptance → CEO state/result readback, with no merge, deploy, portfolio write, or capital authority.

### Biggest Risks

1. **A decorative control plane:** continuing to log events and maintain YAML maps without enforcing transactional pre-action authority, leases, and lifecycle transitions.
2. **Credential collapse:** launching coding agents from the root web process or cloning its environment, thereby handing a worker service-role, storage, billing, provider, and deploy-adjacent authority.
3. **Split-brain orchestration:** turning `mastermind_ai`, `bridge/job_runner`, tmux, APScheduler memory, or Macro Metabolism into competing job truths instead of adapting them to one Executive state store.
4. **False completion:** treating a final model message, parent `ok` event, static scheduler label, or stale generated census as proof despite failed children, lost processes, invalid results, or uncommitted artifacts.
5. **Unsafe autonomous delivery:** sharing mutable worktrees, granting Git/merge/deploy credentials to workers, force-cleaning ambiguous state, or allowing advisory research/Prophet/Neural Web evidence to silently acquire production or capital authority.
