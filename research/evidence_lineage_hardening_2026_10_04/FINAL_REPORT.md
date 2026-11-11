# Commission 7: Evidence Lineage, Correlation & Independence Graph
## Hardened final research report — 4 October 2026

**Disposition:** retain the objective; replace the greenfield implementation prescription with an owner-native, evidence-qualified extension. This report is research and a proposed implementation contract, **not** an accepted schema change, a new runtime programme, an independence certification, or permission to alter portfolio decisions.

**Commission:** an additional audit and hardening pass over the supplied report, followed by GitHub publication. The original A–L organization is retained. Material corrections are explicit in [AUDIT_REGISTER.md](AUDIT_REGISTER.md); the supplied report is preserved byte-for-byte as [source_report.original.md](source_report.original.md).

**Original SHA-256:** `be9d6bd856b59f8bdb4fca54c36dd7c18740732c0b18b36d0185c14ead0080b5` (25,833 bytes; 175 lines).

**Immutable audit sources:** Mastermind `a2646f458f9ff41ddcedd89b338be4a4349e6cd6`; Macro `d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3`. Repository findings below describe those observations, not an unbounded claim about every branch or deployed process. External sources were checked on 4 October 2026. Source citations use **[R…]** for repository evidence and **[S…]** for primary external literature/documentation. Uncited mathematical examples and contracts explicitly proposed below are this audit's analysis, not measured market results.

---

## A. Executive conclusion

### The outcome is valid; the original build instruction is not ready to execute

Mastermind should be able to explain which observations support a decision, which outputs reuse the same observation, which apparently different inputs remain economically or statistically dependent, what was actually available at the decision cutoff, and what is still unknown. Ten renderings of one earnings release must not become ten independent confirmations. Equally, two correlated observations must not be collapsed merely because they share a vendor, ticker, sector, or short sample correlation.

The original report correctly identifies overconfidence from reused evidence, dynamic dependence, incomplete provenance, point-in-time requirements and false precision. Its central error is turning those concerns into an unconditional instruction to create a new lineage database and feed models “only independent” or one-per-cluster features. The current K1 Evidence Foundation already defines **EvidenceRef, EvidenceBlock and EvidenceRecipe**, native clocks, append-only correction semantics, typed missingness, immutable pointers, a semantic validator, and hostile fixtures. K1 expressly rejects an additional store without a measured consumer requirement. [R1, R2]

A second important correction is that **K1 does not establish independence**. It separates source independence, information novelty and economic/mechanism independence; relations remain `declarative_unverified`. Every v1 relation has `automatic_effect=false` and `deterministic_key=null`; the recipe's automatic relation set is empty. Even an `exact_duplicate` label is not suppression authority. A report proposing automatic deduplication must identify this as a separate, versioned owner decision rather than silently relaxing v1. [R1]

### Hardened recommendation

Extend the existing owners in three separately accepted layers:

1. **Traceability and truthful composition:** bind existing owner references to immutable native occurrences, revisions, feature definitions and actual computations; preserve rights, identity, clocks, contradictions and incomplete lineage. Start with one real consumer that can use a lawful same-subject composition.
2. **Descriptive dependence diagnostics:** measure declared-source overlap, sample correlation, nonlinear dependence, concentration and stability at explicit horizons and populations. Keep these separate from independence certificates, calibrated probabilities and investment authority.
3. **Earned decision use:** only after owner-approved identity/lineage contracts and a preregistered evaluation establish the benefit of a specific policy, consider changes to aggregation, selection or risk treatment through the incumbent consumer. Preserve a no-change comparator and a reversible rollout.

The first delivery must answer a real user or machine question with truthful evidence and explicit unknowns. It need not wait for PCA, causal discovery, a feature store, a graph database or a new service. Conversely, a schema, a graph picture, or a green synthetic test suite does not complete the capability.

**Acceptance ceiling:** this hardening pass establishes a better research specification and verifies mathematical counterexamples. It does not establish full source instrumentation, a working cross-owner identity bridge, current production coverage, an independently reviewed implementation, historical alpha, or a portfolio benefit.

---

## B. Current-state census

### B1. What the pinned repository actually supports

| Capability | Evidence observed | Audit disposition |
|---|---|---|
| Existing owner-native evidence contracts | K1 README names three closed contracts, vocabulary, semantic validation and pointer-only composition. | **Source-present**; do not rebuild. Source observation alone is not deployed proof. |
| Native identity, seven clock classes, correction/replay and authority rules | README gives explicit binding and refusal laws, including unknown clocks and mixed date/datetime ambiguity. | Reuse the accepted semantics; qualify each real producer separately. |
| Relations and independence declarations | Three axes are explicit; v1 does not verify them or authorize automatic effects. | **PARTIAL by design** for verified lineage/independence. Do not call declarative metadata a detector. |
| Consumer composition | `compile_recipe()` is documented as in-memory composition of caller-supplied owner-reader results, with no persistence. | Existing seam, not permission to add a universal reader or database. |
| Cross-type identity composition | The AAPL golden recipe is documented as `REFUSED / identity_unresolved`, with four excluded owner objects; v1 has no validated bridge-object slot. | Honest refusal, not a working security-level integration. A pointer index does not solve it. |
| Hostile tests | Function inventories in two existing test files include forged vocabulary, replay lookahead, automatic effects, shared upstreams, authority, corrections and denominator attacks. | Tests exist in source. They were **not executed in this pass**. |
| Universal feature instrumentation, dynamic dependence model and real Portfolio V3 consumption | Not established by the inspected material. | **Unverified**, not automatically `NOT_BUILT`, and not proven live. |

The source documentation states a `NO_BUILD_DIRECT_READERS_SUFFICIENT` physical-store verdict for the measured access question while retaining the golden composition's identity refusal. Those statements concern different capabilities and must not be flattened into either “everything works” or “nothing exists.” The quoted local fixture latency is not a production latency measurement and is not re-used here as one. [R1, R2, R4, R5]

The workstream file explicitly owns `research/evidence_mesh/`, the K1 contracts, validator and tests under **WS:ALPHA-INTELLIGENCE-INTEGRATION**. Its recorded organisational owner is Fable. That is an ownership record, not proof that a particular current session is available or that a source lease has transferred. [R2]

### B2. What is superseded or still unknown

The original claim that Mastermind has no integrated way to trace evidence is too broad. The current repository has substantial contractual machinery and owner-specific provenance. Its completeness for every current feature and consumer remains unmeasured. The original abbreviated audit commit `d1594f3…` and “months old” description are not sufficient current-state evidence; this pass does not reconstruct an unknown full historical SHA.

