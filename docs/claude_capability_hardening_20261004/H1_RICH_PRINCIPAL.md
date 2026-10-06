# H1 — Rich Claude principal: admission, observation and capability composition

## Outcome and source boundary

Preserve the original H1 outcome: one real admitted principal, exact reviewed capability
generation, harmless reads across multiple admitted owners and refusal on drift. A new profile
row, rendered configuration or a test fixture does not close this packet.

Current source has three independent blockers: registry admission [S01], the restricted SDK
configuration/readback contract [S02–S03], and the supervisor's exact-lane predicates [S04].
Treat these as deliberate fences to supersede through qualification, not bugs to delete.
`sealed.worker.claude.*.no-extensions.v1` remains a different product and unchanged.

## Selected implementation

Qualify the existing `claude-agent-sdk` operator path first. Preserve the existing adapter,
OperatorHarnessOrchestrator, Worker/Attempt identity and Capacity routing. Add the rich policy
observation strategy inside that existing adapter/attestation ownership, alongside—not in place
of—the existing restricted read-only observer. No second native session manager.

The proposed profile name `principal.claude.coo.rich.v1` is a design label until the capability
owner accepts the exact row. The reviewed capability generation must include exact package roots,
source commits, skill entrypoints/closures, tool grants, transport identities, permission policy
and resource grants. Use existing `EffectiveSkillGrant` / `CapabilityPackageGeneration` [S29];
never discover arbitrary files in a user's home and declare them part of the trusted closure.

Do not convert the production v3 policy to v4 by replacing it with the test fixture. A schema
migration must retain all current profiles/grants and include old-profile digest/regression
comparisons. Roll out only the exact selected rich profile; other provider surfaces stay as-is.

## Implementation seams

| Owner seam | Required change | Must remain unchanged |
| --- | --- | --- |
| Registry load, `ExecutionCapabilityProfile` [S01–S02] | Consume an accepted qualification condition for the exact rich profile; render only its exact approved policy | Unknown/native-unqualified profiles still refuse; sealed profiles retain no-extension semantics. |
| `project_claude_mcp_client` [S05] | Remains the sole MCP configuration projection; qualify full observed catalogs and adapter-specific packaging | No launch, credential, session or authority acquisition in this pure function. |
| `ClaudeOperatorAdapter` / observer [S03] | Trusted same-generation rich policy/catalog readback and precise enforcement comparison | Existing restricted observer's positive and negative cases continue to pass. |
| Existing operator supervisor [S04] | A separately reviewed rich lane using exact provider/quota/profile/resource facts | No wildcard profile admission, borrowed provider identity or post-claim rebinding. |
| Existing package owner [S29] | Materialize verified package/skill closure into the granted workspace/runtime surface | Package identity is not permission; no ambient plugin/skill discovery. |
| Existing principal host [S11–S12] | Join admitted capability digest to root-installed mission delegation | Caller cannot declare its own binding, lease or authority generation. |

This is one coordinated compatibility unit. A PR that removes only the registry refusal fails
review even if a hand-constructed profile makes a fixture run.

## Current-base rich-generation contract

The current protected implementation makes the H1 admission gap concrete:

- `ExecutionCapabilityProfile.claude_sdk_config_projection()` accepts only the first restricted
  `claude-agent-sdk` generation: read-only sandbox, network disabled, native helpers disabled and
  **zero skills / skill grants / MCP grants / plugins / resources**.
- `ClaudeReadbackPolicyObserver` proves that same generation only. It requires native tools
  `Read/Glob/Grep` (+ provider StructuredOutput readback), empty skill/plugin/MCP catalogs and the
  exact restricted sandbox/permission provenance.
- `ExecutiveOperatorSupervisor` currently admits only
  `operator.claude.readonly.v1` for the Claude Agent SDK path, with empty MCP/resource/skill grants.
- The checked-in capability registry currently has no rich Claude-principal profile. Its MCP registry
  contains existing Company Consultation, OpenAI docs and Browser grants, but **no admitted Executive
  COO MCP grant and no admitted principal Company Dialogue MCP grant**.
- H3 now has a source package for the six-tool Executive COO backend. #955's prior
  issuer-consistency defect is source-repaired at `e17a56b3454c2528239322a1d1b667d427a7a7f0`
  and is back with its original reviewer; installed/native authentication remains unproven until
  that repair is accepted and the real Claude/IdP ceremony passes.
- H6 now has a distinct principal Company Dialogue tool generation plus Runtime COMMIT fencing and
  source-only host composition; that generation is still deliberately absent from capability policy.

Therefore H1 must add a **new generation**. It must not relax the predicates on
`operator.claude.readonly.v1`, retrofit MCP onto sealed Claude worker profiles, or reinterpret the
existing restricted readback as proof of rich capability.

### Required grant generations before the profile can be enabled

The eventual rich profile needs independently accepted identities for at least these two families:

1. **Executive COO MCP** — the exact H3 six-tool role route and OAuth/resource policy proven through
   the #955 transport owner. The CEO submit route/scope is never a substitute.
2. **Principal Company Dialogue MCP** — the exact H6
   `PRINCIPAL_SERVER_IDENTITY / PRINCIPAL_SERVER_VERSION / PRINCIPAL_TOOL_SCHEMA_DIGEST` generation,
   with host composition using the existing Runtime event fence. The ordinary worker Company Dialogue
   server and the existing Company Consultation server are different capabilities and cannot stand in.

Any separate context/source capability used for R0 must also have its own existing owner/grant.
Counting two methods from one Executive server is still one owner.

### Qualification sequence

Implement and review the rich generation in this order:

1. add the exact MCP grant descriptors while leaving the new principal profile disabled;
2. extend the Claude SDK projection with a profile-specific reviewed configuration branch rather than
   widening the first-profile predicate;
