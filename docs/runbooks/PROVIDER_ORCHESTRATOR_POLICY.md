# Provider orchestrator policy deployment

This runbook installs the reviewed user-scope Mastermind CEO/orchestrator policy into local
Codex and Claude provider homes. It is configuration deployment only: it creates no lifecycle,
queue, retry, merge, watcher, source-custody, or permission authority.

Canonical source:

- `ops/executive_os/provider_orchestrator_policy.py`
- `ops/executive_os/provider_orchestrator_guard.py`

The deployer manages one marked policy block in `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`, one `PreToolUse` registration in each provider home, exact native-agent safety settings (`~/.codex/config.toml`: agents disabled by default with thread cap 1; Claude env: max 2 native subagents and spawn depth 1), and identical copies of the reviewed guard. Existing unrelated instructions, hooks, model settings, plugins, permissions, worktree hooks, credentials, and unrelated TOML/JSON fields are preserved. The Codex native-agent disable is intentionally user-scope defense-in-depth: a rare native-child exception requires an explicit reviewed reconfiguration rather than silently consuming local collaboration slots. Legacy and temporary operational policy blocks are migrated into the single v2 block rather than stacked. This includes `mastermind-ceo-async-ci-v1`, `mastermind-ceo-context-discipline-v1`, `mastermind-ceo-forward-execution`, `mastermind-orchestration-burn-guard-v1`, and `mastermind-fabric-routing-operational-v1`. The v2 block is the only managed provider-policy plane after a successful apply.

## Verify before apply

Run from a protected/reviewed Mastermind checkout:

```bash
python3 ops/executive_os/provider_orchestrator_policy.py verify --home "$HOME"
```

`READY` means the exact reviewed guard digest, policy content, managed native-agent configuration values, and both provider hook registrations match **as synchronous command handlers**. It does not prove that the provider process actually loaded/trusted the hook or reloaded those settings, nor that Executive/Fabric runtime admission is live. `DRIFT` is read-only evidence; it does not authorize overwriting an
unrelated provider home. `REFUSED` means preflight found a malformed/unsafe target before
an apply could complete. `APPLY_INCOMPLETE_VERIFY_REQUIRED` is different: at least one
managed file changed before a later write failed. Keep the same host/carrier, inspect the
reported modified files, and run `verify` before any replay or alternate deployment path.

## Apply

After the source revision intended for the host is accepted:

```bash
python3 ops/executive_os/provider_orchestrator_policy.py apply --home "$HOME"
python3 ops/executive_os/provider_orchestrator_policy.py verify --home "$HOME"
```

The first mutation of an existing managed file creates a
`.mastermind-orchestrator-backup`; later idempotent applies do not replace that original
backup.

## Behavioral canary

Installation is not behavior proof. In a disposable Mastermind worktree/provider session,
verify all four observations separately:

1. A foreground `gh run watch <run> --interval 150` is denied with an asynchronous-wait
   explanation.
2. The same watcher launched with the provider's real background primitive is admitted and
   returns context instructing the principal to continue another independent lane.
3. A foreground CI status + `sleep` polling loop is denied even at a 150–300 second cadence.
4. A first bounded CI status read is admitted; an unchanged repeat inside five minutes is
   denied. A real watcher/event remains the next observation.
5. Codex effective config reads `agents.enabled=false` and `max_concurrent_threads_per_session=1`.
6. Claude effective settings read `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=2` and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`.
7. A real `pool run` / `pool remote` launch without `POOL_ORCHESTRATOR_ID`, `POOL_PARENT_RUN_ID`, or `POOL_TASK_CLASS` is denied before dispatch; the same bounded launch with the existing stable root/parent/class is admitted to the Fabric's own routing/admission checks.
8. In a provider session that already inherits `POOL_ORCHESTRATOR_ID`, a child command that attempts to replace or empty that root is denied; changing child parent/task-class metadata does not mint a new root budget.

Do not launch a real workflow merely to prove the guard; use an already-existing run/PR or a
synthetic hook payload where possible. Never cancel/re-dispatch shared CI as part of this canary.

## Execution-efficiency acceptance

The managed policy carries these anti-burn invariants in addition to the CI guard:

- optimize accepted capability delta per original-root budget rather than agent count, tokens, elapsed time, tool calls, or PR count;
- Sol is the default day-to-day project executive; Astra is optional strategic/meta capacity for genuine principal judgment;
- routine bounded labor goes through the existing Executive/Subagent Fabric; native provider children are exceptions, not the worker pool;
- Fabric launches preserve the original root/true-parent/task-class identity at the provider edge so a new chat/helper cannot reset fair-share or descendant accounting;
- capacity is a ceiling, not a utilization target; preserve one original root/grant/depth/budget and reserve review/repair/integration capacity before widening fan-out;
- every worker owns one independently useful bounded outcome with exact source/ref, scope, DONE_WHEN/evidence, non-goals, and escalation condition;
- leaf workers do not recursively fan out; an admitted coordinator's helpers remain descendants of the original root;
- two consecutive support-only parent cycles with no capability delta trigger NO_DELTA_LOOP and force a tactic/lane change;
- two consecutive status-only/no-delta returns for the same worker dependency trigger a worker breaker rather than generic Continue;
- consume a returned child before replacing or duplicating it;
- continuously integrate source through reviewable dependency-correct verticals instead of indefinitely growing private branches;
- phase completion/checkpoint is a save-and-reassess boundary, not automatic finalization while useful authorized work remains.

These are orchestration policy constraints only. They do not create a second router, queue, scheduler,
retry controller, session registry, or lifecycle owner.

## Fleet acceptance

Track the rollout as separate layers:

1. reviewed/merged policy source;
2. exact managed policy bytes and guard digest installed on the host;
3. exact synchronous hook registration;
4. provider hook loading/visibility and any required human trust/selection;
5. effective native-client agent/concurrency/depth settings;
6. behavioral canary for CI and native-child routing;
7. canonical Executive/Subagent Fabric root-budget, admission, START/return, and acceptance proof.

Do not collapse these into one green state. A merged source file proves none of the host/runtime layers.
A copied file proves neither provider selection nor hook execution. Never manufacture a Codex trusted
hash or silently alter unrelated provider permissions/model/account settings. For an offline host, leave
it `NOT_INSTALLED` rather than inferring convergence from another machine.
