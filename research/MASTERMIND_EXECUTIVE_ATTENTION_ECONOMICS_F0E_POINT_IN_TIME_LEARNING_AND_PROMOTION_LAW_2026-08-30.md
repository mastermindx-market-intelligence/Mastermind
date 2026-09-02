# Executive Attention Economics — F0E Point-in-Time Learning & Promotion Law

**Operation:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Parents:** F0/F0A/F0B/F0C/F0D  
**Status:** `ARCHITECTURE FREEZE / SPEC_ONLY / RECORDS_ONLY`

## 1. Why this amendment exists

The Chairman outcome is not "produce a plausible ranking." It is to materially reduce Chairman interruption and Meta-CEO cognitive load **without missed high-severity decisions or hidden stalled work**.

A naïve shadow test can make almost any prioritizer look good by:

- replaying old decisions with current corrected facts;
- counting only demands whose source fields are complete;
- labeling everything uncertain as low priority;
- reducing notifications while ignoring misses;
- measuring card-count compression but not decision latency/starvation;
- using final outcomes that were unavailable at decision time;
- treating an absent record as proof no attention was needed.

Therefore promotion needs a point-in-time counterfactual ruler.

## 2. Point-in-time law

Any historical/counterfactual EAF evaluation must use only facts that were lawfully observable at the evaluation instant.

For a decision/attention time `t`:

- use the Agent OS revision/effective records available at `t`, not today's repaired summary;
- use Executive/Wake events with event/effective times <= `t`;
- preserve corrections as later events rather than backdating their knowledge;
- use the RuntimeBinding/turn/placement state that existed at `t`;
- do not use later PR outcomes, incident resolution, human decisions or future source data as factor inputs;
- later outcomes may be used only as **labels/evaluation evidence**, never as contemporaneous model inputs.

If a required historical input cannot be reconstructed point-in-time, that replay case is `UNREPLAYABLE_INPUT_GAP` for that factor/case. Do not substitute current truth.

## 3. Shadow evaluation units

The atomic evaluation unit is a source-attributed **attention decision episode**, not a notification count.

A shadow episode should bind:

- snapshot/evaluation instant;
- canonical authority partition;
- raw valid attention obligations present;
- exact root bundles;
- EAF dispositions/frontier/omission receipts;
- actual executive intervention/delivery/ACK when existing source owners record it;
- later ground-truth outcome/incident/decision receipts used only for evaluation;
- source coverage and replayability gaps.

Do not create a new production lifecycle store to persist these. During A2/A5, use existing point-in-time event/history owners plus bounded GitHub evidence/report artifacts or an already-authorized analytics plane.

## 4. Core metric families

No single KPI decides promotion. Report the following families together.

### 4.1 Demand coverage

- raw explicit valid attention obligations observed;
- percent with resolvable canonical identity;
- percent with resolvable authority;
- percent with source-backed ready/actionable time;
- percent with structured deadline/window where one is claimed;
- percent with usable wait/autonomy/dependency/actual-impact evidence;
- `RECONCILE_FIRST` rate by reason;
- historical replayable vs unreplayable fraction.

A low-volume frontier with poor admission coverage is a failure, not efficiency.

### 4.2 Compression and fan-in

- raw obligation count;
- exact-root count after lawful fan-in;
- active frontier root count;
- bundle compression ratio;
- every suppressed member receipt coverage;
- semantic-similarity false-fan-in count (must remain zero in accepted corpus).

### 4.3 Interruption safety

For accepted ground-truth critical episodes:

- `INTERRUPT_NOW` recall;
- missed severe decision count;
- authority-escalation violations;
- independent interrupt roots hidden by compaction;
- stale/unknown critical cases incorrectly presented as confident action.

The accepted canary invariants remain zero missed accepted interrupts and zero priority-driven authority escalations. Real-world ground truth may require post-hoc adjudication; preserve that adjudication as evaluation evidence rather than silently retraining labels.

### 4.4 Interruption reduction

- Chairman interruption episodes per active-program interval;
- Sol interruption episodes per active-program interval;
- counterfactual avoidable interruptions: actual interventions that point-in-time EAF lawfully classifies as `BATCH_NEXT`, `AUTONOMOUS_CONTINUE`, `VALID_WAIT`, `COVERED_BY_BUNDLE` or non-actionable;
- context-batch yield: decisions/actions resolved per executive context entry where measurable;
- root-cause fan-in contribution vs simple demotion contribution.

Do not claim reduction solely because Wake delivery was disabled or a source failed.

### 4.5 Delay and starvation

