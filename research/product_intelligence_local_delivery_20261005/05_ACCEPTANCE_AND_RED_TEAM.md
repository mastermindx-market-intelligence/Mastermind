# 05 — Acceptance, falsifiers and red-team review

Use the incumbent domain acceptance contracts first. This document supplies integration discriminators and a review checklist; it does not weaken source, rights, runtime, release or scientific gates. Candidate/test/merge/deployment facts are separately reported.

## 1. Evidence ladder

| Claim | Minimum evidence | Evidence that is insufficient |
|---|---|---|
| Research delivered | Immutable report/registration/results and qualified review disposition | A chat title, a summary saying 'done', or a newly named hypothesis |
| Implementation exists | Exact source and tested behavior at an identified candidate | Plan prose, filename alone or a generated mockup |
| Source accepted | Owner-accepted exact source/contract plus applicable integrated proof | A green historical-base suite or another owner's receipt |
| Installed | Exact release/generation at intended runtime and configured consumer | Merge, package creation or successful build |
| Product works | Real authenticated route/UI journey using intended owner source, including failure states | A standalone fixture, public screenshot or handler test alone |
| Naturally operating | A genuine permitted new source event/report crosses the actual production path | Replay, copied history, manual fixture injection or a publisher heartbeat |
| Predictive value | Admitted point-in-time study with registered baselines, trial accounting and verdict | Better prose, a diagnostic AUC, correlation or a selected anecdote |
| Local offload | Actual assigned principal plus distinct child START/return consumption and durable continuation evidence | Handoff publication, Linear assignment, shell exit, QUEUED or delivery acknowledgement alone |

## 2. Required adversarial cases

### News source and ticker journey

N-A. A provider correction arrives out of order and through both direct and mirror routes. One source item remains one item; an unqualified mirror clock cannot override a qualified direct correction. Two routes of the same source are not independent corroboration.

N-B. A story is withdrawn while its detail is open. Index, snapshot, stream and UI converge to the correct state without retaining unauthorized full text in a cache. A later restoration requires the existing qualified semantics, not any later timestamp.

N-C. A disconnect exceeds a provider replay cache or a REST page cursor repeats. Recovery emits an explicit gap/catch-up result rather than silently claiming completeness. Idempotent replay does not duplicate unread counts or stories.

N-D. A ticker changes while a prior request/stream result arrives. Old data cannot appear under the new identity. Universe membership is exact at its cutoff; share classes and unknown aliases are not silently collapsed.

N-E. The store is unavailable, the provider is silent, the market is quiet, rights expire, the user lacks the product tier, or a cursor expires. These states remain distinguishable and do not fall through to public/unrestricted fetches.

N-F. Migration defaults to non-mutating qualification, preserves legacy source/projection equality and has real backup/restore/single-writer proof before cutover. No UI request launches ingestion. Passing pure SQLite tests is not live migration proof.

### Expectations and native financial joins

E-A. Provider family names differ. A plausible `yfinance -> yahoo` mapping remains candidate-only until its owner accepts the seam. An alias known after an observation cannot identify that earlier observation.

E-B. A relative horizon label stays unchanged while fiscal period-end rolls. Do not record this as an analyst revision. Unknown fiscal year/period or share/accounting basis is not inferred from naming conventions.

E-C. Later corrections/restatements coexist with an earlier decision cutoff. Both source and transaction/recorded clocks must be applied; current alias/ontology/governance changes cannot leak backward.

E-D. Actual, guidance and consensus differ in units, currency, period length, fiscal definition, GAAP/adjusted or per-share basis. The reader refuses comparison unless the native qualification explicitly supports a transform. A price dataset cannot supply missing estimate semantics by convenience.

E-E. The raw EXP-1 capture is nonempty but its normalized baseline is null. UI and model consumers must not turn capture presence into accepted consensus or use null as zero.

E-F. A scenario derived from a valuation is underidentified or assumption-sensitive. Show a conditional scenario/range and assumptions; do not label it the market's unique expectation. Risk-neutral derivative information remains distinct from a calibrated physical probability.

