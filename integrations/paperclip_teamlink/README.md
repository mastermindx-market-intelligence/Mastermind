# Paperclip ↔ T3 Teamlink

This native Paperclip plugin connects existing company bots to exact T3 root
sessions. Paperclip owns issues, agent identities, attention runs, plugin state,
scheduled jobs and activity provenance. T3 owns sessions, subagents, native
queues, runs and transcripts. The bridge stores transport references and bounded
advisory context; it does not create another agent runtime, task queue, daemon,
authentication service or project acceptance owner.

## Native bot instructions

The bundled `agent_skill/SKILL.md` is installed through Paperclip's native company
skill registry and selected for the existing bot team. The current `hermes_local`
adapter reconciles Paperclip-managed skills on every run, including resumed runs.
It does not automatically inject plugin tools, so the skill documents native
tool discovery and the authenticated CLI/API route without introducing an agent
identity, credential store or alternate runtime.

## Tools and ordinary workflow

Tools are registered under the installed plugin's native namespace. Use native
Paperclip tool discovery to obtain their full names; do not fabricate a run ID
or call them with another agent's credentials.

| Tool | Purpose |
| --- | --- |
| `teamlink_inventory` | Configured T3 environment and projects, native root/subagent census, timestamped listener process tree. |
| `teamlink_inspect` | Bounded activity/messages and pending-input state for the issue's bound root. |
| `teamlink_bind` | CAS-bind a checked-out issue to an exact existing root; `expectedRevision=0` creates the first link. |
| `teamlink_send` | One stable operation ID and one queue-mode send, with an original-run receipt. |
| `teamlink_status` | Original delivery/result, uncertainties and returned comment; optional observation-only reconciliation. |
| `teamlink_ack` | Actual original recipient agent explicitly records consumption of this exact reply. |
| `teamlink_context` | Native issue/documents, exact link, unsettled effects and optional expiring context packet. |

The assigned bot first checks out its issue through Paperclip's normal workflow,
discovers the T3 project/root, and binds it. A binding does not launch, restart,
interrupt, change the model or otherwise modify that T3 session. `teamlink_send`
queues the message through the existing `T3NativeClient`. Preserve its operation
ID when re-reading or recovering it. Identical repeated requests return the same
receipt. Reusing that ID with changed semantics is refused.

The complete original result returns as a comment on the same issue. When an
actionable reply is available, the bridge makes one CAS-fenced native attention
invocation addressed to the original Paperclip agent. That agent must re-read
assignment, acquire its native issue checkout, read the exact result and call
`teamlink_ack`. It may send a follow-up with `replyTo` naming the prior operation.
A later run of the same agent can recover the entire conversation from the issue
and receipt references. Delivery, execution, reply publication, requested wake,
consumption and project acceptance remain distinct.

## COO-initiated messages

A COO can initiate a question, blocker or update without a preceding Paperclip
request. Start the **final assistant message** with exactly one block:

```text
<teamlink-to-paperclip>{"bindingId":"EXACT_BINDING_ID","kind":"question","message":"Which canonical source should I use?"}</teamlink-to-paperclip>
```

The binding ID is supplied in every Paperclip→T3 wire message and is returned by
`teamlink_bind` / `teamlink_context`. It names the exact destination. It is a
correlation reference, not an authorization token. The bridge derives the sender
from the verified native environment, project, root, run and item; claimed actor
identities inside the message are never used.

Allowed kinds are `question`, `blocker` and `update`; `replyTo` is optional.
Messages are bounded to 16,000 UTF-8 bytes. Updates create an informational issue
comment without waking a model. Questions and blockers request one native
attention run. Arbitrary prose, user messages and tool output are not routed.
An explicit block inside an already tracked request's original result is not
echoed as a second incoming exchange.

The existing Paperclip plugin scheduler observes bound native timelines each
minute. It waits for native completion before advancing over mutable assistant
content. Receipt insertion precedes cursor advancement, so crashes re-observe
and deduplicate the same native item. A binding made during an active COO run
replays bounded native history through its new binding ID to avoid skipping an
already-streaming item. Initial catch-up and unavailable observations may delay
delivery; neither is reported as an empty or completed inbox.

