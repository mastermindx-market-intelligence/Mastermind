# COO Principal Mandate V1 — broad principal autonomy over bounded Executive effects

**Date:** 2026-09-24  
**Operation:** `coo-principal-mandate-v1-20260924-sol-001`  
**Status:** **SPEC_ONLY / SOURCE-CONTRACT CANDIDATE / PRODUCTION INERT**  
**Protected basis:** Mastermind `ed678f27466392bc53cc03f584f91e4f3adf3aa3`, Skillpack `mastermind.sol_skillpack.v1` 1.0.1  
**Initial target:** Fable as the logical COO principal in Claude Code / Claude Desktop  
**Existing owners preserved:** Agent OS organizational continuity; Executive OS Job/Attempt/effect lifecycle; Capacity/Model Router concrete placement; GitHub/source owners; Business MCP OAuth; Workspace/Workbench scope; current release/proof owners.

## 1. Outcome

The target is not a safer chat assistant. It is a principal that can take one accepted Mastermind project from outcome to accepted completion without routine prompt carriage, preference questions, or repeated Sol/Chairman approval.

Fable does **not** become the CEO seat. The distinction is constitutional scope, not day-to-day competence.

Within one accepted mission, the default is:

```text
observe -> decide -> act -> verify -> repair/replan -> continue
```

not:

```text
observe -> ask Sol which reversible option to choose
```

The governing model is:

> **unbounded program judgment over bounded, receipt-backed concrete effects**

## 2. Worker ceilings are not principal ceilings

The existing `executive_worker_policy` remains the worker capability ceiling. Its denial of `OPEN_PR`, `PUSH_BRANCH`, `MERGE`, `DEPLOY`, `SERVICE_CONTROL`, credential administration and other effects must not be reinterpreted as a principal-COO authority map.

Likewise, `coo_cycle_policy` bounds one deterministic Executive cycle. Its current fan-out/depth/child ceilings do **not** cap the total scale of a Fable-owned programme.

A large programme composes as:

```text
Agent OS workstream / durable outcome
        |
        v
logical COO responsibility (Fable)
        |
        +--> finite Executive root episode A
        |       plan -> work -> review -> repair -> aggregate
        |
        +--> finite Executive root episode B
        |       ...
        |
        +--> finite Executive root episode N
                ...
```

Successor roots remain ordinary Executive roots. No `fable_jobs`, Fable queue, Fable retry state, provider transcript database, or second lifecycle is created.

## 3. Provider-neutral principal contract

The contract is **COO Principal Mandate**, not a Fable-specific prompt contract. Fable is the first qualified consumer.

Portable leadership behavior follows the existing provider-neutral method and current commission/source law. Provider/model-specific adapters transport the principal; they do not define its authority.

A sealed worker profile and a rich principal profile remain separate. A rich principal may deliberately carry reviewed Skills, MCP servers, plugins, browser/design/research surfaces and subordinate helpers when its capability package admits them. Ambient user-home capability is never authority merely because Claude can see it.

## 4. Mandate is a projection, never a durable authority store

`mastermind.coo_principal_mandate.v1` is a server-derived, request-fresh projection over existing owners.

It must derive at least these facts:

```text
principal
  OAuth resource policy
  subject_digest
  client_ref
  exact scopes
  installed principal-binding receipt

mission
  work_ref
  root_job_id when one exists
  outcome/authority reference
  authority generation
  accountable seat
  current owed seat
  completion/proof contract references

continuity
  current logical COO responsibility
  current RuntimeBinding/continuation facts when available
  current effect state
  current source/lease collisions

capability
  reviewed principal capability package/profile
  exact tool/MCP/plugin grants
  source/workspace grant
  economic/spend envelope
  concrete Capacity eligibility is read from the existing Capacity owner

release
  release class
  required source custody / review / CI / proof gates
```

There is no `fable_mandates` table, file, cache, queue, token store or session database. A tool response may display the derived document, but every modifying operation re-reads the applicable owners immediately before effect.

## 5. Principal identity: what is proved and what is not

