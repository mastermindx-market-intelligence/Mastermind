# GitHub Enterprise Cloud estate study — September 5, 2026

Operation: `github-enterprise-cloud-estate-study-20260905-sol-001`

Status: records-only research and bounded local diagnostic evidence. Recommendations are SPEC_ONLY unless an existing implementation is explicitly identified. This record does not create a runtime operation, placement, worker, watcher, new workstream, merge controller, settings writer or production acceptance. It extends the existing Sol Capability Fabric GitHub estate research rather than replacing its owners.

## Outcome and ruling

Use GitHub more deeply, but do not enable every feature or build another GitHub control plane. The strongest sequence is: finish existing safety repairs; establish effective native Enterprise controls; improve measured CI/storage and exact-artifact delivery; finish the narrow live GitHub evidence integration already designed for Sol; add third-party products only for a demonstrated unmet job.

The end state is one authorized builder journey from the correct repository and owner through a bounded change, trustworthy current checks, independent review, accepted exact artifact, actual served identity and real user/machine proof. Sol must distinguish source existence, CI, review, merge, deployment and acceptance without reconstructing chats. Permission denied, partial pagination, stale heads, pending checks, broken publishers and unavailable runners remain visible states, not empty-success results.

GitHub owns implementation/evidence. Executive OS owns runtime Job/Attempt/Worker lifecycle and admission. Agent OS owns durable organizational workstreams, decisions, discoveries and handoffs. Linear is selective projection. Slack is transport/hot-state. GitHub Projects, webhooks, Apps and AI summaries must not duplicate those authorities.

## Exact snapshots and coverage

Initial source snapshots:

- Mastermind protected master: `b0f85b0f1c66825ecec4bf6ce32dcbfac0c14b93`.
- Macro main: `72ef56eb6ec7b536b74d5e8927ead8766539b502`.
- Terminal master: `e89ebda4064715371a56b1fc02b9ec9c9821d433`.

Protected Mastermind was re-read immediately before publication as `0106aaa832a8146810e0905d52b7d5444f6827f0`. The comparison from the initial pin has one commit and exactly two changed paths: `integrations/chairman_surfaces/nonseat_canary_vendors.py` and `tests/test_nonseat_canary.py`. Governing Skillpack and estate-helper paths were unchanged. Current INDEX/procedures were refreshed at the new pin. Compatibility: `mastermind.sol_skillpack.v1`, version 1.0.1, minimum bootstrap major 1.

The connector exposed five repositories including the three core repos and two auxiliaries. This is an accessible census, not proof that no hidden repos exist. Deep scope is the core three; an organization policy must separately account for auxiliary and backup roles.

Observed: repository metadata, branch summaries, ruleset lists and Macro's complete ruleset, selected important workflows and directory trees, current runner-policy source, the administration helper, existing estate research, Terminal Agent OS workstream, relevant current PR/issue metadata and a local exact-source diagnostic.

Not completed: line-by-line application audit; penetration testing; complete enterprise membership/SSO/App/OAuth inventory; every security setting or alert; detailed classic branch protection; billing and full Actions metrics; live runner roster/isolation; every workflow run, branch or PR; deployment-environment census; current served versions; or full repository tests. An administration-required branch-protection read returned permission denied through the connector. This is UNVERIFIED, not disabled. Missing workflow YAML does not prove CodeQL default setup is absent. Empty rulesets do not prove classic protection is absent. Static runner configuration is not liveness.

## Fresh estate findings

### Visibility, size and source authority

All three core repository metadata responses reported public visibility. No credential leak or rights violation is asserted. Proprietary code, internal records, licensed data and publication inputs need an explicit rights/visibility review. Do not flip private before CI, dependency fetches, tools, publishers, deploy and rollback paths pass private-access canaries. Terminal already has a private-cutover gate. Enterprise Cloud does not automatically mean private Code Security, Secret Protection or Copilot entitlements are included.

Reported GitHub repository sizes: Mastermind 20,063 KB; Macro 27,282,503 KB (approximately 26.0 GiB); Terminal 99,064 KB. These are metadata footprints, not measured clone packs or artifact-billing totals. Macro needs an object/churn census before a migration decision. GitHub recommends repositories ideally below 1 GB and strongly recommends below 5 GB [S21]. Do not rewrite history, delete point-in-time evidence or move everything into LFS blindly.

Terminal metadata still says the VPS is canonical; its existing `WS-TERMINAL-GITHUB-CANONICALIZATION` program owns correction of source/deployment authority. Macro's description is absent. Core topics/custom_properties were empty and no license was detected by repository metadata. Public visibility is not an open-source licensing instruction; never add a license cosmetically.

