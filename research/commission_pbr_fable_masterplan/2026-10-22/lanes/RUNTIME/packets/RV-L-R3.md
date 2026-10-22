# Review lane RV-L-R3 — independent review of PR #1711 (class review, C2)

You are an independent reviewer in the Mastermind repository (paper-only portfolio bot). You did NOT build this change.
Your working tree (current directory) is a detached checkout of the exact PR head `2c787cf36f3866f9bb710c988db60a6418183d55`
(branch `claude/ssd-pbr-rt-lr3-d63e0882da5bc65c`, base `origin/master` d31aade9). The builder's packet — the contract the
change must satisfy — is at `~/lanes/tmp/pbr-rt-rv-lr3/BUILD_PACKET.md`. READ-ONLY: do not edit, commit, push, run the bot,
or open network connections. You may run tests. Scratch files go only under `~/lanes/tmp/pbr-rt-rv-lr3/`.

## The change
`git diff d31aade9 HEAD --stat` → two new files: `brain/management_lifecycle.py`, `tests/test_management_lifecycle.py`.
A pure read-only projection of one disposition per manager cycle from scheduler run-ledger events, `packet_accepted`
boundary events and per-book decision rows. Two commits: 6bbc7fe7 (the lane build against BUILD_PACKET.md) and 2c787cf3
(the orchestrator added `book_status()` — a per-book fold to PRODUCT's contract R1 — and `started_at`/`finished_at` on each
disposition). The R1 contract text is at `~/lanes/tmp/pbr-rt-rv-lr3/R1_CONTRACT.md`. Review BOTH commits.

## Review checklist (answer each with PASS/FAIL + file:line evidence)
1. Contract fidelity: every state, reason and field the BUILD_PACKET requires exists with the specified names and meaning.
   List any packet requirement that is missing or altered. The builder declared four judgment calls in its return
   (inertness needle form for "settle", projection_failed/settlement_finalization_incomplete matched before rejected_*/frozen_*
   and that bucket requiring status "warn", missing_due_at, carrying brain_run_id/packet_id/asof from a window-matched
   decision row) — judge each: acceptable / not acceptable, why.
2. Purity / inertness: no file I/O, no wall-clock read (`datetime.now`, `time.time`, `utcnow`), no global mutable state, no
   import of app/, bot/, control_plane/, portfolio/ or brain.decision_submission. Grep the whole repo: nothing imports
   `brain.management_lifecycle` except its test.
3. Correctness against the vocabulary it mirrors: open `app/scheduler.py::_brain_job_outcome` and
   `brain/decision_submission.py::ACCEPTED_TARGET_STATUSES` at this head and confirm every status/reason/target they can emit
   maps to the state the packet specifies. Name any emitted value that falls through to the wrong state.
4. Conservative matching: construct (mentally or in a scratch test under ~/lanes/tmp) at least two adversarial inputs —
   (a) a decision row from a DIFFERENT run of the same date, (b) a `run_finished` of another book in the same window,
   (c) records with naive/malformed timestamps — and say whether the projection borrows evidence across cycles or raises.
5. Failure text: `classify_failure_text` never returns more than 80 chars of evidence, never returns raw text beyond the
   matched needle, and "error result: success" sets label_misleading without being typed as a credential/quota failure.
6. Tests: do the tests assert the behaviour (not just "no exception")? Would they fail if the mapping for
   `missing_submission` or for a superseded decision row were wrong? Name one weak test if any.
7. Run: `mkdir -p ~/lanes/tmp/pytest && PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q tests/test_management_lifecycle.py tests/test_scheduler_decision_outcomes.py tests/test_decision_rows.py`
   and report counts.
8. R1 fold (`book_status`, commit 2c787cf3): names and nullability match R1_CONTRACT.md; `run_status` is never null and is
   decided only by the latest dated cycle WITH an outcome (in-flight `started`, `awaiting_start`, ledger skips and future
   cycles never decide it); `failure_reason_code` is set only for failed/degraded; `halted_by` comes only from the caller;
   nothing in the fold reads I/O, a clock, or mutates its input. Construct one adversarial input (e.g. an older failed cycle
   listed AFTER a newer ok cycle, or a junk/undated disposition) and say what it returns.

Findings must be concrete (file:line, input, expected vs actual). Do not report style preferences as defects.
Severity: BLOCKER (wrong state / purity breach / contract missing), MAJOR (edge case mis-mapped), MINOR (doc/naming).

## Final message
Emit the full RETURN block as your last message:
```
RETURN RV-L-R3
head: 2c787cf36f3866f9bb710c988db60a6418183d55
checklist: 1=<PASS|FAIL> 2=<..> 3=<..> 4=<..> 5=<..> 6=<..> 7=<n passed/n failed> 8=<..>
findings: <none | numbered list: severity, file:line, input, expected, actual>
judgment calls: <1..4: acceptable|not acceptable + one line each>
VERDICT: PASS|FAIL|PARTIAL
```
VERDICT is PASS only with zero BLOCKER and zero MAJOR findings. PARTIAL = MAJOR findings only. FAIL = any BLOCKER.
