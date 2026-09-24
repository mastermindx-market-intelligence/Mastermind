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

### OAuth scope separation from the CEO seat

The initial #955 Claude carrier predates this Chairman clarification and currently documents the existing CEO submit scope. That transport evidence remains useful, but the Fable production enrollment must not inherit `mastermind.executive.intent.submit`.

The final Fable client/profile requires a distinct COO action policy on the same Executive OAuth resource/issuer, conceptually:

```text
mastermind.executive.read
+ mastermind.executive.coo.act
(+ offline_access only as non-authorizing session capability)
```

The exact scope name is frozen only when the role-correct admission implementation is accepted. Do not create an Auth0 scope/client from this SPEC_ONLY document.

CEO and COO clients may share one issuer/resource and signing-key authority. They must remain distinct policy/client bindings, and a token carrying the COO action scope must not pass the CEO submit route or vice versa.

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

## 14. Implementation packet — preserve one mutation sink and one installed service

The first implementation must be additive around the existing Executive owners. Do not fork the CEO request normalizer, clone CeoIngress, or create a second installed Executive MCP daemon.

### P2-A — pure mandate projection

Add a pure `control_plane/coo_principal_mandate.py`-class owner (exact file name may change in implementation review) that reduces already-owner-qualified inputs into `mastermind.coo_principal_mandate.v1`.

It performs no I/O, persistence, OAuth verification, Runtime mutation, placement, GitHub action or provider call.

The projection must distinguish:

- immutable mission/authority identity used for admission;
- current dynamic mission/runtime/effect/capability state used to decide whether an action is safe now.

Dynamic state is **not** a durable grant and must not be copied into a new authority store.

### P2-B — additive principal admission through the existing sink

The existing high-level request normalization and worker execution-profile derivation remain unchanged. `submit_principal_intent` originates bounded Executive work; it does not grant the principal's separate GitHub/source-release powers to worker Jobs.

The current CEO envelope/schemas remain frozen. Do not submit a COO action as a `mastermind.ceo_intent.*` with a misleading CEO actor.

Instead, extend the **existing `ceo_intent.submit_intent` mutation sink** additively with a distinct principal-intent schema/receipt branch, while preserving v1/v2 behavior byte-for-byte. The historical module/sink may retain its name; there is still exactly one Job-creation mutation path and one Executive event store.

The server-derived principal provenance for the COO branch should contain only immutable admission identity, conceptually:

```text
seat = coo
actor = coo-principal
work_ref
principal_binding_digest
mission_authority_ref
authority_generation_digest
```

No raw OAuth subject/client, account label, credential, provider session or model-authored role enters the durable envelope.

**Do not fingerprint current dynamic mandate/runtime state.** A legitimate state change after an accepted submit must not make same-operation reconciliation conflict. Fresh dynamic state is checked before a new effect; immutable authority/binding identity is what belongs in the durable request fingerprint.

Require `workstream` for a COO root/successor-root submission and require exact equality with the current mission authority before effect.

A COO request identity should be separately namespaced from CEO/MCP/Slack identities and bind the logical operation to its mission, e.g. a trusted derivation over `work_ref + operation_key`. It must not depend on token lifetime, OAuth JTI, Claude transcript, provider session, clock or model output.

### P2-C — role-correct ingress on the existing CeoIngress/service

Add a separately versioned principal submit/status frame to the existing CeoIngress contract. Public model input still contains only the normalized high-level request fields. The authenticated App derives the COO seat/principal/mission authority context server-side and carries only the closed trusted projection into the local ingress.

The fresh path order remains:

```text
authenticate exact COO policy/binding
-> normalize caller semantic request
-> resolve immutable mission authority
-> read current effect/source-custody safety
-> observe exact grounding
-> build trusted principal envelope
-> final admission recheck
-> one existing submit_intent sink call
```

If transport becomes ambiguous after send, return EFFECT_UNKNOWN and reconcile the same request identity through the same ingress. Never resubmit through CEO ingress or another carrier.

Durable replay/status resolves the accepted immutable request. It must not be invalidated merely because current dynamic mandate state advanced after the original effect.

### P2-D — one installed process, two static role surfaces

Do not replace the current CEO MCP profile and do not run a second Executive daemon.

Keep the existing CEO `/mcp` contract frozen. Add a separate static COO MCP surface **inside the same installed Executive MCP process/listener** (exact route name may be finalized by implementation review, conceptually `/mcp/coo`).

The COO profile:

- shares the same Executive resource/issuer/JWKS authority;
- authenticates `read + coo.act`, never CEO submit;
- advertises only the COO principal tool set;
- routes reads to the existing Executive/Workspace/Fabric owners;
- routes its one bounded principal admission to the same CeoIngress/Runtime sink;
- has no Runtime, token, retry, session, queue or result store of its own.

The #955 localhost adapter may keep Claude's local resource at its stable `/mcp` URL while translating upstream to the static COO profile. That transport translation does not create authority.

### P2-E — initial COO tool set

First implementation target:

```text
executive_mandate            READ
executive_state              READ
executive_inbox              READ
executive_fabric             READ roots/root/result
submit_principal_intent      MODIFY bounded in-mission/successor work
principal_intent_status      READ/reconcile exact prior request
```

Mission details may be composed from the existing Workspace Mission owner rather than copied into another datastore/tool family.

