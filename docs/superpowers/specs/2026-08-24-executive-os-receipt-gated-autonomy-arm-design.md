# Executive OS receipt-gated autonomy arm

**Date:** 2026-08-24

**Status:** Chairman-approved in chat and frozen for implementation

**Protected-master base:** `4d323d03e4151449a4b76abfdfefca1d56825fde`

**Lifecycle authority:** Mastermind Executive Runtime only

**Implementation truth:** protected GitHub history and the exact installed release

## 1. Observable mission

Turn a formally accepted, exact-release Executive OS host from deliberately
unarmed into one autonomous production system without creating another
scheduler, session controller, queue, identity store, credential plane or
operator ritual.

After this wave, one root-authorized, receipt-gated operation can enable the
existing local path:

```text
typed strict-v2 CEO intent
        |
        v
Executive Runtime root Job
        |
        v
existing bounded COO tick
planner -> work -> independent review -> repair/null -> aggregation
        |
        +-> sealed Codex exec worker
        |
        +-> read-only Codex App Server parent
              + exact OpenAI Docs MCP
              + one inherited read-only native helper
```

The Chairman supplies intent once. Executive Runtime continues to own every
Job, Attempt, Worker, lease, quota claim, process generation, session epoch,
event and terminal result. Agent OS remains durable organizational knowledge,
not execution authority.

## 2. Current state and problem

Protected master already contains the production-unarmed G0-G4 composition:

- `coo_autonomy_armed=false` gates the existing deterministic service-owned
  COO tick and explicit `run-coo-cycle` action;
- `coo_operator_harness_armed=false` gates the existing semi-headless
  App Server planner;
- the selected planner profile is
  `operator.appserver.readonly.docs-mcp.native-helper.v1`;
- the profile digest is
  `536853fb01d69ae8deca9a028b55c90aea0d1529f1fc80d83bb20d5d54f2cc44`;
- the capability-policy digest is
  `b8fbfd9065764206b03f835f7fbc09910326f806584a8185229474aff59008b7`;
- the native-helper grant digest is
  `2d5929ea453f368e7b3284b8509fd6e70d5ac16409642c216217c8fb78908c40`;
- the App Server security-config digest is
  `89612a1d7a64a77b9b42fab1522cab3465a7a763ba5be696f8a952ba7eaa366f`;
- plugins remain empty; and
- Executive MCP remains read-only or fixture-only.

The installer can render an operator-supplied control config, but that is not
an activation protocol. It does not bind a passing host acceptance receipt,
Gate B, current provider readiness, both installed configs, runtime quiescence,
service restart or rollback into one operation. Flipping JSON manually would
therefore be operationally ambiguous and would allow readiness expiry to leave
an apparently armed service running.

## 3. Scope

### In scope

1. A root-only installed `status`, `arm` and `disarm` control surface.
2. Exact-SHA, acceptance, Gate B and provider-readiness verification before arm.
3. Canonical Runtime inspection proving no live or ambiguous Attempt exists.
4. A crash-recoverable transaction across the existing control and worker
   configuration files.
5. One non-secret, tamper-evident latest-state receipt under the existing
   Executive system config root.
6. Control-service and worker-broker enforcement of that receipt whenever the
   armed path can admit or start provider work.
7. Automatic refusal of new autonomous work after the readiness deadline or
   credential/readiness invalidation.
8. Deterministic tests, mutation tests, exact-host acceptance and one real
   strict-v2 end-to-end production proof.
9. Runbook and durable Agent OS closeout updates.

### Explicit non-goals

- no new Job, Attempt, Worker, Event, session or queue table;
- no second scheduler, daemon, background watcher or sidecar;
- no login, device authorization, account switching or secret resolution from
  an Executive Job, model, helper, MCP tool or plugin;
- no credential content read, copy, log, argv, environment inheritance or
  receipt field;
- no production-write mode for Executive MCP in this wave;
- no Slack ingress or Wake transport activation;
- no plugin grant or dynamic plugin installation;
- no MCP OAuth enrollment; the existing Docs MCP grant remains unauthenticated;
- no write-capable native helper;
- no change to the G4 profile, capability-policy or security-config digests;
- no Multilogin lifecycle action or retry; and
- no change to Chairman browser profiles.

