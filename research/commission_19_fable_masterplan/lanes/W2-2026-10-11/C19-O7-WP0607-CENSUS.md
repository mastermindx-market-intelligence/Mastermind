C19-O7-WP0607-CENSUS — trial-ledger durability + evaluation-primitive census (READ-ONLY)
Lane id: c19-o7-wp0607-census-20261011 · Tier: glm-5.3-flash · Budget: 3600 s wall clock (return PARTIAL at 3000 s)
Host: ubuntu2, repo ~/lanes/repos/macro. The tree is DIRTY and shared: never checkout/reset/stash/add/commit; run ONE
`git fetch origin main`, record `git rev-parse origin/main`, and read every file with `git show origin/main:<path>`.

MISSION
Map, at current Macro origin/main, (A) the trial-ledger writer path in engine/trial_ledger.py — the order of in-memory
mutation vs durable append, the lock type, flush/fsync, corrupt-line policy on reload, and every caller — and (B) the
evaluation primitives in engine/lab.py, engine/validation.py and lib/dataos/temporal.py that implement cost warm-up,
initial-capital drawdown, singular-design (VIF/rank) detection, attempt accounting and cohort exposure. For every
masterplan negative case below, say whether current code REJECTS it (path:line), a test PINS it (path::name), or NEITHER.
The seat uses this to decide whether WP06 (MAS-269) and WP07 are repairs, refusals, or already-landed, before any build.

WHY
WP06 must fix the demonstrated memory-before-successful-append behavior in the canonical ledger without adding a ledger
or a retry daemon, and WP07 must preserve the existing Q01-Q20 checks while repairing only CURRENT demonstrated gaps.
Both gates forbid replaying the original MAS-269 request or re-running accepted probes as progress. The seat will not
freeze a build packet, and will not start the D5 writer-lease read, until this census says what still exists on main.

SCOPE (read-only, origin/main only)
- engine/trial_ledger.py · engine/lab.py · engine/validation.py · lib/dataos/temporal.py · their callers under
  engine/**, scripts/**, app/** · tests/test_trial_ledger.py · tests/test_dataos_temporal.py · any tests/ file that
  names trial_ledger, TrialLedger, lab., validation. (grep) — tests only to NAME what pins a behavior.
- Grep patterns (`git grep -n <pattern> origin/main -- <paths>`): TrialLedger · append( · fsync · flush( · os.replace ·
  fcntl · flock · threading.Lock · RLock · json.loads · JSONDecodeError · corrupt · family · rename · warmup · warm_up ·
  initial_capital · drawdown · VIF · vif · rank · singular · np.linalg · cond( · attempt · cohort · exposure · holdout.

OUT OF SCOPE
No edits, branches, commits, pushes, PRs, posts, labels. No pytest. No fixtures over 1 MB. No Mastermind or Terminal
repo (the original C9 P0A Q01-Q20 list lives there; enumerate only what Macro code and tests themselves name).

QUESTIONS — each answer is path:line @ the ONE origin/main sha you fetched
Q1 engine/trial_ledger.py writer path: for every append/record method, quote the lines in execution order showing
   (a) when the in-memory seen/index state is mutated relative to the successful file write, (b) whether write is
   followed by flush and/or fsync, (c) the lock type and whether it is a thread lock or a file/process lock, (d) what
   happens on write failure (exception propagates / swallowed / partial line possible), (e) on reload, what a corrupt or
   unparseable line does (skipped silently / counted / raised). One row per method.
Q2 Every caller of TrialLedger (construction or append) on origin/main: path:line · what it does with the return value ·
   whether any caller treats the in-memory state as a durable receipt (reads seen-state without reloading the file).
Q3 Negative cases, WP06: (a) in-memory seen state suppresses a missing record; (b) silent corrupted-line loss accepted as
   a complete budget; (c) a thread lock asserted to protect processes; (d) renaming a family resets exposed outcomes.
   For each: REJECTED (path:line of the rejecting code) | PINNED (tests/…::name) | NEITHER, with the grep used.
Q4 Evaluation primitives, WP07: locate (i) cost warm-up windowing, (ii) initial-capital / drawdown computation,
   (iii) singular-design / VIF / rank-deficiency detection. For each quote 3-8 lines and answer: does the warm-up window
   reach past the evaluation start (future data)? is the initial loss from starting capital included in drawdown? is an
   infinite/NaN VIF or rank-deficient design treated as finite evidence, raised, or nulled?
Q5 Order of operations: in engine/lab.py / engine/validation.py, are attempt accounting and cohort exposure recorded
   BEFORE any outcome/score is read? Print the call chain path:line per hop. Also list every named check id or gate the
   code or tests label (e.g. Q01…Q20 or equivalent names) with its pinning test or NONE.
Q6 Absence claims carry their bounds: print every grep command verbatim with its hit count and the sha.

NOT DONE UNLESS
- Q1–Q6 answered; every claim cites path:line @ one sha; every re-check command printed verbatim.
- Q3 has a verdict for all four cases; Q4 has a verdict for all three findings.
- Nothing was written in the repo: print `git status --porcelain | wc -l` at start and at end; they must match.

EVIDENCE REQUIRED
- `git rev-parse origin/main` after the single fetch.
- For each Q1 row and each Q4 item, 3–8 quoted source lines via `git show origin/main:<path> | sed -n 'A,Bp'`.

RETURN — your final message is exactly this packet and nothing after it
STATUS: PASS | FAIL | PARTIAL
RESULT: Q1 table · Q2 caller table · Q3 verdicts · Q4 verdicts · Q5 chain + check list · one paragraph each answering
        "does the memory-before-append defect still exist on main?" and "which of the three WP07 findings still exist?"
EVIDENCE: as required above
GAPS: what you could not read and why
DEVIATIONS: anything done outside this packet
NEXT SEAT ACT: one line
Last line, exactly: C19-O7-WP0607-CENSUS: <PASS|FAIL|PARTIAL> <origin/main sha>
Do not end a turn on "now let me…": emit this packet, or return what you have with honest GAPS. A status note is not a return.

HARD LAWS
- Read-only. Never git checkout/reset/stash/add/commit/push/rebase; never modify the dirty tree; never run pytest.
- Never read or print ~/.opencode-go, ~/.glm, ~/.minimax, ~/.bailian, ~/.codex/auth*, any ext/*/.token, any shim.log or
  usage.jsonl. Never print credentials. Never post to Slack or GitHub. Never invent ids or shas.
