# Web CEO Offline Autonomous Delivery Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove one admitted Executive mission can advance from plan through useful work, independent rejecting review, bounded repair, replacement review and aggregation while no Web Sol turn is running, without creating another scheduler/lifecycle or requiring Chris to type `continue`.

**Architecture:** Reuse the already-built `mastermind.executive_autonomy_state/v1` guard, `ExecutiveControlService` bounded COO tick, `CooCycle`, Executive Runtime, current worker/broker adapters, independent review/repair lineage and terminal-return owners. The first slice deliberately does **not** implement arbitrary nested orchestration or a new operational-authority database. It proves the existing deterministic/autonomous delivery path and adds only the smallest missing projection/proof seams discovered by red tests. Sol-reserved final acceptance remains a durable later obligation rather than a liveness prerequisite for worker delivery.

**Tech Stack:** Python 3.12, existing SQLite Executive Runtime, asyncio `ExecutiveControlService`, existing provider-neutral worker/broker and Operator Harness adapters, existing CeoIngress/MCP read path, pytest, canonical JSON/SHA-256 receipts.

**Spec:** `docs/EXECUTIVE_WEB_CEO_AUTONOMOUS_DELIVERY_AMENDMENT.md`

## Global Constraints

- Pickup must fresh-read protected `master`, this spec, #595/#600 current source ownership, and current Executive provider/admission/install state before effects. The authoring source was `ef4682c8b998a9ca522b4690fadf938aa57029ad`. The 2026-09-13 compatibility review at protected `e8f755d1db35f29a227aaac7335caa86fa2b02c4` additionally includes #606, protected #576/#575, and #605. #605's workspace-custody rule is controlling for attended Web/host source edits: use installed `mmx-workspace`; if that launcher is unavailable, do not substitute raw `git worktree add`/clone as a production session-isolation path.
- Executive OS remains the sole Job/Attempt/Worker/Event/result-lineage owner. Do not add a mission DB, scheduler table, queue, retry ledger, watcher DB, browser-session store or result store.
- `mastermind.chairman_delegation_envelope.v1` remains the authority projection. This canary does not introduce a second authority token or caller-selected provider/model/account.
- Checked-in install defaults remain unarmed. Production arming uses the existing exact receipt/host ceremony; source merge is never permission to arm.
- The existing `CooCycle` review/reject/repair/re-review behavior is the implementation to prove, not functionality to rewrite. Any code edit must be justified by a failing discriminating test.
- Current closed policy remains authoritative: depth `1`, max fan-out `8`, max children `16`, max repairs `2`, max review attempts/job `2`. Do not relax review or hide children to fit a demo.
- The canary's first useful mission must fit those limits: one reviewed logical implementation step plus its bounded repair/re-review chain is sufficient. Deep principal fan-out is a later plan.
- No browser robot, private ChatGPT endpoint, transcript scraping, approval-click automation, account rotation, paid API Meta-CEO substitution, or unverified personal-Web wake path enters this slice.
- Web Sol absence means **no Web Sol model turn is generated between admission and integrated candidate**. It does not mean no deterministic service, qualified worker, reviewer or native principal may run.
- Candidate-ready, reviewed, aggregated, Sol-accepted, released and production-proven remain distinct.
- `EFFECT_UNKNOWN` never becomes retry/failover. Existing exact effect/custody reconciliation remains controlling.
- Every source change uses strict red-green TDD and every success claim is backed by a fresh command/output receipt.

---

## File Structure

The implementation begins by proving current capabilities. New production modules are not presumed necessary.

- Modify: `scripts/executive_os_phase1fc_acceptance.py` — add a deterministic `WEB_CEO_OFFLINE_DELIVERY_V1` source acceptance case composed from existing Runtime/COO/review/repair machinery.
- Modify: `tests/test_executive_os_phase1fc.py` — discriminating invariant test that no external Sol/Chairman continuation input is required between admitted plan and aggregated candidate.
- Modify only if red evidence requires it: `control_plane/executive_service.py` — close a service-loop gap preventing an armed service from repeatedly advancing the existing COO cycle after worker/review terminal events. Do not alter the cycle if current behavior already satisfies the invariant.
- Modify only if red evidence requires it: `tests/test_executive_service.py` or the existing service test module owning the failing behavior — service-level canary of the background COO tick.
- Modify: `tests/test_slack_agent_dialogue_executive_terminal_return_projector.py` — prove the integrated terminal result remains durable while the Web target is unavailable and is not falsely marked consumed.
- Create: `scripts/web_ceo_offline_delivery_canary.py` — finite installed-host canary reader/driver only if no existing accepted command can produce the exact proof bundle without broadening a frozen interface. It must call existing owners and persist no new state of its own.
- Create: `tests/test_web_ceo_offline_delivery_canary.py` — hermetic tests for the finite proof bundle and refusal semantics if the script is required.
- No frontend source changes in this plan. #595/Live Fabric receives the resulting finite read contract in a separate consumer slice after the runtime proof is stable.