The earlier A0 recommendation considered a pointer observation log. The later K1 README explicitly freezes contracts without a new store unless a committed consumer has a measured failure that such persistence can cure. A0 therefore supplies historical rationale, not permission to implement its sketch in preference to the later K1 decision. [R1, R3]

The original blanket analyst-revision gap also needs qualification. The current Information→Price programme has existing source-qualification and conditional expectation-consumer carriers, Macro #8309/#8312/#8337. Their records distinguish physical capture, semantic normalization, historical availability, rights and publication. This audit neither re-accepts their evidence nor certifies those sources for a new purpose; it records that “no revisions pipeline exists” would be an unsafe instruction to rebuild. [R6]

The attachment's references to `portfolio/lenses.py`, `held_risk.py` and `brain/research_desk.py` remain **proposed consumer leads, not verified modifying paths** in this pass. No current Portfolio V3 route, callable interface, owner lease or production behaviour was established for them.

### B3. Audit boundary and reproducibility

The full supplied report, the K1 README, selected owner/workstream and earlier recommendation passages, repository inventories, and test/function inventories were inspected. A subsequent deeper implementation read covering selected validator, product-test and workstream ranges was blocked before dispatch by the tool's safety check. That read was not replayed or routed around. Accordingly, this report does **not** claim a line-by-line code audit or a fresh native test run.

The independent-of-production mathematical companion ran 18 checks successfully. “Independent-of-production” means it imports no Mastermind code; it is **author-run verification**, not an independent reviewer sign-off. Exact scope, commands and hashes are in [VERIFICATION.md](VERIFICATION.md).

---

## C. State-of-the-art research and scientific corrections

### C1. Five questions must remain separate

**Computational provenance:** what actual inputs and transformations produced this particular output? A lineage assertion can be declared, inferred from code, or observed at execution. Those are different evidence grades. W3C PROV describes entities, activities, agents and derivation; it is not a certificate that an economic causal mechanism has been identified. [S1]

**Source origination:** do two reports reproduce one originating claim, independently measure the same fact, or merely come from the same distributor? Vendor identity is neither a sufficient nor necessary duplicate key. Shared ownership or access channels can create dependence even when URLs differ. A single source can also contain many distinct facts. This audit therefore proposes claim/occurrence-grained origination, not a vendor-level vote count.

**Statistical dependence:** how does the joint distribution behave for a specified population, time scale and context? A low Pearson correlation addresses a narrow linear relationship. It does not settle nonlinear dependence, conditional dependence, tail dependence or higher-order interactions.

**Incremental predictive information:** does an input improve a specified held-out target under a specified baseline, model capacity and loss? This is a model-and-task-relative question, not equivalent to independence. Independent noise may add no useful prediction; highly correlated signals may retain a small but important difference.

**Economic mechanism:** what mechanism could connect observations, under which assumptions and counterfactuals? A source derivation arrow, a semantic similarity edge, a correlation estimate and a causal hypothesis must use different typed relations. None may silently become another.

### C2. Counterexamples that invalidate blanket orthogonality rules

For equally likely `X ∈ {-1,0,1}`, let `Y=X²`. Then `Cov(X,Y)=0`, but Y is determined by X. The joint probability at `(0,0)` is `1/3`, not the product `1/9`. The mutual information is approximately `0.9183` bits. Zero correlation is therefore not independence.

For independent fair bits X and Y, set `Z=X XOR Y`. Each pair is independent, but the triple is not: `P(0,0,0)=1/4`, whereas the product of its marginals is `1/8`. A pairwise graph or identity correlation matrix can therefore miss a joint constraint. The same example shows why screening features one at a time can miss useful interactions.

For independent, equally likely signs X and Z, define `F1=X` and `F2=X+0.01Z`. Their correlation is approximately `0.99995`, yet `100(F2−F1)=Z` exactly. Under this artificial noiseless construction, choosing only one representative destroys target information. This is a counterexample, not evidence that such a spread is robust or profitable in markets; measurement error could overwhelm it.

A sign reversal is not new information either: X and −X have correlation −1 and one linear dimension. Their average has zero variance. That demonstrates the difference between **risk cancellation** and **independent information**.

All four examples are reproduced by the companion. They replace the original prescriptions to preserve “only orthogonal information,” infer independence from ablation, or automatically retain one signal per highly correlated cluster.

### C3. PCA, ICA and CCA are distinct tools

PCA produces directions that maximize explained variance under its fitted covariance geometry. Its training-sample component scores are uncorrelated in the usual centered covariance construction. That does not establish independence, target relevance, stable future correlations, or economic interpretability. Whitening changes scale; it does not create information. Retaining both original features and their full invertible rotation as extra confirmations is double representation, not additional evidence. [S2]

ICA seeks components under an independent-source modelling assumption and related identifiability conditions; it is not interchangeable with PCA and cannot certify real market causes merely because an algorithm converges. CCA links two variable sets through maximizing correlation of projections and can be supervised with respect to returns. Consequently, all response-dependent selection and regularization belong inside training, not in the test sample. [S2, S3]

Firoozye, Tan and Zohren's 2023 published canonical-portfolios work is a relevant research lead, not proof that Mastermind should install CCA or that canonical portfolios are independent under arbitrary market distributions. Its model and evaluation cannot be inherited without replicating their relevant assumptions for the actual task. [S3]

### C4. Dependence testing must declare assumptions and power

Kernel measures such as HSIC offer ways to detect relationships missed by linear correlation. They are candidates for a controlled diagnostic study, not a licence to run thousands of tests and label nonsignificant pairs “independent.” The original HSIC paper supplies a testing method; adapting calibration to temporally dependent financial panels requires a separate design. [S4]

Conditional independence is particularly demanding. Shah and Peters establish limits for unrestricted conditional-independence testing and motivate assumption-specific methods. Thus a pass/fail regression comparison cannot certify universal independence. Record the null, conditioning set, estimator, sampling assumptions, uncertainty, test power and permitted conclusion. “Dependence not detected at this resolution” is an admissible result; “independent forever” is not. [S5]

Conditioning is also a modelling choice. Market regime may explain common dependence, but a retrospectively fitted regime can leak future data, and conditioning on a collider can create association. Do not infer causal separation from a lineage DAG, blindly partial out every available variable, or equate a zero residual covariance with causal identification.

### C5. Dynamics and interoperable lineage

