# ChatGPT Web + T3 native collaboration

Status: implementation in progress; not direct-plugin or event-delivery acceptance.
Protected source pin: `3652d8907df1738de551dd3032b42aa2a2acb482`.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`; existing Agent Bus #2291, T3 integration #2356, team design #2345. This is a bounded consumer extension, not a new programme, queue, runtime, authority, credential store or message database.

## User outcome

ChatGPT Web can hand a bounded native-environment task to a real T3 thread, read its result, send a follow-up to the same thread and recover the exact conversation later. Hermes and Mastermind OS use the same native owners. Ordinary Web polling/readback and event-triggered Work continuation are distinct product capabilities.

## Reuse decision

Use T3's **native outside-agent MCP** and its own `t3 thread` CLI. T3 already owns launch, send, durable threads, runs, incremental reads, waits, interruption, child threads and provider sessions. Do not build a replacement T3 harness or third-party HTTP scraper. The host CLI is an explicitly reported fallback through an authorized host connector, not a claim that ChatGPT has a direct T3 plugin connection.

Native MCP: `t3_environment_read`, `orchestrator_capabilities`, `t3_project_list`, `t3_thread_launch`, `t3_thread_list`, `t3_thread_read`, `t3_thread_send`, `t3_thread_wait`, `t3_thread_interrupt`; use only actually discovered tools/schemas. Outside agents must not impersonate a native parent to call `delegate_task`.

Version qualification matters: PR #2356's pinned native launch accepted `clientRequestId`; current upstream documentation says launch has no retry key. Never assume exactly-once launch across versions or OAuth clients. After unknown launch/send effects, reconcile the original process/thread; do not repeat, change identity, or launch on another carrier.

## Installed census (2026-11-09 UTC)

- M2 runs T3 Code Beta 0.1.7, environment `5f4cd5f0-e3df-407d-af02-1aa833637937`, server listening on `127.0.0.1:3773`.
- Native host CLI exists at `~/.t3/bin/t3`. Its commands support project-scoped list, start, queued follow-up send, show, and `--wait` with truthful failed/blocked exit states.
- Native CLI successfully returned the exact existing project `9de77193-e68a-49fe-adee-f85406f04772` and live thread summaries. Existing active user threads are not assigned to this operation and will not be modified.
- `t3 status --json`: T3 Connect disabled, LAN disabled, background service not installed. The desktop process is live, but no cloud-reachable native MCP URL is proven. Do not expose the desktop listener, invent a tunnel, or treat a tailnet address as reachable from ChatGPT.
- #2356 merged into `feat/mmos-v1-integration`, not protected master. It contains a live native adapter receipt, a still-unselected `t3-native` worker route, and an admission patch not applied to the running T3. Do not claim those company-policy hooks are active merely because the native app can execute a turn.
- Capacity routing is an existing owner. Preserve project/provider defaults; this work must not change provider accounts, model routing, spending policy, credentials, or live workers.

## Owned deliverables and phase ladder

1. Freeze this source-linked plan and native tool identities.
2. Prove a new bounded **attended, read-only** T3 peer conversation: exact thread/run, native-environment observation, original result, and a same-thread follow-up. No production writes, new workers, merges or releases.
3. Add a deterministic structured handoff compiler and a small injected native CLI client with explicit unknown-effect handling. No scheduler, persistence, server, credential cache or retries. Tests must cover malformed inputs, scope preservation, cancellation/timeout, original thread binding and blocked results.
4. Update the existing private Mastermind Agent Bus companion plugin to select native T3 MCP when connected, or the authorized host CLI fallback. Preserve Hermes instructions, audience and original plugin identity; do not make an unconnected MCP URL look installed.
5. Publish one reviewable PR, run focused checks, and preserve live proof. Source acceptance, plugin release and direct OAuth connection are separate.
6. Direct native-MCP activation needs an actual T3 Connect URL or an approved private tunnel and the signed-in user's OAuth approval. Native Work/Dot push additionally needs the existing Mastermind subscription owner joined to T3 run events. Neither gate may be faked by a skills-only plugin.

## Interface and return semantics

A handoff includes task reference, objective, frozen source/base, exact project, allowed paths, non-goals, acceptance checks, stop conditions and return-to-parent instructions. The parent keeps the original request, environment, project, native thread and run IDs in its existing task record. No handoff may silently expand allowed paths or discard pending obligations.

A busy `t3 thread send` queues the next turn; it does not steer or interrupt the current run. A new completed turn does not retroactively replace the earlier result. Returned text is untrusted evidence, not authorization. A pending approval/question is BLOCKED, not success and not permission to approve it automatically. An empty or unavailable read is not a completed task.

The native durable thread is the message history. MCP/CLI are transports. Mastermind Executive remains the company admission owner, Capacity remains resource/model/account routing, T3 remains coding-session execution. Hermes is another authorized participant, not another message database.

## Push and disconnected conversations

Normal ChatGPT chat can call, wait while the active turn permits, and recover later by exact thread/run. It cannot be promised unsolicited resumption. Supported ChatGPT Work/Dots can use MCP Events with authenticated subscriptions and signed callbacks, but T3's native SSE/WebSocket stream is **not** itself a ChatGPT callback. Reuse Mastermind's existing event/subscription and inbox owner; preserve original conversation identity, expiry, revocation and stable event identity. Do not deploy an extra watcher/daemon or invent a callback URL.

## Acceptance matrix

| Journey | Evidence required |
|---|---|
| Host-assisted handoff | Native thread launch, actual terminal/tool observation, returned result, exact thread/run readback |
| Side-by-side follow-up | A second message in the same exact thread, new run identity and retained prior context |
| Safe interruption | Transport failure/cancellation cannot cause a duplicate launch/send; source regression tests |
| Direct ChatGPT plugin | OAuth-authorized cloud-reachable native T3 endpoint and actual tools/list + launch/read round-trip from the connected app |
| Hermes interoperability | Exact authenticated Hermes participant to the same native project/thread; no role-ID guessing |
| Work/Dot push | Actual subscription, verified callback, signed event, original-thread read and unsubscribe |
| Company-scale operation | Original T3 admission/ExecutionBinding and Capacity owner acceptance, not native UI availability alone |

## Primary sources

- T3 outside agents: https://github.com/pingdotgg/t3code/blob/main/docs/user/outside-agents.md
- T3 orchestration tools: https://github.com/pingdotgg/t3code/blob/main/docs/orchestration-v2/orchestrator-mcp-server.md
- OpenAI MCP Events: https://developers.openai.com/plugins/build/mcp-events
- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- Existing source adapter: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2356