- source-backed ready age distribution for eligible ordinary demand;
- age of oldest fairness sentinel by authority;
- time eligible items spend deferred under emergency pressure;
- decision-window miss rate;
- time from accepted actionable demand to executive disposition/decision where the owner provides those events.

Unknown ready time stays out of age statistics and appears in coverage gaps; do not assign age zero.

### 4.6 Wait fidelity

- valid typed waits honored before review boundary;
- overdue waits actually re-evaluated;
- false early interruptions of valid waits;
- waits invented without explicit source evidence (must be zero);
- cases where expected-information arrival changed the eventual decision or evidence quality, when observable.

### 4.7 Congestion pressure

From F0A:

- independent interrupt roots per authority over time;
- duration of `MULTIPLE_INDEPENDENT` and `FEASIBILITY_UNKNOWN` pressure;
- `PROVEN_WINDOW_COLLISION` episodes;
- ordinary fairness debt accrued during sustained interrupt pressure;
- exact causes: real incidents, noisy admission, stale source truth, unavailable delegation, or capacity gaps where evidence supports the label.

## 5. Baseline before targets

Do not invent percentage targets before measuring the current estate.

A2 should establish at least one real multi-program baseline interval with:

- actual raw attention-demand volume;
- actual Chairman/Sol interruption volume;
- root duplication;
- current source coverage;
- current decision latency where measurable;
- current starvation/wait/congestion state.

Only after that baseline may A5 freeze quantitative promotion thresholds. The following remain hard qualitative/zero-violation gates independent of baseline:

- no priority-to-authority escalation;
- no independent interrupt suppression;
- no semantic/LLM fan-in suppression;
- no invented waits;
- no current-truth substitution in point-in-time replay;
- no mutation/dispatch/retry from report-only EAF state.

## 6. Shadow-to-product stages

### Stage S0 — deterministic corpus

Synthetic/adversarial cases from F0/F0A/F0C/F0D, permutation stable. No live source dependencies.

### Stage S1 — frozen real-source snapshot

Use current production/source snapshots read-only. Prove identities, unknown handling and omission receipts. No historical claims.

### Stage S2 — point-in-time replay

Reconstruct historical attention episodes where source history permits. Measure replayability coverage separately.

### Stage S3 — prospective shadow

For a real multi-program interval, compute EAF results at decision time with **no delivery/suppression side effects**, then compare with actual interventions/outcomes later.

This is the strongest calibration evidence because it prevents hindsight leakage.

### Stage S4 — Control Room default composition

Only after accepted S3 evidence may EAF become the default compact attention composition. Raw forensic facts remain available.

### Stage S5 — any proactive delivery behavior

Out of scope for initial EAF. Any change to Wake/notification cadence/routing requires a separate explicit architecture/release under Wake ownership. A successful EAF does not silently gain delivery authority.

## 7. Counterfactual adjudication

Not every actual human interruption is evidence that an interrupt was necessary, and not every quiet period proves batching was safe.

A5 should preserve an adjudication record for disputed episodes with:

- point-in-time facts;
- EAF output and explanation;
- actual action/interruption;
- later outcome evidence;
- reviewer ruling (`EAF_CORRECT`, `EAF_FALSE_INTERRUPT`, `EAF_MISSED_URGENCY`, `AUTHORITY_ERROR`, `SOURCE_GAP`, `UNREPLAYABLE`, etc.);
- corrective action: source-owner repair vs EAF policy repair vs no change.

This is evaluation evidence, not a new lifecycle plane.

## 8. Learning without self-corruption

EAF V1 remains deterministic. Measurement may discover policy errors, but production policy changes occur through explicit versioned code/source-law changes and replay of the accepted corpus.

Do not let an online model or adaptive weight update silently change attention behavior based on clicks, acknowledgements or Chairman actions. Human behavior is evaluation evidence, not automatic ground-truth authority.

## 9. Promotion completion

The program reaches the Chairman's end-state only when the prospective real multi-program shadow shows all of the following together:

- high enough source/admission coverage to trust the population being measured;
- exact lawful compression/fan-in;
- zero accepted severe-interrupt misses in the canary interval/corpus;
- zero priority-driven authority leakage;
- preserved intentional waits;
- bounded ordinary starvation/fairness debt with truthful unknowns;
- materially reduced executive scanning/interruption relative to the measured baseline;
- no harmful increase in severe-decision latency;
- visible Control Room browser proof;
- useful Chat-native Meta-CEO/Program-CEO consumption;
- correction-safe receipts allowing a fresh session to explain every recommendation.

Only then is EAF an accepted cognition-allocation ruler rather than an architecture or classifier.