### Native policy is only partially established

Macro ruleset 21813020, `c0b-native-main-interlock`, targets the default branch but is **Evaluate**, with no bypass actors. Required checks are `fence-pack`, `ci-authority/main` and `ci-gate`, all bound to integration 15368. Its inspected PR policy allows squash with zero required approvals. Evaluate is not enforcement.

Activation is not a safe blind toggle. Existing Macro #6637 and publisher qualification must demonstrate both denied unauthorized change and successful legitimate production publishing, with rollback. Mastermind and Terminal returned empty ruleset lists; that does not supersede classic branch protections. Mastermind's latest protected-branch summary reports `test` bound to App 15368. Detailed classic controls remain unverified.

### Built work is stranded before acceptance

| Existing owner/carrier | Observed implementation | Boundary |
|---|---|---|
| Mastermind #264 / PR #271 | Truthful assessment-only administration repair | Open Draft; mergeable false at read; head `aae5699bf51253a4aee3df4914484ed5cc19b5a1` |
| Mastermind PR #281 / parent #280 | Pure exact-head evidence core | Open Draft; stacked parent; head `f5fffa1bba55d4ca1e92d1052e1b5b8e05175e84`; no live-gatherer proof |
| Terminal PR #487 | Check-App provenance and candidate read permissions | Open Draft; head `f37f5de8c2de36ddea1a9954e7e7c0003a6a70f2`; browser gate #485 |
| Terminal #483 / Agent OS workstream | Source audit, exact deployment, drift, rollback, private-cutover program | Preserve existing owner, not a new program |
| Macro #6637 / #6351 | Native integrity, trusted CI/runner/private-cutover work | Preserve current control-plane and runner owners |

PR #271 and #281 bodies name older heads than their direct current metadata. Historical green checks in those bodies do not approve the newer head. This is stale narrative, not a GitHub connector defect. Current head, integration, check producer, reviews and source materiality need direct evidence.

### Strengths to preserve

Mastermind CI explicitly narrows contents permissions, has a job timeout and pins its sparse Macro dependency checkout to `256c757b3c4f0ec759571c29a30a71387d0a18f8` with checkout credentials not persisted. Private migration must qualify its token/App path rather than rely on public fallback.

Macro deliberately initiates CI broadly, with a more specific selector determining required work. Do not narrow the catch-all trigger as an optimization and reintroduce the historical new-root/test-only coverage gap. Large CI/daily YAML warrants measured extraction of stable boundaries, not a mass formatting rewrite.

Macro runner policy describes a trusted main executor, hosted forks, selected workflow restrictions, reserved render capacity, three CI slots and a fourth pending slot. Source declaration is not registration/liveness. The broad `ordinary_pr_ci: github-hosted` label needs reconciliation with more specific enabled production-route fields, not speculative rerouting.

Existing disaster-recovery work should receive a real restore proof, not a competing scheduler. Source or upload success is not recovery acceptance.

## Architecture and build-versus-buy decisions

Use native custom properties for a small bounded repository classification: owner, service tier, sensitivity, deployment class and lifecycle class. Restrict policy-driving edits so a production repo cannot evade controls by changing its own classification. Apply a common evaluated baseline with explicit publisher/deployment/backup exceptions [S02-S04].

CODEOWNERS should map sensitive source, workflow, deployment and ownership-file paths to actual eligible teams. Its semantics do not require every listed owner to approve. Enforce intended independence explicitly rather than inferring it from a file [S05].

Native merge queue merits a canary, not immediate activation. All required GitHub Actions checks must run on `merge_group`; PR/push triggers alone are insufficient. Compare it against exact-head, material-source, publisher and Sol authority rules. Only one active merge controller may own a branch. Do not run native queue, a Marketplace merge bot and existing merge-on-green concurrently [S06].

Security is native-first: actual secret-scanning/push-protection settings and safe canary; CodeQL language and successful scan coverage; dependency graph/review/security updates; explicit alert owners; low-churn grouped routine updates separated from security urgency and major changes. Absence of repo YAML is not an enablement census. Private entitlements must be budgeted separately. Terminal dependency maintenance already has an owner/gate; do not install a second updater [S07-S11].

Pin approved Actions to immutable SHAs after an inventory and safe canary; narrow workflow/job permissions; audit privileged events and candidate script execution; bind supported cloud identity through OIDC only where its actual provider/ref/environment conditions are understood. Self-hosting is not by itself a trust boundary [S12-S13].

