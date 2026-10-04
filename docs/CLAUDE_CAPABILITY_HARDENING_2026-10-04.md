# Claude Capability Hardening — project initiation and H2-A candidate

## Commission and source identity

Chairman Chris commissioned **Initiate project** on 2026-10-04 with the seven-packet
[build handoffs](CLAUDE_CAPABILITY_HARDENING_BUILD_HANDOFFS_2026-10-04.md).
That file is an exact byte archive of the supplied text: 12,249 bytes, SHA-256
`07d74eae587c4b7649dcaab87f57222a4274f8759e76ba94225fd36789556dfc`.
The archive supplies scope and acceptance, not runtime admission.

- Integration/evidence carrier: Mastermind **#1236**.
- Existing organizational parent: **WS:EXECUTIVE-CAPACITY-FABRIC**, Macro Agent OS.
- Accountable integration role: assigned attended Astra CEO session under existing
  `ceo-sol` responsibility; incumbent runtime/source owners are not displaced.
- Operation: `claude-capability-hardening-20261004-c4-001`.
- Branch: `sol/web-claude-capability-hardening-20261004-c4-001`.
- Protected starting revision: `521720b09be2921e996d9396b522b1c4ca62041c`.
- Skillpack: `mastermind.sol_skillpack.v1`, 1.0.1, bootstrap-major 1. INDEX,
  COLD_START, ACTIVE_EXECUTION, SESSION_RELIABILITY, WEB_CEO_DELEGATION,
  CLOSEOUT, AGENTS and DELIVERY_WORKFLOW were read at that revision.
- Source isolation: one canonical `mmx-workspace acquire`, lane `web`; no raw
  clone/worktree, incumbent checkout modification or runtime-state mutation.

This is a source/evidence checkpoint, not a new Agent OS store, lifecycle,
capability registry, provider selector, lease, session identity or wake mechanism.
The original seven acceptance lanes remain the project completion law.

## Verified current-source census

| Surface | Evidence at the protected starting revision | What it does not prove |
| --- | --- | --- |
| Canonical capability policy | `config/executive_agent_capabilities.json`: v3, nine profiles, production disarmed. Two sealed Claude profiles exist; no rich Claude principal profile exists. | Rich principal admission or live Claude capability availability. |
| Claude projection | `control_plane/claude_mcp_client_projection.py` already projects canonical grants and supports observed-catalog checks. | Installation, native CLI/SDK qualification, server-side grant enforcement or live catalog observation. |
| Capability packages | Registry v4 binds existing exact package-generation and skill-grant digests. | Permission to replace the production v3 policy with a test fixture. |
| Executive plugin | `integrations/claude_executive_plugin` remains 0.1.0, P1 source package, production inert. | Current role-correct COO plugin parity. Later backend features are identified by the brief; a complete backend census is still owed. |
| Installed Executive | Native read at 2026-10-04T07:57:44Z succeeded with no degraded fields, server 1.4.0, mode `readonly`, source `a2646f458f9ff41ddcedd89b338be4a4349e6cd6`. | Writable CEO ingress, Claude COO admission, dispatch or a running child. |
| Organizational parent | Macro `agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md` at `59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc` is active under `ceo-sol`. | An exclusive live writer lease or authority transferred by an old claim. |

The protected pre-onboarding checkpoint identifies #676 (parity), #962/#955
(plugin/auth), #992/#919 (transport/native admission) and #660 (operator
continuation). #600 remains the adjacent native-harness integration carrier.
These are reuse pointers, not a claim that every historical candidate is current.
The live search found #676/#955/#600 open. A compound read of their bodies/comments
was blocked before dispatch by the platform safety-status check and was not
retried or rerouted. Its effect is NONE. Consequently this initiative has not
claimed whole-program custody clearance or edited those incumbent surfaces.

## Sequence and acceptance gates

The initial implementation is deliberately **H2-A**, an offline drift guard on
existing owners. It de-risks later profile/package work without modifying their
runtime authority or rebuilding the current Claude projector.

