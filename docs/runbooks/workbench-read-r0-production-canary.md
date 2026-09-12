# Workbench Read R0: source composition and separately admitted canary

**State: BUILT_NOT_PROVEN / NOT_INSTALLED.** This source provides the inert
composer, an explicit owner-injected launch boundary, and the source-level
`WorkbenchReadRuntime` owner for one admitted immutable project lease. It does
not install or start a listener, create a project grant, acquire credentials,
open a tunnel, enroll an account, or qualify a real Business-seat canary.

Original composition operation:
`web-ceo-workbench-read-r0-production-20260907-sol-001` at
`C0BSBM78V1N/1788790305.705269`. Shared runtime-services source operation:
`workbench-read-rs0-runtime-services-20260908-sol-001` at
`C0BSBM78V1N/1788896791.117979`.
The source START is separate from runtime/canary admission. Sol retains acceptance
and release authority. No READ1, file writing, shell, provider, desktop/browser
actuation, Executive admission or installed Executive modification follows here.

## Existing services and ownership

`create_deployment(RuntimeServices(...))` composes the existing
`JwtAuthenticator` / `MastermindTokenVerifier`, authenticated SDK server,
descriptor read port and observer. Construction opens no file/root, listener,
credential, executor, queue or tunnel. It does not call the injected resolver,
clock, audit sink or executor to test their production health.

The existing runtime owner supplies all of these, with qualified implementation
and current admission evidence:

| Supplied value | Contract and owner boundary |
|---|---|
| `authenticator`, `policy` | Existing Business auth, validated equal policies and dedicated `workbench.read` resource; Executive audience is never a file grant. |
| `now`, `clock_ms` | Current owner clocks in seconds and milliseconds; configure consistent time and test expiry. |
| `audit_sink` | Existing bounded auth audit destination; no raw token, subject, root, source content or exception payload. |
| `resolve_binding` | Existing owner authorizes subject digest/client/resource/project; returns current `ProjectReadBinding` with retained root descriptor, generation, baseline, allowlist and expiry. No local project/grant registry. |
| `run_io` | Existing node's bounded admission/deadline executor. No inline/default-pool fallback. Callable shape is not proof of its capacity or deadline behavior. |
| `allowed_hosts`, `allowed_origins` | Explicit exact transport allowlists, no wildcard. Include the actual admitted transport's host values; do not disable rebinding protection to make a tunnel work. |

The app borrows these services. Its shutdown must not close owner roots, stop a
shared pool, remove a shared runtime registration or revoke sibling bindings.
The deployment owner supplies service lifecycle and independently reconciles
resource ownership. Constructed fixtures are never real binding evidence.

### Source-level owning runtime

`WorkbenchReadRuntime.open(...)` is the finite source composition for exactly one
immutable stable lease. Before resource acquisition it requires the exact
`workbench.read` policy, one allowed subject, a 64-lowercase-hex subject and
client reference, exact `/mcp` resource, one canonical issuer, and the protected
resource-metadata URL derived by MCP 1.28.1's
`build_resource_metadata_url`. Project, context, owner, and generation references
use their fixed pseudonymous prefixes plus 64 lowercase hexadecimal characters.
It retains no bearer token, first request's `ReadCaller`, token expiry, refresh
family, provider session, account label, or mutable current principal.

After those checks, Runtime independently opens `.` relative to the supplied
project-directory descriptor, opens and locks descriptor-relative
`auth-audit.jsonl`, and creates one `BoundedSyncExecutor`. The host descriptors
remain borrowed; Runtime owns only the descriptions it acquired. The executor
uses the active event loop's existing default executor and adds no thread pool,
retry queue, durable queue, or second lifecycle plane. Executive retry policy
remains in `ExecutiveMcpGateway`; both consumers delegate one physical attempt
to the shared owner.

Each resolver call compares the current already-verified caller to the stable
selector and returns a new request-local `ProjectReadBinding`. Token seconds and
lease milliseconds remain separate. `revoke()` is irreversible. `aclose()` first
closes admission and drains started physical work; only a successful drain may
release audit and root descriptors. `RuntimeCloseIncomplete` retains those same
resources for a later same-owner drain. An uncertain audit or descriptor close is
reported explicitly and is never converted to clean shutdown.

The audit sink uses only the existing `AuthAuditEvent` vocabulary. It holds one
nonblocking exclusive lock, validates directory and named-file identity/security
before and after one append plus `fsync`, and poisons permanently on replacement,
link/mode/flag/size drift, short write, durability failure, or invalid event. It
never rotates, retries an uncertain write, changes basenames, or records token,
content, path, username, or provider-session data.