Use native Actions metrics for workflow/job/runtime/runner usage, queue time, runtime and failure rates before buying a replacement observability platform [S14-S15]. Proposed measures are first-attempt pass rate, checkout/install time, queue p50/p95, cancellation/rerun waste, cost per accepted capability and production change-failure rate. No present savings percentage is claimed because billing/live utilization was not obtained.

Separate source, fixtures, generated publications, point-in-time research inputs, correction records and backups. A storage migration must include one real producer and consumer, immutable manifest/digest, rights, times, null/error behavior and rollback. Missing external data must not produce stale healthy output. Prefer forward migration over destructive history surgery [S21].

Terminal #483 owns build-once/deploy-exact-artifact, attempted/deployed/served/rollback identity, protected environment and real browser/data proof. Attestations establish provenance, not application correctness or actual served state. Immutable releases require asset finalization before publication. Use an existing supported registry/GHCR where appropriate; GitHub Packages is not a universal native PyPI host. Preserve mutable data/secrets outside source replacement [S16-S20].

### Apps and plugins

| Job | Decision |
|---|---|
| Repository/PR operations | Native connected GitHub/CLI/official MCP; no generic replacement API |
| Security, dependencies, CI, release protections | Native first, with actual coverage and entitlement evidence |
| Sol's complete fresh PR evidence | Finish existing GH-A1 PR #281 and GH-A2 live gatherer; do not rebuild the semantic core |
| Production publication identity | Reuse/qualify a narrow separate App where the current owner requires it |
| Repository administration | Keep current families assessment-only until a separate truthful mutation architecture is accepted |
| Extra scanner/updater/coverage or AI review | One measured unmet job and reversible limited-scope pilot |
| All-powerful merge/admin/agent bot | REJECTED_BY_DESIGN: combines evidence, approval, settings, deployment and authority |

GitHub Apps fit durable service integrations because they can use selected repositories, fine-grained permissions and short-lived installation credentials. That is not permission to request broad administration rights. Inventory existing Apps, owners, scope, token custody and event consumers before adding one [S28-S29].

The useful custom read job is: explicit repo/PR -> stable IDs and current head/base/integration -> complete paths/checks with App and SHA -> independent review/thread state -> freshness/completeness -> deterministic blocker assessment -> real Sol consumer. Map failures into the accepted existing contract, not new parallel schemas. Keep missing permission, partial pagination, stale data, head movement, wrong producer, pending check and stale review distinct. A prepared evidence tuple is not a release instruction.

Prefer webhook invalidation and reconciliation through the existing event owner. Follow API pagination/rate limits and conditional GET behavior. Do not turn a GET ETag into an unsupported conditional unsafe update. Lost modifying responses are reconciled on the same carrier, never blind-retried on another transport [S30].

Optional named shortlist: Renovate only for a demonstrated dependency-maintenance gap after the Dependabot census, and never as a second updater of the same ownership. Semgrep only for a useful custom pattern or incremental security finding not covered by selected native scans/current deterministic fences. Codecov only for measured differential-coverage/reviewer value; its current docs warn GitHub annotations are being deprecated, so do not make that mechanism a new mandatory dependency [V01-V03]. All require minimal access, rights-safe data, bounded cost, owner and uninstall path. None was installed here.

Copilot is a bounded experiment, not a replacement organization or independent final approver of its own work. Current organization/enterprise billing uses AI credits, and the June-August promotional allowance ended September 1, 2026. Standard documented included credits are 1,900 per Business seat and 3,900 per Enterprise seat, pooled by billing entity. Inspect paid-overage policy and user/enterprise budgets before a pilot; do not use old promotional/premium-request arithmetic [S31-S32]. No paid AI feature was purchased, assigned or run here.

## Complete avenue map

The expanded study identifies 79 avenues. The following stable research IDs are inventory references only, not runtime jobs or a desired-state control plane. A means helper; B Terminal browser/hardening; C native integrity/publisher; D admin/security census; E CI/runner/storage economics; F deployment/recovery; G evidence integration; H onboarding/collaboration. P0 protects integrity or clears a blocker; P1 next high-value adoption; P2 conditional optimization; P3 optional/defer. Unverified features are not asserted absent.

