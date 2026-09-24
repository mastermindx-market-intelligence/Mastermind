# OCR-7 Cross-Host Operator Continuity Acceptance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the already-proven local cross-realm rollover to two physical worker hosts without creating another remote-execution system: one Fable orchestration Job begins on a Claude realm on host A, terminalizes safely, the normal Capacity Fabric claim selects an eligible Claude realm on host B for Attempt 2, MH1 carries that already-claimed Attempt to host B's local broker/credentials, and the fresh provider session consumes the same OCR-3 continuation contract while the logical Fable root/Slack thread remains stable.

**Architecture:** OCR-7 does **not** rebuild MH1. The existing `2026-08-27-hybrid-workforce-mh1-multihost-broker.md` plan remains sole owner of authenticated remote Worker Broker transport, local credential custody and remote effect-unknown law. OCR-7 adds only continuity integration/proof above accepted MH1: same Job/new Attempt, new host/Worker/account realm, fresh provider session, exact continuation capsule/ACK and current RuntimeBinding/Control Room projection. Host selection remains CF2-I placement among eligible Workers; remote transport resolves only after claim.

**Tech Stack:** accepted MH1 remote broker transport, CF2-I/RF1/HF1, OCR-3/4A/4/5/6, existing Executive Runtime/COO cycle/Operator Harness, pytest + real two-host proof.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-fable-root-seat-amendment.md`
- `docs/superpowers/plans/2026-08-27-hybrid-workforce-mh1-multihost-broker.md`

## Dependency Gate

Do not implement/claim OCR-7 until:

```text
MH1 accepted on at least two real hosts
OCR-5 local two-realm rollover accepted
OCR-3 continuation/binding accepted
OCR-4A/4 Claude rich operator accepted
CF2-I host-aware realm claim accepted
```

OCR-6 Slack/Steward product projection may proceed in parallel after OCR-5; full final UX proof includes it.

## Global Constraints

- One canonical Executive Runtime remains on the control host. Host B has no Executive Job/Attempt scheduler/database.
- Provider credentials remain host-local. No token/Keychain/auth-home copying A -> control host -> B.
- Host A -> B is a **new Attempt** because Worker/placement/host/auth realm changes.
- Capacity/Worker claim occurs before transport resolution. OCR-7 must not “pick M2 because M1 failed” outside CF2-I.
- A remote timeout/disconnect after modifying dispatch is `EFFECT_UNKNOWN` on the same Attempt/host. Never create Attempt 2 on another host until the source Attempt is reconciled and lawfully terminal/requeued.
- The first cross-host canary should use the same clean pre-candidate `QUOTA_OR_RATE_LIMIT` boundary proven by OCR-5; do not invent a new `DRAINED` lifecycle state merely to move hosts.
- If host A becomes physically unreachable without exact provider/process-effect proof, use existing LOST/reconciliation law only when its predicates are satisfied. Lack of connectivity alone is not proof of safe cross-host failover.
- RuntimeBinding public projection may expose opaque `host_ref`; never private IP/hostname/cert path.
- Slack parent/session/operation context remains unchanged. The underlying worker-attempt actor/application context changes.

---

### Task 1: Add cross-host continuation integration tests over the accepted MH1 client seam

**Files:**
- Create: `tests/test_operator_cross_host_continuation.py`
- Modify only current generic transport/continuity fixtures if required; no new remote transport implementation.

- [ ] **Step 1: Build a two-host hermetic fixture**

Represent:

```text
Worker A -> provider=claude, account_label=claude-pro-01, host_ref=host-A, transport=local/MH1-A
Worker B -> provider=claude, account_label=claude-pro-02, host_ref=host-B, transport=MH1-B
same RF1 tier + execution profile
```

Create root R + plan Job P with Attempt limit 2.

- [ ] **Step 2: Run Attempt P1 on host A to safe RATE_LIMITED**

Use the exact OCR-5 terminalization path: provider failure classified quota/rate limit, process writer dead/released, no candidate/result/effect unknown, epoch abandoned, P1/Job RATE_LIMITED.

- [ ] **Step 3: Requeue/claim P2 normally**

CooCycle requeues P. CF2-I sees A unavailable and B lawful/available; dispatch creates P2 with placement evidence for Worker/realm/host B.

Assert no OCR/MH1 code explicitly passes `host-B` or `worker-B` as a failover target in production path.

- [ ] **Step 4: Resolve MH1 only after P2 claim**

The existing `WorkerTransportResolver`/accepted equivalent resolves B's exact `host_ref` to the authenticated remote broker client. Host endpoint metadata does not alter placement.

- [ ] **Step 5: Start fresh Claude session and continuation**

P2 uses OCR-4 on host B. Require:

```text
provider session S2 != S1
P1/P2 account labels differ
P1/P2 host_refs differ
P1/P2 Attempt ids differ
same plan/root Job + COO responsibility
OCR-3 capsule source=P1 target=P2
PREPARED + first TX-5 APPLIED + continuation ACK exact to S2
```

- [ ] **Step 6: Complete P2 through normal Phase 1F-C law**

No special remote result path. Result returns through existing MH1 broker response, OHF evidence, shutdown/terminal seal and CooCycle plan admission.

- [ ] **Step 7: Run tests**

```bash
pytest -q \
  tests/test_operator_cross_host_continuation.py \
  tests/test_operator_cross_realm_continuation.py \
  tests/test_remote_worker_broker_client.py \
  tests/test_remote_worker_transport.py
