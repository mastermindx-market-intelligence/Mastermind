# Agent OS memory provider for Hermes

**Status:** bounded source implementation. Not installed, not enrolled, not
company-accepted.

This adapter makes the *existing* Agent OS context compiler reachable through
the Hermes memory-provider seam. A freshly bound Hermes provider returns the
current organizational context for exactly the workstream its host already
authorized, preserves the owner's provenance and accounting, and shows a
canonical correction to the next fresh instance.

It is an adapter, not a second owner. It adds no compiler, ranker, fact
extractor, memory database, index or summary of its own, and it writes nothing.

## Boundaries

| Concern | Owner |
|---|---|
| Organizational facts, decisions, handoffs, workstream context | Agent OS (existing compiler and validator) |
| Bounded read of one exact workstream | `ops/fabric_launch.agentos.read_context` / `validate_bundle` |
| Company grounding surfaces | Steward — read-only, unchanged |
| Conversation, session identity, profile | Hermes native host |
| Grant, session scope, currentness | The trusted native host (injected ports) |

The provider serves company/workstream context only. It is not private
personal notes and does not implement a personal memory surface.

Read-only means read-only:

- no durable write, no checkpoint, no dispatch, no schedule;
- `get_tool_schemas()` returns `[]` — no model-visible write or file read;
- `sync_turn()` and `on_memory_write()` are deliberate no-ops, so this adapter
  never becomes a second publisher of an organizational fact;
- `pre_compress_checkpoint_api_version` stays at the inherited best-effort
  value `1`. This adapter has no durable checkpoint, so it must never claim
  the fail-closed v2 contract.

## Pinned references

| Reference | Value |
|---|---|
| Mastermind repository | `mastermindx-market-intelligence/Mastermind` |
| Procedure and base SHA | `ad6275a9c4d237bce75e52d0d6a8f41264b4ded5` |
| Assigned branch | `sol/hermes-agentos-memory-20261107-c3` |
| Masterplan commit | `6098b9f2a3c883ee71e85da8a8776900f205d2e6` |
| Upstream Hermes | `NousResearch/hermes-agent` @ `1c0cd667746d3395fe9e1b6c74f8f85952486f18` |
| Upstream `agent/memory_provider.py` SHA-256 | `ac81dcf489c698891f0edebfe26845a75c50d2bde77ec3be8d7938a85c79f1fc` |

The provider source on this branch is a bounded repair of the original leaf:
the same three-file scope, fast-forwarded on the same branch and PR. The
repair qualifies the native default path, the freshness ceiling and the
readiness guard against the pinned upstream source; it adds no new capability
and changes no owner.

## Host integration API

The provider never trusts model text, a constructor string or a retrieved note
for scope. The trusted native host injects two ports.

### The two ports

```python
from integrations.hermes_harness.agentos_memory_provider import (
    AgentOsBinding, AgentOsHostPorts, create_provider, install_host_ports,
)

class NativeBindingResolver:
    """Resolves the host-authorized scope of exactly one session."""
    def resolve(self, session_id: str, **context) -> AgentOsBinding | None:
        ...

class NativeCurrentnessGuard:
    """Reports whether the host still grants this exact binding."""
    def current_generation(self, binding: AgentOsBinding) -> str | None:
        ...
```

`resolve()` returns `None` when the host has no authorized scope for that
session. `current_generation()` returns `None` when the grant was **revoked**,
the binding's own `generation` when the grant is unchanged, and any other
string when the scope **changed**.

### The binding

```python
AgentOsBinding(
    session_id="…",      # the exact Hermes session
    role="…",            # the Mastermind role this session may read for
    profile="…",         # the Hermes profile name (matches agent_identity)
    hermes_home="/…",    # the profile home (matches Hermes' hermes_home)
    workstream="WS:…",   # the one authorized workstream, canonical WS: form
    owner_root="/…",     # the Agent OS compiler root this session may read
    generation="…",      # the host's grant/session generation
)
```

`workstream` must match `WS:[A-Z][A-Z0-9-]{0,95}` — the same canonical form
the existing SessionStart orientation consumer uses.

`owner_root` is read from the binding and never defaulted. An unbound or
mismatched provider does not fall back to a global home, to `~/.hermes`, or to
another project.