Engle's DCC provides a primary research basis for modelling time-varying correlation. It does not require DCC as the first implementation: rolling estimates, shrinkage and prespecified stress slices are simpler baselines. A dynamic estimate must carry its fit cutoff, horizon, uncertainty, sample support and refresh policy. It must not automatically split families or reduce portfolio exposure. [S6]

Feast's official January 2026 announcement and versioned documentation do confirm native optional OpenLineage integration for definition changes and feature materialization. The original general statement can therefore be retained with a real citation; it is not evidence that Feast is installed in Mastermind or is the appropriate new owner. [S7]

OpenLineage's current lineage facets distinguish explicit source/target mappings and kinds of transformation dependence. This is useful interoperability vocabulary. An adapter must preserve exact edges rather than generate a Cartesian product of all job inputs and outputs. Any export remains a projection of incumbent owners, not an additional authority or completeness guarantee. [S8]

---

## D. Source landscape and admission

The original source table bundles different products and makes unsupported global assertions about history, latency, correction frequency and PIT quality. Replace those estimates with product-specific qualification. **Source availability, actual entitlement, retained history and permission for a particular use are four separate facts.**

| Source family | What can be supported here | Required admission evidence / limitation |
|---|---|---|
| Prices and corporate actions | Different price bases answer different questions; vendor record time is not a universal historical-availability guarantee. | Exact feed/product, listing and venue/session, raw versus adjusted basis, corporate-action vintage, sequence/correction semantics, missing bars and entitled use. No blanket “corrections are rare” claim. |
| Analyst estimates and revisions | Existing K3E source/consumer work must be reconciled; no provider subscription or normalized PIT history is established by this report. | Fiscal period, currency, accounting basis, analyst-count support, statistic definition, original capture/availability, rollover identity, correction semantics and rights. Do not replace public availability with retrieval time. [R6] |
| Filings and derived financial databases | An SEC filing and a commercial normalized product are distinct evidence/rights objects. | Filing accession, accepted time, immutable document/span, concept/context/unit/dimensions, reported versus restated policy, extraction version and source-owner rights. Repeated facts are not automatically revisions. |
| Options | Official IvyDB US documentation describes an EOD database beginning in January 1996; TradeFlow is a separate product with intraday interval outputs. | Name the actual product and contract before assigning latency or coverage. Quote/trade/sign/OI/expiry clocks and inferred participant intent remain distinct. No new subscription is assumed. [S9] |
| Institutional holdings, ETF holdings and flows | Form 13F reports quarterly holdings and generally has a 45-day post-quarter filing window. It is not a trade tape. | Distinguish holdings changes, valuation changes, creations/redemptions and actual cash flows. Preserve filing availability, amendments, reporting scope and entity/security joins. [S10] |
| News and narrative | Multiple distributions can repeat a single claim; a factual report and its economic interpretation are separate. | Origination, publisher, claim span, story/event and revision IDs, first observation, correction/retraction, entity roles, rights and extraction-method identity. Never create independent confirmations from model paraphrases. |
| Macro releases | ALFRED supports vintage-aware retrieval; observation date and real-time/vintage period are different axes. | Exact release and revision vintage; day-grained history cannot establish a missing intraday availability instant. Current FRED values are not automatically a historical information set. [S11] |
| Internal computations | A timestamped log can record that a job ran; it does not prove all consumed data were correct, eligible or fully logged. | Actual input digests, input selection/window/membership, code and configuration identity, model/fit artifacts, completion status and completeness denominator. |

**Rights proposal:** reuse incumbent owner-controlled purpose/tenant entitlements for capture, retention, internal analysis, display, redistribution and model processing. Unknown permission blocks the disallowed use rather than being converted to permission by a public URL. Licence withdrawal may require deletion of protected bodies: preserve only lawful audit metadata and a tombstone where permitted; “append-only” is not permission to retain material unlawfully. This report makes no legal determination or purchasing decision.

**Price of adoption:** measure engineering cost, storage, incremental latency and analyst burden against a named consumer requirement. Do not commit to a vendor, generic graph store or fixed sixteen-week programme from the source table alone.

---

## E. Canonical data model — proposed extensions, not replacement tables

### E1. Retain K1 as the reference/composition boundary

The proposed `Feature`, `Source`, `FeatureDependency`, `EvidenceFamily` and `CorrelationMetrics` tables are conceptual categories, not an approved persistence architecture. K1 references existing owner objects; the owner vocabulary preserves native keys, schemas, clock names and readers. A new central Source or Feature table could duplicate those authorities without proving a consumer need. [R1]

Use the following **logical records** only as an owner-adjudication checklist. Names below are proposal vocabulary, **not newly accepted K1 wire fields**. Where the existing closed schema cannot express a field, do not inject it into v1; place the candidate design in research, then obtain the appropriate versioned contract decision.

| Logical record | Minimum semantics | Authority boundary |
|---|---|---|
| Native observation reference | Owner, exact object/revision, supported subject/identity epoch, native digest where available, schema, clocks, missingness, rights. | Existing EvidenceRef and owner accessor. Hash match verifies bytes, not source authenticity or correct identity. |
| Feature definition revision | Formula, units, horizon, window endpoints, expected population, input roles, adjustment/session basis, code/config version. | Existing feature/producer owner. A definition is not a feature observation. |
| Computation occurrence | Definition revision, ordered or role-labelled input references and digests, actual selected population, fit/model artifacts, start/completion and result state. | Incumbent computation provenance; distinguish intended dependencies from observed consumption. No new job lifecycle. |
| Typed lineage relation | Exact endpoints, relation kind, scope, issuer/producer, supporting receipt, valid/recorded clocks, correction state and evidence grade. | Owner-issued provenance; arbitrary caller labels never authorize effects. |
| Family assignment revision | Taxonomy owner, family purpose, feature/version/horizon, manual versus estimated basis, training set/cutoff, assignment knowledge and validity. | Family membership is descriptive until the relevant consumer approves a policy. Multiple memberships do not multiply votes. |
| Dependence assessment | Inputs/versions, population/horizon/context, method and parameters, sample support, selection/missingness policy, estimate/uncertainty, fit cutoff, artifact digest and allowed use. | Research/evaluation-owned result referenced through existing accepted contracts; no timeless pairwise truth table. |
| Consumer composition receipt | Required/optional inputs, exact references and recipe, exclusions, conflicts, lineage coverage, diagnostic versions, authority and correction/rebuild linkage. | Existing EvidenceBlock/EvidenceRecipe or an approved successor, with the same machine/human source basis. |

### E2. Time semantics: availability is a set of requirements, not one timestamp