E-G. A native financial component is stale, withdrawn, rights-ineligible or from a different generation. The composite answer propagates the specific refusal and cannot substitute model prose as a financial value.

### Evidence, research documents and independent sources

R-A. A report has a catalog row but no usable body, only a scan, a truncated FTS body or broken page boundaries. Catalog completeness cannot become full-text completeness. Unknown/no-text remains explicit.

R-B. PDF-byte SHA, extracted UTF-8 SHA and segment SHA differ. Exact source/extractor/segmenter identity and byte offsets reproduce the quoted span, including multibyte text and page separators. Do not compare hashes from different identity domains.

R-C. A producer process is alive but authentication or actual source freshness is absent. Health shows that distinction through existing owners. Reauthentication remains the exact existing profile's human-only ceremony.

R-D. Private raw text, derivative rights, user entitlement, model-processing permission and redistribution permission diverge. Server-side caches, API responses, logs and metadata must respect the actual purpose. Dedicated private storage isolation is not a blanket content-use grant.

R-E. Several articles repeat one release or the same report arrives through two vendors. Evidence independence is measured at the underlying information lineage; article count or a K1 relationship label alone is not independent evidence.

### Theme, tape and leadership

L-A. Source capture, assembly, publication and use occur at different times. Do not copy timestamps to satisfy an equal-clock fixture. Preserve the accepted GMI read-at-use semantics and the old reader's legitimate refusals.

L-B. A membership, taxonomy mapping or source right is only known later. A historical theme answer cannot use it at the earlier cutoff. Forward and inverse membership views must agree at the accepted generation.

L-C. Retained rotation rows lack an explicit replay marker. They are retained-unmarked, not naturally observed. Malformed rows before a requested boundary produce the typed failure; invalid rows after a declared stop boundary must not contaminate a bounded earlier read.

L-D. All AUC scores tie or invalid observations exist. Row order cannot manufacture skill, and missing/invalid populations cannot silently disappear. Repair of the metric does not retroactively revalidate every study.

L-E. A 'new' residual window duplicates another label. It cannot count as an independent test. Beta/volatility estimates, membership and benchmarks use only information allowed at the decision time; stock self-inclusion and overlapping benchmark exposure are explicit.

L-F. Daily residual strength is presented as intraday leadership, a shallow dip as confirmed fund inflow, or diagnostic AUC as a calibrated candidate probability. The product must reject those category changes without separate evidence.

L-G. A halted or stale symbol appears unusually low-volatility/strong because no new bars arrive. Missing/stale/zero-move are not equivalent. Any genuinely new intraday study must specify sessions, intervals, adjusted prices/corporate actions and time-zone/half-day boundaries before outcome access.

### Trials, verdicts and scientific authority

S-A. A TrialLedger append fails and the same process retries. Distinct-trial and budget/exposure accounting must remain correct and durable under the existing owner; a fresh local object must not erase the attempted exposure history.

S-B. A compiler/test passes but the scientific result is null, mixed, insufficient or PIT-partial. The UI retains that exact qualified verdict. Research closure is not promotion, and a positive anecdote cannot override the registered decision.

S-C. Trend Persistence B2/C1 exposed dates, dropped C2 and the rejected profile are proposed again under a new label. Reject the rerun unless there is an independently accepted, genuinely distinct prospective hypothesis and registration. Never edit a frozen registration after seeing the result.

S-D. A historical optics/cybersecurity narrative selects the eventual winners. It is a replay/falsification case, not untouched validation. Reconstruct actual knowability and coverage; do not fill historical expectation/rights/positioning gaps with current observations.

S-E. A module consuming its own downstream ranking or post-event price response appears predictive. Detect circularity and require matched-information baselines. Descriptive/user-product utility and economic predictive utility are measured separately.

### Orchestration and handoff

O-A. A request returned backend unavailable after dispatch may have become durable. Reconcile the exact original reference; never blind-retry, change keys, switch models/accounts or repackage the same effect.