### Installing the ports

Two equivalent routes:

```python
# 1. Native bootstrap installs the immutable ports once, at process start.
install_host_ports(AgentOsHostPorts(resolver=…, guard=…))

# 2. The host constructs the bound instance directly and registers it.
provider = create_provider(ports=AgentOsHostPorts(resolver=…, guard=…))
ctx.register_memory_provider(provider)
```

`install_host_ports()` accepts the same pair only once; installing a *different*
pair is refused with `AGENTOS_HOST_PORTS_ALREADY_INSTALLED`. The ports resolve
per session and hold no profile-specific state, so the same pair serves every
profile without rebinding a shared instance.

Every load constructs a **new** provider instance. There is no module-level or
class-level singleton and no shared mutable profile state.

### The Hermes plugin entry point

`register(ctx)` is the standard Hermes entry point. It registers a new instance
and requires the real upstream `MemoryProvider` base: if Hermes is not
importable, registration refuses with `AGENTOS_CONTEXT_HELPER_UNAVAILABLE`
rather than registering a faked native class.

The concrete Hermes class is produced by a late, dependency-injected factory:

```python
build_provider_class(base=None, *, upstream_module=None, allow_missing_base=False)
```

Importing this Mastermind package never imports Hermes. The factory resolves
the real upstream `agent.memory_provider` only when it is actually needed.

## Startup readiness

`prepare_context()` is the explicit host-controlled seam. It arms the single
background read and returns the bounded state; it never blocks and never reads
inline.

```python
provider.prepare_context()   # arm the read
provider.readiness()         # {"state": …, "reason": …, "context_supplied": …}
```

| `state` | Meaning |
|---|---|
| `UNBOUND` | No host binding. The provider is unavailable. |
| `PENDING` | The single background read is in flight. |
| `READY` | A current snapshot is held, inside its freshness budget, and still granted by the host. |
| `UNAVAILABLE` | No deliverable snapshot; `reason` says why. |
| `CLOSED` | The provider was shut down. |

`context_supplied` is `True` only after context was actually handed to a turn.
A pending read is never labelled as memory successfully supplied.

Recommended first-turn qualification:

```python
provider.initialize(session_id=…, hermes_home=…, agent_identity=…)
provider.prepare_context()
# poll provider.readiness() until state is READY or UNAVAILABLE
```

`readiness()` is a host-facing surface. It reports the closed reason code, the
bound workstream/role/profile, the bundle digest and whether context was
actually supplied.

### Readiness and the host guard

`readiness()` and the cached path of `prepare_context()` consult the host
currentness guard before reporting a cached snapshot as `READY`. A revoked
grant, a changed scope or an unverifiable guard reports `UNAVAILABLE` with the
closed reason instead, and `context_supplied` is `False`: nothing may claim a
deliverable context that the host no longer grants.

The guard is therefore on the host's critical path. Its implementation must be
**cheap, local and non-blocking** — it is consulted before a read, after a
read, immediately before a delivery and on every readiness report. The
provider itself performs no I/O and no compiler read to produce a status, and
`prefetch()` still never reads from the owner.

Consulting the guard never starts a read and never retries one. A revoked or
changed guard drops the cached snapshot; a later `prepare_context()` may
re-resolve the binding, but nothing here loops on its own.

## First-turn barrier

The native host owns this barrier. Before the first model request that
promises recall, the host must complete a **bounded preparation** of this
provider:

1. `initialize()` binds the instance to exactly one session.
2. `prepare_context()` arms the single background read. It never blocks.
3. The host waits, bounded, for `readiness()` to leave `PENDING` — that is,
   until the read has either produced a snapshot (`READY`) or failed with a
   closed reason (`UNAVAILABLE`).

Only then may the first request that depends on organizational recall be
issued.

**Eventual warming is not cold recall.** A provider that is still `PENDING`, or
that reports `UNAVAILABLE` with a closed reason, has *no* context to give the
first turn. The host must not issue a first-turn request that promises recall
on the expectation that the snapshot will arrive later, and must not describe a
warming provider as a warm one. A first turn without context is simply a first
turn without context.

