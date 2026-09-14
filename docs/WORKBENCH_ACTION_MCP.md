# First-party Workbench Action F0

Status: **BUILT_NOT_PROVEN / RUNNABLE_LOOPBACK_SOURCE / NOT INSTALLED / ASTRA-PRO PLATFORM CANARY PENDING**.

Operation: `web-ceo-workbench-action-f0-20260913-sol-001`.

This source composes bounded protected Read and attended text-patch operations in one fixed-channel runtime. It exists so an authorized Web CEO can inspect an allowed file, preview one exact replacement, and prepare/commit that replacement without receiving a generic filesystem, shell, host, credential, Git publication, browser, or administrator tool.

It does **not** make a Web CEO autonomous, install a ChatGPT app, create an Executive Job/Attempt/Worker, grant branch ownership, commit/push/merge source, select provider accounts, or bypass ChatGPT platform safety. Source tests prove the implementation boundary only; they do not prove that a particular ChatGPT model/mode will dispatch the modifying tool.

## Tool surface

The current Phase A model-visible MCP surface is deliberately only:

| Tool | Effect | Input authority |
|---|---|---|
| `workspace_manifest` | read-only | no model-selected authority; reports the current fixed project binding and six-tool source capability as `BUILT_NOT_PROVEN` |
| `read_project_file` | read-only | one allowed relative path plus bounded line paging and optional expected preimage |
| `preview_text_replace` | read-only | one allowed relative path, required preimage, and one exact in-memory replacement; never persists |
| `prepare_text_patch` | read-only | selected project ref, relative path, `CREATE` or one unique-text `REPLACE`, expected preimage for replacement |
| `commit_text_patch` | modifying | **only** the short-lived signed `action_ref` returned by preparation |
| `reconcile_text_patch` | read-only | the original signed `action_ref`; never creates or replays another action |

The annotations are truthful. The three Read tools and patch preparation/reconciliation are read-only. `commit_text_patch` is advertised as modifying/destructive, idempotent for the *same prepared action*, and closed-world. It is intentionally not disguised as a read in an attempt to influence platform classification. The standalone Read profile's `preview_project_command` is not exposed here because its preview recipes are not this executable profile's reviewed command contract.

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

Commit and reconcile also return `cleanup_state: CLEAN | UNCERTAIN`. This reports physical descriptor/lock release separately from the action effect. A qualified historical `APPLIED` receipt may coexist with `UNCERTAIN`; that uncertainty is sticky for the runtime owner and never authorizes replay.

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

The closed service configuration is `mastermind.workbench_action_service.v1` and contains owner-selected policy/project/audit/artifact paths, a 64-hex host identity, one fixed action-key path, fixed loopback bind/authority, bounded concurrency/timeouts/TTL, and the exact stable lease. The service opens secure directory descriptors, retains one artifact-store descriptor and host/boot binding for its lifetime, reads the exact `0600` action-key file, composes the existing Business JWT/JWKS verifier and durable auth audit, and uses the shared `BoundedSyncExecutor`. The host identity and key are host-owned configuration, not model input or provider/account credentials; installation must place them through the existing approved host/secret-owning path.

Example without secrets:

```json
{
  "schema": "mastermind.workbench_action_service.v1",
  "policy_file": "/srv/mastermind/workbench/policy.json",
  "project_root": "/srv/mastermind/workbench/disposable-01",
  "audit_directory": "/srv/mastermind/workbench/audit-c1",
  "artifact_directory": "/srv/mastermind/workbench/artifacts-c1",
  "host_id": "<hex64 host identity>",
  "action_key_file": "/srv/mastermind/workbench/keys/action-c1.hex",
  "bind_host": "127.0.0.1",
  "bind_port": 19443,
  "incoming_authority": "127.0.0.1:19443",
  "max_concurrency": 2,
  "io_timeout_seconds": 5.0,
  "close_timeout_seconds": 5.0,
  "action_ttl_ms": 60000,
  "lease": {
    "expected_subject_digest": "<hex64>",
    "expected_client_ref": "<hex64>",
    "resource": "https://workbench-action.example/mcp",
    "required_scopes": ["workbench.action"],
    "project_ref": "project:<hex64>",
    "context_ref": "context:<hex64>",
    "responsibility_ref": "responsibility:<hex64>",
    "operation_ref": "operation:<hex64>",
    "owner_ref": "owner:<hex64>",
    "generation": "generation:<hex64>",
    "allowed_paths": ["sample.py"],
    "committed_head": null,
    "lease_expires_at_ms": 1800000300000
  }
}
```

`--describe` is dependency-free and reports `BUILT_NOT_PROVEN`; it never claims installation.

## Fixed-channel stdio tunnel entry point

Status: **BUILT_NOT_PROVEN / TRANSPORT SEAM ONLY / NOT INSTALLED / NOT ENROLLED**.

The HTTP/OAuth service above stays exactly as it is. The tunnel entry point is a second composition of the *same* runtime: one host-selected Secure MCP Tunnel channel → one stdio child (`scripts/mastermind_workbench_action_stdio.py`) → `WorkbenchActionRuntime.open_channel(...)` → the existing text patch port plus the borrowed Read port. It exists so a tunnel-terminated client can reach the six-tool Phase A surface without a second authentication service being invented on this path.

The borrowed Read port opens no root and owns no executor, lease, audit sink, descriptor, or cache. Every callback re-resolves the current channel/project binding and maps its exact root descriptor identity, context, owner, generation, allowed paths, expiry, and committed baseline into a `ReadScope`. Its synchronous operation executes through the same runtime `run_io` used by patch work. Read-port refusals become closed MCP errors with `isError=true`.