## Continuity and visibility

`teamlink_context` returns the authoritative issue and its native document
references, the binding, recent exchanges and unresolved effects. Its optional
context packet carries the objective, original `doneWhen`, source references,
remaining work, decisions, uncertain effects and an expiry. Updates require the
current binding revision. Expired packets are marked stale. They do not grant
permissions, replace a source plan, declare acceptance or own task lifecycle.

Inventory and inspection use native T3 tools. Census includes subagents without
reading child transcripts, since reading a child final result can acknowledge
its delivery. Process observation is restricted to the T3 listener's OS process
tree. It reports PID, PPID, start/elapsed times, CPU/memory percentages and
executable basename; it does not expose environment variables or full command
lines. The process tree is not proof of exact process-to-thread ownership.
Results include observation timestamps and explicit truncation/unavailability.

## Recovery boundaries

- Native PostgreSQL uniqueness and revision CAS fence concurrent workers. Each
  external write is preceded by a durable intent/fence.
- An uncertain send is never replayed. Observation can rejoin one unambiguous
  native message after the recorded pre-send boundary, matching the unique wire
  marker and full rendered-message digest, then follow that exact run.
- A lost comment response is recoverable from a server-attributed native
  `issue.comment.created` event and the exact content. A visible marker and a
  null/null author tuple alone are insufficient. If both the original receipt
  and native provenance are unavailable, the comment remains uncertain; the
  bridge does not post a duplicate.
- Native `agents.invoke` addresses the exact original agent and preserves
  company/agent heartbeat admission. It exposes no idempotency key and supplies
  no issue/project context. The bridge attempts it once and never replays an
  uncertain invocation. It is an attention turn, not issue execution approval;
  issue assignment and checkout are revalidated before issue effects. Do not
  describe it as enforcing issue-specific budgets or blocker gates.
- Reassignment/closure observed before attention publication holds the result
  without waking a replacement. A change during publication still cannot retarget
  the native call to another agent.
- Failed/interrupted native runs are returned with their actual disposition.
  Pending native input is surfaced with original request references. Teamlink
  never approves permissions or answers native human-input requests automatically.
- Fair last-attempt rotation prevents held effects or unavailable bindings from
  starving later exchanges. Native cron execution is bounded; there are no
  detached watchers, timers, retry services or retained agent tokens.

## Installation and qualification

The production source is the merged Mastermind commit, not a live development
worktree. Install in a fresh immutable release directory containing this package
and the unchanged `integrations/session_bridge/t3_native_client.py` at the same
source commit. Install the exact declared SDK dependency with the package lock.

Build the native helper using [native_cli/PROVENANCE.md](native_cli/PROVENANCE.md).
Keep its bundle and all runtime externals in the release directory. The normal
T3 app and running server are not replaced or restarted.

Use native `paperclipai plugin install <absolute-package-path> --local --json`
and native company configuration. Required configuration: exact company and T3
environment IDs; allowed native project IDs; absolute `nativeCliPath`,
`nodePath`, `pythonPath`, `portPath`, `t3Home`; native listener `t3Port`; and
`enabled: true`. No tokens or provider credentials belong in configuration.
The plugin starts disabled until configuration is present. Use native plugin
health, jobs and tool discovery to verify startup, migration and company scope.

Local tests:

```sh
node --test integrations/paperclip_teamlink/test/*.test.mjs
python -m unittest discover -s tests -p test_paperclip_teamlink.py -v
```

Acceptance additionally requires real consumer proof: a Paperclip bot sends to
the exact T3 root, receives and consumes the original result, continues with a
referenced follow-up, and responds to a new COO-initiated question on the same
binding. Verify native run/comment/consumption receipts and inventory/process
observations. Passing unit tests or installing the plugin alone is insufficient.

To stop new routing, disable the plugin through Paperclip's native controls.
Retain its database receipts and original source/runtime references. Disabling
the bridge does not cancel native work already admitted by T3 or Paperclip.
