# Agent Dialogue Source Continuity

This runbook defines one shared, read-only receipt family for early remote checkpoints (RCH-P0) and remote-complete same-PR release transfer (RCH-1). It creates no database, daemon, queue, watcher registry, lifecycle, backup branch, retry/failover path, provider resume mechanism, merge authority, or organizational memory store.

## User and machine capability

A long source task can publish a coherent Draft/HOLD checkpoint before its reasoning session becomes fragile. A later session can prove whether the checkpoint is merely remotely recoverable or fully remote-complete. A separate maintenance-only release responsibility is eligible only after the builder result is accepted, terminal STOP is verified, the child watcher source is removed or safely suppressed, the branch writer is explicitly released, and current Git evidence still matches the receipt.

## Command

```bash
GITHUB_TOKEN=... python3 -m scripts.verify_source_continuity --config continuity.json
```

The command reads local Git and GitHub. It never pushes, edits a ref, changes a PR, merges, dispatches, resumes a provider session, or mutates a watcher. Exit 0 returns a verified receipt, exit 1 returns a typed contract refusal, and exit 2 returns one fixed non-echoing input/probe error.

## Receipt states

`CHECKPOINT_VERIFIED` means the exact remote PR/branch/head/tree/base/path set is safe and recoverable, while local/unpushed/dirty/effect/index-lock evidence remains sticky to the current owner. It never authorizes transfer.

`REMOTE_COMPLETE_VERIFIED` additionally requires local head/tree equality, zero unpushed commits, no in-scope or unowned dirt, no index lock, no local-only effect, and no open or unknown external effect. The receipt remains non-authoritative: `transfer_safe=false`, `grants_merge_authority=false`, and `grants_reassignment_authority=false`.

Every receipt is canonical-JSON content-addressed and includes exact source identity, changed-path and ownership evidence, current protected main, bounded probe digests, sticky reasons, and an actionable continuation handoff. Drift invalidates the digest.

## Release decision

`evaluate_release_transfer` may return `RELEASE_RESPONSIBILITY_ELIGIBLE` only when a fresh `REMOTE_COMPLETE_VERIFIED` receipt matches current remote evidence and all of these are true:

1. Sol accepted the builder RESULT.
2. Terminal STOP matches the builder operation and carrier.
3. The exact child watcher source is removed; `WATCH_STOP_FAILED` is acceptable only when the stale source is suppressed from new semantic wakes.
4. The branch writer is explicitly `BRANCH_WRITER_RELEASED`.
5. The release operation key is fresh and targets the same repository, PR, branch, head, tree, merge base, path set, and current main.
6. Requested work is maintenance-only: current-main join, checks, review, Ready, or merge adjudication.

Eligibility does not itself commission a receiver and grants no release, implementation, merge, retry, provider, RuntimeBinding, Wake, or Executive authority. Current Chairman/Sol intent, protected procedure, exact carrier, pickup/START, permissions, review and expected-head gates remain independently required.

## Failure law

Wrong head/base/path ownership, unsafe or credential-shaped source, closed/non-draft PR, collision, malformed evidence, stale receipt, missing STOP, unreleased writer, changed carrier, or widened actions fail closed. Error responses never echo hostile values, file contents, credentials, local absolute paths, Git stderr, or provider/session identifiers.

## Completion boundary

This source wave is `BUILT_NOT_PROVEN / PRODUCTION_INERT` after protected merge. Production acceptance additionally requires the incident #386 native exact-session Wake/continuation canary and Control Room agreement. Green CI, a receipt, or same-PR release eligibility alone is not production proof.