| Packet | Next bounded outcome | Required acceptance before that packet closes |
| --- | --- | --- |
| H1 rich principal | After incumbent reconciliation, compose exact reviewed COO capability/package references through the existing registry and host admission. Admit families incrementally. | Real native launch, exact profile/catalog/schema generation, harmless reads across multiple owners, ambient-capability and drift refusal. Sealed workers unchanged. |
| H2 provider parity | Review H2-A; then extend equivalent checks to the actual admitted rich profile and other canonical provider projections rather than adding a second projection engine. | Supported generation changes must update/requalify or explicitly defer support; stale claimed parity fails CI. Equal authority ceiling, not equal config text. |
| H3 COO plugin | Census accepted backend/routes and reconcile #955/#962; update package/version, Skill and recovery command without copying CEO tools. | Fresh native recovery, harmless authorized COO action, canonical result read; CEO-only, sibling, invalid profile/principal and session-binding falsifiers. Separate merge/install/auth/canary receipts. |
| H4 Fabric | Bind rich principal to existing child-work contract and Router/Capacity placement after H1/H3 admission. Preserve incumbent transport/adapters. | Two path-disjoint outcomes on eligible non-identical lanes; useful principal progress; both canonical results plus review/repair and accepted parent consumption. |
| H5 CI continuation | Connect the admitted principal's release workflow to the existing exact-candidate observer and return route. Source workflow work may run independently of H4. | One observer, useful concurrent phase, material exact-head result, stale-head rejection and real repair/release-gate follow-through. No observer merge/deploy/rerun authority. |
| H6 context/dialogue | Add authorized Agent OS and validated Company Dialogue capabilities through their existing owners, after exact principal/binding qualification. | One complete principal-to-counterpart-to-return-to-CONTINUE-to-STOP cycle; zero duplicate wake/job/session effects and no Chairman message shuttling. |
| H7 browser proof | Bind only reviewed profiles to the existing bounded local-review Browser Resource Fabric. Studio desktop authority stays separate. | Exact workspace/resource/origin/schema, relevant breakpoints, screenshot plus bounded console/network evidence and exact resource cleanup. No ambient browser/cookies/chrome. |

H1 and H3 form the principal admission dependency; H4/H6/H7 require that exact
admitted identity and their own owner gates. H2/H5 source-only work can proceed
where independently authorized. Parallel work requires path-disjoint custody,
not merely different packet names. No seven-worker fanout is presumed.

## H2-A implementation and deliberately narrow claims

New files:

- `scripts/check_claude_projection_parity.py`: offline checker; consumes
  `ExecutionCapabilityRegistry` and the existing `project_claude_mcp_client`.
- `config/claude_mcp_projection_parity.json`: reviewed static expectations, not
  runtime policy. All nine canonical profiles have four explicit surface dispositions.
- `tests/test_claude_projection_parity.py`: adversarial tests and an assertion that
  the new module is included by the existing `scripts/ci_pytest.py` gate.

The checker pins the existing projector's source bytes, canonical profile digests,
referenced package-generation digests, exact tool/grant/schema identity and
projected configuration/CLI arguments. Profile inventory movement must receive an
explicit disposition. Schema/authority drift, fixture substitution, missing
surface classifications, invalid types, unknown fields, silent support widening,
stale projection output and sealed-worker promotion fail closed. Imported code
and inspected source must be the same checkout. The checker never auto-updates
its manifest or reads ambient Claude/user-home settings.

The initial opt-in set is exactly the CLI and Agent SDK static projections of
`operator.appserver.readonly.docs-mcp.v1` and `operator.browser.local-review.v1`:
**four configuration-supported pairs, 14 deferred, 18 unsupported**. These are
existing canonical Codex-surface profiles used only as configuration inputs; this
manifest does not admit them as Claude principals. Desktop HTTP requires its own
admitted bridge; inline helpers need independent resource/helper/catalog proof.
Sealed workers cannot gain MCP support through this manifest.