Keep K1's seven classes and each owner-native field name: `world_valid`, `source_published`, `knowable`, `observed`, `system_recorded`, `belief_or_build`, and `review_due`. Do not flatten them into a generic `as_of`. Its documented mixed date/datetime ambiguity and owner-specific required-clock rules remain binding. [R1]

A proposed computation is eligible for a particular replay only when its **mode-specific** availability, identity, basis and revision requirements are satisfied. There is no universal rule that every clock must precede a single cutoff. A future scheduled earnings date can be known today; future world-valid time alone does not make the schedule lookahead. A review deadline is not a release timestamp.

Separate three questions:

- **Actual historical decision replay:** use the exact facts, code/model versions, ingestion/recording and completed computations that were available to that system then. A source made public at 10:00 but first ingested at 12:00 cannot enter its actual 11:00 decision.
- **PIT reconstruction under a newly specified rule:** one may compute a new rule over historically admissible source vintages, with transformations fit only on the permitted prefix. Label it as reconstruction, retain its present computation time and modern code identity, and do not claim the system actually issued it then.
- **Current-rule recomputation with current knowledge:** useful for correction analysis, but not historical replay or retrospective predictive proof. K1 already distinguishes this mode. [R1]

For fitted transformations, lineage includes training inputs, training cutoff, feature-selection decisions, fitted loadings, hyperparameters and the model artifact—not only serving inputs. Historical family assignment must use the assignment known or valid under the declared replay mode. A clustering result computed using future outcomes cannot become past metadata.

### E3. Identity, relation and correction invariants

**Identity before deduplication.** Content equality, matching ticker text, a shared CIK, same event date, or a coincident numeric value is insufficient to establish a common native occurrence. Corporate actions, ticker reuse, fiscal periods, units and identity epochs can change meaning. The existing K1 refusal of unverified cross-type identity joins is preserved. [R1]

**Typed relation semantics.** Keep separate: `derived_from`, declared shared upstream, same native occurrence, same claim/event, independently measured agreement, contradiction, correction/supersession, statistical dependence and hypothesized mechanism. Map them to current vocabulary only when a semantics-preserving mapping exists. Several useful proposed relation types may require a successor contract rather than a new enum casually appended to v1.

**No equivalence by transitive correlation.** High correlation is not transitive. A can correlate 0.9 with B and B with C while A–C is 0.65 in a valid correlation matrix. A connected component at threshold 0.8 is not a set of interchangeable observations. Exact equivalence and descriptive overlap need different algorithms and proofs.

**Correction propagation.** Preserve the old observation and historical composition; append the owner correction, then recompile an eligible current consumer into a new receipt. A correction can invalidate both serving features and fitted diagnostics whose training data included the old value. A materially incomplete invalidation graph must be visible. Do not rewrite old decisions to pretend the correction was already known.

**No blanket DAG assumption.** A versioned computation-dependency graph should reject cycles for a completed finite computation. Economic feedback, successive state updates, simultaneous equations and documented iterative algorithms are different objects; represent iterations or a declared solver activity rather than mislabelling every financial graph as acyclic.

**Integrity and security.** A producer signature/attestation, when available through the existing trust owner, establishes a different property from a content hash. Untrusted text must not set authority bits, lineage IDs or licences. Traversal must be bounded, and lack of access must not leak protected node labels, counts or topology. Cache keys must include effective tenant/purpose permission and policy versions, not just a public-looking digest.

---

## F. Derived intelligence and its permitted meaning

### F1. Lineage and coverage before a score

For any consumed feature, expose its immutable immediate inputs, transitive owner-native ancestors, transformation/fit artifacts, and unsupported or inaccessible segments. Report both **required-input coverage** and the scope over which completeness was checked. “Eight of eight declared inputs are traced” is not “all true dependencies have been discovered.” A producer can omit an input; declared/observed provenance needs reconciliation tests.

Preserve separate denominators for displayed rows, admitted observations, native occurrences, declared origination groups, model-derived claims and unresolved inputs. Do not label a grouped count an “independent evidence count” unless the relevant narrower meaning is justified. A changing denominator can explain apparently increasing agreement without any new information.

A simple overlap diagnostic can compare ancestor sets, but shared roots need a typed granularity. “Both ultimately use market prices” is too coarse to make two economically different signals duplicates. Shared input at a particular security/session/window and common downstream transformations are more informative. Weighted overlap scores require prespecified weights and should remain descriptive; unknown ancestry is not disjoint ancestry.

### F2. Statistical diagnostics

For each estimate, explicitly choose one sampling unit: within-security time series, same-date cross-section, event-aligned observations, pooled panel, forecast residuals, or realized strategy P&L. These answer different questions. Pooling them without identity, time and exposure controls can create a spurious impression of redundancy or diversification.

At minimum record: universe and membership vintage; horizon; session and price basis; lookback; sample count; missing-pair policy; estimation and fit cutoffs; raw and residualized versions; standardization; uncertainty method; multiple-testing family; and stability across prespecified regimes. Constant features, too few observations, unseen regimes and unsupported clocks return an explicit unavailable assessment—not correlation zero.

Pearson/Spearman correlation, a regularized covariance estimate, limited nonlinear tests and stability diagnostics are candidate baselines. Shrinkage can improve covariance estimation under limited samples; it does not solve source dependence or create independent facts. Pairwise deletion may produce an incoherent non-positive-semidefinite matrix. Diagnose it before PCA, optimization or spectral reporting; disclose a repair/regularization rather than quietly changing the matrix. [S12]

Avoid a single `independence_score`. Prefer a vector such as: lineage support grade, source-overlap state, sample linear dependence, nonlinear-test result, residual dependence, incremental predictive value, mechanism hypothesis, uncertainty and applicability. An observation can be independent in one axis and dependent in another.

### F3. Effective dimensions are not literal independent observations

For a positive-semidefinite covariance or correlation matrix with eigenvalues `λj`, a possible concentration statistic is the **spectral participation ratio**:

`r_PR = (Σ λj)² / Σ λj²`.

Name this definition; entropy-based effective rank is a different statistic. Neither is a general count of independent random variables. The XOR example has an identity correlation matrix despite a joint constraint.

For a different and restrictive model—n equally weighted, equal-variance errors with a common pairwise correlation ρ—the variance-equivalent sample count is:

`n_eff = n / [1 + (n−1)ρ]`.

This is an illustrative variance identity, not a universal evidence multiplier or a calibrated probability. Its interpretation depends on the error model and weights; negative correlations and singular cases require particular care. With five signals and ρ=0.8, this expression is about **1.1905**, whereas the same equicorrelation matrix's participation ratio is about **1.4045**. The two numbers differ because they summarize different properties.

