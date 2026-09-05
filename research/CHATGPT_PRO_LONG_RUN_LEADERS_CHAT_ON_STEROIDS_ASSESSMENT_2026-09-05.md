# ChatGPT Pro long-run leaders: Chat On Steroids assessment

Date: 2026-09-05

Operation: `chatgpt-pro-long-run-leaders-research-20260905-sol-001`

Existing organizational context: `WS:CHAIRMAN-CONTROL-ROOM`; related projection `MAS-198`.

Status: **RESEARCH CANDIDATE / RECORDS_ONLY / NOT AN ARCHITECTURE FREEZE / NO RUNTIME AUTHORIZATION**.

This record answers the Chairman's request to investigate Chat On Steroids and design substantially more capable, long-running ChatGPT-web leadership across Personal Pro and Business accounts. It does not commission implementation, replace an active owner, widen Web-Sol, authorize installation, or claim production capability. Its eventual GitHub research PR is its sole publication carrier; it is not an Executive Job or worker assignment.

## 1. Evidence and method

The protected Mastermind snapshot inspected, and rechecked before this record was authored, is `b0f85b0f1c66825ecec4bf6ce32dcbfac0c14b93`, tree `8d3ad268079a0b3d3438c0fe4ecc7d04a2da2b8a`. INDEX and required COLD_START, WORKER_AVENUE_ROUTING, RECONCILE_STATE and CLOSEOUT procedures were read from that same commit. Compatibility: `mastermind.sol_skillpack.v1`, version 1.0.1, bootstrap major 1.

Chat On Steroids was inspected at `totec448-spec/chat-on-steroids@dbff15b7296358102ee3e141f183e89a4a8d1e0e`. Read sources include README, SECURITY, tool-surface documentation, turn-signal documentation, the MCP surface implementation, platform capability implementation, and extension manifest. This was a bounded static source/document review, not a full security audit or execution test. No third-party binary, extension, tunnel, credential or host process was installed or started.

Macro's `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md` was inspected at `646a9ba04cfb9bbb85c3b75128c3cee50358fa9e`. Current GitHub and Slack evidence was read separately. Searches did not recover the previously mentioned Chat On Steroids session; absence from those searches does not establish that no prior investigation exists.

Official OpenAI and OpenClaw documentation was checked on 2026-09-05. Entitlements, provider interfaces and third-party default behavior require revalidation before any implementation release.

## 2. Thesis and complete intended journey

The target is a long-lived governed program whose reasoning sessions can be replaced, not a browser turn that never ends.

Chairman outcome -> canonical context -> bounded Pro reasoning -> admitted child work -> isolated execution -> immutable evidence -> material return -> exact leader continuation -> adversarial acceptance -> durable organizational handoff.

The Chairman should not have to find the right tab, reconstruct context, carry routine messages, or determine whether a worker actually ran. The leader should preserve the complete product thesis, delegate concrete work, consume real evidence, challenge poor results, and stop only at an explicit accepted or blocked boundary. Long-running execution must survive a leader's inactivity without pretending the leader is still reasoning.

The proposed value measures are accepted capabilities per scarce reasoning turn, lower recovery loss, fewer manual interventions, useful independent reviews, and zero unauthorized or duplicate effects. Elapsed turn duration is not itself a value metric.

## 3. Capacity assumptions

OpenAI currently documents Pro $200 as 170 Sol Pro messages daily, 200 Astra/GPT-6 Pro messages weekly, and a combined 200-message daily cap. Business Premium instead has a shared included 50-message weekly Pro allowance. Work/Codex usage is separate from Chat. These are public plan descriptions, not an account-local entitlement attestation. [O1, O3]

For three eligible Pro $200 accounts, the nominal arithmetic is `3 * (170 * 7 + 200) = 4,170` messages per week, averaging about 596 daily, subject to both time windows and all service restrictions. Multiplying by an assumed 30-60 minute elapsed turn gives roughly 298-596 aggregate task-hours per day, not reserved GPU-hours. Sustaining that elapsed workload would require approximately 12.4-24.8 concurrent turns on average. Actual allowable concurrency, availability and useful throughput remain unmeasured.

The existing Capacity owner should record verified account/workspace/model/surface eligibility and observed reset information. Unknown values stay unknown. No new quota database, account sharing, limit evasion, automatic account hopping after START, or duration-padding objective is proposed.

## 4. What Chat On Steroids contributes

