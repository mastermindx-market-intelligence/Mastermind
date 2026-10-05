# H6 — Canonical company context and commission-scoped reciprocal dialogue

## Outcome and current separation

Claude principals need durable company context and valid reciprocal communication. Agent OS is
the Macro repository's organizational knowledge plane; it is not a scheduler or a source of
self-granted execution permission [S32]. Company Dialogue/Relay owns validated message transport,
while RuntimeBinding/SessionTargetRegistry and existing Wake own exact continuation [S20–S22].

The current Company MCP facade exposes worker-style bound-thread tools [S18–S19]. More importantly,
at the protected source pin, `common/agent_dialogue_contract_v2.py:378–444` permits a COO actor
only the worker-style message set. `integrations/mastermind_company_mcp/adapter.py:129–204`
also rejects non-worker-style allowed-message bindings. These are explicit semantic fences.
A new MCP button alone cannot lawfully make a COO issue CONTINUE/STOP to its children.

## Context workflow: keep Agent OS in Macro

At pickup or recovery, resolve the exact existing workstream and current cumulative checkpoint,
then read relevant decisions/discoveries/handoffs and material invalidators. Preserve source
revision, ownership and disagreement rather than merging contradictory state into a convenient
summary. A file claim or Slack message is evidence, not current source-writer liveness.

Use existing admitted source/context readers. The present one-way boot-packet bridge must remain
one-way [S32]. This audit did not establish a role-correct Claude Agent OS write MCP operation;
do not invent one or make the Executive read bridge write back.

Until an accepted equivalent exists, authorized Agent OS deltas are ordinary scoped changes in
Macro: read its current procedures, acquire the proper source custody, make one bounded DEC/DSC/
handoff change and publish through normal review. Follow that repository's existing record formats
and validators, rather than creating a new Markdown schema in the Claude package. A discovery
needs its actual falsifier and implication; a handoff needs exact effects and next action.

A source branch or draft PR is not yet accepted organizational truth. Distinguish draft delta,
merged canonical record and its projected Linear/Slack state. No runtime lease or job status is
changed by writing a workstream note. Cross-repository permission is explicit; Mastermind source
custody does not grant Macro writes. Do not create a second Agent OS directory in this repository.

## Selected dialogue contract evolution

Extend the **existing neutral dialogue contract and its trusted binding owner** for a narrowly
scoped principal-to-subordinate ruling capability. Preserve worker-to-principal reporting and
all existing roles. Do not globally map `coo` to the CEO message set or rename the actor `ceo`.

The accepted extension must prove, through existing canonical owners:

- the sending principal is the current admitted COO for the exact parent mission/root;
- the target commission/child belongs to that parent and the sender owns the applicable decision;
- the current source/effect/mandate posture permits this specific continuation or terminal ruling;
- the reply lineage and exact channel/thread-root carrier match the bound commission;
- a reserved CEO/Chairman decision is not reclassified as a COO decision.

Keep actor, session, role, child, thread, parent and allowed message types server-derived. The
model may supply bounded ruling semantics, reason and evidence references only. A package setting
cannot make a message type allowed. Use the existing RULING/CONTINUE/STOP body validators and
engine semantics after the accepted contract extension; do not create a parallel frame format.

The binding-owner change must be versioned and synchronized with neutral validation, MCP exposure,
Relay authorization, wake applicability and native profile/schema qualification. Old worker
bindings retain the old restricted tools. Unknown binding versions or unqualified principal-child
relationships fail closed before send. A role-correct principal call should remain in the existing
Company MCP, not a Claude-only service.

## Current staged implementation — H6-A before H6-B

Current protected Mastermind now includes the independently approved/merged #1191 interconnect
repairs: original-parent continuation provenance, a durable pre-COMMIT effect fence, exact
post-effect reconciliation and one Company carrier-composition seam. Those owners remain the
transport/effect substrate; H6 does not rebuild them.

The current #1240 successor source adds **H6-A only** inside
`company_dialogue_runtime_binding.py`:

- a trusted `CooPrincipalDialogueCaller` consumes the existing
  `PrincipalAdmissionContext`, current capability-profile digest, reasoning surface,
  `NewEffectGate`, accountable seat and owed seat;
- `resolve_company_dialogue_principal_binding` joins that principal to one exact current
  subordinate Job/Attempt, parent fingerprint, commission, operation/session identity, thread,
  reply target, Company Dialogue attestation, target execution profile and RuntimeBinding
  generation;
