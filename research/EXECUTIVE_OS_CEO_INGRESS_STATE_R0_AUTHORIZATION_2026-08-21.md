# Executive OS CeoIngress R0 — diagnostic hot-state authorization

**Date:** 2026-08-21  
**Linear:** MAS-107 / R0, parent MAS-48  
**Status:** RECORDS-ONLY POST-PR-A SOURCE LAW. NO RUNTIME OR SLACK IMPLEMENTATION IS SHIPPED BY THIS RECORD.  
**Pickup base:** protected Mastermind `master` `ada77ab927394c5e406108f2e0d48d96bd89a785`

## 0. Observable mission

Authorize exactly one later additive read capability on the already-merged dedicated Executive `CeoIngress` boundary:

```text
exact approved local peer
  -> existing dedicated CeoIngress AF_UNIX listener
  -> closed state request: mastermind.executive_ceo_ingress_state.v1
  -> transport-neutral mastermind.executive_hot_state.v1
  -> typed Executive service/runtime/grounding diagnostic state only
```

The capability exists so a least-privilege future Relay can determine why CEO modification is safe or unsafe without receiving the broad Operator command surface, a second runtime/service, raw SQLite access, the rich CEO boot packet, Agent OS prose, or a new state database.

R0 is architecture/source law only. B1 implements the authorized read and its outbound `MMX/SOL_STATE_V1` consumer later.

## 1. Authority and precedence

This record is subordinate to, and must be read with:

1. Mastermind PR #91 / `e61e48904302d0aae53baeab0e2681ee3fbec97d` — accepted dedicated CeoIngress parent architecture.
2. Mastermind PR #96 / `5f9016f2db45acf60d4344656d85dfc496b87252` — exact hermetic PR-A implementation/security/lifecycle law.
3. Mastermind PR #99 / `b02630fc1f3587672390b383998b28cb3206202f` — Personal-Pro shell / hot-state / read-before-write architecture amendment.
4. Mastermind PR #100 / `ada77ab927394c5e406108f2e0d48d96bd89a785` — Sol-accepted, merged PR-A implementation.
5. This R0 record — exact post-PR-A state-read authorization.

R0 does **not** retroactively widen PR-A. PR-A remains complete as exactly two merged schemas:

* `mastermind.executive_ceo_ingress_submit.v1`
* `mastermind.executive_ceo_ingress_status.v1`

The third state schema becomes implementation-authorized only after this R0 record is accepted and merged.

## 2. Current implementation facts R0 binds to

At pickup, merged Runtime enum truth is:

### Jobs

```text
QUEUED
RUNNING
CHECKPOINTED
RATE_LIMITED
FAILED
LOST
CANCEL_REQUESTED
COMPLETED
CANCELLED
```

### Attempts

```text
CLAIMED
RUNNING
CHECKPOINTED
CANCEL_REQUESTED
RATE_LIMITED
FAILED
LOST
COMPLETED
CANCELLED
```

### Workers

```text
AVAILABLE
BUSY
DRAINING
RATE_LIMITED
OFFLINE
ERROR
```

No synthetic Job status such as `BLOCKED` is authorized.

Merged `ExecutiveControlService` has one raw configured service state whose constructor accepts `READY` or `AWAITING_CANARY`; the existing PR-A admission predicate treats any other/future/dynamic value, including `QUARANTINED`, as unsafe. CEO submit/status admission additionally requires the in-memory dual-listener startup latch and host-owned `ceo_ingress_armed` flag.

R0 may project a closed normalized diagnostic vocabulary over those facts; it may not create new Executive lifecycle authority.

## 3. Closed request schema

The only new request frame authorized by R0 is:

```json
{"schema":"mastermind.executive_ceo_ingress_state.v1"}
```

Exact top-level key set: `{ "schema" }`.

There are no optional keys and no business inputs. In particular the caller cannot provide:

* observed grounding;
* operation/intent/job identity;
* objective, department, priority or workstream;
* execution profile or authorities;
* provider/model/credential information;
* paths, branches, worktrees or validation commands;
* requested status filters;
* Slack/channel/user metadata;
* timestamps or freshness claims.

Unknown/extra fields refuse `invalid_input`. Unknown schemas retain the existing `unsupported_ingress_schema` behavior.

The existing CeoIngress request ceiling remains 8,192 UTF-8 bytes and the existing one-frame/newline/strict-UTF-8 transport law remains unchanged.

## 4. Narrow post-PR-A parser/readiness correction

This is the only intentional lifecycle/security change R0 authorizes for later implementation.

### 4.1 PR-A behavior today

