# Workbench Read R0: runnable loopback source and separately admitted canary

**State: BUILT_NOT_PROVEN / NOT_INSTALLED.** This source provides the inert
composer, source-level `WorkbenchReadRuntime` owner and a concrete configured
loopback process boundary for one admitted immutable project lease. It does not
install or start a service, create a project grant, acquire credentials, open a
tunnel, enroll an account, or qualify a real Business-seat canary.

Original composition operation:
`web-ceo-workbench-read-r0-production-20260907-sol-001` at
`C0BSBM78V1N/1788790305.705269`. Shared runtime-services source operation:
`workbench-read-rs0-runtime-services-20260908-sol-001` at
`C0BSBM78V1N/1788896791.117979`. Concrete service-process P0 operation:
`web-ceo-workbench-read-service-process-p0-20260907-sol-001` at
`C0BSBM78V1N/1789277137.919909`.
Source START is separate from installation/canary admission. Sol retains
acceptance and release authority. No READ1, file writing, shell, provider,
desktop/browser actuation, Executive admission or installed Executive
modification follows from source construction.

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

The authenticated app borrows these services. A generic composer must not close
owner roots, stop a shared pool, remove a shared runtime registration or revoke
sibling bindings. The concrete P0 process instead owns exactly one
`WorkbenchReadRuntime`, which in turn owns exactly one FastMCP server, one project
root description, one durable audit sink and one bounded executor generation.
Constructed fixtures are never real binding evidence.

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

## Concrete P0 service and launcher boundary

For inert description, including without optional SDK installation:

```sh
python3 -S scripts/mastermind_workbench_read_server.py --describe
```

The descriptor is intentionally non-live and reports the source capability as
`BUILT_NOT_PROVEN`, mode `configured-loopback-service`, tool
`read_project_file`, config schema `mastermind.workbench_read_service.v1`, and
`installed=false`.

The only serving entrance is:

```sh
python3 scripts/mastermind_workbench_read_server.py --config /absolute/path/workbench-read.json
```

There is no serving `--host`, `--port`, `--root`, dynamic factory, credential,
tunnel, environment fallback or automatic service-discovery flag. Missing
`--config` returns `SERVICE_CONFIGURATION_REQUIRED` / exit 2 before the optional
serving stack is imported.

The service document is exact and closed. Top-level keys are only:

```text
schema
policy_file
project_root
audit_directory
bind_host
bind_port
incoming_authority
max_concurrency
io_timeout_seconds
close_timeout_seconds
lease
```

`schema` is exactly `mastermind.workbench_read_service.v1`; `bind_host` is
literal `127.0.0.1`; `bind_port` is an explicit integer 1..65535;
`incoming_authority` has an explicit port and is independently validated against
the existing deployment authority contract. `max_concurrency` is 1..32 and both
timeouts are finite positive values at most 60 seconds. Unknown/missing fields,
bool-as-int, wildcard/nonloopback host, implicit port and nonfinite/overbound
limits refuse closed.

The nested `lease` is also exact and contains only the existing
`StableWorkbenchLease` projection:

```text
expected_subject_digest
expected_client_ref
resource
required_scopes
project_ref
context_ref
owner_ref
generation
allowed_paths
committed_head
lease_expires_at_ms
```

The service document never carries bearer/refresh tokens, OAuth secrets, signing
keys, account labels, tunnel credentials, provider sessions, a mutable project
registry, retry state, JWKS payload/cache state or an audit filename. The
`policy_file` remains the canonical closed Business resource policy; issuer/JWKS
and token rules are not duplicated into the service document.

Config and policy files are bounded, nofollow descriptor reads with stable
lstat/open/fstat metadata and duplicate-key/nonfinite JSON refusal. Project root
and audit directory are absolute, real, same-effective-UID directories opened
with `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`; group/world-writable roots refuse.
These bootstrap descriptors are closed after exactly one Runtime has acquired
its independent owned descriptions. Any uncertain bootstrap cleanup prevents
socket admission and is not converted to clean startup.

