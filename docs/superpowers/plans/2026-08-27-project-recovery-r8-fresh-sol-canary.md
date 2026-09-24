# Project Recovery R8-G — Fresh-Sol Adversarial & Production Recovery Canary Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that a genuinely fresh Sol can discover and safely recover a real unfinished Mastermind program from current durable system state without Chairman context carriage, while refusing valid waits, runtime uncertainty and duplicate carriers.

**Architecture:** R8-G is evidence/acceptance, not a new runtime. Use the existing fresh-Sol evaluation capability only after its own PR #162/F0 is independently accepted for isolated behavioral tests; then run one production-relevant fresh ChatGPT Sol session through the real MastermindX Project/Control Room grounding path. The final canary consumes current R8 assessment/Agenda/Control Room state, uses normal Skillpack and Executive admission law for any commission, and closes the chosen real recovery item through existing Agent OS/GitHub/Linear projections.

**Tech Stack:** accepted R8-A assessment, Improvement Agenda, Chairman Control Room, current protected Sol Skillpack, existing OHF fresh-Sol harness if accepted, real ChatGPT MastermindX Project session, Executive OS/Agent Relay only if production-proven, GitHub/Agent OS evidence.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current-state amendment.

## Global Constraints

- R8-G begins only after R8-A is Sol-accepted on a current-estate census and R8-C/E are usable on the real read path.
- The isolated fresh-Sol harness in PR #162 is currently open/draft and is not yet a proven capability. Do not depend on it until its own acceptance says `PROVEN_LIVE` for fresh isolated Sol evaluation.
- Isolated OHF evidence cannot by itself prove the real operating path because that harness intentionally disables MCP/plugins/tools and production mutation.
- The final production canary must use a genuinely fresh Sol conversation/session with no prior R8/project chat transcript as hidden context.
- No canonical/primary Sol chat is designated.
- The Chairman may perform the one user action needed to open/start a fresh ChatGPT turn; R8 does not pretend an inactive ChatGPT conversation can wake itself.
- After launch, the Chairman must not paste prior program archaeology, PR history or next action into the canary. The system must supply the grounding.
- Any modifying commission must use current explicit Chairman intent plus current Skillpack/runtime/app gates and one-carrier identity.
- Generic `#agent-dispatch` Slack fanout is forbidden as a substitute for Executive/Fable claim.
- If Executive/Fable production admission is not yet proven, R8-G may prove read-only recovery/adjudication but remains `BUILT_NOT_PROVEN` for end-to-end sustained handoff.
- Fixture-only success is insufficient.

## Evidence Structure

Use existing review-evidence conventions under:

```text
review_evidence/project_recovery/r8g/
```

Persist only sanitized receipts. Raw chat/session content is retained only to the extent existing fresh-Sol evidence law permits; never store credentials, private URLs, cookies, tokens or secret-bearing browser data.

---

### Task 1: Freeze the twelve-case machine/behavioral scorecard

**Files:**
- Create `review_evidence/project_recovery/r8g/SCENARIO_CONTRACT.md`
- Create `tests/test_project_recovery_r8g_contract.py` for schema/scorecard parsing only.

**Interfaces:**

Each scenario result:

```json
{
  "scenario": "S01_ABANDONED",
  "input_assessment_hash": "sha256:...",
  "expected_disposition": "RECOVERY_REQUIRED",
  "expected_action": "recover",
  "must_refuse_commission": false,
  "observed": {
    "disposition": "RECOVERY_REQUIRED",
    "action": "recover",
    "commission_refused": false
  },
  "pass": true
}
```

- [ ] **Step 1: Define exact cases**

```text
S01 abandoned unfinished work -> RECOVERY_REQUIRED
S02 expired natural review -> CEO_ATTENTION / MISSED_REVIEW_GATE
S03 valid prospective wait -> VALID_INTENTIONAL_WAIT, do not recover
S04 exact active carrier -> NO_RECOVERY_ACTION
S05 Slack dead letter/no receiver -> recovery/attention from typed evidence, not delivery-as-execution
S06 merged implementation/proof open -> MERGED_PROOF_DEBT
S07 runtime unavailable -> UNKNOWN_RECONCILE, refuse duplicate commission
S08 building semantic program/no workstream -> ORPHAN_BUILDING_PROGRAM
S09 all waves terminal/top active -> ACTIVE_BUT_COMPLETE organizational repair
S10 duplicate active carriers -> UNKNOWN_RECONCILE/blocking, refuse commission
S11 Linear false-green -> canonical proof debt survives
S12 stale next_action -> consume SUPERSEDED_NEXT_ACTION, no prose inference
```