Merged PR-A authenticates exact peer UID, then applies the full CEO admission predicate **before reading the request body**. Therefore unarmed or dynamically unsafe service state cannot currently request diagnostics.

### 4.2 R0 behavior after implementation

The dedicated connection sequence becomes:

```text
1. exact configured peer UID authentication before body read
2. require dual-listener startup latch == true
3. read exactly one bounded newline-terminated UTF-8 JSON frame
4. inspect the closed schema discriminator
5a. state schema -> diagnostic read path
5b. submit/status schema -> apply the unchanged PR-A full admission predicate
                         -> only then delegate to existing business validation/read/mutation law
5c. unknown schema -> closed refusal
```

The startup latch remains non-negotiable. Before both listeners have successfully started, every frame still receives `ingress_unavailable` before business access.

The narrow difference is that **after successful startup and exact peer authentication**, an unarmed/unsafe peer may supply a bounded frame so the service can identify the state schema. This does not authorize submit/status business parsing, trusted-envelope construction, grounding comparison, Runtime mutation, quarantine clearing, arming, or generic Operator access.

A submit/status frame received while unarmed/unsafe must still refuse `ingress_unavailable` before calling the grounding provider, `ceo_request` business normalizer, `ceo_intent`, or Runtime business APIs.

Edits to PR-A behavior beyond this discriminator/readiness split are out of scope for B1.

## 5. `mastermind.executive_hot_state.v1` exact contract

The successful state result is exactly one object with this semantic shape:

```json
{
  "schema": "mastermind.executive_hot_state.v1",
  "generated_at": "2026-08-21T00:00:00Z",
  "snapshot_hash": "<64 lowercase hex>",
  "grounding": {
    "mastermind_sha": "<40 lowercase hex or null>",
    "macro_sha": "<40 lowercase hex or null>",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1 or null"
  },
  "service": {
    "service_state": "READY|AWAITING_CANARY|QUARANTINED|UNKNOWN",
    "ceo_admission": "READY|UNARMED|BLOCKED_QUARANTINED|BLOCKED_UNSAFE_STATE"
  },
  "generic_operator_mutations": "AVAILABLE|BLOCKED_AWAITING_CANARY|BLOCKED_QUARANTINED|UNKNOWN",
  "runtime": {
    "projection_state": "OK|DEGRADED|UNAVAILABLE",
    "jobs": {
      "total": 0,
      "by_status": {
        "QUEUED": 0,
        "RUNNING": 0,
        "CHECKPOINTED": 0,
        "RATE_LIMITED": 0,
        "FAILED": 0,
        "LOST": 0,
        "CANCEL_REQUESTED": 0,
        "COMPLETED": 0,
        "CANCELLED": 0
      }
    },
    "attempts": {
      "total": 0,
      "by_status": {
        "CLAIMED": 0,
        "RUNNING": 0,
        "CHECKPOINTED": 0,
        "CANCEL_REQUESTED": 0,
        "RATE_LIMITED": 0,
        "FAILED": 0,
        "LOST": 0,
        "COMPLETED": 0,
        "CANCELLED": 0
      }
    },
    "workers": {
      "total": 0,
      "by_status": {
        "AVAILABLE": 0,
        "BUSY": 0,
        "DRAINING": 0,
        "RATE_LIMITED": 0,
        "OFFLINE": 0,
        "ERROR": 0
      }
    }
  },
  "degraded": [],
  "do_not_submit": false
}
```

No additional top-level or nested fields are part of V1.

## 6. Grounding law

The state read reuses the same injected, trusted, value-only grounding provider already composed for PR-A.

It calls no Git subprocess and imports no CEO boot-packet builder. It may receive only the already-reviewed value shape:

```text
mastermind_sha
macro_sha
boot_packet_schema
```

Successful observation populates all three values.

If the trusted observation is unavailable or malformed:

```json
"grounding": {
  "mastermind_sha": null,
  "macro_sha": null,
  "boot_packet_schema": null
}
```

and `GROUNDING_UNAVAILABLE` is included in `degraded`; `do_not_submit` is true.

A diagnostic grounding failure does **not** erase otherwise available Runtime counts. State-read success may therefore be degraded rather than all-or-nothing.

The caller supplies no `observed_grounding` on the state frame.

## 7. Service/admission normalization

R0 freezes this precedence.

### 7.1 `service_state`

Normalize the service's current raw state as:

* raw `READY` -> `READY`
* raw `AWAITING_CANARY` -> `AWAITING_CANARY`
* raw `QUARANTINED` -> `QUARANTINED`
* any other/future/unreadable value -> `UNKNOWN` and degradation `SERVICE_STATE_UNKNOWN`