P0 reserves exactly one `AF_INET` loopback socket before serving, marks it
non-inheritable, does not enable `SO_REUSEPORT`, and passes only that socket to
one `uvicorn.Server.serve(sockets=[...])`. There is no alternate port, worker
fan-out, reload, proxy inference or bind retry. The Runtime's FastMCP
`streamable_http_app()` is materialized once; a tiny top-level Starlette app adds
`/healthz` and `/readyz` before delegating all other paths to the SDK app. The
top-level lifespan enters the Runtime-owned FastMCP session manager exactly once.
It never calls `create_deployment()` a second time.

`/healthz` is process/event-loop liveness only. `/readyz` is a non-authorizing
service-local projection: config/runtime/lifespan/socket must be admitted and not
stopping, then one ephemeral `ReadCaller` built only from the already-validated
stable lease calls public `runtime.resolve_binding(...)`. The synthetic seconds
value is rounded down from lease milliseconds, never passed through JWT auth,
never leaves the process and grants no request. Binding mismatch, expiry, root
drift, revoke or shutdown produces 503. Latent audit poison is not falsely
claimed observable through readiness; a real auth/read discovers it fail-closed.

Shutdown truth is fixed:

```text
mark stopping / ready=false
-> Uvicorn stops network admission and drains HTTP work under its bounded timeout
-> lifespan irreversibly runtime.revoke()
-> runtime.aclose(close_timeout_seconds)
-> exit one MCP session-manager lifespan
-> close/read back the service socket
```

A clean shutdown is exit 0. `RuntimeCloseIncomplete` is exit 3.
`RuntimeCloseUncertain` is exit 4. Pre-bind/config refusal is exit 2. Unexpected
post-bind/server or startup-cleanup failure uses bounded nonzero exit 5. No close
uncertainty, Uvicorn-contained lifespan exception, socket-close failure or
cancelled physical read may be rewritten as clean success, retried or rebound.
The Uvicorn HTTP graceful bound and Runtime physical-I/O close-classification
bound are sequential owner bounds. They do **not** bound process lifetime.
After `RuntimeCloseIncomplete`, CPython 3.12's `asyncio.run()` still drains its
default executor and interpreter shutdown joins surviving threads. Exit 3 is
therefore delivered only if physical work eventually finishes; a stuck read can
prevent that exit indefinitely. No automatic kill, retry, replacement process,
or claim that cancellation interrupted physical I/O follows from this source.

Runtime-close-attempted and whole-lifespan-completed are separate service facts.
SDK entry failure still closes the acquired Runtime; SDK exit failure and
Uvicorn's force-exit/failed-lifespan flags cannot produce clean exit 0. Fallback
close runs once, and socket closure requires descriptor readback. Runtime or
socket acquisition with uncertain cleanup produces
`SERVICE_STARTUP_CLEANUP_UNCERTAIN` / exit 5, never an ordinary pre-effect refusal.

**P1 operational gate: NOT_ESTABLISHED.** Before installed/production acceptance,
qualify the admitted supervisor's bounded stop/escalation behavior, actual process
completion, no-orphan result, audit/root cleanup, and rollback owner. A missing
process reply or close deadline is not a stopped process. Preserve and reconcile
the same owner/process until its effect is known. This P0 limitation does not
amend any higher-authority bounded-process acceptance requirement.

## Dedicated source environment

P0 owns a dedicated macOS-arm64 / CPython 3.12 dependency input and generated
hash lock; it must not copy/install the broad repository gate lock. Direct roots
are exactly:

```text
mcp==1.28.1
PyJWT[crypto]==2.13.0
httpx==0.28.1
jsonschema==4.26.0
pydantic==2.13.5
starlette==1.6.0
uvicorn[standard]==0.52.4
```

Generate `requirements/workbench-read-macos-arm64-py312.lock` with pip-tools
7.6.1 on an organization-authorized Darwin arm64 CPython 3.12 environment using
`--generate-hashes`. The lock owns every transitive package/hash. Resolver
movement from the frozen direct identities or missing binary support is a HOLD,
not permission to substitute versions. Acceptance installs the generated lock
into a fresh validation environment with `pip --require-hashes
--only-binary=:all:`; no system/editable install.

## Source validation and independent review