This adds no new lifecycle owner. The barrier is the existing native host's
own startup sequence, and the provider contributes only the two seams it
already exposes (`prepare_context()` and `readiness()`). The provider never
blocks, never schedules and never starts a service.

## Native hook lifecycle

| Hook | Behavior |
|---|---|
| `is_available()` | Cheap: true only with host ports installed and the provider not closed. No network, no filesystem, no read. |
| `initialize(session_id, **kwargs)` | Resolves through the host port and binds this instance to exactly this session. A missing or mismatched session/profile raises a bounded refusal (upstream logs and swallows it) and leaves the instance unbound. |
| `prepare_context()` | Host seam: arms the one in-flight background read. A cached snapshot is re-served only while the host guard still grants it; otherwise it is dropped, not retried. |
| `prefetch(query, *, session_id="")` | Returns the current snapshot or `""`. The query is never parsed for scope. A non-empty `session_id` that does not match the bound session is refused. |
| `queue_prefetch(query, *, session_id="")` | Arms the next read after a turn. Never reads inline. |
| `sync_turn(...)` | Deliberately inert. |
| `on_memory_write(...)` | Deliberately inert. |
| `on_pre_compress(messages)` | Deliberately inert; returns `""`. |
| `on_session_switch(new_session_id, ...)` | Re-resolves through the host port. Clears pending and cached material first, so a late read cannot repopulate the old session. A different role is refused with `AGENTOS_REBIND_REFUSED`. |
| `shutdown()` | Clears every cached and pending piece of material. A late background return is discarded. |
| `readiness()` | Host-facing status. Consults the local currentness guard; a revoked, changed or unverifiable grant is never reported as `READY`. |

### Concurrency

At most one background read is in flight per provider instance. It is spawned
through the native context helper (`agent.memory_provider.spawn_context_thread`)
so the profile's `contextvars` — the active `HERMES_HOME` and the per-turn
secret scope — are preserved. There is no durable queue, no service and no
scheduler.

**The default path is the native path.** A provider built against the real
upstream module finds `spawn_context_thread` itself; no injected spawn
substitute is needed and none is expected in production. The upstream module
is *stored* under `_native_memory_module` and reached through the
`_upstream_module()` lookup, so the stored module can never shadow the lookup
and turn the default path into a raw `TypeError`. If the helper is missing or
is not callable, the read is refused with the closed reason
`AGENTOS_CONTEXT_HELPER_UNAVAILABLE` — never with an untyped exception.

Currentness is required three times:

1. before the read is acquired;
2. after the read returns;
3. immediately before a snapshot is delivered.

Any revoke or change drops the whole snapshot. A late background return cannot
repopulate an old session.

### Freshness

A snapshot carries a bounded monotonic freshness budget: a **finite, positive**
number of seconds, at most **300 s**, default **120 s**. The budget is
validated when the provider is constructed — before a binding is resolved and
before any context is acquired — so an unusable budget never reaches a read.
`bool`, a string, `NaN`, `±inf`, zero, a negative value and anything above the
ceiling are all refused with the closed reason `AGENTOS_FRESHNESS_INVALID`.
The clock is `time.monotonic` by default; a supplied clock is a test seam,
never a freshness authority.

After it expires the snapshot is dropped: there is no stale-while-revalidate
delivery. The next `prepare_context()` or `queue_prefetch()` reads the current
bundle from the owner again.

Freshness is never inferred from assistant memory. A canonical correction
lives in Agent OS; the next fresh instance — and the next read of an existing
instance after expiry — observes the new bundle and its new source version.

## What the provider validates

The owner's raw bytes are validated with the owner's own validator
(`validate_bundle`), which preserves the owner's `sections`, `degraded`,
`excluded` and `omitted_due_to_budget` verbatim. The provider then requires
the read observation to match the original read:

- `owner == "agent_os"`;
- `workstream` equals the bound workstream;
- `execution_authority is False`;
- `bundle_sha256` equals the SHA-256 of the delivered bytes;
- `source_script_sha256` is a 64-character lowercase hex digest;
- `repo_sha` is a non-empty string.

