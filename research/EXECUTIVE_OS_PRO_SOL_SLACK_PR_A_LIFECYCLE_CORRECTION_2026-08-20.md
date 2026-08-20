# Executive OS Pro Sol Slack ingress — MAS-75 PR-A lifecycle correction R2

**Date:** 2026-08-20  
**Linear:** `MAS-75`  
**Status:** **RECORDS-ONLY / LIFECYCLE CORRECTION. NO RUNTIME IS ARMED OR IMPLEMENTED BY THIS FILE.**  
**Parent records:** PR-A implementation adjudication + R1 security correction  
**Precedence:** this R2 is more specific for service-lock/running-marker/startup-readiness semantics. R1 remains higher for opaque error handling and the refusal-only startup latch; the parent adjudication remains binding elsewhere.

## 1. Current source fact that must be preserved

Final source review found a wording ambiguity in R1: current `ExecutiveControlService` does **not** create its running marker after listeners become ready.

Today `_prepare_socket()` calls `_acquire_service_lock()`, and that operation:

- acquires the one non-blocking Executive service `flock`;
- writes/replaces the instance-owned `running_marker_path` containing the service `instance_id` + PID;
- does so **before** Runtime health, supervisor composition and listener startup;
- removes that marker only through `_release_service_lock()` when the same instance owns it.

That marker is therefore a **service-instance/lock ownership marker**, not a receipt that all listeners are accepting requests.

Current `_started_at` is set later, after ordinary listener startup succeeds. PR-A may add its own non-durable ingress startup latch as frozen in R1.

## 2. Do not move or reinterpret the existing running marker in PR-A

R1's phrase about publishing/setting a marker after both listeners start must **not** be implemented by moving the existing `running_marker_path` creation.

PR-A must preserve existing service-lock/marker timing and meaning:

1. `_prepare_socket()` / `_acquire_service_lock()` continue to acquire the single service lock and create the current instance-owned running marker before Runtime/listener startup, as current source does;
2. the marker remains evidence that this Executive service instance owns the service lock / startup attempt, not proof of request readiness;
3. dual-listener readiness is represented only by the new **process-local ingress startup latch** plus existing service state / `_started_at` behavior—not by a new durable marker or by changing the old marker contract;
4. on any startup failure, existing close/release cleanup must remove the current instance's marker and release the same one lock exactly as today;
5. no second lock, marker, readiness file, receipt, SQLite row or startup database is added in PR-A.

Production CEO-ingress readiness receipt remains PR-C and is separate from the current runtime-state running marker.

## 3. Correct dual-listener startup sequence after R2

The safe sequence is now explicit:

1. preserve current `_prepare_socket()` call and single lock/running-marker acquisition;
2. open/health-check the one Runtime and compose supervisor using current rules;
3. construct/bind Operator and CeoIngress servers with `start_serving=False` or equivalent no-accept construction;
4. validate listener/socket invariants;
5. start CeoIngress first while its **new in-memory startup latch remains false**; racing valid ingress peers may receive only `ingress_unavailable` before business parsing;
6. start Operator listener second;
7. after both start successfully:
   - set the ingress startup latch true;
   - set/update existing `_started_at` exactly where the service records successful startup (after both listeners rather than after only Operator);
8. on any failure:
   - keep/reset ingress startup latch false;
   - close any created/started listeners;
   - preserve existing dispatch cleanup semantics;
   - remove owned non-launchd socket nodes as applicable;
   - call the existing service-lock release path so the pre-created running marker is removed only by its owning instance;
   - re-raise.

Do not make the generic Operator handler consult the new ingress latch. Operator begins serving second; if Operator start succeeds, both listeners exist. If Operator start fails, only CeoIngress could have accepted during the narrow interval and R1 already makes it refusal-only.

## 4. Service startup/close invariants to test

PR-A must pin the existing marker semantics before and after the dual-listener refactor:

- after lock acquisition but before listeners start, the existing running marker may already exist exactly as current service law dictates;
- that fact does **not** make `startup_ready` true and does not allow CeoIngress business admission;
- a second service instance cannot acquire the service lock during this startup window;
- if second-listener startup fails, the marker/lock are cleaned through the existing release path and a fresh instance can then start;
- after both listeners successfully start, `_started_at` is non-null/current and ingress startup latch is true;
- `close()` drains CeoIngress handlers under the parent law, closes listeners, removes owned socket nodes, then releases the one lock/marker;
- `close()` remains idempotent and may not delete a running marker owned by another instance;
- no production acceptance code is changed merely to reinterpret the current marker.

A mutation that delays the existing `running_marker_path` creation until after listener readiness should fail compatibility tests. A mutation that treats marker existence alone as CeoIngress startup/readiness authority should fail the startup-latch tests.

## 5. No widening

This R2 changes no user-facing ingress schema/error code, no canonical CEO intent, no Runtime schema, no MCP behavior, no worker/provider/Wake behavior and no production config.

The final PR-A readiness predicate remains conceptually:

```text
existing Executive service instance/lock is valid
AND ingress startup latch == true
AND ceo_ingress_armed == true
AND current service_state in {READY, AWAITING_CANARY}
```

The first line is current service lifecycle ownership, not a new model/caller-supplied field. None of these conditions may be set by an ingress request.
