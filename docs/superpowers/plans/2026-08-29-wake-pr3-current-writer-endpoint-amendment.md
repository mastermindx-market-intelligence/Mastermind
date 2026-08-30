# Wake PR3 / WP-TW2 — Current Writer Endpoint Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Parent plan:** `docs/superpowers/plans/2026-08-29-wake-pr3-runtime-completion.md`  
**Operation:** `wake-pr3-wptw2-runtime-completion-plan-20260829-sol-001`  
**Protected reconciliation basis:** `Mastermind@0604158caca9e3b8a43ec57dd36ca4dadf05198b`, Skillpack v1.0.1 / bootstrap-major 1  
**Capability:** RECORDS_ONLY / no runtime authority

## 1. Narrow precedence

This amendment has precedence over the parent plan only for what an exact Codex `threadId` proves and what W3C must bind before provider mutation. Every other parent-plan owner, no-rebuild boundary, W3A/W3B scope, effect-unknown rule and completion ruler remains controlling.

## 2. Current first-party Codex finding

Current first-party Codex App Server behavior distinguishes two materially different paths:

1. **running-thread reconnect inside the owning persistent App Server** — `thread/resume(threadId=...)` can rejoin the already-loaded/running thread and preserve its active runtime;
2. **cold resume in another App Server process** — the same persisted thread identity can be loaded from durable thread history when it is not resident in that process.

Therefore:

> **Exact Codex thread identity is necessary but is not sufficient proof of exact current writer identity.**

A fresh standalone `codex app-server` process that cold-resumes the same persisted thread must not be treated as the current writer merely because the returned `thread.id` matches. Starting a new turn there while another process may still own the active task would violate Mastermind's one-writer/effect-unknown law.

This finding strengthens, rather than replaces, the existing MAS-237 RuntimeBinding requirement.

## 3. W3A interpretation

W3A remains a valid production-disarmed transport primitive:

```text
exact supplied thread id
-> initialize accepted App Server client
-> thread/resume(exact id)
-> turn/start(exact id)
-> accepted/delivered observation
```

W3A proves protocol behavior and pre-submit versus post-submit uncertainty. It **does not** prove that the supplied client is the current owning App Server/writer for a live Desktop/Codex task.

W3A MUST NOT:

- discover a thread by title, timestamp, OCR, window order or newest-session heuristic;
- claim that spawning a fresh App Server is equivalent to waking an already-running Desktop writer;
- select or rotate a RuntimeBinding;
- bypass an effect-unknown existing writer;
- become production-armed by merge alone.

Its capability state after merge, absent a real owning-endpoint canary, is `BUILT_NOT_PROVEN`.

## 4. W3C current-writer gate

Before W3C may issue the first real provider `turn/start`, trusted composition must prove all of:

1. the target `RuntimeBinding` is the current accepted generation for the logical session alias;
2. the binding names the exact Codex thread/native handle;
3. the binding also identifies or resolves the **current owning App Server/writer endpoint/process generation** through an accepted runtime-only seam;
4. the endpoint/process generation is still current immediately before provider mutation;
5. no unresolved prior writer/effect exists for the same logical operation that would make a second writer unsafe;
6. the provider client used by W3A is connected to that exact owning endpoint, rather than merely cold-resuming the same persisted thread in a fresh standalone process.

If exact current writer/endpoint cannot be proven:

```text
SESSION_LOST / RUNTIME_BINDING_RECONCILIATION_REQUIRED
```

or the current accepted typed equivalent applies. No provider call, GUI fallback, new App Server writer, retry or failover is authorized.

## 5. MAS-237 requirement strengthened

MAS-237 must not stop at:

```text
session_alias + binding_id + generation + native thread id
```

for the production Codex wake path if those fields cannot prove the current writer endpoint.

The accepted production projection must carry or resolve enough runtime-only evidence to bind the exact current writer/process endpoint without checking that coordinate into Git or Slack. If an existing RuntimeBinding/Operator-Harness seam already owns that evidence, extend/project it; do not create a second provider-session registry.

## 6. Canary falsifier

A real W3C canary fails if any of the following is true:

- the canary starts a fresh standalone App Server and only proves the same thread ID;
- two processes can concurrently issue turns to the same logical task under one supposedly current binding;
- the old active writer is effect-unknown when the new writer begins;
- endpoint/process generation changed after route derivation and before provider submission;
- success is inferred from resumed history rather than a turn on the exact current owning endpoint.

The canary passes this gate only when the exact current writer is proven before the single persisted provider submission.

## 7. Do not rebuild

Do not create a new writer registry, thread database, GUI/session selector, daemon, provider lifecycle owner or retry system to satisfy this amendment. Reuse the canonical RuntimeBinding / Operator Harness / Codex App Server ownership seams and extend only the missing runtime projection needed to prove the current writer.
