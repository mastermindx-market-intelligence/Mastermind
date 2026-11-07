# Native Hermes registration for the selected-child delegation tool

Status: **source adapter implemented; native installation and enrollment still
open**.

This is the third increment of the selected-child chain. It answers one part
of the open item 3 in
[`EXECUTIVE_DELEGATION_BINDING.md`](EXECUTIVE_DELEGATION_BINDING.md): *Native
Hermes plugin registration with qualified profile/session lineage and a
genuinely enrolled Executive principal connection.*

It does not answer the rest. No native Hermes profile has been changed, no
Executive principal has been enrolled, no transport has been opened, and
`NATIVE_EXTENSION_NOT_INSTALLED` is untouched.

## What this module is

`integrations/hermes_harness/native_tool_registration.py` registers exactly one
tool, `mmx_delegate`, in native Hermes, and publishes only the closed
selected-child request shape.

Native Hermes owns its plugins. The loader calls `register(ctx)` with one
`hermes_cli.plugins.PluginContext`; `ctx.register_tool` owns the installed
entry, the profile scope and the unload. This module is the adapter behind
that owner. It keeps no second registration ledger, no separate tool registry
and no process-global binding.

The consumer contract is unchanged and is not re-implemented here:
`integrations/hermes_delegate/executive.py` still owns
`ExecutiveSelectedChildComposition.submit_async`/`status_async` (same-process
receiving Control) and `submit`/`status` (a different thread), and
`integrations/hermes_delegate/schema.py` still owns the closed request parser
and the canonical command format.

## The upstream contract this adapter relies on

Read at the pinned upstream `1c0cd667746d3395fe9e1b6c74f8f85952486f18`
(`integrations.hermes_runtime.constants.PINNED_UPSTREAM_SHA`, identical to
`integrations.hermes_delegate.policy.HERMES_PIN`):

| Upstream fact | Consequence here |
|---|---|
| `PluginContext.register_tool(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description="", emoji="", override=False)` | This is the only registration call. The handler and the probe are passed as keyword arguments with the upstream names. |
| The loader calls `register(ctx)` or a one-argument callable entry point, and injects no binding argument | The binding has to arrive from the host's own startup state. See the startup seam below. |
| `ctx.register_tool` registers into `registry` at the manager's `scope_key` | The readback must use the same scope or it proves nothing. |
| `registry.register` refuses a cross-toolset shadow without `override=True`, and `register_tool` returns `None` when nothing was installed | A collision is not a registration. This module never reports REGISTERED on a `None` handle. |
| `registry.snapshot_registration(name, scope=...)` reads the local profile slot with no global fallback | This is the profile-scope readback. |
| `registry.dispatch` **never calls `check_fn`** | The availability probe is discovery only. The handler re-checks the caller lineage and the binding currentness itself. |
| `registry.dispatch` narrows the injected kwargs to the handler's declared signature | The handler declares `session_id` and `task_id`, so the native dispatcher's own identity reaches it outside the model's arguments. |
| `model_tools._execute_tool` passes `task_id` and `session_id` on every dispatch | Those are the real native caller identity. They are never read from the request body and never guessed from the environment. |
| `gateway.session_context.bound_session_key()` returns `""` when nothing is bound and has no environment fallback | The route key is used only when it is genuinely available. An unavailable module means "not provable", not "no key". |
| `hermes_cli.plugin_isolation` loads third-party plugins in a separate host process under `plugins.isolation: host` | A live transport binding cannot cross that boundary, so only the in-process loading mode is supported. |

## The private host binding

`NativeDelegateBinding` is one frozen object. Every field is supplied by the
host; nothing is derived from a role label, a model argument or an environment
lookup.

| Field | Meaning |
|---|---|
| `transport` | The authenticated Executive transport the host already owns. It exposes `submit_selected_child(command_id)` and `selected_child_status(command_id)` and returns the canonical selected-child envelope. |
| `currentness_guard` | The host's synchronous proof that this binding is still current. It must return exactly `True` immediately before any possible transport write; awaitables and other truthy values refuse. |
| `profile_id` | The native Hermes profile name (`default`, a named profile, or `custom`) reported by `ctx.profile_name`. This is distinct from an absolute-home native-authority identity and must be supplied explicitly by the host. |
| `session_id` | The exact native session the registration serves. The native dispatcher's `session_id` must equal it. |
| `session_key` | Optional. The native route key, checked against `bound_session_key()` when one is genuinely bound. |
| `task_id` | Optional. The native task identity, checked against the dispatcher's `task_id` when the host binds one. |
| `command` | The frozen canonical command reference. |
| `job_id` | The selected child Job. It must be the command's own Job segment, so the two cannot describe different children. |

