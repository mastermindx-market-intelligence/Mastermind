# Mastermind Executive MCP — ChatGPT Business Production Proof

**Date:** 2026-09-16
**CEO owner:** Sol
**Chairman:** Chris
**Operation:** `executive-os-plugin-finalization-20260914-sol-001`
**Final narrow capability state:** `PROVEN_LIVE`

## Capability proved

A real ChatGPT Business conversation used the installed private **Mastermind Executive**
app to authenticate, discover exactly five tools, call all four readers against the
installed Executive runtime, and exercise the queue-only CEO-intent admission contract.
The accepted canary remained `QUEUED`, reported `dispatched=false`, and produced no
Attempt or Worker. Same-payload replay reconciled to the same Job; changed payload under
the same operation identity was refused as `operation_conflict`.

This receipt qualifies the authenticated app/tool path only. It does not claim that every
upstream Executive information source is healthy or that queued work executed.

## Procedure and release identity

- Protected procedure pin: `bf843961c0e1b5bd45fa481f0138c71f2a87d4e2`.
- Skillpack schema/version: `mastermind.sol_skillpack.v1` / `1.0.1`.
- Installed Executive control release: `4c148709f52ff036d71dd212abd2688212d91ed0`.
- Installed Executive MCP component: `46bea20832a8f0d01559eb8bfb0e9b1406774956`.
- Server contract: `mastermind-executive` version `1.0.0`.

## Exact production app and transport

- ChatGPT Business app ID: `plugin_asdk_app_6aa89de1c45c81918b192d0a18dcfc15`.
- App display/version: `Mastermind Executive` / `1.0.0`.
- Production tunnel: `tunnel_6a966926e4b48191b93e5b5df2457afd`.
- Authorization server: `https://dev-eo0jf8us5mup7wd5.us.auth0.com/`.
- Proof conversation: `https://chatgpt.com/c/6aaaf383-c830-83ea-9a61-00715bce563b`.
- MCP loopback listener: `127.0.0.1:8443`.

Two older fixture profiles were explicitly excluded from production evidence:

- `mastermind-executive-chatgpt1` / `tunnel_6a9d2e22e01c819189d7574645e52873`;
- `mastermind-executive-chatgpt3` / `tunnel_6a9d32826bf08191b37a0e2a45942dcd`.

Those profiles invoke the historical fixture script in `--mode fixture`. They did not
supply any acceptance evidence in this operation.

## OAuth result

The production app initially returned an expired-connection error. The native ChatGPT
`Reconnect` path completed successfully. The same Business conversation then invoked
live Executive tools through the production tunnel, proving usable bearer forwarding
and refresh-capable authorization. No credential, token, password, or raw subject value
is retained in this receipt.

## Exact tool discovery

The registered Business app advertised exactly these five tools and no sixth tool:

1. `executive_state`
2. `executive_inbox`
3. `executive_job`
4. `ceo_intent_status`
5. `submit_ceo_intent`

## Four-reader production proof

| Tool | Production result |
|---|---|
| `executive_state` | Live installed-runtime envelope; baseline was 2 Jobs, both `QUEUED`, 0 Attempts, 0 Workers. |
| `executive_inbox` | Live installed-runtime inbox envelope with canonical grounding and runtime counts. |
| `executive_job` | Read `JOB-001`, `JOB-002`, and post-canary `JOB-003` through typed registries, not raw SQL. |
| `ceo_intent_status` | Resolved durable intent receipts for accepted Jobs through `control_plane.ceo_intent.resolve_intent`. |

The reader envelopes identified their runtime as
`readonly:installed-executive-runtime`. `executive_job` identified its source as
`control_plane.executive_runtime registries (no raw SQL)`.

## Queue-only canary request

- Operation key: `executive-os-plugin-live-canary-20260916-sol-003`.
- Expected/request reference: `req-5e7a696ee0eb98c18d51169e57aa5a6a`.
- Expected/accepted intent ID: `auto-61a72bb12b6a65d5ca317831fedc40dc`.
- Accepted Job: `JOB-003`.
- Execution profile: `research_only` (`READ`, `RESEARCH`).
- Attempt limit: `1`.
- Allowed write paths: none.
- Validation commands: none.
- Payload source artifact SHA-256: `9b3abc11e7ffdbe40da5e224e0ea3ca30f0777cd1642115802201fc75c7d3228`.

The native ChatGPT confirmation dialog was presented and deliberately approved for the
one queue-only operation. The accepted receipt was:

```json
{
  "accepted": true,
  "created_at_ms": 1789589352082,
  "dispatched": false,
  "duplicate": false,
  "fingerprint": "bd9ccfd53abda2320ce0e36de0d4cb34c9a6bed6e3add6c74b987d2e66f72fb6",
  "intent_id": "auto-61a72bb12b6a65d5ca317831fedc40dc",
  "job_id": "JOB-003",
  "request_ref": "req-5e7a696ee0eb98c18d51169e57aa5a6a",
  "status": "QUEUED"
}
```

