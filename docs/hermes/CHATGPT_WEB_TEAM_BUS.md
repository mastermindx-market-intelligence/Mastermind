# ChatGPT Web ↔ Hermes/DeepSeek team bus: incumbent-owner integration

**State at 2026-11-08:** SOURCE CLIENT BUILT, NOT PRODUCTION-PROVEN.
**Workstream:** `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`. This is a bounded addendum to
`research/EXECUTIVE_ECOSYSTEM_COMPLETION_PROGRAMME_PLAN_2026-10-17.md`, not a new
lifecycle, architectural owner, launch track or claim that H1-H8 are complete.

## Decision

Use the **already-authenticated Web-CEO v3 Executive MCP + Session Bridge** as the
ChatGPT-facing communication bus. The direct hot path is:

```text
ChatGPT Web session (+ connected Executive MCP plugin)
    -> authenticated MCP / existing authorized secure tunnel
    -> Executive v3 host (OAuth, read/submit scope, principal, audit)
    -> private CeoIngress / InstalledSessionBridgeProvider
    -> canonical Runtime + Agent Dialogue owner
    -> selected native Hermes profile (mmmeta / mmsecretary)
    -> original response via session_reply_read
```

For delegated project work, `session_summon` calls existing Executive admission
and Capacity placement. DeepSeek as a **native harness** is NOT interchangeable
with a DeepSeek model used as an inference pool. The actual native DeepSeek
create/resume/client and original-answer consumer remain owned by existing
[PR #2177](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2177)
and `integrations/deepseek_attended_fabric/`. No new DeepSeek launcher or
session store is created here. Existing
[PR #2202](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2202)
owns Hermes/DeepSeek desktop conversation UI. Existing
[PR #2066](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2066)
owns durable Web continuation/observation. Do not overwrite their source
or publish a second observer/watcher.

The shared OS UI may later present this exact tool flow in a chat-like team
picker. A plugin with an MCP Apps component can render such a picker but must
call the SAME authenticated tools; it must not maintain its own messages.

## Exact immediately reusable ChatGPT tool flow

1. **Select:** Call `session_targets({"kind":"hermes_meta"})` or
   `session_targets({"kind":"hermes_secretary"})`. A missing/empty role is
   UNAVAILABLE/NOT ENROLLED, not permission to invent a target. Omitted kind
   deliberately yields the legacy inventory rather than native Hermes.
2. **Send:** Copy the selected row's `target_ref` and
   `continuation_operation_key` verbatim into one `session_send` call with
   the bounded `instruction` and `stop_condition`. A receipt can mean
   COMMITTED/ADMITTED, not that the model has completed or the parent read it.
3. **Read:** Call `session_reply_read({"operation_key":<same key>})`.
   For Hermes, only actual `native_status=OBSERVED`, terminal admission and
   original answer support a reply claim. Read is NOT acknowledgement or
   parent consumption. No success is inferred from `ok` alone.
4. **Continue:** For a follow-on native Hermes turn, discover the newly
   current exact target and send its own canonical continuation. Preserve all
   original keys/receipts; never rerun an uncertain prior SEND.
5. **Work, not chat:** When project admission is needed, call
   `session_summon` with the real workstream, department, objective, priority,
   bounded execution profile and exact validation/write scope. It is
   provider-neutral and does not promise DeepSeek execution.

These are the existing installed tool contracts in
`integrations/executive_mcp/web_ceo_sessions.py`,
`integrations/session_bridge/return_tools.py`, and
`integrations/session_bridge/installed.py`. The thin Python helper
`integrations/session_bridge/web_team_client.py` is a presentation client
for exactly these calls. It has no separately callable MCP listener.
It deliberately preserves typed refusals and original-effect uncertainty.

Transport loss while sending a continuation preserves the `session_send` tool
name and original continuation key for `session_reply_read`. An uncertain
`session_summon` instead preserves its admission operation key: recover the
original Executive admission receipt and use its exact `request_ref` with the
existing Executive reconciler when available. A missing receipt remains
unresolved; a continuation read cannot reconcile a worker admission, and the
request must not be resubmitted. Cancellation after either dispatch retains
the original `CancelledError`, with `team_bus_effect` and an exception note
carrying the same original tool/key and recovery guidance.

## Live census and known deployment gaps (do not flatten the layers)

- The protected source's Session Bridge target kinds include
  `hermes_meta` and `hermes_secretary`; their native Runtime owner is
  implemented in `hermes_native.py`/`runtime_return.py`. Arbitrary
  Hermes role profiles are NOT yet in this authenticated public target
  catalog. Extending coverage requires the current Hermes native owner to
  expose an enrolled, principal-filtered exact roster; no profile guessing
  from local config or role names.
- At this inspection the connected **Executive V3 tool** advertised
  `session_targets.kind` only for fabric_attempt/codex/claude, despite
  newer protected source adding native Hermes kinds. Refresh the installed
  app's tool metadata only after the actual host composition is verified.
  This is a deployment/schema mismatch, not proof that Hermes is addressable.
- Earlier connection probes returned OpenAI-facing MCP SSE 429. The subsequent
  2026-11-08 recovery reached Executive V3: `session_targets({})` returned a
  successful empty legacy projection, while `executive_state` returned
  `backend_unavailable`. The installed Control reader at `b4a5a8925c6c`
  rejects valid multiline quoted Macro frontmatter. The accepted parser fix
  is already in merged PR #2088 (`910b3eca8d2ed868cb5a83a8459ee702c4c30f6a`);
  adoption must use the original installed Control release path. An MCP-only
  update cannot replace the Control parser. No send, native turn or worker
  launch was attempted. Current installation and original-effect holds remain
  tracked under programme issue #1893; this source client does not release them.
- Source tests for `integrations/deepseek_attended_fabric` prove its
  native AgentLoop boundary under fixtures, NOT installed DeepSeek session
  enrollment, a real admitted remote worker or source-provider usage.
- A custom MCP plugin can be attached to the existing authorized remote
  endpoint or Secure MCP Tunnel. Do not open an unauthenticated public
  listener or reimplement OAuth/JWT. Existing workspace/plugin permissions
  and OAuth subject/scope policies must independently authorize every call.
- ChatGPT tools act while the Web turn is active. An asynchronous reply
  can be recovered on a later Web turn by original operation key. MCP event
  subscription/source exists, but events do not automatically wake a finished
  ChatGPT conversation. Native always-on agents may be real callback
  consumers through the existing subscribed owner after activation.

## Acceptance (the product journey, not just source presence)

| Journey | Required evidence |
|---|---|
| Web plugin connection | Exact installed Executive MCP host generation and OAuth read/submit identities, current tool inventory with Hermes target kinds; no SSE 429 |
| Select bot | Authenticated target list for both enrolled Meta and Secretary under independent Web principals; revoked/unenrolled profiles absent |
| Web to Hermes and back | One real native provider turn, original SEND commit/admission, retained original reply and returned answer in that Web session; no Slack hop |
| Interrupted continuation | Timeout/lost transport, exact original key recovery by read-only `session_reply_read`, no duplicate native submit, no false answer |
| Multi-bot roster | Native enrolled and authorized additional profiles from existing owner; exact immutable session generation, no ad-hoc registry |
| Web to DeepSeek harness | Existing #2177 original session create/resume, real agent execution, session history and returned result, original-parent consumption; not just the same model called via Fabric |
| Revocation/restart | Current principal and native generation fences, signed-in/out transitions, no cross-account leakage, original delivery preserved |
| OS team UI | Bot selector, message composer, pending/error/answer distinction, original operation reference and rerender after restart; no second transcript DB |

Completion of this addendum is **not** completion of the Executive Ecosystem
programme's original H1-H8 or the native Hermes/DeepSeek release tracks.

## Source qualification and rollback

`tests/test_session_bridge_web_team_client.py` exercises exact target
selection, a single verbatim send, stale/forged target refusal, typed/transport
EFFECT_UNKNOWN, read-only original-answer recovery, unavailable reads and
provider-neutral Executive work admission. Regressions distinguish admission
recovery from continuation recovery, reject numeric/malformed `ok` values and
retain original cancellation after a single dispatch. Repository CI executes
these tests against real `integrations.session_bridge.schemas`; earlier local
shim results are not a substitute for that exact-head qualification.
No active configuration, OAuth, public route, plugin installation, service,
Hermes profile, DeepSeek session, run admission or deployment is changed by
this candidate. Rollback removes only the optional client and test/docs.

## Native ChatGPT Work / Dot webhook continuation (source owner reconciliation)

**Verified platform capability:** OpenAI's [MCP Events specification](https://developers.openai.com/plugins/build/mcp-events) supports asynchronous signed webhook events into **ChatGPT Work chats on Web**, Work Cloud on desktop, and **Dots**. Ordinary finished ChatGPT chats do **not** gain unsolicited wake-up merely by having a plugin. A skills-only plugin is not an MCP event server and cannot advertise events itself.

**Actual existing Mastermind source** (protected `master` pin `5c3d3885234358aefb97ecdbc59be0864df14f8b`): `ops/executive_os/executive_mcp_entry.py` already has the explicit default-off `reply_events_armed` host selection; `integrations/executive_mcp/server.py` injects `reply_event_rpc` only with the original authenticated `session_reply_read`; `integrations/session_bridge/web_reply_event_asgi.py` supports modern MCP event method dispatch under the unchanged bearer authorizer. `reply_event_host_composition.py` and `installed_reply_events.py` are pre-existing conditional host owners, while `runtime_reply_subscriptions.py` and `runtime_reply_delivery.py` preserve sealed original subscription facts and bounded signed delivery **within existing Executive Runtime**. These are already source-built; do not build an alternative webhook server, subscriber DB, queue, admission, or token verifier.

**Important Hermes gap:** The incumbent `session.reply_committed` event projection is built around canonical **Agent Dialogue / native Codex-Claude** reply commits with `request_ref`, `message_key`, and `in_reply_to`. The direct Hermes Meta/Secretary path in `RuntimeSessionReturn.send_hermes/read_hermes` has independent native admission/original-answer evidence and has not been shown to trigger that event. Until a current, owner-approved bridge joins **the actual observed Hermes native original result** to a correctly authorized event definition/subscriber, **do not claim that live Hermes replies push into Work/Dots**. Never fabricate an Agent Dialogue message merely to satisfy event fields. Existing exact-key `session_reply_read` remains the primary Hermes answer path.

**Activation path:** Qualify actual installed Executive V3 MCP health and current JWT resource policy; ensure real Meta/Secretary enrollment and refresh advertised target inventory; inspect the opt-in `reply_events_armed` and sealed original key/owner grant and authenticated subscription composition without assuming that source means armed. Then add only the missing Hermes-original-result event projection or real producer hook *inside the incumbent event owner*, with tests covering original identity, same-operation idempotency, revocation, retained committed answer vs pending, restart, malformed callbacks, and no duplicate native submits. Prove full event discovery (`events` capability), `events/list`, `events/subscribe`, challenge and sealed persistence, signed HTTPS 2xx, Work/Dot event receipt, `session_reply_read` and `events/unsubscribe`. For native Codex/Claude, reuse existing `session.reply_committed` exactly. Do not enable the feature before host key/policy custody and exact user presence are verified.

**ChatGPT-side plugin:** [Mastermind Agent Bus](https://chatgpt.com/plugins/Plugin_8ce83097d87081919bba9f5a0063ec34) v0.1.1 describes this Work/Dot flow and explicit native-Hermes caveat. It is a skills-only companion to the separately installed/authenticated **Executive V3 MCP**; installation does not replace the installed Control reader, enable direct native target kinds or activate webhook delivery. Recovery of these live dependencies is part of the original Executive release path.
