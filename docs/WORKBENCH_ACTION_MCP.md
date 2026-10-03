# First-party Workbench Action F0

Status: **BUILT_NOT_PROVEN / RUNNABLE LOCAL SOURCE / NOT INSTALLED / C1 PERSONAL CANARY PENDING**.

Base operation: `web-ceo-workbench-action-f0-20260913-sol-001`.

Artifact Return extension: `web-ceo-artifact-return-f0-20260918-sol-001`.

This source composes bounded protected Read, attended text-patch operations, three pinned command recipes, and exact owner-bound artifact return in one fixed-channel runtime. It exists so an authorized Web CEO can inspect an allowed file, preview and apply one exact replacement, run checksum, intentional-refusal, or deterministic PNG source-fingerprint canaries, and consume retained text or binary output without receiving a generic filesystem, shell, host, credential, Git publication, browser, or administrator tool.

It does **not** make a Web CEO autonomous, install a ChatGPT app, create an Executive Job/Attempt/Worker, grant branch ownership, commit/push/merge source, select provider accounts, or bypass ChatGPT platform safety. Source tests prove the implementation boundary only; they do not prove that a particular ChatGPT model/mode will dispatch the modifying tool.

## Tool surface

The attended fixed-channel MCP surface contains exactly eleven tools:

| Tool | Effect | Input authority |
|---|---|---|
| `workspace_manifest` | read-only | no model-selected authority; reports the current fixed project binding and eleven-tool `attended_workbench_f0` source capability as `BUILT_NOT_PROVEN` |
| `read_project_file` | read-only | one allowed relative path plus bounded line paging and optional expected preimage |
| `preview_text_replace` | read-only | one allowed relative path, required preimage, and one exact in-memory replacement; never persists |
| `prepare_text_patch` | read-only | selected project ref, relative path, `CREATE` or one unique-text `REPLACE`, expected preimage for replacement |
| `commit_text_patch` | modifying | **only** the short-lived signed `action_ref` returned by preparation |
| `reconcile_text_patch` | read-only | the original signed `action_ref`; never creates or replays another action |
| `prepare_project_command` | read-only | selected project ref, allowed relative path, exact preimage, and one of three pinned recipe IDs; starts no process |
| `run_project_command` | process start | **only** the short-lived signed `action_ref` returned by command preparation |
| `read_action_result` | read-only | original command action ref plus bounded UTF-8 stream/line/page selectors; never starts or replays a process |
| `read_action_artifact` | read-only | signed owner-issued artifact ref plus byte offset and length only; no path, root, slot, media-type, or host selector |
| `reconcile_action` | read-only | original command action ref; classifies retained evidence without spawning |

The annotations are truthful. The three Read tools, both prepare tools, both reconcile tools, result paging, and exact artifact reading are read-only. `commit_text_patch` and `run_project_command` are advertised as modifying/destructive, idempotent for the *same prepared action*, and closed-world. The standalone Read profile's `preview_project_command` is not exposed here because its preview recipes are not this executable profile's reviewed command contract.

`workspace_manifest` validates authority through the borrowed Read manifest call, then labels the complete envelope and data as `attended_workbench_f0` with `mutation_allowed=true`. Its effects are `file_write=true`, `process_start=true`, `network_call=false`, and `durable_prepare=false`. Preparation is a stateless, short-lived signed reference; it is not a durable queue, ledger, or pending action. Individual Read and preview results retain the borrowed `pro_read_prepare` profile with `mutation_allowed=false`.

The model never supplies an absolute root, machine, worktree, branch, account, credential, environment, shell, executable, recipe path/hash, network destination, action-signing key, source-writer identity, or effect state. Those remain owner-derived.

## Owner-bound action

One runtime owns one already-authorized selected project descriptor. The eleven-tool stdio profile derives authority from the host-selected Secure MCP Tunnel channel. The separate three-tool HTTP patch profile uses the existing Business JWT/OAuth policy. Both use an internal `workbench.action` lease scope; this is not the tunnel client's `main` channel name or the ChatGPT app's `noAuth` setting. The owner-issued lease binds:

- pseudonymous channel subject/client references, or the verified OAuth subject/client for the HTTP profile;
- project, attended context, responsibility, operation, owner and capability generation;
- exact project root device/inode;
- explicit relative-path allowlist;
- committed baseline when known;
- expiry.

Patch and command preparation capture that authority plus the exact preimage and intended operation into a short-lived HMAC-signed action reference. The service reads one owner-provisioned generation key from a fixed `0600` file; the model never receives or selects it. Apply/run requires an unexpired reference. Evidence decoding can accept an expired reference, but current matching authority still gates reconciliation and result access. Ordinary child restart must retain the key, canonical artifact store, and required host/project/channel/generation bindings. Preparation is stateless; execution evidence is durable. Key rotation is therefore a generation/reconciliation event and must not strand an unresolved `EFFECT_UNKNOWN` action.

Every prepare/commit/reconcile re-resolves current binding. A prepared action cannot be remapped to another project, operation, responsibility, root, generation or caller.

## Source and effect semantics

`REPLACE` requires the caller-supplied current SHA-256 to match and requires `old_text` to occur exactly once. `CREATE` requires the target to be absent. Paths are descriptor-relative; absolute, `..`, symlink and non-allowlisted paths refuse.

Commit builds a same-directory candidate, revalidates source/binding immediately before publication, applies at most once, and reads the postimage. The common effect vocabulary is:

```text
NOT_APPLIED | APPLIED | EFFECT_UNKNOWN
```

Commit and reconcile also return `cleanup_state: CLEAN | UNCERTAIN`. This reports physical descriptor/lock release separately from the action effect. A qualified historical `APPLIED` receipt may coexist with `UNCERTAIN`; that uncertainty is sticky for the runtime owner and never authorizes replay.

Same-action replay requires matching qualified evidence and postimage to return `APPLIED` without issuing a second write. A matching postimage alone is insufficient. Changed/foreign source is not overwritten intentionally; it returns or reconciles to `EFFECT_UNKNOWN`. A lost client response is never permission to prepare another action or fail over to another actuator.

Command execution accepts only `canary_checksum`, `canary_refuse`, and `source_fingerprint_png`, each bound to a source-pinned SHA-256 recipe. The PNG recipe independently verifies the descriptor-held input preimage and emits one deterministic `image/png` source-integrity diagnostic without network, ambient environment, an output path, or a third-party dependency. The host pins an absolute Python executable and its SHA-256, the recipe root, and a deadline of at most 15 seconds. The child receives a closed environment and descriptor-bound project/file inputs. Exit `0` and intentional exit `7` are completed MCP results, not transport failures. Stdout/stderr are retained in the same Action artifact store and paged or returned as exact bytes without replay. Process identity, cleanup state, and effect state remain separate facts.

Command input is limited to 65,536 bytes; each retained output stream is limited to 65,536 bytes. A result page contains at most 128 lines and 8,192 UTF-8 bytes. An artifact transfer chunk contains at most 49,152 raw bytes so the base64/MCP envelope remains beneath the fixed 262,144-byte wire ceiling. The configured process deadline must be greater than zero and no more than 15 seconds.

F0 depends on the owner-issued project binding to exclude concurrent authorized writers. It does not claim a kernel-level compare-and-swap primitive against an uncooperative process that mutates the same path in the final filesystem publication window. Production admission therefore requires an isolated or otherwise writer-fenced disposable workspace for the first canary, and a stronger local-source fence before any unattended mutation claim.


## Exact artifact return

Workbench Action remains the sole byte owner. A qualified command result now projects one immutable descriptor for each retained stream. The descriptor carries an `artifact_id`, short-lived signed `artifact_ref`, media type, retained byte length, SHA-256, truncation/size state, Action/process/source provenance, transfer ceilings, and explicit issue/expiry times. `artifact_id` binds the action, project, generation, recipe, relative source label, source preimage and inode identity, output slot, media type, byte length, digest, and truncation state. Renewing an artifact reference changes its expiry-bearing token but not that immutable identity.

