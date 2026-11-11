# Scoreboard proposal — the V4 lanes (2026-11-11)

Proposed rows for the scoreboard at the end of `OPERATING_METHOD_V3.md`, covering the
lanes since its last update: the plan V4 lanes T1, T1s, T1w, T2, T3i, T45, T6, T7, H9,
T4b, R4b, CQ (both tasks) and the attack rounds found in their records. Same columns as
the existing table. Every count below comes from a named file; where the record does not
say, it says "not recorded". Nothing here is estimated.

The hard limit first, because it shapes every row: the durable record names the driver
model for only two of the twelve V4 lanes — T7 ("Lane T7 (started 19:05 UTC, GLM 5.3)",
`PROGRAM_PLAN_V4.md` section 13) and R4b ("read-only, Opus, which wrote none of it",
section 17, decision 3). For T1, T1s, T1w, T2, T3i, T45, T6, H9, T4b and CQ no document
in `integrations/mmos/` and no evidence ledger states it. That gap is backlog row 29 in
`IMPROVEMENT_BACKLOG.md`; until it is closed, most of the table cannot be filled.

| Model | Tasks | Accepted first pass | Rejected | False reports | Notes |
|---|---|---|---|---|---|
| `claude-opus-5-5` | 1 (R4b review) | 1 | 0 | 0 | Read-only review of the T4b diff: 15 findings, and the principal re-ran its five reproductions — "all five reproduce" (`PROGRAM_PLAN_V4.md` section 18). It found the four critical defects the lane's own attack round missed (`R4B_REVIEW_FINDINGS.md` findings 1 to 4). Verdict "not safe to build on" was accepted and drove the withdrawal and lane T4c. |
| `kimi-k3.1-pro` | 5 | 3 | 0 | 0 | Attack and test authoring, all consumed: the T2 attack reproduced one real double-post defect, fixed `3a28810dd` (`T2_TEAMMATE_BINDING_AND_DISPATCH.md`, "ATTACK"); the T45 attack script ran live four times, "Final verdicts, all **HELD**" (`T45_MILESTONE_LOOP.md` item 7); the L4 listener attack file — 15 tests, 18 cases — passed 18 of 18 after the principal corrected four test-client bugs ("Result: no defeat", `L4_LISTENER_ATTACK.md`, "Second attack"). The two runs it could not execute it reported honestly: "executed none of them and said so". Also: one T2 binding investigator memo (acceptance not recorded beyond "They agree", section 9), and the T4b item-8 child, which failed twice on router 503 with zero output — a transport failure, not a model verdict (`~/.mastermind/mmos_evidence/t4b-20261110/LEDGER.md`, "Child work"). |
| `deepseek-v4.1-flash` | 2 | 2 | 0 | 0 | T4b item-2 child: the `paperclip_task` return transport, merged `8dd7720ec`, with one live-found defect (UUID `clientRequestId`) fixed in `04c2938ee` (t4b LEDGER, "Child work"). T4b attack round: 12 findings, every reproduction real — "All 25 in-scope reproductions were re-run on this tree before triage" (`T4B_ATTACK_FINDINGS.md`, "Disposition") — 11 fixed, 1 partial. But it missed the four critical findings that withdrew the lane's readiness (section 18); see the routing note below. |
| `glm-5.3` | 1 (T7 driver) | 1 | 0 | 0 | The one V4 lane whose driver model is recorded: "Lane T7 (started 19:05 UTC, GLM 5.3)" (section 13). Accepted at trunk `e1b338021`, 39 tests in the principal's run (section 5); the lane found and fixed its own third-apply memory-erasure bug with a regression test (t7 LEDGER), and its verdict "fork needed for: nothing" closed lane T3 with no fork. The generation-length limit from the wave-3 row (dies above about 15 minutes) still applies. |
| not recorded | 10 lanes + 4 attack rounds | not recorded | not recorded | not recorded | Lanes whose driver model no input states: T1, T1s, T1w, T2 (its two investigators are recorded; its driver is not), T3i, T45 (its attack child is recorded), T6 (its attack child is not), H9, T4b (two of its three children are recorded), CQ. Attack rounds with no model in the record: T1s (one real defect, section 11), T6 (child died on router 503; the driver ran its committed script and found a real installer defect, t6 LEDGER evidence 09), T8 ("five findings fixed", t8 LEDGER), the L8 shell-mode pass (`L8_SHELL_MODE_ATTACK.md`, verdict PASS, two LOW findings). |

Rows not repeated from the existing table: `grok-4.7` (its five false reports and the
L4 attack rounds are already recorded there; nothing new in the V4 window) and
`gemini-4-argon` (withdrawn, unchanged).

## What the rows say

For **read-only review of a critical surface**, the one data point is decisive in
direction: the Opus review found every real critical defect, with reproductions that
all ran, where the lane's cheap attack round had found none of them. One task is not a
trend, but it is the only V4 evidence on that output type, and it is what section 18's
rule (review before acceptance on a critical surface) already assumes.

For **attack and test authoring**, `kimi-k3.1-pro` is 3 for 3 consumed with zero false
reports, and its clearest virtue is honesty about what it did not run. For **bounded
implementation with a test**, `deepseek-v4.1-flash` is 2 for 2 consumed. The same
deepseek attack also shows the ceiling of a cheap attack round: everything it reported
was real, and it still missed the four findings that mattered. "No false reports" and
"found what matters" are different axes, and the V4 record now has one clean example of
each.

For **lane leadership**, the record offers exactly one model-attributed lane (glm-5.3,
T7), accepted first pass. That is consistent with the wave-3 rows but proves nothing
new.

## Where the evidence is too thin

Everywhere a count would be useful. Ten of twelve lane drivers and four attack rounds
carry no model in the durable record, so "which model suits which kind of work" cannot
be answered for lane leadership, investigation or statement work at all from the V4
record. The "Rejected" column is zero for every model — either nothing was rejected
first-pass in V4 or rejections were not written down; the record does not say which.
T4b's acceptance-then-withdrawal is the nearest thing to a rejection in the record, and
it was the principal's act on acceptance, not a first-pass verdict on a dispatch. One
Opus review, three kimi attacks and
one glm lane are enough to keep the existing routing table roughly right, not enough to
move it. The cheapest fix is not another lane: it is backlog row 29 — make every return
name its model.

## One routing note for the principal

`OPERATING_METHOD_V3.md` ("Model routing by output type") lists `glm-5.3` and
`kimi-k3.1-pro` as the attack models. The T4b attack was dispatched to
`deepseek-v4.1-flash` (`T4B_DECISIONS.md`, "Attack round") — off the table, and it is
the attack that missed the four critical findings. The table and the dispatch record
disagree; either the table or the habit should change, and the section 18 rule
(independent review before acceptance on a critical surface) covers the gap either way.
