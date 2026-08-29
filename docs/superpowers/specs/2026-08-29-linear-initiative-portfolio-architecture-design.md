# Mastermind-X Linear Initiative Portfolio Architecture

**Date:** 2026-08-29  
**Owner:** Sol / Chairman-approved portfolio architecture  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / WRITTEN-SPEC-USER-REVIEW-GATE`  
**Operation key:** `linear-initiative-portfolio-architecture-spec-20260829-sol-001`  
**Carrier:** `Mastermind:sol/linear-initiative-portfolio-architecture-20260829`  
**Protected procedure pin:** `mastermindx-market-intelligence/Mastermind@adccc544509aaa0ef7c0bb4f8bdbbfab19cf85e2`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1 compatible  
**Macro census pin:** `mastermindx-market-intelligence/macro@3ed822213caa096b8665b21ce9c3c3f5c860064f`  
**Parent architecture:** `docs/superpowers/specs/2026-08-29-project-management-operating-surface-cutover-amendment.md`

This document freezes the Chairman-approved **strategic Initiative layer** for Linear. It does not authorize any Linear mutation, Agent OS mutation, runtime action, worker dispatch, code implementation, merge, deployment or Initiative creation by itself.

It extends the existing Project-management operating-surface law rather than replacing it:

```text
Company strategic outcome
    -> Linear Initiative

Agent OS WS:<KEY>
    -> Linear Project

selected human-relevant wave / gate / deliverable / admin action
    -> Linear Issue

GitHub / Agent OS / Executive OS / Slack
    -> evidence, runtime truth, organizational truth and transport underneath