Do not multiply model confidence by either number, round one into a source count, or use a sign-ignoring absolute-correlation matrix as a covariance model for portfolio risk.

### F4. Predictive gain and confidence

For target Y, baseline inputs B, candidate F and context C, the conceptual target can be written `I(Y;F | B,C)`. Estimating it reliably is a separate problem. A practical alternative is a prespecified out-of-sample loss difference between equally governed models trained with B and with `(B,F)`. State model capacity, regularization, target and uncertainty; failure to improve one baseline is not proof of no information under all models.

Naively multiplying evidence likelihoods requires the relevant conditional factorization under the hypotheses being compared. Unconditional pairwise correlation is not the criterion. In a toy equal-prior example, one observation with likelihood ratio 4 gives posterior 0.8; treating three copies as separate observations gives `64/65 ≈ 0.9846`. The correct result for identical copies remains the one-observation result. This is an illustration of the error, not a probability model authorized for Mastermind.

A valid predictive model may consume correlated features without counting them as independent “votes.” Compare regularized joint models against dedup/family policies, not just a deliberately naive vote-sum strawman. Corroboration, calibration, explanatory simplicity, execution risk and portfolio diversification are separate acceptance targets.

---

## G. Mastermind integration map

### G1. Existing owners remain authoritative

| Responsibility | Existing seam or required owner | This report's boundary |
|---|---|---|
| Native observations, corrections and source rights | Respective source owners; K1 vocabulary binds native objects/readers. | Do not copy payloads into a universal lineage warehouse. |
| Canonical identity and lawful cross-type joins | Existing Data OS/owner identity contracts and validated bridges. | Do not turn a join declaration into proof or bypass the documented K1 refusal. |
| Evidence reference, block and recipe validation | Existing K1 contracts and `lib/evidence_foundation.py`, under WS:ALPHA-INTELLIGENCE-INTEGRATION. | Reuse; propose explicit versioning for changed semantics. |
| Feature computation and fit provenance | Each incumbent feature/model producer. | Instrument actual consumption; no second lifecycle or producer scheduler. |
| Statistical studies and evaluations | Existing owner-approved research/evaluation path, resolved before execution. | Register methods/splits there; do not invent a research database. |
| Consumer explanation and investment decisions | Exact incumbent Portfolio/Market OS/model consumer, once verified. | Diagnostics do not inherit rank, gate, size, originate or entry authority. |
| Product delivery, freshness and access | Incumbent publication/access and health owners. | Same accepted receipt for human and machine consumers; no parallel publisher. |

The source owns truth; the recipe composes references; a diagnostic assesses a specified relationship; the consumer's approved policy decides what that assessment can affect. A single convenient service must not silently inherit all four roles. [R1, R2]

```text
Owner-native observations / identity / rights / corrections
            │ existing owner accessors and validated references
            ▼
Incumbent feature or model computation
  └─ actual input and fit provenance (where not already supplied)
            │
            ├────────► bounded, versioned dependence diagnostics
            │                        │ research/context only initially
            ▼                        ▼
Existing EvidenceRef → EvidenceBlock → EvidenceRecipe / approved successor
            │ exact subject, clocks, denominators, conflicts, authority
            ▼
One named existing consumer → existing publication and access owner
```

### G2. Choose the first consumer by a provable seam

Do not start with “every signal everywhere.” Select one current user question for which the owner can supply lawful same-subject evidence—for example, showing how multiple displayed features reuse one owner-native earnings observation. The exact consumer and source path must be named in its implementation pickup; this report does not invent a functioning Portfolio V3 API.

The documented cross-type AAPL golden recipe may instead serve as a **negative acceptance case**. Until the owner supplies an accepted bridge input and validation route, it must remain refused. Starting with a positive same-subject fixture must not be advertised as solving that broader identity problem. [R1]

A useful initial output would say, in substance: “These displayed items cite two native observations; three are transformations of one observation. Source independence is unverified. One optional source is unavailable; this is not four independent confirmations.” Values must come from actual receipts, not that illustrative wording.

### G3. No policy laundering

Preserve all current K1 authority flags as false. Displaying an evidence assessment is not permission to change alerts, rankings, entry availability, capital sizing, or trade instructions. A dashboard warning may also change behaviour; consumer owners must explicitly define whether it is an informational explanation or a decision-affecting alert.

A future verified duplicate contract would require owner-native key semantics, origin authentication, correction rules, same-claim scope, collision resistance, identity proof and hostile tests. Even then, counting a duplicate once for one consumer does not imply deletion from the source ledger or suppression of a contradictory occurrence. None of that authority is granted by this report.

---

## H. Empirical validation programme

### H1. Four verdicts, not one success label

Keep separate: **contract correctness**, **source/temporal admissibility**, **empirical usefulness**, and **production consumer acceptance**. Passing the first cannot override failure of another. A negative predictive result is scientifically acceptable; accurate provenance may still justify adoption for auditability. Conversely, an apparent Sharpe improvement cannot excuse forged lineage or time leakage.

The present pass's 18 mathematical checks prove only the stated finite counterexamples. They do not execute any of the future acceptance cases below against Mastermind. Existing test names are not substituted for fresh results.

### H2. Required contract and adversarial acceptance matrix

The following is a **proposed future test specification**. All rows require implementation-specific execution and receipts before being called passed.

