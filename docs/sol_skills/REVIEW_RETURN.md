---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: review_return
---

# REVIEW RETURN — Adversarially Review Work Against Intent

Use when Fable, Claude, Codex, Grok, a mechanical agent or another session returns a PR,
research packet, production receipt or claimed completion.

## Mission

Decide whether the returned work actually advances/completes the **original user/machine
outcome**, not merely whether its code is competent or CI is green, while ensuring a watcher-enabled
worker is never left indefinitely waiting for Sol's ruling.

Apply `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` whenever the returning counterpart is on a
watch/wait path.

## Step 1 — Recover the authority packet

Before reading the worker's self-assessment as truth, recover:

* original Chairman/Sol outcome;
* governing architecture/source-law documents and precedence;
* exact commissioned scope and stop condition;
* builder pickup base and any newer accepted authority that landed during the wave;
* explicit non-goals;
* required production/browser/machine-consumer proof.

The worker's prompt/PR body is evidence of what it believed the commission was; it is not
higher authority than the accepted architecture.

## Step 2 — Verify current implementation identity

Pin:

* repo;
* PR number;
* exact head SHA;
* base/merge base;
* changed files;
* current CI/check state;
* whether another overlapping PR/source-law change landed after pickup.

Do not review a mutable branch name as if it were an immutable artifact.

## Step 3 — Ask the Sol review questions

For every substantive return, answer:

1. Can the primary persona complete the primary task now?
2. What user or machine capability exists that did not exist before?
3. Did the worker preserve the full product thesis or narrow it to implementation convenience?
4. Is any feature technically present but practically useless/dark/disconnected?
5. Is a spec/docs/schema being called shipped?
6. Did foundation/infrastructure replace product or intelligence?
7. Are claims grounded at the precision promised by the architecture?
8. Did the worker create a duplicate control/state/memory/authority plane?
9. Can the result be seen on the real production/user/machine-consumer path when proof is owed?
10. What discovery/ruling must be durable for the next session?

## Step 4 — Review the diff against boundaries, not aesthetics

Prioritize:

* authority widening;
* duplicate state/policy implementations;
* bypass of the canonical sink/owner;
* hidden persistence;
* caller/model-supplied privileged fields;
* stale/replay/TOCTOU/correction behavior;
* error leakage/secret/path exposure;
* false completion/health claims;
* unreviewed fallback/failover;
* production configuration or credentials smuggled into a hermetic wave;
* required consumer missing despite infrastructure landing.

Avoid expanding the review into unrelated cleanup. A real adjacent defect becomes a separate
bounded follow-up unless it makes the current capability unsafe/false.

## Step 5 — Test claims with discriminating evidence

Prefer tests/probes that would fail under the exact forbidden mutation, not generic coverage.

Examples:

* move grounding observation before durable replay lookup;
* remove pre-commit reread;
* change fixed opaque error to forwarded exception text;
* make `dispatched=true` appear on admission;
* duplicate a supposedly canonical normalization law;
* mark a docs PR as implementation complete;
* disconnect the real consumer while leaving producer tests green.

If the worker reports a mutation kill, verify the test actually distinguishes the law rather than
failing for an unrelated reason.

## Step 6 — Separate findings by release consequence

Use three practical classes:

**BLOCKER** — violates architecture/authority/security/canonical truth or makes the promised
capability false. Must repair before acceptance.

**MAJOR / follow-up required** — capability can be correct but a material usability/operability
issue needs its own bounded wave.

**NONBLOCKING** — cleanup/clarity that does not change the promised outcome or authority.

Do not turn every nit into a release block. Do not waive a constitutional boundary because the
rest of the implementation is excellent.

## Step 7 — If requesting changes, bound the repair

A change request should say:

* the exact violated law/source;
* the concrete current behavior;
* why tests/parity/prose do not satisfy the law;
* the smallest acceptable repair;
* frozen compatibility/non-goals that must remain unchanged;
* the discriminating regression required;
* the exact evidence to return.

Do not send the builder back to “rethink everything” unless the architecture itself failed.

## Step 8 — Acceptance law

Accept only when:

* every blocker is closed on the exact current head;
* required hosted CI/checks are green on that head;
* the changed-file set and authority surface remain bounded;
* production/browser/consumer proof exists when the wave owes it;
* the capability ledger is updated truthfully;
* no higher-priority accepted source law collided during review.

A records-only architecture PR may be accepted without production proof when its contract says
implementation is a later wave. An implementation PR may be `BUILT_NOT_PROVEN` when production
proof is explicitly deferred. Preserve those distinctions.

## Step 9 — Close or continue the reciprocal dialogue explicitly

A worker return does not become terminal merely because Sol has enough information to continue
CEO-only adjudication.

After every watcher-enabled `BLOCKED`, `DECISION_REQUEST`, or `RESULT`, Sol must post **exactly one
explicit edge in the same lawful carrier/thread before leaving that dialogue turn**:

### Nonterminal

Use `SOL CONTINUE`, `SOL RULING / CONTINUE`, or `SOL REQUEST_REPAIR` (or the exact currently
accepted semantic equivalent). Name the exact child operation, state the next action, and tell the
worker to re-arm its watcher after its next nonterminal return.

### Terminal

Use `SOL STOP`, `SOL ACCEPTED / STOP`, or `SOL CLOSED / STOP`. State that the child wave is terminal,
tell the worker to stop work and disarm its temporary watcher, state that no further reply is needed
except any exact terminal consumption receipt required by current transport law or watcher shutdown
failure, and state that this STOP authorizes no independent next wave.

If final CEO review/merge/release work remains after the worker portion is complete, **STOP the
worker child wave first** and conduct that CEO work outside the child operation. Never leave a worker
on an armed watcher because “the next step is mine.”

If watcher shutdown fails, report `WATCH_STOP_FAILED` (or current accepted equivalent), keep the
child operation terminal, and never let the leftover watcher originate another continuation.

## Review-return output

State:

```text
Verdict: PASS | REQUEST_CHANGES | HOLD | BLOCK
Exact head reviewed
Capability gained
Blocking findings
Nonblocking residue / separate follow-ups
Proof reviewed
What the merge would and would not make true
Exact continuation action
Dialogue edge: CONTINUE | STOP | NOT_WATCHER_ENABLED
Watcher state: ARMED | DISARMED | WATCH_STOP_FAILED | NOT_APPLICABLE
```

## K1 pass criteria

A fresh Sol reviewing a worker return must catch a technically green architecture violation,
false completion, duplicate authority/policy implementation or missing real consumer without
needing the original authoring session's hidden reasoning. For watcher-enabled returns, K1 also
fails if Sol leaves the counterpart waiting without an explicit nonterminal continuation or terminal
STOP edge.