| ID | Avenue | Current observation or gap | Priority / lane |
|---|---|---|---|
| GH-001 | Enterprise/add-on entitlements | Admin census unverified | P0 D |
| GH-002 | Repository custom properties | Core metadata empty | P1 D |
| GH-003 | Teams/least-privilege roles | Effective membership unverified | P0 D |
| GH-004 | SAML/account model | Unverified; no default managed-user migration | P1 D |
| GH-005 | SCIM/offboarding | Must test revoked access, not only logout | P1 D |
| GH-006 | Audit logs/streaming | Effective retention/sink unverified | P1 D |
| GH-007 | PAT/OAuth governance | Endpoint access narrower than role flags | P0 D |
| GH-008 | Private visibility/fork policy | Three core repos public; cutover gated | P0 D |
| GH-009 | Parent organization rulesets | Common effective baseline not established | P1 C |
| GH-010 | Macro native enforcement | Existing ruleset Evaluate | P0 C |
| GH-011 | Classic protections | Summaries protected; full admin read unavailable | P0 D |
| GH-012 | CODEOWNERS coverage | Effective coverage unverified | P1 D |
| GH-013 | Check App provenance | Terminal #487 already owns repair | P0 B |
| GH-014 | Exact-head review/reuse | Body/head drift in #271/#281 | P0 A/G |
| GH-015 | Native merge queue | Current controller/checks not qualified | P2 C |
| GH-016 | Merge methods/cleanup/break-glass | Repo methods differ; preserve owner law | P1 C |
| GH-017 | Protected tags/immutable releases | Effective configuration unverified | P1 F |
| GH-018 | Repository descriptions | Terminal authority stale; Macro absent | P1 H |
| GH-019 | Security configurations/entitlement | Unverified effective coverage | P0 D |
| GH-020 | Secret scanning/push protection | Enablement/alerts not read | P0 D |
| GH-021 | CodeQL | Successful language coverage not read | P1 D |
| GH-022 | Dependency graph/advisories | Manifest/transitive census needed | P1 D |
| GH-023 | Dependency review | Current policy unverified | P1 D |
| GH-024 | Security updates | Effective setting/owner unverified | P1 D |
| GH-025 | Grouped routine updates | Terminal maintenance already gated | P1 D |
| GH-026 | Action pins/allow policy | Reviewed source uses mutable major tags | P1 D |
| GH-027 | Security report ownership | Private response path unverified | P1 H |
| GH-028 | SBOM/release dependencies | Artifact-bound evidence unverified | P2 F |
| GH-029 | Token/job permissions | Mastermind read; Terminal #487 pending | P0 B/D |
| GH-030 | Candidate/privileged trust boundary | Existing Macro route to preserve | P0 E |
| GH-031 | OIDC | Actual provider/use unverified | P1 F |
| GH-032 | Reusable workflows | Stable duplication census needed | P2 E |
| GH-033 | Path-aware selection | Existing catch-all plus selector | P1 E |
| GH-034 | Native Actions metrics | Actual dashboard/baseline not obtained | P1 E |
| GH-035 | Concurrency/cancellation | Present; race contracts must survive | P1 E |
| GH-036 | Timeouts/artifact bounds | Some source controls; full budget unverified | P1 B/E |
| GH-037 | Runner groups/workflow restrictions | Static declared design; live probe needed | P0 E |
| GH-038 | Live runner census | Fourth slot pending, not proven online | P1 E/G |
| GH-039 | Cache trust and efficiency | Hit rates/isolation unverified | P1 E |
| GH-040 | Artifact/log retention | Actual usage unmeasured | P1 E/F |
| GH-041 | Hosted/self-hosted economics | Live costs and utilization unavailable | P1 E |
| GH-042 | Workflow maintainability | Large YAML; extract bounded consumers | P2 E |
| GH-043 | Environments | Effective settings unverified | P1 F |
| GH-044 | Deployments/history projection | Existing Terminal owner | P1 F |
| GH-045 | Build once/deploy digest | W2 incomplete in latest read durable record | P0 F |
| GH-046 | Attestations | Consumer verification unverified | P1 F |
| GH-047 | GHCR/package reuse | Existing registry census required | P2 F |
| GH-048 | Served build/rollback | W4 unproven in latest read durable record | P0 F |
| GH-049 | Preview environments | Need isolated data/budget pilot | P2 F |
| GH-050 | Cross-repo compatibility | Pinned Macro consumer exists | P1 F/G |
| GH-051 | Release notes/lifecycle | Must describe actual accepted artifact | P2 F |
| GH-052 | Git object/churn census | Macro size cause not measured | P0 E |
| GH-053 | Generated-data separation | Preserve existing store/consumer ownership | P1 E |
| GH-054 | Selective LFS | Need not established | P2 E |
| GH-055 | Sparse/partial fetch | Mastermind pinned sparse consumer exists | P1 E |
| GH-056 | No blind history rewrite | Many exact-SHA consumers/carriers | P0 E |
| GH-057 | Recovery completeness | Source/upload is not restore proof | P1 F |
| GH-058 | Devcontainers | Effective coverage unverified | P2 H |
| GH-059 | Codespaces/prebuilds | Usage/budget unverified | P2 H |
| GH-060 | README/onboarding | Fresh-worker journey not fully audited | P1 H |
| GH-061 | PR/issue forms | Templates exist; useful coverage unverified | P2 H |
| GH-062 | Code search/navigation | Native available; avoid duplicate CodeIntel | P2 H |
| GH-063 | CLI/official MCP | Connected surface has explicit limits | P1 G |
| GH-064 | Issue types/sub-issues/dependencies | Use implementation structure only | P2 H |
| GH-065 | Projects views | Do not duplicate Agent OS/Linear state | P2 H |
| GH-066 | Issue closure/acceptance linkage | Records/CI must not auto-close proof gates | P0 A/G |
| GH-067 | Discussions/wiki/community | No audience need established | P3 H |
| GH-068 | License/public-IP posture | No detected license; three public repos | P0 D/H |
| GH-069 | Installed App/OAuth census | Complete inventory unavailable | P0 D |
| GH-070 | Read-only evidence integration | Core #281 exists; live proof missing | P1 G |
| GH-071 | Separate publisher identity | Existing qualification dependency | P0 C |
| GH-072 | Truthful settings adapter | #264/#271 plus new type diagnostic | P0 A/D |
| GH-073 | Webhook reconciliation | Extend existing owner; no new queue | P1 G |
| GH-074 | Native evidence annotations | Exact source links; no prose authority | P2 G |
| GH-075 | Copilot bounded pilot | Entitlement and comparative value unknown | P2 H |
| GH-076 | AI-credit budgets | Actual overage/caps unverified | P1 D/H |
| GH-077 | Alternative updater | Renovate only for documented native gap | P3 D |
| GH-078 | Extra scanner/coverage | Semgrep/Codecov conditional, measured | P3 D |
| GH-079 | Super-bot combining all authority | REJECTED_BY_DESIGN | P0 G |

