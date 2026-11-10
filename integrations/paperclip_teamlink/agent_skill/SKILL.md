---
name: paperclip-teamlink
description: Communicate with an exact T3 COO session from a Paperclip issue, consume returned replies and COO-initiated questions, recover project continuity across runs, and inspect T3 sessions and running processes. Use for Teamlink attention, T3 coordination, COO questions, project handoffs, or native environment visibility.
---

# Paperclip Teamlink

Use the installed `mastermind.teamlink` plugin through Paperclip's native agent
identity. Paperclip owns issues, agents, checkout and attention runs; T3 owns the
COO session, queues, runs and subagents. Keep the original task and DONE_WHEN.

## Discover and authenticate

Discover exact names and schemas using the native plugin tool list. If plugin
tools are not directly exposed by the adapter, use the installed `paperclipai`
CLI's `plugin tools` and `plugin tool:execute --payload-json` commands, or the
native HTTP API. Do not infer the namespaced tool name.

The HTTP tool request is `POST /api/plugins/tools/execute`:

```json
{
  "tool": "EXACT_DISCOVERED_NAME",
  "parameters": {"issueId": "CURRENT_ISSUE_ID"},
  "runContext": {
    "agentId": "YOUR_ACTUAL_AGENT_ID",
    "runId": "YOUR_ACTUAL_CURRENT_RUN_ID",
    "companyId": "YOUR_ACTUAL_COMPANY_ID",
    "projectId": "ISSUES_NATIVE_PAPERCLIP_PROJECT_ID"
  }
}
```

Use only native credentials and identity supplied to your own current process.
Use `PAPERCLIP_API_KEY` and `PAPERCLIP_RUN_ID` without printing or retaining them.
Require both values before invoking a tool: the CLI can otherwise fall back to
stored board credentials. Read your authenticated `/api/agents/me` identity and
the issue, and verify the current run identity before any Teamlink effect.
For HTTP, send `Authorization: Bearer $PAPERCLIP_API_KEY` and
`X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID`; for the CLI, request `--json` output.
Use the issue's Paperclip project ID in runContext; use the T3 project ID only
in Teamlink parameters. The issue must belong to a native Paperclip project.
Never fabricate a run,
borrow another agent's credentials, or use board actions to claim agent work.
The native HTTP response wraps the tool result as
`{pluginId, toolName, result: {content, data}}`. Check both a top-level `error`
and `result.error`, then use `result.data` and verify its operation, binding,
recipient and phase. An HTTP 200 or a succeeded tool-invocation record does not
prove that the requested Teamlink effect succeeded.

## Link and send

1. Read the issue, verify current assignment to you, and acquire its native
   checkout for your actual run before any Teamlink effect.
2. Call `teamlink_context` to recover an existing binding and unsettled effects.
   Call `teamlink_inventory` to inspect configured T3 environments/projects,
   exact root/subagent metadata and timestamped process observations.
3. Bind only an explicitly identified existing T3 root using `teamlink_bind`.
   Use the exact native project/thread IDs, never a title or latest-thread guess.
   Use `expectedRevision=0` for a new binding; re-read revision for changes.
   Binding does not create or interrupt a COO session.
4. Save a bounded context packet with original objective, DONE_WHEN, source refs,
   remaining work, decisions, uncertain effects and expiry. It is advisory;
   the native issue, documents and canonical source remain authoritative.
5. Use `teamlink_send` with one stable unique `operationId`, the bounded request,
   and `replyTo` when continuing an already returned exchange. Keep that ID and
   returned receipt. The bridge queues the message and returns the exact original
   native run's result to this issue. The wire includes the COO's reverse protocol
   and exact binding ID.
6. Finish the finite bot turn when waiting for native work. Do not create a poller,
   detached watcher, replacement session or retry queue. Paperclip's existing
   plugin listener observes native changes and requests attention; the existing
   scheduler provides recovery. Neither requires you to keep a model turn alive.

## Consume a reply or COO-initiated message

On Teamlink attention, re-read assignment and acquire native checkout for this
fresh run. Read `teamlink_context`, then `teamlink_status` for the exact operation
in the attention prompt. Read the returned native comment and result before
calling `teamlink_ack`. Acknowledgment records your actual consuming run; it does
not accept code, close the issue or authorize additional work.

Context includes native document summaries. Recover the current document body
through `GET /api/issues/<issueId>/documents/<key>` and retain its returned
revision when it contains acceptance, decisions or continuity needed for the
reply. Do not treat a summary or an expired advisory packet as that source.

For a COO question or blocker, answer on the same binding with a new stable
operation ID and `replyTo` naming the incoming operation. Preserve the original
acceptance and unresolved effects. Use `wakeOnReply=false` for an informational
final confirmation that needs no further bot turn. Do not close an issue while
an acceptance-critical exchange is unsettled.

## Observe and recover

Use `teamlink_inspect` for the bound root's bounded activity, messages and native
pending-input references. Inventory exposes child metadata without consuming
child transcripts. Process data covers the T3 listener and OS descendants; it is
not proof of exact process-to-thread ownership. Respect timestamps, pagination,
truncation, stale context and explicit unavailable states.

If a return is delayed, inspect the exact operation and native plugin health.
Check subscription coverage and observation errors before interpreting silence.
A connected listener or a requested attention run does not prove consumption.
Keep the original operation ID while the native recovery path catches up.

Recover using `teamlink_status` with the original operation ID; `reconcile=true`
observes existing effects. Never resend an uncertain operation under a new ID.
Changed operation semantics, changed destinations, reassignment, permission
refusals and uncertain effects require their exact native disposition. Do not
change accounts, providers, adapter flags, permissions or carriers to force a
pass. Teamlink does not approve native input requests. Escalate the original
request through its existing owner when human input is actually required.