| Case | Required result |
|---|---|
| One source occurrence exposed through several feature views | Preserve all inspectable views and original observation; do not create new independent confirmations or automatic v1 suppression. |
| Same bytes, different native identity/context | No dedup solely from bytes; require lawful occurrence/claim equivalence. |
| Same ticker after listing/identity-epoch change | Refuse ambiguous join; no historical cross-entity merge. |
| Shared vendor but distinct independently measured facts | Do not blanket-collapse the vendor into one fact. Preserve narrower dependence uncertainty. |
| Different vendors syndicating one primary claim | Expose the common origin when proved; URL diversity does not certify independence. |
| Rehashed caller-authored relation or forged deterministic key | Existing v1 rejects automatic effects; any successor must authenticate owner-issued scope and receipt. |
| Three-axis disagreement | Preserve source, novelty and mechanism assessments separately; no scalar laundering. |
| Pairwise-independent XOR and nonlinear zero-correlation examples | Diagnostic claims remain within tested scope; never infer mutual independence from the pairwise graph. |
| Near-duplicate with useful target difference | No destructive cluster reduction without task-specific evaluation. |
| Correlation-chain connected component | Do not treat threshold connectivity as exact equivalence. |
| Unknown/constant/insufficient data | Explicit unevaluable state, not zero correlation, zero risk or positive support. |
| Contradictory observations | Both remain inspectable with a conflict state; no majority vote or silent netting. |
| Future publication/capture/recording added after a past cutoff | Actual historical output remains unchanged under the appropriate clocks. |
| Future event announced before cutoff | Future event date alone does not exclude already-known schedule context. |
| Date-only source matched to intraday decision | Refuse unsupported ordering; no invented midnight or end-of-day time. |
| Correction or withdrawal | New eligible receipt; original decision preserved; dependent current computations and fits are invalidated/rebuilt as specified. |
| Historical family definitions or fitted transforms | Future training/assignment information cannot enter an earlier fold. |
| Required versus optional missing/rights-blocked inputs | Required input refuses its consumer path; optional absence degrades exactly as the recipe specifies. |
| Cross-type AAPL composition without accepted bridge | Preserve the documented identity refusal. |
| Undeclared input and failed/partial computation | Mark lineage completeness honestly; no successful output with fabricated full ancestry. |
| Different tenant or purpose; access revoked | No payload, topology or cached-result entitlement leakage. |
| Permutation, batching and repeated reads | Semantically identical inputs give stable identities/results except explicitly non-identity observation logs. |
| Graph cycle/oversize/pathological input | Typed refusal or bounded truncation with visible incompleteness; no unbounded traversal. |
| Diagnostics disabled/unavailable | Existing lawful consumer behaviour is preserved; no hidden ranking, sizing, gating or alerts. |

### H3. Preregister a task, not “does orthogonalization improve Sharpe?”

Before opening protected outcomes, obtain an owner-approved experiment record naming: decision/forecast task; unit of analysis; security/event population; country/session/horizon; label and maturity; information/replay mode; allowable sources and rights; cohort/split identifiers; existing exposures to those outcomes; model-selection budget; primary loss; materiality and noninferiority margins; multiple-testing family; power analysis; stop rules; and permissible conclusions.

Do not import any unrelated programme's AUC, acceptance, rejection or source qualification. This pass reports no historical market score and does not retune any existing detector.

Recommended comparator structure:

- **Incumbent unchanged consumer/model**, with its actual treatment of correlated inputs.
- **Traceability-only addition**, with unchanged predictions/actions, to measure correctness and operational value independently of a statistical policy.
- **Owner-approved exact-identity handling**, only after the separate deterministic-key/automatic-effect gate is accepted. Until then, its evaluation is a hypothetical policy study, not a live v1 change.
- **Dependence-aware candidate**, such as a regularized joint model, family pooling or carefully trained projection, with comparable model-selection budget and a clearly specified target.

Raw-plus-component duplication is a hostile comparator, not the default candidate. A naive vote-sum model may illustrate a problem but is not a sufficient benchmark against a competent incumbent.

### H4. Time, sampling and leakage controls

Use chronological outer evaluation. Fit scaling, imputers, feature selection, family clustering, covariance, PCA/ICA/CCA, hyperparameters and calibration on permitted training data only. Preprocessing fitted before a split leaks test information even without directly reading the target. [S13]

Purge training observations whose outcome intervals overlap the evaluation interval. Define any additional embargo from the actual horizon/information structure and record it; an arbitrary fixed gap is not automatically sufficient. Group related manifestations, revisions and syndicated claims so the same originating event cannot appear as a fresh independent example in both train and test.

For panel studies, use date/event/security-aware resampling and uncertainty appropriate to the claimed estimand. Repeated overlapping returns do not create an equal number of independent observations. Specify an effective-support/power rule rather than a universal minimum sample count. Stress/regime labels must be obtainable under the declared information mode, or honestly labelled retrospective diagnostics.

Reserve an untouched final temporal evaluation only if one truly remains. If historical outcomes have already influenced hypotheses, label the study exploratory and require prospective evidence for stronger claims. A modern language model annotating old text can import later world knowledge through its parameters; historical text cutoffs alone do not prove PIT semantics. Record model/version/context, audit leakage, and prefer prospective first-seen evaluation where historical independence from future knowledge is not defensible.

### H5. Metrics and promotion gates

**Integrity:** accepted-input lineage coverage, unknown ancestry rate, identity refusal rate, correction propagation completeness, replay invariance, contradiction preservation and denominator accuracy. Use hard invariants for forbidden effects rather than improving averages.

**Predictive utility:** prespecified proper loss/calibration measures for probability forecasts, task-relevant ranking metrics where applicable, effect size and uncertainty, cohort/era stability, and incremental value versus the unchanged incumbent. A probability requires its own calibrated derivation, not a rescaled 0–100 score.

**Portfolio outcomes, only when in scope:** net-of-cost returns, drawdown, turnover, exposure, liquidity/capacity assumptions and tail behaviour from the same execution model. Distinguish return correlation from evidence dependence. No need to trade or change allocation merely to verify lineage.

**Operations:** actual consumer p50/p95 latency and load, availability, storage/compute cost, incremental analyst burden, access-isolation failures and recovery/correction lag. Compare to a named requirement, not an invented SLA.

Promotion requires all hard integrity/source gates, prespecified empirical acceptance where a policy changes, independent exact-head review, current hosted checks, accepted producer→consumer proof and a tested rollback. Numerical performance thresholds are intentionally not fabricated in this report: consumer owners must freeze them **before** protected outcome access.

---

## I. Risks, falsifiers and failure modes

**False independence from incomplete lineage.** A graph missing a shared input looks reassuring precisely when it should be unknown. Mitigation: grade observed versus declared provenance, retain coverage denominators, audit sampled actual reads against declared inputs and propagate unsupported segments.

**Information destruction from coarse grouping.** Same-family signals at different horizons, measuring different mechanisms or retaining useful spread information can be lost. Mitigation: prespecified incremental-value and interaction tests; preserve originals; use reversible consumer policies rather than rewriting source history.

**Source multiplicity laundering.** Aggregators, paraphrases, model summaries and downstream feature views can multiply one claim. Mitigation: typed origin scope and derivation refs; narrative similarity is only a candidate match until supported by an owner receipt.

**Apparent disagreement hidden by dedup.** Competing measurements can be mistaken for duplicate errors. Mitigation: exact context/unit/period identity, contradiction preservation, and deterministic tests that a conflict is not turned into support or absence.

**Overfit dependence estimates and regime labels.** Searching windows, kernels, clusters, factors and eras can select a convincing history. Mitigation: bounded preregistered candidate families, train-only transforms, uncertainty that respects sampling dependence, and an honest exploratory/confirmatory distinction.

