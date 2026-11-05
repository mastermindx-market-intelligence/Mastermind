# E-G — Canonical Model, Derived Intelligence and Integration

## E. Canonical data model

Mastermind does not need a giant universal securities schema. It needs four small canonical contracts plus one versioned equivalence registry.

### SecurityIdentityV1

Minimum contract:
- issuer_id, security_id, listing_id;
- country_of_risk, incorporation_country, region;
- MIC, venue, ticker, currency, security_type, share_class;
- primary_listing_id and explicit ADR/A-H/cross-listing relationships;
- local issuer/listing identifiers;
- effective_from, effective_to;
- source_id, observed_at, correction_generation.

A/H twin identity is especially important because current HK research uses A/H relative-value evidence that has no US analogue.

### EvidenceObservationV1

Minimum temporal envelope:

~~~text
observation_id
source_id
source_record_id
issuer_id
security_id
region
venue
evidence_family
semantic_subtype
metric
value
unit
currency
event_time
as_of
observed_at
available_at
ingested_at
effective_from
effective_to
correction_generation
supersedes_observation_id
source_timezone
quality_flags
rights_state
provenance_receipt
~~~

Clock meanings must remain distinct:

| Clock | Meaning |
|---|---|
| event_time | when the underlying economic event happened |
| as_of | period/date to which a value refers |
| observed_at | when Mastermind actually saw/fetched it |
| available_at / known_at | earliest lawful public actionability timestamp |
| ingested_at | canonical-store commit time |
| effective_from / effective_to | validity interval for identity/classification/state |
| correction_generation | ordered later correction/restatement version |

**available_at is the historical admissibility gate.** A backtest at T may use an observation only when available_at <= T. Later corrections create later generations and must never rewrite the information set that existed at T.

### CoverageStateV1

~~~text
scope = region × security × evidence_family
decision_time
coverage_state
expected_for_profile
observed_source_count
expected_source_count
history_start
history_end
pit_grade
freshness_sla
last_success_at
latest_available_at
identifier_match_confidence
correction_policy
rights_state
adapter_health
semantic_equivalence
reason_codes[]
~~~

Required state enum:

~~~text
observed
stale
missing_expected
structurally_unavailable
not_applicable
rights_blocked
adapter_failed
identity_uncertain
correction_uncertain
~~~

missing_expected, structurally_unavailable and not_applicable must remain different.

### DecisionCoverageReceiptV1

This is the bridge to Portfolio V3 without becoming a competing Decision Snapshot.

~~~text
decision_id / shadow_snapshot_id
decision_time
book
security_id
region
required_families[]
optional_families[]
family_receipts {
  family,
  coverage_state,
  semantic_subtype,
  equivalence_class,
  pit_grade,
  freshness,
  source_receipt_ids[]
}
critical_missing[]
confidence_cap_state
actionability_state
abstention_reason
~~~

It should remain read-only/shadow until the canonical V3 Decision Snapshot owner exists.

### EvidenceEquivalenceRegistry

The registry maps local semantics to broad decision questions while preserving non-equivalence.

Examples:
- US SEC Form 4 → insider / direct_local.
- HK Part XV → insider_or_large_holder / local_equivalent.
- HK CCASS participant holding → institutional_positioning / proxy, with beneficial_owner and 13F_equivalent explicitly prohibited.
- CN margin financing → positioning / local_context, with short_interest explicitly prohibited.

Every mapping should be versioned and effective-dated.

## F. Derived intelligence

Most normalization and arithmetic should occur deterministically before any LLM reasoning.

**Fundamentals**
- reported and normalized values separately;
- period-over-period and TTM changes;
- accounting basis, currency and fiscal-calendar alignment;
- restatement generation and data age;
- cross-sectional valuation/quality only where denominators are economically compatible.

**Expectations**
- consensus level and analyst count;
- up/down revision breadth;
- revision magnitude;
- dispersion and forecast age;
- revision acceleration/deceleration;
- guidance-versus-consensus gap;
- surprise and standardized surprise/SUE.

Never use today's consensus to synthesize an earlier consensus.

**Filings/disclosures**
- filing type;
- original/amendment relation;
- publication latency;
- reporting period;
- management/holder role;
- material numeric deltas.

**Positioning**
Retain local denominators. 13F position change, CCASS concentration shift, southbound ownership, major-shareholder disclosure and margin-financing change should remain separate subfeatures. They may share a broad family but should not be summed.

**Short positioning**
Compute within-jurisdiction changes, ranks and z-scores only after respecting each regime's reporting threshold and denominator.

**Options/derivatives**
Where instrument quality is sufficient: implied move, IV term structure, skew, open-interest/volume anomalies, strike concentration and event proximity. Lack of a liquid listed instrument is a coverage fact, not neutral evidence.

**Microstructure**
Spread, liquidity, turnover and order-book features should be deterministic. In mainland China, session state, limit lock, suspension and quote-age logic are region-native facts.

**Themes**
Every membership needs effective_from, effective_to, source and taxonomy generation. Current memberships must never be projected backward.

**Coverage**
Completeness is descriptive metadata, not alpha. Do not begin with arbitrary penalties such as “missing estimates = -15 confidence points.” Start with interpretable states:
- fully_evidenced;
- reduced_evidence;
- price_only;
- abstain_due_coverage;
- rights_blocked.

Future numeric caps should be learned from prospective calibration.

### LLM roles

Cheap models may assist bilingual normalization, alias-resolution suggestions, document/news categorization, guidance tagging and qualitative extraction when every extraction points to source evidence.

Frontier models may reconcile contradictory evidence, reason about supplier/customer and second-order effects, compare region-specific evidence and propose causal hypotheses/falsifiers.

LLMs must never:
- turn missing_expected into neutral;
- change rights_blocked;
- reconstruct unavailable historical consensus;
- promote a proxy into a direct equivalent;
- override deterministic identity/PIT/correction state;
- assign new source trading authority.

## G. Mastermind integration map

The correct architecture is **regional adapters feeding existing owners**, not a new regional intelligence OS.

| Producer | Canonical owner / artifact | Evidence family | Consumer |
|---|---|---|---|
| SEC / US official sources | existing US/Macro owners + PIT observations | filings, fundamentals, insider, ownership, government | portfolio.lenses, held_risk, Prophet, research |
| HK fundamentals / consensus collectors | Macro HK owner, upgraded prospectively | fundamentals, estimates | HK Brain/board; later common receipts |
| HKEX / SFC adapters | Macro regional adapters | filings, Part XV, CCASS proxy, short | HK evidence families |
| China fundamentals / native adapters | Macro China owner | fundamentals, disclosures, corporate actions | China Brain/Prophet |
| CN Prophet live infrastructure | existing CN Prophet owner | price/state/microstructure | existing China consumers |
| Global estimates trial | one canonical expectations owner | expectations/revisions | US/HK/CN Prophet, held-risk, research |
| Coverage engine | CoverageStateV1 + receipts | data quality / epistemic coverage | current data-quality lane; later V3 snapshot |
| Themes/rotation | existing owner | thematic evidence | research/portfolio |
| Existing prediction/outcome infrastructure | signal history, outcome ledger, predictions, shadow books | validation | promotion program |

The integration priority is:

1. expose coverage and PIT receipts around what already exists;
2. improve historical evidence families;
3. widen sources only where incremental value is plausible.

This prevents a sophisticated upstream HK/CN signal from being reduced to a thin downstream standout without its evidence coverage.

The current US Prophet feed is additive and non-authoritative; regional enrichment should preserve that boundary. New expectations evidence for China should feed the existing Prophet architecture after validation, not replace or reinterpret the current live price/state machinery.