The project offers a real local-tool design rather than a prompt-only productivity pack. Core exposes approved-file reads, images, patching, terminal execution and continuing process handles. Its optional Desktop surface exposes screen/window observation and bounded input actions. Its companion extension provides local session recording and supports externally orchestrated worker chats, compaction and a goal/loop controller. These are project implementation/documentation findings, not proof of reliability on Mastermind's hosts. [C1-C6]

Useful patterns to adapt:

- Small tool families separated by capability boundary; Core and Desktop are distinct discovery surfaces.
- Batched file reads, bounded result sizes, cursors and process-output deltas instead of repeatedly loading full context.
- Familiar read/patch/exec/continue semantics that reduce model adaptation cost.
- Permission enforcement at invocation time even when the conversation retains an older tool schema.
- Desktop actions bound to a recent observation, with stale-target refusal and partial-batch effect reporting.
- Explicit incomplete/unknown states rather than treating silence as success.

Patterns not to import as Mastermind authorities:

- Its independent session recorder as organizational memory.
- Its prime/worker identity and slot system as Executive lifecycle or Capacity.
- Its automatic compaction as RuntimeBinding succession.
- Its free-running Loop mode as company policy or acceptance.
- Its React/Fiber/DOM observations as canonical execution or semantic ACK.

The repository is MIT-licensed, but any reused code needs pinned provenance, preserved license notices, dependency review and tests. Selective lawful reuse is preferable to deploying the whole application as another company control system. [C7]

## 5. Security and compatibility findings

### 5.1 Local tools are not a sandbox

The project's security policy explicitly states that shell commands run with the logged-in user's normal privileges and are not confined to approved folders. Filesystem root checks therefore do not establish a shell isolation boundary. Fresh Core permissions are enabled, read-only is off, and recording is enabled. Recorded history is not encrypted by Electron safeStorage. Release binaries are unsigned and macOS builds unnotarized. [C2]

A Mastermind evaluation should begin with read-only synthetic files in an isolated environment. Any later shell authority needs the existing worker sandbox/worktree boundary, scoped credentials and network policy. Do not expose the Chairman's home directory, authenticated account settings, cookie stores, Keychain contents or unrelated desktop windows.

### 5.2 Documentation drift is real

One SECURITY bullet describes Desktop as unavailable on macOS, while the tool reference and actual `src/main/platform.ts` support macOS desktop capabilities on compatible systems. The source gates macOS desktop support by Darwin version. This is documentation inconsistency, not a claim that the runtime is broken. Platform-specific production behavior still needs a pinned-binary canary. [C2-C4]

### 5.3 The continuation controller is not free or authoritative

The README describes Goal/Loop as using an additional OpenRouter model. It receives user messages and final answers, not all tool evidence. Therefore its completion assessment is not independently grounded in the omitted evidence. Any such external-model path also needs explicit data-egress approval and a separate cost budget. Mastermind should instead make deterministic state transitions consume canonical receipts, with a model used only for bounded judgment. [C1]

### 5.4 Browser access is not provider authorization

A browser extension can implement an action without that action being an approved provider integration. OpenAI's consumer terms restrict automated extraction and bypassing service restrictions. Unattended prompting or transcript capture must not be presumed authorized merely because open-source code implements it. Use approved integrations, preserve native confirmations, and keep unsupported wake paths blocked or attended. This is an operational release gate, not a categorical claim that all browser automation is prohibited. [O8]

## 6. Account-specific routes into one system

### Business: direct supported custom tools

Proposed route: Business ChatGPT -> approved custom MCP -> existing Executive read/admission owners and isolated workbench -> existing workers/evidence.

OpenAI documents full custom MCP write support for Business/Enterprise/Edu, whereas Personal Pro custom MCP remains read/fetch. Secure MCP Tunnel can reach a private/local MCP server through outbound connectivity; its permissions and workspace association do not grant extra app or filesystem authority. [O2, O4]

Do not put arbitrary shell execution behind a general CEO-admission endpoint. Expose narrow workbench tools only to an authorized, exact-bound worker role. Leadership tools should favor mission/evidence/decision interfaces.

### Personal Pro: governed delegation without fake write tools

Preserve the accepted Personal-Pro Shell from merged Mastermind PR #99: protected source and canonical context -> fresh approved state -> supported Slack action -> dedicated Executive Relay/CeoIngress -> Executive OS. The model's ability to send a permitted Slack message is not itself Executive admission. [M3]

Some approved apps support actions on Personal Pro; that is distinct from the custom-MCP restriction. The exact account/app permissions must be attested. Do not disguise a command or filesystem mutation as `search`, `fetch`, a URL parameter, or a read-only MCP tool. [O2, O5]