Use an isolated external worktree and environment. Keep environment, pip/temp
caches and evidence external. No system install or version substitution follows a
setup failure.

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/workbench_read_mcp/test_service.py \
  tests/workbench_read_mcp/test_service_process.py \
  tests/workbench_read_mcp/test_deployment.py \
  tests/workbench_read_mcp/test_production_composition.py
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

The production-composition module uses ephemeral signed JWTs and real in-process
ASGI initialize/list/call, the existing binding/port and real descriptor observer.
Its disposable bounded executor, signing key and fixture project map belong only
to tests. The complete production output schema must remain in parity with the
observer and port: source/content/hash identities, context/owner/generation,
working-tree view, explicit committed baseline or null, returned ranges and
cursor, `NOT_OBSERVED` index state and `atomic_workspace_snapshot=false`. All
three digest strings require exactly 64 lowercase hex characters; a non-null
committed baseline requires exactly 40. Real-read terminal-LF regressions omit
`expected_sha256` so the output schema is independently tested; valid64, valid40
and null controls remain. Concrete-service launch tests must prove exact incoming
Host enforcement before network admission and the real subprocess matrix must
use the reserved listener, not a launch spy.

Retain RED/GREEN command, cwd, timestamps, output, exit, exact source hashes and
dependency identities. Mutation tests keep identical baseline/adverse requests
and assertions while killing fake observer, synchronous execution, cross-project
binding, removed post-await binding check, bypassed post-read auth, model-supplied
authority, forged observer hash, digest/baseline length guards, incoming-authority
validation, config closure, loopback-only bind and truthful drain/exit behavior.
A kill requires the intended assertion failure with no setup/runtime error.

No source file is modified by a mutation test. Future tests must not substitute a
fake port for positive listener proof, accept unrelated refusals as kills, use
different baseline/mutant security assertions, or claim cancellation stopped
kernel I/O. Source tests are not Darwin acceptance or production proof.

Before long CI/review, retain CHECKPOINT_VERIFIED for the actual source branch,
Draft/HOLD PR, exact remote head/tree/base/owned blobs, local cleanliness and
known effects. Root commissions independent semantic review; the builder never
self-approves. Use ordinary current integration/security proof and do not create
an ancestry-only commit merely because protected master moves disjointly.

P0 source acceptance additionally requires one organization-authorized Darwin
arm64/CPython3.12 real subprocess proof from the generated dedicated lock:
pre-reserve the real loopback socket, start one configured service, perform signed
MCP initialize/list/call against one harmless temporary selected-project file,
verify exact output/audit behavior, then exercise clean and bounded adverse
shutdown. The adverse physical-read fixture retains an actual admitted
descriptor operation until the real close attempt returns/raises, then releases
its own finite hold. It proves incomplete classification and eventual exit 3,
not a process deadline for stuck I/O. Real audit-file mode drift proves exit 4;
clean shutdown proves exit 0; each completed child leaves its listener closed.
The actual launcher is exercised, and an additional `python -I` subprocess from
outside the checkout proves direct-script imports do not depend on `PYTHONPATH`.
This is source qualification only; the exact Mac Studio remains the separate
P1 deployment target.

## Darwin dependency and repair qualification — September 13, 2026

The dedicated lock was generated once by pip-tools 7.6.1 / pip 26.1.2 on the
organization-authorized Admin-Mini, Darwin arm64 / CPython 3.12.13, after the
previous ENOSPC attempt was reconciled. The new attempt finished exit 0 at
16:44:19Z: 34 pinned packages, 825 SHA-256 hashes, and all seven frozen direct
versions unchanged. Input SHA-256:
`4939a866ca8afb5b70b56b134195df3975b0787cf005afc20e0dde0152a50315`.
Lock: 72,656 bytes, SHA-256
`16fe1dc1c7c7eb2af39d28c040e0b76149fe185520a214cf2e00a70ff7b9e496`.
The generated header's `--no-index` rendering is a pip-tools comment artifact;
the recorded resolver invocation used the explicit PyPI index and emitted no
index/trusted-host directives. The immutable carrier retains the actual argv.