The state projector does not mutate the raw service state.

### 7.2 `ceo_admission`

Because the state request itself is available only after the startup latch is true, normalize in this order:

1. normalized service `QUARANTINED` -> `BLOCKED_QUARANTINED`
2. normalized service `UNKNOWN` -> `BLOCKED_UNSAFE_STATE`
3. `ceo_ingress_armed == false` -> `UNARMED`
4. normalized service in `{READY, AWAITING_CANARY}` and armed -> `READY`

`AWAITING_CANARY` deliberately permits CEO admission when armed, matching merged PR-A. It does not imply generic Operator mutation availability or worker/provider readiness.

### 7.3 `generic_operator_mutations`

Normalize only the reviewed service-state gate:

* `READY` -> `AVAILABLE`
* `AWAITING_CANARY` -> `BLOCKED_AWAITING_CANARY`
* `QUARANTINED` -> `BLOCKED_QUARANTINED`
* `UNKNOWN` -> `UNKNOWN`

This field does not claim a specific Operator command will succeed; authority, job state and other command-specific checks remain separate.

## 8. Runtime projection law

The projector uses the already-open `Runtime` and its typed registry APIs. No raw SQL, new SQLite connection, database path, `PRAGMA quick_check`, schema-migration dump, event-payload scan or direct table query is authorized.

For V1 the implementation may enumerate:

```text
runtime.jobs.list_jobs()
runtime.attempts.list_attempts()
runtime.workers.list_workers()
```

Each successful subprojection returns:

* `total` = exact number of returned typed records;
* every frozen enum member in `by_status`, including zero counts;
* sum of `by_status` exactly equals `total`.

A missing status key is not shorthand for zero.

If one subprojection cannot be produced safely, that subprojection is `null`, never an empty/zero success claim, and its fixed degradation code is added.

Runtime projection state:

* all three subprojections available -> `OK`
* one or two available -> `DEGRADED`
* none available -> `UNAVAILABLE`

A corrupt/unknown status that cannot be represented by the frozen enum fails that subprojection closed rather than minting a new status string.

## 9. Fixed degradation vocabulary

`degraded` is a sorted, duplicate-free array containing only:

```text
GROUNDING_UNAVAILABLE
SERVICE_STATE_UNKNOWN
RUNTIME_JOBS_UNAVAILABLE
RUNTIME_ATTEMPTS_UNAVAILABLE
RUNTIME_WORKERS_UNAVAILABLE
```

No exception messages, filesystem paths, URLs, secrets, arbitrary diagnostic prose or provider-auth diagnoses are allowed in this array or elsewhere in the state document.

A new degradation concept requires a later reviewed contract revision.

## 10. `do_not_submit` law

`do_not_submit` is conservative diagnostic policy, not authority by itself.

It is `false` only when all of these are true in the same snapshot:

* trusted grounding is available;
* normalized service state is `READY` or `AWAITING_CANARY`;
* `ceo_admission == READY`;
* Runtime projection state is `OK`;
* `degraded` is empty.

Otherwise it is `true`.

A future Slack Relay may add stricter transport/reconciliation/freshness gates in `MMX/SOL_STATE_V1`; it may never turn Executive `do_not_submit=true` into false.

Neither a green hot-state document nor `do_not_submit=false` dispatches work.

## 11. Hash and clock law

`generated_at` is a UTC RFC3339 timestamp at whole-second precision with a `Z` suffix.

`snapshot_hash` is SHA-256 over UTF-8 canonical JSON of the full hot-state semantic object **excluding both `generated_at` and `snapshot_hash`**, with:

* keys sorted lexicographically;
* separators `,` and `:` with no insignificant whitespace;
* Unicode emitted directly (`ensure_ascii=false` semantics);
* no NaN/Infinity values.

The hash is a semantic change detector, not a signature/authenticator.

Changing only the clock must not change `snapshot_hash`.

## 12. Null, correction and partial-failure law

Null means unavailable/unsafe-to-project, never zero and never "not applicable" unless this contract explicitly says so.

The only V1 null-bearing fields are:

* the three `grounding` values together on grounding failure;
* `runtime.jobs` on jobs projection failure;
* `runtime.attempts` on attempts projection failure;
* `runtime.workers` on workers projection failure.

No stale previous-success value may be copied into a new snapshot to hide a current failure.

Every request recomputes from current in-process service/runtime/grounding sources; there is no mutable state snapshot cache with independent authority.

## 13. Bounds and failure behavior

The semantic `mastermind.executive_hot_state.v1` document has a hard V1 ceiling of **8,192 UTF-8 bytes** after canonical serialization.

