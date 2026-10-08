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

The current branch now makes the H1 admission gap concrete in two separate generations:

- The original restricted `operator.claude.readonly.v1` path remains unchanged: read-only sandbox,
  network disabled, native helpers disabled and **zero skills / skill grants / MCP grants / plugins /
  resources**. `ClaudeReadbackPolicyObserver` continues to prove only that restricted generation.
- H1-RG1 adds a separate checked-in **disabled** profile
  `principal.claude.coo.rich.v1` plus the exact reviewed MCP grant records
  `executive-coo-mcp-v1` and `company-dialogue-principal-mcp-v1`. The global policy stays
  `production_armed=false`; the profile itself stays `enabled=false`.
- The RG1 candidate projection carries exactly the six Executive COO tools plus four Principal Company
  Dialogue tools, but its sandbox still has `deniedDomains=["*"]`,
  `allowAllUnixSockets=false`, and `allowLocalBinding=false`. The candidate therefore describes
  the transport generation without making either loopback HTTP or Unix stdio usable.
- `ClaudeProjectedMcpReadbackObserver` can bind the projected server/tool-name inventory to
  same-session native readback, but explicitly reports
  `native_tool_schema_attested=false` and `resource_generation_attested=false`.
- `ExecutiveOperatorSupervisor` still admits only the original
  `operator.claude.readonly.v1` Claude Agent SDK lane. There is no runnable rich-principal
  supervisor predicate yet.
- #955's issuer-consistency repair is now merged in protected Mastermind source. That closes the
  source defect only; installed Claude/IdP authentication and the real native canary remain unproven.
- H6 now has the distinct principal Company Dialogue tool generation, Runtime COMMIT fence, host
  factory, peer-authenticated Unix transport, shared immutable stdio edge and Executive-service
  listener source. Installed config/socket activation and native capability admission remain open.

H1-RG1 therefore advances the programme to **DISABLED_REGISTRY_CANDIDATE / BUILT_NOT_PROVEN**. It
does not relax `operator.claude.readonly.v1`, retrofit MCP onto sealed Claude workers, or treat
configuration/readback as provider admission.

### Required grant generations before the profile can be enabled

The eventual rich profile needs independently accepted identities for at least these two families:

1. **Executive COO MCP** — the exact H3 six-tool role route and OAuth/resource policy proven through
   the #955 transport owner. The CEO submit route/scope is never a substitute.
2. **Principal Company Dialogue MCP** — the exact H6
   `PRINCIPAL_SERVER_IDENTITY / PRINCIPAL_SERVER_VERSION / PRINCIPAL_TOOL_SCHEMA_DIGEST` generation,
   with host composition using the existing Runtime event fence. The ordinary worker Company Dialogue
   server and the existing Company Consultation server are different capabilities and cannot stand in.

The current source now freezes both authority-bearing server generations **and** their RG1 registry
identities:

- Executive COO: capability `executive-coo-mcp-v1`, config
  `mastermindExecutiveCoo`, streamable HTTP at the one reviewed loopback resource
  `http://127.0.0.1:8444/mcp`, OAuth, server `mastermind-executive-coo/1.0.0`, six tools,
  tool-schema digest
  `8d4ff58a30c02b717788b80fdfd1c5b8b35493dc11dd76cac351cde7b4509d72`, grant digest
  `6e279edd1c0b4236c9b8679c706831df44e7da1881af64863a71884dc65e74d1`.
- Principal Company Dialogue: capability `company-dialogue-principal-mcp-v1`, config
  `mastermindCompanyDialoguePrincipal`, stdio through the exact installed principal-edge
  bootstrap, server `mastermind-company-dialogue-principal-mcp/0.1.0`, four tools,
  tool-schema digest
  `d45c0f8fe2451c726757c42be729e0e49fc5b2637c33efc97dee00168fab7abd`, grant digest
  `508e734ae94f0cd89f1fb545b7ca2ade089a1fcca0a54cdc9b755b8b9f948a3a`.
- Candidate profile `principal.claude.coo.rich.v1` has profile digest
  `c7c104f39940a96f105be5e30954db2a14d9919e7366e2c38fbe36390d394930`; policy generation
  `2026-10-06.claude-rich-principal-rg1` has digest
  `b240b6eee9566f6590c60d3b4b410df8cd74220088b735b375ee10558d690dfd`.
- `RICH_PRINCIPAL_CAPABILITY_GENERATIONS.json` v2 records those immutable IDs/digests without
  embedding URL/command/args or credentials. It remains deliberately not loadable as a capability
  policy and states `production_armed=false`.

The parser change is capability-specific rather than a generic transport relaxation:

- generic streamable-HTTP grants remain HTTPS-only; only
  `executive-coo-mcp-v1` can name exactly `http://127.0.0.1:8444/mcp`;
- stdio remains closed to reviewed command/argument tuples and now adds exactly the Principal
  Company edge alongside Browser B1 and Company Consultation;
- both principal-only grants are rejected from every profile except
  `principal.claude.coo.rich.v1`;
- that profile refuses any enable flip, write capability, helper, Skill, plugin, resource, forbidden
  capability, browser network policy or missing/extra MCP grant.

Focused H1/H2 validation across registry, frozen generations, projection parity, Model Router and
principal edge is **207 passed**. H2 parity now explicitly classifies 12 profiles:
4 configuration-supported pairs, 26 deferred and 18 unsupported. Native admission and observed
tool-schema attestation remain false.

#1196 remains an open ACP draft touching the same registry file but only its ACP execution-surface
constant block; no live #1196 workspace/process was observed during this RG1 wave. H1-RG1 changes
different semantic regions and must still be reconciled against #1196/current protected source at
review/release time. This is not authority to overwrite a future moved ACP head.

Any separate context/source capability used for R0 must also have its own existing owner/grant.
Counting two methods from one Executive server is still one owner.

### Qualification sequence

Implement and review the rich generation in this order:

1. **RG1 source complete:** exact MCP grant descriptors are checked in and the new principal profile
   remains disabled.
2. **RG1 source complete:** the Claude SDK projection has a profile-specific exact candidate branch;
   the original restricted-profile predicate remains unchanged.
3. **PARTIAL:** `ClaudeProjectedMcpReadbackObserver` verifies exact server/tool-name readback and
   launch provenance, but native tools/list schemas and installed resource generations are still
   explicitly unattested.
4. **NOT BUILT:** add a separate supervisor/adapter admission predicate for the exact new
   profile/policy/grant digests; do not reuse the restricted `operator.claude.readonly.v1` predicate.
5. **RG1 source complete:** profile/grant/transport/borrowing drift negatives pass while the profile
   remains disabled.
6. **NOT PROVEN:** after source review and accepted transport/network policy, install/observe the exact
   generation and run harmless native reads.
7. **NOT PROVEN:** R1 modifying admission requires real #955/H3 authentication + role policy;
   H6 modifying dialogue requires its installed host/profile generation and native canary.

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