The binding is validated on construction: the transport must expose both
entries, the currentness guard must be a synchronous callable, the identities must be
non-empty bounded strings, the command must match the canonical command
pattern, and the command's Job segment must equal `job_id`.

**There is no replaceable process-global binding.** The handler and the probe
capture the binding object they were built with. A later binding cannot
retarget a live handler, and two registrations never share a command, a root
or a transport.

## The request

The published schema is the closed selected-child request and nothing else:

```json
{
  "type": "object",
  "additionalProperties": False,
  "required": ["action", "command"],
  "properties": {
    "action": {"type": "string", "enum": ["selected_child_status", "selected_child_submit"]},
    "command": {"type": "string"}
  }
}
```

The Bridge's `oneOf` submit/status/cancel parser is not reused and no
additional request field is injected. A model `idempotency_key`, Job id, root
id, parent id, carrier, objective, acceptance, reviewer, attempt or authority
field is refused with `UNKNOWN_FIELD`. A legacy or unknown action is refused
with `UNKNOWN_ACTION`.

The action is type-checked before it is compared with the closed action set,
so an unhashable model value (a list or a dict) is refused instead of
escaping the handler as a `TypeError`.

The model cannot choose the child. The command in the request must equal the
binding's frozen command, and the transport is always called with the
binding's command, never with the request's string.

## Refusal is not uncertainty

| Situation | State | `live_submit` | Transport called |
|---|---|---|---|
| Malformed arguments, unknown action, unknown field, malformed command | `REFUSED` | `false` | no |
| The request names another command | `REFUSED` | `false` | no |
| Missing, foreign or stale native caller | `REFUSED` | `false` | no |
| The binding is no longer current | `REFUSED` | `false` | no |
| A submit raised, timed out or returned an invalid envelope | `EFFECT_UNKNOWN` | `null` | once |
| A status read raised or returned an invalid envelope | `UNAVAILABLE` | `null` | once |
| A valid canonical envelope for the bound command | the canonical state | the canonical flag | once |

A refusal is a proved no-effect: the transport was never called. Anything
after a possible send is uncertain: the original `command_id` and `job_id` are
kept, the state is `EFFECT_UNKNOWN` for a submit and `UNAVAILABLE` for a read,
and nothing is retried, cancelled or moved to another carrier.

An invalid post-call return is uncertain, not a no-effect. The returned
envelope must carry the canonical schema, the bound `command_id`, the bound
`job_id`, a canonical state, a canonical Attempt where the state requires one,
and the canonical `live_submit` value. A return that describes another
command, another Job, an unknown state or a contradictory `live_submit` is
rejected as uncertain.

The model-facing projection carries the canonical envelope fields only:
`schema`, `state`, `reason`, `command_id`, `job_id`, `attempt_id`,
`attempt_status`, `job_status`, `live_submit`, `result_status`,
`result_envelope_digest` and `terminal_evidence_digest`. It never carries the
worker's result text, a credential, a path, a grant or a private exception
detail.

## Registration

```python
from integrations.hermes_harness.native_tool_registration import (
    NativeDelegateBinding,
    NativeDelegateStartup,
    register_native_delegate_tool,
    register_native_delegate_tools,
)

registration = register_native_delegate_tool(ctx, binding)
```

`register_native_delegate_tool` does, in order:

1. Refuse a loading mode that cannot carry a live binding: the plugin-host
   process, or `plugins.isolation: host` for a plugin that is not bundled.
2. Read the profile scope the upstream owner registers into.
3. Refuse a binding whose `profile_id` is not the profile the owner reports.
4. Enter the existing `replacement_coordinator.transaction()` and refuse a
   name already installed in this profile scope, or taken process-globally.
   Keep the absence checks, registration, readback and any lease rollback in
   that same native-owner transaction.
5. Register through `ctx.register_tool` with the closed schema, the bound
   handler and the bound availability probe.
6. Refuse a `None` handle. The owner's refusal is never reported as a
   registration.
7. Read back through the owner's own registry API
   (`registry.snapshot_registration(name, scope=...)`) and require the exact
   entry, handler, toolset, schema and probe.

