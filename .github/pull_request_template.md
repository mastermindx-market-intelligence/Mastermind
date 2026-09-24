Workstream: REQUIRED
Linear: REQUIRED
Portfolio-Mode: REQUIRED
Wave: REQUIRED
Authority: REQUIRED
Completion: REQUIRED

<!--
MAS-28 V1 canonical authoring grammar. The six contiguous lines above are the strict
header zone: replace every REQUIRED token with one concrete allowed value before a
report can be interpreted. This template is an authoring aid, not execution authority.

Allowed values:
- Workstream: WS:<KEY> | NONE
- Linear: MAS-### | NONE
- Portfolio-Mode: tracked | maintenance_exception | creates_workstream | architecture_candidate
- Wave: a non-empty bounded identifier
- Authority: implementation | records | research | maintenance | proof | deploy | architecture_candidate
- Completion: merge-is-done | built-not-proven | proof-required | acceptance-required | records-only

Use an exact canonical WS key—never fuzzy-match by title. Workstream: NONE is valid
only for an explicitly typed maintenance or architecture-candidate change. A PR may
not self-authorize a successor phase, production arming, Wake, or worker execution.

MAS28-V1-CONTRACT-SHA256: 9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e
MAS28-V1-RULESET-SHA256: 2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa

Native relationship law: `Fixes`/`Closes MAS-###` is permitted only when
`Completion: merge-is-done`. For every other completion class, use `Refs MAS-###`
or the issue URL; merge must not erase proof, natural-time, independent-review, or
acceptance obligations.
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
- [ ] Relevant tests pass and `git diff --check` passes.
- [ ] No secrets, environment files, runtime state, logs, caches, or backups are included.
- [ ] This branch was created from current `origin/master` in an isolated worktree.
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
- [ ] After merge, deploy the exact `origin/master` merge SHA with `scripts/deploy_from_git.sh` and verify the VPS `/health` endpoint returns HTTP 200.
