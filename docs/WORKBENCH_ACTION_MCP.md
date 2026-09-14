# First-party Workbench Action F0/F1

Status: **BUILT_NOT_PROVEN / RUNNABLE_LOOPBACK_SOURCE / NOT INSTALLED / C1-PERSONAL WEB CANARY PENDING**.

Operation: `web-ceo-workbench-action-f0-20260913-sol-001`.

This source adds the bounded attended action sibling to the protected Workbench Read surface. It exists so an authorized Web CEO can make one exact selected-project text change and run owner-approved finite validation commands without receiving a generic filesystem, shell, host, credential, Git publication, browser, process-PID, or administrator tool.

It does **not** make a Web CEO autonomous, install a ChatGPT app, create an Executive Job/Attempt/Worker, grant branch ownership, commit/push/merge source, select provider accounts, or bypass ChatGPT platform safety. Source tests prove the implementation boundary only; they do not prove that a particular ChatGPT model/mode will dispatch the modifying tool.

## Tool surface

The model-visible MCP surface is deliberately bounded to eight tools:

| Tool | Effect | Input authority |
|---|---|---|
| `prepare_text_patch` | read-only | selected project ref, relative path, `CREATE` or one unique-text `REPLACE`, expected preimage for replacement |
| `commit_text_patch` | modifying | **only** the short-lived signed `action_ref` returned by preparation |
| `reconcile_text_patch` | read-only | the original signed `action_ref`; never creates or replays another action |
| `list_validation_recipes` | read-only | selected project ref; returns only owner-configured recipes |
| `prepare_attended_command` | read-only | selected project ref + owner recipe id, with optional lower timeout/output ceilings |
| `start_attended_command` | modifying | **only** the signed `command_ref` returned by preparation |
| `reconcile_attended_command_start` | read-only | original signed `command_ref`; observes the original start effect without replay |
| `read_process` | read-only | original live `command_ref` + bounded stdout/stderr cursors |

The annotations are truthful. `commit_text_patch` and `start_attended_command` are advertised as modifying/destructive and idempotent only for the *same prepared reference*. They are not disguised as reads to influence platform classification.

The model never supplies an absolute root, machine, worktree, branch, account, credential, environment, shell, executable, network destination, process PID, action-signing key, source-writer identity, or effect state. Validation executables and argv are owner configuration, not model input.

## Owner-bound action

One runtime owns one already-authorized selected project descriptor and consumes an existing Business authentication policy with exactly `workbench.action` scope. The owner-issued lease binds:

- pseudonymous subject and OAuth client;
- project, attended context, responsibility, operation, owner and capability generation;
- exact project root device/inode;
- explicit relative-path allowlist;
- committed baseline when known;
- expiry.

Preparation captures that authority plus the exact pre/post image into a short-lived HMAC-signed action reference. The service reads one owner-provisioned generation key from a fixed `0600` file; the model never receives or selects it. Keeping that key stable across ordinary service restart lets the original signed action remain reconcilable until its own lease/TTL expires, without creating an action registry or replay database. Key rotation is therefore a generation/reconciliation event and must not strand an unresolved `EFFECT_UNKNOWN` action.

Every prepare/commit/reconcile re-resolves current binding. A prepared action cannot be remapped to another project, operation, responsibility, root, generation or caller.

## Source and effect semantics

`REPLACE` requires the caller-supplied current SHA-256 to match and requires `old_text` to occur exactly once. `CREATE` requires the target to be absent. Paths are descriptor-relative; absolute, `..`, symlink and non-allowlisted paths refuse.

Commit builds a same-directory candidate, revalidates source/binding immediately before publication, applies at most once, and reads the postimage. The common effect vocabulary is:

```text
NOT_APPLIED | APPLIED | EFFECT_UNKNOWN
```

Same-action replay observes an already matching postimage and returns `APPLIED` without issuing a second write. Changed/foreign source is not overwritten intentionally; it returns or reconciles to `EFFECT_UNKNOWN`. A lost client response is never permission to prepare another action or fail over to another actuator.

F0 depends on the owner-issued project binding to exclude concurrent authorized writers. It does not claim a kernel-level compare-and-swap primitive against an uncooperative process that mutates the same path in the final filesystem publication window. Production admission therefore requires an isolated or otherwise writer-fenced disposable workspace for the first canary, and a stronger local-source fence before any unattended mutation claim.

## Bounded attended process semantics

Command execution is not a generic shell. The owner configuration contains a sorted, unique set of exact `ValidationRecipe` values: recipe id, description, absolute executable argv, timeout ceiling, and stdout/stderr retention ceiling. Shell interpreters, `/usr/bin/env`, and `osascript` are refused as recipe executables; the model can only choose a listed recipe and may lower its time/output ceilings.

Preparation binds the current caller, selected-project authority, root identity, committed baseline, exact recipe digest, and exact internal runner digest into a short-lived HMAC `command_ref`. Before launch, the owner reopens and hashes the runner and executes those exact verified bytes through `/dev/fd`; a path swap after preparation refuses before command state is created. The wrapper launches the owner-selected argv with no stdin, a fixed minimal environment, a new process group, no core dumps, and a bounded file-descriptor budget.