`read_action_artifact` accepts only `{artifact_ref, offset?, max_bytes?}`. The signed reference fixes the caller/channel, project/context/responsibility/operation/owner/generation, root and artifact-store identities, source, recipe, stream, media type, byte length, digest and truncation state. The caller cannot substitute an absolute path, traversal, symlink target, credential file, arbitrary machine root, alternate output slot, or media type. Every read re-resolves the live channel/project lease, re-qualifies the original command result, reads through the incumbent no-follow artifact store, verifies length and SHA-256, rereads the exact slot, and reauthorizes before releasing content. Expired references return `ARTIFACT_EXPIRED`; revocation/generation movement returns `ARTIFACT_BINDING_CHANGED`; a removed, replaced, mutated, symlinked, hard-linked, or otherwise unqualified artifact returns `ARTIFACT_UNAVAILABLE`. There is no result cache, so missing bytes are never reconstructed from an earlier response.

UTF-8 artifacts use byte offsets but are returned only on code-point boundaries; a range that starts inside a code point or cannot fit one complete code point is refused. `read_action_result` remains a UTF-8 text pager and returns `ARTIFACT_TEXT_UNSUPPORTED` for a binary stream without changing the Action's known effect or cleanup truth. Successful, non-truncated PNG stdout must also pass bounded PNG structure and CRC validation before it is advertised or returned as MCP `ImageContent`; refusal, partial, malformed, or truncated PNG-recipe stdout is retained as `application/octet-stream` and returned only through the blob path. Other binary ranges are returned as `BlobResourceContents`; binary bytes never pass through text decoding. Base64 is only the MCP wire encoding and is verified against the returned raw-byte count and chunk SHA-256 before release. A producer stream that reached its retention ceiling is explicitly `retained_prefix`; its digest and length never pretend to describe unavailable producer bytes.

This adds no artifact database, lifecycle table, URL bucket, public listener, arbitrary file reader, or second evidence store. Executive Job/Attempt lineage may later carry these opaque descriptors where that owner genuinely has a join, but Executive OS does not become the byte store.

## Platform-dispatch receipt

The HTTP adapter emits one privacy-safe process telemetry line **after successful auth/schema admission and before invoking the action port**:

```text
MMX_WORKBENCH_ACTION_CALL_RECEIVED { ... }
```

The payload contains only a schema, `RECEIVED` phase, tool name, pseudonymous subject/client refs and a SHA-256 `call_ref`. It contains no patch text, action token, path, credential or absolute project location. This telemetry is diagnostic evidence, not an action ledger or retry authority.

The configured stdio launcher does not supply this optional telemetry sink. Its actual dispatch evidence is the durable `ChannelAuditEvent` described below: every recognized tool name records accepted or refused channel admission before dispatch. An accepted row establishes admission, not completion or effect. Missing optional stderr telemetry must never be interpreted as a C1 platform block.

For a canary whose service and applicable receipt channel are independently healthy:

- ChatGPT reports a block and no corresponding admission receipt exists: report that server admission was not observed; establish a platform pre-dispatch block only from separate platform evidence;
- a receipt exists and Workbench refuses: diagnose Workbench auth/binding/source policy;
- for a patch, a qualified matching action receipt and postimage establish `APPLIED`; for a command, qualified retained process/result evidence establishes `APPLIED`. A matching postimage or successful transport response alone is insufficient;
- receipt/effect may have occurred but the response is lost: `EFFECT_UNKNOWN` until `reconcile_text_patch` or `reconcile_action` resolves that original action;
- the modifying call was refused by fixed-channel admission before dispatch (for example the stable lease expired between prepare and commit/run): `CHANNEL_ADMISSION_REFUSED` with a durable `channel_refused` row for the exact action digest. After a same-carrier lease refresh, `reconcile_text_patch` / `reconcile_action` on that original reference return `NOT_APPLIED` (see **Pre-dispatch refusal reconciliation**). Recover with one replacement prepare/commit or prepare/run against the same preimage; the original reference expired with its lease and never applies.

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

The HTTP/OAuth service above stays exactly as it is. The tunnel entry point is a second composition of the *same* runtime: one host-selected Secure MCP Tunnel channel → one stdio child (`scripts/mastermind_workbench_action_stdio.py`) → `WorkbenchActionRuntime.open_channel(...)` → the existing text patch port, borrowed Read port, and closed command port. It exists so a tunnel-terminated client can reach the eleven-tool attended surface without a second authentication service being invented on this path.

