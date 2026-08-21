<!--
Mastermind-X tracked-work PR template for the Executive OS repository.

This file is an authoring aid, not execution authority. Replace every placeholder,
delete inapplicable guidance, and link the current canonical records. A PR may not
self-authorize a successor phase, production arming, Wake, or worker execution.
-->

Workstream: WS:<KEY> | NONE
Linear: MAS-### | NONE
Portfolio-Mode: tracked | maintenance_exception | workstream_creation | architecture_candidate
Wave: <bounded wave ID or maintenance label>
Authority: runtime | records | research | architecture | maintenance | production-proof
Completion: merge-is-done | built-not-proven | production-proof-required | acceptance-required

<!--
Use an exact canonical WS key—never fuzzy-match by title. Executive OS architecture
may legitimately use Workstream: NONE while no accepted organizational workstream
exists; in that case use architecture_candidate or a typed maintenance exception and
state the boundary explicitly.

`Fixes/Closes MAS-###` is allowed only when Completion is `merge-is-done`.
For every other completion class, use `Refs MAS-###` or the issue URL so merge
cannot erase production, independent-review, natural-time, or CEO acceptance gates.
-->

## Observable mission

<!-- One independently useful user or machine capability. Outcome before mechanism. -->

## Why it matters

<!-- Name the executive/user job, machine job, security boundary, operating burden, or capability unlocked. -->

## Authority and current-state receipt

<!--
List document precedence and the exact state verified immediately before editing:
- repository default-branch SHA;
- relevant open PRs and live worktree/path owners;
- accepted Executive architecture and direct organizational records;
- current boot/readiness/provider/canary/production state where relevant.

Stop rather than silently combining incompatible authority.
-->

## Exact scope

<!-- Repositories, owned capabilities/paths, protocols, schemas, producer and real consumer. -->

## Explicit non-goals

<!--
Name adjacent phases and authorities excluded. For Executive work, distinguish CEO
admission from worker execution, provider readiness, Wake, scheduling, production
installation, Slack networking, MCP schema, and autonomous continuation.
-->

## Complete user / machine journey

<!-- Include unavailable, refusal, duplicate/replay, ambiguous response, degraded, quarantine, split-deploy, and correction states. -->

## Data, identity, time, null, and correction law

<!--
State exact operation/intent/job/attempt identities, grounding, idempotency, clocks,
readback/reconciliation, null/refusal behavior, and durable correction rules. A caller
or model must not author privileged fields or silently re-ground stale work.
-->

## Method and authority boundary

<!-- Distinguish deterministic first-party policy from model-authored prose. Name what may not dispatch, execute, mutate, or widen authority. -->

## Security / authorization / failure states

<!-- Enumerate closed protocol schemas, peer/principal scope, fail-closed states, secret handling, timeout/readback law, and unsafe-state refusals. -->

## Ordered implementation sequence

1. Refresh current heads, open PRs, worktrees, and accepted architecture.
2. Freeze discriminating authorization/idempotency/failure tests before implementation.
3. Implement the smallest admission-to-canonical-consumer vertical.
4. Run adversarial/mutation/security and compatibility proof.
5. Prove the real production path only when this PR is authorized to arm it.
6. Update durable architecture/handoff state.
7. Stop at this PR's bounded capability.

## Acceptance tests and real proof

<!--
List exact commands, negative authorization matrix, idempotency/crash-window proof,
one-created/one-created counts, compatibility snapshots, production identity, or state
why production proof is explicitly not owed. Green CI alone is not acceptance.
-->

## Stop condition and continuation handoff

<!-- State the exact terminal condition, what remains unauthorized, and the cold-stranger return required for Sol. Do not absorb the next phase. -->

## Author checklist

- [ ] Exact `WS:<KEY>` / `MAS-###` / portfolio mode / wave / authority / completion fields are resolved.
- [ ] Current default branch, open PRs, worktrees, and path/semantic collisions were checked before editing.
- [ ] One independently useful capability is delivered; infrastructure names its real caller and canonical consumer.
- [ ] Scope and non-goals preserve accepted architecture and no-duplicate-control-plane boundaries.
- [ ] CEO admission, worker execution, provider readiness, Wake, installation, and production arming remain separate unless explicitly commissioned together.
- [ ] No duplicate identity, event, queue, scheduler, store, auth, grounding, dedupe, or lifecycle plane was created.
- [ ] Privileged fields are derived by trusted deterministic code; caller/model authority is bounded.
- [ ] Failure, timeout, replay, ambiguity, stale grounding, quarantine, and correction behavior is explicit and fail-closed.
- [ ] Tests discriminate the intended law; relevant mutations/adversarial attacks were executed.
- [ ] Real production proof is attached where `Completion` requires it—or the PR states why none is owed.
- [ ] Merge is not represented as proof, readiness, execution, or acceptance when another gate remains.
- [ ] Durable architecture/Agent OS/Linear state is reconciled with one exact lawful next action.