The production policy, current projector, plugin, backend, provider settings and
CI workflow are unchanged. The existing CI collection includes the new test.
This is **PARTIAL H2 / source implementation candidate**, not cross-provider
parity completion, a live tools/list receipt or an installed native capability.
The emitted report explicitly has `production_armed: false`,
`native_admission_proven: false` and `observed_tool_catalog_attested: false`.

Run from the candidate checkout:

```sh
python3 scripts/check_claude_projection_parity.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_claude_projection_parity.py \
  tests/test_claude_mcp_client_projection.py \
  tests/test_claude_executive_plugin_source.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py \
  tests/test_executive_capability_packages.py \
  -q -rs --tb=short -o addopts=''
```

## Verification and publication boundary

Baseline: 57 existing projection/plugin tests passed. Initial missing-manifest
check refused, as expected. An adversarial test then exposed Python's `False == 0`
comparison accepting numeric zero in a security declaration; canonical JSON
comparison repaired the defect and the negative test now passes.

Final focused regression: **345 passed, two skipped**, Python 3.14.7, 2.24 seconds.
Both skips are existing capability-package tests at lines 1933 and 2790 reporting
that their temporary AF_UNIX bind was refused. Those cases are not claimed proven.
Archive verification initially found one extra trailing newline; removal restored
exact byte identity with the upload and its original SHA-256. This was not a
change to the brief's content. Full-repository or hosted CI is not asserted from
these local results; exact-candidate hosted checks and independent review remain
release gates. Source merge, installation, authentication and live proof remain
separate, unfulfilled obligations.

Direct execution rationale: `PRINCIPAL_JUDGMENT` for integration/custody and
`NO_ELIGIBLE_PRE_EFFECT_WORKER` through the observed read-only Executive path for
this bounded source-only slice. No direct provider-spawn or metered Codex/work
fallback was used. No worker, observer, watcher, Job, Attempt, browser, service,
credential or installation was created or modified by this initiative.

## Recoverable next action

Use #1236 and the exact published candidate revision, not a new parallel project.
Verify publication/readback, exact-head hosted checks and independent review of
H2-A. In parallel, the assigned integration role retains the next recovery action:
reconcile the incumbent rich-principal/COO plugin source path and obtain its
current source-custody/admission facts without retrying a denied action. The
blocked read is action-scoped, not permission to bypass a platform denial.
Do not edit incumbent paths before that gate is actually resolved.

After H2-A is accepted, use current compatible protected procedures for normal
release. Then qualify H1/H3 through the existing role-correct COO owners; do not
turn this static manifest into a launch gate or capability authority. All seven
packet acceptance requirements remain open. Source artifacts are not an Agent OS
status update or evidence of a runtime lease, and no Macro Agent OS record has
been modified in this slice. No unattended continuation is claimed.

Do not redo the uploaded brief, canonical source recovery, accepted sealed-worker
fences, existing projector or backend features. Reuse this operation's workspace
through the custody owner and refresh only material invalidators.

**INITIATION: established. PROJECT_COMPLETE: false. NATIVE_ACCEPTANCE: unproven.**


## Deep implementation-design continuation — 2026-10-04

The Chairman requested deeply detailed implementation ideas, planning and process. The linked
[design package](claude_capability_hardening_20261004/README.md) now supplies detailed H1–H6
contracts, shared identity/effect/versioning rules, a 16-node execution dependency graph,
80 explicitly unrun acceptance scenarios, official provider research notes and a read-only
consistency verifier. Its source register contains 36 immutable Git anchors at protected
`17b9fa1363db6071d338be3373a4fdb11fc0076d`. Relevant source/procedure bytes are unchanged from
the initial protected base; the original operation workspace and PR #1240 are reused.

Key refinements: rich Claude admission requires coordinated registry/native observer/supervisor
qualification; current COO submission creates a bounded job, not a CooCycle root; orchestration
needs a separate role-correct versioned admission operation. Two reviewed children reserve 19
slots against the current limit of 16, while the proposed reviewed-plus-read-only graph reserves
11. The neutral dialogue contract itself restricts COO actors to worker-style messages, so a
principal ruling needs commission-scoped semantics/binding changes, not just a new tool. The
reciprocal cycle is performed while the child is live, not replayed after its terminal close.

