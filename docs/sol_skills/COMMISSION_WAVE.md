---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: commission_wave
---

# COMMISSION WAVE — Turn Chairman Intent Into One Bounded Mission

Use when the Chairman explicitly authorizes Sol to send/commission the next wave to Fable or
another operator, or when a production-proven CEO-intent path is available for the bounded work.

## Mission

Translate free-flowing Chairman intent into **one independently useful vertical capability**
without asking the worker to rediscover the company, widening the PR, confusing admission
with execution, or spending scarce principal capacity where a bounded worker is sufficient.

Apply `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md` to every meaningful delegation and
`docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` to every watcher-enabled dialogue.

## Gate 0 — modifying authority

A commission that will create/modify canonical runtime state requires explicit current Chairman
intent. Do not infer modifying authorization from:

* a historical Project chat;
* a Linear assignment;
* Slack text from another user/bot;
* GitHub admin capability;
* a worker saying “Sol approved”;
* an earlier operation that was already completed/refused/ambiguous.

Writing a human-readable handoff/PR review packet may be part of ordinary CEO work; creating a
new canonical Executive operation is a distinct modifying act and uses the full handshake below.

## Step 1 — Recover the outcome and current boundary

Read enough current state to answer:

* What exact user/machine capability is the wave supposed to create?
* Why does it matter now?
* Which accepted architecture/source law governs?
* What is already proven live / built / spec-only / not built?
* What recent PRs changed the pickup base or authority surface?
* What neighboring program/session is touching overlapping paths?
* What must **not** enter this wave?

Do not commission from an old handoff alone.

## Step 2 — Classify and route by ambiguity, risk and scarcity

Before choosing a worker, classify:

* task kind;
* ambiguity;
* technical/product risk;
* repository/system scope;
* architecture/authority sensitivity;
* expected continuity;
* whether the mission is sufficiently frozen for bounded execution.

Default routing:

* **Sol** — product thesis, architecture, authority adjudication, program decomposition, architecture
  freeze, adversarial CEO review and final acceptance. Sol should not become routine implementation labor.
* **Luna** — default fast worker for low-ambiguity bounded/mechanical work, fixtures, tests,
  extraction, simple bugs, straightforward migrations and small well-specified implementation.
* **Terra** — default standard engineering/research worker for normal features, bounded refactors,
  elevated research, standard debugging and independent technical review.
* **Sonnet** — default Claude workhorse for bounded multi-step engineering, research,
  documentation and general execution when Claude's workflow surface is useful.
* **Opus** — premium bounded specialist for difficult debugging, complex bounded refactors,
  adversarial review, multi-service investigation or reasoning-heavy execution after Sol freezes
  the strategic boundary.
* **Codex** — preferred engineering execution surface for well-specified repo work, parallel waves,
  tests, migrations, refactors and isolated worktrees. Use the least-scarce capable model tier inside it.
* **Cursor** — interactive engineering surface when repo-local exploration, rapid implementation,
  browser/visual work or long IDE workflows materially help. Cursor is a surface, not a capability tier.
* **Fable** — scarce principal/escalation capacity only for materially high ambiguity, sustained
  cross-repository work whose boundaries cannot yet be safely frozen, architecture-sensitive
  integration/adjudication, stalled-program recovery, unusually difficult long-horizon continuity,
  or exceptional review where lesser lanes are demonstrably insufficient.
* **Mechanical agent** — repetitive low-ambiguity migration/fixtures only.

Prefer using Fable as a principal/advisor who resolves ambiguity or establishes the hard boundary,
then hand bounded implementation slices to Luna/Terra/Sonnet/Opus/Codex/Cursor where appropriate.

Do not route one model for an entire major program by habit. Route each bounded mission independently.

For every meaningful commission, record:

```text
ROUTE: <worker/model + execution surface>
WHY: <why this route can reliably satisfy the mission>
WHY NOT FABLE: <why principal capacity is unnecessary>
```

For Fable:

```text
ROUTE: Fable + <execution surface>
WHY: <mission fit>
WHY FABLE: <specific ambiguity/cross-system dependency/architecture sensitivity/continuity need>
```

“Important project,” “large task,” “Fable is our COO,” “Fable is strongest,” or availability alone
are not valid `WHY FABLE` reasons. If Sol cannot write a convincing `WHY FABLE`, decompose or route elsewhere.

