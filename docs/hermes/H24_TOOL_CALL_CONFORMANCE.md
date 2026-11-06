# H24-01 — Structured-tool and original-command conformance

## Scope and delivery state

This is a source-only diagnostic for the H24-01 packet. It tests the C28 one-tool
contract against frozen selected-child coordinates, injected authenticated-host
fixtures, an injected invocation transport, and an independent read of the same
receiving owner's original command. It creates no production tool, authorization
path, broker, provider, retry controller, command ledger, or claim lock.

The implementation and fixtures are applied to the exact isolated packet branch
listed below. The earlier checkpoint was an unapplied artifact: Desktop
Commander refused the original Ubuntu worktree path, and readback proved no
source write. The Chairman then explicitly requested Studio Direct. Its
installed workspace owner allocated the required `sol` lane on M2 Studio after
an unused, clean `web`-lane checkout was reconciled and released. The original
Ubuntu worktree remained unchanged at the base; its denied write was not replayed.

The source files were read back against the verified candidate hashes, then
exercised directly from the Studio worktree. Source delivery and its exact
commit/head/diff receipt are recorded in the parent checkpoint. The contract
base below remains immutable when the delivery head advances. Neither these
fixtures nor a source commit establish installation, activation, or live
execution. No merge or self-approval is part of H24-01.

| Coordinate | Exact value |
| --- | --- |
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Required branch | `sol/h24-01-tool-conformance-20261106` |
| Immutable contract base | `b54cb10e4abdd3766c62d4088f6a576ecfe80437` |
| Managed Studio worktree | `/Volumes/Mastermind 2/agent-workspaces/sol/h24-01-tool-conformance-20261106` |
| Pinned Hermes source | `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18` |
| Actual C28 catalog SHA-256, canonical JSON | `bb2ed3a7c5a00f3af5bc9f5ea8605eb6e481f40afbbaee277bb98059f47bbe36` |
| Direct Studio verification | **239 passed, 2 subtests passed; exit 0; no skips** |

Only these three new repository paths belong to this packet:

- `integrations/hermes_harness/contract_probe.py`
- `integrations/hermes_harness/tests/test_h24_contract_probe.py`
- `docs/hermes/H24_TOOL_CALL_CONFORMANCE.md`

Only the three paths above belong to the source diff. Earlier checkpoint
archives and temporary verification logs are evidence outside that diff. C28
implementation, C29–C34 owner files, Runtime/Job/Attempt source, release owners,
credentials, and existing CI workflows are unchanged. Tests create only
disposable receiving-owner fixture state; no installed Control is contacted.

## Verified contract joins

All Mastermind source links below resolve to the immutable packet base.

| Owner | Reused contract and boundary |
| --- | --- |
| [C28 native registration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_harness/native_tool_registration.py) | The actual `NATIVE_TOOL_SCHEMA`, `TOOL_NAME`, selected-child schema and state constants, synchronous `submit_selected_child(command)` / `selected_child_status(command)` seam, and incumbent registration/unload fixture. The probe never calls registration. |
| [Selected-child request parser](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_delegate/schema.py) | Actual `SELECTED_CHILD_FIELDS`, `parse_selected_child`, command grammar, and digest grammar. Exact scalar checks run before the existing parser because list/object action values would otherwise reach set membership. |
| [C17 selected-child composition](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_delegate/executive.py) | Actual frozen `ExecutiveChildSelection` / `ExecutiveSelectedChild`, validation, command identity, `ExecutiveSelectedChildComposition`, and original `submit_async` / `status_async` receiving-owner behavior. Claims remain owned by the original Executive service. |
| [Native private session control](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_runtime/native_session_control.py) | Actual `validate_target`: closed native profile/session/principal/instance identity and strict authority epoch, revision, and execution-generation counters. This schema is not a Job/Attempt identity or a selected-child dispatch API. |
| [Existing private ingress transport](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_executive_app/gateway.py) | Actual `CeoIngressResponse`, `TRANSPORT_NOT_SENT`, `TRANSPORT_SENT_OK`, and existing 8,192-byte request / 32,768-byte response limits. Reusing the receipt type does not assert that C29 ingress exists at this base. |
| [C29 exclusive commission](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6680534154) | Read-only composition evidence. Its `ExecutiveSelectedChildTarget`, selected-child private ingress frame, authenticated App/Control path, and target-digest owner are later integration work. H24 does not implement or claim those components. |
| [Pinned Hermes MCP task](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/tools/mcp_tool.py) and [call handlers](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/tools/mcp_tool_handlers.py) | Actual `MCPServerTask`, `_track_inflight_rpc`, `_call_tool_racing_stdio_death`, and `_fail_inflight_calls` own in-flight liveness and cancellation. H24 interprets the observed failure and adds no liveness or retry controller. |