- [ ] **Step 2: Freeze pass law**

Every case must match expected disposition/action. S03/S04/S07/S10 must explicitly demonstrate **no new commission**. One false-safe classification fails R8-G.

- [ ] **Step 3: Run parser/contract tests and commit**

```bash
python -m pytest tests/test_project_recovery_r8g_contract.py -q
git add review_evidence/project_recovery/r8g/SCENARIO_CONTRACT.md tests/test_project_recovery_r8g_contract.py
git commit -m "test(exec): freeze fresh Sol recovery scorecard"
```

---

### Task 2: Reuse the existing OHF fresh-Sol harness only after independent acceptance

**Files:**
- Do not modify PR #162 carrier from R8-G.
- R8-G evidence only.

- [ ] **Step 1: Reconcile PR #162 current truth**

Require an immutable merge/acceptance receipt proving its fresh process/thread/model/Skillpack isolation and cleanup falsifiers. If #162 remains docs-only/open/unproven, record `R8_G_BEHAVIORAL_HARNESS_HELD` and skip this task.

- [ ] **Step 2: If accepted, prepare bounded R8 scenario packets**

Each packet contains only:

- current protected Skillpack bytes/identity supplied through the harness’s accepted mechanism;
- one synthetic `mastermind.project_recovery_assessment.v1` summary or bounded current receipt;
- the CEO question: classify the situation, state whether a commission is safe, and name the exact next CEO action.

Do not give the expected answer or historical chat reasoning.

- [ ] **Step 3: Run one independent fresh Sol sample per scenario**

Use a new process/private group + new thread/start for every scenario, no resume/fork. Require served model `gpt-5.6-sol`, exact immutable Skillpack identity and capability attestation from the accepted harness.

- [ ] **Step 4: Deterministically score all twelve**

A separate scorer maps the Sol output to the closed expected fields using a bounded structured answer contract. If the harness only returns prose, add a scenario instruction requiring the final answer include exactly:

```text
DISPOSITION: <closed enum>
COMMISSION_SAFE: YES|NO
NEXT_ACTION_CLASS: RECOVER|WAIT|RECONCILE|REPAIR_ORG|NO_ACTION
```

Do not let a second LLM judge ambiguous prose.

- [ ] **Step 5: Persist sanitized aggregate receipt**

Record process/thread opaque IDs or hashes as allowed by the harness contract, Skillpack SHA, assessment hash, served model, scenario result and cleanup proof. No raw secrets.

**Pass:** 12/12 exact classifications and all required refusal cases.

---

### Task 3: Select the real production recovery subject from current truth

**Files:**
- Evidence only.

- [ ] **Step 1: Re-pin current protected Skillpack and all recovery sources**

Generate a current R8-A assessment and current Improvement Agenda through accepted paths. Do not use the stale list from the design conversation.

- [ ] **Step 2: Choose by deterministic current Agenda rank**

Select the highest-ranked item satisfying all of:

```text
disposition == RECOVERY_REQUIRED
exact current recovery evidence is available
no MULTIPLE_ACTIVE_CARRIERS / UNKNOWN_RECONCILE blocker
not already claimed in Executive/runtime current truth
program outcome is material enough to require CEO recovery
```

If no safe `RECOVERY_REQUIRED` item exists, record `NO_SAFE_REAL_RECOVERY_SUBJECT`; do not manufacture one. Use a controlled stale fixture only for UI proof, and leave end-to-end R8-G pending a natural real case.

- [ ] **Step 3: Freeze selection receipt**

Record assessment semantic hash, Agenda artifact hash/date, subject, recovery finding, exact current carrier absence evidence and why higher-ranked items were skipped if blocked/unknown.

---

### Task 4: Launch one genuinely fresh production Sol through the real product path

**Files:**
- No code modification.

- [ ] **Step 1: Start from a genuinely fresh ChatGPT conversation/session**

Allowed entry:

- MastermindX Project new chat, or
- accepted Control Room `Open Sol` navigation that creates/focuses a fresh intended Sol surface without typing/sending the task.

The session must not have prior selected-program chat history.

- [ ] **Step 2: Give only the minimal Chairman intent**

Use a bounded instruction equivalent to:

```text
Take the next CEO Recovery item and own it end to end under current Mastermind law.
```

Do **not** paste subject identity, stale PRs, architecture recap or our prior recovery reasoning.

- [ ] **Step 3: Require fresh Sol to recover current truth itself**

Pass requires the Sol session to:

1. load current protected Skillpack;
2. inspect current CEO Recovery/Agenda/Control Room assessment;
3. identify the exact selected subject from the system;
4. cold-start its full program outcome, not merely stale `next_action`;
5. detect any post-selection source movement/collision;
6. state current capability ledger and exact next vertical.

- [ ] **Step 4: Compare with frozen selection receipt**

The fresh Sol must select the same subject or produce a canonically valid newer reason the frozen subject is no longer safe/next. A stale but confident choice fails.

---

### Task 5: Prove safe sustained handoff without Chairman becoming the bus

**Files:**
- Durable Agent OS/Executive/GitHub records produced through their normal owners, not R8-specific stores.

- [ ] **Step 1: Reconcile current Executive/Fable capability**

Require current production evidence that the intended CEO ingress and sustained Fable/worker routing path can create/claim a real Job/Attempt/Worker. If not proven, record `R8_G_EXECUTION_HANDOFF_HELD`; do not post a generic Slack pickup.

- [ ] **Step 2: Fresh Sol freezes/uses the existing program architecture**

It must preserve one canonical workstream/carrier and create no duplicate recovery workstream. If architecture is incomplete, Sol completes architecture first under normal major-program law.

- [ ] **Step 3: Commission one bounded first recovery wave through the lawful runtime**

The commission must contain the full current observable mission, authority precedence, exact scope/non-goals, user/machine journey, data/time/null/correction behavior, method, failures, tests, real proof and stop condition.

- [ ] **Step 4: Prove actual claim**

Pass requires canonical Executive/session evidence of a real receiver claim. Slack delivery or a GitHub branch alone does not count.

- [ ] **Step 5: Let sustained COO/worker execution advance one independently useful capability**

Routine progress does not need Chairman copy/paste. Sol attention returns only for a material blocker/decision/milestone/final review under current runtime law.

---

### Task 6: Close the selected recovery finding through real proof

- [ ] **Step 1: Sol reviews the returned wave against the original full outcome**

Use current `REVIEW_RETURN.md`; merge/CI is not enough.

- [ ] **Step 2: Require the program’s actual production/research acceptance evidence**

The selected subject’s own completion law controls. R8 cannot lower it.

- [ ] **Step 3: Update durable Agent OS organizational state**

After accepted proof, update the existing workstream/handoff/decision as required so the next R8 assessment sees the new lawful frontier or terminal state.

- [ ] **Step 4: Regenerate R8 assessment and Agenda**

The original recovery finding must clear or become a different truthful disposition (`NO_RECOVERY_ACTION`, typed wait/gate, etc.). It may not disappear because a projection was manually edited.

- [ ] **Step 5: Verify Linear/Control Room projection**

Control Room must reflect the cleared/new state. Linear managed block updates only if R8-D is armed; otherwise projection debt remains explicit and does not fail canonical closeout.

- [ ] **Step 6: Slack is optional**

If R8-F remains dependency-held, no Slack recovery-cleared event is required for R8 truth acceptance.

---

### Task 7: Final acceptance receipt

**Files:**
- Create `review_evidence/project_recovery/r8g/FINAL_ACCEPTANCE_<date>.md` plus bounded JSON receipt if consistent with repository evidence law.

- [ ] **Step 1: Record truth**

Include:

- exact protected Skillpack SHA;
- Mastermind/Macro relevant SHAs;
- R8 assessment + Agenda hashes before/after;
- selected subject and finding;
- fresh session identity evidence under allowed privacy law;
- whether OHF 12/12 corpus passed;
- Executive operation/job/claim identifiers if execution occurred;
- GitHub/Agent OS proof references;
- Control Room browser proof;
- Linear projection state or explicit projection debt;
- Slack projection state or explicit dependency-held status.

- [ ] **Step 2: Apply completion law**

R8 is `PROVEN_LIVE` only if:

```text
machine 12-case falsifiers pass
AND real current assessment is usable
AND genuinely fresh production Sol selects/reconstructs current recovery without Chairman archaeology
AND unsafe duplicate/wait/unknown cases are refused
AND one real recovery subject is handed to a real claimed sustained execution path
AND accepted program progress/closeout clears or truthfully transforms the recovery finding
AND no duplicate lifecycle/queue/identity/retry/scheduler/store was created
```

If the real Executive/Fable handoff is unavailable, classify R8 as `BUILT_NOT_PROVEN` for full autonomy even if read-only fresh-Sol recovery is proven.

**Stop condition:** final Sol acceptance. Do not substitute green CI, fixture-only OHF results, Control Room rendering, Linear projection or Slack delivery for the full end-to-end canary.