The borrowed Read port opens no root and owns no executor, lease, audit sink, descriptor, or cache. Every callback re-resolves the current channel/project binding and maps its exact root descriptor identity, context, owner, generation, allowed paths, expiry, and committed baseline into a `ReadScope`. Its synchronous operation executes through the same runtime `run_io` used by patch work. Read-port refusals become closed MCP errors with `isError=true`.

**Authority model.** The tunnel association authenticates a *channel*, not a cryptographically attested end user. Admission therefore never claims a `VerifiedPrincipal`, JWT, token verification, or an OAuth-accepted audit row. The channel is an exact `FixedTunnelChannel` triple (tunnel/organization/workspace) selected by the host; `channel_subject_digest`/`channel_client_ref` derive domain-separated opaque digests (`mastermind.secure_mcp_tunnel_channel.v1`) that must already be the stable lease's pinned `expected_subject_digest`/`expected_client_ref`, and `WorkbenchActionRuntime` re-checks them live on every tool call. Receipts and audit expose `authority_kind = "secure_mcp_tunnel_channel"` plus the opaque `channel_ref`. There is no end-user identity claim. One tunnel per account and one workspace per account are separate host compositions; they are not interchangeable here.

**Durable channel admission.** Every recognized tool call persists one `ChannelAuditEvent` (`mastermind.business_mcp_auth_channel_audit.v1`) in the same `auth-audit.jsonl` mechanics (same descriptor/lock/append/fsync/poison/close discipline; the OAuth event encoding is unchanged byte-for-byte) **before** dispatch; an audit failure blocks the effect (`CHANNEL_AUDIT_UNAVAILABLE`). The event carries only `accepted`, `code` (`accepted` | `channel_refused` | `request_refused`), the sink's `policy_id`, `schema`, opaque `channel_ref`, the fixed `tool` name, and an optional `action_digest` (SHA-256 of the action reference — never the token itself). No path, patch content, or credential is ever audited. Unknown tool names are not channel admissions and are not audited.

**Pre-dispatch refusal reconciliation.** The durable admission ledger is also the only evidence that lets a reconcile classify an action with no artifact at all as `NOT_APPLIED`. Artifact absence alone stays `EFFECT_UNKNOWN` (an admitted commit/run may have been lost before its claim). The sink reads its own named ledger back through the same continuity proof an append uses (owned identity, owned size, owner lock, every line re-encoded byte-for-byte through the exact event encoders) and the tunnel classifies the rows for the exact action digest: `NOT_APPLIED` requires at least one `channel_refused` row for the matching modifying tool (`commit_text_patch` for `reconcile_text_patch`, `run_project_command` for `reconcile_action` / `read_action_result`) under this channel and policy identity, **no** accepted row for any modifying tool for that digest from any channel, an artifact store that still reports the action unclaimed, and (for patches) a source that still reads as never patched (`REPLACE` at its exact preimage, `CREATE` target absent). Any accepted modifying admission — including one the port later refused for expiry or preimage mismatch, which is not durably distinguishable from a loss before claim — a torn, foreign, off-policy or off-channel row, a rotated audit policy over the same ledger, identity or size drift of the named file, a moved-on source, or any ledger read failure keeps the action `EFFECT_UNKNOWN`. The ledger is consulted last, after artifact and source observation, so a modifying call admitted during the reconcile is seen. The read never appends, never poisons the sink, and never reopens admission; reconcile remains read-only, so the classification is re-derived from durable evidence on every call and survives restarts. The OAuth adapter composes the same ports without a ledger reader and is unchanged. This adds no ledger, queue, retry owner, or modifying action identity. Artifact Return adds one read-only tool while `reconcile_action` retains the common `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN` vocabulary.

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
  "python_executable": "/absolute/hash-locked/python3.12",
  "python_sha256": "<hex64 executable hash>",
  "recipe_root": "/absolute/protected/source/integrations/workbench_action_mcp/recipes",
  "process_deadline_seconds": 5.0,
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