This route can provide project-leadership parity without claiming identical direct-computer permissions. An external authorized worker executes, and Pro reads the resulting evidence.

### Work/Codex: complementary supported execution surfaces

ChatGPT Work has documented Slack-triggered tasks; Business release notes also document app-event triggers including GitHub PR activity. These are useful candidate attention/execution adapters, but are not proof that a particular existing Chat Pro conversation can be resumed or that its Chat Pro quota pays for Work. [O3, O5, O6]

Codex App Server provides documented thread start/resume, turn operations and event subscriptions. Prefer the existing Codex provider adapter for concrete long-running coding work rather than rebuilding that execution protocol through screenshots. Provider thread persistence remains a provider implementation detail under Executive ownership, not a second company lifecycle. [O7]

## 7. Existing estate and disagreement ledger

| Capability or record | Evidence-supported status for this assessment | Consequence |
|---|---|---|
| Protected Personal-Pro Shell architecture | Records landed in PR #99 | Preserve its dedicated admission path; merge does not prove live relay. |
| Web-Sol extension/native-host/protocol source | Source present at inspected protected commit | Do not build a competing extension or native bridge. |
| Exact context succession | Accepted source law and CR-F0 design exist, labeled SPEC_ONLY | Extend existing CR-P1/CR-B1/CR-D1/CR-PROD1 ladder; do not invent a rollover system. |
| Responsibility-aware watcher projection | PR #484 protected at the inspected head, explicitly BUILT_NOT_PROVEN/default-disarmed | Host-fact acquisition, pre-Wake integration and canary evidence remain distinct. |
| Web-Sol Realm1 source repair | PR #485 and its existing carrier were active during research | Do not redirect its worker, reuse its child operation, install its candidate or issue a competing release. |
| Control Room refresh | PR #486 was Draft/HOLD during research | Respect the existing Integration owner's release/proof slot. |
| Macro Control Room next-action text | References older #432/#435 boundaries while newer GitHub/Slack evidence discusses #485 | Organizational text is not a current release receipt. Owner must reconcile after the current operation's result; this research does not rewrite status. |
| Real multi-account unattended leadership | Not demonstrated by this inspection | No PROVEN_LIVE claim; verify separately per account and path. |

The context-rotation law keeps existing v1 Web-Sol at INSPECT/FOREGROUND. It envisages only separately reviewed closed successor/create/bootstrap/verify actions. Generic CLICK, TYPE, SEND_TEXT, EXECUTE_JS, READ_TRANSCRIPT and account switching are forbidden on that surface. This candidate does not amend that law. A local product-testing workbench is a separately authorized worker capability, never a back door into ChatGPT session control. [M1, M2, M4-M7]

## 8. Proposed capability backlog and owner boundaries

The following is a design candidate, not evidence that these interfaces exist or authorization to implement them.

| Capability | Required behavior | Existing owner to extend |
|---|---|---|
| Account/surface capability census | Attest model/mode/workspace, read/write permissions, connector schema, host/extension versions and freshness; report unknown honestly | Capacity and runtime/provider attestation owners |
| Canonical context bundle | Compose intent, same-SHA skills, accepted decisions, current exact heads, open dialogue, evidence references and next action | Existing boot packet/context composition plus Agent OS |
| Efficient repository intelligence | Batched reads, precise symbol/reference lookup, isolated worktree context, bounded diffs and evidence queries | Existing CodeIntel/repository tools; verify exact current contracts before reuse |
| Isolated local workbench | Read/image/patch/build/test with head/path/permission preflight and attributable outputs | Existing worker/provider execution and sandbox owners |
| Durable long-running execution | Commands or workers survive the leader turn; reconcile handles, exit state, cancellation and partial effects | Executive Job/Attempt plus existing provider process/session adapters |
| Bounded child delegation | Concrete mission, scope, independent reviewer, reserved ownership and budget; no second swarm registry | Executive/Capacity and current worker routing |
| Event-driven material-return routing | Wake for result, blocker, decision or exception; coalesce low-value progress; replay-safe and explicitly unavailable when unsupported | Company Dialogue, Agent Relay and Wake |
| Exact continuation and rotation | Durable handoff, reconciled effects, exact successor, semantic ACK, conditional binding cutover and predecessor fencing | Existing Web-Sol CR ladder, RuntimeBinding and Agent OS |
| Production evidence and acceptance | Tests, artifacts and browser/machine evidence bound to the exact candidate/deployment; no self-certified completion | GitHub, existing proof owners and Sol review |
| Chairman operational visibility | Current responsibility, next action, blocker, proof age, binding health and available pause/revoke actions | Existing Control Room; keep navigation distinct from action authority |
| Capacity efficiency and evaluation | Accepted outcomes per turn, intervention rate, context loss, duplicates, queue delay and observed limits | Existing Capacity/observability/evaluation owners |