---

### Task 1: Freeze the CEO-offline invariant in the existing Phase 1F-C acceptance harness

**Files:**
- Modify: `scripts/executive_os_phase1fc_acceptance.py`
- Modify: `tests/test_executive_os_phase1fc.py`

**Interfaces:**
- Add constant `WEB_CEO_OFFLINE_DELIVERY_ACCEPTANCE_ID = "WEB-CEO-OFFLINE-DELIVERY-V1"`.
- Add a pure acceptance helper returning one JSON-serializable receipt with exact root/job/attempt/result/review/repair/handoff identities.
- The helper consumes only existing `Runtime`, `CooCycle`, role-result and fixture-dispatch interfaces. It introduces no service, provider or authority interface.

- [ ] **Step 1: Write a failing invariant test.** Add a test named exactly:

```python
def test_web_ceo_offline_delivery_reject_repair_re_review_reaches_handoff_without_sol_turn(
    tmp_path: Path,
) -> None:
    receipt = run_web_ceo_offline_delivery_acceptance(tmp_path)
    assert receipt["acceptance_id"] == "WEB-CEO-OFFLINE-DELIVERY-V1"
    assert receipt["web_sol_turns_between_admission_and_handoff"] == 0
    assert receipt["review_verdicts"] == ["reject", "approve"]
    assert receipt["repair_rounds"] == [1]
    assert receipt["aggregation_handoff_ready"] is True
    assert receipt["production_accepted"] is False
    assert receipt["manual_continue_edges"] == 0
```

The fixture must use the real existing typed plan/work/review/repair result contracts. Do not insert a fake `continue` callback whose absence is the assertion.

- [ ] **Step 2: Run the exact test and confirm RED.**

```bash
python3 -m pytest -q \
  tests/test_executive_os_phase1fc.py::test_web_ceo_offline_delivery_reject_repair_re_review_reaches_handoff_without_sol_turn
```

Expected first failure: missing `run_web_ceo_offline_delivery_acceptance` or missing acceptance receipt, not an unrelated environment failure.

- [ ] **Step 3: Implement the helper by composing current paths.** The implementation must follow this exact sequence through current `CooCycle.run_once()` and typed role completion:

```python
root = submit_intent(runtime, intent)
planner_created = cycle.run_once(root_id)
planner_dispatch = cycle.run_once(root_id)
complete_plan(planner_dispatch)
plan_admitted = cycle.run_once(root_id)
work_dispatch = cycle.run_once(root_id)
complete_work(work_dispatch)
review_created = cycle.run_once(root_id)
review_dispatch = cycle.run_once(root_id)
complete_review(review_dispatch, verdict="reject")
repair_created = cycle.run_once(root_id)
repair_dispatch = cycle.run_once(root_id)
complete_repair(repair_dispatch)
review2_created = cycle.run_once(root_id)
review2_dispatch = cycle.run_once(root_id)
complete_review(review2_dispatch, verdict="approve")
handoff = cycle.run_once(root_id)
```

Use the existing acceptance helpers for typed completion and exact independent reviewer identities. Do not call Slack, Wake, Sol or Chairman code anywhere inside this chain.

- [ ] **Step 4: Make the test GREEN without changing production cycle code.** Current source already contains `create_cycle_review()` and `create_cycle_repair()` behavior; prove it. If the test fails because current source actually requires a Sol edge, stop and record that exact call boundary before touching production code.

- [ ] **Step 5: Add negative assertions.** Assert the receipt contains no invented production authority:

```python
assert receipt["sol_final_acceptance_pending"] is True
assert receipt["production_deploy_authority"] is False
assert receipt["new_control_planes_created"] == 0
```

- [ ] **Step 6: Run focused regression and commit.**

```bash
python3 -m pytest -q tests/test_executive_os_phase1fc.py
python3 scripts/executive_os_phase1fc_acceptance.py --help
```

Commit only the acceptance/test delta if current production code already passes the invariant.

---

### Task 2: Prove the armed service, not a hand-driven test loop, advances the same existing COO cycle

