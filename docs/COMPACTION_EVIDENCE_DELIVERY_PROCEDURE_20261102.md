# Delivery-procedure compaction evidence — 2026-11-02

Source pin: `22c08067ed0f480d1d5324a815fa248661c4ab46` (protected `master`, Skillpack 1.0.1 / bootstrap major 1). Later protected commit `ab93f3ede66486e82e995c88a86e662677973732` touched only Paper/C19 source, not these procedures.
Candidate branch: `sol-917-src-compact-20261102-01`. Status: **source compaction candidate for independent review; not accepted policy.**
This revision is the bounded repair requested by the parent adjudication of 2026-11-02; it supersedes §2 of the previous revision of this file.

## 1. Measured size (UTF-8 bytes, exact `wc -c`)

| File | Pin | Prior candidate (278ae8e4) | This repair | Δ vs pin |
|---|---:|---:|---:|---:|
| docs/sol_skills/INDEX.md | 20,014 | 19,985 | 19,379 | −635 |
| docs/sol_skills/COLD_START.md | 10,830 | 10,346 | 10,205 | −625 |
| docs/sol_skills/ACTIVE_EXECUTION.md | 56,650 | 53,704 | 52,842 | −3,808 |
| docs/sol_skills/SESSION_RELIABILITY.md | 16,465 | 16,357 | 16,248 | −217 |
| docs/sol_skills/WEB_CEO_DELEGATION.md | 17,925 | 17,682 | 17,302 | −623 |
| docs/CEO_PROJECT_PLAN_CONTINUITY.md | 20,640 | 20,635 | 20,613 | −27 |
| docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 25,275 | 23,533 | 23,426 | −1,849 |
| **Total (7 files)** | **167,799** | **162,242** | **160,015** | **−7,784 (−4.64%)** |

## 2. Correction of the previous "~3% floor" claim — retracted

The previous revision inferred a ~3% floor from counting 464 distinct test assertion literals. **That inference is retracted as methodologically unsupported**: a literal count is not a byte-union lower bound, and the owning-commission language explicitly permits equivalent static assertion rephrasing. The corrected measurements are:

- **Pinned-literal byte-union coverage is ~15%** of the current seven-file corpus (method: every string literal ≥12 chars in `tests/*.py`, whitespace-normalized, longest-match coverage over the normalized concatenated file text). Even total renegotiation of every pin could therefore remove at most a minority of bytes — pins are not the binding constraint in either direction, and the previous revision was wrong to treat them as a floor.
- **Verbatim duplication is already gone.** Sentence-level (≥40 chars) duplication *within* each file measures **zero** bytes across all seven files, and cross-file 12-word shingle overlap measures **near zero** (7 shingles total, all between ACTIVE_EXECUTION and SESSION_RELIABILITY). The prior candidate's removals (worked pressure examples, duplicated receipts, duplicated persistence mapping) eliminated the mechanical dedup surface.
- **What remains is condition density, not redundancy.** Manual inspection of the longest unpinned runs (e.g. ACTIVE_EXECUTION refusal provenance, `EFFECT_NONE`/`EFFECT_UNKNOWN` retry law, chunked-prefix law) shows continuous rules plus their conditions/exceptions; the commission forbids deleting or weakening exactly these.

**Corrected conclusion:** after a full equivalent-content consolidation pass on all seven files (three passes: structural dedup, sentence-level tightening, cross-reference consolidation), the measured equivalent-byte reduction is **−4.64% from the pin (−1.4% beyond the prior candidate)**. The ≥40% / ≤100,000-byte target is **not reachable under the commission's semantic constraints at this pin**: it would require deleting or weakening normative conditions (forbidden), moving unconditional requirements behind optional references (forbidden), or restructuring whole sections into files outside the seven (outside this change's scope). Per the parent ruling, this smaller result is reported with its method rather than declared as an immutable floor: the byte union that remains is enumerated in §4, and the specific interventions that *would* go further are returned as parent questions in §6.

## 3. Consolidations performed in this repair (old → new/canonical owner)

- All seven files: sentence-level tightening preserving every condition/exception; pinned-phrase capitalization preserved where suites anchor on sentence-initial wording; two exact-line-break pins (`next\nconcrete executable action`, `does not exhaust the\ncommission`) renegotiated to their single-line equivalents in `tests/test_sol_stop_at_blocker_regression.py` (identical invariant, no line-break dependency).
- INDEX: paper/RDC entry and skill entries compressed with all load gates retained; hard laws 18–22 tightened with all three suite-anchored clauses (`Routine worker placement is not Chairman labor`, `that delivery is the receiver-assignment edge`, `No ChatGPT, Codex, Claude, Fable, Grok or another surface`) retained and `WORKER_AVENUE_ROUTING.md` named as the placement-detail owner it already is.
- ACTIVE_EXECUTION: Step 4's worked local-admin example converted to its general rule (the specific example was illustrative; the rule and the `WAITING_EXTERNAL` lane-local law are retained); duplicated persistence-disposition phrasing kept single-stated where already deduplicated by the prior candidate.
- WEB_CEO_DELEGATION §2/§5/§7/§8: delegation-economics detail cross-referenced to its enrolled active-turn owner (ACTIVE_EXECUTION Step 2A/2B/7A) instead of restating the reason-label semantics; all `OPERATOR_OWNED_DELIVERY`, planning-shape, capacity and attestation rules retained.
- Prior candidate's consolidations (DO_NOT_REDO except where this repair touches them): pressure examples A–E removal, plan-record layout to `docs/CEO_PROJECT_PLAN_CONTINUITY.md`, addendum §10 receipt dedup to §2, WEB_CEO §5/§7 consolidation, SESSION_RELIABILITY returned-fields merge.

