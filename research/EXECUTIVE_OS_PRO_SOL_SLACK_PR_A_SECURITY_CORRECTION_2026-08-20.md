# Executive OS Pro Sol Slack ingress — MAS-75 PR-A security correction R1

**Date:** 2026-08-20  
**Linear:** `MAS-75`  
**Status:** **RECORDS-ONLY / SECURITY CORRECTION. NO RUNTIME IS ARMED OR IMPLEMENTED BY THIS FILE.**  
**Parent record:** `EXECUTIVE_OS_PRO_SOL_SLACK_PR_A_IMPLEMENTATION_ADJUDICATION_2026-08-20.md`  
**Precedence:** this R1 correction is more specific and governs where it conflicts with the parent PR-A implementation adjudication. All parent laws not amended here remain binding.

## 1. Why this correction exists

Final adversarial review of the PR-A implementation adjudication found two implementation ambiguities that must be closed before a builder writes code:

1. `asyncio.start_unix_server(..., start_serving=False)` lets two servers be constructed safely, but the two later `start_serving()` calls are still sequential. Without an explicit readiness latch, one listener could briefly accept a real business request before the second listener has successfully entered service.
2. `common.redaction.sanitize_external_text()` is a secret/shape redactor and length bounder, **not a filesystem-path scrubber**. Its own contract deliberately preserves filesystem paths and URLs. Therefore a rule that forwards a merely “sanitized” grounding/backend exception conflicts with the stronger MAS-75 acceptance requirement that a fake host path in such an exception never cross `CeoIngress`.

Neither issue requires a new control plane, runtime state, protocol, store, or production configuration.

---

## 2. Dual-listener startup must be business-atomic, not only bind-atomic

The parent record's preferred `start_serving=False` construction remains correct, but the following readiness law is now binding.

### 2.1 Startup latch

Dual-listener composition owns an **in-memory, non-durable startup/readiness latch** for the dedicated ingress, default false. It is process lifecycle only and grants no durable authority.

Required sequence:

1. acquire the existing single Executive service lock/marker;
2. open and health-check the one Runtime and compose the supervisor exactly as current service startup requires;
3. construct/bind both Operator and CeoIngress servers with `start_serving=False` (or an equivalently proven no-accept mechanism);
4. validate both socket identities/paths and all constructor-time invariants;
5. start **CeoIngress first while its startup latch is still false**;
6. if an ingress connection arrives in this narrow interval, authenticate peer as usual but refuse before business parsing/mutation with `ingress_unavailable`; it may not reach grounding, Runtime business access, or `ceo_intent`;
7. start the existing Operator listener second;
8. only after both `start_serving()` operations succeed, set the ingress startup latch true and publish/set the ordinary service started marker/timestamp used to represent successful startup;
9. if either start operation fails, keep/reset the latch false, close every listener created by the attempt, perform owned socket cleanup, release the one service lock/marker, and re-raise.

This sequence deliberately avoids modifying the existing generic Operator request contract merely to coordinate the new listener. The generic Operator listener is the **second** server to begin accepting, so there is no interval in which Operator is publicly accepting while CeoIngress failed to start. The only possible pre-ready acceptance is on CeoIngress, whose explicit latch makes it refusal-only.

### 2.2 Startup tests

PR-A must prove:

- after both binds but before either serves, neither socket processes business requests;
- if CeoIngress begins serving but Operator `start_serving()` then fails, any racing ingress request gets only `ingress_unavailable`, creates zero Job, calls zero grounding provider, and reaches no generic dispatcher;
- startup failure tears both listeners down and the service is restartable under the same single lock law;
- after both listeners start and the latch becomes true, ordinary readiness law (`ceo_ingress_armed` + service-state allowlist) governs ingress;
- no request can set or alter the startup latch.

The startup latch is not the PR-C production `ceo_ingress_armed` readiness decision. Both must be true for business admission once production composition later exists:

```text
startup_ready == true
AND ceo_ingress_armed == true
AND service_state in {READY, AWAITING_CANARY}
```

