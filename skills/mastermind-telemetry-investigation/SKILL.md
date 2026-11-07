---
name: mastermind-telemetry-investigation
description: Investigate a Mastermind service, fleet, browser, tunnel, worker or data-pipeline reliability incident using bounded logs, metrics, traces, deployment events and request identities. Use for outages, freezes, latency, memory pressure or interrupted operations. Do not use for routine CI assertion failures or treat correlation, a healthy ping or a service restart as root-cause proof.
---

# Mastermind Telemetry Investigation

## Work inside the current assignment

Reuse the verified Mastermind source pin and applicable repository instructions; do
not restart full bootstrap for each observation. This method supplies no runtime,
tool grant, release approval or trade authority. Keep denied actions denied and
EFFECT_UNKNOWN on the original operation and carrier. Continue independent safe
work instead of widening access or retrying an uncertain effect. Use existing
Executive/Fabric, Agent OS, source, browser and deployment owners, not replacements.

## Anchor the incident

Record user-visible symptom, onset/observation times, affected target/generation,
operation/request/process identities, last known good behavior and impact scope.
Separate availability, correctness, freshness and latency. Confirm whether a
modifying request was sent before treating the effect as absent or uncertain.

Use the existing telemetry, host/Fleet, process and runtime owners. A log explorer
or source file is not a new incident state machine. Keep this method separate from
CI triage when the failure is a deterministic test assertion rather than an
operational incident. Read [incident cases](references/cases.md) as needed.

## Form competing explanations

Choose a small set of answer-changing hypotheses, including service/dependency,
resource pressure, transport, client, configuration and data-state explanations.
State the smallest observation that would distinguish them. Prefer exact targets
and time windows over broad process/log dumps. Preserve sensitive payloads at
source; retrieve counts, signatures, request IDs and relevant redacted excerpts.

## Correlate without inventing causality

1. Read the exact failing request/trace and bounded errors around the incident.
   Correlate request, worker, deployment and host identity; clock skew or mismatched
   generations can make an apparent timeline false.
2. Compare a relevant healthy control in the same interval and the affected target
   before onset. Distinguish missing telemetry from a measured zero. Account for
   sampling, dropped spans, incomplete pagination and counter resets.
3. Inspect latency distributions, saturation, queueing, CPU/memory/disk/network and
   dependency behavior only where each can change the explanation. A host average
   can conceal a single exhausted process; a successful ping proves little about
   authenticated file, tool, provider or database actions.
4. Check relevant deployment/configuration changes against event time, not merely
   the newest commit. A temporal association is a hypothesis until a mechanism and
   discriminating evidence support it. Do not infer model downgrades or hidden
   quota from slow responses.
5. Preserve original processes and effects. Never duplicate a job after a timeout,
   reset a lease or switch credentials/accounts to reproduce an uncertain effect.
   Use the original owner's bounded reconciliation read.

## Repair only the authorized causal scope

Prefer a reversible, minimal repair with a stated falsifier and known blast radius.
Do not kill unknown processes, restart security/authentication services, disable
checks, widen permissions, create new telemetry stores or raise concurrency just
to obtain a green metric. A restart can mitigate symptoms without identifying the
cause; state mitigation and root cause separately.

Re-exercise the original permitted consumer action and observe the relevant metric
or error signature after the change. Preserve normal workload and comparable
windows where possible. Follow the existing rollback/forward-repair owner rather
than inventing a second automation. Two equivalent no-delta diagnostics require a
new hypothesis or independent lane, not another unchanged polling cycle.

## Return useful operational evidence

Report impact and timeline; observed versus hypothesized cause; supporting and
contrary evidence; exact repair/effect state; tests and real-path readback; residual
risk; and the precise next recovery action. Distinguish source repaired, service
healthy, consumer action proven and full incident resolution. Save material
findings through the existing incident/source and Agent OS records, with readback.