## 4. Where the remaining 160,015 bytes live (invariant coverage)

| Block family | Approx. bytes | Why retained |
|---|---:|---|
| Receipt/enums/schema code blocks (ROUTING §1A/§2/§4/§7/§10, PLAN §B tables and `agentos.handoff.v1` enums, capsule layout) | ~9,500 | Actual field names/enums/refusal strings; commission requires them verbatim |
| Editorial-label and canonical-owner tables (PLAN §B/§homes, WEBCEO §2 route table, INDEX ownership table) | ~5,500 | Normative "means / does not mean" columns; each cell is a distinct fact |
| INDEX hard laws 1–23 + atomic-load law | ~7,000 | Always-loaded entry safeguard; parent requires entry needs in INDEX itself (references are not loaded content) |
| Load gates and companion enrollment (INDEX entries, ACTIVE/WebCEO enrollment sections) | ~4,500 | Missing/ambiguous required-action law must stay before the constrained action |
| Refusal / effect / retry law (ACTIVE ceremony, Step 4, SESSREL timeout/taint) | ~8,000 | Deny/unknown-effect rules; single-recovery and no-filter-probing conditions |
| Checkpoint / continuation / rotation law (ACTIVE 7A/8, SESSREL classifier+sequence, PLAN §D) | ~11,000 | CHECKPOINTED_CONTINUATION's five conditions, rotation sequence, recovery order |
| Routing/cognition economics (ROUTING §1–§11, WEBCEO §1/§2/§4) | ~22,000 | Every role boundary, tier rule and budget condition is a distinct decision input |
| Remaining per-file procedure steps | ~92,000 | Condition-bearing normative steps enumerated in the files themselves |

These families sum to the corpus; each is reviewable against the files. The regression suite (`tests/test_delivery_procedure_compaction_contract.py`) now additionally pins the recovery gates and the three required-read bundles below so consolidation cannot silently drop them.

## 5. Required-read bundles (profile assumptions, measured)

Assumptions: "required read" = files INDEX declares mandatory before the profile's constrained action, loaded from one verified pin; conditional companions stay conditional per their INDEX gates. Sizes are exact UTF-8; ceilings are the same files' sizes at the pin (constants in the test, not pins on current wording).

| Profile | Bundle | This repair | Same files at pin |
|---|---|---:|---:|
| A. Ordinary one-phase source task | INDEX + COLD_START + ACTIVE_EXECUTION | 82,426 | 87,494 |
| B. Multi-phase delegated CEO project | A + PLAN_CONTINUITY + WEB_CEO + ROUTING_ADDENDUM | 143,767 | 151,334 |
| C. Error / unknown-effect recovery | ACTIVE_EXECUTION recovery sections + SESSION_RELIABILITY recovery sections (gates pinned in the regression) | included in A/whole-file | — |

Bundle A shrinks 5.8% vs the pin; startup path (INDEX+ACTIVE front matter to Step 1) is unchanged in file count by design — INDEX remains the single always-loaded entry. SESSION_RELIABILITY stays conditional for profile A exactly as INDEX declares.

## 6. Returned to the parent (not resolved here)

1. **Target renegotiation vs semantic scope:** reaching ≤100,000 bytes requires one of (a) deleting/weakening conditions — forbidden; (b) moving whole normative sections to owner files outside the seven and referencing them — outside this change's authorized file set; (c) a pin-renegotiation program covering ~560 literals whose byte union is only ~15% of the corpus and therefore cannot reach 40% alone. No combination of permitted transformations reaches the target; the parent may re-scope which sections are condition-bearing.
2. Whether INDEX hard laws 18–22 may compress to one-line entry rules + owner pointers with their suite pins rewritten against `WORKER_AVENUE_ROUTING.md` (its actual owner). This repair kept the three suite-anchored clauses in INDEX and did not take that step.
3. The prior candidate's remaining consolidations are retained except where this repair explicitly touched them (§3).

## 7. Actual verification

- 27 focused existing suites (every existing test file that reads the seven targets) + the extended regression `tests/test_delivery_procedure_compaction_contract.py` (now with identity, link-resolution, load-gate and three profile-bundle/recovery-gate tests): **green, exit 0**; 1 pre-existing environment-only skip. `tests/test_executive_capacity_source_closure_repair.py::test_runbook_materializes_exact_protected_tree_and_preserves_carrier_blobs` fails identically at the prior published head `278ae8e4` on this host (`git fetch <sha>` returns 128; host git serving-config drift since the prior run) — pre-existing, unrelated to these files; it reads only `docs/sol_skills/WATCHER_ACTION_LOOP.md`.
- `git diff --check` clean. Static string/conformance tests passing is **not** proof of fresh-session behavior; no such claim is made.

## 8. Explicit independent-review-needed status

**Independent review is required and has not occurred.** This branch is a scoped source proposal on its own admitted branch; it has not been approved, merged, or installed anywhere, and it changes no runtime code, workflow, service, credential, or live setting. Reviewers should specifically adjudicate: (a) §2's corrected measurement and conclusion against the parent's ≥40% expectation; (b) §6's returned questions; (c) each §3 consolidation against its canonical owner; (d) the two renegotiated line-break pins in `tests/test_sol_stop_at_blocker_regression.py`.