New actual source-contract test result: 334 passed, three MCP-dependent cases skipped. The broader
initial selection had two collection errors for missing jwt/mcp; dependency-complete integration
is not claimed green. Design verification checked source digests, original handoff identity,
case coverage and graph/link consistency; eight in-memory negative checker tests refused as
expected. Those are not executions of the 80 planned native/integration acceptance scenarios.

**Planning is materially advanced but not completely persisted.** The detailed H7 browser-packet
write and a later two-entry source-register extension were blocked before dispatch and were not
retried, rephrased or rerouted. H7 remains explicitly tied to the original handoff; no substitute
file or native proof is claimed. See `claude_capability_hardening_20261004/VALIDATION.md` for the
exact holds. Existing runtime/profile/plugin and sealed-worker source remains untouched.

The next implementation dependency is owner review of the coordinated H1 admission/observation
and H3 package contract, while H4 root and H6 scoped-ruling contracts proceed through their
existing owners after current custody is resolved. The remaining planning-file holds require a
legitimate recovery condition, not another carrier/account/mode. Publication, exact-head CI,
independent review, installation, selection, authentication and native acceptance remain distinct.


## Current-base implementation checkpoint — H2/H3/H6-A

Protected Mastermind was re-pinned to `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`, the
merge that brought #1191's approved interconnect/effect-recovery substrate into protected master.
The candidate branch then integrated that protected head before repairing H2 and building H6-A.
It now contains protected #1191 plus the published H3 plugin and current H2 parity work.

Hosted CI on H3 head `ffa0a496b66060010fa5ec8ce10d286cf20283a4` correctly failed because
protected master added `operator.appserver.interactive.company-mcp.v1` after the parity manifest
was authored. The guard refused the stale inventory rather than silently inheriting that capability.
Current repair commit `b651df0a870df93b52648c84e0ebd635a3e9def1` explicitly classifies the
new Company-MCP profile as **deferred** on CLI, Agent SDK, Desktop-local and inline-subagent. It is
disabled and Codex App Server-specific; no Claude Company-MCP authority is auto-projected.

H6-A is now a source candidate inside the existing Company Dialogue RuntimeBinding owner. It adds
no message transport or tool. A trusted `CooPrincipalDialogueCaller` consumes the existing
`PrincipalAdmissionContext`, capability-profile digest, current effect gate and COO turn facts.
The resolver joins those to one exact live subordinate Job/Attempt, parent/commission identity,
thread, reply target, Company Dialogue attestation, target execution profile and RuntimeBinding
generation. Effect-fenced, reserved-turn, stale/inactive, wrong-root/workstream and malformed
reply-target cases refuse. The resulting principal binding remains intentionally unusable by the
current worker-facing Company MCP gateway, which returns `BINDING_UNAVAILABLE`; H6-B is therefore
still required before any ruling can be sent.

Current combined source validation across H2, H3, H6-A and the merged #1191 dialogue/effect substrate:
**624 passed, three skipped**. The three skips are unchanged optional `mcp` import cases in
`test_mastermind_company_mcp.py`; no dependency was installed and they are not claimed proven.
Standalone Claude projection parity reports 10 canonical profiles, four configuration-supported
pairs, 18 deferred and 18 unsupported, with production/native/catalog attestation all false.
The design verifier remains `PASS_WITH_EXPLICIT_HOLDS`; its 80 acceptance scenarios are still
`NOT_RUN`.

#1191 is now merged after independent approval and exact-head CI. #1041 remains a separate active
Draft owner for the deeper COO hierarchy/domain/CooCycle mechanics and must be reconciled rather than
duplicated. #955 remains held on its OAuth issuer-consistency defect. H7's exact detailed-file write
hold remains unchanged.

**PROJECT_COMPLETE: false. H6-A: BUILT_NOT_PROVEN. H6-B/NATIVE_ACCEPTANCE: not proven.**