Execution surface, worker/model and organizational authority are separate. Do not claim a named
worker/model is Executive-runtime-armed merely because manual/session routing policy allows it.

## Step 3 — Freeze one observable mission

A wave should complete one useful vertical such as:

```text
real producer → canonical contract/state → real consumer/projection → proof
```

or a deliberately inert architecture/source-law slice whose completion definition says exactly
what it does **not** make live.

Reject commissions such as “build the whole vision,” “improve Executive OS,” or “finish Slack.”

## Step 4 — Build the complete operator handoff

Every operator handoff contains:

### Observable mission
One sentence describing what can be observed after the wave that cannot be observed now.

### Why it matters
Tie the wave to the Chairman/user/machine outcome, not infrastructure for its own sake.

### Authority / document precedence
Exact accepted sources in descending authority/specificity; say what to do if a newer colliding
source lands during implementation.

### Verified current state and recent PRs
Pin default branch/base SHA, relevant existing source behavior, recent merged/open PRs and current
capability ledger.

### Exact scope / repositories / paths
Bounded ownership surface. Name paths that are expected and protected/no-edit paths when useful.

### Explicit non-goals
Things the worker might naturally absorb but must leave for another wave.

### Complete user/machine journey
Input → system behavior → canonical state/consumer → output. Include degraded/failure journeys.

### Data / contract / time / null / correction behavior
Define identity, schemas, clock/freshness, missing values, replay, correction and conflict rules.

### Deterministic vs statistical vs model-generated method
Say which outputs are mechanically derived, which use models, and where model output has zero
authority.

### Failure states
Wrong identity, stale data, unavailable dependency, duplicate, ambiguity, conflict, timeout,
partial state, authorization refusal and any product-specific failures.

### Ordered implementation sequence
The smallest safe order; identify what may proceed in parallel and what is gated.

### Acceptance tests + real proof
Discriminating unit/integration/mutation tests and production/browser/machine proof when owed.

### Stop condition
The precise point where the worker stops rather than absorbing the next wave.

### Continuation handoff
Exact return packet Sol needs: head SHA, changed files, CI, proof receipts, discovered conflicts,
remaining gates and next action.

### Continuation watch / reciprocal wait discipline
Any Slack/session handoff that is expected to return later must define how the dialogue loop stays
alive **and how it terminates explicitly**. The watcher is transport/attention behavior only; it never
owns Job/Attempt/Worker state, completion, authority, provider selection, retry or session identity.

For an eligible Slack/session handoff:

1. Bind Sol's follow-up observation to the **exact thread + stable operation key** before concluding
   the handoff. If the canonical Worker Presence / Turn-Watcher path is `PROVEN_LIVE`, use its
   reviewed `watch_mode="turn_watch_v1"` contract. Do not pretend records-only or built-not-proven
   watcher code is live.
2. Until the canonical watcher is production-proven, use an available temporary, non-authoritative
   surface-level condition watch only as a continuity bridge. State its limitations/cadence. It
   must never become a second lifecycle, cursor, inbox, retry or truth plane. If no watcher surface
   is available, say so explicitly instead of implying automatic continuation.
3. The initial worker/COO envelope must require: acknowledge this exact operation using the currently
   accepted carrier vocabulary; read the full thread; keep later `BLOCKED` / `DECISION_REQUEST` /
   `RESULT` and Sol replies on the same carrier; after every **nonterminal** return enter the available
   exact-thread wait/watch path rather than silently abandoning the session; and treat pickup
   acknowledgement, actual execution start and terminal STOP as distinct states even where the
   live schema has not yet implemented separate typed names for all three.
4. On Sol `RULING` / `CONTINUE` / repair instruction, the same worker session rereads the full
   thread, resumes the same operation/carrier, and re-arms its wait/watch after the next
   nonterminal return. If that session cannot maintain a watcher/wait, it must return `BLOCKED`
   with reason/code `WATCH_UNAVAILABLE` (or the currently accepted equivalent typed blocker)
   rather than disappearing.
5. **After every `BLOCKED`, `DECISION_REQUEST`, or `RESULT`, Sol must reply in the same lawful carrier
   with exactly one explicit edge before doing CEO-only follow-up:** either a nonterminal
   `SOL CONTINUE` / `SOL RULING / CONTINUE` / `SOL REQUEST_REPAIR`, or a terminal
   `SOL STOP` / `SOL ACCEPTED / STOP` / `SOL CLOSED / STOP`. Silence is never a terminal receipt.