## Concrete local repair discovery

Source: full 620-line, 24,072-byte `scripts/github_estate_governance.py` at initial protected head. Its reconstructed local bytes matched Git blob `95bf9ff8cf9fd2885b0975ccc6ec2a29201e411a` exactly. This was not a whole-repository checkout.

`AdministrationFamily(str, Enum)` dictionary lookup accepts equal plain strings/foreign string enums, while later family branches use `is`. A lookalike can therefore skip family-specific restrictions. Six adverse cases reached the in-memory fake writer on the old source. Plain strings may then fail while constructing a receipt; foreign enums provide `.value`. Lists/dicts escape as TypeError. No live exploit or production caller was established.

Proposed minimal addition before dictionary lookup in `_assert_family_contract`:

```python
if not isinstance(spec.family, AdministrationFamily):
    raise GovernanceRefusal("administration family must be an AdministrationFamily")
```

Focused diagnostic evidence: baseline **8 failed / 16 passed**; after guard **24 passed**; compileall passed. Portable refusal/idempotence subset **21 passed**. Every transport was fake; no GitHub settings, credentials, runtime, runner or production effects occurred. Full original helper suite, repository suite, current PR-head suite and hosted CI were not executed.

Regression matrix: all three families times plain string/foreign string enum (6) must refuse before any I/O; None/bool/int/float/list/dict/empty/unrecognized/bytes (9) must yield typed refusal and zero I/O; actual enum with unsafe payload (3) must retain family refusal; actual enum with already-configured state (3) must remain zero-write. The additional three legacy successful-write controls belong only to diagnosing protected old behavior, not to the new owner contract.

**Integrate through existing #264 / #271, not a competing implementation PR.** #271 makes every current family assessment-only because GitHub does not document conditional unsafe writes for these endpoints [S30]. Its current inspected validator retains the lookalike pattern. The guard complements, but cannot replace, that architecture. Do not port legacy APPLIED/write-positive tests into the assessment-only repair. Fold the 21 refusal/idempotence cases into its existing test path, retain drift refusal with strong/weak ETags and safe permission-metadata tests, and run the actual current full suite. Capability is BUILT_NOT_PROVEN locally, not remotely integrated or production accepted.

## Bounded fanout contract