## Launcher boundary

For inert description, including without optional SDK installation:

```sh
python3 -S scripts/mastermind_workbench_read_server.py --describe
```

Standalone serving returns `RUNTIME_SERVICES_REQUIRED` before importing the SDK
or attempting bind. No `--root`, dynamic import factory, credential, tunnel or
automatic service-discovery flag exists. The parser accepts only a loopback host
and an explicit port in 1..65535 for the serving boundary.

After separate runtime admission, the **existing trusted host bootstrap** may
call `main(argv, runtime_services=services, serve=owner_serve,
incoming_authority=owner_qualified_authority)`. The `serve`
callback receives the constructed ASGI application plus exact host and port.
Source tests use only a launch spy and in-process ASGI transport, never a listener.
The concrete production bootstrap, service binding and process owner remain
UNKNOWN until qualified. An executable Python entry point is not an installed
production system.

The trusted `incoming_authority` is the exact HTTP `Host` the admitted transport
will send, including an explicit port; it is not a CLI/model parameter or derived
from the listener bind tuple. This launcher supports one qualified authority and
requires `services.allowed_hosts == (incoming_authority,)` before `serve`. Missing,
malformed, wildcard, portless or mismatched values refuse before the callback.
For example, a loopback bind at127.0.0.1:8765 may receive either that exact Host or
an independently qualified tunnel-facing `read0.example:443`; the owner must prove
which one the transport actually sends. A transport using an implicit/default-port
Host is not qualified by this explicit-port launcher contract. No DNS-rebinding
protection is disabled, and an otherwise valid string is not runtime identity proof.

Missing services or pre-bind configuration refusal returns status2. Once the
explicit owner's `serve` callback begins, exceptions propagate: they are not
misreported as harmless pre-bind refusals, caught for retry, or converted to a
fallback listener. The host must reconcile any ambiguous launch effect on the
same carrier before another action.

## Source validation and independent review

