# Paperclip company integration

Request-scoped composition of an **existing** Paperclip company into Mastermind OS. Hermes remains the agent runtime. This package adds no database, bot installer, scheduler, service process, auth registry or background observer.

The canonical [architecture, installed configuration, ownership and cutover guide](../../docs/architecture/PAPERCLIP_CONTINUOUS_TEAM.md) defines the replace/retain boundaries and outstanding runtime bindings. The [engineering plan](../../docs/plans/2026-11-09-paperclip-continuous-team-integration.md) retains the Chairman assignment and source custody.

## Mounted interfaces

- Existing Workspace GET `/workspace/company/current`: bounded company, people, project, goal, task, routine, artifact, activity, original receipt and runtime-integration views.
- Existing Workspace POST `/workspace/company/command`: separately enabled `create_backlog` only. No agent creation, assignment, wake, runtime switch, schedule activation or arbitrary source action.
- Existing native IPC: `read_company_workspace`, `create_company_backlog`.
- Existing OS host: `MissionHost.company`. Primary navigation: Team.

The optional sealed `workspace.paperclip` block is composed by `ops/executive_os/executive_mcp_entry.py`. The complete `workspace-binding.example.json` is **inert**: no principal grant, no profile/project binding and no authoring. The example company ID is a dated existing-company observation and the port is an example; reconcile both with the installed owner before adoption. Never provision a second company just to make the example work.

The API is qualified against upstream Paperclip commit `d69631b01b9c658f80bf8bed389863dce82643e1`. The official `hermes_gateway` adapter's HTTP/SSE protocol is not the private `hermes-gateway-v1` native protocol. The runtime inspector prepares the mapping but does not mutate an agent. General agent adapter PATCH lacks a source-revision CAS at this donor pin; preparation cannot claim exclusive writer ownership.

## Recovery and limits

Backlog commands use the upstream native idempotency key and the existing OS durable pending-pointer store. Only original IDs and principal scope are retained. A marker or missing readback is not a source receipt; unresolved writes stay held without an automatic resend. The inspected source does not yet establish a generally available authoritative read endpoint for all native create-idempotency receipts. The architecture guide records this actual integration gap.

No source mutation is performed by viewing a page. Credentials stay host-owned; source projection excludes adapter configuration, secrets, private logs and arbitrary runtime detail. Operator bindings and the actual source ACL both apply. Tests, canaries and live-result proof were deferred by the current assignment; installed activation and runtime acceptance are not claimed.