These are proposed continuation packets, not assignments or START records. Reconcile any existing started receiver, dirty/effectful worktree and exact carrier before source work. Do not use an old stopped child, old Slack thread or repo text as new assignment. For ordinary new unbound work: `RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE`, `PLACEMENT_STATE: WAITING_CAPACITY / needs_placement`. No broadcast self-claim or Chairman account-allocation fallback. Prefer Terra for bounded standard work and CTO Sol for difficult bounded integration; neither grants CEO authority. Fable is escalation only for unresolved principal-level ambiguity.

Every packet uses current same-SHA Skillpack, exact current owner sources, explicit scope/non-goals, complete input-to-user/machine journey, identity/time/null/correction contracts, deterministic acceptance, original negative discriminator, full current tests and real consumer proof. Missing permission, stale data, pagination, conflicting owner and effect-unknown remain typed blockers. Source-modifying work spanning CI/context exposure requires current source-continuity evidence. Builder and independent reviewer are separate. If a real dialogue uses a watcher, its same-carrier explicit CONTINUE/REQUEST_REPAIR/STOP and disarm law applies; none is armed here.

### A — helper assessment and family refusal

Preferred avenue Terra; principal capacity unnecessary because scope and discriminator are supplied. Existing operation `github-estate-interlock-truthful-write-safety-20260830-sol-001`, Mastermind #264/#271. Mission: malformed/lookalike families refuse before transport and every current lawful family remains assessment-only. Scope only helper plus existing `tests/test_github_estate_governance.py` unless current owner adjudicates more. Journey: actual family + exact contract + current snapshot -> already configured zero-write or explicit unsupported drift refusal. Deterministic; malformed/null values cannot widen authority. Sequence: reconcile current receiver/head; reproduce negatives; add minimal guard; retain #264 contracts; focused/full/static/current hosted tests; independent exact-head review. No admin/settings/App/publisher changes. Stop after this bounded two-path evidence result; any mutation for a current family, active collision or unknown effect is a refusal. Return exact head/tree/paths, tests, zero effects and held downstream gates.

### B — Terminal browser authority, then dependent hardening

Preferred avenue CTO Sol; difficult state/readiness diagnosis but existing bounded owner. Terminal #483, browser #485, dependent #484/#487 and later #488. Read actual current #485 carrier before edits; this study did not prove its latest state. Mission: real saved-layout create/save/reload/restore journey at relevant desktop/narrow breakpoints, with reliable readiness for the correct reason. Freeze exact producer/consumer/test paths after trace. Distinguish empty state, absent persisted data, auth/network failure, stale fixtures and not-ready UI. Pin trace/build/fixture identities. Reproduce -> negative test -> one producer/consumer repair -> first-attempt hosted acceptance -> independent real browser proof. No sleeps/timeouts/skips/force-clicks or rerun-to-green releases; no dependency megabump. Stop at #485 proof; dependent PR acceptance is a separate exact-head decision. Return original discriminator, artifact links and actual outstanding gates.

### C — native Macro enforcement and legitimate publisher

Preferred avenue CTO Sol. Existing Macro #6637/#6351 and publisher owners. Mission: deny unauthorized default-branch write while one real authorized publication succeeds. First slice reads full classic/parent/repo policy and publisher installation/consumer facts. Pin repo/ruleset/App/check identities, field delta and observation time. Missing access is not missing policy; describe any non-atomic effect honestly. Qualify producer and candidate denial -> freeze exact activation and rollback -> acquire all gates -> one carrier-bound effect -> readback -> real denied/allowed canaries. No broad bypass/App admin secret, second merge controller or blanket private flip. If current publisher, safe effect model or rollback is unknown, remain held. Lost response means same-carrier reconciliation. Stop at this transition, not downstream queue modernization.

### D — real Enterprise/security/App baseline

Preferred avenue Terra. Mission: complete permission-aware inventory, then one independently useful native control under a separate bounded freeze. Existing estate/security owners; no invented workstream. Read entitlements, effective membership/protections/security, App/OAuth scope, billing/environment and auxiliary roles via authorized admin surface. Inventory fields contain no secrets; distinguish denied/ambiguous404/inherited/absent/configured-but-unproven. Deterministic census -> owner gaps -> select one safe control -> reviewed minimum permission/effect/rollback -> positive/negative canary and audit proof. No account-model migration, mass App uninstall, purchase, private flip or blanket update. Inventory with explicit inaccessible fields is not compliance pass. Stop after census or the one approved control; return access gaps and useful next gate.

