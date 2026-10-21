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
Attempt or Worker. Same normalized-payload replay reconciled to the same Job; changed
payload under the same operation identity was refused as `operation_conflict`.

This receipt qualifies the authenticated app/tool path only. It does not claim that every
upstream Executive information source is healthy or that queued work executed.

The document-level operation identifies the non-effectful finalization/closeout carrier.
The later `executive-os-plugin-live-canary-20260916-sol-003` operation key identifies the
single modifying production canary performed within that authorized finalization scope.
They are intentionally distinct identities and must not be substituted for one another.

## Procedure and release identity

- Protected procedure pin: `bf843961c0e1b5bd45fa481f0138c71f2a87d4e2`.
- Skillpack schema/version: `mastermind.sol_skillpack.v1` / `1.0.1`.
- Installed Executive control release: `4c148709f52ff036d71dd212abd2688212d91ed0`.
- Installed Executive MCP component: `46bea20832a8f0d01559eb8bfb0e9b1406774956`.
- Server contract: `mastermind-executive` version `1.0.0`.
- Protected `master` at final compatibility review: `5ee11ab1e993616f3568cfca4069cb21fa61fd8f`.
  Protected movement from the procedure pin changed no `docs/sol_skills/**` file. It
  merged #697's sealed boot-context source repair, while the observed production host
  remained on the installed releases named above.

## Exact production app and transport

- ChatGPT Business app ID: `plugin_asdk_app_6aa89de1c45c81918b192d0a18dcfc15`.
- App display/version: `Mastermind Executive` / `1.0.0`.
- Production tunnel: `tunnel_6a966926e4b48191b93e5b5df2457afd`.
- Authorization server: `https://dev-eo0jf8us5mup7wd5.us.auth0.com/`.
- MCP loopback listener: `127.0.0.1:8443`.

The Auth0 hostname is retained verbatim because it is the issuer configured by the
installed Executive MCP policy and the issuer used by the successful ChatGPT
authorization flow. This receipt does not infer deployment tier from the provider's
`dev-` tenant-name prefix; “production” refers to the exact installed app, tunnel,
service, runtime, and canonical-effect path identified here.

Two older fixture profiles were explicitly excluded from production evidence:

- `mastermind-executive-chatgpt1` / `tunnel_6a9d2e22e01c819189d7574645e52873`;
- `mastermind-executive-chatgpt3` / `tunnel_6a9d32826bf08191b37a0e2a45942dcd`.

Those profiles invoke the historical fixture script in `--mode fixture`. They did not
supply any acceptance evidence in this operation. No
`mastermind-executive-chatgpt2` Executive fixture profile existed in the inspected
`tunnel-client` configuration; similarly numbered ChatGPT 2 labels belong to Studio
Direct transport and are unrelated to this Executive app/tunnel proof.

## OAuth result

The production app initially returned an expired-connection error. `Reconnect` was
invoked from the exact app page identified by
`plugin_asdk_app_6aa89de1c45c81918b192d0a18dcfc15`; the same app remained selected in
the Business conversation that then invoked live Executive tools through the production
tunnel. Those authenticated tool calls establish a usable authorization and bearer path
for the named app identity, rather than a different client registration. Token expiry and
subsequent reconnect remain normal auth-lifecycle states, not evidence that authorization
can never expire. No credential, token, password, or raw subject value is retained in
this receipt.

## Exact tool discovery

The registered Business app advertised exactly these five tools and no sixth tool:

1. `executive_state`
2. `executive_inbox`
3. `executive_job`
4. `ceo_intent_status`
5. `submit_ceo_intent`

## Four-reader production proof

Reader proof spans pre-canary and post-canary evidence. The table is an operation-wide
summary and names the phase actually used for each tool; the modifying admission receipt
appears in the immediately following section. A read of the new `JOB-003` is post-effect
reconciliation and is not represented as evidence that the Job existed before admission.

| Tool | Phase | Production result |
|---|---|---|
| `executive_state` | Pre-canary baseline and post-canary reconciliation | Before submit: 2 Jobs, both `QUEUED`, 0 Attempts, 0 Workers. After canaries: 3 Jobs, all `QUEUED`, 0 Attempts, 0 Workers. |
| `executive_inbox` | Authenticated read-only reconciliation | `attention_count=0`; 3 typed degraded facts; runtime counts were 3 `QUEUED` Jobs, 0 Attempts, and 0 Workers; runtime grounding was `readonly:installed-executive-runtime`. |
| `executive_job` | Existing-job proof, then post-effect readback | A fresh compact read of pre-existing `JOB-001` returned `QUEUED`, no current Attempt, no assigned Worker, and `attempt_count=0`. `JOB-003` was read only after its accepted submit and is recorded under post-effect reconciliation. |
| `ceo_intent_status` | Existing-intent proof, then post-effect readback | Existing intent `auto-7e10a5d196b414c8194276797a202a47` resolved to accepted `JOB-001`, `QUEUED`, `dispatched=false`. The canary intent was resolved separately after admission. |

Selected exact fields from the compact `executive_inbox` read were:

```json
{
  "attention_count": 0,
  "degraded": [
    "boot_packet: agentos brief exited 1: <no stderr>",
    "boot_packet: strategic state unreadable: /Library/Application Support/MastermindExecutive/releases/4c148709f52ff036d71dd212abd2688212d91ed0/config/strategic_state.yml: PyYAML is required to read the strategic state",
    "boot packet carries no Agent OS brief; CEO attention not projected"
  ],
  "runtime_counts": {
    "attempts": {
      "by_status": {
        "CANCELLED": 0,
        "CANCEL_REQUESTED": 0,
        "CHECKPOINTED": 0,
        "CLAIMED": 0,
        "COMPLETED": 0,
        "FAILED": 0,
        "LOST": 0,
        "RATE_LIMITED": 0,
        "RUNNING": 0
      },
      "total": 0
    },
    "jobs": {
      "by_status": {
        "CANCELLED": 0,
        "CANCEL_REQUESTED": 0,
        "CHECKPOINTED": 0,
        "COMPLETED": 0,
        "FAILED": 0,
        "LOST": 0,
        "QUEUED": 3,
        "RATE_LIMITED": 0,
        "RUNNING": 0
      },
      "total": 3
    },
    "workers": {
      "by_status": {
        "AVAILABLE": 0,
        "BUSY": 0,
        "DRAINING": 0,
        "ERROR": 0,
        "OFFLINE": 0,
        "RATE_LIMITED": 0
      },
      "total": 0
    }
  },
  "grounding_runtime": "readonly:installed-executive-runtime",
  "grounding_source": null,
  "generated_at": "2026-09-16T21:07:43Z",
  "ok": true,
  "schema": "mastermind.executive_mcp_result.v1",
  "tool": "executive_inbox"
}
```

The compact inbox projection returned `grounding_source=null`; the artifact preserves that
null rather than inventing provenance. The runtime identity and tool name remained explicit,
and the same installed-runtime counts were independently corroborated by `executive_state`.

The existing-intent read returned:

```json
{
  "accepted": true,
  "dispatched": false,
  "duplicate": false,
  "intent_id": "auto-7e10a5d196b414c8194276797a202a47",
  "job_id": "JOB-001",
  "status": "QUEUED",
  "fingerprint": "f05ab8f37fdc2d89494ad34bd98c0dc129a3efef73393a7b0d9658159e7fee78",
  "grounding_runtime": "readonly:installed-executive-runtime",
  "grounding_source": "control_plane.ceo_intent.resolve_intent",
  "generated_at": "2026-09-16T21:08:12Z",
  "ok": true,
  "schema": "mastermind.executive_mcp_result.v1",
  "tool": "ceo_intent_status"
}
```

`executive_job` identified its source as
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

The same submitted `operation_key` and the same normalized intent payload were sent once
more through the same app/conversation carrier. The reviewed app contract derives the
stable `request_ref` from that `operation_key`; the
`control_plane.ceo_intent.canonical_bytes` / `intent_fingerprint` contract serializes the
whole validated envelope as canonical JSON and hashes it with SHA-256. The replay then
returned the same request reference and fingerprint shown below, so the evidence is
normalized-envelope identity, not a claim about raw transport-byte formatting. The
duplicate result was:

```json
{
  "accepted": true,
  "created_at_ms": 1789589352082,
  "dispatched": false,
  "duplicate": true,
  "fingerprint": "bd9ccfd53abda2320ce0e36de0d4cb34c9a6bed6e3add6c74b987d2e66f72fb6",
  "intent_id": "auto-61a72bb12b6a65d5ca317831fedc40dc",
  "job_id": "JOB-003",
  "request_ref": "req-5e7a696ee0eb98c18d51169e57aa5a6a",
  "status": "QUEUED"
}
```

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

Aggregate pre-canary state showed two queued Jobs. `JOB-001` was individually read and
identified as a harmless admission-path canary; `JOB-002` was observed only through the
aggregate count and is not individually characterized by this receipt. No submit in this
operation targeted either pre-existing Job, and the canonical state delta was exactly one
additional queued Job: `JOB-003`.

## Provider-surface interaction proof

- Message-body entry: one semantic CDP `Input.insertText` fill per message.
- Body-character synthetic keystrokes: `0`.
- Tab/Shift-Tab discovery: `0`.
- Confirmation: direct semantic selection of the native `Allow` control.
- Clipboard use: none; therefore no cross-session clipboard collision.

## Residual degraded inputs

The authenticated reader envelopes also exposed these pre-existing degraded inputs:

- Agent OS brief unavailable from the installed boot-packet path;
- strategic-state YAML unreadable because PyYAML is absent in that installed reader path;
- therefore CEO attention projection is incomplete.

This receipt does not infer their root cause from the app proof. It scopes them separately:
the broader Executive context quality remains `PARTIAL`, while the OAuth, five-tool,
four-read, admission, idempotency, and conflict path is production-proven.

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
| Same normalized-payload replay reconciles as duplicate | PASS — same canonical fingerprint, durable identity, and Job. |
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

Protected master now contains #697's source-level sealed boot-context repair, but the
observed production host remains on the older installed release recorded above. The
highest-leverage independent continuation is to reconcile open PR #653 against merged
#697, then install and production-prove the legitimate surviving reader repair. That
work must preserve the existing Executive lifecycle, boot-packet, Agent OS, and
strategic-state owners; it is not a reason to reopen or rebuild the plugin path.

## Projection collision held

The natural runbook projection path,
`docs/runbooks/mastermind-executive-app.md`, was changed by merged PR #697 and remains
in open PR #653's overlapping scope. This closeout deliberately does not edit that path,
overwrite either history, or manufacture a third reconciliation branch. The production
receipt remains canonical GitHub evidence; the surviving reader/runbook carrier owns any
later projection after #653 is reconciled against protected master.
