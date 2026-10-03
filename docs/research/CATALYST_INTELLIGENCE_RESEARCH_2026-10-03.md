# Catalyst Intelligence System — Research Paper

**Date:** 2026-10-03
**Status:** research guidance, not production proof
**Protected-source pin:** `Mastermind@20adcaf65c2dd1bb734ab06e215feb1a0eb65659`

## Thesis

Mastermind should not rebuild Catalyst Intelligence from scratch. The estate already contains the hard ingredients: bitemporal identity/evidence infrastructure, BioCatalyst, Government Revenue/Defense, Special Situations, Mining, Earnings, Options, event-study machinery, and a mature ontology that separates event truth from timing, outcome, materiality, expectations and research priority. The failure mode is fragmentation and incomplete integration.

The finished system should be one correction-safe Catalyst truth/evaluation spine, specialist probability/economics engines, one shared expectations layer, economic propagation through GMI Theme Graph, Prophet/Options integration, and prospective learning.

Canonical chain:

`occurrence → timing → outcome probability → exposure → materiality → historical response → expectations/incorporation → conditional payoff → research priority → revision → realized learning`

Do not collapse these into a generic Catalyst Score.

## Current-state census

| Capability | State | Reuse | Missing |
|---|---|---|---|
| BioCatalyst | PARTIAL | trial/browser foundations; Macro #6712 ontology | broad WMN, calibrated timing/outcomes, economics, incorporation, prospective proof |
| Defense/GovRev | PARTIAL | GovRev app, program/budget/entity/award machinery; #7175 | end-to-end proof, prime/sub mapping, program→financial transmission, expectations |
| Catalyst Anticipation | PARTIAL/PARKED | pre-event/options/attention research | PIT risk-set model, ablations, prospective calibration |
| Unified Catalyst | SPEC_ONLY/PARKED | #6712 + #8061 | canonical shared API used by real engines |
| Special Situations | PROVEN_LIVE as source; scoring NOT_PROVEN | collector/engine/backtest | transaction identity/roles/economics, repaired evaluation |
| Semiconductor | PARKED/BUILT_NOT_PROVEN | #7870 | land shared kernel + specialist event/economics |
| Energy/Nuclear/Grid | PARKED/BUILT_NOT_PROVEN | #8002 | unstack/land + project/economics model |
| Mining/Resources | PARTIAL | mainline Mining + #8083 | ownership/royalty/stream, project state, funding/dilution |
| MedTech | SPEC_ONLY/early PARTIAL | #8182 | ingestion, identity, cohorts, reimbursement/adoption |
| GMI Theme Graph | PROVEN_LIVE infrastructure | identity + append-only bitemporal graph | economic mechanism/sign/magnitude/lag/falsifier |
| Prophet | PARTIAL | Earnings catalyst + annotations | confirm/contradict/risk/re-evaluation contract |
| Options | PARTIAL | options intelligence, IV/skew/term structure | event-conditioned expectations + incremental proof |
| Economic exposure | PARTIAL | Economic Propagation + financial primitives | event→revenue/margin/FCF/capital/valuation bridge |
| Evaluation | PARTIAL | ex-ante/realized separation, abnormal returns | one PIT Evaluation OS |
| Terminal/Paper | PARTIAL | event impact, Catalyst Window, thesis catalysts | unified Catalyst workspace |

### Continue, do not rebuild

Continue #6712 Bio V3, #7175 Defense V3, #7870 Semiconductor, #8002 Energy, #8083 Resources economics, #8087 Special Situations identity, #8182 MedTech, and #8258/#8259 evaluation repairs. Recover #8061 shared types/tests as input to the canonical contract. Historical PR prose is evidence, not current-state authority.

## Target architecture

Shared objects:
- `EventFact`
- `EventOccurrenceAssessment`
- `TimingAssessment`
- `OutcomeProbabilityAssessment`
- `ExposureRelationship`
- `IssuerMaterialityAssessment`
- `HistoricalResponseDistribution`
- `ExpectationBaseline`
- `IncorporationEvidence`
- `ConditionalPayoffDistribution`
- `ResearchPriority`
- `ThesisRevision`
- `RealizedOutcome/EvaluationRecord`

Every assessment carries `as_known_at`, effective time where applicable, source vintages, method/model version, calibration population, coverage/uncertainty, identity version, dependency group and abstention reason. Corrections supersede prior facts and never rewrite historical model inputs.

Ownership: Prophet owns technical/entry state; Catalyst owns event/outcome/economic/expectation evidence; Options owns options-derived expectations; Financial Intelligence owns cash/debt/financing/dilution; Theme Graph owns propagation; Special Situations originates horizontal corporate events; Market Memory/Evaluation owns frozen forecasts and scorecards.

Themes must become `theme/event → mechanism → company exposure → financial impact → expectation gap → security opportunity`, with typed edges carrying direction, magnitude, lag, evidence and falsifier.

## Specialist engines

**Bio:** `company↔asset↔indication↔trial↔endpoint↔regulator↔commercial rights↔competitors`. Condition PoS on phase/indication/modality/design/evidence/execution/regulatory history; materiality includes market, rights, cash and dilution.

**Defense:** `budget request→authorization→appropriation→program→opportunity→award/modification→obligation/outlay→prime/sub→revenue/backlog→margin/FCF→recognition`. Never equate award ceiling with revenue.

**Semis:** `end demand→customer capex→wafer demand→utilization/node→HBM/packaging→equipment/material→supplier economics`. Focus on HBM, packaging, utilization, capex, export controls and industrial policy.

**Energy/Nuclear/Grid:** `application→review→license→FID/finance→PPA/offtake→EPC→construction→delivery→interconnection→commissioning→operation`.