**Files:**
- Inspect first: `control_plane/executive_service.py`
- Modify only if RED requires: `control_plane/executive_service.py`
- Modify: the existing test module that owns `ExecutiveControlService` armed COO tick behavior

**Interfaces:**
- Reuse `ExecutiveControlService._coo_tick_loop`, `_run_coo_cycle_once`, `_require_current_autonomy`, current dispatch supervisor and `coo_tick_interval_seconds`.
- No new daemon or scheduler API.

- [ ] **Step 1: Locate the exact current service test owner.** Use repository search for `coo_autonomy_armed=True`, `_coo_tick_task`, and `_coo_tick_loop`. Add the canary to that module rather than creating a duplicate service fixture family.

- [ ] **Step 2: Write a failing async service test.** The test must start one hermetic service with:

```python
config = dataclasses.replace(
    base_config,
    coo_autonomy_armed=True,
    coo_tick_interval_seconds=0.01,
)
service = ExecutiveControlService(
    config,
    runtime_factory=runtime_factory,
    supervisor_factory=supervisor_factory,
    autonomy_guard=lambda: None,
)
```

Submit one root before or immediately after service start through the existing admitted Runtime path. Arrange typed role completions from fixture workers/reviewers, but do not call `_run_coo_cycle_once()` or `CooCycle.run_once()` from the test after service start.

- [ ] **Step 3: Assert the service reaches the first deterministic boundary on its own.** Use a bounded wait helper and canonical Runtime reads, not sleeps that merely hope the state changed:

```python
await wait_until(lambda: aggregation_handoff_ready(runtime, root_id), timeout=3.0)
assert service._coo_last_error is None
assert service._coo_last_tick_at is not None
```

- [ ] **Step 4: Run RED and identify the actual boundary.**

```bash
python3 -m pytest -q <service-test-module>::test_armed_service_advances_review_repair_without_web_continue -x
```

If current service behavior already passes, no `executive_service.py` change is allowed. If it fails, record whether the root discovery, active-child reconciliation, terminal-return scheduling, or tick wake is the cause before making one minimal edit.

- [ ] **Step 5: Implement only the proven missing service seam.** Preserve these invariants:

```text
one existing Runtime
one existing bounded tick
one action per cycle invocation
current autonomy guard before effectful selection
no model polling
no new root registry or queue
no duplicate dispatch after ambiguous effect
```

- [ ] **Step 6: Add shutdown/restart tests.** While a worker/reviewer completion exists, close and restart the service. Assert current Runtime evidence is reconciled and no duplicate repair/review Job is created.

- [ ] **Step 7: Run service + COO regression and commit.**

```bash
python3 -m pytest -q \
  tests/test_executive_os_phase1fc.py \
  <service-test-module>
```

---

### Task 3: Preserve the Sol-reserved terminal obligation while delivery is autonomous

**Files:**
- Modify: `tests/test_slack_agent_dialogue_executive_terminal_return_projector.py`
- Modify only if RED requires: existing terminal-return/Wake owner already identified by that test module

**Interfaces:**
- Reuse current `TerminalReturnProjector`, canonical terminal wake candidate, RuntimeBinding/session target validation and Wake ledger.
- The expected outcome is **delivered/pending**, not consumed, when no current Web Sol reasoning action occurs.

- [ ] **Step 1: Write a failing test for an aggregated result with no live Web consumer.** The test must prove all of:

```python
assert terminal_result_is_canonical(runtime, root_id)
assert one_projection_attempt_exists(runtime, root_id)
assert no_duplicate_attempt_or_result(runtime, root_id)
assert parent_consumption_is_recorded(runtime, root_id) is False
assert root_is_not_production_accepted(runtime, root_id)
```

- [ ] **Step 2: Run RED.**

```bash
python3 -m pytest -q \
  tests/test_slack_agent_dialogue_executive_terminal_return_projector.py \
  -k "offline or unavailable or terminal"
```

- [ ] **Step 3: Reuse the existing pending/target-unavailable state.** Do not add `WAITING_FOR_WEB_CEO` to Executive Job status. The pending strategic obligation is a Dialogue/Wake/target-serviceability fact layered over the canonical result.

- [ ] **Step 4: Add replay/restart proof.** Reconstruct a fresh service/Runtime reader and assert the same terminal result and unresolved parent-consumption obligation are recovered without copying chat text.

- [ ] **Step 5: Add stale-successor refusal.** Given a replaced RuntimeBinding generation, prove the obsolete target cannot mark the result consumed. The current target may consume only after existing binding verification.

- [ ] **Step 6: Run terminal-return regression and commit.**