Authority policy digest:
`8d5389d98e4d3e46863c2ef859f59421d9e2fa90b9cf18a8db3b2e16c9af820e`.
The receipt grounded Mastermind at the installed control release and Macro at
`84b2f9e50f9a41eee4ffd620bb8d991d90f5b8c0`.

## Duplicate and conflict canaries

The same operation key and byte-equivalent semantic payload was submitted once more
through the same app/conversation carrier. It returned:

- `duplicate=true`;
- the same `JOB-003`;
- the same intent ID, request reference, fingerprint, creation time, and grounding;
- `dispatched=false` and `status=QUEUED`.

The same operation key was then submitted with a deliberately changed objective. It
returned no acceptance receipt and exactly:

```json
{
  "error": {
    "code": "operation_conflict",
    "message": "intent_id was already accepted with a different request"
  },
  "ok": false,
  "request_ref": "req-5e7a696ee0eb98c18d51169e57aa5a6a",
  "status": "operation_conflict"
}
```

No retry or carrier failover followed the conflict.

## Post-effect reconciliation

After acceptance, duplicate reconciliation, and changed-payload conflict:
- total Jobs: `3`;
- Jobs by status: `QUEUED=3`, every other status `0`;
- total Attempts: `0`;
- total Workers: `0`;
- `JOB-003.current_attempt_id=null`;
- `JOB-003.assigned_worker_id=null`;
- `JOB-003.attempt_count=0`;
- `JOB-003.status=QUEUED`;
- durable intent status: accepted, `dispatched=false`, `JOB-003`, `QUEUED`.

The two Jobs present before this operation (`JOB-001`, `JOB-002`) were already queued
harmless canaries. They were read but not modified. The delta from this operation was
exactly one additional queued Job.

## Provider-surface interaction proof

- Message-body entry: one semantic CDP `Input.insertText` fill per message.
- Body-character synthetic keystrokes: `0`.
- Tab/Shift-Tab discovery: `0`.
- Confirmation: direct semantic selection of the native `Allow` control.
- Clipboard use: none; therefore no cross-session clipboard collision.

## Residual degraded inputs

The readers truthfully exposed pre-existing degradation unrelated to app transport:

- Agent OS brief unavailable from the installed boot-packet path;
- strategic-state YAML unreadable because PyYAML is absent in that installed reader path;
- therefore CEO attention projection is incomplete.

Those facts remain `PARTIAL` for broader Executive context quality. They do not negate the
successful OAuth, five-tool, four-read, admission, idempotency, and conflict production path.

## Completion-ruler adjudication

| Required proof | Result |
|---|---|
| OAuth authorization succeeds | PASS — native reconnect followed by authenticated live tool calls. |
| Exactly five tools discovered | PASS — four readers plus `submit_ceo_intent`, no sixth MCP tool. |
| Four reads succeed against installed canonical state | PASS. |
| One confirmed harmless submit is accepted | PASS — `JOB-003`. |
| Job remains `QUEUED` | PASS. |
| `dispatched == false` | PASS. |
| Attempts remain `0` | PASS. |
| Workers remain `0` | PASS. |
| Same-payload retry reconciles as duplicate | PASS — same durable identity and Job. |
| Changed payload under same operation conflicts/refuses | PASS — `operation_conflict`. |
| No unresolved modifying uncertainty | PASS — post-effect state and intent were reread canonically. |
| Sanitized durable production receipt exists | PASS — this artifact. |

## Capability ruling

The authenticated **Mastermind Executive ChatGPT Business app path** is
`PROVEN_LIVE` for the frozen five-tool contract, including its queue-only modifying
boundary and idempotency/conflict semantics.

This ruling does **not** mean:

- the queued Job executed, dispatched, or obtained a Worker;
- the broader Executive context/attention inputs are healthy;
- fixture tunnels are production-qualified;
- source tests alone are production proof;
- another app, workspace, account, or tunnel inherits this proof;
- the five-tool schema may be widened without a separate reviewed carrier.

## Exact continuation boundary

The plugin-finalization operation is terminal. Do not rerun its modifying canary or
create another Job to strengthen an already-complete proof.

The highest-leverage independent continuation is a separate repair operation for the
installed reader's missing Agent OS brief and PyYAML-backed strategic-state input. That
work must preserve the existing Executive lifecycle, boot-packet, Agent OS, and
strategic-state owners; it is not a reason to reopen or rebuild the plugin path.

## Projection collision held

The natural runbook projection path,
`docs/runbooks/mastermind-executive-app.md`, is concurrently modified by open PRs
#653 and #697. This closeout deliberately does not edit that path, overwrite either
carrier, or manufacture a third reconciliation branch. The production receipt remains
canonical GitHub evidence; the runbook projection should be updated by the legitimate
surviving runbook carrier after those PRs reconcile.