### E — measured Macro CI/runner/storage improvement

Preferred avenue Terra for evidence, CTO Sol only for a subsequent difficult frozen migration. Existing #6351/CI/runner owners. Mission: identify largest actual bottleneck and change one producer/consumer path without lost proof or data. Read-only object/churn census plus native metrics and live roster first. Preserve catch-all/selector, hosted-fork trust, reserved render capacity, pending fourth slot, PIT/correction/rights and current event/attempt identity. Statistical comparisons require comparable windows; route/selector/pass decisions remain deterministic. Baseline -> ranked costs -> source/live reconciliation -> one change -> new-root/test-only/cross-contract/trust/cancellation/cache negative controls -> real consumer/publication -> comparable after measure. No history rewrite, unrestricted candidate host, mass YAML edit or speculative savings. Stop after one evidenced improvement; return denominators and next bottleneck without auto-starting it.

### F — Terminal exact artifact and recovery

Preferred avenue CTO Sol; existing #483 W2/W4 owns source/deploy/rollback. Mission: accepted source builds once, exact digest reaches service, served identity and real user journey verified, deliberate rollback restores known version. Current served SHA was not read by this study. Freeze actual build/deploy/receipt paths and mutable-state boundaries after current source/browser gate read. Missing/tampered artifact, unauthorized environment, stale served state and failure phase are explicit. Sequence: owner/gates -> artifact contract -> producer/consumer -> negative integrity/access tests -> authorized deployment -> real browser/data proof -> rollback -> records. No moving-branch rebuild, live-directory reset/clean, secret/data replacement, false pre-copy health proof or private flip. Stop on unknown effects/current rollback identity; successful stop requires one exact deployment/rollback capability, not provenance alone.

### G — live read-only GitHub evidence for Sol

Preferred avenue CTO Sol. Parent #280, core #281, existing GH-A2 live owner. First reconcile/accept core at actual head and parent; do not copy old body green. Mission: explicit repo/PR request produces complete current blocker evidence consumed by real Sol. Scope authenticated gatherer plus accepted pure assessor and one consumer, not new API/schema/server/DB. Stable IDs, all pages, head movement, time/freshness, producer App, stale reviews and unresolved threads must remain truthful. Reconcile core -> freeze read permission/completeness -> implement -> adversarial stale/wrong-App/head race -> real held and eligible PR observations -> real Sol consumer. No merge/rerun/admin effect or hidden retry/queue. Stop at proven read capability with zero effect evidence; action execution remains separately governed.

### H — useful fresh-worker onboarding

Preferred avenue Terra. One repo and one setup/change journey per PR, current owners; Terminal authority wording belongs to #483. Mission: fresh authorized builder finds correct source/owner, installs without production credentials, runs an owned test and routes a small change for review. Scope minimal current README/setup/devcontainer/template/owner view after existing-equivalent read. Pin actual dependency/environment references; offline/auth/missing secret are explicit. Observe clean setup -> select one ambiguity -> minimum edit -> run documented commands -> independent fresh reader -> measured errors/time. No cosmetic licensing, unbounded prebuild spend, duplicate wiki/Linear/AgentOS, blanket renames or community surface without audience. Stop after one independently useful onboarding result, not product acceptance.

## Completion and continuation

This research creates a feature map, owning-carrier reconciliation, a bounded local defect reproduction and a continuation architecture. It does not make the estate upgraded. No settings/visibility/App/runner/production change, merge, worker dispatch or watcher was performed by the diagnostic/research work. Source publication is records-only and remains Draft/HOLD for review.

First primary action: reconcile #271's actual head and existing receiver, integrate family refusal in the same two-path assessment-only repair, obtain full current tests/hosted proof and independent review. Read-only admin/security/App entitlement census and Macro metrics/object census may proceed independently without touching helper/browser source. Existing Terminal #485 remains an important independent program gate.

Acceptance requires fresh reliable rights-safe truth; useful deterministic blocker/impact evidence; a real source-to-user/machine workflow with negative and rollback paths; and measured learning about first-pass reliability, queue delay, review cost and production failures. Numerical cost/speed targets follow baseline data. Never close a production gate because this report or a code PR merged.

## Evidence register

Internal evidence is point-in-time unless commit-pinned. Re-read mutable links before action.