Use an isolated external worktree and environment with the repository's declared
`business-mcp` and `dev` profiles. The protected profiles pin MCP1.28.1 and
PyJWT2.13.0; retain the actual Python and complete resolved dependency versions.
Keep environment, pip/temp caches and evidence external. No system install or
version substitution follows a setup failure.

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_bounded_sync_executor.py \
  tests/test_business_mcp_auth_audit.py \
  tests/workbench_read_mcp/test_runtime.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_executive_mcp.py tests/test_executive_mcp_e1_composition.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/workbench_read_mcp
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_business_mcp_auth_*.py
```

`test_runtime.py` owns the source-level Runtime lifecycle. It proves validation
before resource acquisition, independently owned root identity, current-caller
renewal, adverse stable selectors, irreversible revoke, incomplete close with
resources retained, and revocation both during a real descriptor read and after
completed observation but before awaited release. Its signed in-process SDK flow
performs initialize/list/call over a real temporary file, verifies the exact
22-key result and content/hash/range, distinguishes expired token A from renewed
token B, then reads the fixed-basename durable audit. This remains source test
evidence; it is not installed process, filesystem-placement, provider, tunnel,
account, or browser proof.

The production-composition module uses ephemeral signed JWTs and real
in-process ASGI initialize/list/call, the existing binding/port and real descriptor
observer. Its disposable bounded executor, signing key and fixture project map
belong only to tests. The complete production output schema must remain in parity
with the observer and port: source/content/hash identities, context/owner/generation,
working-tree view, explicit committed baseline or null, returned ranges and cursor,
`NOT_OBSERVED` index state and `atomic_workspace_snapshot=false`. All three digest
strings require exactly64 lowercase hex characters; a non-null committed baseline
requires exactly40. Real-read terminal-LF regressions omit expected_sha256 so the
output schema is independently tested; valid64, valid40 and null controls remain.
Real-lifespan launch tests prove initialize200 at the exact incoming Host, including
a Host distinct from the bind tuple, and no serve call for invalid owner policy.

Retain RED/GREEN command, cwd, timestamps, output, exit, exact source hashes and
dependency identities. The mutation test runs identical baseline/adverse requests
and identical assertions against process-local controls for fake observer,
synchronous execution, cross-project binding, removed post-await binding check,
bypassed post-read auth check, model-supplied authority and forged observer hash.
Five additional pairs remove each digest/baseline length guard and the incoming
request-authority guard, preserving the same successful baseline and refusal
assertion. These24 nested baseline/mutant executions are not added to top-level
suite counts.
Each control must produce an intended assertion failure with no setup/runtime
error. Successful-response and completed-I/O preconditions are outside expected
failure handling. The forged-hash control deliberately corrupts both observer
hash enforcement and its reported hash; it is not a claim that removing one of
the several hash checks alone bypasses the application.

No source file is modified by a mutation test. Future tests must not substitute a
fake port for positive read proof, accept unrelated refusals as kills, use different
baseline/mutant security assertions, or claim cancellation stopped kernel I/O.
The fixture capacity/deadline test proves waiter timeout while shielded work drains;
it does not qualify production executor deadlines or suppression of its late results.

Before long CI/review, retain CHECKPOINT_VERIFIED for the actual source branch,
Draft/HOLD PR, exact remote head/tree/base/owned blobs, local cleanliness and
known effects. Root commissions independent semantic review; the builder never
self-approves. Use the ordinary current integration/security campaign, preserve
review reuse qualifications, and do not join a branch merely for ancestry.
WBR529's independently accepted full composition is separately required before
canary; this source does not edit or supersede its test file.

## Canary admission: no values may be guessed

Before a real account, listener, app, tunnel, credential, binding or host action,
Sol must separately admit the finite canary and its exact effect ceiling. Record:

1. Immutable reviewed source/release and dependency/tool/output-schema hashes.
2. One approved Business seat, workspace/account association and separately
   versioned Workbench app generation; actual principal evidence.
3. One exact tunnel profile, endpoint and credential custodian, plus the approved
   issuer/resource/client/subject digest and public metadata policy. Secrets stay
   in existing approved custody, outside source and public receipts.
4. Selected-project binding issuer, generation, descriptor identity, baseline,
   relative-path allowlist and expiry; approved harmless real file and independently
   known hash. A supplied project_ref alone grants nothing.
5. Actual process/bootstrap/executor/audit owners, concurrency/admission limit,
   deadline, output and upstream frame/aggregate limits, supported local filesystem,
   test budget and real draining/cleanup procedure.
6. Exact rollback actor, artifact preimages, canary-only binding/app/tunnel
   identities and a readback plan proving installed Executive remains unchanged.

Preserve the507 shared relay pause and unrelated custody. The separate installed
Personal Executive source/schema issue is neither a prerequisite nor a mutation
target. Missing original parent context requires only the precise needed authority
excerpt; public transport prose must not replace an unavailable source grant.

## Finite proof matrix

| Case | Required observation |
|---|---|
| Positive | Actual approved seat initialize/list/call reads the selected real file; exact content, full-file hash, file identity, context/owner/generation, baseline, range/cursor and schema agree. |
| Identity/authority | Wrong subject/client/resource/scope/project and model root/identity fields refuse; unauthorized observer admission remains zero. |
| Paths/files | Undeclared/absolute/traversal, symlink/nonregular/hardlink, stale hash, root/file/ancestry drift, oversized or unrepresentable content refuse safely. |
| Await fences | Expiry, revocation and generation/policy change before admission, while queued and after actual read completion withhold content. Keep binding and app-auth discriminators independent. |
| Isolation/schema | Concurrent callers keep disjoint roots/results; malformed identity/range/cursor, extra fields, overflow and false index/snapshot claims are withheld. |
| Resource behavior | Existing executor enforces its real bounded admission and deadline. A timed-out/cancelled read may remain draining; no late result is delivered and capacity is released only at actual completion. |
| Disconnect | Exact canary tunnel/app disconnect produces unavailable/refused behavior; no empty success, stale cached content or alternate endpoint. |
| Audit/cleanup | Closed audit with no secret/root/content leakage; canary-owned descriptors/tasks/listener cleaned while borrowed shared services remain intact. |

Source tests qualify synthetic ASGI and filesystem behavior only. The real
disconnect, installed executor/transport limits, account enrollment and canary
rollback rows remain NOT_RUN until their separate admission. A healthy tunnel,
green CI, fixture token or merged source alone remains BUILT_NOT_PROVEN.

## Rollback and stop

Stop new canary admission and revoke only its selected binding. Reconcile and
drain actual in-flight reads under the existing executor owner; cancellation is
not kernel interruption. Disconnect exactly the admitted canary app/tunnel and
remove or restore only its generation-owned artifacts against frozen preimages.
Do not delete shared stores or terminate a shared process/executor.

Read back revoked/unavailable canary access, stopped canary resources and unchanged
installed Executive configuration/app/tunnel identities. On an ambiguous effect,
preserve the same operation/carrier and reconcile: no blind retry, replacement
profile, second backend or alternate account. Return finite proof and rollback to
Sol and await an explicit ruling/STOP. No successor is authorized by completion.