O-B. A Web owner has no recent prose update but an active current branch/lease, or an old workstream says active without any actual receiver. Resolve concrete custody instead of both assuming abandonment and waiting indefinitely on a historical label.

O-C. A native worker exits zero but returns only tests or an incomplete patch. Mark the actual result, consume it, and complete/recommission only the remaining admitted slice. Do not record implementation PASS from process exit.

O-D. A plugin is published or a source capability merges but the connected action catalog/binding is unchanged. Verify publication, installation, catalog selection and execution independently. Do not create a duplicate plugin/runtime merely to avoid an incumbent gate.

O-E. Fast workers finish but reviews/returns accumulate. Limit admitted parallelism to the existing scheduler's real capacity and review bandwidth; keep one writer on shared files. A static work-package list is not a second queue.

## 3. Real-path product proof

For each user-facing slice, retain exact source/config/data generation and release refs, real API response/trace, relevant browser behavior, rights/identity context and absence of client-visible secrets. Capture the actual desktop/mobile, EN/ZH and dark/light matrix where the incumbent feature plan requires it. Use real routes and mounted components, not a replacement demo app.

The integrated answer must allow a reviewer to traverse each material statement to its source span or deterministic calculation, see native observation/decision times, inspect explicit exclusions, and reproduce the same allowed-cutoff result after a later correction. A missing component should reduce the answer's supported scope, not silently change the financial interpretation.

Natural acceptance includes a genuinely new permitted story/report/event, a separately observed correction or controlled fault appropriate to the incumbent contract, and a recovery/rollback proof where production state changes. Do not label synthetic fault injection natural data; retain both evidence classes separately.

## 4. Measurement plan

Measure capture-to-store, store-to-API, API-to-visible-client and correction-to-client latency separately with consistent native clocks. Report sample size, tested universe, provider/route, inclusion/exclusion rules and p50/p95 where the sample supports them. A source's coarse publication timestamp cannot establish precise end-to-end latency. Existing plan SLOs remain targets until measured and accepted.

Track source/report/body/identity/comparable-baseline coverage with explicit denominators; freshness of source content independently from publisher liveness; source-rights refusals; correction and replay failures; and actual consumer generation mismatch. Use the existing observability owners. Do not introduce another metrics store or silently broaden provider collection to improve the dashboard numbers.

For new research, predeclare the effect being tested, decision time, observation cutoff, baselines, costs, label horizon, overlap/embargo, multiple-testing treatment, coverage threshold, null/inconclusive rules and reader authority before viewing outcomes. Reuse existing registrations and accounting where applicable; do not invent a success threshold after the test.

## 5. Review and release protocol

Builders supply true RED/GREEN or another discriminating failure reproduction when appropriate. Independent review must be author-distinct and match the exact candidate and intended proof scope. Shared integration proof binds the actual current base/tree; unrelated source movement alone is not a reason for indiscriminate retests, but relevant changed dependencies require a fresh discriminator.

This packet is a candidate integration overlay. Its author-side consistency/link/scope checks are not independent architecture acceptance, product validation, data-rights clearance or production proof. The existing #1202/C19/domain owners must adjudicate the relevant interface/ownership deltas. Do not auto-merge or claim all-account adoption from a published handoff.

## 6. Packet acceptance checklist

- All three requested product priorities have a recovered existing plan, evidence-backed current capability and a bounded next action.
- Every first work package names its incumbent parent, allowed scope, inputs, tests, return location and actual gate.
- Stale news/EXP-1/Vault/GMI frontiers are corrected without rewriting historical evidence.
- Closed research, original missing artifacts, source-rights restrictions and effect-unknown/denied carriers are preserved.
- No second source, identity, event, theme, financial, experiment, memory, queue, watcher, scheduler or orchestration authority is introduced.
- A single eligible local principal can consume the packet without asking Chris to reconstruct the context; actual assignment, START, delegation and acceptance are not falsely claimed.
- Publication has an exact commit/readback and the existing roots receive a concise reference. Canonical Agent OS synchronization, if not performed by its lawful Macro writer, stays explicitly owed.