**Read/patch/command guarantees preserved.** The fixed-channel entry point has one runtime owner (root descriptor, artifact-store descriptor, revoke, `run_io`, physical drain, audit closure). It composes the existing text patch port, borrowed Read port, and command port without another physical owner. Patch and command share the same token codec and exact artifact-store object. Each advertised input and success output has a bounded closed schema; stdio dispatch uses bounded full-schema validation with `validate_input=False`, fixed sanitized error payloads (`{"code": ...}`, never reflected rejected values), and explicit `CallToolResult.isError`. Responses are measured as their exact escaped MCP JSON-RPC envelope against the 262,144-byte wire cap; a predictably oversized text preview returns `PREVIEW_TOO_LARGE` without truncation. Across ordinary restarts, retain the same key, artifact store and required bindings; expired action references may still support evidence access under current matching authority, while apply/run requires an unexpired reference. Key rotation remains a generation boundary and must not strand an unresolved `EFFECT_UNKNOWN`.

**Not claimed by this seam.** No tunnel enrollment, native account admission, ChatGPT app connection, install, supervisor, or `PROVEN_LIVE`. Local command subprocess tests establish source behavior only. Honest modifying-tool admission on the C1 Personal account is the parent rollout's next step.

## Required C1 Personal Web-seat canary

The first product target is the existing C1 Personal account, its dedicated private Workbench tunnel, and its single associated Personal workspace. Current user evidence says that surface offers custom change/write capability; the canary must measure honest modifying annotations and calls directly. No Business-only condition is assumed, and results from another account, workspace, model, plugin, or Studio Direct route do not qualify this Workbench path.

The initial rollout retains its already assigned external-SSD helper worktree; this source integration does not claim a new workspace acquisition. Future attended Web workspace acquisition, reuse, and release follow the canonical `mmx-workspace` custody contract and external storage policy. Preserve the existing checkout and any unresolved action evidence; do not create another custody registry.

The real canary must use a disposable writer-fenced project and the actual intended ChatGPT app/tunnel/channel binding. It must prove, in order:

1. app connection and `tools/list` exposes exactly the final reviewed eleven-tool bounded inventory for that installed generation;
2. `prepare_text_patch` reaches the service and returns `PREPARED` with zero source effect;
3. `commit_text_patch(action_ref)` reaches the service and returns/reads back `APPLIED`;
4. prepare/run `canary_checksum` completes with actual exit `0`, `canary_refuse` completes with actual exit `7` while remaining an MCP success, and `source_fingerprint_png` emits a deterministic PNG;
5. `read_action_result` pages all retained UTF-8 lines, `read_action_artifact` reconstructs exact text ranges and renders the exact PNG bytes with matching length/SHA-256, and `reconcile_action` observes the same actions without a second spawn;
6. replaying the same prepared patch action produces no second write;
7. simulated/lost responses are recovered with the appropriate reconcile tool, never replayed blindly;
8. an outside-allowlist, stale-preimage, unknown-recipe, or model-supplied environment/executable request is refused with zero unauthorized source effect;
9. the configured profile's actual admission audit distinguishes observed Workbench admission/refusal from an unobserved call; optional telemetry absence is not platform proof;
10. exact source/app/channel/host/project/store generation and rollback/disarm are recorded.

Run controls on other model/mode routes when useful, but do not infer C1 Workbench admission or effect from them. Each route's capability posture changes only from direct evidence on that route.

## Remaining production gates

This branch has source and local/adjacent test evidence only. Before any `PROVEN_LIVE` claim it still needs:

- current-base hosted CI/security and independent exact-head review;
- protected source release under ordinary repository protection;
- reviewed installation/supervision/rollback on the selected host;
- the exact dedicated Secure MCP Tunnel / ChatGPT app association, using its selected `main` channel and no additional application OAuth;
- actual selected-project/attended-Web channel binding;
- the C1 Personal Web-seat canary above;
- post-canary disarm/rollback proof and a final Sol acceptance decision.

A source merge, successful service startup, or a passing control route is not evidence that C1 Personal admits the Workbench modifying call.
