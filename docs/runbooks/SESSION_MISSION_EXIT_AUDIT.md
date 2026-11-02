# Mission-exit proof-gap audit (read-only source candidate)

## Purpose

Prevent one recurring false-completion pattern: a terminal zero-exit analysis worker is
mistaken for accepted code delivery, or a successful CI/review from an unchanged head
is mistaken for the remaining commercial/production evidence. This is a bounded,
secret-free, standard-library diagnostic over an **operator-collected snapshot**.
It adds no owner, queue, retry, session, clock, autonomous watcher, permission,
credential handler, or publication right.

Current organizational owners remain Executive OS (Job/Attempt/consumption), Fabric
(result/acceptance), GitHub (source/CI/reviews), Agent OS (project continuity),
ProviderRealm (issuer attestation), and the original effect carrier (denial/unknown).

## Run and interpret

From the Mastermind repository root:

```sh
python3 -m scripts.ohf.mission_exit_audit research/fixtures/mission_exit_byteplus_20261101.json
```

The sample is a *historical illustration* of the November 1 BytePlus incident, not
live owner data, not a synthetic acceptance receipt and not an automatic status
refresh. It deliberately shows an unaccepted terminal analysis result, unchanged
source, CI/current-head MiniMax review already passed, and the exact denied source
write kept on hold. The script exits 1 for incomplete proof, 0 for a packet ready
for external canonical adjudication, and 2 for invalid/unreadable input.

No return value authorizes a source write, retry, account fallback, merge, spend,
START, approval or production activation. The caller must read current canonical
owners and apply the platform's existing authorization and effect fences. The
`held_actions` section never supplies a replacement execution carrier. A new task
may proceed only if genuinely independent in target, authority and effect, as
already determined by current protected law.

## Integration sequence and boundaries

1. Source tests + exact-head CI and independent review of this diagnostic.
2. Use the existing fresh-Sol/served-model evaluation owner to test realistic
   BytePlus-like scenarios: terminal analysis vs implementation, safety denial
   vs other independent work, current-head review invalidation, blocked provider
   versus session completion. Record actual served-model outcomes, not static
   source-test passes.
3. Integrate this helper's **read-only proof-gap shape**, if accepted, into the
   incumbent Executive/OS owner that already renders mission progress; do not
   create an alert daemon, second acceptance registry or independent task queue.
4. Release through the existing source/installation owners and prove three live
   interrupted/normal missions with zero lost/duplicated effects, verified
   original-parent consumption, and lower false-stop rate versus baseline.

This slice implements **Step 1 source candidate only**. It does not repair the six
BytePlus P2 findings, assign a commercial credential owner, run a billable canary,
restart a source writer, or resolve the earlier platform safety refusal.