The current request is exactly an object with `action` and `command`. Its action
is `selected_child_submit` or `selected_child_status`; the command must be the
frozen selected child's original command. A model cannot provide a job, attempt,
principal, digest, target, or source generation in that request.

The actual selected-child response schema is
`mastermind.hermes_delegate.selected_child/v1`. Required fields are `schema`,
`state`, `reason`, `command_id`, `job_id`, `attempt_id`, `attempt_status`,
`job_status`, and `live_submit`. The probe permits only the incumbent additional
root, ordinal, role, operation, session, and sealed-result projection fields. It
rejects missing fields, foreign fields, mismatched schema, and invalid states.

## Diagnostic API and trust boundary

`ContractProbe` captures a real frozen `ExecutiveSelectedChild`, a frozen
`AuthenticatedHostFixture`, an injected transport exposing the two existing C28
methods, an `observe_host()` fixture callback, and a `read_original(command)`
callback. An already known `original_attempt_id` may also be frozen into it.

`AuthenticatedHostFixture` carries native target JSON validated by the actual
native private-control schema, the actual `PrincipalAdmissionContext` value
type, an owner-supplied target digest, an opaque registration lease identity,
source-generation coordinates, and explicit fixture booleans. These are
**injected test observations**. Their construction is not authentication,
enrollment, authorization, installation, or proof of a live native binding.

The target digest is compared with the frozen expected value. H24 does not
invent C29's target serialization or digest algorithm. The current C17 response
does not carry that target digest, so it is checked in host observations rather
than added as a new response field. A future host adapter must obtain these
observations from the existing authoritative owners.

`SourceGeneration` freezes the Mastermind SHA, catalog-source SHA, upstream SHA,
and catalog digest. Expectations remain pinned to the packet base. The probe
rehashes the actual C28 module's catalog at each boundary, including replacement
of the entire schema object; it never adopts an observed changed catalog as a
new expectation.

`run(arguments, tool_name=TOOL_NAME)` performs one invocation at most. It validates
host/session/lease/source/target observations before the call, after the response,
and after original-command readback. Only the initial fresh submit requires
admission to be open. Closing fresh admission cannot turn a possible earlier
send into a not-sent receipt or prevent otherwise-valid original status reads.

The module opens no sockets, files, processes, credentials, clocks, or Runtime.
All transport and original-command observations are explicit injected calls.
It keeps no mutable command history and adds no local claim lock. Callers must
retain an earlier `EFFECT_UNKNOWN`; a later unavailable status does not erase it.

## Strict input and response rules

- Exact JSON/Python types: booleans are not integers; Python subclasses and
  coercible objects are not accepted as their base JSON types.
- Text and byte JSON reject duplicate keys, including equal values and escaped
  spellings; reordered distinct keys have identical canonical meaning.
- NaN, positive/negative infinity, exponent overflow, invalid Unicode/surrogates,
  unsupported values, excessive nesting, excessive nodes, and excessive UTF-8
  bytes are rejected. Trees are limited to depth 32 and 4,096 visited nodes.
- Validated dictionaries are detached through canonical JSON before use.
- The command and job must match the frozen child. An exposed root and ordinal
  must also match exactly. Response and original readback must name the same
  attempt, including any previously frozen original attempt.