```bash
python3 -m pytest -q \
  tests/test_slack_agent_dialogue_executive_terminal_return_projector.py \
  tests/test_company_dialogue_runtime_binding.py
```

---

### Task 4: Produce one finite machine-readable canary receipt from existing owners

**Files:**
- Prefer modifying an existing acceptance/read script if one already returns all required facts.
- Otherwise create: `scripts/web_ceo_offline_delivery_canary.py`
- Otherwise create: `tests/test_web_ceo_offline_delivery_canary.py`

**Interfaces:**
- Input: exact existing `root_job_id` and expected accepted release SHA.
- Output schema: `mastermind.web_ceo_offline_delivery_canary/v1`.
- Read source: existing Executive Runtime/service read paths and current terminal-return evidence.
- The script owns no persistence and performs no provider dispatch itself.

- [ ] **Step 1: Search for an existing accepted read/acceptance script that can emit the complete receipt.** Reuse it if it can prove every field below without broadening a frozen interface.

- [ ] **Step 2: If and only if a new finite script is required, write the failing schema test.** Exact top-level keys:

```python
EXPECTED_KEYS = {
    "schema",
    "release_sha",
    "root_job_id",
    "plan_digest",
    "work_revisions",
    "review_revisions",
    "repair_revisions",
    "aggregation_result_digest",
    "web_sol_turns_between_admission_and_handoff",
    "manual_continue_edges",
    "parent_consumption_state",
    "production_acceptance_state",
    "effect_uncertainty",
    "source_evidence",
    "observed_at",
}
```

No provider token, prompt transcript, cookie, account secret or raw environment field is permitted.

- [ ] **Step 3: Implement read-only receipt construction.** Reject unknown/missing root, malformed lineage, stale expected release, ambiguous result, unresolved `EFFECT_UNKNOWN`, duplicate current revision, or incomplete independent review. Do not heal state.

- [ ] **Step 4: Add canonical digest/secret-hygiene tests.** A stable source state must produce deterministic canonical field content except `observed_at`; secrets or arbitrary provider output must not enter the receipt.

- [ ] **Step 5: Run the finite script against a hermetic Runtime fixture.**

```bash
python3 -m pytest -q tests/test_web_ceo_offline_delivery_canary.py
```

- [ ] **Step 6: Run static CLI refusal tests and commit.** The CLI must return a closed error document rather than a traceback on malformed input.

---

### Task 5: Execute one real reversible CEO-offline production-path canary

**Files / systems:**
- No new code path is assumed in this task.
- Existing installed Executive release and autonomy receipt owner.
- Existing provider/Capacity/broker stack accepted by the incumbent #600 integration.
- Existing Git branch/worktree publisher path for the selected harmless canary artifact.

**Interfaces:**
- One current `mastermind.chairman_delegation_envelope.v1` authority source.
- One admitted Executive root fitting current depth/children/repair limits.
- One qualified builder worker and one independent reviewer identity.
- One reversible non-production artifact change or source-grounded research artifact selected at canary time.

- [ ] **Step 1: Re-pin current source and installed runtime.** Require exact protected Mastermind SHA, installed release SHA, current autonomy status/receipt, current provider-readiness/capacity evidence, current principal/workspace custody and zero unresolved effect on the canary scope.

- [ ] **Step 2: Choose the smallest useful mission that can exercise one reject/repair/re-review without production deployment.** It must have a deterministic falsifier and rollback and fit the current 16-child budget. Do not manufacture a fake review rejection; select a bounded candidate where the reviewer can discover or be seeded with a documented reversible fault drill under the accepted canary law.

- [ ] **Step 3: Admit the mission through the existing CEO/Executive path.** Record the root/job IDs. After admission, perform **no Web Sol continuation** until the integrated candidate or genuine reserved-decision boundary is reached.

- [ ] **Step 4: Let the existing armed service and qualified workers advance.** Record actual worker/provider/realm/profile/host identities through current non-secret evidence. Do not run `CooCycle` manually as an operator shortcut.

- [ ] **Step 5: Require independent reject -> repair -> re-review.** The repair must reference the exact rejected candidate and reviewer result. A different new root or worker retry under a fresh identity is a failed canary unless current effect law explicitly requires a reconciled successor.

- [ ] **Step 6: Read the final canary receipt.** Pass requires:

```text
useful artifact/result exists
independent reviewer rejected exact first revision
bounded repair created under current policy
independent re-review approved exact repair revision
aggregation/integrated candidate exists
manual Chairman CONTINUE count = 0
manual account selection count = 0
Web Sol turns between admission and integrated candidate = 0
production acceptance = not claimed
no duplicate Job/Attempt/result/effect
no EFFECT_UNKNOWN
```

