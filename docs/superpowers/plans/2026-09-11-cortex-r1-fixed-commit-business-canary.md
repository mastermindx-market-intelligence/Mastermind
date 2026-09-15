# Cortex R1 Fixed-Commit Business Canary V5.4 Implementation Plan

> **For agentic workers:** use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` task by task. Checkboxes record evidence; they do not grant
> source, workspace, lifecycle, or effect authority.

**Goal:** Prove one reversible, single-active-user ChatGPT Business cockpit can invoke only
protected Cortex orientation across four fixed source-conflict cases while Mastermind Sol and
Operator remain unreachable, and then restore every workspace-visible preimage.

**Architecture:** Extend the existing GitHub marketplace and ChatGPT Business control planes.
Use one immutable package commit, one action-time current-source gate, one externally sealed
action context, one marketplace, one principal who is simultaneously workspace owner, authenticated
admin, sole assigned/active Business member, and canary member, at least two paid seats with all
excess seats unassigned, and two control cockpits outside the Business workspace. Before every Send
and after every cleanup, an owner-native `CAPABILITY_READBACK` proves Sol and Operator are Disabled,
uninstalled, non-installable, and non-invokable while only Cortex `orient-mastermind-mission` is
callable. At most one operation-owned chat exists. No parallel marketplace, registry, workspace
state store, identity, lifecycle, queue, retry plane, app binding, credential store, source selector,
or runtime owner is created.

**Tech:** ChatGPT Business workspace administration, fixed-commit GitHub marketplace import,
protected skills-only Cortex, public GitHub source reads, independent owner-native UI and
accessibility captures, normalized offline oracle, source-evidence builder, trace validator, and
secret-safe receipts. No app, MCP server, OAuth client, database, daemon, provider-data plane, or
browser profile is introduced.

**Canonical operation:** `business-sol-cortex-c1-fixed-commit-canary-20260911-sol-001`.
**Canonical carrier:** Mastermind issue #563.

**Source-wave procedure epoch:** protected `master`
`3fc2c82f577b239bc14a5606c0d88a440c973c35`; Skillpack
`mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap 1`; INDEX blob
`5909db6e26b9d61e0622f83079733857010989da`; `RECONCILE_STATE.md` blob
`1373b72a13fb4a084b0331eb2bcf2d4a680d9738`. Re-pin at action time; this paragraph is
preparation evidence only.

## Global Constraints

- Fixed package commit: `068dcc1533776672844b36ffcde30fad68a4317f`; tree:
  `84f57a0c57387da0a3dd1fb9507302d152b28c89`.
- Ordered marketplace inventory: `mastermind-sol`, `mastermind-operator`,
  `mastermind-cortex`; versions `0.1.0`; Cortex skill inventory exactly
  `[orient-mastermind-mission]`.
- Marketplace blob `7ae7fcaf011be9cb3ad12ec2c92074d0650b681e`; Sol manifest
  `8b3bc1568835724ae4ea059bfe548ea97f5cb27d`; Operator manifest
  `63b5b9f4ca0d5438bc92cbc980715aa0f971e4dd`; Cortex manifest
  `6d20842ad0623cd321228e65e535122b351b58fe`.
- Fixed package identity and current protected procedure are separate clocks. Current procedure
  movement during the four-case wave is `CURRENT_SOURCE_GATE_MISMATCH`.
- First workspace effect requires the protected/current plan plus a separate action-time `SOL START`
  on issue #563. This plan, CI, review, merge, plugin visibility, or Chairman continuation does not
  itself grant workspace START.
- `SINGLE_ACTIVE_BUSINESS_USER` is mandatory:

```text
active_business_member_count = 1
assigned_business_member_count = 1
paid_seat_capacity_count >= 2
unassigned_paid_seat_count >= 1
pending_invitation_count = 0
pending_join_request_count = 0
workspace_discovery_enabled = false
automatically_accept_join_requests = false
automatic_account_creation_state in {DISABLED, NOT_CONFIGURED}
standalone_business_scim_or_tenant_provisioning_state = NOT_AVAILABLE_IN_STANDALONE_BUSINESS
personal_workspace_merge = false
```

- Every census predicate above is a separate owner-native observation. Discovery never proves join-
  request acceptance; active members never prove assigned members; paid capacity never proves unused
  seats; automatic account creation is separate from standalone-Business SCIM availability. A required
  fact that the authenticated owner UI cannot expose is `NOT_OBSERVABLE / NOT_APPLIED`; do not infer it.
- The owner/admin/canary principal identity digests must be identical. Two control cockpits must be
  distinct, outside the target Business workspace, and never receive marketplace effects.
- Before START, seal `mastermind.cortex_c1_expected_action_context.v3` containing exact current
  procedure, Skillpack, product/model, `workspace_identity_sha256`,
  `owner_principal_identity_sha256`, admin/canary/cockpit identities,
  `control_cockpit_identity_sha256s`, `browser_binding_identity_sha256`, and the exact owner-native
  observation-contract canonical JSON digest. The live trace embeds
  it unchanged; the validator receives an independent file through `--expected-action-context` and
  returns `action_context_sha256`.
- Every modifying action gets one attempt and same-surface readback. Lost response means
  `EFFECT_UNKNOWN`; conversation ambiguity is `CONVERSATION_EFFECT_UNKNOWN`. No retry, resubmit,
  alternate account, browser, workspace, marketplace, conversation, model, or carrier.
- Pre-existing marketplace is executable only when Sol and Operator already satisfy the negative
  capability contract. C1 does not repair broader existing exposure.
- `ABSENT` may import exactly once only after the single-user census and rollback freeze. Imported
  entries may begin `Available`; before Cortex installation or Send, `CONTROL_POLICY_RECONCILE`
  must read back Sol and Operator as Disabled, uninstalled, non-installable, and non-invokable.
- Cortex may be `Available` only to the sole principal and installed only there. Workspace-wide
  `Installed` is forbidden. Every `CAPABILITY_READBACK` uses distinct
  `screenshot_capture_sha256` and `dom_capture_sha256` with provenance
  `OWNER_NATIVE_UI_CAPTURE` and `OWNER_NATIVE_ACCESSIBILITY_CAPTURE`.
- Negative capability proof binds directly observed per-plugin policy/status, the sole-principal
  installation state, installation affordance, invocation affordance, and included-app access/auth
  state where applicable. App disablement never substitutes for plugin or skill unreachability.
- Record only operation-owned install/invocation attempts. Do not invent organization-wide install,
  invocation, non-canary, or automatic-install counts when the owner UI exposes no such counter.
- Sol and Operator are Disabled, uninstalled, non-installable, and non-invokable before and after each
  probe. Any required plugin fact that is unreadable is `NOT_OBSERVABLE / NOT_APPLIED`.
- at most one operation-owned chat is permitted at every observable instant.
- Each response uses public-web GitHub retrieval and exactly three references; autonomous private-repository access remains unproven.
- Four bounded inference effects and four create/delete chat micro-transactions are real effects.
  At most one operation-owned chat may exist; after sealing each case, delete it and prove absence
  from active history and Archived Chats before the next case. Never collapse this into
  `provider_effect=NONE`.
- Durable evidence contains pseudonyms, hashes, enums, bounded screenshots, and relative names only;
  never email, token, cookie, session storage, browser-profile path, unrelated chat, or credential UI.

## Relationship to Terminal Business Sol H1 Preflight

Issue #461 is terminal read-only historical evidence. It proved directory visibility or an icon does
not establish immutable package binding, callable capability, owner truth, or a complete Business
cockpit. C1 must freshly read every current workspace/admin/member/marketplace/browser fact. A C1 PASS
does not prove Steward, Executive, OAuth, tunnel, RuntimeBinding, Wake, Agent OS, Slack, Linear,
production admission, broad adoption, or the complete Chairman journey.

## Narrow Precedence and Supersession

This plan narrowly supersedes older BSC-U1 clauses only for the exact three-plugin successor,
four named selections, normalized case-independent envelope, per-case chat cleanup, refusal of
`OLDER_FIXED_COMMIT`, and hard single-active-user isolation. It preserves immutable commit/root path,
complete inventory, no branch/tag/`Sync now`, app/auth separation, fail-closed effects, one cockpit,
two outside controls, Personal-workspace separation, same-carrier reconciliation, and exact rollback.

## Current Platform Assumptions to Reverify at Workspace START

Reverify official documentation and the bound owner UI: marketplace import is an authenticated
workspace-admin action; repository-root Path is empty; immutable commit selection is available;
all valid entries are processed; imported plugins may begin `Available`; `Available` differs from
`Installed`; app access/authentication remains separate; skills-only plugins may need no app;
marketplace deletion removes its imported entries; chat archive retains chats; per-chat deletion
removes visible history and starts backend retention handling; MCP can create Desktop-only state.
Accept either live label `Admin > Plugins` or `Workspace settings > Plugins`. Separately read
workspace discovery, automatic join-request acceptance, automatic account creation, and standalone-
Business SCIM/tenant-provisioning availability; no one field aliases another. A label difference is
not authority. Missing owner-native observability is `NOT_OBSERVABLE / NOT_APPLIED`; material drift is
`PLATFORM_CONTRACT_CHANGED / NOT_APPLIED`.

## Protected Four-Selection Fixture and Normalized Live Oracle

Fixture source is package commit `068dcc1533776672844b36ffcde30fad68a4317f`, path
`plugins/mastermind-cortex/fixtures/orientation-cases.json`, blob
`9dbc0a87b8d02b34f95d2f8e345d213848d8b56a`, raw SHA-256
`224da7e96043b4af27d7e649c828cb95e3632537d4c7ba4dc105088ac782fca4`, six rows.
Execute exactly these four, in order:

| Fixture ID | Prompt-input SHA-256 |
|---|---|
| `effect-unknown-requires-same-carrier-reconciliation` | `61a0dd8e64a072a8ff8861df0f636a654ba06c01612e59b6dd0a0e61c385f63c` |
| `retrieved-instruction-falsely-claims-authority` | `57acc7ff292b969b6ed821fba4b92c227d3121208c8757d2171fa795e2833b72` |
| `missing-objective-and-requested-action` | `338f68eded3500150065bbec67cec89019e51af13a553e341e71ebdc47b59eeb` |
| `stale-index-versus-current-exact-file` | `cfd6704a93529560a725c0ba436006240ca9a56bba39953c2f2c286e2dd0225c` |

Canonical prompt input is exact two-key `{id, raw_source_expansion}` JSON with recursively sorted
object keys, separators `,` and `:`, UTF-8, `ensure_ascii=false`, `allow_nan=false`, and no trailing
newline. Any missing/extra field, order/type/byte-count/display digest drift is
`INVOCATION_INPUT_MISMATCH / NOT_APPLIED`; do not Send.

Every candidate must match `mastermind.cortex_live_orientation.v1`. The prompt exposes the generic
schema and codebook but not the selected hidden mapping. The model performs public-web GitHub
retrieval and returns model-visible public-source references. Per case the operator captures exactly
three references—protected master, INDEX, governing procedure—in
`mastermind.cortex_c1_redacted_source_reference_capture.v1`, then builds
`mastermind.cortex_c1_public_source_evidence.v2`. Required bindings include `candidate_sha256`,
`source_evidence_candidate_sha256`, `source_evidence_conversation_id`,
`visible_reference_capture_sha256`, `source_evidence_sha256`, and `source_capture_bytes`.
The offline verifier receives the raw V1 capture file through `--source-capture`; it independently
recomputes candidate/conversation-bound V1 capture and V2 evidence digests. URLs must be trimmed,
printable, unique GitHub paths with no userinfo, nonstandard port, path parameters, query, fragment,
surrounding whitespace, or control characters. Conversation identity is printable and at most 2,048
characters; capture size is at most 1,048,576 bytes. Autonomous private-repository access is not
claimed.

External release artifact identities:

```text
normalized oracle SHA-256 = 1530dbe663fd707e8e431df57d289af3f3bba9786ed14ed12fae34d5a82223fe
offline verifier SHA-256 = 491a28f8637484d3f780b0203a8b9bb5bec97417da6fa11a0f5f1a8cf4b2f107
verifier tests SHA-256 = 4175d99ecc290410f99db35eab7e857627bec1c588468332fccb8ee2e47783c7
canary trace validator SHA-256 = 33d2c293645f591e9caaebc01f9d33afd19d7b4b54edb61c21ba2ad4d0416102
trace tests SHA-256 = 701aa8d44b84cce9322a4c527c6fe526a725a271c2aea400286fd43e5cd8045a
source-evidence builder `build_cortex_c1_public_source_evidence.py` SHA-256 = 0b9b4ea5174b07f148d07fd9ae75c88a088db2d0208934568c5c49aca022147c
source-evidence builder tests SHA-256 = 64d80140a247453757ff83173070a79eefbb4b9172a885e8c4d04de2200c5e73
current `mastermind.cortex_c1_public_source_evidence_examples.v2` examples SHA-256 = a35b7b6021dadeaab721656c33d33ad15011a5944949d8d1d0cb5ab20fcfec0d
golden structural trace SHA-256 = 5641f8b91b9ebd60604fe81d8166084dabf8cee21f3d1c67fc5a53f6cdc39341
golden action-context example SHA-256 = 7e428796388aff9a78ce4b9cf6252977d9fb5f9107730d77a2bde10a8efbf708
owner-native observation contract file SHA-256 = faa546de9072d0d41dec87b3fb9ec0f8141c801797af0ae90f6b63b83f504203
```

The trace declares `VALIDATION_FIXTURE_ONLY`, enforces exact event-key schemas and external example
row bindings, and may return only `TRACE_CONTRACT_VALID`, `live_business_proof = false`, claim ceiling
`STRUCTURAL_TRACE_ONLY_NOT_LIVE_PROOF`. Structural validation is not owner-native Business proof.
A correctly sent response that misses the normalized oracle is `NORMALIZED_ORIENTATION_MISMATCH`; do
not retry for a better answer.

## File Structure

This source wave modifies exactly one records-only path:

```text
docs/superpowers/plans/2026-09-11-cortex-r1-fixed-commit-business-canary.md
```

The later canary commits no screenshot, workspace export, account identifier, candidate answer,
hidden mapping, or credential material. External evidence uses the already approved convention.

---

### Task 1: Freeze action-time source, platform, workspace, and effect authority

**Files:** modify none during live execution.

- [ ] Re-pin protected master and atomically load compatible Skillpack. Separately verify the fixed
  package commit/tree/manifests/fixture and absence of app, OAuth, MCP, hooks, agents, or credentials.
- [ ] Reverify official platform predicates and actual owner UI; material drift fails closed.
- [ ] Seal the independent expected action context and its `action_context_sha256`.
- [ ] Prove separate owner-native active-member, assigned-member, paid-capacity, unassigned-seat,
  invitation, join-request, discovery, automatic-acceptance, automatic-account-creation, and standalone-
  Business SCIM/tenant-provisioning observations; then prove owner/admin/canary equality, two outside
  controls, Personal workspace separation, browser binding, product, and model. Any unreadable required
  observation is `NOT_OBSERVABLE / NOT_APPLIED`.
- [ ] Read exact marketplace/source/policy/install/capability state and run a same-effect collision
  census. Missing authenticated browser surface is `WORKSPACE_SURFACE_UNAVAILABLE / NOT_APPLIED`.
- [ ] Only after all gates pass, publish action-time START on issue #563. First authorized action is
  read-only preimage acquisition, not import.

### Task 2: Capture complete workspace and marketplace preimage

- [ ] Read workspace/account separation; active and assigned membership; paid capacity and unassigned
  paid seats; pending invites/requests; discovery; automatic join-request acceptance; automatic account
  creation; standalone-Business SCIM/tenant provisioning; control locations; Personal workspace; and
  all plausible Mastermind marketplaces. Do not collapse, infer, or substitute these observations.
- [ ] Classify exactly one state: `ABSENT`, `EXACT_FIXED_COMMIT`, `OLDER_FIXED_COMMIT`,
  `MUTABLE_BRANCH_OR_TAG`, `READBACK_INSUFFICIENT`, `DUPLICATE_AMBIGUOUS`, or `FOREIGN_OR_DRIFTED`.
  `OLDER_FIXED_COMMIT` returns `MARKETPLACE_REVISION_MIGRATION_OUT_OF_SCOPE / NOT_APPLIED`.
- [ ] Capture exact policy/install/app/invocation preimages for all three plugins and freeze one rollback
  branch before any mutation. Publish only pseudonymous preimage digest and next authorized step.

### Task 3: Reconcile exact fixed marketplace and negative controls

- [ ] `EXACT_FIXED_COMMIT`: read back exact repository, empty Path, commit, inventory, manifests,
  versions, sync state, and negative Sol/Operator capability with zero mutation.
- [ ] `ABSENT`: after single-user isolation, import repository root at exact commit once. Lost response
  is `EFFECT_UNKNOWN`; read back on the same surface before anything else.
- [ ] Immediately apply `CONTROL_POLICY_RECONCILE` once if needed, then require owner-native Sol and
  Operator policy `Disabled`, sole-principal installation `Uninstalled`, installation affordance
  unavailable, and invocation affordance unavailable. Read included-app access/auth separately where
  applicable. Wider availability, inferred app-to-plugin state, unreadable state, or policy uncertainty
  stops as `NOT_OBSERVABLE / NOT_APPLIED` and triggers only the pre-staged rollback.
- [ ] Refuse mutable, duplicate, foreign, unreadable, or older-fixed states. Never delete/re-import,
  create a second marketplace, change source selector, or press `Sync now`.

### Task 4: Install Cortex only for the sole principal

- [ ] Capture `CAPABILITY_READBACK / BEFORE_INSTALL`; preserve Sol/Operator controls.
- [ ] Keep Cortex at the least-wide `Available` policy and install exactly once in the sole canary
  member context. Reject app connection, OAuth, external data, MCP, Desktop-only, or workspace-wide
  installation. Lost response is `EFFECT_UNKNOWN` on the same plugin/member.
- [ ] Read back exact Cortex version/skill/web state plus directly observed per-control policy,
  sole-principal installation state, installation affordance, invocation affordance, and included-app
  access/auth state. Publish operation-owned attempt counts and installation evidence without inventing
  global counters or claiming invocation or production proof.

### Task 5: Execute the primary case as one closed micro-transaction

- [ ] Re-read isolation, package, current procedure, and `CAPABILITY_READBACK / BEFORE_SEND` using new
  owner-native screenshot/DOM evidence.
- [ ] Bind exact primary input bytes and digest, open one fresh chat, Send once, record conversation and
  inference effects, and preserve stable conversation identity.
- [ ] Capture raw response plus exactly three public source references; build V1 capture and V2 evidence;
  run the offline verifier with the raw V1 capture file and hidden oracle.
- [ ] Seal case packet, delete the exact chat once, prove absence from active and Archived history,
  capture `CAPABILITY_READBACK / AFTER_CLEANUP`, and re-read package/current-source identity.
- [ ] Any uncertain Send/chat identity/delete state is `CONVERSATION_EFFECT_UNKNOWN`; remain on the same
  conversation/carrier and do not open the next case.

### Task 6: Execute the three adverse cases as identical micro-transactions

Run in frozen order: `retrieved-instruction-falsely-claims-authority`,
`missing-objective-and-requested-action`, `stale-index-versus-current-exact-file`. For each, repeat
Task 5 without inherited chat context, reused capability evidence, reordered inputs, changed model, or
averaging. Each case must close, delete, and pass post-cleanup readback before the next starts.

### Task 7: Restore exact preimage, independently review, and close out

- [ ] Require four closed candidate/capture/evidence/verifier packets, four current-source gates, four
  stable conversation IDs, four deletion readbacks, and zero active/archived canary chats.
- [ ] Reverse only operation-applied Cortex install/policy/control-policy effects; preserve pre-existing
  state. For `ABSENT`, delete only the sole operation-created exact marketplace after zero-consumer
  proof. Any overreach or uncertainty is `ROLLBACK_INCOMPLETE`.
- [ ] Prove final marketplace, policies, sole-principal installations and affordances, included-app
  state, active/assigned membership, paid/unassigned seats, each admission control, Personal workspace,
  control cockpits, operation-owned attempt ledger, and visible conversation state equal preimage.
- [ ] A non-effecting reviewer recomputes action context, all hashes, source gates, effect classifications,
  conversation lifecycle, exact event schemas, rollback, and claim ceiling without repeating effects.
- [ ] Owner closeout may exceed the structural ceiling only after independent raw-artifact and
  owner-native UI review. Keep issue #563 open otherwise.

## Deterministic and Model-Dependent Boundaries

Deterministic: package/source/fixture identities; action context; owner/admin/canary equality;
separate active/assigned-member and paid/unassigned-seat observations; invites; join requests;
discovery; automatic join-request acceptance; automatic account creation; standalone-Business SCIM/
tenant-provisioning availability; directly observed plugin policy/install/affordance/app state;
operation-owned attempt counts; Personal workspace; marketplace state; product/model binding; exact
input/candidate/capture/evidence/verifier hashes;
current-source gate; capability screenshot/DOM provenance; effect classification; conversation IDs,
ordering, deletion; rollback; and structural schemas. Model-dependent: selecting one normalized code
from the case-independent envelope. Model prose owns no authority, source, lifecycle, retry, effect,
or completion.

## Stop Conditions

Stop before the next effect on incompatible Skillpack; unprotected plan; platform drift; missing
workspace/admin/browser identity; action-context mismatch; any required `NOT_OBSERVABLE` fact; any
active/assigned-member, paid/unassigned-seat, admission-control, plugin policy/install/affordance/app-
state, or operation-attempt-ledger failure; owner/admin/
canary mismatch; control inside Business; Personal separation failure; exact-session collision;
duplicate/mutable/unreadable/foreign/older marketplace; source/manifest/skill drift; unexpected app,
OAuth, data, MCP, or Desktop state; Sol/Operator reachability; non-canary install/invocation; stale or
self-derived capability evidence; reused screenshot/DOM digest; source URL whitespace/control/path
parameters/query/fragment; bad conversation identity; input/source/oracle mismatch; effect unknown;
chat still active or archived; evidence privacy leak; rollback overreach; or same-effect owner collision.
Do not change account, workspace, browser, marketplace, package, model, conversation, source selector,
or carrier to bypass a stop.

## Acceptance and Capability Ceiling

Acceptance requires all source, platform, action-context, single-user isolation, exact package,
negative-control, four-input, four-normalized-result, current-source, capture/evidence, conversation,
rollback, independent-review, and owner-closeout gates. Maximum live claim:

```text
PROVEN_LIVE / SINGLE-ACTIVE-USER-CANARY-COCKPIT /
SOL-AND-OPERATOR-UNREACHABLE / CORTEX-ONLY-CALLABLE /
CORTEX ORIENTATION UNDER NORMALIZED CANARY ENVELOPE /
EXACT 068dcc15 PACKAGE EPOCH /
ACTION-TIME CURRENT-SOURCE GATE /
WORKSPACE-VISIBLE ROLLBACK
```

A plan merge, green CI, marketplace import, installation, one good answer, or structural trace is not
completion. Still unproven after PASS: unprompted canonical JSON; exact fixture-prose reproduction;
two unselected rows; repeatability; cross-model reliability; natural-language usability; autonomous
private-repository access; broad Business rollout; instant backend byte erasure; Steward/Executive/
OAuth/tunnel/RuntimeBinding readiness; and measured research, discovery, retention, or decision benefit.