- Runtime status values come from the actual `AttemptStatus` and `JobStatus`
  enums. Effect flags use the actual three-valued selected-child meaning:
  observed attempt means `true`; qualified absence means `false`; uncertainty
  without an observed attempt means `null`.
- `COMPLETED` requires a completed attempt and job, `result_status=RESULT`, a
  valid result-envelope digest, and a valid terminal-evidence digest. Terminal
  claims cannot contradict the original owner. Disclosed sealed-result values
  must match original readback. Normal `ACTIVE` to `COMPLETED` progress between
  reads is allowed; the report uses the validated later original snapshot.
- Raw exception text is not disclosed. Diagnostic reasons are closed codes.
  An accidentally returned coroutine is closed and treated as an incomplete
  synchronous call, not completed authentication or a successful response.

## Effect classification and deterministic report

| Observation | Diagnostic outcome | Effect treatment |
| --- | --- | --- |
| Invalid request or stale/unauthenticated host before invocation | `REFUSED` | No invocation; no possible modifying send. |
| Actual `CeoIngressResponse` proves `not_sent`, with no success/result/error payload | `REFUSED` for submit; `UNAVAILABLE` for status | The sole entered call is proven not sent. A lookalike dictionary or conflicting receipt is insufficient. |
| Timeout, EOF, disconnect, cancellation, malformed/mismatched response, or failed readback after entering submit | `EFFECT_UNKNOWN` | Original identity retained; no automatic readback, submit replay, cancellation, replacement, or failover is initiated after the failure. |
| Status call or its readback fails | `UNAVAILABLE` | Observation failed; status never becomes submit, and no earlier uncertain effect is cleared. |
| Valid response, current fixture observations, and matching original readback | `CONFORMANT` | The protocol check passed. The original envelope may itself be `REFUSED`, `EFFECT_UNKNOWN`, or another actual owner state. |

The failure split distinguishes a proven pre-send refusal from uncertainty after
a possible modifying send. It does not flatten the owner's three-valued
`live_submit` field or turn an observed owner refusal into a transport failure.

`ProbeReport.to_json()` emits stable sorted compact JSON with schema
`mastermind.hermes_h24.contract_probe/v1`, `evidence=SOURCE_ONLY`,
`production_execution_proven=false`, pinned source/catalog coordinates, original
command/job/attempt, action, closed diagnostic reason, transport/readback flags,
and the validated original envelope when available. It adds no current time,
random identifier, synthetic START receipt, or production-serving assertion.

`CONFORMANT` means conformance of supplied evidence only. Even a real claim in a
disposable Runtime fixture does not establish live dispatch or acceptance.

## Acceptance fixture matrix

| Case group | Exercise and assertion |
| --- | --- |
| Valid submit and status | Both request representations and both actions preserve original coordinates and canonical report bytes. |
| Original completed result | Required sealed fields and digest values are checked against the original owner; no result is synthesized. |
| Malformed action and request | List/object/null/numeric action, missing/extra keys, legacy fields, foreign command, and wrong tool name refuse before transport. |
| Strict JSON | Duplicate and reordered keys, nonfinite tokens, exponent overflow, Python coercions, Unicode, byte limits, and depth limits. |
| Envelope drift | Schema/version mismatch, missing/extra fields, invalid scalar types, job/root/ordinal/attempt/status/digest mismatch. |
| Host currentness | Session, lease, principal, source generation, authentication, and target digest drift before send, after send, and after original readback. |
| Catalog drift | Mutation of the actual catalog and replacement of its module object are both rejected. |
| Not-sent evidence | Only the actual unambiguous transport receipt clears possible-send classification; fake/contradictory receipts do not. |
| Lost call or result | Timeout, EOF, cancellation, and transport/readback exceptions yield uncertainty after submit, with no replay. |
| Admission closed | Status retains the original observation and makes no submit; fresh submit refuses. Admission closing after send preserves uncertainty. |
| Initial concurrent submissions | Two callers both observe `NOT_CLAIMED` and reach the original dispatch boundary before release. The real receiving owner persists one claim and one Attempt, with one supervisor start. No probe lock is introduced. |
| Real original-result recovery | Lose a reply after the actual disposable receiving claim, let its original result settle, quarantine fresh admission, then read the same sealed original result twice. Claim count stays one. |
| Actual C28 registration | Incumbent fixture checks registration/readback, owner unload, lease-scoped cleanup after readback failure, and registration exception uncertainty. |
| Actual Hermes call disconnect | Pinned `MCPServerTask` and call-handler tracking cancel the in-flight injected model tool call. One call occurs, the in-flight set drains, and H24 returns `EFFECT_UNKNOWN` without replay. No server connection is created. |
| Report hygiene | Deterministic output, source-only evidence markers, no private exception disclosure, no synthetic execution-success assertion. |