- [ ] **Step 7: Reboot/restart one owned service after the result and prove recovery.** The accepted result and pending Sol acceptance obligation must survive without transcript reconstruction.

- [ ] **Step 8: Disarm/rollback if the canary contract requires it and preserve exact receipts.** Do not leave experimental authority armed beyond its accepted envelope.

---

### Task 6: Hand the proven read contract to Live Fabric and Agent OS owners

**Files / owners:**
- Mastermind #595 source owner for conversation-first Live Fabric consumer.
- Existing Agent OS `WS:CHAIRMAN-CONTROL-ROOM` writer (#7120 lineage or lawful successor).
- Existing Agent OS `WS:EXECUTIVE-CAPACITY-FABRIC` owner from merged #7123 / incumbent #600 integration.

**Interfaces:**
- Consume the exact canary/read receipt from Task 4/5; do not duplicate lifecycle state in frontend or Agent OS.

- [ ] **Step 1: Provide #595 the finite field mapping.** C0/C1 must show from existing evidence:

```text
what current delivery may finish autonomously
what exact strategic/Chairman decision is pending
current operational principal and admitted children
review/repair/integration state
parent-delivery vs parent-consumption state
production acceptance as separate state
```

- [ ] **Step 2: Refuse inferred UI state.** A Figma label, chat title, model sentence, queued Job or delivery receipt cannot generate `autonomous`, `consumed`, `accepted` or `production proven` without its canonical source.

- [ ] **Step 3: Update Agent OS through the existing writers only after runtime/source evidence exists.** Record the protected law/implementation SHA, canary receipts, actual capability state, unresolved Web/native-review limitation and exact next action. Do not create `WS:WEB-CEO-AUTONOMY`.

- [ ] **Step 4: Keep source/product capability states separate.** The expected first closeout after a successful canary is:

```text
Web-Sol strategic office: existing policy, not newly "proven" by this canary
CEO-offline bounded delivery: PROVEN_LIVE for the exact canary class only
Live Fabric consumer: BUILT_NOT_PROVEN or PROVEN_LIVE according to actual browser proof
exact unattended personal-Web Pro invocation: unchanged until separately qualified
arbitrary deeper orchestration: PARTIAL / not implied by depth-one canary
```

- [ ] **Step 5: Close reciprocal dialogues explicitly.** Every child receives the correct terminal STOP/source-removal edge; the parent program may remain active for the next gated slice.

---

## Self-Review

### Spec coverage

- Web Sol is not runtime liveness: Tasks 1, 2, 5.
- Existing authority envelope rather than a new mission store: Global Constraints, Task 5.
- Deterministic review/repair mechanics proceed without routine Web `CONTINUE`: Tasks 1–2.
- Sol final acceptance remains reserved: Tasks 1, 3, 5.
- Lost/unavailable Web result remains durable and unconsumed: Task 3.
- Existing source owners and no duplicate runtime/UI stores: all tasks, especially Task 6.
- Real production-path proof, not CI-only acceptance: Task 5.
- Live Fabric receives canonical projection only after producer proof: Task 6.
- Personal-Web automation is not introduced: Global Constraints.
- Deep/multi-level parallel orchestration is not falsely claimed by this first slice: Global Constraints and Task 6.

### Placeholder scan

This plan intentionally contains no `TBD`, `TODO`, generic “add tests,” or unowned “handle errors” steps. Every conditional source edit is gated by a named failing test so the implementer does not modify already-correct runtime code merely to show activity.

### Type/interface consistency

The plan introduces only one optional new schema, `mastermind.web_ceo_offline_delivery_canary/v1`, and only if the existing read/acceptance surface cannot emit the required proof. All execution semantics reuse existing `Runtime`, `CooCycle`, `ExecutiveControlService`, terminal-return and authority contracts.

## Execution Handoff

Implement this as **one independently useful first capability**. Do not combine deeper fan-out, provider-fleet expansion, browser automation, native scheduled Sol review or the full Live Fabric frontend in the same PR.

Preferred execution model: incumbent #600/Fable principal coordinates source/canary ownership; bounded Codex/Terra-style workers implement exact test/source slices; an independent reviewer adjudicates the exact candidate. Sol reviews the completed capability against this spec and the original Chairman outcome.

Stop the slice only at a genuine missing authority/provider/install/effect gate or after the production-path CEO-offline delivery canary and its recovery proof are complete. The exact next program after this slice is the separately qualified native executive-review entry, followed only then by deeper parallel/dependency scale.