## 4. Chosen architecture

### 4.1 One post-acceptance transaction

Add an installed Python entrypoint:

```text
ops/executive_os/autonomy_control.py
```

It runs only under the pinned Executive Python with effective UID 0. Its three
commands are:

```text
status  --expected-sha SHA
arm     --expected-sha SHA --gate-b-receipt PATH
        --expected-credential-kind KIND
        --workspace-binding-class company-workspace-admin-attested
        --credential-expires-at UTC
disarm  --expected-sha SHA
```

`status` is read-only and returns a closed, secret-free state. `arm` is the only
operation that can move both installed arm bits from false to true. `disarm` is
the only supported recovery and rollback operation; it always converges both
installed arm bits to false and stops both services before reporting success.

There is no generic config editor and no caller-supplied path for the installed
system root, runtime root, control config, worker config, readiness receipt,
arm receipt, service labels or release root. The expected SHA and Gate B receipt
are bounded inputs; all production paths are constants derived from the exact
installed SHA.

### 4.2 Why this shape

Three approaches were evaluated:

1. **Post-acceptance transaction — selected.** Separates inert installation,
   readiness, formal acceptance and production activation. It gives rollback
   one clear owner and receipt.
2. **Install directly with an armed control config — rejected.** This mixes
   deployment with activation and may run acceptance while autonomous work is
   eligible.
3. **New arming sidecar or launcher — rejected.** It duplicates lifecycle and
   process-control authority and creates another availability boundary.

## 5. Authority and admission gates

`arm` must prove every predicate before it writes a config byte:

1. macOS, EUID 0 and the exact pinned Executive Python are active;
2. the exact release directory/manifest, both LaunchDaemon working directories
   and program arguments, formal-acceptance receipt and requested SHA all
   identify the same already reviewed commit; protected-master ancestry is
   deployment evidence, not a volatile live-network arm predicate;
3. the installed release, config roots, runtime roots, plists, Codex binary,
   Python runtime and receipt ancestors retain the existing owner/mode/no-ACL/
   no-symlink requirements;
4. the formal acceptance summary exists below
   `/var/db/mastermind-executive/control/acceptance/<sha>/`, is a safe immutable
   file, names the exact SHA and says `passed=true` with every named acceptance
   predicate `PASS`;
5. the caller-supplied Gate B receipt is root-owned, mode `0600`, no-ACL,
   single-link, bounded, schema-valid, `passed=true` and names the exact SHA;
6. `provider_readiness.py reuse` validates the existing passing readiness
   receipt against the unchanged auth-file metadata, installed Codex binary,
   requested credential kind, company binding class and exact credential
   expiry/revalidation deadline; this command never reserves or spends a
   provider canary;
7. at least thirty minutes of readiness remain;
8. the control and worker configs are safe, schema-valid, mutually consistent,
   exact-host configs and both are currently unarmed;
9. the control and worker LaunchDaemons can be stopped and proven unloaded;
10. the canonical Runtime opens with `create=False`, passes integrity checks,
    and contains no Attempt in a live, cancel-requested, effect-unknown,
    identity-ambiguous or otherwise nonterminal execution state;
11. there is no live process owned by either Executive service UID after the
    existing bounded stop/sweep boundary; and
12. no incomplete autonomy transaction already exists.

Any missing, malformed, stale or ambiguous predicate refuses before config
mutation. The tool never repairs receipt content, guesses credential kind,
extends a deadline or treats login status as readiness.

## 6. State and transaction model

### 6.1 Closed states

`status` emits exactly one of:

- `UNARMED` — both configs false, services stopped or safely startable, no
  passing arm receipt required;
- `ARMED_READY` — both configs true, passing arm receipt matches them, readiness
  remains current and both services report `READY`;
- `ARMED_DEGRADED` — both configs and receipt agree on armed state, but services
  are stopped/unavailable or readiness is near expiry; no new provider work is
  eligible;
