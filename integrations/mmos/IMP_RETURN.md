# IMP lane return — 2026-11-11

Lane IMP ran on branch `t3/mmos-v4-imp` (base `ea1fbcebd`), documents only, no
children. Outputs: `IMPROVEMENT_BACKLOG.md` (29 rows, each sourced and
status-checked against the repository), `SCOREBOARD_PROPOSAL_20261111.md` (five
rows, every number from a named file), both skills, this file. Evidence:
`~/.mastermind/mmos_evidence/imp-20261111/LEDGER.md` — ten rows with the exact
quoted sentences that support them, plus the repository checks behind every
"fixed" status.

## What changed in the skills, and why

`mmos-module-dev` (42 to 58 lines) gained two facts a cold agent would get wrong:
the dev Paperclip on port 3190 is a standing shared instance (check `status`
before `up`; stop it only if your brief owns it — T4b's ledger records leaving it
up on purpose), and every write accepted on loopback is recorded with
`authorType: "user"`, so machine-posted comments need a bracketed prefix to be
told apart from a person's words (the R4b finding 4 class). No commands changed.

`mmos-app-dev` (67 to 90 lines) gained the two traps that caused real incidents:
the `t3` CLI picks its server from `T3CODE_HOME` and `T3CODE_PORT`, never from an
address in your arguments (this minted 14 pairing codes on the Chairman's app in
T4b), and the stock `~/.t3/bin/t3` prints a warning line in front of its JSON
against a newer home (T6's correction). Pairing guidance (0600 file, the
two-minute `access.txt` token, never dump the pairing page) points to
`LANE_RULES_V4.md` rather than restating it. The proof recipe now warns that
accessibility reads fail transiently and that a step counts as done only once its
evidence file exists — T1w wrote three DONE lines that were not true. The stale
test count ("8 tests") was corrected to 12; both L8 attack recommendations were
verified adopted in `shell_mode.rs` (lines 492 and 513), and the optional
`on_navigation` hardening from L8 finding 2 remains open and is not claimed.

## Three backlog items most worth the principal's time

1. **Row 5 — cheap attack rounds cannot clear a critical surface.** The T4b
   attack found twelve real defects and missed the four that mattered; the Opus
   review found all four, after acceptance. Section 18 already decided this; the
   proposed lane-rule sentence would make it survive outside the plan's prose.
2. **Row 29 — the record does not say which model drove most lanes.** Ten of
   twelve V4 lanes and four attack rounds have no model in any durable document,
   so the scoreboard the method routes by cannot be filled. The fix is one
   sentence in the return format, not another lane.
3. **Rows 1 and 14 — outage losses and long-generation deaths.** Both are already
   method prose; the proposed "pushed steps" lane rule (first push inside ten
   minutes, then every slice) makes them structural instead of dependent on each
   brief remembering.

## Where the inputs contradict each other

- `OPERATING_METHOD_V3.md` routes attacks to `glm-5.3` or `kimi-k3.1-pro`; the
  T4b attack was dispatched to `deepseek-v4.1-flash` (`T4B_DECISIONS.md`), and it
  is the attack that missed the four critical findings. Either the routing table
  or the dispatch habit should change.
- `T4B_DECISIONS.md` says the crash journey recovers "through `reconcile_restart`"
  (build-list item 5); R4b finding 15 shows the door's supervisor is a stub
  returning `[]` and no journey exercised the engine reattach — the runbook's
  mechanism claim was wrong even though the journey result was real.
- `T4B_ATTACK_FINDINGS.md` disposition marks F12 "FIXED — the reattach path is
  now reachable in the composed service"; R4b finding 1 shows that same wired
  path strands the attempt it adopts. Both are true at their own level, but a
  reader of the attack file alone would believe item 8 was safe to build on.

Nothing else in the inputs contradicts; in particular the plan's sections 17 to 20
and the CQ and R4b files agree with each other and with the repository.