If the document cannot fit, state read refuses visibly with the existing `response_too_large` protocol code. It is never truncated and never drops enum keys or degradation entries to fit.

The enclosing existing CeoIngress response ceiling remains 32,768 bytes.

Unexpected projector defects that prevent a structurally valid V1 document use the existing fixed opaque `internal_error` behavior. Dependency exception text never reaches the caller.

## 14. Explicit exclusions

The hot state must not call, embed or derive from:

* full `ceo_boot_packet.build_packet` / Executive Inbox;
* Agent OS workstreams, decisions, handoffs or next-action prose;
* Linear or Slack APIs;
* GitHub APIs/subprocesses;
* repository roots/worktrees/branches beyond the trusted SHA values;
* Job objectives, results, errors, artifacts, command IDs or event bodies;
* provider/model/credential/auth diagnostics;
* secrets/tokens;
* database path, WAL/quick-check/migration details;
* arbitrary exception text;
* generic Operator command output.

No new database/table/cache/cursor/inbox/queue/socket/process/service/runtime is authorized.

## 15. Security rationale

### 15.1 Why not the broad Operator socket

The future Relay needs one read-only machine projection and, later, bounded CEO submit/status. Giving its principal the broad Operator dispatcher would expose unrelated backup/requeue/cancel/proof/service operations and turn transport compromise into a larger authority compromise.

### 15.2 Why not a fourth listener/service

A fourth listener would duplicate peer policy, startup/shutdown composition, lock ownership, failure behavior and runtime access while protecting no distinct authority boundary. The already-dedicated CEO-facing listener is the correct least-privilege home once R0 adds the closed read schema.

### 15.3 Why diagnostics survive blocked mutation

If the read disappeared whenever admission was unarmed/quarantined, Sol could not distinguish transport health from intentional Executive refusal. The state schema is therefore diagnostic after successful process/listener startup while submit/status remain fail-closed under the existing admission predicate.

## 16. B1 implementation acceptance matrix

R0 authorizes B1 implementation only if it proves at minimum:

1. exact state schema accepts `{schema}` and refuses every extra/missing/business field;
2. wrong/unavailable peer credentials refuse before body read exactly as PR-A;
3. startup latch false refuses state before body/business read;
4. after latch true, unarmed state read succeeds while submit/status still refuse before grounding/business access;
5. `AWAITING_CANARY` + armed: state says CEO admission READY and generic Operator mutations blocked;
6. dynamic `QUARANTINED`: state remains readable, says blocked, and cannot clear quarantine;
7. unknown service state -> fixed UNKNOWN/unsafe/degraded result;
8. trusted grounding success and opaque degraded grounding failure;
9. exact Job/Attempt/Worker enum census including zero keys;
10. one registry failure produces `null` + exact degradation code, never zero-success laundering;
11. all registry failures produce `UNAVAILABLE` without arbitrary backend text;
12. no raw SQL / `_database_health()` / boot-packet / Agent OS / subprocess / Slack import or call;
13. identical semantic state at two clocks -> identical `snapshot_hash`;
14. semantic mutation -> different `snapshot_hash`;
15. >8,192-byte semantic state refuses rather than truncates;
16. state read causes zero Job/Attempt/Worker/Event mutation;
17. existing PR-A submit/status golden, replay, readiness, error-opacity and handler-drain tests remain green unmodified unless a test must be deliberately extended for the new post-startup discriminator split;
18. mutation tests kill any widening that lets state input mutate, lets unarmed submit reach business code, invents statuses, forwards exception text or reuses stale values.

B1 may then add the real Slack outbound `MMX/SOL_STATE_V1` publisher as its separate consumer within the B1 commission, but R0 itself ships no Slack code.

## 17. Capability ledger after R0 merge

R0 merge would make true:

* post-PR-A state-read architecture = `SPEC_ONLY` / implementation-authorized;
* exact `executive_hot_state.v1` V1 contract = canonical source law;
* B1 = unblocked for implementation.

R0 merge would **not** make true:

* the state frame exists in runtime;
* `SOL_STATE_V1` exists in Slack;
* `#sol-runtime` exists;
* any production Relay/app/principal is installed;
* any Personal-Pro write path is live;
* S0 is proven;
* B2/C2 are authorized to start.

## 18. Stop condition

Stop after this records-only law is accepted and merged.

Do not implement the state frame, create `#sol-runtime`, provision a production Relay, start B2, arm CEO writes, repair provider auth, or touch Wake in R0.

The exact next critical-path wave after accepted R0 is **MAS-108 / B1 — Executive hot state + outbound `SOL_STATE` publisher**. S0 remains independently parallel and must pass before B2.