- only an OPEN current new-effect gate with COO accountability/turn may resolve;
- root-as-target, stale/inactive child, wrong mission/root, effect-fenced principal, reserved turn,
  malformed reply target and lost Company attestation fail closed;
- the returned evidence digest changes with principal authority/profile, reply target or child
  RuntimeBinding generation.

H6-A is deliberately **inert**. It does not extend the neutral V2 actor/message validator, change
the Company MCP tool schema, send Slack, arm Wake or mutate Runtime. Its returned binding carries
`RULING / CONTINUE / STOP` as the intended successor message family, but the current worker-only
`CompanyDialogueGateway` still rejects that binding as `BINDING_UNAVAILABLE`. This refusal is an
explicit regression test and is the safety fence between H6-A and H6-B.

H6-B is now split into a source-safe **B1** and a later owner-composition **B2**.

**H6-B1**, on the current #1240 source branch, adds the neutral/provider-facing contract without
making it operational:

- Dialogue V2 gains a distinct `executive_principal` actor carrying current principal-binding,
  mission-authority generation, capability-profile and root identities. It is *not* the existing
  `executive_surface/coo` actor and therefore does not widen that actor's worker-style message set.
- That actor may emit only `RULING / CONTINUE / STOP`; `RULING` is additionally constrained in
  the neutral contract to `WITHIN_COMMISSION`. Reserved/higher-seat authority cannot be supplied
  through an alternate provider projection.
- Engine reply direction accepts the principal only as the opposite side of a
  `worker_attempt`; it cannot rule on another executive surface.
- A separate `mastermind-company-dialogue-principal` MCP facet exposes exactly four tools:
  `read_thread`, `ruling`, `continue`, and `stop`. The existing six worker tools and their
  schema/tool digests remain byte-stable.
- No model-visible principal tool accepts actor, child, root, workstream, session, thread, provider,
  account, host, RuntimeBinding or placement selectors. Ruling is fixed to current commission;
  continuation injects `scope_change=false`.
- One deterministic message key is derived from the exact child-return/carrier identity, excluding
  the message body and principal generation. An identical replay therefore reconciles to the same
  key/fingerprint; changed semantics, a changed principal generation, or switching CONTINUE↔STOP
  on the same child return produces the existing `MESSAGE_KEY_CONFLICT`, never a second edge.
- Effectful calls use the existing Relay `READY -> COMMIT` exact-send protocol and the verified
  Relay-authored parent. The gateway requires a host callback at the exact pre-COMMIT boundary.
  That callback must return a typed durable-fence receipt whose digest matches the exact public
  commit-intent facts. A missing/no-op/mismatched fence refuses before COMMIT.
- A lost response after the durable fence/COMMIT boundary returns `EFFECT_UNKNOWN` with the same
  reconciliation message key. The gateway does not retry or switch carriers.

B1 still has **no durable effect owner factory** and is not wired into a production capability
profile, so source existence cannot activate it. Local source regressions cover the principal
contract, binding, engine, worker-MCP compatibility, replay/conflict and fence semantics. The
host's missing local MCP SDK leaves server-runtime assertions for dependency-complete CI.

**H6-B2** must compose the B1 `before_commit` contract with the accepted existing Runtime/effect
owner and reconciliation reader, then bind that exact principal server/tool-schema generation into
H1 admission and current Company/Wake applicability. B2 must not create another effect ledger,
dialogue store or wake system. Only after that composition and independent review may a real native
principal use the modifying tools.

## Message operation and effect reconciliation

The principal gateway does not generate a fresh UUID for each retry. It derives one semantic reply
slot from the bound work/commission/session/operation, exact child Attempt, thread root and child
return message. The existing engine's prepared-send/single-flight rules own duplicate/conflict
semantics; the merged #1191 Relay exact-send path owns READY/COMMIT and post-COMMIT uncertainty.
The injected B2 durable owner must fence the exact B1 commit-intent digest before COMMIT and later
reconcile the same message key. A source-level or no-op callback is not sufficient proof.

Before an effectful ruling, fresh-read the exact bound carrier after the latest local evidence-
producing action, apply current mandate/decision authority and verify the returned child revision.
The resulting frame can reference accepted authority; it cannot create that authority by prose.
Do not reinterpret `progress`, `result` or `request_decision` text containing the word STOP as a
terminal ruling. Slack text is not a fallback for a denied or missing principal operation.

