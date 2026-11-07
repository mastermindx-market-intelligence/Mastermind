# Authenticated adopted Agent OS context

This source composes the existing adopted-context receiver into the current COO
App, MCP server and App-peer Control transport. It does not enroll a principal,
install a release, activate native memory, or establish production acceptance.

## Owner path

`/mcp/coo` → authenticated `CooApp` → `CooFactsClient` → existing Workspace client
and Control socket → `CooHostProvider` → the collector-issued
`AgentOsContextBundleReader` → the adopted Macro compiler.

The installed `CooInstalledSource` remains the principal/mission/profile owner.
The Control process uses the existing `InstalledBootPacketCollector`; the public
App does not open Runtime, execute Macro, or choose a filesystem source. The
collector's receipt and limits are specified in `AGENTOS_CONTEXT_RECEIVER.md`.

## Two fixed catalogues on one authenticated connection

| Contract | Legacy | Explicit context alternative |
| --- | --- | --- |
| Catalogue | `coo.v1` | `coo.agentos_context.v1` |
| Tools | Existing seven, unchanged | Those same seven plus `executive_agentos_context` |
| Schema digest | `5cf2a0de4a47686c545d1ee3d9c388ab4dc94c880cb0670140de2eca2e54f550` | `5fa24aa1d907d66d0ca0a56168617f955e09d063f532cf527fe0d7b923fb50af` |
| Native profile | `principal.hermes-native.executive-coo.v1` | `principal.hermes-native.executive-coo.context.v1` |
| Public MCP grant | `mastermind-executive-coo-v1` | `mastermind-executive-coo-context-v1` |
| Source default | Existing behavior | Profile disabled |

Both grants describe the same `mastermindExecutiveCoo` connection at
`https://mcp.mastermind-x.com/mcp/coo`, server `mastermind-executive-coo` version
`1.0.0`. The policy loader permits only this exact alternative pair to share the
configuration name. Both records must preserve the fixed connection identity;
normalized capability-ID aliases and a third record refuse. A profile cannot
resolve two grants with the same configuration name. Only the exact context
profile can reference the new grant. Tool-schema ownership remains in the COO
descriptor module and installed source, with no arbitrary subset or union.

The existing Claude and native Hermes profile digests remain, respectively:

* `5d4a2b7e89c5fee0e34be6a623a4a19e5d91b5d743c7365826ef3384af8bf217`
* `468554c7ba97df5fe86933f08d6928daa48910a1fba2494cd3a537a417382a3d`

The inert rich-Claude loopback candidate `executive-coo-mcp-v1` is a different
grant and does not participate in this alternative pair.

`tools/list` authenticates the current principal and selects from that binding's
enabled missions. Mixed active catalogues refuse. Disabled retained missions do
not poison selection. With no enabled missions the seven-tool reconciliation
surface remains; that fallback grants no context acquisition. Concurrent
principals select independently on the same server.

## Read authorization

The public tool accepts exactly `{"work_ref":"WS:..."}`. It accepts no source,
path, budget, profile, compiler, commit, or latest-data selector.

An enabled mission must explicitly grant `read_adopted_agentos_context` in its
existing v2 action list and reference the enabled context profile's exact digest.
Default principal actions remain unchanged. App derives the principal frame,
mission authority and generation from its installed owners. Control independently
derives and compares the same facts before and after compilation.

This read does not require fresh-job admission to be armed. The launcher may
compose the existing facts factory when a sealed installed context grant exists,
while retaining `principal_admission_armed=coo_effects_armed`. Principal and
selected-child submission retain their incumbent arming checks. A closed
new-effect gate does not itself prohibit reading authorized continuity.

The App checks the selected mission again after Control returns. This check is
scoped to the requested workstream: a different still-enabled mission cannot
keep a revoked mission readable. The full mission row is compared at Control
because the original generation intentionally excludes `enabled`. Disabled
mission authority remains available to original-request reconciliation under its
existing rules.

Construction-time App settings/providers, installed source callbacks and the
private client's original socket/connection method are retained. Replacements
refuse rather than adopting equal-looking successors. Control also holds and
rechecks the same App binding, factory, Runtime, namespace custody, connection,
peer, readiness, arming values, provider source/workspace and opaque reader around
the awaited operation. The receiver retains its own materialized source and
runtime custody checks. These are observations at the receiving boundaries;
they do not promise detection of every unobserved revoke-and-restore interval.

## Wire and bounds

The private request discriminator is
`mastermind.ceo_ingress.coo_agentos_context.v1`. It contains only `schema`, the
existing six-field `principal`, server-derived `principal_context`, and
`capability_profile_digest`.

The result discriminator is `mastermind.coo_agentos_context_result.v1`. Its exact
fields are `schema`, `catalogue`, `principal_context`,
`capability_profile_digest`, `bundle_encoding`, `bundle_base64`, and `receipt`.
Encoding is only canonical standard padded base64. The original UTF-8 compiler
bytes are never reserialized or trimmed.

The shared decoder rejects duplicate keys, nonfinite numbers, malformed UTF-8,
unknown fields, noncanonical base64 and oversized input. It applies both the
incumbent `validate_bundle` and receiver `validate_context_read`, then cross-binds
workstream, repository SHA, fixed integer budget, generation timestamp, degraded
count and omitted count. The principal context and capability digest must equal
the requesting authority. A well-shaped receipt alone is insufficient.

| Boundary | Limit |
| --- | --- |
| Private context request | 8 KiB |
| Original context bundle | 128 KiB |
| Owner receipt | 16 KiB |
| Private context response | 224 KiB |
| App response | Existing 256 KiB |
| Serialized MCP context result | Existing 256 KiB less 4 KiB framing reserve |
| Context read transport | Existing 30-second read allowance |
| Context transport cleanup | At most one additional second |
| Legacy FACT transport | Existing 10 seconds, unchanged |

The compiler's 25-second cooperative result deadline is unchanged and is not a
new hard wall-clock guarantee. Oversized or conflicting results refuse as a
whole. A successful result is a read receipt with `execution_authority:false`,
not a Job, claim, attempt, model-request proof, or held-out EVAL.

## Verification and remaining acceptance

`tests/test_executive_coo_agentos_context.py` uses the captured actual Macro
compiler/helper, the real installed collector and opaque reader, disposable Git
sources, genuine signed JWTs, and the real App/MCP implementation. CF2 host
attestation is an explicit fixture and is not represented as installed evidence.

Coverage includes old profile/catalogue identity, the closed alternative pair,
cross-principal selection, refusal before compilation, late mission revocation,
owner/settings/client replacement, raw/receipt contradictions, final serialized
response sizing, selected read budgets and optional unarmed source selection.
Synthetic whitespace around actual compiler JSON tests the 128 KiB transport
edge separately from natural corpus size. In-memory stream tests do not open or
prove a socket.

The two real AF_UNIX tests compose the actual Control service and signed MCP
client, assert exact returned bytes and an unchanged empty Runtime Job set, and
cover principal admission both armed and disarmed. Local execution encountered
`PermissionError: [Errno 1] Operation not permitted` creating the Unix socket.
That denied local action was not retried; these tests remain required evidence in
an authorized test environment and are not counted as local passes.

Installed acceptance still requires a qualified release, explicit profile and
mission enrollment, the original authorized host connection, and a source-bound
native consumer that uses its existing captured MCP connection and memory loader.
This change does not substitute a local Macro tree, create a second memory store,
or expose raw Executive tools to the native model.