**False confidence from semantic authority leakage.** A descriptive “independence group” can be consumed as a rank bonus or entry permission. Mitigation: closed contracts, explicit consumer mapping and all-false authority until a separate accepted policy exists.

**Expensive infrastructure without a consumer.** Metadata can become a second catalogue, persistence plane or lifecycle. Mitigation: start through existing direct readers; require the K1 physical-store flip conditions and measured need before introducing persistence. [R1]

**Security, privacy and licence leakage.** Pointer graphs and shared caches can disclose non-public research inputs even without raw bodies. Mitigation: access checks on traversal, topology and outputs; purpose-bound caching; no unsupported “public because URL is public” rule.

**Falsifiers / stop conditions:** stop a candidate policy that fails the prespecified noninferiority or stability gate; stop a numerical study when source eligibility or power is insufficient; stop a new-store proposal when existing readers satisfy the named requirement. Preserve useful traceability work even when a predictive hypothesis fails. Do not keep retuning until one variant passes, and do not relabel `NON_EVALUABLE` as a demonstrated empirical null.

---

## J. Build priority

**P0 — truth and safety of the existing seam.** Correct the research instructions; resolve the exact consumer and current custody; preserve K1 v1 authority, identity and correction laws; demonstrate one real source→reference→composition explanation plus adverse states. Document where lineage is unknown. No new store or universal vote filter.

**P1 — versioned provenance and diagnostics where a real gap is measured.** Extend the incumbent producer's observation/fit lineage where missing; qualify the statistical panel; implement descriptive measures and their applicability/uncertainty through owner-approved contracts. The research result may be that a subset is not evaluable.

**P2 — empirically earned consumer policy and exploration UI.** Introduce a specific dependence-aware policy only through the existing decision owner after its experiment passes. Add useful human inspection and correction navigation on the same machine receipt. A graph explorer is not an alternative evidence authority.

**Defer:** causal discovery automation, general ICA/CCA deployment, all-pairs high-dimensional nonlinear testing, mandatory feature-store adoption, new graph databases, and LLM-inferred provenance as ground truth.

**Reject:** a universal “independence percentage,” an opaque master evidence score, “one per correlated cluster” as a global rule, automatic K1 v1 suppression, copy-based lineage warehouses, and any guarantee of never double-counting unknown dependencies.

---

## K. Proposed implementation phases — exit gates instead of invented weeks

| Phase | Bounded work | Exit evidence |
|---|---|---|
| K0: owner/consumer qualification | Re-pin protected procedure and relevant source, live custody and pending effects; select a lawful existing consumer; identify missing contracts. | Exact owner/carrier, read/write scope, immutable sources, user/machine question and approved no-effect ceiling. |
| K1: real traceability slice | Compose existing admissible refs for that consumer; preserve original observations and explain actual derivations, unknowns and contradictions. | Same-source human/machine output, negative identity case, missing/rights/conflict cases, no policy delta and no second store. |
| K2: provenance gap closure | Add only absent producer-native occurrence/fit metadata under approved schema/version; do not reconstruct unsupported past certainty. | Exact input/code/config/fit receipts; sampled consumption reconciliation; correction and cutoff-extension invariance. |
| K3: descriptive dependence | Build an admissible panel and train-only diagnostics for specified horizons and populations. | Reproducible estimates, uncertainty, support/refusal states and prospective or labelled retrospective applicability. |
| K4: controlled policy study | Execute the preregistered unchanged/incumbent and candidate comparisons. | Frozen outcome access, trial accounting, preserved nulls, uncertainty and a scoped PASS/FAIL/NON_EVALUABLE result. |
| K5: accepted rollout | Independent review, current checks, owner-admitted deployment/canary and existing rollback path. | Actual producer→consumer production receipts, adverse/rollback proof, current owners and durable closeout. |

These are dependency gates, not six new workstreams. A blocked cross-type bridge does not prevent lawful same-subject diagnostic work, but it remains a blocker for claims requiring that bridge. A report or fixture cannot bypass an owner-admission or production gate.

---

## L. Exact implementation handoff

### Revised Commission 8 — owner-native evidence traceability and dependence qualification

**Mission:** extend the existing Evidence Foundation and one verified consumer to explain reused, dependent, conflicting and unknown evidence without creating a new evidence engine, source store, identity authority, scorer, scheduler or lifecycle.

**Existing programme:** WS:ALPHA-INTELLIGENCE-INTEGRATION, with the current K1 source owner and incumbent native producers/consumers. The recorded owner role is not an automatic current lease. Recover actual custody before modifying any owned path. The earlier report's generic “data platform team / Chief Data Officer” assignment is not accepted as current Mastermind ownership. [R2]

**Read first:** the current protected Mastermind procedure; current K1 README/contracts/vocabulary; the two native test suites; the applicable producer and consumer contracts; and current same-path PR/carrier/effect state. The pins in this report are audit evidence, not permission to ignore a newer relevant contract. Preserve active adjacent work such as Information→Price and financial lineage rather than rebasing it into this programme. [R6, R7]

**First bounded implementation objective:** produce one read-only consumer explanation from existing owner-issued refs with a lawful same-subject identity, truthful row/origination/unknown denominators, original contradiction/correction states and all current authority flags false. Reuse the existing recipe and access/publication path where sufficient. Also demonstrate that the unbridged cross-type negative case remains refused. If no existing consumer can accept that shape, return the exact contract/owner decision required—do not mint a generic replacement service.

**Explicit holds:** no automatic deduplication; no changed ranking/gating/sizing/entry; no claim that PCA creates independent evidence; no retrospective public timestamps invented from fetch times; no shared store; no silent bridge; no owner-payload copying; no source-policy or licence upgrade; no market-performance claim from fixtures.

**Required deliverables:** exact consumer/source map; owner-admitted schema deltas only if needed; an existing-path vertical slice; adversarial tests with real commands and source identities; correction/replay and denominator receipts; descriptive diagnostic protocol; independent exact-head review; and rollout/rollback proof when production is actually commissioned. Test count, documentation completeness and production acceptance must remain separate.

**Future automatic effects gate:** should a consumer demonstrate a genuine need for counting or suppressing proved duplicate occurrences, take a separate versioned proposal to the K1/consumer owners. It must bind an authenticated native deterministic key, exact scope, identity, correction lineage, conflicting-fact handling and effect ceiling. Existing v1 refusal remains the baseline until acceptance.

