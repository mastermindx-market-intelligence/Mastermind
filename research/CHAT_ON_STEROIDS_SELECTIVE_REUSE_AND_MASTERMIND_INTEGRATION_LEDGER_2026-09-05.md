# Chat On Steroids selective reuse and Mastermind integration ledger

**Date:** 2026-09-05  
**Research carrier:** Mastermind PR #490  
**Parent operation:** `chatgpt-pro-long-run-leaders-research-20260905-sol-001`  
**Status:** `RESEARCH CANDIDATE / RECORDS_ONLY / NOT AN ARCHITECTURE FREEZE / PRODUCTION_INERT`  
**Protected Mastermind source at publication preflight:** `c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36`, tree `95e00ca4e342648796a0e81950052d36b07bf3ef`  
**Compatible procedure:** `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1, loaded atomically from the protected commit above  
**Third-party audit pin:** `totec448-spec/chat-on-steroids@dbff15b7296358102ee3e141f183e89a4a8d1e0e`  
**License at the audit pin:** MIT, blob `4863f21719abdc21a635c77b9230c9e734a419a1`

This ledger answers the build-versus-buy question at mechanism level. It does not install or execute the third-party application, copy its code, create an app or connector, alter a Mastermind runtime contract, assign a worker, or authorize a later implementation wave. It preserves the exact source window inspected, separates useful interaction patterns from duplicate control systems, maps every accepted idea to an existing Mastermind owner, and defines the proof needed before any production use.

The source inspection was static. No Chat On Steroids binary, extension, tunnel, terminal, desktop backend, Goal/Loop model, browser command, or session recorder was run. No real Mastermind or ChatGPT account was exposed to it. A mechanism marked `ADOPT_PATTERN` means the design idea is worth implementing or preserving through an existing owner; it does not mean the audited implementation has passed Mastermind production acceptance.

---

## 1. Executive ruling

### 1.1 Build-versus-buy decision

**Do not install the upstream default product into the real Mastermind account fleet and do not adopt its app-wide session/agent/recording control system as Mastermind architecture.**

Use one of three narrower paths:

1. **Adopt or preserve a pattern through the existing Mastermind owner** when the pattern improves tool ergonomics, output bounds, identity, effect truth, or recovery without importing another lifecycle.
2. **Run a source-pinned disposable falsifier** when actual behavior must be observed before deciding whether a component is useful.
3. **Observe upstream only** when the mechanism is useful as comparative evidence but unsafe, duplicate, or lower priority than current Mastermind owners.

### 1.2 Why not deploy upstream whole

The audited application combines several distinct products:

- local file, patch, image, terminal, and desktop tools;
- public MCP surface discovery and enforcement;
- a Chrome extension and loopback extension bridge;
- durable conversation recording and search;
- request-to-conversation attribution;
- local session and workspace identity;
- context compaction and chat replacement;
- an independent prime/worker broker and worker revival system;
- an external-model Goal/Loop continuation controller;
- tunnel, release, update, and packaging machinery.

That breadth is valuable for learning. It is incompatible with adopting the product as Mastermind's governing runtime because Mastermind already has separate canonical owners for lifecycle, durable organizational state, exact surface binding, capacity, wake, dialogue, code truth, and evidence. Whole-product adoption would introduce parallel identities, state, retry semantics, session succession, worker ownership, and automatic model-input authority.

### 1.3 Immediate product implication

The fastest safe path to stronger ChatGPT web leadership is not a wholesale upstream installation. It is:

```text
finish the existing Business Steward read vertical
→ improve existing plugin/context composition
→ expose exact-bound worker capabilities through current worker profiles
→ prove material return and exact-session continuation
→ prove stale-session action coverage
→ scale only after matched evaluation
```

The exact sequence, role profiles, and completion ruler are preserved in the companion runtime-profile master plan on the same PR.

---

## 2. Verdict vocabulary

| Verdict | Meaning |
|---|---|
| `ADOPT_PATTERN` | The semantic pattern is directly useful and should be preserved or implemented through an existing Mastermind owner. The upstream code is not automatically adopted. |
| `ADAPT_IN_EXISTING_OWNER` | The mechanism is valuable only after it is re-expressed inside a named existing owner, identity model, and proof contract. |
| `DEFER_PENDING_PROOF` | Potentially useful, but actual client, platform, security, or production behavior must be falsified first. |
| `REJECT_AS_DUPLICATE` | The mechanism creates or owns state/lifecycle/identity already owned canonically in Mastermind. Do not import it. |
| `REJECT_FOR_SECURITY` | The audited boundary is too broad or weak for the intended Mastermind production claim. A separate narrow implementation may still be designed. |
| `OBSERVE_UPSTREAM_ONLY` | Retain as comparative research or potential future evidence; do not place it on the current critical path. |

A row may carry a primary verdict plus an explicit secondary condition. The most restrictive relevant boundary controls production use.

---

## 3. Source and methodology

### 3.1 Audited immutable source

All third-party findings in this ledger bind to:

```text
repository = totec448-spec/chat-on-steroids
commit     = dbff15b7296358102ee3e141f183e89a4a8d1e0e
```

A later upstream `main` was observed at `62608f266c92a4ff64f093af3721ecb20cd47c57`. It is not silently mixed into this assessment. Any later build or falsifier must pin its own exact source and re-run the relevant audit because upstream comments, defaults, protocols, packaging, and native dependencies can move.

### 3.2 Audited source families

The static review included:

- `README.md`, `SECURITY.md`, `AGENTS.md`, `LICENSE`, `package.json`, `electron-builder.yml`;
- extension manifest and bridge/runtime architecture;
- `src/main/mcp/**`, including server, Core, Desktop, session and instruction surfaces;
- path sandbox, filesystem operations, terminal execution, caller/process ownership and workspaces;
- session store, recorder, request correlation, retention, continuation and handoff logic;
- agent broker, Goal/Loop, bridge commands, update and tunnel adapters;
- historical tool-error evidence and release packaging workflows.

### 3.3 Authority and uncertainty rules

- Current code and reproducible tests outrank comments or older prose inside the upstream repository.
- This review did not execute those tests, so a source mechanism remains `BUILT_NOT_PROVEN` relative to Mastermind.
- The audit records several internal documentation/comment drifts. They are reasons to pin exact source and test behavior, not proof the complete application is defective.
- A Mastermind source file, plan, or catalog is also not live capability until its declared consumer and production proof exist.
- No retrieved source grants permission to install, call, mutate, merge, deploy, or widen authority.

---

## 4. Selective reuse ledger

### 4.1 Tool discovery, permissions, and result ergonomics

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 1 | Separate Core and Desktop MCP surfaces | Two independently discoverable servers keep the large Desktop schema and permissions out of ordinary coding sessions. | `ADOPT_PATTERN` | Existing federated SCF/BSC app generations and worker capability profiles | Preserve small authority-aligned surfaces. Do not create one super-MCP or make Desktop mandatory for code/research work. Test full no-query schema cost, tool-selection quality, and cross-surface leakage. |
| 2 | Static schema advertisement plus live invocation-time permission checks | A server generation keeps schema exposure monotonic while every call rechecks the current capability state. Revocation can refuse a cached tool instead of pretending the old schema disappeared. | `ADAPT_IN_EXISTING_OWNER` | Existing app-generation and capability-profile owners | Preserve immutable app schema generations and owner-side action-time enforcement. A cached schema must not retain authority. Prove revoked permission produces a typed zero-effect refusal without silently serving a different action. |
| 3 | Compact tool vocabulary aligned with familiar Codex operations | `read`, `view_image`, `find`, `apply_patch`, `exec_command`, and `write_stdin` reduce model adaptation overhead. | `ADOPT_PATTERN` | Existing CodeIntel, GitHub, worker execution and provider-adapter surfaces | Reuse familiar semantics where current owner contracts allow. Do not copy names into frozen five/six/six-tool CEO apps or create generic commands on a leadership surface. Measure tool selection and wrong-tool rates. |
| 4 | Batched bounded file reads | One call can read multiple approved targets, report failures per item, expose truncation, and retain useful partial success. | `ADAPT_IN_EXISTING_OWNER` | CodeIntel exact-worktree reads or exact-bound worker workbench | Bind every path to the current Attempt/worktree and source identity. Report coverage and truncation. Deny cross-root/symlink escape. Prove one invalid target does not erase useful safe targets or hide a security refusal. |
| 5 | Bounded repository search with explicit coverage | Search has time/result ceilings and can report elapsed time and truncation rather than imply complete absence. | `ADOPT_PATTERN` | Code Intelligence Fabric global discovery and exact-worktree semantics | Preserve requested/indexed ref, coverage, freshness, result cap, and continuation. A negative incomplete search must never establish nonexistence, ownership, or path freedom. |
| 6 | Validated local image reads | The implementation validates supported image signatures/structure and bounds decoded input before returning model-visible content. | `ADAPT_IN_EXISTING_OWNER` | Exact-bound worker artifact/image capability and Worker Browser evidence | Preserve MIME/structure/size validation, immutable artifact identity, and source path containment. Do not permit image reads from arbitrary account screenshots or secret-bearing settings. |
| 7 | Per-conversation learned workspace | Relative paths become ergonomic after an exact conversation has already proved an absolute project path. Unknown identity refuses relative paths. | `ADAPT_IN_EXISTING_OWNER` | Existing Attempt/workspace identity and CodeIntel binding | Do not use a chat-local 12-hour map as authoritative workspace selection. Derive the exact worktree from Job/Attempt/Worker and allow relative paths only inside that binding. Preserve no-guess behavior. |
| 8 | Canonical path sandbox with symlink/root-change checks | Canonicalization and real-path checks defend file tools against root escape and changed directory identity. | `ADOPT_PATTERN` | Existing worker sandbox, Source Continuity and exact-worktree readers | Test symlink, mount, nested repo, root replacement, case-folding, Windows junction and TOCTOU attacks. A file sandbox does not constrain shell or Desktop authority. |
| 9 | Patch preflight, staged replacements and best-effort reverse rollback | File operations preflight expected text, stage complete writes, rename, and attempt reverse rollback only when the path still matches the recorded post-state. Source explicitly says this is not filesystem-wide ACID. | `ADAPT_IN_EXISTING_OWNER` | Exact worker source writer / Source Continuity | Preserve current blob/head/path ceiling and return exact changed/unchanged/uncertain paths. Correct any instruction claiming cross-file atomicity. A rollback failure or concurrent edit remains visible and blocks blind retry. |
| 10 | Core instructions claiming cross-file patch atomicity | Model-facing prose says multi-file patching is atomic, while filesystem source documents best-effort rollback and no ACID transaction. | `REJECT_FOR_SECURITY` | No direct destination; use accurate worker instructions | Never copy this claim. Mastermind packets must distinguish preflight zero-effect failures, staged writes, partial commit, rollback attempt, rollback failure, and effect uncertainty. |
| 11 | Explicit output/token/result bounds | Reads, searches, images, request bodies, screenshots, session rows, and terminal output have independent ceilings. | `ADOPT_PATTERN` | Every existing owner-specific result contract | Bound bytes, decoded size, items, nested structure and continuation independently. Preserve decisive fields—effect, blocker, freshness, correction and stop condition—or return a typed refusal/evidence reference. |

### 4.2 Terminal execution and process ownership

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 12 | General `exec_command` shell | Commands execute as the logged-in user, begin in an approved root, and may outlive the call. The shell is intentionally not confined to approved folders. | `REJECT_FOR_SECURITY` for CEO/real-account use; `DEFER_PENDING_PROOF` for isolated worker | Existing sealed worker profiles / Codex execution owner | A production worker shell needs exact Attempt/worktree, least-privilege OS identity, positive environment allowlist, network policy, process group, resource bounds and cleanup. Do not expose it to ordinary Meta-CEO/Program CEO chats. |
| 13 | Shared child-environment scrubber | The implementation removes known connector/provider secrets and normalizes PATH before launching children. | `ADAPT_IN_EXISTING_OWNER` | Existing sealed worker process launcher | Use a positive allowlist or independently verified closed environment rather than relying on a blacklist of known key names. Prove unrelated GitHub, SSH, market-data, app, browser and deployment credentials are absent. |
| 14 | PTY/process handles across calls | A command can return a session ID and be polled or written through a follow-up call. | `ADOPT_PATTERN` | Existing Executive Attempt/provider process handle | Bind the handle to operation, Attempt, execution profile, worker, worktree, process generation and current effect state. A handle does not prove liveness, correctness, cancellation or exact-parent wake. |
| 15 | Same-session ownership of `write_stdin` | Proven local session ownership prevents another proven chat from controlling the process. | `ADAPT_IN_EXISTING_OWNER` | Existing Attempt/Worker/SessionEpoch/ProcessGeneration identities | Require exact current owner; do not accept anonymous ownership for modifying Mastermind processes. Prove compacted/rotated frontends do not transfer process authority except through the canonical binding transition. |
| 16 | Legacy anonymous process bucket | Calls without proven identity can create/continue only anonymously owned sessions. | `REJECT_FOR_SECURITY` for modifying work | No Mastermind equivalent | Unknown attribution must fail closed for worker/process mutation. It may produce unattributed diagnostics but cannot create an adoptable process or source effect. |
| 17 | Unread-result and unattended-process reminders | The connector reminds the same owner about terminal output and long-unpolled live sessions. | `ADAPT_IN_EXISTING_OWNER` | Existing material-return / Attention / Wake projection | Use deterministic event coalescing. Completed results and actionable stale processes can create material attention; unchanged polling must not consume reasoning turns. Reminders never create lifecycle, retry or stop authority. |
| 18 | Bounded terminal output deltas | Terminal output uses head/tail and deltas instead of repeatedly returning a growing transcript. | `ADOPT_PATTERN` | Provider adapter and Attempt evidence projection | Preserve exact byte/sequence cursor, lost/truncated interval, terminal exit, artifact refs and source process identity. Do not let a local cursor become a second process or retry ledger. |

### 4.3 Exact request, conversation, workspace, and caller identity

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 19 | Exact request-ID to page conversation join | Ownership uses the shared HTTP `x-request-id` and page `message.metadata.request_id`; tool name, timing, active tab and “only chat generating” are excluded. First exact proof wins and is persisted. | `ADOPT_PATTERN` | Existing host-context, RuntimeBinding and app/session attestation owners | Use only provider-supported exact evidence available on the actual host. If a trusted durable ChatGPT conversation handle is unavailable, report `CHAT_SURFACE_UNVERIFIED`; do not infer identity from DOM order/title/activity. |
| 20 | First-proof-wins correlation across reloads | Proven request ownership has no age TTL; later contradictory page observations cannot silently steal it. | `ADAPT_IN_EXISTING_OWNER` | Existing RuntimeBinding/host context evidence | Bind the proof to provider/account/workspace/app generation and local session epoch. Define correction only through stronger canonical evidence; prevent an old provider request from electing current responsibility authority. |
| 21 | Calls may proceed unattributed for ordinary Core tools | Unknown conversation attribution is recorded separately; some tools still execute. | `REJECT_FOR_SECURITY` for Mastermind mutations | Diagnostics only | Any filesystem write, shell, Desktop action, Executive mutation, dialogue edge, source write or provider action requires exact attributable authority. Read-only synthetic diagnostics may degrade to unattributed only when their data boundary remains safe. |
| 22 | Agent control requires exact conversation ownership | Multi-agent commands refuse absent/ambiguous caller identity. | `ADOPT_PATTERN` | Existing Job/Attempt/Worker and Company Dialogue | Preserve exact parent responsibility/current runtime binding for child commission and continuation. A message sender, role string or shared OAuth subject is not exact current child authority. |
| 23 | Conversation-scoped workspace movement during compaction | Learned relative-path context is moved from predecessor to successor and removed from the old conversation. | `ADAPT_IN_EXISTING_OWNER` | Existing RuntimeBinding succession and Attempt/workspace owner | Workspace remains an Attempt fact, not text in a handoff. Transfer only after exact successor/binding transition. A stale predecessor must lose both relative-path convenience and modifying authority. |

### 4.4 MCP endpoint and extension bridge boundaries

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 24 | Loopback MCP server on an ephemeral port with secret path | The model-facing MCP service is loopback-only; a high-entropy tokenized URL path acts as bearer authority. | `ADAPT_IN_EXISTING_OWNER` | Existing app edge, Secure MCP Tunnel or approved authenticated public HTTPS resource | A secret path alone is not the Business OAuth/resource/subject boundary. Use exact app generation, OAuth resource/audience/scope, host/origin/media/body controls, least-privilege host principal and action-time owner checks. |
| 25 | Separate Chrome extension bridge | The browser bridge does not expose file, shell or permission mutation routes and has a different threat model from MCP. | `ADOPT_PATTERN` | Existing Web-Sol extension/native host separation | Preserve separation between page observation/closed browser actuation and worker/Executive tools. Do not merge browser state, session recording and local execution into one bearer surface. |
| 26 | Silent loopback pairing | `/pair` provisions a bearer token to a compatible caller on loopback. The source explicitly acknowledges that any same-user local process can obtain it. Missing Origin is allowed; any `chrome-extension://` Origin is allowed before token auth. | `REJECT_FOR_SECURITY` | No production Mastermind adoption | Do not use as a Chairman/session/worker identity boundary. Existing Web-Sol native host, approved extension identity, RuntimeBinding and exact profile/account owners must remain stronger. A disposable upstream falsifier must run under an isolated OS user with no real account or secrets. |
| 27 | Explicit browser disconnect sentinel | Deliberate user disconnect is distinguished from missing/corrupt secrets so silent provisioning does not immediately undo revocation. | `ADOPT_PATTERN` | Existing app/extension enrollment and revocation owner | Persist explicit revoked/disabled generation state at the owning configuration boundary. Prove reconnect requires current authorized ceremony and cannot be caused by a stale page. |
| 28 | One-shot browser command lease and redemption | A browser-open command is claimed by one page/client; leases are made durable before handing over the text; sent/unresolved boundaries prevent duplicate delivery. | `ADAPT_IN_EXISTING_OWNER` | Existing Web-Sol CR-P1/continuation and Wake owners | Preserve one operation, one exact target, pre-send/attempted/dispatched/sent checkpoints, lost-receipt reconciliation and no second successor. Do not expose arbitrary text/navigation as a generic public action. |
| 29 | Extension page observation plus local tool evidence | The extension watches ChatGPT while the local app records exact tool results; the extension does not execute tools. | `ADAPT_IN_EXISTING_OWNER` | Web-Sol observation, current host-context, GitHub/Attempt evidence | Browser evidence can support health/attribution but cannot become semantic ACK, Job state, source effect or completion. Tool result/effect belongs to the actuator/owner. |
| 30 | Automatic page repair/reload mechanisms | The bridge can queue exact recovery for no-tab, unattributed, assistant-error, silence and Goal cases under different cooldowns. | `DEFER_PENDING_PROOF` | Existing Wake/Web-Sol exact-session recovery | Preserve closed reason vocabulary, exact binding, no newest-tab fallback, material event suppression and explicit unavailable state. A reload is not a retry of the underlying modification. |

### 4.5 Desktop and clipboard

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 31 | Separate read-only Desktop `observe` tool | Supports screen/window/UI inspection and returns bounded screenshots plus opaque state-scoped element references. | `ADAPT_IN_EXISTING_OWNER` | Existing Worker Browser B1 or separately reviewed disposable Desktop worker | Keep ordinary CEO profile free of Desktop. Bind observation to exact disposable profile/window/process generation; never inspect credentials, browser storage, Keychain, account settings or unrelated windows. |
| 32 | Batched Desktop action tool with frame/ref checks | Actions are serialized and can return completed count, routes and failed index. Stale helper generation or reference refuses. | `ADOPT_PATTERN` only inside bounded worker | Existing browser/computer execution profile | Revalidate immediately before each consequential action. Preserve partial effect and no blind replay. One bundle cannot claim atomicity. Final production action needs owner-specific effect reconciliation. |
| 33 | Refusal of browser tab/window/address-bar chords | Certain shortcuts that would alter the browser's broader navigation/session state are blocked. | `ADOPT_PATTERN` | Web-Sol and worker browser/computer policy | Maintain allowlisted semantic actions rather than generic keyboard control for account/session management. Test variants, platform mappings, menu paths and clipboard shortcuts; keystroke blocking alone is not a complete fence. |
| 34 | Clipboard read/write inside the computer tool | Clipboard operations execute in the same serialized action sequence as input. | `REJECT_FOR_SECURITY` by default | Separate capability only if a later exact need is proven | Clipboard is a cross-application secret and ambient-data channel. Keep it disabled for CEO and ordinary workers. Any later use must bind exact content class, source/destination, no secret material, post-action clearing and observation. |
| 35 | Native Windows and macOS backends; Linux Desktop absent | Platform projection removes unsupported Desktop tools; macOS fresh install starts them off and requires OS permissions. | `OBSERVE_UPSTREAM_ONLY` | Existing platform-specific worker/browser owners | Mastermind already has bounded Playwright/worker-browser paths. Native Desktop is a later optional capability after a concrete user journey and disposable-host proof; do not make it a prerequisite for repository work. |

### 4.6 Session recording and local history

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 36 | Durable local conversation/session store | JSONL, message shards and overflow assets retain authored messages and tool activity under local app data. Session recording is enabled on fresh install and not encrypted by `safeStorage`. | `REJECT_AS_DUPLICATE` for company memory; `REJECT_FOR_SECURITY` on real accounts | Agent OS, GitHub evidence, Executive/Dialogue receipts | Do not import a second transcript/memory store. Real-account use would also require a privacy/retention/at-rest-encryption ruling. Mastermind continuation stores decisions/evidence/next action, not full transcripts. |
| 37 | Cross-session search and read tool | A model can search prior/concurrent recordings and retrieve authored history or exact tool details by local session ID/cursor. | `REJECT_AS_DUPLICATE` for organizational use | Existing Agent OS/Steward/GitHub/Dialogue reads | Do not give one chat broad local transcript search. It crosses role/privacy boundaries, promotes retrieved instructions, and can conflict with canonical state. If used in a disposable upstream study, synthetic sessions only. |
| 38 | Retention sweep and protected active-session exceptions | Default retention is time-bounded and active/worker/continuation sessions can be retained. | `OBSERVE_UPSTREAM_ONLY` | Existing durable owners' own retention policies | A local retention policy does not solve organizational authority, legal/privacy classification or canonical closeout. Do not add another retention scheduler. |
| 39 | Exact attribution or Unattributed stream | Tool activity with no proven conversation is stored separately rather than guessed into the most recent chat. | `ADOPT_PATTERN` | Existing audit/evidence projection | Preserve uncertainty. An unattributed event may trigger diagnosis but cannot create source ownership, Job progress, worker completion or retry authority. |
| 40 | Complete overflow assets behind bounded inline summaries | Large redacted messages/results spill into referenced local assets so inline truncation does not imply loss. | `ADAPT_IN_EXISTING_OWNER` | Existing GitHub artifacts, Attempt evidence and proof packets | Use immutable, access-controlled evidence artifacts already owned by the operation. Do not create a second asset store inside a Chat plugin. Preserve truncation/loss explicitly and enforce secret/private-data policy. |

### 4.7 Continuation and context rotation

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 41 | Local session identity survives frontend chat A→B | A local session is the durable identity; source/destination ChatGPT conversations are replaceable attachments. | `REJECT_AS_DUPLICATE` as authority; `ADOPT_PATTERN` conceptually | Existing logical responsibility plus RuntimeBinding generation | The durable identity is Mastermind responsibility/Job/Attempt as applicable, not an upstream local session. Conversation replacement must use existing Agent OS continuation and RuntimeBinding succession. |
| 42 | Explicit continuation phases and send checkpoints | Open, summary, claim, commit and abort; source and destination sends distinguish not-attempted, attempted-unresolved, dispatched-unresolved and sent. | `ADOPT_PATTERN` | Existing Web-Sol CR ladder and effect reconciliation | Preserve exact effect truth, one candidate, one claimant, one bootstrap, no blind duplicate and post-cutover predecessor fence. Use canonical owner readback, not local app state, for company authority. |
| 43 | Atomic local session rebind with stale predecessor suppression | Commit moves the local session and workspace to the successor; late old-page observations do not mint a new session. | `ADAPT_IN_EXISTING_OWNER` | RuntimeBinding writer / Web-Sol / Agent OS | Require semantic readiness, CAS/ABA-safe generation N→N+1, exact same profile/Project, predecessor fence and independent all-mutator coverage. Navigation is a projection, not authority. |
| 44 | Model-generated 10k–30k handoff brief | The compaction prompt asks for specification, state, completed/current/planned work, failed approaches, files, verification, environment, next steps and prohibitions. | `ADAPT_IN_EXISTING_OWNER` | Agent OS handoff and long-run leader context composition | Adopt the section coverage and claims-versus-evidence discipline. Do not treat a giant model brief as canonical state, require the dying chat to produce it, or preserve hidden reasoning/full transcript. |
| 45 | Token estimate and automatic compaction threshold | Local estimates trigger app/browser continuation when a working chat crosses configured levels. | `DEFER_PENDING_PROOF` | Existing closed rotation classifier | Context pressure may inform `ROTATION_SUSPECTED`, never prove provider context exhaustion or grant successor authority. Require closed reasons, effect fence and exact succession. |
| 46 | Worker chats never auto-compact | Worker identity is bound to its conversation in the upstream broker, so automatic compaction is disabled to avoid stranding it. | `OBSERVE_UPSTREAM_ONLY` | Existing provider continuation / Attempt ownership | Mastermind should permit only owner-supported exact worker continuation. A provider session may be sticky; a replacement worker requires canonical reconciliation. Do not infer a universal “workers never rotate” rule. |

### 4.8 Multi-agent broker and worker revival

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 47 | Independent prime/worker broker | Owns one active run, agent slots, queues, leases, sleeping workers, message routing, context ceilings and durable recovery. | `REJECT_AS_DUPLICATE` | Executive OS, Capacity, RuntimeBinding, Dialogue, Agent OS | Do not import or wrap it as another agent fleet. Any upstream worker study must run isolated with no Mastermind lifecycle claims. |
| 48 | Exact conversation is agent identity | The broker binds worker/prime roles to ChatGPT conversation IDs and can persist them. | `REJECT_AS_DUPLICATE` | Existing responsibility and RuntimeBinding identities | A conversation is a rotating surface, not the durable executive/worker identity. Do not let browser identity elect organizational role or authority. |
| 49 | Sleeping reusable worker and explicit revival | Workers may sleep after finish and receive later messages; app opens/reuses the exact conversation rather than spawning by default. | `ADAPT_IN_EXISTING_OWNER` | Existing provider-thread continuation, Capacity and Wake | Reuse a worker only when its canonical Attempt/provider/thread obligations permit it. A terminal STOP consumes the child. Old provider context cannot self-authorize another operation. |
| 50 | Global one-active-run claim | One executing swarm holds app-wide ownership; other runs park. | `REJECT_AS_DUPLICATE` | Existing Executive atomic claim and Capacity | Do not create an app-wide run mutex outside Executive OS. Preserve per-operation ownership, capacity backpressure and independent disjoint work. |
| 51 | Bounded worker count and context ceiling | Fresh multi-agent uses two workers with hard max eight; terminal context-ceiling workers are replaced. | `OBSERVE_UPSTREAM_ONLY` | Capacity and provider-control owners | Numerical bounds require measured host/provider/review capacity. Do not inherit 2/8/400k as Mastermind constants or equate advertised context with safe execution. |

### 4.9 Goal, Loop, and second-model continuation

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 52 | Goal mode | An external model receives bounded user messages and final assistant answers, then drafts the next message or stops. It does not receive full tool results/files. | `REJECT_FOR_SECURITY` as completion/authority | At most an optional advisory planning aid after data-egress approval | Omitted tool/effect evidence makes it unsuitable for canonical completion, retry, acceptance or continuation. Any advisory text is untrusted model output and must pass current owner gates. |
| 53 | Loop mode | The controller can keep drafting follow-up prompts without a declared terminal objective. | `REJECT_FOR_SECURITY` for Mastermind autonomous operation | None on critical path | It incentivizes activity over outcome, can spend usage/cost indefinitely, and lacks canonical proof. Use material-event continuation and bounded mission/stop conditions instead. |
| 54 | OpenRouter side-model dependency | Requires a separate key/provider/model and sends selected conversation content externally. | `DEFER_PENDING_PROOF` only for synthetic research | No default Mastermind dependency | Requires data classification, vendor/legal/security review, hard budget, exact payload audit and explicit bounded purpose. It cannot become a silent supervisor over included Chat reasoning. |
| 55 | Goal acts only on completed final answers and is fenced from worker chats | The implementation avoids two simultaneous authors on a worker and uses page terminal signals. | `ADOPT_PATTERN` conceptually | Existing one-parent/one-carrier Dialogue and material-return law | Exactly one action-authoritative parent writes the next semantic edge. Browser completion evidence still does not equal accepted RESULT or company completion. |

### 4.10 Durable local state, updates, packaging, and tunnels

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 56 | Small named JSON durable state files | Correlation, continuation, worker and command state is written under app data with serialized/coalesced updates. | `REJECT_AS_DUPLICATE` for company runtime | Existing Executive/Agent OS/RuntimeBinding/Wake owners | Do not import state files that become a shadow lifecycle or session registry. A component-local cache is acceptable only when reconstructible, non-authoritative and explicitly owned. |
| 57 | Updater checks upstream and stages releases | Windows/AppImage update path polls GitHub periodically and stages a downloaded release for later install. | `REJECT_FOR_SECURITY` for Mastermind real fleet | Existing reviewed release/deployment owner | No moving-latest download/install on real accounts. Require immutable source/artifact identity, SBOM, signatures or equivalent provenance, current review, staged canary, rollback and exact host inventory. |
| 58 | Unsigned Windows installers and unsigned/unnotarized macOS builds | Packaging config intentionally disables macOS identity/notarization; release artifacts have no publisher trust chain. | `REJECT_FOR_SECURITY` for direct production install | Source-pinned self-build disposable falsifier only | Do not bypass Gatekeeper or install on real account hosts. A later vendor artifact path requires accepted signing/provenance and dependency review. |
| 59 | Linux AppImage fallback may use `--no-sandbox` | Release smoke explicitly tests a launcher fallback where namespace setup is unavailable. | `REJECT_FOR_SECURITY` for sensitive deployment | None | Do not run a browser/Electron control application without its expected sandbox on a real account host. Disposable research must record the exact sandbox state. |
| 60 | OpenAI Secure MCP Tunnel adapter | Outbound-only tunnel makes the local MCP server reachable and monitors control-plane health. | `ADAPT_IN_EXISTING_OWNER` | Existing approved BSC/private-network transport owner when selected | Tunnel is transport, not identity or authorization. Preserve exact app/OAuth/subject/resource scopes, secret handling, immutable generation and health proof. Current first Business canary may use the accepted public-HTTPS path instead. |
| 61 | Cloudflared quick tunnel with secret URL path | Creates a public URL whose path token is treated as the primary secrecy boundary. | `REJECT_FOR_SECURITY` for production | Disposable synthetic falsifier only, if needed | A secret path is not sufficient for company reads/actions. Do not expose real local filesystem, session, shell, or account data through it. |
| 62 | Release CI builds and native-smokes six OS/architecture artifacts | Workflow uses pinned actions, `npm ci`, verification, packaging and platform-specific smoke checks. | `ADOPT_PATTERN` for supply-chain rigor, not artifact trust | Existing release-artifact and CI owners | Reproduce the exact source, dependency lock, native closure, SBOM/license inventory and clean-build proof. CI success does not overcome unsigned artifact or application-security boundaries. |

### 4.11 Defaults and operational metrics

| # | Upstream mechanism | Finding at audit pin | Verdict | Mastermind destination | Required proof / retained boundary |
|---:|---|---|---|---|---|
| 63 | Broad fresh-install capabilities | Fresh install enables all Core permissions, read-write mode, recording, automatic compaction and multi-agent; zero approved roots prevent immediate root-requiring publication. Desktop is platform-dependent. | `REJECT_FOR_SECURITY` as Mastermind default | Existing explicit capability profiles | Start with zero-write, zero-recording, zero-Desktop, no Goal/Loop, no agent broker and synthetic roots. Enable one capability per approved falsifier. |
| 64 | Corrupt-config fallback is conservative | Invalid existing configuration falls back to safer migration defaults rather than silently restoring broad first-launch values. | `ADOPT_PATTERN` | Existing immutable app/profile generations | Fail closed on invalid config, preserve last-known accepted generation only where current law allows, and surface degraded state. Never “repair” by broadening permission. |
| 65 | Historical tool-error classification | In one snapshot, many nonzero terminal results were expected RED validation; remaining failures exposed command UX problems. The report projected, rather than claimed, improvement. | `ADOPT_PATTERN` | Existing evaluation/observability owner | Distinguish expected RED, protective refusal, operator/input error, transport failure, unknown effect, product defect and success. A zero-error target would reward weaker tests and hidden failures. |
| 66 | Internal source/document drift | Current implementation differs from older comments/docs on platform support, tool counts, defaults, timings and continuation details. | `ADOPT_PATTERN` as audit warning | Every external component integration | Pin exact commit, derive capabilities from implementation/schema, run client/host tests, and record the observed generation. Never implement from a blog/README summary alone. |

---

## 5. Net adoption map by Mastermind owner

### 5.1 Code Intelligence Fabric

Adopt or preserve:

- bounded batch reads and exact result coverage;
- honest negative-search completeness;
- task-relevant progressive disclosure;
- exact request/worktree attribution;
- familiar read/search semantics and bounded continuation.

Do not absorb:

- Chat On Steroids' conversation workspace map as the canonical worktree;
- its local session history as code truth;
- its upstream worker broker;
- a direct third-party semantic backend without the stable Mastermind facade.

Current CodeIntel B0/C0/Z0 children retain their exact existing branches, worktrees, carriers, effects and proof gates. This ledger is a dependency map, not reassignment.

### 5.2 Executive worker profiles and provider adapters

Adopt or preserve:

- exact process ownership and durable command handles;
- bounded output deltas and terminal/unread-result attention;
- positive closed environment and no ambient credential inheritance;
- exact Attempt/workspace/process-generation binding;
- no blind second launch after lost response;
- partial effect, cancellation and cleanup receipts.

Do not expose:

- unrestricted shell or arbitrary environment to leadership chats;
- anonymous process continuation;
- a process manager that becomes another Job/Attempt database.

Current protected `config/executive_agent_capabilities.json` already defines sealed read-only and workspace-write profiles, a dedicated worker auth realm, network-disabled defaults, and a loopback-only browser-review profile with `production_armed=false`. Extend those owners rather than installing the upstream default app.

### 5.3 Worker Browser B1 and later computer use

Adopt or preserve:

- observe-before-action;
- state-scoped refs and screenshots;
- serialized action execution;
- completed-count/failed-index evidence;
- exact process/profile/runtime generation;
- external-egress falsifiers and cleanup proof;
- fixed viewport/artifact evidence.

Current Worker Browser B1 already provides a more Mastermind-aligned bounded Playwright resource for exact loopback product review. Native whole-desktop control is later and optional. It needs one independently useful journey that cannot be served by the existing browser worker, plus disposable-host proof and a narrower action schema.

### 5.4 Web-Sol, RuntimeBinding, Wake, and context succession

Adopt or preserve:

- exact command/page claims;
- durable pre-send/attempt/dispatched/sent effect checkpoints;
- one claimant and one candidate;
- no title/timing/newest-tab authority;
- stale predecessor suppression;
- explicit failed/unknown recovery states.

Do not adopt:

- upstream local session ID as durable Sol identity;
- arbitrary new-chat typing, generic browser commands or transcript export;
- silent loopback pairing as exact session authorization;
- upstream compaction state as a second RuntimeBinding store;
- a worker/prime broker as Capacity or Wake.

The current closed Web-Sol protocol remains INSPECT/FOREGROUND. Successor creation/bootstrap/verification belongs only to its separately reviewed CR ladder. Semantic readiness and RuntimeBinding transfer remain separate from visible model output.

### 5.5 BSC plugin, Steward, Executive, and Dialogue apps

Adopt or preserve:

- one coherent plugin experience with separate app generations;
- current protected Skillpack retrieval instead of stale static authority;
- small task-relevant tool families;
- immutable schema/app generation and invocation-time authorization;
- bounded results with explicit source/freshness/degraded states;
- exact user/resource/scope and trusted host-derived action context.

Do not add:

- `.mcp.json` to the web package merely because the endpoint is remote;
- broad local tools to Steward or Executive;
- one super-MCP mixing company reads, CEO admission, worker dialogue, GitHub, filesystem, browser and admin;
- full session recordings or live workstream state in plugin files;
- a generic Slack or GitHub writer as a substitute for exact company action semantics.

Current S1 and U1 operations remain on their existing carriers and owners. The current S1 ruling preserves a truthful partial read slice and does not authorize this research branch to modify #463.

### 5.6 Agent OS and long-run context

Adopt the upstream handoff **section coverage**, not its local transcript/session store:

- original user and machine outcome;
- accepted state and current capability ledger;
- completed/current/planned work;
- failed approaches and why;
- exact source, evidence, environment and effect state;
- unresolved risks and next action;
- explicit do-not-redo boundaries.

Store only durable decisions, discoveries and handoffs in Agent OS; implementation/evidence in GitHub; lifecycle in Executive OS. A context bundle is an ephemeral composition over those owners and may be rebuilt from references after a chat is dead.

---

## 6. Disposable upstream falsifier plan

A later upstream runtime test is useful only as a **source-pinned comparative falsifier**, not as the Mastermind implementation path. It requires a separate explicit effect-authorized child. This section does not commission it.

### Stage COS-D0 — static supply-chain preparation

- Pin the exact audited commit or a separately reviewed newer commit.
- Build from source in a clean disposable checkout; do not download a moving-latest binary.
- Record repository/commit/tree, lockfile digest, dependency inventory, native binaries, extension digest, license notices, build commands and artifact digest.
- Scan dependency scripts, packaged resources, network/tunnel binaries, unsigned status and platform sandbox behavior.
- Keep the original MIT notice in any copied substantial source or distributed derivative.
- No connection to a real ChatGPT account, Mastermind repository credentials, user home directory, browser profile, Slack, GitHub, Linear, Agent OS, Executive OS, market data, SSH, Keychain or deployment credentials.

### Stage COS-D1 — isolated read-only local tools

Environment:

```text
disposable VM or isolated OS user
synthetic repository only
no real browser account
no tunnel
recording off
multi-agent off
Goal off
Loop off
automatic compaction off
Desktop off
edit off
command execution off
one synthetic approved root
```

Proof:

- exact package/extension versions and capability projection;
- no Core publication before an approved root when required;
- batched read, binary/image refusal, truncation and search coverage;
- symlink/root-replacement/path escape denial;
- no access outside the synthetic root;
- no session store or network/tunnel process when disabled;
- complete cleanup and snapshot comparison after uninstall.

### Stage COS-D2 — isolated patch behavior

Enable only file edit on a disposable synthetic repository.

Proof:

- exact preimage and path scope;
- successful single-file and multi-file staged patch;
- stale expected-text zero-effect refusal;
- induced commit-time failure and exact rollback result;
- concurrent third-party edit remains untouched and rollback is reported incomplete;
- no claim of ACID atomicity;
- source diff, process and filesystem residue inventory.

### Stage COS-D3 — isolated shell behavior

Enable command execution only after entering an OS/container sandbox with a positive environment allowlist and no network or credentials.

Proof:

- process begins in expected workdir but cannot escape the actual OS boundary;
- inherited environment contains only the approved allowlist;
- process/session ownership cannot cross exact callers;
- lost start response creates no second process;
- output deltas, unread terminal result and unattended live process behavior;
- cancellation request versus confirmed termination;
- process group/child cleanup and no survivors.

The upstream logged-in-user shell is not accepted as Mastermind production isolation even if these synthetic tests pass.

### Stage COS-D4 — extension/identity mechanics without a real account

Use a local synthetic extension harness or disposable account specifically approved for this stage.

Proof:

- exact request-ID correlation and first-proof-wins behavior;
- wrong conversation cannot steal a proven request;
- missing identity refuses relative path and all modifying tools;
- silent loopback pairing threat is reproduced and documented under the isolated OS user;
- disconnect survives restart and requires explicit approved re-enrollment;
- one-shot browser command is not delivered twice after lease/send uncertainty;
- no arbitrary file/shell route exists on the bridge.

No real Mastermind account is introduced at this stage.

### Stage COS-D5 — Desktop comparative test

Only if Worker Browser B1 cannot serve an independently useful journey.

- Use a disposable local application and disposable browser profile.
- No credential, account, settings, clipboard, email, or personal windows.
- Prove stale frame/ref refusal, wrong-window refusal, action partial-completion evidence, focus changes, screenshot bounds, helper restart, and cleanup.
- Keep clipboard disabled unless a separate exact test requires it.
- Compare reliability, token cost, artifact quality and security with existing Worker Browser B1.

### Stage COS-D6 — decision

The result may support only one of:

```text
NO_PORT_NEEDED
PORT_NARROW_PATTERN_TO_EXISTING_OWNER
CONTINUE_DISPOSABLE_EVALUATION
REJECT_COMPONENT
```

It cannot establish production readiness, authorize a real account installation, or replace the existing Mastermind owner.

---

## 7. Threat and failure matrix for any adapted component

| Threat/failure | Required behavior |
|---|---|
| Tool schema cached after permission revocation | Invocation-time owner refuses with current capability generation; no effect. |
| Wrong or unknown conversation/Attempt | Refuse all modifying operations; retain diagnostic uncertainty without guessing. |
| Same-user local process reaches bridge pairing | This must not be the Mastermind identity boundary. Isolate or replace with approved native/app identity. |
| Hostile repository/Slack/page text asks for authority | Treat as data; preserve current system/Chairman/source gates. |
| Symlink, root swap, mount or junction escape | Refuse before read/write or return exact effect uncertainty if the identity changed mid-operation. |
| Shell sees ambient credential | Fail the worker profile; no command result can compensate. Rotate exposed secrets if a canary ever leaks one. |
| Process start response lost | Reconcile the original process/Attempt; never launch a replacement blindly. |
| Patch commit partially applies | Report exact path post-images and rollback state; no false no-effect or atomicity claim. |
| Desktop action batch fails after earlier inputs | Return completed steps/routes and failed index; no replay of the whole batch. |
| Browser/profile/account target changes | Refuse and re-resolve through the exact owner; no title/newest-tab fallback. |
| Recorded transcript contains sensitive data | Mastermind default is no upstream recording on real accounts. Disposable tests use synthetic data and destroy evidence under approved retention. |
| Large result omits effect/blocker/correction | Preserve decisive fields or return explicit truncation/evidence reference/refusal. |
| Continuation create/send response lost | Effect unknown; inspect the exact target and do not create/send another candidate. |
| Old predecessor produces text after cutover | Text is non-authoritative; all claimed modifying paths must deny the stale generation. |
| Native GitHub/Slack/Linear remains writable by predecessor | Exclude from unattended claim, technically restrict it, or keep it attended; internal RuntimeBinding fence alone is insufficient. |
| Goal/Loop says work is complete | Advisory model output only; canonical evidence and Sol acceptance remain required. |
| Updater downloads a new release | Disabled in disposable pin; production uses approved immutable release owner only. |
| Tunnel is connected but identity/authorization is absent | Connection is transport only; refuse all protected data/action. |
| Platform/docs drift | Re-pin code/schema/client/host and rerun discriminating compatibility tests. |

---

## 8. Prioritized implementation order inside existing owners

These priorities describe where accepted patterns would create value. They are not implementation commissions.

### P0 — safe read and evidence ergonomics

1. Complete the existing Business Steward partial source correction/review and the current U1 source operation.
2. Prove one useful authenticated read with initial/post-expiry/rollback evidence.
3. Improve existing plugin/context discovery using bounded owner-attributed results and progressive disclosure.
4. Preserve exact coverage/freshness/truncation and unmatched source disagreements.
5. Measure baseline and candidate tool/discovery/repeated-evidence cost.

### P1 — exact-bound worker workbench

1. Extend current sealed worker profiles, not CEO apps.
2. Compose CodeIntel exact-worktree read, bounded image/artifact read, source patch and provider process handles through current Job/Attempt/Worker identity.
3. Use positive environment, explicit network policy, exact worktree/path ceiling, process-group cleanup and Source Continuity.
4. Prove one read-only investigation, then one patch/test vertical with explicit parent adjudication.
5. Keep whole-desktop and arbitrary browser control out of this stage.

### P2 — material return and continuation

1. Coalesce material worker events into existing Dialogue/Wake.
2. Resume the exact parent or expose exact-session wake unavailable.
3. Preserve explicit parent `CONTINUE`, `REQUEST_REPAIR`, or terminal `STOP` after every return.
4. Prove dead-parent durable recovery and one exact context succession through the current CR ladder.
5. Add all-reachable-mutator coverage before claiming unattended stale-session fencing.

### P3 — optional native Desktop

Proceed only when a named product/operations journey cannot be completed by Worker Browser B1, provider-native browser automation, or closed Web-Sol actions. Build a narrow task-specific capability, not a generic CEO desktop. Require disposable-host proof, no secrets, current window/profile identity, per-action effect evidence and exact cleanup.

### Rejected/deferred

- upstream prime/worker broker;
- upstream durable session/transcript memory as company state;
- Goal/Loop as completion or automatic next-turn authority;
- silent loopback pairing as production identity;
- public quick tunnel plus secret path as company authorization;
- unsigned moving-latest production installation;
- direct logged-in-user shell on a real account host;
- fleet-wide use before matched evaluation and production acceptance.

---

## 9. Acceptance gates before any real-account installation

A real-account installation of any derived or upstream component remains forbidden until all applicable gates are independently satisfied:

1. **Outcome gate:** a concrete user/machine journey requires the component and existing safer capabilities are insufficient.
2. **Owner gate:** the component extends one named existing Mastermind owner and creates no parallel lifecycle/state/identity/retry plane.
3. **Source gate:** exact repository/commit/tree/dependency/native-binary/SBOM/license/artifact identities are reviewed.
4. **Signature/provenance gate:** release trust is independently established; unsigned moving-latest artifacts are ineligible.
5. **Host isolation gate:** exact OS user, sandbox, worktree/root, environment, network, process and credential boundaries are proven.
6. **Account/profile gate:** exact disposable profile first; real account only under a separate current ceremony and rollback.
7. **Tool gate:** closed tool census, schema generation, permission enforcement, output bounds and secret/path sanitization.
8. **Identity gate:** exact caller/Attempt/binding evidence; no timing/title/active-tab/only-chat fallback.
9. **Effect gate:** start/send/patch/action/cancel/stop ambiguity is reconcilable without blind retry.
10. **Continuation gate:** the component cannot create a second responsibility, worker, successor, or retry owner.
11. **Privacy gate:** recording/search/clipboard/screenshots/data egress are disabled or separately accepted with retention/destruction proof.
12. **Production proof gate:** exact installed generation through the real consumer, adverse cases, rollback and monitoring.
13. **Authority coverage gate:** every modifying route included in the autonomous claim is enforced or technically denied.
14. **Evaluation gate:** no safety regression and measurable user/recovery/evidence value versus the existing path.
15. **Closeout gate:** Agent OS/GitHub/Linear/Slack projections reflect only what the evidence proves.

No single green CI run, source merge, packaged binary, plugin import, tunnel health result, visible chat response, or successful synthetic call satisfies these gates collectively.

---

## 10. Current collision and non-takeover boundary

At this research window:

- protected Mastermind is `c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36`;
- PR #490 is the sole research publication carrier for this investigation;
- the S1 source operation `business-sol-steward-s1-v2-repo-successor-20260904-sol-001` remains bound to PR #463, issue #458, exact Slack root `C0BSBM78V1N/1788508146.063109`, and its existing Codex task/watcher;
- the current Sol ruling adopts truthful partial product disposition and does not widen that worker into producer owners;
- the U1 source operation `business-sol-u1-installation-binding-compiler-20260904-sol-001` remains bound to root `C0BSBM78V1N/1788508195.214199`, its incumbent source owner and reserved branch;
- CodeIntel B0/C0/Z0 remain active on their existing sticky carriers;
- existing Web-Sol, Worker Browser, SCF, Executive, Dialogue, Steward, Agent OS, RuntimeBinding and Wake owners remain authoritative for their domains.

This ledger creates no receiver assignment, child START, watcher, review request, source lease, release window, installation, endpoint, credential, account/profile action or production effect.

---

## 11. Exact next action

The near-term product action remains unchanged:

> Finish the current S1 truthful partial-source return and exact-head review on its existing carrier, finish the active U1 source publication through its incumbent owner, then conduct the separately authorized one-cockpit authenticated Steward read, post-expiry refresh, and rollback canary.

This selective-reuse ledger should receive architecture/security review together with the parent runtime-profile plan. Any accepted P0/P1/P2 pattern must then be attached to its current existing owner and separately commissioned as one independently useful vertical. Do not install upstream on a real account as a shortcut around those gates.

---

## 12. Immutable source references

### Chat On Steroids at `dbff15b7296358102ee3e141f183e89a4a8d1e0e`

- `AGENTS.md` — runtime planes, authority map, identity boundaries, fresh-install defaults and documented drift.
- `README.md` and `SECURITY.md` — product claims, user-visible setup, explicit shell/recording/release limitations.
- `src/main/mcp/surfaces.ts`, `tools-core.ts`, `tools-desktop.ts`, `server.ts`, `instructions.ts`, `session-tool.ts`.
- `src/main/sandbox.ts`, `fsops.ts`, `exec.ts`, `workspace.ts`.
- `src/main/codex/ownership.ts`.
- `src/main/session/store.ts`, `recorder.ts`, `correlation.ts`, `retention.ts`, `continuation.ts`, `handoff-prompt.ts`.
- `src/main/agents.ts`, `goal.ts`, `bridge.ts`, `durable.ts`, `update.ts`.
- `src/main/tunnel/index.ts`.
- `extension/manifest.json`, `electron-builder.yml`, `.github/workflows/release.yml`, `package.json`.
- `docs/tool-error-rate-2026-08-24.md`.
- `LICENSE`, blob `4863f21719abdc21a635c77b9230c9e734a419a1`.

### Mastermind at protected `c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36`

- `docs/sol_skills/INDEX.md`, `COLD_START.md`, `RECONCILE_STATE.md`, `CLOSEOUT.md`.
- `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md`.
- `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`.
- `integrations/chairman_surfaces/web_sol_protocol.py`.
- `control_plane/worker_browser_b1.py`.
- `config/executive_agent_capabilities.json`.
- existing BSC, SCF, CodeIntel, Executive, Company Dialogue, Steward, RuntimeBinding, Wake and Agent OS sources referenced in the preceding PR #490 research documents.