If readback raises or differs after a lease was returned, dispose that exact
captured lease through its native owner. Disposal is idempotent and
identity-conditional, so it preserves a later registration. A disposal failure
is `NATIVE_TOOL_ROLLBACK_EFFECT_UNKNOWN` and retains that original handle.

The native owner can write its registry slot and then raise before returning
its lease. Such an exception is `NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN`,
with the original context, binding, scope and tool retained privately on the
error for owner reconciliation. Do not retry, replace the context or broadly
unregister the name. The native coordinator serializes supported context and
lease users; unrelated raw-registry writers are outside this guarantee.

The returned `NativeDelegateRegistration` holds the owner's own lease.
Disposing it releases the entry exactly as Hermes unload does; this module
never calls `registry.deregister` behind the owner's back.

`register_native_delegate_tools(ctx, startup)` is a private host composition
helper. The loader does not inject its second argument. It takes the host's
startup object, whose default state is unbound:

```python
startup = NativeDelegateStartup()          # unbound by default
register_native_delegate_tools(ctx, startup)  # -> NATIVE_TOOL_STARTUP_UNBOUND
```

The host owns the instance and installs the binding it actually holds.

## Two profiles do not exchange handlers

Each registration lands in the profile scope of its own manager and holds its
own binding. Two registrations in two scopes keep two separate entries, two
separate handlers and two separate transports; a dispatch in one scope never
reaches the other's transport or command. A second registration in the *same*
scope is refused with `NATIVE_TOOL_COLLISION` and leaves the first
registration untouched.

## The startup seam, and what is still open

This module supplies an honest source-level seam. It does not supply the
binding, and it cannot obtain one by itself: `register(ctx)` carries no
binding argument, and a remote Hermes process cannot share this Python
binding.

The remaining production dependencies are explicit and unchanged:

1. An actual host owner selecting and freezing the child, then supplying the
   immutable target, the authenticated Executive transport and the
   currentness guard as one `NativeDelegateBinding`.
2. A Hermes plugin package that owns the startup instance, imports this
   module and calls `register_native_delegate_tools(ctx, startup)` from its
   actual `register(ctx)` hook, inside the native Hermes process, where the pinned upstream is
   the only importable Hermes source.
3. A genuinely enrolled Executive principal connection and the installed
   mission generation. Provider BYOK credentials and the read-only Steward
   token do not authorize this operation.
4. The installed producer-to-consumer proof, including the original-command
   return.

Nothing here routes through the read-only Steward or `submit_principal_intent`,
opens another listener, mints a token owner, imports mutable source through
the environment, alters the runtime install, supervisor or configuration, or
clears `NATIVE_EXTENSION_NOT_INSTALLED`.

## Verification

```sh
python3 -m unittest discover -v -s "integrations/hermes_harness/tests" -p 'test_*.py'
```

The focused file is
`integrations/hermes_harness/tests/test_native_tool_registration.py`. It has
two layers.

**Controlled adapter tests** need no upstream runtime. They cover the binding
contract, the closed request shape, the caller-lineage fence, the
refusal/uncertainty split, the binding isolation and the drift guard against
the accepted contract's state set and envelope schema.

**Native API tests** exercise the real pinned `PluginContext`,
`PluginManager` and `ToolRegistry`: registration, the profile-scope readback,
collision refusal, the owner unload, the real discovery path with the real
availability probe, the real dispatch with the real `session_id`/`task_id`
kwargs, the real route-key context and the two-profile isolation.

They run only when a checkout of the pinned upstream is available:

```sh
MASTERMIND_HERMES_VENDOR_ROOT=/path/to/hermes-agent \
  python3 -m unittest discover -v -s "integrations/hermes_harness/tests" \
  -p 'test_native_tool_registration.py'
```

Without that variable the native layer skips with the exact reason, and the
controlled layer still runs.

### The exact test-environment limit

The pinned upstream imports `ruamel.yaml`, which is absent from the review
environment and cannot be installed under this grant. The native test
therefore installs an **import-only** shim for that library: the shim's
`YAML` raises if anything actually parses YAML, so the native path under test
provably never touches a YAML parser. The upstream code under test is the
pinned code, and the test asserts the vendor checkout's `HEAD` is
`PINNED_UPSTREAM_SHA` when the checkout is a git repository.

No package was installed, no provider was called, no credential was used, no
service was started and no native profile was touched.