- `TRANSACTION_INCOMPLETE` — the root transaction marker exists;
- `CONFIG_DRIFT` — the two arm bits, config digests or receipt disagree;
- `READINESS_EXPIRED` — the armed receipt deadline has passed;
- `EFFECT_UNKNOWN` — process/service/config identity cannot be reconciled.

No state is inferred from prose or a single LaunchDaemon label.

Classification precedence is fixed and tested: `TRANSACTION_INCOMPLETE`, then
`CONFIG_DRIFT`, then `EFFECT_UNKNOWN`, then `READINESS_EXPIRED`, then
`ARMED_READY` or `ARMED_DEGRADED`, and finally `UNARMED`. A higher-precedence
unsafe condition is never hidden by a lower-precedence nominal condition.

### 6.2 Files

Reuse the existing config root:

```text
/Library/Application Support/MastermindExecutive/config/
```

Add:

```text
autonomy-state-v1.json
autonomy-transaction.lock/
```

`autonomy-state-v1.json` is `root:wheel`, mode `0444`, single-link, no-ACL and
non-secret. Its ancestors remain root-owned and non-writable by either service
principal, so both principals can read one canonical receipt but neither can
replace it. It contains only:

- schema and closed state (`ARMED` or `DISARMED`);
- exact release SHA;
- acceptance and Gate B receipt SHA-256 digests;
- provider-readiness receipt SHA-256 and its existing credential/readiness
  expiry timestamps;
- credential kind and binding class, never account identity;
- before/after control and worker config SHA-256 digests;
- frozen G4 capability/profile/helper/security digests;
- transaction ID, observed timestamp and tool version; and
- closed predicates.

It is an operational configuration receipt, not a Job/Event/session store.

The transaction directory is root-only mode `0700`. It contains immutable
copies of the two prior secret-free configs, their identities/digests, the
target digests and a closed phase marker. Each file and directory is fsynced.
An existing marker blocks `arm`. `disarm` validates the marker and converges to
known unarmed configs; it never guesses that a partial arm succeeded.

### 6.3 Config commit

With services stopped:

1. write and fsync both candidate configs inside the root-owned config
   directory;
2. validate them through the existing control and worker config loaders under
   their real service UIDs;
3. record the prepared target identities in the transaction marker;
4. atomically replace the worker config, fsync the directory, then replace the
   control config and fsync again;
5. write the `ARMED` receipt binding both final digests and fsync it;
6. start the same two LaunchDaemons through `service-control.sh`;
7. wait for exact PID/principal/socket/status attestation and service
   `READY` within a bounded timeout; and
8. remove the transaction marker only after every proof passes.

The two config renames cannot be one filesystem syscall, so stopped services
and the durable marker are load-bearing. A crash between renames cannot start a
mixed configuration. On any synchronous failure, the tool stops services,
restores both prior configs, writes `DISARMED`, verifies the rollback and only
then removes the marker. If rollback cannot be proven, the marker remains and
the result is `EFFECT_UNKNOWN`; automatic retry is forbidden.

`disarm` follows the same transaction law in the shrink-only direction. It
stops services first, sets both arm bits false, writes a matching `DISARMED`
receipt and leaves services stopped. Starting an unarmed accepted service later
is an explicit service-control operation, not implicit re-arming.

## 7. Runtime enforcement

Configuration alone is not sufficient evidence. The existing control service
and worker broker must enforce `autonomy-state-v1.json` whenever their installed
config is armed.

### Control service

On startup, and immediately before each autonomous tick or explicit COO cycle,
the control service verifies:

- receipt metadata and closed schema;
- `state=ARMED`;
- exact installed SHA;
- its own config digest and the expected worker config digest;
- the frozen G4 capability/profile/helper/security digests; and
- an exact provider-readiness receipt digest and at least the existing
  thirty-minute admission margin remaining before `readiness_expires_at`.

A failed guard admits no new claim or provider effect. The service records one
bounded refusal event on the affected existing root when possible, moves to
`QUARANTINED`, and surfaces exception attention. It does not cancel or kill an
already-running Attempt solely because wall time crossed the deadline; that
Attempt may reconcile/finish, but no new Attempt or provider session may start.
The same no-new-work rule begins when the remaining readiness window falls
below the thirty-minute admission margin, before absolute expiry.