The competing-call test uses a fixture barrier immediately before the actual
`ExecutiveControlService.dispatch_selected_child` implementation. Both requests
cross qualification before either reaches the original claim owner. The barrier
is orchestration for a race fixture, not a second claim implementation.

The upstream fixture verifies the exact checkout SHA and byte identity of
`tools/mcp_tool.py`, `tools/mcp_tool_health.py`, `tools/mcp_tool_handlers.py`,
`hermes_cli/plugins.py`, `tools/registry.py`, and `registration_lifecycle.py`.
It reuses C28's incumbent import fixture, including its import-only dependency
shim. No packages, plugin registration, or service configuration are installed.

## Executed verification and receipts

### Direct source verification on Studio

The applied files were tested directly from the exact managed branch on M2
Studio, using Python 3.14.7, pytest 9.1.1, and the pinned upstream source checkout.
No in-memory candidate replacement was used in this run. The implementation
and test file bytes used for this run matched the earlier verified candidate:

```text
integrations/hermes_harness/contract_probe.py
d148bf1467b4fbbcc07aaae8079e7c855941fb9bd70585b65654319a4b541330
integrations/hermes_harness/tests/test_h24_contract_probe.py
ec1e9039d0279ae91f9a890526211e1ae75ce5f815d4799181b4d3dbd1f2c173
```

The subsequent diff check identified one redundant blank line at EOF in each
Python file. Removing those two newline bytes was the only Python-source change
after the passing run. ASTs including every source-position attribute were
compared before/after and were identical. Final file SHA-256 values are:

```text
contract_probe.py
 a45e5045cd22061af1bf01519a10eef6b38efcab0df698ea7b45e854c52efc87
test_h24_contract_probe.py
 4a6efb9322ae0b2e2c31146930165aa72d9c3965905b0fc329b59fcd1b87a000
```

Exact executed command, from the managed Studio worktree:

```bash
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 MASTERMIND_HERMES_VENDOR_ROOT=/tmp/h24-01-hermes-source-1c0cd667-studio python3 -B -m pytest --noconftest -o addopts= -q -p no:cacheprovider integrations/hermes_harness/tests/test_h24_contract_probe.py integrations/hermes_harness/tests/test_native_tool_registration.py tests/test_hermes_selected_child_dispatch.py
```

The shell redirected stdout/stderr to
`/tmp/h24-01-studio-canonical-regression.log`, retained the test exit code,
printed its final lines, and exited with that same code. Observed result:

```text
239 passed, 2 subtests passed in 29.56s
Process completed with exit code 0
```

No tests were skipped. The captured passing log has SHA-256
`f722a31810ec71d6277c6a9265d76cfe39a9dfe08a8a82e790f6c67abc7cc450`.
The command exercises H24 plus the existing full C28
registration and C17 selected-child fixture files. Bytecode and pytest cache
writes are disabled. Source changes are limited to the three owned additions.

**macOS temporary-path requirement:** On this host, `/tmp` resolves to
`/private/tmp`. The first direct run used the former spelling and produced
`8 failed, 231 passed, 2 subtests passed in 25.99s`. Those failures were in native
registration/dispatch fixtures: their expected scope retained `/tmp`, while
registration canonicalized the scope to `/private/tmp`. The final command sets
`TMPDIR=/private/tmp` so the incumbent fixtures supply canonical scopes. No C28
source, upstream source, installed configuration, or dependency was changed.
The first result remains historical failure evidence, not a passing run.