The owner's bytes are then wrapped in a small envelope that states plainly
that the content is organizational evidence and **not execution authority**.
The complete envelope defaults to 32 KiB, consistent with the existing
SessionStart consumer. The trusted host may explicitly set
`AgentOsBinding.max_context_bytes` for one bound consumer to a positive integer
up to 128 KiB. This is part of the immutable host binding, never a model argument
or an environment override. Any changed binding remains subject to the existing
generation/currentness checks. Invalid, boolean, non-integer or over-ceiling
limits refuse before an owner read.

A real Control Room compiler read on 2026-11-07 returned 108,257 bytes at the
unchanged compiler budget of 4,000. Mandatory law, acceptance declarations and
accounting can exceed that advisory token budget. The larger explicit envelope
accommodates such a bundle without selecting, reserializing or trimming it.
The total rendered bytes include the evidence wrapper; even a raw bundle below
128 KiB can therefore refuse. An oversized bundle is **refused in full**.

The host must separately prove that the actual native request has room for the
complete envelope alongside existing OMH, instructions, tools and response
reserve. The compiler's character-based token estimate is not that proof.
The raw reader's 128 KiB/25 s ceilings and compiler budget stay unchanged.
This option does not wire a host, change M2's OMH selection, install a provider,
or replace the first-turn preparation barrier.

A no-answer bundle (`no_answer_reason` set) is not delivered: the owner's
validator refuses it and the provider reports the closed reason.

## Reason codes

Every failure is a closed code. No raw exception text, credential, private path
or partially unauthorized bundle ever reaches a caller, a log line or a
model-visible string.

| Code | Meaning |
|---|---|
| `AGENTOS_PROVIDER_UNBOUND` | No host ports or no binding. |
| `AGENTOS_BINDING_UNAVAILABLE` | The host resolved no usable binding. |
| `AGENTOS_SESSION_MISMATCH` | The binding does not describe this session. |
| `AGENTOS_PROFILE_MISMATCH` | The binding does not describe this profile. |
| `AGENTOS_REBIND_REFUSED` | A shared provider was asked to change role. |
| `AGENTOS_SCOPE_REVOKED` | The host revoked the grant. |
| `AGENTOS_SCOPE_CHANGED` | The host rotated the grant or scope. |
| `AGENTOS_SCOPE_UNVERIFIED` | The guard could not be consulted; delivery fails closed. |
| `AGENTOS_CONTEXT_PENDING` | The read is in flight. |
| `AGENTOS_CONTEXT_UNAVAILABLE` | The read failed for a non-specific reason. |
| `AGENTOS_CONTEXT_EXPIRED` | The snapshot left its freshness budget. |
| `AGENTOS_CONTEXT_DELIVERY_TOO_LARGE` | The complete bundle exceeds 32 KiB. |
| `AGENTOS_OBSERVATION_MISMATCH` | The observation did not match the read. |
| `AGENTOS_CONTEXT_HELPER_UNAVAILABLE` | The upstream base or context helper is absent. |
| `AGENTOS_FRESHNESS_INVALID` | The freshness budget was not a finite, positive value inside the 300 s ceiling. |
| `AGENTOS_CONTEXT_LIMIT_INVALID` | The trusted host delivery limit was not a positive integer at or below 128 KiB. |
| `AGENTOS_SESSION_CLOSED` | The provider was shut down. |
| `AGENTOS_HOST_PORTS_ALREADY_INSTALLED` | A second, different host port pair was installed. |

The incumbent owner's own closed codes (`AGENTOS_BUNDLE_MALFORMED`,
`AGENTOS_EXACT_WORKSTREAM_UNRESOLVED`, `AGENTOS_OWNER_SOURCE_CHANGED`, …) are
passed through unchanged so the caller still learns why the owner refused.

## Rollback

Rollback restores the **exact prior state**. It never guesses a substitute.

1. **Capture the previous selection before anything changes it.** Hermes
   selects one external memory provider at a time, through the
   `memory.provider` key of the role profile's config; the core built-in
   store is selected by the sentinels `""`, `default`, `builtin`, `built-in`
   or `none`. Record the selected provider name and the whole relevant
   provider configuration for that profile before touching it.