**Mining:** `exploration→resource→PEA→PFS→feasibility→permit→finance→construction→commissioning→production→ramp`; include ownership/JV, royalties/streams, capex, funding gap, commodity sensitivity and dilution.

**MedTech:** `evidence→regulatory pathway→clearance/approval→reimbursement→adoption→utilization→scale`. Regulatory success is not commercial success.

**Special Situations:** transaction-first model for M&A, tenders, reviews, spin-offs, financings and restructurings: `transaction→parties/roles→terms→conditions→timing→downside→dependencies→realized lifecycle`.

## Catalyst Anticipation

Research:

`P(material catalyst class within H | PIT public information + public market footprint)`

Separate scheduled, publicly inferable unscheduled, and genuinely unexpected events. Test residual returns, abnormal volume/liquidity, IV/term structure/skew/implied move/OI, Prophet state changes, peer/theme residuals and public-evidence intensity. For unscheduled events prefer discrete-time hazard/competing-risk designs.

Options-led discovery creates a **research candidate**, not an event fact. Catalyst-led research uses options to confirm, contradict or time. Never imply leaks or insider knowledge.

## Validation law

Freeze prediction identity, event/security identity, cutoff, source vintages, feature hash, model/training/calibration versions and abstention state. Track effective, published, ingested and corrected clocks separately.

Deduplicate/cluster linked trials, programs, transactions, issuers and security families. Use comparable matched controls, pseudo-events, factor/sector-neutral returns, walk-forward validation, untouched chronological holdouts, dependency-aware splits, effective-N, clustered/bootstrap inference and FDR control. No pre-event window may overlap the event.

Evaluate separately: occurrence, timing, outcome probability, reaction direction, reaction magnitude, expected return, time-to-repricing and adverse excursion. Use Brier/log loss/calibration/PR metrics plus abnormal return, MFE/MAE, drawdown, coverage, severe-loss rate and abstention quality.

Required baselines: base rate; momentum+volume; sector/factor; Prophet vs Prophet+Catalyst; fundamentals vs fundamentals+options; Catalyst without/with Anticipation; Catalyst without/with Theme Graph.

Prospective proof requires an append-only Catalyst Forecast Ledger containing the frozen pre-event forecast and post-event realized outcome/return path.

## Product architecture

Flagship surface: **What Matters Next**, not a calendar. Each event–issuer row exposes event, timing, outcome distribution, issuer role, economic materiality, historical response, expectation state, Prophet, Options, research priority, revision and evidence freshness.

Linked surfaces:
1. Catalyst Timeline
2. Event Studio
3. Anticipation Radar
4. Post-Event Learning

Paper consumes the same view models; it is not a parallel intelligence implementation.

## Data/PIT notes

Public cores include ClinicalTrials.gov/FDA/SEC; SAM.gov/USAspending/DoD/DSCA; BIS; FERC/NRC/DOE/ISO/RTO; EDGAR/NI 43-101; FDA device data; corporate/regulatory/court sources. Licensed layers will likely be needed for historical options, consensus, deep supply chain, normalized pipeline/procurement/project data and some reimbursement/adoption data. Every field needs rights metadata for internal use, derived output and display entitlement.

## Competitor/literature conclusion

Bloomberg, AlphaSense and Wall Street Horizon are broad benchmarks; Citeline/Evaluate/BioPharmCatalyst are Bio specialists; GovWin/GovTribe are procurement specialists; Mergermarket/The Deal are event-driven specialists. Mastermind's leapfrog opportunity is the combination:

`truth/revisions + specialist outcome model + issuer economics + historical response + expectations/options + Prophet + theme propagation + research priority + prospective learning`

Academic anchors: MacKinlay on event studies; Wong/Siah/Lo on clinical-trial success rates; Pan/Poteshman on carefully defined option-volume information. These support rigorous experiments, not semantic shortcuts.

## Highest-leverage build sequence

1. Catalyst Intelligence Contract v1.
2. Orphan-carrier adjudication.
3. Canonical Event Evaluation OS.
4. Shared PIT Catalyst store/assessment API.
5. Real cross-sector What Matters Next.
6. Finish Bio Decision Intelligence V3.
7. Finish Defense program→issuer→financial transmission.
8. Shared Expectations & Incorporation layer.
9. Preregistered Catalyst Anticipation shadow program.
10. Sector expansion factory: Semiconductor → Energy/Nuclear/Grid → Mining economics → MedTech.

## External references

- MacKinlay: https://www.jstor.org/stable/2729691
- Wong/Siah/Lo: https://pubmed.ncbi.nlm.nih.gov/29394327/
- Pan/Poteshman: https://www.nber.org/papers/w10925
- FDA: https://www.fda.gov/drugs
- SAM.gov: https://sam.gov/content/opportunities
- SEC EDGAR: https://www.sec.gov/search-filings
- FERC: https://www.ferc.gov/what-ferc-does
- NRC: https://www.nrc.gov/facilities-safety/new-reactors/advanced-reactors
- BIS: https://www.bis.gov/
- BioPharmCatalyst: https://www.biopharmcatalyst.com/
- Citeline: https://www.citeline.com/
- Evaluate: https://www.evaluate.com/
- GovWin: https://www.deltek.com/products/govwin/
- GovTribe: https://govtribe.com/
- Bloomberg Professional: https://professional.bloomberg.com/products/
- AlphaSense: https://www.alpha-sense.com/
- Wall Street Horizon: https://www.wallstreethorizon.com/
- ION/Mergermarket: https://ionanalytics.com/
- The Deal: https://www.thedeal.com/
