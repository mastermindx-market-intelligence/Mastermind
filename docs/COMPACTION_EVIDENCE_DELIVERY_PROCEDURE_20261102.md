# Delivery-procedure compaction evidence - 2026-11-02 (second pass)

Source baseline: `22c08067ed0f480d1d5324a815fa248661c4ab46` (protected Mastermind, Skillpack 1.0.1 / bootstrap major 1). Original branch: `sol-917-src-compact-20261102-01`. Repair parent for this pass: `c4359eaf538f5f659528ac381c36d2f9dbc369b2`. Latest protected observed pin: `b4a5a8925c6c1412dac67ba296cf65ee81c4d4c8`. The unmerged candidate is not operating authority.

**Outcome: the commissioned >=40% / <=100,000-byte reduction is NOT achieved.** This pass implements the substantive same-owner consolidation that the available evidence supports, preserves every measured obligation, anchor, enum and consumer contract, and records the exact remaining conflict with reproducible measurements. It does not re-scope the parent's target, does not approve, merge, install or adopt anything, and does not claim served-model behaviour.

## 1. What this pass changed

- Consolidated each governing proposition onto its canonical owner and replaced repeated explanations with exact references to that owner, used only where the owner is already mandatory before the action it constrains (`WEB_CEO_DELEGATION.md` now names `ACTIVE_EXECUTION` Steps 2A/2B/3/8 and the routing addendum Sections 1-2/4/10 as the owners of active-turn advancement, no-delta re-planning, finalization, cognition route, tier routing and Fable admission).
- Removed the measured intra-file restatements (`INDEX.md` hard law 18 already carries the `CHAIRMAN_SELECTS` manual-exception clause, so the `WORKER_AVENUE_ROUTING.md` entry no longer repeats it; `CEO_PROJECT_PLAN_CONTINUITY.md` section A already carries the task-tree identity rule, so section D no longer repeats it).
- Trimmed duplicated clause text in `ACTIVE_EXECUTION.md`, `WEB_CEO_DELEGATION.md` and `EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md` without dropping any rule, enum, receipt field, exception or gate.
- Added the clause-loss regression set (`tests/test_delivery_procedure_compaction_contract.py`) that proves each consolidated safety-critical rule is still load-bearing at its owner and fails when that clause is deleted.

## 2. Measured size (UTF-8 bytes)

Source bytes are exact file sizes, not tokens, reading latency, installed behaviour or served-model behaviour.

| File | Baseline `22c08067` | Parent `c4359eaf` | This pass | Delta vs baseline |
|---|---:|---:|---:|---:|
| `docs/sol_skills/INDEX.md` | 20,014 | 19,379 | 19,227 | -787 |
| `docs/sol_skills/COLD_START.md` | 10,830 | 10,205 | 10,205 | -625 |
| `docs/sol_skills/ACTIVE_EXECUTION.md` | 56,650 | 55,269 | 54,877 | -1,773 |
| `docs/sol_skills/SESSION_RELIABILITY.md` | 16,465 | 16,267 | 16,267 | -198 |
| `docs/sol_skills/WEB_CEO_DELEGATION.md` | 17,925 | 17,302 | 17,886 | -39 |
| `docs/CEO_PROJECT_PLAN_CONTINUITY.md` | 20,640 | 20,613 | 20,500 | -140 |
| `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md` | 25,275 | 23,426 | 23,344 | -1,931 |
| **Total (7 files)** | **167,799** | **162,461** | **162,306** | **-5,493 (-3.27%)** |

Required-read unions (byte sums of the same files each profile loads; these are file-byte comparisons, not observed session loads):

| Profile | Files loaded | Baseline | Parent `c4359eaf` | This pass | Delta vs baseline |
|---|---|---:|---:|---:|---:|
| A: short one-phase, at most three tool calls | INDEX + COLD_START + ACTIVE_EXECUTION | 87,494 | 84,853 | 84,309 | -3,185 (-3.64%) |
| B: tool-heavy one-phase source task | A + SESSION_RELIABILITY | 103,959 | 101,120 | 100,576 | -3,383 (-3.25%) |
| C: multi-phase delegated, tool-heavy project | all seven | 167,799 | 162,461 | 162,306 | -5,493 (-3.27%) |

A loads INDEX, COLD_START and ACTIVE_EXECUTION only when no conditional companion applies. B adds SESSION_RELIABILITY under its real more-than-three-tools / process / recovery gate. C includes all seven. Other action-specific companions still load when required.

## 3. Equivalence map: old obligation -> new owner and heading