The exact transferred bytes then passed a fresh `--require-hashes
--only-binary=:all:` install and `pip check` on Mac-Studio at 16:48:58Z,
Darwin arm64 / CPython 3.12.13, boot
`ED37CEED-BE01-42EA-8F94-04A4C6C2C85F`. Worktree, environment and receipts were
placed through the required external-SSD policy (volume UUID
`7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A`). The runtime environment stayed separate
from the five-package pytest tooling overlay extracted with hashes from the
repository gate lock; no broad repository or system package install occurred.

Independent semantic review identified acquisition-cleanup uncertainty,
SDK entry/exit and force-exit reconciliation, and the direct-script import
boundary. Six discriminating regressions failed for those specific defects
before repair. After repair, the complete service/process group passed 31 tests
at 17:19:29Z, including real listener/JWT/MCP/read/audit/exit 0/3/4 checks.
The complete repaired-source validation then passed in separate prescribed groups
at 17:22:26Z: Executive 136 tests; Workbench 242 tests plus 86 subtests; shared
authentication/executor 414 tests. All three commands exited 0. Earlier failed
qualification logs remain retained: the long Unix-socket path setup, one
non-reproduced readiness deadline, and a monolithic Executive 30 ms scheduling
assumption. No production timeout was widened to make those checks pass.

The final review also required a nonblocking bootstrap open before descriptor
validation. Three regular-file/primitive-contract regressions failed before the
repair; the complete Workbench suite then passed 245 tests plus 86 subtests,
exit 0 at 17:35:51Z. Config and policy reads now require `O_NONBLOCK` together
with `O_NOFOLLOW` and retain all descriptor and pathname identity checks. The
Executive and shared authentication/executor owners remain byte-identical to
the earlier green receipts. Protected base movement to
`d6eccb0d81c9db3d009eafa7b37ea97a4dc99bc8` adds only four disjoint evaluation
harness paths; the governing procedure and Workbench dependency owners did not
change. Hosted latest-base integration remains a separate release gate.

The tested implementation hashes are:

| Path | SHA-256 |
|---|---|
| `integrations/workbench_read_mcp/service.py` | `0476c15551fc6855364b62e7b291eb3bd633f6304ae9c7e0a5e75ed2b461ff4a` |
| `scripts/mastermind_workbench_read_server.py` | `7264fb1e78476ee28196305c10e575606cf7eac4082b2d76d0711a66b0500d25` |
| `tests/workbench_read_mcp/test_service.py` | `57bbf76fa844f98db78740cafb6727a50a8db83a3158abba3d25a2c23e66a4b8` |
| `tests/workbench_read_mcp/test_service_process.py` | `b08e2ad2c905bdb318f6677defc4e356d28e85b64cd7c20d1538281068bd5895` |

Qualification uses the dedicated interpreter, disables plugin autoload/cache and
portfolio-only root conftest, and supplies the isolated test-tool overlay.
Temporary Unix-socket fixtures use a short real directory on the same approved
SSD to respect Darwin's pathname limit; no internal worktree fallback is used.
These receipts establish source qualification only. Installation, actual approved
seat/principal/app binding, bounded supervised process stop and production canary
remain separate gates below.

## Canary admission: no values may be guessed

Before a real account, installed listener, app, tunnel, credential, binding or
host action, Sol must separately admit the finite canary and its exact effect
ceiling. Record:

1. Immutable reviewed source/release and dependency/tool/output-schema hashes.
2. One approved Business seat, workspace/account association and separately
   versioned Workbench app generation; actual principal evidence.
3. One exact tunnel profile, endpoint and credential custodian, plus the approved
   issuer/resource/client/subject digest and public metadata policy. Secrets stay
   in existing approved custody, outside source and public receipts.
4. Selected-project binding issuer, generation, descriptor identity, baseline,
   relative-path allowlist and expiry; approved harmless real file and independently
   known hash. A supplied `project_ref` alone grants nothing.
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

Source tests and P0 Darwin subprocess qualification remain source evidence only.
The real disconnect, installed executor/transport limits, account enrollment and
canary rollback rows remain NOT_RUN until their separate admission. A healthy
loopback service, green CI, generated lock, fixture token or merged source alone
remains BUILT_NOT_PROVEN / NOT_INSTALLED.

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