3. add a separate rich native readback observer that compares the full exact MCP server/schema catalog
   and refuses extra ambient MCP/skills/plugins/hooks;
4. add a separate supervisor admission predicate for the exact new profile/digests;
5. prove profile/package/grant drift negatives while the profile remains disabled;
6. only after source review install/observe the exact generation and run harmless native reads;
7. add R1 modifying admission only after #955/H3 authentication + role policy are independently
   accepted; add H6 modifying dialogue only after its installed host/profile generation is accepted.

### Transport/network decision

Do not silently broaden native network policy merely because H3's current transport uses localhost HTTP.

Preferred order:

1. reuse an accepted stdio/Unix/local installed wrapper for the same canonical backend when it can
   preserve OAuth/role/resource semantics without a second auth plane; otherwise
2. separately qualify the exact loopback endpoint(s) required by the accepted Executive transport and
   prove the native sandbox cannot reach arbitrary local or external network targets.

The selected network rule becomes part of the rich profile digest/readback contract. A generic
`network enabled` or inherited user MCP registration is not acceptable H1 evidence.

## Capability increments

Use explicit new reviewed generations, not live feature toggles authored by the model.

**R0 context:** Executive read/mandate plus bounded company/workstream source context. Native
local tools remain limited to the exact needed reads. Prove the second owner through an admitted
source/context capability, not by calling two Executive methods and counting them as two owners.

**R1 bounded COO action:** add only the role-correct principal submission/status pair, its exact
scopes and root-installed mission facts. H3's native action/status/refusal proofs are mandatory.
No orchestration/fanout claim from this generation.

**R2 coordinated work:** add only the accepted H4 delegation and H6 dialogue/source contracts.
Native helper tooling remains disabled unless separately admitted. An ordinary child receives
its own narrower execution profile, not a copy of the principal's tools.

**R3 visual/design capabilities:** add the exact H7 Browser Resource Fabric grant. Studio/Paper
is another independently authorized host carrier and grant; browser admission does not imply
Studio process, file or desktop authority. Missing Paper enrollment holds that family only.

The original broad H1 family list is not dropped: families that cannot yet be admitted are
explicitly deferred with their exact gate. Avoid an all-or-nothing profile that blocks useful
context/action proof behind optional visual tooling.

## Launch protocol

1. Resolve current mission, caller binding, source custody and unresolved effects through their
   owners. Refuse a live conflicting source lease, ambiguous prior launch or unqualified mission.
2. Obtain the already-admitted worker/provider/host selection from Runtime/Capacity. The principal
   never supplies the provider home or account as a substitute for routing.
3. Verify exact SDK/native binary and package generation against the qualification artifact.
   Select a reviewed explicit permission mode, explicit tool inventory and explicit configuration
   sources. No reliance on provider defaults or environment inheritance.
4. Materialize only the approved closure and construct MCP config using S05. Keep approval rules
   separate from visible inventory. Enforce resource restrictions on the server/host side.
5. Start through the existing generation owner; retain its operation/process identity. A dropped
   launch response is reconciled there, not retried under a new key.
6. Collect trusted native settings, tool list, plugin/skill/hook inventory and MCP connection/schema
   observation from the same generation. Ensure a paginated/incomplete catalog cannot pass.
7. Compare profile, packages, grant/schema identity, native settings, egress/resource bindings and
   actual visible/usable tool ceiling. Caller-authored echo data is not native enforcement proof.
8. Seal accepted observation through the existing attestation owner, then permit only the mission's
   next admitted action. If any mismatch exists, fence effects and release/reconcile that generation
   through its owner; do not silently fall back to a broader or different profile.

Re-run the relevant observation barrier after reconnect, resume, package/profile change or managed
policy movement. No universal guessed expiry is introduced. If the native surface cannot prove a
necessary enforcement property, keep that increment unqualified and document the precise falsifier.

## Provider-specific safety and compatibility

The provider source review is in EXTERNAL_NOTES.md. Qualification must test actual behavior of the
pinned SDK/native combination, including the old empty-settings-list defect; version strings are
necessary identifiers, not sufficient proof. Managed policy is always a separate observation and
cannot be disabled. Strict MCP configuration excludes plugin-provided MCP declarations, so load
instruction-only plugin content plus explicitly projected servers for the first qualified path.

A native allow rule is not an exclusive tool list. Do not put the only authorization check in a
callback that a pre-approved tool can skip. Server-side grant validation remains authoritative;
any provider hook used as an additional control must itself belong to the reviewed closure.

## Acceptance and falsifiers

Required positives: exact native generation launches; Executive mandate read succeeds; one
independent admitted context owner read succeeds; expected tools are usable within their actual
scope; no extra model-visible or host-effective capability is silently accepted.

Required negatives: extra ambient MCP/skill/plugin/hook; wrong profile/package digest; schema
change after connection; dropped deny; native policy observer supplied only copied request values;
unknown native version; wrong host/provider after claim; attempts to turn on a sealed profile's
MCP; resource changes during attestation; and response loss after launch.

The live report must preserve expected/observed comparisons, actual source/native versions,
canonical generation receipts, all refusal outcomes and cleanup. Local fixture tests cannot
close those obligations. Cases H1-01 through H1-12 in ACCEPTANCE_CASES.json define the scenarios.

## Ready-to-build boundary

First implement provider-free candidate parsing, projection and adversarial comparison tests in
path-disjoint test/fixture work after custody clearance. Leave production profiles disarmed.
Then obtain independent review of the native policy observation and supervisor admission change.
Only the existing installation/enrollment owners can authorize the actual generation and live
canary. No login, credential inspection, service restart or profile enablement is requested by
this design. H2 static work and H3 source packaging can advance while native qualification is held.