### Earlier unapplied-candidate verification

Before Studio source delivery, ubuntu1 tested the same implementation and test
bytes against the unchanged immutable base with Python 3.12.3 and pytest 9.1.1.
That runner loaded the candidate module from a temporary artifact into memory
and asserted exact source/upstream heads and a clean source tree before and
after pytest. It did not apply source changes.

Exact executed candidate command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/h24-01-probe-verification/verify_candidate.py --source-root /home/longr/.mastermind/agent-workspaces/sol/h24-01-tool-conformance-20261106 --candidate-root /tmp/h24-01-probe-verification --upstream /tmp/h24-01-hermes-source-1c0cd667 > /tmp/h24-01-probe-verification/final-regression.log 2>&1; h24_rc=$?; tail -60 /tmp/h24-01-probe-verification/final-regression.log; exit "$h24_rc"
```

Observed candidate result:

```text
239 passed, 2 subtests passed in 10.21s
{"managed_source_unchanged": true, "pytest_exit_code": 0}
```

The historical final candidate log has SHA-256
`94869e2478466da55cff0284994dd88cc6d54fb498036d190e6a2242ef740f2b`.
Earlier environment/import failures were retained in the initial checkpoint:
unavailable `numpy` entered through the broad `tests/conftest.py`, and two
incumbent bare-test imports failed in the first candidate run. Fixture isolation
with `--noconftest` and the real tests import path resolved them without
installation or incumbent source changes. The final candidate and direct Studio
runs above include the actual pinned upstream fixtures without skips.

The old candidate runner requires a clean source tree at the immutable base. It
must not be used as a post-commit test runner; use the direct repository command.

## Later owner composition

**C29:** The commission proposes a frozen `ExecutiveSelectedChildTarget`, its
owner-derived digest, and private frame schema
`mastermind.ceo_ingress.selected_child.v1` with exact fields `schema`, `request`,
`target_digest`, `principal`, `principal_context`, and
`capability_profile_digest`. The authenticated App providers (`CooApp._auth`,
`_authority`, `_same_auth`), `CeoIngressClient.send_frame`, Control's
`_handle_ceo_ingress_connection`, and existing selected-child composition remain
the owner joins to complete. H24 does not implement that proposed frame or trust
model-supplied authentication fields. C29's target/receiving guard expects exact
`None`; C28's binding guard expects exact `True`. Those contracts must not be
combined by truthiness.

**C31/native host composition:** The actual native startup owner must join its
captured session and registration lease to an authenticated C29 transport,
current selected target, immutable installed source generation, and the original
return path. C28's `register_native_delegate_tools(ctx, startup)` helper and
upstream registration/liveness owners remain the real seams. A plugin loader
calling `register(ctx)` does not itself supply the missing startup binding.
This packet has not verified a C31 production composition and creates no
substitute for it. See the base [C28 registration documentation](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/docs/hermes/NATIVE_TOOL_REGISTRATION.md).

## Parent checkpoint and composition boundary

The source-only packet is ready for parent consumption on
`sol/h24-01-tool-conformance-20261106`. The parent return records the actual
committed/published head and the SHA-256 of the three-path diff from the immutable
base; a clean working-tree diff after commit is not that owned diff. This document
intentionally does not embed its own commit SHA.

The earlier Ubuntu directory denial and uncertain Studio workspace receipt were
reconciled before source work. They are historical recovery facts, not active
release/review gates. The Studio `web`-lane checkout was clean at the base and was
released before the exact required `sol` branch was acquired. No source content
was written or published on the `web` branch.

H24-01 delivers only the pure probe, fixtures, and documentation. The C29 and
C31 joins above remain with their designated composition surfaces. There is no
production registration, live dispatch, installed service, credential action,
merge, formal approval, or production-serving claim in this packet. A real
installed producer-consumer proof remains outside its source-only acceptance.