Business MCP OAuth already yields a verified pseudonymous principal including `subject_digest`, `client_ref`, resource and scopes. Installed Workspace authorization already demonstrates exact sealed principal bindings over the same kind of tuple.

Use that pattern to enroll a COO-capable Claude client without accepting a caller-provided `actor`, `seat`, account name, model name or chat title as authority.

A modifying COO operation requires:

```text
verified OAuth principal
AND installed COO principal binding
AND current mission authority
AND current effect/source-custody safety
```

### Exact Claude conversation binding is NOT assumed

Current MCP protocol identity is insufficient for exact conversation authority. Modern MCP is stateless and client information is implementation metadata, not a security credential. Surface bindings are also explicitly navigation-only in Mastermind.

Claude Code hooks do expose a provider session identifier (`session_id`) and SessionStart can establish session-local environment/context. This is a promising **future binding input**, not accepted authority by itself.

Before claiming exact-conversation mutation isolation, a native falsifier must prove a local binding path that:

1. receives the real Claude Code hook `session_id` outside model control;
2. binds it to the exact current COO responsibility/mission;
3. survives context compaction/restart only under accepted continuation law;
4. reaches the modifying Executive request through a trusted non-model-controlled channel;
5. refuses a sibling Claude conversation authenticated as the same human/client;
6. creates no second identity/session lifecycle.

Until that proof exists, the honest V1 ceiling is **authenticated COO principal + current mission grant**, not “cryptographically exact Claude conversation.”

## 6. Standing in-mission COO rights

Once an authenticated COO principal owns an accepted mission, ordinary reversible judgment is delegated. Fable may decide and continue without another CEO/Chairman approval round for:

- implementation, architecture, product and design choices that preserve the commissioned outcome;
- execution sequencing and replanning;
- splitting, combining, reprioritizing and superseding pre-effect bounded child work;
- originating bounded in-mission Executive work and lawful successor-root episodes;
- commissioning research, implementation, tests, independent review and repair;
- selecting required capability, quality, risk and cost classes; exact provider/account/host placement stays with Capacity/Model Router;
- directly performing principal work when delegation overhead is worse or judgment is inseparable;
- using exact mission-granted GitHub, browser, Figma/design, research, Slack and other reviewed capability packages;
- writing mission branches and source through the existing source/workspace owner;
- pushing mission branches and opening/updating PRs through an approved principal source grant;
- consuming independent reviews and repairing findings;
- updating durable Agent OS decisions/discoveries/handoffs for the programme through the existing knowledge owner;
- completing ordinary source release when the mission carries the release class below and all target gates are satisfied;
- declaring mission completion only when the accepted proof contract is actually met.

“Multiple reversible options exist” is never by itself an escalation condition.

## 7. Release classes

V1 freezes two principal release classes.

### `AUTONOMOUS_SOURCE_RELEASE_WITH_GATES`

Permits normal in-mission source delivery through existing source owners, including branch write/push, PR create/update and merge/release **only after** every applicable source-custody, independent review, required CI/security and declared real-path proof gate is satisfied.

It does not bypass branch protection, reviewer independence, merge queues, release proofs or source leases.

### `RESERVED_RELEASE`

The mission may prepare/review evidence but cannot perform the reserved effect. The named higher authority/admin remains the effect owner.

Reserved by default:

- credential creation/rotation/custody changes;
- new paid-provider/account enrollment and native administrator ceremonies;
- capital execution or financial-book expansion not explicitly predelegated;
- destructive data operations;
- security-boundary weakening;
- authority/governance edits that widen the principal's own power;
- company Charter/north-star/objective-set changes;
- material external/public/customer effects outside the accepted mission envelope;
- spend/risk expansion beyond the accepted economic envelope;
- production/runtime effects explicitly marked reserved by their current release owner.

## 8. Mandatory escalation conditions

Fable escalates only when the next material action requires one of:

```text
OUTCOME_CHANGE
COMPANY_STRATEGY_CHANGE
SELF_AUTHORITY_EXPANSION
HUMAN_OR_ADMIN_CREDENTIAL_CEREMONY
RESERVED_CAPITAL_OR_DESTRUCTIVE_EFFECT
UNDELEGATED_EXTERNAL_PUBLIC_EFFECT
BUDGET_OR_RISK_EXPANSION
EFFECT_UNKNOWN
LIVE_SOURCE_OR_LEASE_CONFLICT
EXPLICIT_RESERVED_RELEASE
MISSING_REQUIRED_PROOF_WITH_NO_IN_SCOPE_RECOVERY
```

A blocker freezes its lane first. Fable continues every path-disjoint action still inside the mandate.

## 9. Authorization semantics — broad mission law, explicit technical capabilities

The principal contract separates **organizational permission** from **technical capability exposure**.

### Organizational decision law

Inside an accepted mission, do not enumerate every ordinary action Fable is allowed to take. That would recreate micromanagement as a permissions schema.

Instead, the organizational rule is:

```text
action preserves accepted mission outcome
AND action is reversible or already covered by the mission's release class
AND action does not cross a closed reserved boundary
AND no current effect/custody conflict makes it unsafe
=> COO may decide and continue
```

This is a broad mission delegation constrained by a small closed reserved-boundary vocabulary. Adding a new reversible implementation technique does not require adding another COO permission token.

### Technical capability law

Concrete execution remains fail-closed:

```text
organizationally permitted action
AND exact reviewed tool/MCP/plugin/source capability is present
AND target owner accepts the current scope/effect
=> executable
```

A rich principal profile therefore uses explicit tool/package grants even though its organizational mission authority is broad. This prevents ambient Claude plugins from becoming authority while avoiding a giant micro-action allowlist.

### The two questions remain separate

```text
MAY Fable make this decision?     -> mission mandate + reserved boundaries
CAN this surface execute it now?  -> capability profile + target owner + current effect state
```

A technical absence does not shrink Fable's organizational mandate; it creates a capability/blocker to solve. Conversely, an available GitHub/Figma/browser/Slack tool never grants a mission action that crosses a reserved boundary.

## 9. Executive plugin surface

Prefer a small semantic surface that composes existing owners rather than exposing Runtime internals.

Target V1 composition:

- `executive_mandate` — read-only derived mandate/current boundary projection;
- existing Executive state/inbox/Workspace mission reads;
- existing `executive_fabric` root/child/result reads;
- `submit_principal_intent` — role-neutral principal admission using the existing high-level request normalization and CeoIngress effect semantics;
- `principal_intent_status` / reconcile — same stable request identity, never blind resubmit;
- `submit_coo_ruling` — only against a current COO-owned decision point, with a closed semantic decision vocabulary.

Do **not** expose raw SQL, generic shell, provider/account binding, worker registration, raw claim/dispatch, `run-coo-cycle`, service control, credential admin or generic governance mutation as model-callable plugin tools.

Routine plan/work/review/repair progression remains Executive COO automation. Fable is invoked for principal judgment, replanning, material exception handling, successor-wave origination and final acceptance.

## 10. Owed-turn behavior

When the current canonical projection says `owed_turn=coo`, the default principal behavior is DECIDE + CONTINUE.

When it says `owed_turn=ceo` or `owed_turn=chairman`, Fable may recommend but must not answer that seat. It continues any path-disjoint work remaining inside its own mandate.

When it says `owed_turn=worker` or deterministic execution can proceed, Fable should not micromanage the worker cycle.

## 11. Direct principal tools and Executive lifecycle

Not every principal tool call must be proxied through Executive OS.

Executive OS remains lifecycle/effect authority for organizational work. Mission-granted provider tools such as GitHub/Figma/browser/Slack may be used directly when:

- the rich-principal capability profile admits the exact package/tool;
- the target system's own permission/source/release controls remain effective;
- the action is inside the current mandate;
- no existing owner requires a more specific effect-safe ingress.

The mandate does not turn external plugins into Executive lifecycle owners.

## 12. Platform falsifiers

The implementation must explicitly test these platform facts rather than assuming them:

1. modern MCP client metadata does not grant conversation identity;
2. Mastermind `surface_bindings` cannot be reused for authority;
3. SessionStart hook input can supply a real Claude `session_id`, but a secure non-model-controlled bridge from that hook to each modifying request must be proven before session isolation is claimed;
4. plugin sync/installation must not widen the effective tool set beyond the reviewed rich-principal profile;
5. a sibling Claude session under the same human account must not be described as isolated unless the session-binding falsifier actually proves refusal.

## 13. End-to-end production acceptance

The decisive canary is a meaningful project, not a tool demo.

One Chairman/Sol assignment occurs once. Fable must then:

1. recover outcome/current durable state;
2. make at least one nontrivial reversible architecture/product judgment without asking;
3. form and revise the plan;
4. originate successive bounded work as needed;
5. route workers through the existing Capacity/Model Router;
6. consume results;
7. commission independent review and repair;
8. advance ordinary source release under `AUTONOMOUS_SOURCE_RELEASE_WITH_GATES`;
9. obtain the declared real-path proof;
10. update durable organizational state;
11. close/return the finished mission.

Acceptance fails if routine preference questions or manual prompt carriage are required.

## 14. Claude packaging boundary

The first production packaging target is one private **Mastermind Executive** Claude plugin/desktop extension, not a public Internet-facing replacement for Executive OS.

Current provider behavior supports this composition:

- Claude plugins may bundle skills, connectors/MCP servers, sub-agents and hooks.
- A plugin enabled for the same Claude account loads into Claude Code on supported current versions; local plugin MCP servers execute on the user's computer.
- Desktop extensions are the provider-supported mechanism for local/private MCP resources and support Node.js, Python and binary servers.
- Remote custom connectors originate from Anthropic's cloud and require a publicly reachable MCP endpoint; do not make the private Executive loopback service public merely for connector parity.
- #955 observed Claude Code 2.1.275, above Anthropic's documented 2.1.273 minimum for Claude-account plugin sync at the time of this spec.

Therefore the intended client composition is:

```text
private Mastermind Executive Claude plugin
  + rich principal skill/method package
  + exact reviewed MCP/tool projection
  + optional hooks whose authority effect is separately proven
        |
        v
local authenticated Executive edge (#955)
        |
        v
existing Executive / Workspace / Fabric owners
```

Plugin installation is capability availability, not mission authority. A Required/default-installed organization plugin must still pass the same exact tool/profile/mandate checks before any modifying effect.

### Provider evidence for the session-binding falsifier

The current MCP 2026-07-28 specification is intentionally stateless: the protocol-level session ID and initialize handshake are removed; client information is request metadata and is not a security identity. Claude Code's official plugin hook-development material documents a `session_id` field on hook input and a `SessionStart` hook that can persist session-local environment/context through `CLAUDE_ENV_FILE`.

These facts establish a viable investigation seam, not the final security design. The implementation must still prove how hook-origin session identity reaches each modifying Executive request without becoming model-controlled or a second session registry.

Provider references (fresh at spec authoring time):
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md
- https://support.claude.com/en/articles/13837440-use-plugins-in-claude
- https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop
- https://support.claude.com/en/articles/11725091-when-to-use-desktop-and-web-connectors

## 14. Non-goals

This wave does not:

- arm production;
- create an Auth0 client;
- change a credential;
- install a plugin;
- mutate Executive Runtime;
- grant a provider realm;
- bypass #955's current Auth0 gate;
- retry or reinterpret another EFFECT_UNKNOWN operation;
- merge #676 or replace its portable-principal/profile work;
- create another scheduler, session registry, identity store, queue, retry engine, memory plane or authority database.

## 16. Dependency relationship

- #955 owns the authenticated Claude client edge.
- #676 is accepted SPEC_ONLY evidence for native Claude parity and the sealed-worker vs rich-principal split.
- current Fable root-seat continuity law owns logical COO responsibility across provider sessions.
- Executive Runtime/COO owns Job/Attempt/effect progression.
- Capacity/Model Router owns exact execution placement.
- Agent OS owns long-horizon workstream continuity.
- Business MCP OAuth and existing sealed binding patterns own principal authentication.
- Workspace/Workbench/GitHub owners retain source/work/release custody.

This contract is additive glue across those owners, not a replacement for any of them.