### Contract discipline

The shared envelope should derive existing responsibility/Job/Attempt/binding references; include schema version, observed time, source revision, binding generation, effect state and evidence references; and explicitly type refusal and stale/unknown states. Any projected next action is advice, not authority. Every mutation rechecks current permission, binding and expected source at the owner boundary.

Reads can be cached by immutable source hash. Runtime and permission state cannot be made fresh by rewrapping an old timestamp. Tool output uses pagination and evidence references; essential failure fields must survive truncation. Tool names and schema variants should remain small and discoverable, with larger tool families loaded only for their concrete task.

Patch preflight is not a claim of cross-file crash atomicity. Cancellation requested is not cancellation proven. An expired lease must not automatically authorize a replacement writer when an effect is unknown. These states are reconciled through existing owners, not a new retry ledger.

### Intelligence and authority split

Deterministic code handles identity, permissions, idempotency, binding generations and admissible transitions. Statistical estimates may inform context pressure or capacity forecasts but cannot prove context exhaustion or grant authority. Models handle plans, synthesis, review and bounded decisions; model prose is not a runtime receipt.

## 9. How the sessions should work harder

Give a Pro turn a coherent mission, an evidence plan, a substantial reasoning budget, exact non-goals, and an explicit stopping boundary. Favor architecture, hard debugging, research synthesis and adversarial acceptance. Do not spend Pro turns on routine acknowledgments, status polling, trivial routing or ceremonial continuation; current WORKER_AVENUE_ROUTING already distinguishes these classes.

A leader need not personally perform every command. The valuable loop is thesis -> bounded implementation -> independent evidence -> difficult review -> next useful slice. Batch independent research questions and repository reads. Checkpoint after meaningful decisions, before context pressure, and at every handoff. Store the durable continuation in Agent OS rather than relying on the dying chat to summarize itself.

The continuation packet should preserve original intent, accepted decisions, rejected alternatives, current claims and supporting evidence, exact source/binding references, unresolved effects, open reciprocal dialogue, and one next action. Do not attempt to export hidden chain-of-thought. Preserve useful conclusions and provenance instead.

## 10. Chrome, Codex and OpenClaw roles

Use the existing Mastermind extension as the narrow exact-session actuator. Use existing deterministic host services for timers, health and material-return handling; expensive model reasoning should not be the always-on polling mechanism.

Codex is the preferred supported coding execution surface through the existing adapter. OpenClaw is optional as a bounded browser/computer provider where its permissions and host compatibility are verified, not as a replacement CEO, memory store, scheduler, account selector or failover system. Its documentation explicitly assumes a shared trusted boundary per gateway and describes broad cross-session visibility defaults. Treat that as a security design constraint, not multi-tenant isolation. [O7, X1, X2]

Do not run multiple independent composer writers against the same live ChatGPT profile. Existing Mastermind records identify managed GoLogin/Multilogin profiles as the relevant estate; support for ordinary Chrome does not prove compatibility with those environments. No real-seat migration or takeover is authorized here. [M5]

## 11. Proposed proof-first sequencing

These are observable outcomes to map onto existing operations, not newly commissioned waves or a parallel queue.

1. **Capability truth in the existing cockpit.** One account's actual tool/model/permission/binding readiness is visible, and absent proof is shown as unknown. No invented quota scraping or session registry.
2. **One read-only local investigation.** A Business chat inspects a synthetic isolated repository and image, receives exact references, and cannot access forbidden paths or another session's data. Pro consumes the same permitted evidence through its supported read route.
3. **One governed lead-to-worker result.** A Pro leader uses the approved admission carrier, one existing worker performs a harmless repository task in isolation, and the leader reviews immutable test evidence. Duplicate delivery produces no duplicate work. Business direct admission, when separately approved, reaches the same owner.
4. **One real wait/return continuation.** A child completes while the leader is inactive. The accepted material-return/wake path resumes the exact leader or truthfully reports wake unavailable; Slack delivery alone does not pass. No permanent polling loop is credited as reasoning.
5. **One complete existing CR-ladder succession.** Follow CR-P1 then CR-B1, CR-D1 and CR-PROD1 under their current gates. The old generation cannot modify; dead-predecessor recovery works; lost receipts do not create another chat or repeat a bootstrap.
6. **One product capability through production acceptance.** Exercise a real program slice with exact deployment proof, relevant browser breakpoints or a real machine consumer, independent review and durable acceptance. Then measure multi-account scaling without changing quota or authority boundaries.