- Mastermind repository/protected branch: https://api.github.com/repos/mastermindx-market-intelligence/Mastermind ; https://api.github.com/repos/mastermindx-market-intelligence/Mastermind/branches/master
- Macro metadata/ruleset: https://api.github.com/repos/mastermindx-market-intelligence/macro ; https://api.github.com/repos/mastermindx-market-intelligence/macro/rulesets/21813020
- Terminal metadata: https://api.github.com/repos/mastermindx-market-intelligence/mastermind-terminal
- Helper and estate source: `scripts/github_estate_governance.py` and `research/sol_capability_fabric/GITHUB_CURRENT_ESTATE_LEDGER_2026-08-30.md` at initial Mastermind pin.
- Helper authority/carrier: https://github.com/mastermindx-market-intelligence/Mastermind/issues/264 ; https://github.com/mastermindx-market-intelligence/Mastermind/pull/271
- Evidence program: https://github.com/mastermindx-market-intelligence/Mastermind/pull/280 ; https://github.com/mastermindx-market-intelligence/Mastermind/pull/281
- Terminal program/proof: https://github.com/mastermindx-market-intelligence/mastermind-terminal/issues/483 ; https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/487 ; Macro `agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md` at its initial pin.
- Macro owners: https://github.com/mastermindx-market-intelligence/macro/issues/6637 ; https://github.com/mastermindx-market-intelligence/macro/issues/6351
- Workflow evidence: each repo's `.github/workflows/ci.yml` and Macro `.github/runner-policy.yml` at the exact source pins above.

First-party feature references consulted September 5, 2026 (Cloud/general GitHub.com; do not substitute Server-only behavior):

- S02 custom properties: https://docs.github.com/en/enterprise-cloud%40latest/admin/managing-accounts-and-repositories/managing-organizations-in-your-enterprise/custom-properties
- S03 organization rulesets: https://docs.github.com/en/enterprise-cloud%40latest/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization
- S04 enterprise governance: https://docs.github.com/en/enterprise-cloud%40latest/admin/enforcing-policies/enforcing-policies-for-your-enterprise/enforcing-policies-for-code-governance
- S05 CODEOWNERS: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- S06 merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- S07 security availability: https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security
- S08 code scanning: https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning
- S09 security configuration: https://docs.github.com/en/code-security/how-tos/secure-at-scale/configure-organization-security/establish-complete-coverage/create-custom-configuration
- S10/S11 dependency grouping: https://docs.github.com/en/code-security/concepts/supply-chain-security/multi-ecosystem-updates ; https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configuring-multi-ecosystem-updates
- S12 Actions policy: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
- S13 Actions security: https://docs.github.com/en/actions/reference/security
- S14/S15 native metrics: https://docs.github.com/en/actions/concepts/metrics ; https://docs.github.com/en/actions/how-tos/administer/view-metrics
- S16/S17 environments/deployment: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments ; https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments
- S18 attestations: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
- S19 immutable releases: https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases
- S20 Packages: https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages
- S21 repository size: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
- S22 repository customization: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository
- S23/S24 Issues: https://docs.github.com/en/issues/tracking-your-work-with-issues/learning-about-issues/about-issues ; https://docs.github.com/en/issues/tracking-your-work-with-issues/learning-about-issues/quickstart
- S25/S26 Codespaces: https://docs.github.com/en/codespaces/prebuilding-your-codespaces/about-github-codespaces-prebuilds ; https://docs.github.com/en/codespaces/prebuilding-your-codespaces/configuring-prebuilds
- S27 official MCP: https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/set-up-the-github-mcp-server
- S28/S29 Apps: https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/deciding-when-to-build-a-github-app ; https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- S30 unsafe conditional writes/API practices: https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- S31/S32 current AI billing/budgets: https://docs.github.com/en/enterprise-cloud%40latest/copilot/concepts/billing/organizations-and-enterprises/usage-based-billing ; https://docs.github.com/en/copilot/tutorials/budgets/getting-started-with-budget-controls
- S33-S36 identity governance: https://docs.github.com/en/enterprise-cloud%40latest/admin/managing-iam/using-saml-for-enterprise-iam/configuring-saml-single-sign-on-for-your-enterprise ; https://docs.github.com/en/enterprise-cloud%40latest/admin/concepts/enterprise-fundamentals/choose-an-enterprise-type ; https://docs.github.com/en/enterprise-cloud%40latest/organizations/managing-saml-single-sign-on-for-your-organization/about-scim-for-organizations ; https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- V01 Renovate: https://docs.renovatebot.com/getting-started/installing-onboarding/
- V02 Semgrep: https://semgrep.dev/docs/semgrep-ci/sample-ci-configs
- V03 Codecov annotation caveat: https://docs.codecov.com/docs/github-checks