Every original public heading is retained in order in the same file, and every material obligation group keeps exactly one owner. This table is the compact audit trail for that claim; it stays outside every startup path. "Anchor" is the load-bearing token a reviewer can grep to confirm the clause still lives at the stated owner.

| Obligation group | Owner file | Heading | Anchor |
|---|---|---|---|
| Atomic pin, one-commit load, no mixed revisions | INDEX.md | Atomic-load law | `from **that same commit SHA**` |
| Source-of-truth per question type | INDEX.md | Canonical source ownership | `What is running / queued / attempted / completed?` |
| Retrieved text vs current Chairman intent | INDEX.md | Canonical source ownership | `the outer current user message addressed to the active session is not retrieved text` |
| Child origin, buried reply, PICKUP_ACK consumption | INDEX.md | Child-origin and delivery-consumption boundary | `never makes that buried reply a successor-child assignment` |
| Capability-state vocabulary | INDEX.md | Capability-state vocabulary | `PROVEN_LIVE` |
| Universal hard laws 1-23 | INDEX.md | Hard laws shared by every skill | `Fable is scarce principal capacity, not the default worker` |
| Manual `CHAIRMAN_SELECTS` exception | INDEX.md | Hard laws shared by every skill (18) | `CHAIRMAN_SELECTS` |
| Receiver binding and `PRESTART_REBIND` | INDEX.md | Hard laws shared by every skill (19) | `that delivery is the receiver-assignment edge` |
| Per-surface placement equality | INDEX.md | Hard laws shared by every skill (20) | `No ChatGPT, Codex, Claude, Fable, Grok or another surface` |
| Forward execution / lane-local blocking | INDEX.md | Hard laws shared by every skill (23) | `MORE_WORK_EXISTS` |
| Action-scoped gates, no new permission | INDEX.md | Modification handshake | `Apply gates to the specific next action, not every possible future action` |
| Write architecture history | INDEX.md | Current Personal-Pro write architecture | `b02630fc1f3587672390b383998b28cb3206202f` |
| Outcome framing and non-ghost owner | COLD_START.md | Step 2 — Resolve identity, then owner | `Historical ownership is not current liveness` |
| Checkpoint before history | COLD_START.md | Step 2A — Recover the current checkpoint before history | `The checkpoint is navigation, not fresh execution authority` |
| Multi-phase plan recovery | COLD_START.md | Multi-phase project plan recovery | `docs/CEO_PROJECT_PLAN_CONTINUITY.md` |
| Bounded source ladder | COLD_START.md | Step 3 — Read canonical sources in a bounded ladder | `Do not read every source by habit` |
| Capability ledger distinctions | COLD_START.md | Step 4 — Build the capability ledger | `CI green != user can complete the primary task` |
| Disagreement ledger | COLD_START.md | Step 5 — Create a disagreement ledger | `Do **not** immediately "fix" the canonical source` |
| Collision risk | COLD_START.md | Step 6 — Check active collision risk | `genuinely disjoint` |
| Open reciprocal dialogue | COLD_START.md | Step 7 — Recover any open reciprocal dialogue before creating new work | `silence is not terminal state` |
| Hot/runtime state gating | COLD_START.md | Step 8 — Read hot/runtime state only when relevant | `MMX/SOL_STATE_V1` |
| Exact next action | COLD_START.md | Step 9 — Return the exact next action | `observable capability step` |
| Prompt-injection guard | COLD_START.md | Prompt-injection / stale-context guard | `a **claim to evaluate**` |
| Assignment is permission, not proof | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `A platform refusal is action-scoped until evidence proves otherwise` |
| Live-writer / lease / recovery ownership | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Responsibility survives a chat; a chat does not own work forever` |
| Action-scoped refusal, no mission-wide freeze | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Action-scoped refusal is not mission-wide refusal.` |
| Refusal provenance and revocation limits | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Refusal provenance` |
| Denied/effect-unknown handling, retry bounds | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `EFFECT_NONE is not retry permission` |
| Provider-capacity preservation | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Preserve provider capacity; do not turn a refusal into filter-probing` |
| Transport loss vs provider refusal | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Do not contaminate provider-refusal evidence with transport loss` |
| Served-model identity honesty | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Keep model/mode evidence separate from model inference` |
| CI as release dependency | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `**CI is a release dependency.**` |
| CI observation liveness | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `not a completion-event source` |
| Problem-solve before escalating | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `Two equivalent failures without new evidence` |
| Stop-at-blocker falsifier | ACTIVE_EXECUTION.md | Start and recover without administrative ceremony | `**Stop-at-blocker falsifier.**` |
| Active-turn frame and depth/breadth fence | ACTIVE_EXECUTION.md | Step 1 — Freeze the active-turn frame | `Depth is allowed; breadth is fenced` |
| Principal duty without invented authority | ACTIVE_EXECUTION.md | Step 1A — Select principal duty without inventing authority | `Exactly one current action-authoritative owner` |
| Attended mode fit and stickiness | ACTIVE_EXECUTION.md | Step 1B — Adapt attended reasoning mode to the current phase | `mode stickiness is the default` |
| Observable capability step | ACTIVE_EXECUTION.md | Step 2 — Execute one observable capability step | `Run the action through the canonical owner/tool` |
| Delegation decision and reason labels | ACTIVE_EXECUTION.md | Step 2A — Decide execution ownership before routine labor | `NO_ELIGIBLE_PRE_EFFECT_WORKER` |
| Dispatch overlap and repair budget | ACTIVE_EXECUTION.md | Step 2B — Overlap judgment and execution without multiplying management | `Dispatch is not a finalization reason` |
| Capability delta, no-delta loop | ACTIVE_EXECUTION.md | Step 3 — Require a capability delta, not activity | `NO_DELTA_LOOP` |
| Lane-local blocker classification | ACTIVE_EXECUTION.md | Step 4 — Treat a blocker as lane-local first | `WAITING_EXTERNAL` |
| Bounded reconciliation | ACTIVE_EXECUTION.md | Step 5 — Bound reconciliation and concurrent-session churn | `material invalidator` |
| Exact action-capability discovery | ACTIVE_EXECUTION.md | Step 6 — Discover exact action capability, then react to evidence | `UNPROBED` |
| Durable execution claim | ACTIVE_EXECUTION.md | Step 7 — Offload work that should outlive the reasoning turn | `DURABLE_EXECUTION_RUNNING` |
| Checkpoint/frontier ownership | ACTIVE_EXECUTION.md | Step 7A — Preserve operational continuity before interruption | `The reliability invariant is the **recovery gap**, not runtime:` |
| Finalization classification | ACTIVE_EXECUTION.md | Step 8 — Final-response gate | `PROVEN_OUTCOME` |
| Persistence-failure disposition mapping | ACTIVE_EXECUTION.md | Step 8 — Final-response gate | `NOT_CANONICALLY_PERSISTED` |
| Recoverable stop record | ACTIVE_EXECUTION.md | Step 9 — Make every genuine stop recoverable | `INTENDED_RESUME_SURFACE` |
| Pressure cases A/B/B2/C/D/E | ACTIVE_EXECUTION.md | Pressure cases | `HUMAN_AUTH` |
| Role-aware delivery cases | ACTIVE_EXECUTION.md | Role-aware pressure cases | `do not self-narrow scope` |
| Single active-turn / finalization ownership | ACTIVE_EXECUTION.md | Procedural ownership and companion enrollment | `sole active-turn owner` |
| Session-health classification | SESSION_RELIABILITY.md | Session-health classifications | `ROTATION_SUSPECTED` |
| Output and command budgets | SESSION_RELIABILITY.md | Tool-output and command budgets | `8 KiB or 150 lines` |
| Timeout and process identity | SESSION_RELIABILITY.md | Timeout and process continuation | `A timeout is never permission to replay the command` |
| Connector taint | SESSION_RELIABILITY.md | Connector taint | `a tainted connector generation is unusable` |
| Context discipline, no transcript rebuild | SESSION_RELIABILITY.md | Conversation-context discipline | `Never reconstruct or replay private reasoning` |
| Compact continuation capsule | SESSION_RELIABILITY.md | Compact continuation capsule | `12 KiB / 1500 words` |
| Failure-layer classifier | SESSION_RELIABILITY.md | Failure-layer classifier | `WORKSPACE_OR_EFFECT_UNCERTAIN` |
| Mode-specific continuation defaults | SESSION_RELIABILITY.md | Mode-specific continuation defaults | `not a timer law` |
| Failure triage | SESSION_RELIABILITY.md | Failure triage | `REPEATED_TERMINAL_GENERATION_FAILURE` |
| Rotation sequence and successor custody | SESSION_RELIABILITY.md | Closeout and rotation sequence | `CONTEXT_ROTATION` |
| Work-profile selection | WEB_CEO_DELEGATION.md | 1. Choose the work profile, not a prestige hierarchy | `OPERATOR_OWNED_DELIVERY` |
| Delegable-unit decision | WEB_CEO_DELEGATION.md | 2. Make a delegation decision before substantial routine execution | `genuinely separable` |
| Conserved root and optional layers | WEB_CEO_DELEGATION.md | Optional layers, conserved root | `Choose the shallowest capable route` |
| Bounded commission packet | WEB_CEO_DELEGATION.md | 3. Commission a complete bounded outcome | `COMMISSION_WAVE` |
| Capacity, money and credential holds | WEB_CEO_DELEGATION.md | 4. Capacity and money are real constraints | `Model Router fixes the first lawful suitability tier` |
| Evidence-not-transcript consumption | WEB_CEO_DELEGATION.md | 6. Consume evidence, not worker transcripts | `Summaries are navigation, not proof` |
| Continuity without fictional persistence | WEB_CEO_DELEGATION.md | 7. Preserve continuity without fictional persistence | `not a served-model or Web Pro attestation` |
| Difficulty-signal separation and complexity classes | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 1A. Difficulty-signal calibration law | `C3_FRONTIER_JUDGMENT` |
| Operator-first completion economics | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 1B. Operator-first completion economics | `ordinary return adjudication` |
| Cognition route and Pro-mode exception receipt | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 2. Mandatory Chat-native cognition law | `COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT` |
| Metered-cognition exception receipt | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 2. Mandatory Chat-native cognition law | `METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE` |
| Organizational routing defaults | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 3. Organizational routing defaults | `FABLE — scarce principal / escalation capacity` |
| Fable admission | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 4. Fable admission rule | `WHY FABLE` |
| Builder/reviewer separation | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 6. Builder / reviewer separation | `Independent review never grants` |
| Route/surface/worker/authority separation | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 7. Cognition route / surface / worker / authority separation | `runtime identity` |
| Runtime-alias honesty | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 8. Runtime-alias honesty | `config/executive_worker_routes.json` |
| No blind failover | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 9. No blind failover | `EFFECT_UNKNOWN` blocks blind failover` |
| CEO routing receipt | EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md | 10. CEO routing receipt | `WHY NOT FABLE` |
| Plan ownership split | CEO_PROJECT_PLAN_CONTINUITY.md | Canonical homes: one planning experience, existing owners | `DEC:AGENTOS-NO-TASK-STORE` |
| Plan acquisition or creation | CEO_PROJECT_PLAN_CONTINUITY.md | A. Before substantial project execution: acquire or create the plan | `PLAN_NOT_ORG_LINKED` |
| Master-plan content contract and editorial labels | CEO_PROJECT_PLAN_CONTINUITY.md | B. Master-plan record: compact header, arbitrarily deep tasks | `implementation_complete` |
| Handoff schema and enum discipline | CEO_PROJECT_PLAN_CONTINUITY.md | C. Granular updates and plan revisions | `agentos.handoff.v1` |
| Deterministic crash recovery | CEO_PROJECT_PLAN_CONTINUITY.md | D. Failed ChatGPT session: deterministic recovery, not transcript reconstruction | `ended_because: crashed` |
| Cockpit without a second control plane | CEO_PROJECT_PLAN_CONTINUITY.md | E. Executive cockpit: smallest integration, no second control plane | `create_plan` |
| Acceptance and failure tests | CEO_PROJECT_PLAN_CONTINUITY.md | F. Acceptance and failure tests | `zero duplicate child Jobs` |

## 4. Measured consolidation pool - the exact remaining conflict

The commissioned target needs the seven-file total at or below 100,000 bytes, i.e. **62,306 further bytes must leave the corpus**. The following measurements bound what a semantics-preserving rewrite can reach. All are reproducible from the same source tree.

| Candidate pool | Measured | Method |
|---|---:|---|
| Verbatim repetition inside the seven-file corpus | 123 repeated 6-grams out of 21,716 (0.6%) | 6-gram shingles over all seven files at this head; identical measure at the baseline pin is 137 of 22,254 (0.6%) |
| Overlap with the canonical non-seven owner docs (`AGENT_DIALOGUE_SESSION_CLOSE_LAW`, `DELIVERY_WORKFLOW`, `EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW`, `RECONCILE_STATE`, `CLOSEOUT`, `REVIEW_RETURN`, `BOOTSTRAP_KERNEL`, `EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW`, `EXECUTIVE_WORKER_ROUTING`, `COMMISSION_WAVE`, `WORKER_AVENUE_ROUTING`, `WATCHER_ACTION_LOOP`) | ~3,300 bytes (2.0%) | 8-gram overlap of each of the seven files against those owners |
| Intra-file clause restatement | 5 clauses, ~700 bytes | pairwise clause Jaccard >= 0.55 inside each file |
| Non-rule-bearing prose (no obligation modal, no enum, no pinned token) | 21,152 bytes (14.0%), of which manual review leaves 4 sentences (155 bytes) deletable | sentence classifier plus pinned-phrase, fixture-heading, enum and leaf-contract exclusion sets |
| Structural floor | ~17,500 bytes | 140 mandatory public headings, 5 frontmatter blocks, the receipt/class/field/capsule code blocks, the 2 mandatory tables |
| Form-only rewrite of the largest section (`ACTIVE_EXECUTION.md` "Start and recover without administrative ceremony", 12,204 bytes, ~107 distinct obligation claims) into the rule-list form the frozen design prescribes | 12,398 bytes (102%) | whole-section replacement, held to the same claim set |

The last row is decisive: converting the corpus's densest section from prose to one-rule-per-line costs bytes rather than saving them, because the prose already carries roughly one obligation claim per sentence. The corpus therefore has no redundancy pool of the size the target requires; the remaining 61,701 bytes are operative, non-duplicated normative content.

**The exact smallest conflict**, stated concretely rather than as a general impossibility: the target can only be met by deleting operative obligation groups. Measured candidates, in ascending order of protection loss, are (a) the 23 universal hard laws, 6,125 bytes in `INDEX.md`; (b) the `ACTIVE_EXECUTION.md` start/recover refusal-and-effect block, 12,217 bytes; (c) the eight organizational routing-default subsections, 4,246 bytes; (d) the six pressure-case and seven role-aware specifications, 3,990 bytes; (e) the plan-cockpit product specification, 2,205 bytes; (f) the K0/K5/K6 pass-criteria checklists, 2,706 bytes. Removing any of (a), (b), (d) or (f) removes a protected condition, and the parent ruling and the independent review both forbid that ("Do not simulate 40% by removing protective conditions or making mandatory loads optional"). The parent owns that adjudication.

## 5. Clause-preservation checks

- `tests/fixtures/delivery_compaction_public_headings_22c08067.json` is unchanged; the manifest SHA-256 assertion still binds it. All 140 baseline headings remain, in order, in the same seven files, with local content under each.
- The 19 leaf-content contracts in `tests/test_delivery_procedure_compaction_contract.py` still resolve their required local terms.
- The new clause-loss regression asserts each consolidated safety-critical rule at its stated owner, and asserts that deleting that clause makes the check fail. It is a negative mutant, not a phrase count.
- Existing positive and negative consumer contracts (denial handling, effect-unknown reconciliation, live-writer custody, provider-capacity preservation, CI liveness, Fable admission, Pro-mode refusal, builder/reviewer separation, no-blind-failover, plan enums and editorial labels) are unchanged in wording where they pin behaviour, and remain green.
- `git diff --check` is clean.
- Focused suite result at this head: `tests/test_delivery_procedure_compaction_contract.py` 205 passed; the sixteen other suites that read these seven files pass. Four failures elsewhere (`test_mastermind_plugin_packages.py::test_unexpected_package_socket_is_refused_without_opening_it` and three `test_sol_watcher_contract.py::test_under_limit_recursive_json_returns_fixed_non_echoing_error` cases) reproduce unchanged at the pristine parent head `c4359eaf538f5f659528ac381c36d2f9dbc369b2` and are preserved separately as pre-existing environmental failures; they touch no path in this change.

## 6. Remaining parent outcome

The >=40% / <=100,000-byte objective remains **NOT_ACHIEVED**, and this file does not lower that target, does not claim an irreducible floor, and does not present line-count or formatting changes as the outcome. What this pass does deliver is the consolidation that the corpus actually supports, a per-obligation owner map that makes the preserved set auditable, and the measured pool analysis above so the parent can adjudicate a re-scope or a narrower same-owner redesign without re-running the measurement.

## 7. Verification scope

Source-byte figures are exact file sizes at this head. All 140 baseline public headings are present in the same seven files, in the baseline order, with local content under each; the immutable heading fixture is byte-unchanged and its SHA-256 assertion still binds it. Required-read unions are byte sums of the files each profile loads; they are not observed session loads, served-model behaviour, latency or task-completion evidence. Hosted CI, independent new-head review, parent source release, installed policy adoption and fresh-session stop/continuation evaluation remain separate and unproven here.

## 8. Release and adoption boundary

No Ready/un-draft/enqueue/merge, release-label change, service installation, provider setting, credential change or runtime mutation is authorized by this record. The source remains a held proposal pending current-head checks, independent review and the parent's unresolved efficiency acceptance. A source-only test pass is not installed or served adoption.