```

- [ ] **Step 8: Commit**

```bash
git add tests/test_operator_cross_host_continuation.py
git commit -m "test(exec): prove continuation across claimed worker hosts"
```

---

### Task 2: Pin remote effect-unknown as a hard failover fence

**Files:**
- Modify: `tests/test_operator_cross_host_continuation.py`
- Modify current MH1 tests only if needed for exact integration.

- [ ] **Step 1: Lose response after P1 modifying request is fully sent**

MH1 returns/raises its accepted `EFFECT_UNKNOWN` classification.

- [ ] **Step 2: Assert zero movement**

Require:

```text
zero P1 RATE_LIMITED/LOST terminalization from connectivity alone
zero JOB_REQUEUED
zero P2
zero Worker B claim
zero remote request to host B
zero continuation PREPARED/ACK
```

- [ ] **Step 3: Reconcile same host/Attempt**

Only read/status/reconcile operations against exact P1/host A may proceed. Once canonical outcome is known, existing lifecycle law determines whether P1 continues/completes/fails/loses and whether a later requeue is lawful.

- [ ] **Step 4: Mutation tests**

Kill:

- network exception automatically marks source Attempt LOST;
- endpoint resolver tries second host;
- Capacity Fabric is re-run before old Attempt terminal;
- fresh provider session starts on B while P1 writer/effect unknown remains;
- Slack “transport degraded” interpreted as provider/runtime failure.

---

### Task 3: Extend RuntimeBinding/Steward projection with opaque host movement

**Files:**
- Modify after OCR-6 lands: `control_plane/operator_continuity_projection.py`
- Modify: `tests/test_operator_continuity_projection.py`
- Modify Control Room UI tests only.

- [ ] **Step 1: Preserve public privacy**

Projection shows only accepted opaque `host_ref`/host class, never endpoint/IP/hostname/certificate/key path.

- [ ] **Step 2: Show host change as execution evidence, not identity**

Stable:

```text
Mastermind · Fable
root/session/thread
```

Changed:

```text
Attempt/Worker/realm/host/binding/provider session
```

- [ ] **Step 3: Degraded remote transport state is distinct**

If MH1 transport is unavailable but current Executive state remains RUNNING/unknown, UI must say `TRANSPORT_DEGRADED` or `RECONCILIATION_REQUIRED`, not falsely claim another host took over.

---

### Task 4: Real M1 -> M2 two-subscription canary

**Files:**
- No source changes unless a current same-carrier defect is found.
- Sanitized receipts only.

- [ ] **Step 1: Re-pin exact host/runtime identities**

Require two OCR-1 native Claude realms on separate eligible host/principal pairs, MH1 installed/attested on both, current provider/capacity observations fresh, and no active colliding worker carrier.

- [ ] **Step 2: Run P1 on host A**

Capture current Attempt/Worker/account/host/provider session and real provider-capacity evidence.

- [ ] **Step 3: Reach a genuine safe provider capacity boundary**

Prefer provider-real quota/rate-limit. Prove exact provider writer shutdown and P1 terminal receipt before any remote B activity.

- [ ] **Step 4: Observe normal claim onto host B**

CooCycle/CF2-I must select B without Chairman/Sol manually naming the machine. Capture claim/capacity evidence digest.

- [ ] **Step 5: Prove continuation on host B**

Fresh provider session, exact capsule/ACK, real plan result, same root/session dialogue identity.

- [ ] **Step 6: Run separate MH1 ambiguity drill**

A harmless controlled modifying transport loses its response; prove zero automatic A->B movement until reconciliation.

- [ ] **Step 7: Product proof**

After OCR-6 core, show the same Control Room/Fable card/thread before and after host movement at desktop/narrow breakpoints.

- [ ] **Step 8: Return to Sol**

Return exact release head, P1/P2/Worker/opaque realm/host refs, MH1 request/receipt identities, capacity evidence, continuation ACK, result, negative effect-unknown zero-failover proof, CI/security and browser proof.

---

### Task 5: Extend to the third host without changing architecture

After M1->M2 acceptance, provision/attest the third eligible host through the existing MH1 plan and OCR-1 realm law. Run one independent bounded child on each of three hosts or a later safe rollover onto the third host. No new multi-host protocol, scheduler, host database or provider credential distribution mechanism is authorized.

## Stop Condition

OCR-7 stops when one real Fable/Phase 1F-C responsibility moves from host A to host B only **after** the first Attempt is canonically safe/terminal, the second host is selected through normal CF2-I claim, MH1 carries the new Attempt without credential copying, continuation is acknowledged on a fresh provider session, and a remote `EFFECT_UNKNOWN` drill proves zero host failover. The third host is expansion proof, not a new architecture.