### Worker broker

When `operator_harness_armed=true`, startup and every worker start request
verify the same arm receipt, exact worker-config digest and readiness deadline.
A missing, stale, near-expiry or mismatched receipt refuses before spawning
Codex.

### Credential/readiness invalidation

`provision-worker-auth.sh` already invalidates the readiness receipt before an
explicit credential replacement. This wave makes it refuse logout,
reauthorization or credential replacement while the autonomy receipt/configs
are armed. The operator must first run the shrink-only `disarm` transaction,
which stops both services and writes both config bits false. Only then may the
credential helper invalidate readiness and replace the credential. Credential
enrollment never edits service configs or re-arms production.

## 8. CEO intent and execution flow

This wave uses the existing local private-socket ingress:

1. `scripts/ceo_intent.py` submits one typed strict-v2 envelope;
2. the control service creates or reconciles one durable root Job;
3. submission stops at `QUEUED` and reports `dispatched=false`;
4. the armed bounded COO tick selects at most one eligible root and performs
   one deterministic action;
5. the existing model router and exact capability profile bind planner, work,
   review and repair Jobs;
6. the existing supervisor owns claim, validation, cleanup and terminal result;
7. the read-only planner may use only the exact Docs MCP server and one
   inherited read-only native helper inside its existing Attempt/session epoch;
8. independent review remains a separate Executive Job/Attempt on an excluded
   worker identity; and
9. completion or exception state is projected through existing Inbox/Wake
   contracts without granting them lifecycle authority.

The arm tool never submits an intent. Activation and business work remain
separate modifying operations and therefore separate carriers/receipts.

## 9. Failure behavior

| Failure | Required result |
|---|---|
| Missing/failed acceptance or Gate B | Refuse before mutation. |
| Missing/stale readiness | Refuse before mutation; never spend a canary. |
| Credential kind/binding/expiry mismatch | Refuse before mutation. |
| Live or ambiguous Attempt | Refuse; do not cancel, requeue or fail over. |
| Services cannot stop cleanly | `EFFECT_UNKNOWN`; no config write. |
| Crash before first config rename | Marker retained; `disarm` recovers. |
| Crash between config renames | Services remain stopped; marker retained; `disarm` restores both false. |
| Service start/READY timeout after commit | Stop, rollback both configs, verify `DISARMED`; otherwise retain marker. |
| Readiness expires while idle | Quarantine; no new tick/claim/session. |
| Readiness expires during an Attempt | Allow reconciliation/finish only; admit no new work. |
| Credential replacement requested while armed | Refuse before logout; require `disarm`, then invalidate readiness and replace. |
| Manual single-config edit | Startup/per-dispatch digest mismatch; refuse and surface `CONFIG_DRIFT`. |
| Repeated `arm` with identical passing state | Return the existing receipt; no restart or rewrite. |
| Repeated `arm` with changed evidence | Refuse until explicit `disarm` and fresh gates. |

## 10. Testing and falsification

### Pure/unit tests

- closed receipt/schema validation and canonical digests;
- safe metadata/ancestor checks;
- exact acceptance and Gate B classifiers;
- readiness reuse outcome mapping;
- runtime quiescence classification;
- candidate config derivation and preservation;
- expiry boundary, including the thirty-minute minimum;
- arm/disarm idempotency;
- mixed-config and stale-receipt refusal; and
- no secret-bearing key/value can enter receipt output.

### Transaction tests

Inject failure after every durable phase:

- lock creation;
- prior-config archive;
- candidate preparation;
- worker rename;
- control rename;
- receipt rename;
- worker start;
- control start; and
- READY proof.

For each failure, prove either exact rollback to both false or a retained marker
that blocks `arm` and can only be converged by `disarm`.

### Runtime enforcement tests

- armed service refuses without matching arm receipt;
- unarmed fixture behavior remains unchanged;
- expired/missing/mismatched receipt blocks tick, explicit cycle and worker
  spawn before provider construction;