Per-command state lives under one owner-selected private `0700` process directory. The owner writes/validates `0600` start/ready/child/terminal receipts, a liveness lock, and bounded stdout/stderr evidence. A root-level command lock makes concurrent same-ref starts one physical launch. Timeout, cancellation, output overflow, or a surviving descendant is terminated/fail-closed; command output is pipe-bounded rather than using `RLIMIT_FSIZE`, so legitimate project artifacts are not silently size-capped.

Process start uses the same effect vocabulary as text patches. Critically, a runner failure after the child has physically spawned but before a durable child receipt is available is `EFFECT_UNKNOWN`, never `NOT_APPLIED`. Terminal receipts carry explicit effect truth and retained-byte counts; reconciliation verifies the receipt against the retained files. Effect reconciliation can survive command-ref expiry or later binding revocation for the original authenticated principal, while output reads remain subject to the current binding and live command-ref policy. A lost start response is reconciled with the same `command_ref`; it is never permission to prepare or start a replacement command.

This process owner is intentionally for finite attended validation/build commands. It is not a daemon supervisor, background worker scheduler, terminal emulator, arbitrary package installer, network policy owner, deployment actuator, or Executive Job/Attempt/Worker substitute.

## Platform-dispatch receipt

The MCP adapter emits one privacy-safe process telemetry line **after successful auth/schema admission and before invoking the action port**:

```text
MMX_WORKBENCH_ACTION_CALL_RECEIVED { ... }
```

The payload contains only a schema, `RECEIVED` phase, tool name, pseudonymous subject/client refs and a SHA-256 `call_ref`. It contains no patch text, action token, path, credential or absolute project location. This telemetry is diagnostic evidence, not an action ledger or retry authority.

For a canary whose service/log channel is independently healthy:

- ChatGPT reports a block **and no receipt exists**: classify the attempted MCP dispatch as `PRE_DISPATCH_BLOCKED / NOT_APPLIED` for this server path;
- a receipt exists and Workbench refuses: diagnose Workbench auth/binding/source policy;
- Workbench returns and a text postimage or process child receipt proves the effect: `APPLIED`;
- receipt/effect may have occurred but the response is lost: `EFFECT_UNKNOWN` until the matching text-patch or command-start reconciliation tool resolves it.

Absence of a receipt is not meaningful when the service or its log channel is itself unavailable.

## Runnable service

`scripts/mastermind_workbench_action_server.py` exposes only a configured loopback service. Its serving mode accepts one absolute owner configuration path; it does not accept host, project root, patch path, token key, credential or tunnel selectors on the command line.

The closed service configuration is `mastermind.workbench_action_service.v1` and contains owner-selected policy/project/audit paths, a private `0700` process-state directory, one fixed `0600` action-key path, a sorted owner recipe set, fixed loopback bind/authority, bounded concurrency/timeouts/TTL, and the exact stable lease. The service opens secure directory descriptors, reads the action-key file, composes the existing Business JWT/JWKS verifier and durable auth audit, and uses the shared `BoundedSyncExecutor`. The same integrity key domain-separates text-patch and command references. It is service-integrity material, not a provider/account credential, and installation must place it through the existing approved host/secret-owning path rather than model input.

`--describe` is dependency-free and reports `BUILT_NOT_PROVEN`; it never claims installation.

## Required C1 Personal Web-seat canary

The current attended qualification target is the Chairman-selected **C1 Personal** ChatGPT account, using one private tunnel/process and one custody-owned workspace for that account. This canary qualifies the actual model/tool route; it does not infer capability for another account, mode, or provider session.

The real canary must use a disposable writer-fenced project acquired/reused through the canonical `mmx-workspace` custody owner and the actual intended tunnel/auth principal. It must prove, in order:

1. app connection and `tools/list` exposes exactly the eight bounded Action tools;
2. `prepare_text_patch` reaches the service and returns `PREPARED` with zero source effect;
3. `commit_text_patch(action_ref)` reaches the service and reads back `APPLIED`, with same-ref replay producing no second write;
4. lost text-patch response is recovered only with `reconcile_text_patch`; stale/out-of-scope patch requests refuse with zero unauthorized effect;
5. `list_validation_recipes` exposes only the installed owner recipes and `prepare_attended_command` has zero process effect;
6. `start_attended_command(command_ref)` launches the exact prepared recipe once, `read_process` returns bounded output/terminal truth, and same-ref replay produces no second child;
7. a simulated/lost command-start response is recovered only with `reconcile_attended_command_start`; timeout/output-limit and stale/binding-change paths fail closed;
8. service receipts distinguish platform pre-dispatch absence from Workbench refusal, and exact source/app/recipe generation plus rollback/disarm are recorded.

Controls on other Web CEO seats may be useful, but each route changes capability state only from direct evidence on that route.

## Remaining production gates

This branch has source and local/adjacent test evidence only. Before any `PROVEN_LIVE` claim it still needs:

- current-base hosted CI/security and independent exact-head review;
- protected source release under ordinary repository protection;
- reviewed installation/supervision/rollback on the selected host;
- Secure MCP Tunnel / ChatGPT app enrollment with the dedicated `workbench.action` resource;
- actual selected-project/attended-Web binding and intended principal;
- the C1 Personal Web-seat canary above;
- post-canary disarm/rollback proof and a final Sol acceptance decision.

A source merge, successful service startup, or a passing local control is not evidence that the selected Web route accepts the modifying calls.