Do **not** add `submit_coo_ruling` until its exact canonical effect owner is identified. Current repository search shows owed-turn/ruling semantics are projected across Mission/Control Room/dialogue/continuation owners; inventing a generic write now would create a competing dialogue/lifecycle path. The first vertical can still prove broad autonomy through planning, successor work, direct mission-granted source tools, review/repair and gated source release.

### P2-F — direct source/release authority stays outside worker Job authority

The principal mandate may authorize direct mission-scoped GitHub/Workbench effects under their own exact grants. Do not add `OPEN_PR`, `PUSH_BRANCH` or `MERGE` to `executive_worker_policy` merely so Fable can complete projects.

The Executive root records organizational work and evidence. Source owners retain source custody and branch/review/merge protections.

### P2-G — exact-session isolation is a separate falsifier

Do not block broad authenticated principal + mission autonomy on an unproven exact-conversation mechanism.

Ship/accept the principal/mission binding first at its honest ceiling. In parallel, run the hook/session falsifier. Only after it proves a non-model-controlled binding to every modifying request may the mandate add exact Claude-conversation isolation as a required gate.

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

## 16. Exact-session falsifier — optional hardening, not the V1 autonomy gate

Fresh provider evidence makes the possible Claude-session hardening path more concrete, while also showing why it must stay separate from the first production mandate.

Claude Code's official hook contract supplies every hook a real `session_id`. `PreToolUse` runs before a tool call and may return `hookSpecificOutput.updatedInput` to replace fields in the tool request. This is the only current provider-native surface inspected in this design that can both observe the provider's session identity outside the model-authored tool input and modify the exact call before execution.

### F0 candidate

For **modifying COO tools only**, a deterministic plugin `PreToolUse` command hook may:

1. receive the provider hook `session_id`, `tool_name` and `tool_input` on stdin;
2. refuse any unexpected tool/schema shape;
3. remove/overwrite any model-authored session-binding field;
4. inject the hook-observed session identity, or preferably a purpose-bound assertion over it when an already-qualified signing owner exists;
5. return only the updated tool input, never `permissionDecision=allow` as an authority grant.

The Executive server must still perform all normal OAuth, principal-binding, mission-authority, effect/custody and scope checks. Hook output is additional evidence, never a substitute for those owners.

### No suitable signing owner is assumed

Current Mastermind source has stateless HMAC/action-token precedents, notably Workbench Action's `ActionTokenCodec` and its owner-provisioned stable generation key. That key belongs to Workbench Action and must **not** be silently reused for COO session assertions.

The current Executive source audit did not identify an already-approved, purpose-correct principal-session assertion key owner. Therefore this spec does not create a new signing key, key file, credential service or token registry merely to make the session claim look stronger.

If a later hardening wave requires cryptographic session assertions, it must either:
- compose a purpose-separated assertion from an existing owner whose accepted threat model actually covers this use; or
- explicitly review the smallest new local attestation-key custody as its own security boundary.

Neither is required for the first authenticated COO-principal + mission vertical.

### Why MCP environment/session metadata is not enough

Do not use MCP `clientInfo`, Mastermind navigation bindings, or the MCP subprocess environment as the authorization source.

Provider issue evidence has documented a resume case where the stdio MCP subprocess received a `CLAUDE_CODE_SESSION_ID` different from the identifier delivered to hooks/Bash. A resumed-session binding that trusts the MCP environment can therefore bind the wrong conversation even when both values are stable.

The F0 test must use the hook input as the provider-session observation and exercise:
- fresh session;
- `--resume` / resumed session;
- context compaction;
- sibling conversation under the same authenticated human/client;
- plugin reload/restart.

Any mismatch, missing hook evidence, multiple conflicting hook rewrites or unsupported provider behavior refuses the optional session-bound mutation. It never falls back to accepting a model-supplied session id.

### Honest acceptance levels

`COO_PRINCIPAL_MISSION_BOUND`
: OAuth principal + installed COO binding + current mission authority is proven. This is sufficient for the first production autonomy vertical.

`COO_PRINCIPAL_PROVIDER_SESSION_BOUND`
: additionally, the exact installed Claude version proves the deterministic hook path and sibling/resume falsifiers. This is defense-in-depth against the Claude model/session choosing another mission binding.

`COO_PRINCIPAL_CRYPTOGRAPHIC_SESSION_BOUND`
: reserved for a future accepted purpose-bound signer/attestor. Do not use this label merely because a hook supplied a session id.

### Desktop parity remains a real proof obligation

A source-level plugin manifest is not proof that Claude Desktop's Code surface loaded the plugin, hooks and MCP tools. Provider issue history includes version-specific plugin-loading and MCP-registration defects. Production acceptance therefore separately proves the exact installed Claude Code CLI and macOS Desktop Code surfaces, on the versions actually deployed, rather than inheriting one surface's result into the other.

Provider evidence inspected for this section:
- Anthropic Claude Code plugin hook-development contract: `session_id` input and `PreToolUse.updatedInput`;
- Anthropic Claude Code plugin structure: plugin hooks + local MCP auto-start;
- Anthropic issue #64412: resumed stdio MCP `CLAUDE_CODE_SESSION_ID` differed from hook/Bash session identity on the reported version;
- Claude Help: local MCP Desktop Extensions are installed and executed locally.

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