- crossing expiry during an active Attempt permits only reconciliation/finish;
- credential replacement is refused while armed and succeeds only after a
  verified disarm; and
- App Server/MCP/helper G4 lineage and all write-profile helper prohibitions
  remain byte-identical.

### Static/mutation fences

- no new SQLite schema/table or lifecycle registry;
- no login command reachable from control service, worker broker, model prompt,
  MCP or plugin;
- no new TCP listener or daemon/plist;
- no Executive MCP production mode;
- no plugin grant;
- no dynamic caller path to system/config/runtime roots; and
- mutation battery kills skipped acceptance, readiness, expiry, config-digest,
  rollback, quiescence and receipt guards.

## 11. Live acceptance

Live proof proceeds in this order and stops at the first failed gate:

1. install exact protected master with both arms false;
2. enroll the dedicated worker credential through the native boundary;
3. mint/reuse one passing composite provider-readiness receipt;
4. pass distinct-UID Gate B;
5. pass formal Phase 1C-A host acceptance;
6. run `status` and prove `UNARMED`;
7. run `arm` once and prove `ARMED_READY` with both exact configs and services;
8. submit one harmless, independently useful strict-v2 Chairman intent;
9. observe the same root advance without manual prompt carriage through plan,
   work, independent review, any bounded repair/null result and aggregation;
10. for the planner, explicitly request one documentation lookup and prove the
    exact parent/helper/Docs-MCP lineage without recording prompt or output
    content;
11. prove no extra child, MCP, plugin, skill, account, session or process;
12. prove completion/exception projection; and
13. run `disarm`, prove both services stopped and both configs false, then run a
    second `status` proving `UNARMED`.

Only after the disarm rehearsal passes may production be re-armed. The
Chairman's approval of this rollout authorizes that one final re-arm without a
second prompt only when every input receipt/digest remains unchanged and no new
authority or capability is introduced; otherwise the rollout stops for fresh
authorization. Green tests, merge, install, acceptance and `ARMED_READY` are
distinct receipts. “Chairman out of the loop” is not claimed until step 9
completes through the real installed path.

## 12. Rollout and rollback

Implementation is one independently useful vertical wave:

1. pure arm policy/receipt and transaction primitives;
2. root CLI with status/arm/disarm;
3. control and worker runtime enforcement;
4. credential-readiness replacement/disarm interlock;
5. deterministic/mutation test battery;
6. exact-host runbook; and
7. live acceptance plus durable Agent OS handoff.

Rollback is `disarm`. It is shrink-only, stops services first, restores both arm
bits to false, retains existing Runtime/Job evidence, and neither removes nor
reads worker credentials. A code rollback may occur only after disarm; an older
release must never be started against configs that still claim this arm receipt.

## 13. Exact next waves after acceptance

This capability prepares, but does not silently absorb:

1. Executive MCP production intent admission with caller-identity binding;
2. one authenticated worker MCP server using its own supported OAuth flow and
   exact tool/schema/identity attestation;
3. exact installed-plugin bundle and tool attestation before any plugin grant;
4. exception-only Wake/Control Room projection; and
5. additional worker realms with separate credentials, readiness receipts and
   quota identities.

Each remains a separate reviewed vertical capability. None may become a second
worker/session control plane.

## 14. Primary references

- OpenAI Codex authentication and device login:
  <https://learn.chatgpt.com/docs/auth>
- OpenAI Codex service accounts and finite access tokens:
  <https://learn.chatgpt.com/docs/enterprise/service-accounts>
- OpenAI Codex App Server thread/session contract:
  <https://learn.chatgpt.com/docs/app-server>
- OpenAI Codex MCP configuration and OAuth:
  <https://learn.chatgpt.com/docs/extend/mcp?surface=cli>
- OpenAI Codex subagent inheritance and configuration:
  <https://learn.chatgpt.com/docs/agent-configuration/subagents>
- Existing Mastermind capability freeze:
  `research/MASTERMIND_AUTONOMOUS_EXECUTIVE_AGENT_CLI_CAPABILITY_FREEZE_2026-08-24.md`
- Existing host runbook: `ops/executive_os/HOST_PREREQUISITES.md`
