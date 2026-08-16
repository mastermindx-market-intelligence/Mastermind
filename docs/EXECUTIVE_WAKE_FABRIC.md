# Executive Wake Fabric — PR-1 core contracts

**Status:** contracts only. No Control Panel UI, no GUI automation, no Grok
computer-control, no production MCP write arm, no public HTTP endpoint.

The Wake Fabric is the missing notification layer between durable Executive OS
lifecycle transitions and the human-or-AI seat that must continue the work.  It
does **not** become a second Job / Attempt / Worker / Event authority.

```text
Executive OS lifecycle authority (SQLite)
        ↓
    Wake Fabric contracts (this PR)
        ↓
  Dispatcher protocol + typed receipt
        ↓
provider-specific adapter (none armed in PR-1)
```

A later Control Panel is a view/controller over these contracts.  It must not
invoke Codex, ChatGPT, or Grok directly.

## 1. Where durable state lives

| Concept | Home | Why |
|---|---|---|
| Job / Attempt / Worker / Event / lease | `control_plane/executive_runtime.py` SQLite | Sole lifecycle authority. Unchanged by this PR. |
| Wake envelope identity | Content-addressed `WAKE-*` from the identity tuple | Reconstructable on replay. Shaped to fit `events.command_id`. |
| Wake delivery idempotency (PR-2) | Existing `events.command_id TEXT NOT NULL UNIQUE` | Do not add a wake table, queue, or scheduler. Persist by using `WAKE-*` as `command_id`. |
| Logical session alias | `config/wake_session_targets.json` | Documentation-as-config identity mapping, same class as `config/executive_worker_routes.json`. Not a lifecycle registry. |
| Provider address (`external_handle`) | Null in PR-1. Later: copy from `attempts.provider_session_id` or worker metadata | Provider IDs are never Mastermind identity. |
| Inbox `next_actions` / worker prose | Existing Job payload, copied verbatim by the inbox | Inert data. The router must not execute or route from it. |
| MCP tool surface | Frozen five-tool table in `integrations/executive_mcp/schemas.py` | PR-1 stays below MCP. `acknowledge_ceo_wake` remains a reserved later schema bump. |

This PR creates **no** SQLite table, **no** queue, **no** scheduler, **no** lease,
and **no** second session database.

## 2. Canonical wake event

Module: `control_plane/wake_events.py`  
Schema: `mastermind.wake_event.v1`

```json
{
  "schema": "mastermind.wake_event.v1",
  "event_id": "WAKE-<32 hex>",
  "event_type": "REVIEW_REQUIRED",
  "created_at": "2026-08-16T16:00:00Z",
  "project_id": null,
  "job_id": "JOB-001",
  "attempt_id": "ATT-<32 hex>",
  "target_seat": "coo",
  "session_alias": "PROPHET-COO-A",
  "reason_code": "worker_completion_requires_review",
  "evidence_refs": ["JOB-001", "ATT-<32 hex>"]
}
```

**Identity ruling.** `event_id` is content-addressed, not a random UUID:

```text
WAKE- + sha256(canonical JSON of
  schema, event_type, job_id, attempt_id, project_id,
  target_seat, session_alias, reason_code
)[:32]
```

`created_at` is recorded on the envelope and **excluded** from the hash so a
replay of the same lifecycle fact reconstructs the same id.  Extra keys, command /
argv / authority / prompt fields, and non-`JOB-*`/`ATT-*` evidence refs fail
closed.

PR-2 should persist the envelope by inserting an Executive OS event whose
`command_id` is this `WAKE-*` id.  `RuntimeStore.find_event_by_command_id`
already exists for the replay half.

## 3. Stable session / target identity

Module: `control_plane/session_targets.py`

- `session_alias` — Mastermind logical identity (`PROPHET-COO-A`)
- `target_seat` — `ceo` or `coo`
- `adapter_type` — `codex-app-server` / `codex-cli` / `chatgpt-gui` / `grok-computer`
- `external_handle` — provider address, nullable, never canonical
- `workstream` — optional association used only to pick the default alias

Worker/model prose that names an alias is ignored.  Resolution is seat +
workstream against the checked-in JSON.

## 4. Deterministic router

Module: `control_plane/wake_router.py`  
No LLM.  Closed `transition` vocabulary only.

| Transition | Action | Seat | Event type |
|---|---|---|---|
| `healthy_running`, `queued` | `NO_WAKE` | — | — |
| `worker_completed` | wake | coo | `REVIEW_REQUIRED` |
| `revision_completed` | wake | coo | `REVISION_COMPLETED` |
| `architectural_contradiction` | wake | coo | `ARCHITECTURAL_CONTRADICTION` |
| `strategic_ambiguity` | wake | ceo | `STRATEGIC_AMBIGUITY` |
| `mandate_change` | wake | ceo | `MANDATE_CHANGE` |
| anything else | fail closed | — | — |

`next_actions`, `worker_prose`, `claimed_session_alias`, `claimed_target_seat`,
`claimed_command`, and `claimed_event_type` are stored only so they can be listed
as suppressed.  They never select a seat, alias, command, or event type.

## 5. Dispatcher contract

Module: `control_plane/wake_dispatcher.py`

```python
class WakeDispatcher(Protocol):
    async def wake(self, target, event) -> WakeReceipt: ...
```

Outcomes: `ACCEPTED`, `DELIVERED`, `ALREADY_DELIVERED`, `TARGET_UNAVAILABLE`,
`UNSUPPORTED`, `REFUSED`, `FAILED`.

PR-1 ships `UnsupportedWakeDispatcher` for every registered adapter.
`authenticate_receipt` refuses a success claim from an unimplemented descriptor.
`already_delivered_receipt` is trusted fabric code for PR-2 command-id replay; it
is not an adapter.

The existing bounded Codex CLI worker (`control_plane/codex_worker.py` +
`worker_adapter.py`) is unchanged.  Persistent Codex App Server threads are a
future adapter behind this same protocol.

## 6. Explicit non-goals (this PR)

- Control Panel UI
- Grok / computer-use automation
- ChatGPT GUI wake relay implementation
- Codex App Server client
- MCP `acknowledge_ceo_wake` or any schema-snapshot bump
- Public HTTP endpoint
- Runtime transition → wake emission (that is PR-2)
- Changing Executive supervisor, broker, service, or worker-adapter behavior

## 7. Recommended PR-2

Runtime transition → wake event integration:

1. After a trusted Executive OS terminal transition (worker completion, revision
   completion, named contradiction/ambiguity/mandate facts — **not** from
   `next_actions` prose), call `WakeRouter.route`.
2. If `NO_WAKE`, stop.
3. Persist the envelope as an Executive OS event with `command_id = event.event_id`.
   On `UNIQUE` conflict, return `already_delivered_receipt`.
4. Call `dispatch_wake`.  PR-2 may still keep adapters unimplemented; the
   receipt remains `UNSUPPORTED` until a separately reviewed transport lands.
5. Still no MCP write arm, no GUI automation, and no Control Panel execution
   authority.