For each slice, the implementation handoff must include current source/owners, complete journey, contracts and null/correction behavior, deterministic versus model method, failure matrix, ordered changes, proof, stop condition and continuation. Reuse the existing operator assignment and routing laws; this document assigns no worker.

## 12. Minimum adverse test matrix

Wrong account/profile/Project; stale or superseded binding; two attempted writers; duplicate or renamed chat titles; lost submit/patch/process receipt; missing semantic ACK; revoked permissions with cached schemas; hostile instructions in repository/Slack/tool output; forbidden path and symlink escape; desktop target changed after observation; host/extension restart; expired authentication; tool schema drift; provider quota exhaustion; output truncation; predecessor dead before checkpoint; and late predecessor revival.

Pass conditions are no unauthorized effect, no blind duplicate, exact attribution, recoverable evidence and explicit degraded state. Testing should separate simulated source proof from the approved real host path. Green CI is necessary when required but not production acceptance.

## 13. Closeout and exact next action

Before this research, the supplied project's mechanisms and current platform limits were not recovered in a single pinned Mastermind record. After publication, this candidate makes the comparison, no-rebuild boundaries and proof-oriented backlog recoverable. Runtime capability is unchanged.

No install, credential change, Executive admission, worker assignment, merge, release, production proof, native watcher, Slack commission or Linear status update was performed by this research. No counterpart was placed on a reciprocal watch. The branch/PR are research evidence only. Agent OS wave status is intentionally unchanged because no new implementation or architecture acceptance is being asserted.

**Primary next action:** the existing Web-Sol/Session Automation and Integration owners review this research candidate against their fresh canonical state, attach each accepted capability to its existing owner/operation, and approve the first missing end-to-end proof slice. Resolve current source/host/semantic-ACK gates rather than start another session-management program. Any architecture amendment or implementation release needs its own explicit current approval and applicable gates.

## Sources

### Official provider documentation, checked 2026-09-05

- O1: https://help.openai.com/en/articles/20001354-gpt-56-and-gpt-6-pro-in-chatgpt
- O2: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- O3: https://help.openai.com/en/articles/20001275
- O4: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- O5: https://help.openai.com/en/articles/12525822
- O6: https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes
- O7: https://developers.openai.com/codex/app-server (redirects to https://learn.chatgpt.com/docs/app-server)
- O8: https://openai.com/policies/row-terms-of-use/
- X1: https://docs.openclaw.ai/tools/chrome-extension
- X2: https://docs.openclaw.ai/gateway/security

### Chat On Steroids, immutable source

All C references use repository `https://github.com/totec448-spec/chat-on-steroids` at commit `dbff15b7296358102ee3e141f183e89a4a8d1e0e`:

- C1: `README.md`
- C2: `SECURITY.md`
- C3: `docs/tool-surface.md` and `src/main/mcp/surfaces.ts`
- C4: `src/main/platform.ts`
- C5: `extension/manifest.json`
- C6: `docs/chatgpt-turn-signals.md` (a historical 2.0.2 signal analysis present in the inspected tree, not proof that all cited line numbers match current source)
- C7: repository license metadata reports MIT; preserve and review the actual LICENSE and dependency notices before reuse.

### Canonical Mastermind evidence

Unless otherwise specified, file references use `mastermindx-market-intelligence/Mastermind@b0f85b0f1c66825ecec4bf6ce32dcbfac0c14b93`:

- M1: `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`
- M2: `docs/superpowers/specs/2026-09-01-web-sol-chat-context-continuity-design.md`
- M3: PR #99, merge `b02630fc1f3587672390b383998b28cb3206202f`, and its Personal-Pro Shell research records.
- M4: `integrations/chairman_surfaces/web_sol_protocol.py`, extension/native-host paths located by protected source search; this is source-presence evidence, not a complete implementation review.
- M5: `macro@646a9ba04cfb9bbb85c3b75128c3cee50358fa9e:agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`.
- M6: Mastermind PR #484/protected commit message; PR #485, integrated head `194fa99ef27435631d60445122a8ee9b775e161c`, and existing carrier `C0BSBM78V1N/1788590911.956009`; these are time-bounded observations, not new release permission.
- M7: Mastermind PR #486, Draft/HOLD as inspected.
- Procedural references: same-SHA `docs/sol_skills/INDEX.md`, `COLD_START.md`, `WORKER_AVENUE_ROUTING.md`, `RECONCILE_STATE.md`, `CLOSEOUT.md`.
