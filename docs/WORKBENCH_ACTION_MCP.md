# First-party Workbench Action F0

Status: **BUILT_NOT_PROVEN / RUNNABLE_LOOPBACK_SOURCE / NOT INSTALLED / ASTRA-PRO PLATFORM CANARY PENDING**.

Operation: `web-ceo-workbench-action-f0-20260913-sol-001`.

This source adds the bounded attended write sibling to the protected Workbench Read surface. It exists so an authorized Web CEO can make one exact selected-project text change without receiving a generic filesystem, shell, host, credential, Git publication, browser, or administrator tool.

It does **not** make a Web CEO autonomous, install a ChatGPT app, create an Executive Job/Attempt/Worker, grant branch ownership, commit/push/merge source, select provider accounts, or bypass ChatGPT platform safety. Source tests prove the implementation boundary only; they do not prove that a particular ChatGPT model/mode will dispatch the modifying tool.

## Tool surface

The model-visible MCP surface is deliberately only:

| Tool | Effect | Input authority |
|---|---|---|
| `prepare_text_patch` | read-only | selected project ref, relative path, `CREATE` or one unique-text `REPLACE`, expected preimage for replacement |
| `commit_text_patch` | modifying | **only** the short-lived signed `action_ref` returned by preparation |
| `reconcile_text_patch` | read-only | the original signed `action_ref`; never creates or replays another action |

The annotations are truthful. `commit_text_patch` is advertised as modifying/destructive, idempotent for the *same prepared action*, and closed-world. It is intentionally not disguised as a read in an attempt to influence platform classification.

The model never supplies an absolute root, machine, worktree, branch, account, credential, environment, shell, executable, network destination, action-signing key, source-writer identity, or effect state. Those remain owner-derived.

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

## Platform-dispatch receipt

The MCP adapter emits one privacy-safe process telemetry line **after successful auth/schema admission and before invoking the action port**:

```text
MMX_WORKBENCH_ACTION_CALL_RECEIVED { ... }
```

The payload contains only a schema, `RECEIVED` phase, tool name, pseudonymous subject/client refs and a SHA-256 `call_ref`. It contains no patch text, action token, path, credential or absolute project location. This telemetry is diagnostic evidence, not an action ledger or retry authority.

For a canary whose service/log channel is independently healthy:

- ChatGPT reports a block **and no receipt exists**: classify the attempted MCP dispatch as `PRE_DISPATCH_BLOCKED / NOT_APPLIED` for this server path;
- a receipt exists and Workbench refuses: diagnose Workbench auth/binding/source policy;
- Workbench returns and postimage matches: `APPLIED`;
- receipt/effect may have occurred but the response is lost: `EFFECT_UNKNOWN` until `reconcile_text_patch` resolves it.

Absence of a receipt is not meaningful when the service or its log channel is itself unavailable.

## Runnable service

`scripts/mastermind_workbench_action_server.py` exposes only a configured loopback service. Its serving mode accepts one absolute owner configuration path; it does not accept host, project root, patch path, token key, credential or tunnel selectors on the command line.

The closed service configuration is `mastermind.workbench_action_service.v1` and contains owner-selected policy/project/audit paths, one fixed action-key path, fixed loopback bind/authority, bounded concurrency/timeouts/TTL, and the exact stable lease. The service opens secure directory descriptors, reads the exact `0600` action-key file, composes the existing Business JWT/JWKS verifier and durable auth audit, and uses the shared `BoundedSyncExecutor`. The key is service-integrity material, not a provider/account credential, and installation must place it through the existing approved host/secret-owning path rather than model input.

`--describe` is dependency-free and reports `BUILT_NOT_PROVEN`; it never claims installation.

## Required Astra Pro Web-seat canary

The product target is to restore useful modifying CEO work specifically on the affected **Business Premium Astra Pro** path where generic external writes have shown pre-dispatch safety refusals. This is a qualification of that model/mode/tool route, not a restriction on other Web CEO modes.

The real canary must use a disposable writer-fenced project and the actual intended ChatGPT app/tunnel/auth principal. It must prove, in order:

1. app connection and `tools/list` exposes exactly the three bounded tools;
2. `prepare_text_patch` reaches the service and returns `PREPARED` with zero source effect;
3. `commit_text_patch(action_ref)` reaches the service and returns/reads back `APPLIED`;
4. replaying the same prepared action produces no second write;
5. a simulated/lost commit response is recovered with `reconcile_text_patch`, never replayed blindly;
6. an outside-allowlist or stale-preimage request is refused with zero unauthorized source effect;
7. service logs distinguish platform pre-dispatch absence from Workbench receipt/refusal;
8. exact source/app generation and rollback/disarm are recorded.

Run the same bounded canary as controls in **Sol** and **Astra Extra High** when useful, but do not downgrade, gate or relabel those modes merely because Astra Pro has shown a different failure pattern. Their capability posture changes only from direct evidence on their own route.

## Remaining production gates

This branch has source and local/adjacent test evidence only. Before any `PROVEN_LIVE` claim it still needs:

- current-base hosted CI/security and independent exact-head review;
- protected source release under ordinary repository protection;
- reviewed installation/supervision/rollback on the selected host;
- Secure MCP Tunnel / ChatGPT app enrollment with the dedicated `workbench.action` resource;
- actual selected-project/attended-Web binding and OAuth principal;
- the Astra Pro Web-seat canary above;
- post-canary disarm/rollback proof and a final Sol acceptance decision.

A source merge, successful service startup, or a passing Sol control is not evidence that Astra Pro's platform safety layer accepts the modifying call.