PR-A may model both as injected/process-local policy; PR-C later binds the host-owned arming proof.

---

## 3. Grounding/provider/backend exception text is opaque on the CeoIngress wire

The parent record's statement that provider failures are “sanitized/bounded” is too weak for the dedicated ingress boundary and is superseded here.

### 3.1 `sanitize_external_text` is not a path-removal guarantee

Current `common.redaction.sanitize_external_text()` intentionally:

- removes environment/shape-matching secrets;
- removes control characters;
- bounds output length;
- **preserves filesystem paths and URLs by design**.

It may still be useful for internal/operator logging where that contract is appropriate. It is not sufficient evidence that host paths cannot cross a model-facing CeoIngress error response.

### 3.2 Wire error messages for external/internal dependencies

For expected CeoIngress failures whose underlying exception may contain host/environment/provider data, the wire response uses a **fixed code-specific message authored by the ingress**, never forwarded exception text.

At minimum:

```text
grounding_unavailable -> "trusted grounding is unavailable"
backend_unavailable   -> "Executive CEO ingress backend is unavailable"
backend_refused       -> "Executive CEO ingress backend refused the request"
internal_error        -> "Executive CEO ingress failed"
```

A stable internal exception **class label** may be logged locally if existing Executive logging policy permits it, but it is not required on the CeoIngress wire. The safest PR-A default is the fixed text above with no class name.

Validation/protocol refusals whose message is derived entirely from already-bounded caller fields or reviewed constants may remain specific enough to name the invalid field/value class. They still must not echo unbounded user prose.

Authority refusal may return fixed `authority_refused` text; it does not need to forward the nested `StateConflict`/authority exception message to prove the classification.

### 3.3 No-path/no-secret tests

PR-A must construct exceptions containing all of the following simultaneously:

- a fake absolute host path such as `/Users/operator/private/repo`;
- a fake production path such as `/var/db/mastermind-executive/secret-state`;
- a fake URL with a query value;
- a fake token/secret-shaped value;
- multiline/control characters.

Inject those exceptions separately from the grounding provider, canonical status/readback backend, and unexpected internal path. The CeoIngress response must contain **none** of the path/URL/secret substrings and must match the reviewed fixed code/message shape.

No test may claim `sanitize_external_text()` alone proves this invariant. A mutation that replaces fixed ingress text with `sanitize_external_text(str(exc))` must be killed by the no-path test.

---

## 4. Closed server error vocabulary after R1

The parent record's error **codes** remain unchanged:

```text
peer_credentials_unavailable
peer_denied
ingress_unavailable
unsupported_ingress_schema
request_too_large
response_too_large
invalid_json
invalid_input
invalid_intent_id
not_found
grounding_unavailable
grounding_mismatch
grounding_changed
operation_conflict
authority_refused
backend_unavailable
backend_refused
internal_error
```

`timeout` remains excluded from the PR-A **server** error vocabulary for a started canonical mutation under the parent timeout/effect-unknown law.

This R1 changes message provenance, not codes: external/backend exception text is opaque; caller-validation text may be specific only when it is derived from bounded reviewed request fields/constants.

---

## 5. Acceptance impact

A PR-A implementation cannot pass Sol review unless it now additionally proves:

1. the two listener binds are no-accept until explicitly started;
2. CeoIngress startup is refusal-only until Operator start succeeds and the startup latch flips true;
3. a second-listener start failure cannot create a Job through a racing ingress connection;
4. no provider/backend/internal exception can leak a filesystem path, URL, secret, traceback, or raw exception text across CeoIngress;
5. replacing fixed dependency-failure messages with the repository's ordinary sanitizer is detected by a regression/mutation test;
6. the new latch and handler-drain task set remain process-local lifecycle state only—no SQLite, queue, lease, request registry, or second authority.

All timeout/effect-unknown, shutdown-drain, replay, grounding, MCP compatibility, v1-only, no-edit, no-Wake, no-worker-execution, and no-production-arming laws from the parent adjudication remain binding.
