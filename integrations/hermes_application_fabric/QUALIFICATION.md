# Hermes APPLICATION adapter qualification

## Observed result

On 2026-11-06, the installed Hermes v0.23.0 runtime completed **53 tests, zero
failures, zero errors, zero skips**, exit code 0. This is actual native Hermes
execution against the original APPLICATION client and a loopback endpoint.
**Live provider acceptance is false.** The endpoint, bearer token, served model,
usage and tool handler are fixture data. Production identity, a physical provider
account, quota/budget settlement and release/install acceptance are not proved.

| Source or receipt | Exact identity |
| --- | --- |
| Tested adapter | `179bc6fc9ce232292816669895504e7274eb77fb` |
| Protected source/procedure base | `2f60dc913622da61a65a2cc6f8a793a81c61eea1` |
| Clean installed Hermes v0.23.0 | `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` |
| Macro #10740 APPLICATION owner | `2ef828e569b683b9dfaa94f81116da3ac55f6186` |
| Original client Git blob | `4d2be0731fee7728d9027d0d09c5a517cc313f3b` |
| Original client SHA256 (45,525 bytes) | `3250f2ea9b56b4762619a960c23dd5cc57ae05c273fe8e2b63c89a0f868d0ce0` |
| Runtime | Python 3.14.9; jsonschema 4.26.0 |
| Qualification log SHA256 (9,273 bytes) | `74dbb01762318e264f3f018a939454577a7fc184c6c9766a9b5b1cc233f6ee53` |

The [machine-readable receipt](qualification/installed_native_receipt.json)
records the tested source hashes and test identifiers. Later documentation and
offline CI additions do not change the native-tested product sources. A later
change to those source hashes requires focused requalification.

## What ran

| Suite | Count | Evidence |
| --- | ---: | --- |
| Conversation/response codec and original owner loopback | 32 | Real Macro client, native APPLICATION headers/protocol, identity, model/usage, bound/error behavior. |
| Installed native Hermes | 12 | Actual provider resolution, AIAgent, middleware, transport, tools, error classifier and watchdog. |
| Structured JSON | 9 | Installed jsonschema validation, forced result-tool consumption, invalid/ref/unknown schema rejection without repair/replay. |

The immutable candidate was staged as test material. The installed Hermes tree
was verified clean at its pinned commit. The existing `runtime_command` launcher
ran `qualify_installed.py` through a `runpy.run_path` code entry, with an isolated
`HERMES_HOME` and no provider-key environment. Candidate hashes and the exact
owner source checksum were checked before imports. The loopback fixture injects
a test-only binding; successful production `from_factory` and role admission were
not exercised. Standard OpenAI and
AsyncOpenAI constructors were instrumented to fail; neither was called.
External network connections were denied, with zero attempted external connects.

### Native primary/tool journey

The actual primary AIAgent returned the fixture text through the original owner.
The tool journey used Hermes's native deferred `tool_call` wrapper and its real
tool registry. One in-memory fixture handler executed exactly once; the next
model request contained its original tool-call ID and tool result. The two API
request IDs were distinct, while the original APPLICATION operation and client
were retained. No adapter-side tool execution was substituted.

### Recovery without replay

A connection loss on the second model call, after native tool execution, caused
terminal failure: two original inference attempts total, one tool execution, one
original close. Rebuilding the facade with a new native API ID could not create
a third owner call.

The real native non-streaming watchdog was exercised by reducing only its test
timeout threshold and holding the loopback response. Its timeout crossed the
actual middleware wrapper. The original owner's local close fence prevented a
late result and a new API identity from dispatching; one inference attempt and
one original close occurred. This proves the local/original-client fence, **not
provider cancellation or release of a real reservation**.

Native exception causes/contexts were detached, and retry, compression,
credential-rotation and fallback flags were disabled. A typed original-owner
429 refusal did not cause adapter failover. An uncertain/pending owner receipt
kept its uncertainty. No timeout or generic HTTP status was treated as permission
to call another provider.

### Compatibility fixes found by actual execution

Hermes v0.23 injects a bounded W3C trace header and an SDK `timeout` after normal
request construction. Only that trace metadata is accepted; arbitrary header
overrides refuse. A finite positive SDK timeout must cover the already-bound
owner timeout. A tighter deadline refuses before dispatch rather than changing
the owner's in-flight timeout. The owner can establish a narrower timeout at
initial host binding through its existing caller configuration.

The native middleware wraps downstream failures; the adapter unwraps only the
observed native wrapper and prevents Hermes from traversing a raw original
exception into a retry/fallback route. Keyless native construction and the
native async-wrapper escape are covered at the installed revision.

## Repeatable checks

The separate `Hermes APPLICATION inference contract` workflow runs 41 offline
tests on Python 3.12 and 3.13. It checks out the exact Macro client using the
repository's existing read-only checkout credential, checks its SHA256, and
copies only that source into an isolated temporary import fixture. It receives
no provider keys and does not import the owner's startup/package initializer.
This workflow does not claim the additional 12 installed-Hermes checks or a live
account result. Its CI result must be read from the exact PR head independently
of this installed-runtime receipt.

```sh
python -B integrations/hermes_application_fabric/qualification/qualify_offline.py \
  --owner-root /path/to/exact/macro/checkout
```

## Remaining owner integration and acceptance

At the qualification boundary, Macro #10740 remained open/draft at the exact
owner SHA above, with its original exclusive writer. Its service relation does
not enroll Hermes, and source-defined APPLICATION transports remain unqualified
and disallowed. The adapter's production factory therefore refuses. No Brain
identity or provider endpoint is borrowed to bypass that decision.

The existing owners must supply these source-linked deltas through their current
admission/release paths:

1. Enroll a qualified Hermes application role/service relation and compose the
   existing authenticated role/session host with `ApplicationBinding.from_factory`
   and the native middleware resolver. Retain the original binding for recovery.
2. Extend the existing APPLICATION selection contract with trusted capability,
   complexity, latency, cost and strict model/pool constraints, and actual
   provider/model/physical-account selection proof. Reuse ModelRouter/Fabric
   account, quota, lease and budget ownership. No Hermes-side ranker is added.
3. Qualify one real eligible account with a bounded primary/tool conversation,
   actual usage, admission/budget denial, settlement and original-result recovery.
   Deduplicate headroom by physical quota bucket across model/pool aliases.
4. Supply original-operation result/recovery and any required genuine streaming
   or provider cancellation through the incumbent protocol. Local facade close
   and buffered output are not substitutes for these receipts.
5. Integrate, release and install through the existing protected-source and Hermes
   installer custody. Tests alone do not enable the adapter in a production role.

The owner request is [Macro #10740](https://github.com/mastermindx-market-intelligence/macro/pull/10740#issuecomment-6696511751).
Delivery is recorded; owner pickup/START and live-account acceptance are not.
The programme remains incomplete until its original real-account acceptance is
proved. No background runner or automatic continuation is claimed.
