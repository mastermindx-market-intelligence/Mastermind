# Executive Attention Economics — F0C Partial-Order & Explanation Law

**Operation:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Parents:** F0 architecture, F0A concurrent-demand amendment, F0B portfolio/input canary  
**Status:** `ARCHITECTURE_FREEZE / SPEC_ONLY / RECORDS_ONLY`

This amendment prevents a later implementation from preserving the words "Pareto frontier" while silently reintroducing a universal ranking through hidden weights or a fixed lexicographic order.

## 1. Controlling principle

When two valid demands are grounded and comparable, EAF may determine dominance. When they represent a real tradeoff among incomparable dimensions, EAF must expose that tradeoff.

> **A partial order is allowed to remain partial.**

The purpose of EAF is to remove avoidable scanning, duplicates, false urgency and invalid interruption. It is not to manufacture certainty where organizational facts do not justify one unique answer.

## 2. No hidden totalization

After authority partition and closed disposition classification, A1 may not use:

- a hidden weighted sum;
- a fixed undocumented lexicographic sequence;
- a model-generated rank;
- repository/file order;
- source ingestion order;
- random order;
- title/name order;
- arbitrary numeric enum values;
- "first matching rule wins" where rules encode compensating tradeoffs;

to force a unique winner among genuinely incomparable grounded demands.

If one demand has a severe source-backed decision window and another has larger exact dependency unblock with no safe progress, and neither dominates the other under the frozen factor semantics, both remain on the non-dominated frontier unless a separate accepted policy/source fact resolves the tradeoff.

## 3. Comparison relation

For any two demands in the same authority partition and actionable disposition, EAF should be able to explain one of these relations:

- `DOMINATES` — one is no worse on all comparable load-bearing pressure dimensions and strictly stronger on at least one;
- `EQUIVALENT` — grounded comparable load-bearing dimensions are equivalent for service purposes;
- `INCOMPARABLE_TRADEOFF` — each is stronger on at least one grounded dimension, with no accepted policy allowing compensation;
- `INCOMPARABLE_UNKNOWN` — missing/stale/conflicted optional facts prevent a valid comparison, but not enough to invalidate the demand itself;
- `INVALID_FOR_COMPARISON` — a load-bearing identity/authority/effect problem requires `RECONCILE_FIRST` rather than service comparison.

Exact enum spelling is an A1 contract detail; the semantics are frozen.

## 4. Legitimate local tie-breakers

Context affinity and ready age are **service tie-breakers**, not compensating priority weights.

They may choose among `EQUIVALENT` ordinary candidates or select a context batch from a set whose load-bearing urgency/impact/autonomy factors do not establish a stronger relation.

They may not make an item with materially weaker grounded time/impact/autonomy pressure outrank another simply because it is in the current context or older.

The fairness sentinel is an explicit anti-starvation exception to compact visibility/service selection. It does not rewrite dominance and does not demote emergencies.

## 5. Unique winner is evidence, not a requirement

An authority frontier may have:

- one unique dominant current focus;
- several co-dominant/equivalent items that can be batched;
- several genuinely incomparable tradeoffs;
- several independent interrupts;
- a mix of grounded and unknown-comparison items.

The product should show the smallest truthful set, not insist on a single `#1`.

For a genuinely incomparable set, the card/header should state the conflict plainly, for example:

```text
2 FOCUS-NOW tradeoffs — no grounded unique winner
A: window critical; 1 direct unblock
B: window open; 7 exact blocked descendants; no safe autonomous progress
```

That is better executive support than a fabricated `A = 91, B = 88`.

## 6. Every omission requires a receipt

A compact projection may omit an ordinary raw demand from the primary view only when it can explain the omission deterministically with an exact reason such as:

- `COVERED_BY_BUNDLE -> <bundle_id>`;
- `DOMINATED_BY -> <demand_id>` with factor receipts;
- `VALID_WAIT -> <review boundary/condition>`;
- `AUTONOMOUS_CONTINUE -> <current owner/turn/progress receipt>`;
- `NON_ACTIONABLE -> <terminal/superseded receipt>`;
- `DEFERRED_EQUIVALENT_CONTEXT -> <selected context bundle>`;
- `DEFERRED_BY_FAIRNESS_SERVICE -> <current selected ordinary service set>`.

A raw demand may never disappear merely because the UI has a card limit.

`INTERRUPT_NOW` is governed by F0A and cannot be compacted away at all after exact root fan-in.

## 7. Freshness is owner-relative, not one TTL

EAF must consume source-owner freshness semantics where they exist. It must not impose one universal "older than N minutes = stale" rule across Agent OS, runtime, Wake, market-session evidence, external approvals and calendar decisions.

A1 may expose normalized states such as `CURRENT`, `STALE`, `CONFLICTED`, `UNKNOWN`, but the determination must be backed by the owning contract/source window.

Where no owner supplies a valid freshness policy, EAF should expose freshness `UNKNOWN` rather than inventing a TTL from observation age.

Observation time and event/effective time must remain separate.

## 8. Correction safety

The frontier is a pure snapshot transform. Every result should carry enough source identity to explain its derivation, and a corrected source snapshot should produce a new result rather than mutating a hidden rank ledger.

No allocator-local state may be the sole reason an item is dominated, old, ready, stale or suppressed.

## 9. Adversarial corpus additions

Add at least:

22. one critical-deadline item vs one high-unblock/no-safe-progress item where neither dominates -> both remain `INCOMPARABLE_TRADEOFF`;
23. same facts in reversed input order -> same relation/frontier/output;
24. equivalent ordinary items, one current-context and one unrelated -> context may select service candidate but relation remains equivalent and omitted item gets an explicit deferral receipt;
25. one old but materially weaker ordinary item vs one stronger grounded FOCUS item -> fairness sentinel remains visible without rewriting dominance;
26. one item missing optional impact fact vs one grounded item -> no silent zero; relation is unknown/incomparable when required;
27. owner-specific freshness says a day-old strategic approval is current while a ten-minute incident snapshot is stale -> normalized freshness follows each source owner, not one global TTL;
28. compact UI limit smaller than raw ordinary frontier -> every omitted raw demand has an exact suppression/defer receipt; no interrupt omitted.

## 10. Freeze effect

F0 + F0A + F0B + F0C now rule the V1 architecture:

- closed attention dispositions;
- absolute priority/authority separation;
- explicit valid-demand admission;
- exact root fan-in;
- source-backed factor vectors with truthful unknowns;
- genuine partial-order/Pareto reasoning with no hidden totalization;
- deterministic local batching/fairness only where legitimate;
- complete omission receipts;
- owner-relative freshness;
- explicit concurrent-demand pressure;
- report-only shadow before promotion.