```

Linear remains a **selected human portfolio projection**. Agent OS remains organizational workstream truth. Executive OS remains Job / Attempt / Worker / Event lifecycle truth. GitHub remains implementation and proof truth. Slack remains dialogue / transport / hot-state visibility.

---

## 1. Chairman outcome

The Initiative layer exists so the Chairman can open Linear and answer a more strategic question than “what projects exist?”

The top-level view must answer:

1. what are the small number of company outcomes Mastermind-X is actively trying to achieve;
2. which durable programs/workstreams contribute to each outcome;
3. which outcomes are strategically urgent versus merely active;
4. whether each outcome is on track, at risk or off track once Sol has issued a real assessment;
5. what the current strategic frontier is for each outcome;
6. what the largest blocker or risk is;
7. what company-level dependency should happen next; and
8. what evidence changed the assessment.

The Initiative layer must not become a second workstream registry, a project-status rollup masquerading as strategy, or a classification system based on whichever market or subsystem has the most current work.

---

## 2. Product and company thesis

The governing productization thesis is:

> **Institutional depth. Retail compression. One canonical intelligence substrate.**

Mastermind-X is building one intelligence system with multiple projections, not separate retail and institutional brains.

The product moat is the compounding chain:

```text
one real-world development
-> one evidence lineage
-> one economic episode
-> one governed transmission chain
-> one company / opportunity synthesis
-> many user-specific projections
-> prospective learning
```

The company itself is also a product system. Agent OS, Executive Capacity, Chairman Control Room, CI / runner reliability and governed orchestration are not merely internal chores: they determine whether Mastermind can operate as an AI-native organization without the Chairman becoming the message bus, session monitor, project reconciler or provider-account dispatcher.

The Initiative hierarchy therefore has to represent **both** the investor-facing intelligence product and the autonomous company operating system.

---

## 3. Current estate and why normalization precedes hierarchy

Read-only census at the design pin found:

- Linear: 50 visible Projects;
- Linear: 0 Initiatives;
- Linear: 0 Initiative labels;
- Linear: 0 Project labels;
- Agent OS generated state: 54 canonical workstreams;
- canonical active / blocked / awaiting-CI / awaiting-review workstreams: 44;
- canonical done / parked workstreams: 10;
- current Linear estate includes stale status/summary projections, compatibility residue and one Project without a corresponding `WS:<KEY>` identity;
- two materially active canonical workstreams are missing from Linear: `WS:TOP-ANATOMY` and `WS:EVAL-OS-EVIDENCE-VIEW`.

The hierarchy must not encode this drift as if it were strategy.

Therefore Initiative creation is downstream of a bounded normalization pass:

```text
GitHub / proof law
-> repair canonical Agent OS only where Agent OS itself is stale
-> deterministic Agent OS -> Linear Project desired-state reconciliation
-> truthful Project normalization
-> Initiative creation
-> exact primary Initiative membership
```

No majority vote among GitHub, Agent OS and Linear is allowed. Each fact is repaired at its canonical owner.

---

## 4. Alternatives considered and rejected

### 4.1 Market / vertical hierarchy — rejected as primary architecture

Examples would be `US`, `China`, `Options`, `Crypto`, `Biotech`.

This is useful as a lens but structurally wrong as the company hierarchy because shared capabilities cross markets. China alone contains alpha research, macro context, company intelligence, SOE evidence, identity, Prophet, product experience and source-governance work. Options contributes to discovery, security analysis, timing and future portfolio intelligence.

Using markets as Initiatives would fragment the canonical intelligence substrate and encourage duplicate stacks.

### 4.2 Customer journey hierarchy — rejected as primary architecture

Examples would be `Today`, `Discover`, `Analyze`, `Monitor`, `Research`, `Portfolio`.

These are the correct product-navigation jobs, but not the correct corporate portfolio hierarchy. A program such as Market OS spans most of them. Alpha Intelligence Integration is foundational to several without being a user-facing journey itself. Eval OS is necessary for trust and learning but does not fit one navigation tab.

The six jobs remain product IA and future reporting lenses, not Initiative parents.

### 4.3 Strategic capability outcomes — selected

The chosen architecture uses a small set of durable company advantages. Each Initiative answers **why the company is investing**, while Projects remain exact durable workstreams that answer **what program is being advanced**.

This keeps transient terms such as “recovery,” “revamp,” “P0,” or a current worker lane out of the strategic layer.

---

## 5. Hierarchy and source-of-truth law

### 5.1 Initiative

A Linear Initiative represents one **company-level strategic outcome**.

It is not:

- a market bucket;
- a team bucket;
- a product page family;
- a runtime program;
- a recovery state;
- a collection of PRs;
- an automatic average of child statuses.

### 5.2 Project

A Project remains the selected Linear projection of one canonical organizational workstream (`WS:<KEY>`) unless a separately accepted architecture explicitly establishes another durable program owner.

The current deterministic `linear_portfolio_plan.py` remains the Project normalization mechanism. Initiative rollout must not create a second hand-maintained Project name / summary / lifecycle pipeline.

### 5.3 Issue

Selected human-relevant waves, gates, deliverables and Chairman/admin blockers belong as Issues under Projects according to the existing operating-surface law. This Initiative design does not widen Issue projection scope.

### 5.4 Evidence / runtime

GitHub, Agent OS, Executive OS and Slack stay underneath Linear. No Initiative field can prove runtime execution, production acceptance or product capability by itself.

### 5.5 Strategic membership authority

Until this written artifact passes the Chairman review gate and lands on protected `master`, it is the single design candidate for the seven Initiative definitions and primary Project -> Initiative membership. **After Chairman written-spec approval and protected merge, this artifact becomes the v1 canonical source for that strategic classification.**

A future implementation may encode this exact strategy in **one machine-readable static companion** if the existing projector requires deterministic input. Such a companion may contain only stable Initiative metadata and exact workstream membership. It must not contain Job/Attempt lifecycle, workstream status, Project progress, Slack state, retries or provider identity, and it must not become another organizational store.

No membership may be inferred from title similarity, Agent OS `program`, repository name, market name, current worker or recent PR volume.

---

## 6. Primary-membership law

Every eligible Project receives **exactly one primary Initiative** in v1.

Linear may technically allow more than one Initiative relation. Mastermind-X intentionally does not use multi-parent Initiative membership by default because it would double-count strategic progress and recreate ambiguity.

Cross-cutting contribution is represented through:

- dependency relationships;
- Project descriptions;
- source/evidence links;
- later bounded labels/views if a real navigation need exists.

A Project moves between Initiatives only after a strategic scope ruling changes its durable primary outcome. Touching another Initiative's consumer does not justify a second parent.

Existing completed Projects may remain attached to show strategic history. Initiative membership never reactivates a completed or parked workstream.

Missing parked / done workstreams are **not backfilled merely for visual completeness**.

---

## 7. Initiative field contract

All seven v1 Initiatives use:

```text
status: Active
lead team: MastermindX
owner: unset
parent initiative: none
sub-initiatives: none
labels: none
target date: unset
health: unset at creation
```

The Initiative priority is strategic and independent of child Project priority.

Native Linear progress rollups, if displayed, are **navigational only**. They never prove the Initiative completion ruler.

Initial metadata:

| Initiative | Priority |
|---|---:|
| Canonical Intelligence Substrate & Learning | High |
| Legendary Alpha Discovery & Timing | Urgent |
| Institutional Company & Event Intelligence | High |
| Global Markets, Regimes & Risk Command | High |
| Personal Institutional Desk | Urgent |
| Trusted Production & Customer Platform | High |
| Autonomous AI Organization | Urgent |

No target dates are invented in v1. A future target date requires an explicit planning basis rather than cosmetic roadmap pressure.

No owner is invented in v1. Durable accountability remains role/workstream based; provider seats and ChatGPT/Claude account identities are never Initiative owners merely because they executed work.

---

## 8. Initiative definitions

### 8.1 Canonical Intelligence Substrate & Learning

**Summary**

Unify identity, evidence, ontology, graph, memory and prospective evaluation into one correction-safe intelligence substrate that every Mastermind product can reuse without duplicate truth stores.

**Outcome**

Mastermind has one canonical intelligence substrate for identity, evidence, relationships, history and learning that every product can compose without rebuilding truth.

**Moat**

Exact provenance, point-in-time semantics, corrections, ontology, graph relationships and prospective evaluation compound across every new capability.

**Completion ruler**

Major product consumers can compose owner-native intelligence across multiple domains with stable identity, clocks, provenance, missing/conflict behavior and prospective evidence, without a parallel warehouse, score store or truth plane.

**Scope law**

This Initiative owns reusable intelligence capability, not individual customer interfaces and not execution lifecycle state.

---

### 8.2 Legendary Alpha Discovery & Timing

**Summary**

Make Mastermind exceptional at finding, timing and validating opportunities across markets through Prophet, options, China alpha, entry intelligence and empirically earned signal authority.

**Outcome**

Mastermind surfaces genuinely useful opportunities early enough to matter, explains their setup and timing, and earns stronger authority through prospective evidence rather than presentation confidence.

**Moat**

Multiple independent market, options, company, behavioral and timing systems converge through governed contracts while preserving distinct evidence and failure modes.

**Completion ruler**

Users can discover and monitor high-value opportunities across major markets with production-proven timing/context, honest abstention, point-in-time replay and prospective evaluation demonstrating where each signal family helps.

**Scope law**

Descriptive context, research priority, calibrated forecast and trade authority remain separate. No blended score earns authority merely because several systems agree.

---

### 8.3 Institutional Company & Event Intelligence

**Summary**

Deliver institutional-depth company and event research across earnings, filings, financials, capital structure and differentiated specialist primary-source intelligence.

**Outcome**

Opening a company or material event gives a user institutional-grade understanding of what happened, why it matters, the financial and capital consequences, specialist evidence, catalysts, uncertainties and corrections.

**Moat**

Owner-native primary-source intelligence is composed across earnings, filings, financial statements, capital structure and differentiated domain sources rather than reduced to generic summaries.

**Completion ruler**

Multiple real issuers can travel from primary source through canonical identity, event/fact extraction, financial interpretation and customer-facing Retail/Desk projections with correction-safe lineage and honest missing states.

**Scope law**

Specialist programs retain source authority. This Initiative composes depth rather than creating another company-facts truth store.

---

### 8.4 Global Markets, Regimes & Risk Command

**Summary**

Understand global regimes, rates, inflation, cycles, crypto and risk so every opportunity is interpreted inside the correct macro and cross-asset context.

**Outcome**

Mastermind continuously explains the market environment around securities and portfolios: what regime exists, what is changing, where evidence conflicts and which risks deserve attention.

**Moat**

Market, rates, inflation, cycle, liquidity, crypto and risk evidence remains independently inspectable but can be synthesized into coherent context instead of isolated dashboards.

**Completion ruler**

Current global context is production-fresh, contradiction-aware, historically grounded and consumable by security, discovery and portfolio workflows without inventing consensus where evidence disagrees.

**Scope law**

Context informs research and decision support; it does not silently become security rank, position size or trade authority.

---

### 8.5 Personal Institutional Desk

**Summary**

Unify Macro and Terminal into a persistent personal investing OS for discovery, security analysis, portfolio/watchlists, live workspaces, Brain and meaningful return loops.

**Outcome**

One user can move coherently from what changed, to opportunity discovery, to security understanding, to holdings/watchlists, to live analysis and back through useful monitoring without feeling like they crossed unrelated products.

**Moat**

Institutional-depth intelligence is compressed into a personal operating system while the same canonical objects remain inspectable at Desk depth.

**Completion ruler**

A real user can complete the Today -> Discover -> Security -> Portfolio/Watchlist -> Terminal/Brain -> return-via-change-monitoring loop across real account state, responsive surfaces and failure modes.

**Scope law**

Macro and Terminal remain distinct execution surfaces where appropriate, but they compose one customer experience and one underlying intelligence system.

---

### 8.6 Trusted Production & Customer Platform

**Summary**

Make Mastermind dependable enough to sell and trust: correct identity and entitlements, recoverable customer data, observable commercial paths, reliable releases and resilient compute.

**Outcome**

Customer- and company-critical paths behave truthfully, recoverably and predictably in production.

**Moat**

Sophisticated financial intelligence becomes commercially usable because identity, entitlements, customer state, backups, release systems, infrastructure and alerting do not silently undermine it.

**Completion ruler**

Account boundaries are correct, customer data has proven restoration, commercial failures become human-visible, normal product changes ship through reliable gates, and critical workloads survive expected machine/provider failures.

**Scope law**

Infrastructure work counts only when it unlocks or protects an observable customer/company capability. Green CI or installed infrastructure alone is not completion.

---

### 8.7 Autonomous AI Organization

**Summary**

Let Chairman set intent while Sol and governed workers operate the company through durable truth, capacity, control-room visibility and reliable orchestration—without Chairman as message bus.

**Outcome**

Chairman can direct the company at the strategic level while Sol and governed operators recover state, commission bounded work, continue stalled work and surface decisions without requiring manual session reconciliation.

**Moat**

The company itself compounds through durable organizational memory, governed AI capacity and reliable executive orchestration rather than losing decisions and work across chats.

**Completion ruler**

From Linear plus Chairman Control Room, Chairman can see material programs, accountable next-turn roles, blockers, evidence and exact next actions; Agent OS remains organizational truth, Executive OS remains runtime truth, GitHub remains implementation/proof truth, and Slack/Linear remain transport/projection rather than duplicate control planes.

**Scope law**

No second queue, lifecycle, identity, retry or memory plane may be introduced.

---

## 9. Exact Project -> Initiative membership

The mapping below is the v1 primary strategic home. `Normalization before linkage` describes a required truth repair or explicit check; it is not a new lifecycle state.

| Project / canonical identity | Primary Initiative | Normalization before linkage |
|---|---|---|
| `WS:ALPHA-INTELLIGENCE-INTEGRATION` | Canonical Intelligence Substrate & Learning | Project fields come from fresh deterministic projector output |
| `WS:GMI-THEME-GRAPH` | Canonical Intelligence Substrate & Learning | Project fields come from fresh deterministic projector output |
| `WS:STOCK-IDENTITY` | Canonical Intelligence Substrate & Learning | refresh current frontier from canonical record |
| `WS:MARKET-MEMORY-W2C` | Canonical Intelligence Substrate & Learning | refresh current frontier from canonical record |
| `WS:MASSIVE-STOCK-DAY-R2-COHERENCE` | Canonical Intelligence Substrate & Learning | Project fields come from fresh deterministic projector output |
| `WS:EVAL-OS-MEASUREMENT-LAW` | Canonical Intelligence Substrate & Learning | Project fields come from fresh deterministic projector output |
| `WS:EVAL-OS-EVIDENCE-VIEW` | Canonical Intelligence Substrate & Learning | **create missing Project from exact canonical WS** |
| `WS:EVAL-OS-T1-ENGINE-REGISTRY` | Canonical Intelligence Substrate & Learning | preserve Completed |
| `WS:EVAL-OS-OUTPUT-HEALTH` | Canonical Intelligence Substrate & Learning | correct stale Linear In Progress -> canonical Completed |
| `WS:ADVANCED-DATA-OPTIONS` | Legendary Alpha Discovery & Timing | refresh current frontier |
| `WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY` | Legendary Alpha Discovery & Timing | refresh current OA frontier |
| `WS:INTRADAY-FLOW-P0-RECOVERY` | Legendary Alpha Discovery & Timing | remain active until its declared real production proof closes it |
| `WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2` | Legendary Alpha Discovery & Timing | Project fields come from fresh deterministic projector output |
| `WS:CHINA-ALPHA-INTELLIGENCE` | Legendary Alpha Discovery & Timing | replace stale Linear P1/L0 summary with current canonical frontier |
| `WS:CN-LIMIT-ALPHA` | Legendary Alpha Discovery & Timing | refresh current DEP / execution frontier |
| `WS:PROPHET-CONDITIONAL-FUSION` | Legendary Alpha Discovery & Timing | Project fields come from fresh deterministic projector output |
| `WS:PROPHET-HK-CA-REVAMP` | Legendary Alpha Discovery & Timing | refresh presentation/intelligence split |
| `WS:PROPHET-US-AVAILABILITY` | Legendary Alpha Discovery & Timing | refresh current permanence / availability frontier |
| `WS:PROPHET-US-ENTRY-TIMING` | Legendary Alpha Discovery & Timing | Project fields come from fresh deterministic projector output |
| `WS:PROPHET-US-V4-RECOVERY` | Legendary Alpha Discovery & Timing | refresh current B1 / D5 frontier |
| `WS:LIVE-ENTRY-RADAR` | Legendary Alpha Discovery & Timing | replace stale summary with current completion-program frontier |
| `WS:BREATHING-PLATFORM` | Legendary Alpha Discovery & Timing | refresh current completion-program state |
| `WS:TOP-ANATOMY` | Legendary Alpha Discovery & Timing | **create missing Project from exact canonical WS** |
| `WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER` | Institutional Company & Event Intelligence | refresh current TFG / E3-C frontier |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | Institutional Company & Event Intelligence | reconcile any wave/merge disagreements before projection |
| `WS:CALCBENCH-FILING-FORENSICS-PARITY` | Institutional Company & Event Intelligence | canonical blocked -> Linear paused projection |
| `WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2` | Institutional Company & Event Intelligence | reconcile merged W2C/W2D versus declared completion law; refresh summary |
| `WS:DEFENSE-PROCUREMENT-V3` | Institutional Company & Event Intelligence | resolve current direct-status versus accepted-boundary wording before projection |
| `WS:BPC-JV-RECON` | Institutional Company & Event Intelligence | Project fields come from fresh deterministic projector output |
| `WS:CN-SOE-DEMAND` | Institutional Company & Event Intelligence | Project fields come from fresh deterministic projector output |
| `WS:BIOCATALYST-CORE-PRODUCT` | Institutional Company & Event Intelligence | canonical parked -> Linear paused; do not reactivate |
| `WS:BIOCATALYST-RECOVERY-V2` | Institutional Company & Event Intelligence | preserve Completed |
| `WS:EARNINGS-INTELLIGENCE-OS` | Institutional Company & Event Intelligence | preserve Completed |
| `WS:FUNDAMENTAL-FORENSICS` | Institutional Company & Event Intelligence | canonical parked -> Linear paused; do not reactivate |
| `WS:RATES-INFLATION-COMMAND` | Global Markets, Regimes & Risk Command | repair stale F0 merge/state disagreement while keeping broader program law intact |
| `WS:MACRO-CONTEXT-INDEX` | Global Markets, Regimes & Risk Command | Project fields come from fresh deterministic projector output |
| `WS:GREY-DEER-RISK-INTELLIGENCE` | Global Markets, Regimes & Risk Command | refresh after latest accepted GD frontier |
| `WS:CRYPTO-INTELLIGENCE` | Global Markets, Regimes & Risk Command | canonical blocked -> Linear paused projection |
| `WS:CYCLE-PATTERN-ISSUER-MECHANISM` | Global Markets, Regimes & Risk Command | resolve Agent OS active-but-all-waves-terminal warning before projection |
| `WS:MARKET-OS` | Personal Institutional Desk | replace stale A1A-only Linear summary with current canonical state |
| `WS:STOCK-DOSSIER-LIVE-QUOTE` | Personal Institutional Desk | replace stale “realtime proof outstanding” projection with current canonical state |
| `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` | Personal Institutional Desk | preserve Completed; reference-law history only, never production completion |
| `WS:ACCOUNT-IDENTITY-HARDENING` | Trusted Production & Customer Platform | canonical blocked -> Linear paused projection |
| `WS:CUSTOMER-DATA-BACKUP` | Trusted Production & Customer Platform | canonical blocked -> Linear paused projection |
| `WS:COMMERCIAL-PATH-ALERTING` | Trusted Production & Customer Platform | refresh current merge / proof frontier |
| `WS:CI-MERGE-CONTROL-PLANE` | Trusted Production & Customer Platform | refresh current control-plane frontier |
| `WS:RUNNER-FLEET-RESILIENCE` | Trusted Production & Customer Platform | refresh current runner / trusted-CI frontier |
| `WS:AGENT-OS` | Autonomous AI Organization | refresh current durable Agent OS frontier |
| `WS:CHAIRMAN-CONTROL-ROOM` | Autonomous AI Organization | refresh current Control Room / operating-surface frontier |
| `WS:EXECUTIVE-CAPACITY-FABRIC` | Autonomous AI Organization | refresh current Capacity frontier |

### 9.1 Deliberately unassigned exceptions

Exactly two visible Projects remain unassigned in v1 after the two missing active Projects are created.

#### `WS:WATCHLIST-PORTFOLIO-CEO`

This is a compatibility redirect, not an independent strategic investment program. Canonical continuation is `WS:MARKET-OS`; the legacy record remains active only while old readiness/fixture consumers still rely on its identity.

Rules:

- do not attach it to Personal Institutional Desk merely to make the count look complete;
- do not resume its superseded persistence architecture;
- park it when the remaining compatibility dependency is lawfully removed;
- Market OS carries the actual strategic product progress.

#### `Mastermind-X Linear OS`

Current Linear Project ID at census: `9aef6461-306a-4a3c-911b-c6a4b6635a78`.

This Project has a legitimate non-command portfolio-projection mission but no corresponding canonical `WS:<KEY>` identity, and its milestones have accumulated sister Executive-ingress / autonomous-dispatch scope that its own description says belongs elsewhere.

Rules:

- leave it unassigned until durable organizational ownership is reconciled;
- do not mint a new Agent OS workstream merely to legitimize the Project;
- remove or re-home milestones owned by sister runtime programs before assigning the remaining Project;
- do not pre-select an Initiative for the residual Project; determine its primary strategic home only after canonical organizational ownership is established;
- no Initiative assignment may be used as a substitute for that reconciliation.

---

## 10. Existing excluded workstreams that remain absent

The rollout does not backfill every parked or completed Agent OS workstream for aesthetic completeness.

At the census pin, examples include:

- `WS:DEEPVUE-INTELLIGENCE-WORKSPACE` — parked;
- `WS:CN-COMMERCIAL-SUPPLY-DILIGENCE` — parked;
- `WS:TUSHARE-ENTITLEMENT` — done.

They remain absent unless independently reactivated or a future historical-portfolio policy explicitly requires them.

If DeepVue is reactivated later, its strategic home is Personal Institutional Desk unless a newer strategic ruling supersedes this spec.

---

## 11. Project normalization law before Initiative linkage

The existing deterministic Agent OS -> Linear desired-state compiler remains authoritative for managed Project identity and lifecycle projection.

Before Initiative linkage:

1. refresh current protected Mastermind procedure and current Macro main;
2. regenerate current Agent OS state;
3. resolve direct Agent OS warnings only where canonical evidence and the declared completion law show the Agent OS record itself is wrong;
4. generate a fresh `linear_portfolio_plan.v1` against a fresh read-only Linear snapshot;
5. refuse fuzzy matching;
6. bind existing Projects by exact `WS:<KEY>` identity;
7. repair Linear as projection, never rewrite canonical organizational truth merely to match Linear;
8. create only missing currently eligible active Projects;
9. preserve done/parked historical Projects already visible, with truthful status;
10. do not interpret merge alone as proof that a proof-gated wave is done.

Current high-value normalization defects include, but are not limited to:

- `WS:BIOCATALYST-CORE-PRODUCT`: Linear In Progress while canonical workstream is parked;
- `WS:FUNDAMENTAL-FORENSICS`: Linear In Progress while canonical workstream is parked;
- `WS:EVAL-OS-OUTPUT-HEALTH`: Linear In Progress while canonical workstream is done / PROVEN_LIVE for its bounded capability;
- `WS:ACCOUNT-IDENTITY-HARDENING`, `WS:CALCBENCH-FILING-FORENSICS-PARITY`, `WS:CRYPTO-INTELLIGENCE`, `WS:CUSTOMER-DATA-BACKUP`: canonical blocked but currently projected as generic In Progress;
- `WS:CYCLE-PATTERN-ISSUER-MECHANISM`: direct/generated warning because all current waves are terminal while the workstream says active;
- `WS:RATES-INFLATION-COMMAND`: stale F0 awaiting-CI state despite merged implementation, requiring canonical reconciliation without assuming the broader program is complete;
- materially stale summaries in Market OS, Stock Dossier Live Quote, China Alpha, Defense Procurement, Capital Structure, Live Entry Radar and other fast-moving workstreams.

The repair method is current source law + declared proof law, not blind status advancement.

---

## 12. Initiative status law

Linear Initiative status vocabulary is interpreted as follows:

| Linear status | Mastermind meaning |
|---|---|
| Proposed | candidate strategic outcome, not yet Chairman/Sol-approved |
| Planned | approved strategic outcome but no currently authorized active Project is advancing it |
| Active | at least one canonical Project is materially advancing the outcome and the outcome remains company strategy |
| Completed | the Initiative's outcome-level completion ruler is proven |
| Canceled | company explicitly abandons the strategic outcome |

All seven v1 Initiatives start `Active`.

Child Project completion does **not** automatically complete an Initiative.

A recovery Project finishing does not mean the strategic outcome is complete. Conversely, an Initiative may later be completed even if historical Projects remain visible.

---

## 13. Initiative health law

Health is **unset at creation**.

The first formal Sol strategic update may set:

| Health | Meaning |
|---|---|
| On track | current strategic frontier is advancing and no known blocker materially threatens the outcome |
| At risk | a viable path exists, but a material blocker, stale capability, missing proof, authority boundary or dependency threatens progress |
| Off track | the current strategy/path cannot presently achieve the Initiative outcome without architectural, authority or product correction |

Health is a Sol strategy adjudication, not an automatic average of child status, issue count, PR count or percent complete.

A blocked child Project does not mechanically make the Initiative At risk; the blocker must matter to the strategic frontier. Likewise many green Projects cannot make an Initiative On track if the critical path is failing.

---

## 14. Initiative status-update contract

Initiative updates remain executive-level. Each update should contain these semantic fields in concise prose:

```text
Material change
Current strategic frontier
Largest blocker / risk
Next company-level dependency
Evidence / proof that changed the assessment
```

Do not dump every PR, Slack message, worker return or issue update into the Initiative feed.

Updates may link to Projects and evidence but do not become organizational or runtime authority.

---

## 15. Labels, views and cross-cutting dimensions

### 15.1 v1 label ruling

Create **zero Initiative labels** and **zero new Project labels** as part of this rollout.

Current workspace has no Initiative labels and no Project labels. Adding taxonomy labels at the same time as the hierarchy would create a second unresolved classification problem.

### 15.2 Cross-cutting dimensions remain lenses

Markets, assets and surfaces are useful dimensions, not hierarchy:

```text
Market: US / China / HK / Canada / Global / Multi
Asset: Equity / Options / Crypto / Macro
Surface: Macro / Terminal / Internal
Product job: Today / Discover / Analyze / Monitor / Research / Portfolio
```

A later bounded design may add labels only when a named human navigation/view requirement demonstrates the need.

### 15.3 Initial useful views

v1 can rely on native Initiative, Project status, Project priority and Initiative health once health is actually set.

Do not block the Initiative rollout on a custom-view or label system.

---

## 16. Application sequence

Implementation planning must preserve this order:

```text
N0  Re-pin protected procedure + current repos + fresh Linear snapshot
N1  Reconcile canonical Agent OS disagreements against GitHub/proof law
N2  Run existing deterministic Project desired-state compiler
N3  Normalize existing Linear Project identity / summary / lifecycle projection
N4  Create only WS:TOP-ANATOMY and WS:EVAL-OS-EVIDENCE-VIEW if still missing and eligible
N5  Reconcile Mastermind-X Linear OS; preserve Watchlist redirect as exception
N6  Create exactly seven Initiatives with frozen metadata
N7  Assign exactly one primary Initiative to each eligible Project
N8  Re-read all Initiatives and Projects; prove no duplicate / missing / multi-parent membership
N9  Publish first strategic status updates and only then set health where evidence supports it
N10 Durable closeout in the existing architecture
```

No later step grants authority to skip an earlier truth-reconciliation gate.

---

## 17. Failure, concurrency and reconciliation behavior

The Initiative rollout is a modifying portfolio operation and must fail closed on ambiguity.

### 17.1 Freshness

If protected Mastermind, Macro Agent OS records or relevant Linear state change materially between dry run and apply, regenerate the dry run before mutation.

### 17.2 Existing unexpected Initiative

If any Initiative with the same or confusingly similar name appears before apply, stop and reconcile exact identity. Never create a duplicate by suffixing a name.

### 17.3 Project binding ambiguity

If an existing Linear Project cannot be bound to exactly one canonical `WS:<KEY>` using the accepted binding law, do not assign an Initiative by title similarity.

### 17.4 Manual/remote edit collision

If a managed Project or Initiative changed after the read snapshot, re-read and classify the difference. Preserve meaningful manual content; do not overwrite it merely to complete the batch.

### 17.5 Effect-unknown write

If a Linear mutation response is lost or ambiguous:

```text
EFFECT_UNKNOWN
-> keep the same logical operation/carrier
-> re-read the exact target
-> reconcile whether the intended relation/object exists
-> never blind retry or fail over
```

### 17.6 Partial batch

If the operation stops after some Initiatives or memberships were successfully created, do not roll forward blindly. Re-read the exact live portfolio and resume idempotently from confirmed current state.

### 17.7 Strategy disagreement

If a workstream's primary strategic home is genuinely unclear, leave it unassigned and return to Sol/Chairman. An unassigned truthful exception is better than a neat false hierarchy.

---

## 18. Acceptance canaries

The Initiative rollout is accepted only when a fresh read proves all of the following:

1. exactly seven v1 Initiatives exist with exact names, summaries, status, priority, lead team and null owner/target/initial-health contract;
2. no parent or sub-Initiative relation exists;
3. no Initiative labels were created;
4. the two currently missing active workstreams are projected as Projects if they remain canonically eligible;
5. all eligible visible Projects have exactly one primary Initiative;
6. `WS:WATCHLIST-PORTFOLIO-CEO` remains unassigned and visibly a compatibility redirect;
7. `Mastermind-X Linear OS` remains unassigned until its canonical ownership is resolved;
8. no Project has multiple Initiative parents in v1;
9. parked/done Projects already visible remain truthful and are not reactivated by membership;
10. missing parked/done workstreams were not backfilled merely for aesthetics;
11. blocked canonical Projects are not displayed as generic healthy active work after normalization;
12. Project names/summaries/statuses match the accepted deterministic desired-state output or carry an explicit unresolved disagreement;
13. Initiative native progress is not used as semantic completion evidence;
14. no Linear mutation altered Agent OS, Executive OS, GitHub proof state, Slack dialogue state or runtime lifecycle;
15. Chairman can scan the Initiative view and understand the company's strategic bets without reconstructing the flat 50+ Project list.

---

## 19. Expected post-rollout dry-run state

Assuming the two missing active Projects remain eligible and no new portfolio objects appear before apply:

| Metric | Expected |
|---|---:|
| Initiatives | 7 |
| Parent/sub-Initiatives | 0 |
| Initiative labels created | 0 |
| Project labels created | 0 |
| Current visible Projects before normalization | 50 |
| Missing active Projects created | 2 |
| Expected visible Projects after rollout | 52 |
| Projects with exactly one Initiative | 50 |
| Explicit unassigned exceptions | 2 |
| Initiative target dates | 0 |
| Initiative owners invented | 0 |
| Initiative health invented at creation | 0 |

Expected primary membership counts:

| Initiative | Projects |
|---|---:|
| Canonical Intelligence Substrate & Learning | 9 |
| Legendary Alpha Discovery & Timing | 14 |
| Institutional Company & Event Intelligence | 11 |
| Global Markets, Regimes & Risk Command | 5 |
| Personal Institutional Desk | 3 |
| Trusted Production & Customer Platform | 5 |
| Autonomous AI Organization | 3 |
| **Assigned total** | **50** |
| Explicit unassigned exceptions | **2** |

These counts are an acceptance expectation for the current census, not a permanent quota. Future workstreams may legitimately change membership counts while the seven strategic outcomes remain stable.

---

## 20. Explicit non-goals

This architecture does not:

- make Linear canonical company truth;
- replace Agent OS program/workstream records;
- replace Executive runtime lifecycle;
- replace GitHub implementation/proof truth;
- replace Slack dialogue transport;
- create a second Project registry;
- create a new queue, retry plane, identity plane or provider-account registry;
- infer Initiative membership from titles, markets, repositories or current workers;
- create Initiatives for `China`, `US`, `Options`, `Prophet`, `Infrastructure`, `Research`, `Recovery`, `Today`, `Discover`, `Analyze`, `Monitor` or `Portfolio` in v1;
- create sub-Initiatives in v1;
- create Initiative or Project taxonomy labels in v1;
- add target dates without real planning evidence;
- assign provider seat identities as strategic owners;
- auto-set Initiative health from child statuses;
- auto-complete an Initiative because all current Projects are Done;
- reactivate completed/parked work because it was linked to an Initiative;
- backfill every historical workstream merely to make the portfolio look complete;
- authorize any Linear mutation before the written-spec review and implementation-plan gates complete.

---

## 21. Completion boundary for this spec

The design phase is complete only when:

1. this written spec is committed on its one canonical design carrier;
2. self-review finds no placeholders, internal contradictions, unresolved membership ambiguity or hidden implementation authorization;
3. the Chairman reviews this written artifact and approves or requests revisions.

Only after written-spec approval may Sol invoke the `writing-plans` procedure to create the detailed implementation/reconciliation plan.

The implementation plan must then bind exact current revisions, exact Linear Project IDs, exact Initiative mutations, fresh deterministic Project drift, idempotent reread behavior and verification canaries before any live Linear write.

Until then, this file is **design authority only** and every live Linear mutation remains withheld.