**Authority model.** The tunnel association authenticates a *channel*, not a cryptographically attested end user. Admission therefore never claims a `VerifiedPrincipal`, JWT, token verification, or an OAuth-accepted audit row. The channel is an exact `FixedTunnelChannel` triple (tunnel/organization/workspace) selected by the host; `channel_subject_digest`/`channel_client_ref` derive domain-separated opaque digests (`mastermind.secure_mcp_tunnel_channel.v1`) that must already be the stable lease's pinned `expected_subject_digest`/`expected_client_ref`, and `WorkbenchActionRuntime` re-checks them live on every tool call. Receipts and audit expose `authority_kind = "secure_mcp_tunnel_channel"` plus the opaque `channel_ref`. There is no end-user identity claim. One tunnel per account and one workspace per account are separate host compositions; they are not interchangeable here.

**Durable channel admission.** Every recognized tool call persists one `ChannelAuditEvent` (`mastermind.business_mcp_auth_channel_audit.v1`) in the same `auth-audit.jsonl` mechanics (same descriptor/lock/append/fsync/poison/close discipline; the OAuth event encoding is unchanged byte-for-byte) **before** dispatch; an audit failure blocks the effect (`CHANNEL_AUDIT_UNAVAILABLE`). The event carries only `accepted`, `code` (`accepted` | `channel_refused` | `request_refused`), the sink's `policy_id`, `schema`, opaque `channel_ref`, the fixed `tool` name, and an optional `action_digest` (SHA-256 of the action reference — never the token itself). No path, patch content, or credential is ever audited. Unknown tool names are not channel admissions and are not audited.

**Configuration.** The closed document is `mastermind.workbench_action_tunnel.v1`, loaded with the same secure acquisition pattern as the loopback service (absolute same-euid paths, duplicate-key rejection, exact schema, `O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC`, `nlink=1`, regular-file/final identity re-check, bounded bytes; `0600` 64-hex-char action key; root/audit directories same-owner and not group/world-writable). Example without secrets:

```json
{
  "schema": "mastermind.workbench_action_tunnel.v1",
  "tunnel_id": "c1-personal-tunnel",
  "organization_id": "org-example-01",
  "workspace_id": "ws-disposable-01",
  "audit_policy_id": "workbench-action-tunnel-c1",
  "project_root": "/srv/mastermind/workbench/disposable-01",
  "audit_directory": "/srv/mastermind/workbench/audit-c1",
  "artifact_directory": "/srv/mastermind/workbench/artifacts-c1",
  "host_id": "<hex64 host identity>",
  "action_key_file": "/srv/mastermind/workbench/keys/action-c1.hex",
  "max_concurrency": 2,
  "io_timeout_seconds": 5.0,
  "close_timeout_seconds": 5.0,
  "action_ttl_ms": 60000,
  "lease": {
    "expected_subject_digest": "<channel_subject_digest of the triple>",
    "expected_client_ref": "<channel_client_ref of the triple>",
    "resource": "https://workbench-action.example/mcp",
    "required_scopes": ["workbench.action"],
    "project_ref": "project:<hex64>",
    "context_ref": "context:<hex64>",
    "responsibility_ref": "responsibility:<hex64>",
    "operation_ref": "operation:<hex64>",
    "owner_ref": "owner:<hex64>",
    "generation": "generation:<hex64>",
    "allowed_paths": ["sample.py"],
    "committed_head": null,
    "lease_expires_at_ms": 1800000300000
  }
}
```

Run: `/path/to/python scripts/mastermind_workbench_action_stdio.py --config /srv/mastermind/workbench/tunnel-c1.json` (stdio MCP on stdin/stdout; diagnostics on stderr). `--describe` is dependency-free and never claims installation. The lease's digest fields are derived by the host from the exact channel triple — the model can never supply the channel, lease, key, or locations.

**Read/patch guarantees preserved.** The fixed-channel entry point has one runtime owner (root descriptor, revoke, `run_io`, physical drain, audit closure). It composes the existing text patch port and the borrowed Read port without another physical owner. Each advertised input and success output has a bounded closed schema; stdio dispatch uses bounded full-schema validation with `validate_input=False`, fixed sanitized error payloads (`{"code": ...}`, never reflected rejected values), and explicit `CallToolResult.isError`. The same stable action key across ordinary restarts keeps an already-prepared action reconcilable until its own lease/TTL expiry; key rotation remains a generation boundary and must not strand an unresolved `EFFECT_UNKNOWN`.

**Not claimed by this seam.** No tunnel enrollment, native account admission, ChatGPT app connection, command execution (`run_project_command` remains pending final composition), install, supervisor, or `PROVEN_LIVE`. Honest write admission on the C1 Personal account is the parent rollout's next step.

## Required Astra Pro Web-seat canary

The product target is to restore useful modifying CEO work specifically on the affected **Business Premium Astra Pro** path where generic external writes have shown pre-dispatch safety refusals. This is a qualification of that model/mode/tool route, not a restriction on other Web CEO modes.

The real canary must use a disposable writer-fenced project and the actual intended ChatGPT app/tunnel/auth principal. It must prove, in order:

1. app connection and `tools/list` exposes exactly the final reviewed bounded inventory for that installed generation (Phase A source exposes six; command integration will increase this to ten);
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