2. **Restore that exact selection and that exact configuration.** Put back
   the recorded provider name and the recorded configuration values verbatim.
   **Do not blindly switch to the built-in store.** The OMH ("Oh My Hermes")
   bridge is the memory provider currently selected on M2, and it carries its
   own file-backed memory and its own configuration. Replacing it with the
   built-in store would silently drop a different provider's behavior,
   configuration and state. Restoring the built-in store is correct only when
   the built-in store is what was selected before.
3. Remove the `install_host_ports()` call from the native bootstrap.
4. Preserve the canonical Agent OS records, the built-in Hermes memory, the
   previously selected provider's own state and any private native notes.
   Rolling back this adapter must never erase company facts, and must never
   erase the previously selected provider's state.

This packet changes no live configuration and installs no provider decorator.
The selection and its rollback belong to the native host owner that holds the
role profile, at the time of the change.

There is no derived index to rebuild and no service to stop.

## Verification

`integrations/hermes_harness/tests/test_agentos_memory_provider.py` (standard
library `unittest`, no new dependencies) covers:

- an unbound provider is unavailable and never falls back;
- importing this package does not import Hermes;
- the owner's bytes and observation are delivered verbatim, with accounting and
  degraded semantics preserved;
- two roles and two workstreams do not cross-contaminate, and one role's
  private fact never reaches the other;
- query text cannot switch scope, and `prefetch` never calls the reader;
- a revoked guard and a revoke during the read discard the whole snapshot;
- a late response after a session switch or a shutdown cannot leak;
- a scope change drops the snapshot;
- a canonical correction is visible to a fresh instance, with a new bundle
  digest and source version;
- malformed bundles, digest mismatches, wrong target workstreams, no-answer
  bundles, oversized bundles and reader errors all fail safely with closed
  codes;
- no tool schemas, no write, no dispatch and no checkpoint claim;
- the freshness budget is finite and positive, at most 300 s with a 120 s
  default, and `bool`, `NaN`, `±inf`, zero, negative, over-limit and string
  values are refused before any context is acquired;
- readiness and the cached `prepare_context()` never report `READY` for a
  snapshot the host guard has revoked, changed or cannot verify, and never
  report `context_supplied` for one;
- interface compatibility against the **actual pinned upstream
  `agent/memory_provider.py`**, including its exact commit and SHA-256, and the
  real upstream `spawn_context_thread` preserving the profile context;
- the **native default path** with the real upstream module and **no injected
  spawn**: a bound provider arms the real upstream `spawn_context_thread`
  itself, the read happens exactly once, the caller's `contextvars` reach the
  read and the context is delivered;
- the same default path reached through a **real-shaped registration
  context**, so the instance is obtained the way Hermes obtains it;
- a missing or non-callable context helper failing closed with
  `AGENTOS_CONTEXT_HELPER_UNAVAILABLE` instead of a raw `TypeError`.

The upstream compatibility check locates the pinned checkout through
`MMX_HERMES_PIN` or the fleet's external-SSD pin path, and skips with an
explicit message when the pinned source is not on the host. Fixture-based
tests and the real-native check are separate cases: the native check asserts
the upstream file digest, so a fixture can never pass as native code, and a
host without the pinned source **skips** the native qualification instead of
passing it.

## Remaining live enrollment and acceptance gap

This packet delivers source only. Still open, and owned by the parent:

- **Host enrollment.** The native session/role binding that supplies
  `AgentOsBinding`, the currentness guard and the real `owner_root` is not
  wired. `install_host_ports()` is the seam; the call site lives in native
  session code that this packet does not touch.
- **Profile selection.** The role profile that activates the external
  provider (`memory.provider`) is not selected or installed.
- **Real owner read.** The qualified run against the live Agent OS compiler
  root is not performed here; the owner root in the binding is host-supplied.
- **First-turn readiness qualification.** The host must complete the bounded
  preparation above — `prepare_context()`, then a bounded wait for
  `readiness()` to leave `PENDING` — before the first request that promises
  recall. The barrier is the host's to enforce; this packet only supplies the
  two seams it needs.
- **Acceptance fixture.** The two-role/two-project fixture with a permitted
  common fact, a private fact, a stale shared fact and a source-linked
  correction must be run against the live owner publication workflow.
- **Installation and company acceptance.** Merge is not deployment, and a
  green suite is not product acceptance.