**Completion statement:** the user and machine can inspect the exact admitted evidence supporting the named consumer, see reuse and unsupported independence honestly, recover what was available at the decision cutoff, and trace later corrections through the existing owners. Any later dependence-aware decision policy must additionally satisfy its own empirical and rollout gates. This is a verifiable scoped outcome—not a guarantee that every unknown dependence in markets has been eliminated.

---

## Source register

### Repository evidence — pinned unless expressly marked as live carrier metadata

**[R1] K1 Evidence Foundation README.** Source of current contract, clock, authority, identity, physical-store and golden-recipe assertions. Inspected at Macro `d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3`.
https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/contracts/evidence_foundation/README.md

**[R2] WS:ALPHA-INTELLIGENCE-INTEGRATION.** Selected pinned ownership/path and K1-status passages, not proof of live custody.
https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md

**[R3] A0 Minimal Evidence Mesh Recommendation.** Historical pointer-layer rationale; later K1 no-store decision governs the described K1 scope.
https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/research/evidence_mesh/A0_MINIMAL_EVIDENCE_MESH_RECOMMENDATION.md

**[R4] Evidence Foundation validator.** File/function inventory inspected; deeper selected implementation read was blocked and not retried. Not a full code-audit or execution citation.
https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/lib/evidence_foundation.py

**[R5] Existing contract/product test inventories.** Function names inspected, including adversarial and negative cases. Not rerun by this pass.
https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_evidence_foundation_contract.py
https://github.com/mastermindx-market-intelligence/macro/blob/d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3/tests/test_evidence_foundation_product_contract.py

**[R6] Information→Price / K3E existing carriers.** Current issue/search records inspected 4 October 2026; dynamic coordination references, not immutable source acceptance or audited runtime results.
https://github.com/mastermindx-market-intelligence/macro/issues/8309
https://github.com/mastermindx-market-intelligence/macro/pull/8312
https://github.com/mastermindx-market-intelligence/macro/pull/8337

**[R7] Adjacent financial lineage carrier.** Open PR metadata returned in the current search; no code changes or new test results independently verified here. Preserve incumbent ownership and fixture/production distinction.
https://github.com/mastermindx-market-intelligence/macro/pull/7518

**[R8] Protected procedure.** Mastermind pin used for this research publication: Skillpack 1.0.1, minimum bootstrap major 1; INDEX SHA-256 `608aebc84a106f4e3c687f020a7f0e69af88f38e014d4664a376e2be2ddfa220`.
https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/sol_skills/INDEX.md

### Primary external evidence — inspected 4 October 2026

**[S1] W3C, PROV-DM (Recommendation, 30 April 2013).** Provenance entities, activities, agents and derivations; not economic causal identification.
https://www.w3.org/TR/2013/REC-prov-dm-20130430/

**[S2] scikit-learn, Decomposing signals in components.** Official PCA/ICA modelling and transformation documentation. Live documentation version may change; no package version is adopted by this report.
https://scikit-learn.org/stable/modules/decomposition.html

**[S3] Firoozye, Tan and Zohren, “Canonical portfolios: Optimal asset and signal combination,” Journal of Banking & Finance 154 (2023), 106952.** Primary author/institution record and paper abstract; preprint first appeared in 2022. This pass did not reproduce its experiments.
https://discovery.ucl.ac.uk/id/eprint/10163895/
https://arxiv.org/abs/2202.10817
https://doi.org/10.1016/j.jbankfin.2023.106952

**[S4] Gretton et al., “A Kernel Statistical Test of Independence,” NeurIPS 2007.** Primary proceedings abstract for HSIC testing, not a validated temporal-panel implementation.
https://papers.nips.cc/paper/2007/hash/d5cfead94f5350c12c322b5b664544c1-Abstract.html

**[S5] Shah and Peters, “The hardness of conditional independence testing and the generalised covariance measure,” Annals of Statistics 48(3), 2020.** Primary authors' preprint abstract; unrestricted testing limitations must not be overstated as impossibility under every restricted model.
https://arxiv.org/abs/1804.07203
https://doi.org/10.1214/19-AOS1857

**[S6] Engle, “Dynamic Conditional Correlation,” Journal of Business & Economic Statistics 20(3), 2002, 339–350.** Publisher's primary abstract. Its later online-posting date does not change the 2002 publication year.
https://doi.org/10.1198/073500102288618487

**[S7] Feast, official OpenLineage announcement (29 January 2026) and versioned integration documentation.** Confirms the optional integration; no Mastermind installation or adoption inferred.
https://feast.dev/blog/feast-openlineage-integration/
https://docs.feast.dev/v0.60-branch/reference/openlineage

**[S8] OpenLineage, official lineage dataset/job facets.** Explicit field/dataset mappings and transformation roles; interoperability reference rather than a new canonical plane.
https://openlineage.io/docs/spec/facets/dataset-facets/lineage/
https://openlineage.io/docs/spec/facets/job-facets/lineage/
https://openlineage.io/docs/spec/facets/dataset-facets/column_lineage_facet/

**[S9] OptionMetrics official IvyDB US and TradeFlow product descriptions.** EOD versus distinct intraday product, not confirmation of Mastermind's entitlement or retained history.
https://optionmetrics.com/united-states/
https://optionmetrics.com/ivydb-tradeflow/

**[S10] SEC Investor.gov, Form 13F reports.** Quarterly holdings and filing timing; not transaction-flow coverage.
https://www.investor.gov/introduction-investing/investing-basics/glossary/form-13f-reports-filed-institutional-investment

**[S11] Federal Reserve Bank of St. Louis, ALFRED download help and FRED real-time-period API documentation.** Observation/vintage semantics and historic information sets; not missing intraday-clock proof.
https://alfred.stlouisfed.org/help/downloaddata
https://fred.stlouisfed.org/docs/api/fred/realtime_period.html

**[S12] scikit-learn, Covariance estimation.** Official empirical/shrinkage covariance guidance. Coherence/PSD checks and the numerical counterexamples in this report are the audit's proposed controls and derivations.
https://scikit-learn.org/stable/modules/covariance.html

**[S13] scikit-learn, Common pitfalls and recommended practices.** Train/test separation and preprocessing leakage. The event/panel purge, trial-accounting and model-knowledge cautions are this audit's proposed protocol, not claims that this page implements those controls.
https://scikit-learn.org/stable/common_pitfalls.html

**Source hygiene:** the original unsourced quotations, generic industry claims and dangling references “[52]” and “[53]” are not carried forward as evidence. Primary-source verification confirmed the Feast integration claim; other prescriptive conclusions are either corrected above or explicitly proposed for testing. No proprietary datasets, credentials, private runtime logs or paid source bodies are included in this publication.
