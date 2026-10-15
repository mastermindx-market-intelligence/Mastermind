# Exact-candidate CI observation for an existing native executor

## Purpose and boundary

`python3 scripts/github_ci_candidate.py` connects real GitHub observations to the existing candidate classifier, material-change filter and process-local waiter. A native executor can spend one tool invocation awaiting CI rather than generating repeated reasoning turns. The command is GET-only and uses the installed GitHub CLI's existing account. It creates no scheduler, queue, credentials, persistent watcher registry, model invocation, merge or deployment operation.

This source candidate is not a fleet installation or an idle-chat wake service. A returned GREEN means only that the supported required check identities are satisfied in the sampled exact-candidate observation. Formal review, source custody, queue qualification, permission and product acceptance remain separate. Every output sets `release_authorized=false` and `wake_delivered=false`.

## Use the exact assigned candidate

From the operation's existing workspace:

```sh
python3 scripts/github_ci_candidate.py \
  --repository OWNER/REPOSITORY --pr PR_NUMBER --head EXACT_40_CHARACTER_SHA
```

One read returns immediately. To let an existing native/process owner await a pending candidate without an LLM polling loop:

```sh
python3 scripts/github_ci_candidate.py \
  --repository OWNER/REPOSITORY --pr PR_NUMBER --head EXACT_40_CHARACTER_SHA \
  --max-samples 60 --interval-seconds 60
```

`--max-samples` is the additional sample budget after the initial observation, not a runtime guarantee. The interval applies before every additional sample; request time is additional. Each individual CLI read has a 15-second timeout and bounded captured output. The waiter returns once on a terminal/material result, policy or identity conflict, a read failure, or bounded exhaustion. It does not retry a denied read or change accounts.

An already-running native parent uses its supported process/task handle and consumes the JSON and exit status in that same assignment. Keep that process handle and candidate identity in the existing frontier. Reconcile the original handle after lost output before creating another observer. Process-local registration is NOT a cross-process duplicate lock or proof of durable registration. The existing host/process owner must ensure one observer per candidate; do not launch duplicates from different chats.

A foreground command can complete independently of a Web turn only if its actual process owner preserves it. Neither publication of this script nor a PID alone proves an idle native chat will resume. Do not claim automatic original-parent consumption, whole-project completion or background Web reasoning from this command's output.

## Result handling

| Exit | Observation | Existing executor's next responsibility |
|---|---|---|
| 0 | GREEN | Read the exact current candidate/review/release state, then perform only the already-authorized next operation. |
| 1 | FAILED | Diagnose the binding check failure in the same source operation; preserve the failed evidence. |
| 2 | UNKNOWN or rejected read | Inspect the typed reason. Preserve actual permission refusals; do not infer missing evidence is green. |
| 3 | STALE | Stop using this result for the superseded head. Reconcile the actual intended candidate; do not silently rebind. |
| 4 | PENDING | The finite sample budget ended. This is not acceptance, delivered wake or a failed build. The existing owner decides the next legitimate wait. |

Do not wrap every nonzero exit in a generic retry. `material_return`, the decision digest, the observation source references and the exact candidate identify what was actually observed.

## Supported evidence and limitations

V1 supports open, same-repository PRs whose required status checks have an unambiguous GitHub Actions producer identity. It reads branch protection and active inherited branch rules, all bounded pages of check runs, the bound workflow and the exact current attempt's job membership. It rechecks the candidate, check policy and workflow generation after collection. A successful old check absent from the current attempt cannot qualify that newer attempt. When both workflow reads positively establish an active attempt whose current job is not yet present, the required check remains PENDING rather than interrupting the native wait. Completed/unknown workflows with missing membership, permission errors and generation changes still refuse; no old success is synthesized into a current result.

GitHub Actions `queued`, `waiting`, `pending`, and `requested` map to the existing nonterminal QUEUED state. IN_PROGRESS remains nonterminal. SKIPPED or NEUTRAL do not silently satisfy a required check. Unsupported producers, required-workflow rules, fork candidates, ambiguous latest generations, partial pages and changed identities are explicit errors, not policy waivers.

An unrelated target-branch commit or repository metadata update does not restart PR-head observation. The target branch identity and policy still must match. This is PR-head evidence, not the merge queue's integrated candidate qualification.

There is no claim that a multi-request REST observation is transactionally atomic. Its hashes bind the sampled content; later release operations must retain their own fresh expected-head and required-check controls.

## Verification and acceptance

The source tests cover real API shapes, generation/rerun changes, identity mismatches, policy movement, pending states, bounded wait/exhaustion and disallowed endpoints. A real GET-only sample of Mastermind PR #1201 is retained under `research/execution_throughput_20261015/live_read_pr1201.json`.

The exact validation manifest records two unresolved original pagination-fixture failures alongside passing cases; do not call the whole suite green. Their previously refused correction remains held. The independent review is a separate retained Fabric operation. This candidate must not be installed as an accepted release until those actual obligations are resolved.

The end-to-end programme still owes an authorized native executor consuming a material CI result and advancing a real product delivery after the initiating Web turn ends. This command supplies the read/wait boundary, not that entire proof.