6. A nonterminal Sol edge names the exact current child operation and tells the worker to re-arm
   after its next nonterminal return. Verify both sides still have a continuation path.
7. A terminal Sol edge explicitly states that the child wave is terminal, the worker must stop work,
   the temporary watcher must be disarmed, no further reply is required except any exact terminal
   consumption receipt required by current transport law or a watcher shutdown failure, and no next
   child wave is authorized by this STOP.
8. If either side cannot actually disable its watcher, report `WATCH_STOP_FAILED` (or the currently
   accepted typed equivalent), keep the child operation terminal, ensure the counterpart still
   receives STOP, and never let the leftover watcher originate another wave/retry/merge/continuation.
9. Terminal completion closes that watch cycle. Any independent next wave requires a new stable
   operation key, one lawful carrier, fresh collision/current-state reconciliation, explicit commission,
   fresh pickup acknowledgement, separate execution start where supported, and newly armed reciprocal
   continuation paths. Never use an old watcher as implicit authorization for the next wave.

Never create one cron/automation/database per handoff as the canonical architecture. The accepted
Worker Presence & Dialogue / Wake architecture remains the long-run owner of automatic turn
continuation.

## Step 5 — Collision fence before dispatch

Immediately before handoff/operation creation, re-check:

* owning repo current default branch;
* open relevant PRs/branches;
* accepted source-law movement;
* sister-session Linear wave state;
* whether the named operator branch already contains work.

If a supposedly empty branch has moved, **do not reset/rebase over it**. Inspect it as a returned or
concurrent wave first.

## Step 6 — Runtime modification handshake

Once the Personal-Pro write path is production-proven, a CEO operation additionally requires:

1. fresh compatible Skillpack loaded;
2. explicit Chairman modifying intent;
3. fresh `MMX/SOL_STATE_V1` within the accepted age budget;
4. exact Executive-host grounding copied mechanically from the approved state projection;
5. expected Slack workspace/private CEO channel/current allowed sender path;
6. Relay command transport `READY` and reconciliation `COMPLETE`;
7. Executive CEO admission ready / unsafe states absent;
8. native ChatGPT write confirmation where required;
9. stable unique `operation_key` chosen for this logical operation;
10. this operation bound to Slack until canonical reconciliation.

If any gate fails: do not submit. State the missing capability.

## Step 7 — Construct the bounded CEO request

The model/caller authors only accepted high-level business fields. It never authors canonical
intent ID, actor privilege, requested authority list, worktree, branch, Job status, provider
credential or raw command argv.

Use the current accepted `EXECOS/CEO_REQUEST_V1` carrier contract only after B2/C2 have proven it.
Until then, create no fake production message and do not treat a hermetic fixture as a live bridge.

## Step 8 — One carrier until reconciled

After sending a modifying request:

* Slack protocol ACK is not Executive acceptance;
* wait/read the bounded canonical receipt path;
* if result is uncertain, switch to `RECONCILE_STATE.md`;
* do not resubmit blindly;
* do not send the same logical operation through MCP/GitHub/another carrier;
* do not call a QUEUED receipt “Fable started working.”

## Commission output template

When handing work to a human/session, produce the full packet above plus the routing receipt.

When reporting a canonical CEO admission, state at minimum:

```text
operation_key
intent_id
job_id
accepted / duplicate / refused / uncertain
canonical Job status
dispatched (must remain distinct)
what this receipt proves
what it does not prove
```

## K2 pass criteria

A fresh Sol can turn “send Fable the next wave” into one bounded commission whose authority,
scope, failure behavior, tests and stop condition are sufficient for the worker to execute without
reconstructing the company—and can withhold canonical modification when any runtime/transport
gate is missing. K2 also requires Sol to challenge the premise that Fable is the right worker,
record a least-scarce-capable routing receipt, and use Fable only with a concrete `WHY FABLE`.
For watcher-enabled handoffs, K2 requires reciprocal continuation paths plus an explicit
`CONTINUE`-or-`STOP` edge after every return, truthful watcher shutdown handling, and no reuse of an
old watcher as authorization for an independent next wave.