Transport receipt, native pickup, execution start, result and acceptance remain separate. A
validated frame may cause an existing Wake obligation only when its target and applicability are
qualified. Arbitrary messages, mentions, stale target IDs and new top-level posts cannot resume
an unrelated child. A thread-root timestamp is part of the carrier identity, not merely formatting.

## Representative reciprocal flow

1. The principal recovers its exact mission/root and accepted target-child commission. It reads
   the bound context and source facts; no free channel or session selector is provided.
2. The child receives the actual valid assignment and separately records pickup/start under the
   existing lifecycle. Delivery alone is not START.
3. The child returns a decision request or bounded result via the existing worker message set,
   with exact canonical result/revision references.
4. The principal fresh-reads that carrier and the decisive result evidence, adjudicates within
   mandate, and issues a valid scoped CONTINUE or repair ruling through the accepted extension.
5. The same child performs the permitted next action and returns a current result. The principal
   verifies acceptance and emits terminal STOP on the exact same child carrier.
6. Retire only that child's temporary dialogue/watch obligation. If an aggregate resource also
   serves another live child or principal inbox, keep those valid sources active. Preserve failed
   shutdown as a transport obligation without pretending the child is nonterminal.
7. Persist the material organizational delta in the existing Agent OS owner and verify accepted
   revision/readback. Do not claim that this automatically changed Runtime or woke another session.

The selected live proof performs this cycle during H4's active review/repair flow, after the
H4/H6 successor profile is qualified. The later H6 evidence review consumes that recorded cycle;
it must not resume an already terminal child to manufacture a second demonstration. H5's material-
return route may be reused after its own dependencies clear; no duplicate graph or watcher is required. A continuation applies only to a still-nonterminal
child assignment. If the Runtime allocates repair as a new child/Attempt, its fresh admitted
binding and commission are required; the old terminal assignment cannot be reused. Complete the
H6 cycle on one eligible live child inside the broader H4 graph. A separate counterpart is acceptable only
with its own current commission and exact binding, not a historical provider session.

## Required refusals and races

Wrong parent/root, sibling child, wrong workstream, expired/replaced binding, reserved decision,
wrong thread root, unrelated top-level message, stale reply target, duplicate semantic send,
response loss after Slack accepted, provider session ID in public content, arbitrary-message wake,
closed child with a still-live sibling watch, and context revision changing during a write all
need explicit tests. The existing engine/owner determines error and reconciliation vocabulary.

For each send test, count actual external messages and canonical wake effects, not just returned
HTTP status. For each resume test, verify the exact target actually consumed the frame. For each
Agent OS write, verify only intended record paths changed and the final revision is recoverable.
Do not inspect real user credentials or deliberately send malformed production messages to obtain
negative evidence; use approved disposable carriers and fixtures.

## Acceptance and implementation boundary

H6-01 through H6-12 cover context, principal-role and transport cases. The original DONE WHEN
requires a real complete principal → counterpart → return → continuation → STOP cycle, with the
same Executive/Agent OS mission identity, no Chairman message shuttling and no duplicate
wake/job/session effects. A worker-only reporting loop or successful Slack post is insufficient.

Current source candidate: **H6-A + H6-B1**. The pure principal/child resolver, neutral
principal actor ceiling, principal-only four-tool schema, exact-send gateway, one-edge replay
identity and typed pre-COMMIT fence contract are built and source-tested. They are
`BUILT_NOT_PROVEN / PRODUCTION_INERT`: no production profile or factory supplies the required
durable fence receipt, and no native principal can be claimed from these files.

Held for **H6-B2 / acceptance**: compose the pre-COMMIT callback with the accepted existing
Runtime/effect owner and reconciliation read; qualify exact Company/Wake applicability; bind the
resulting principal server/tool-schema digest into the H1 native profile; prove installation and
native selection; then run the real reciprocal principal → child → return → CONTINUE → return →
STOP cycle and verify zero duplicate message/Wake/Job/session effects. Macro Agent OS publication
authority remains separate. These are engineering gates under existing owners, not permission to
invent a Claude inbox, thread registry, effect ledger or wake daemon. H6 is not complete until the
real canary satisfies the original DONE WHEN.
