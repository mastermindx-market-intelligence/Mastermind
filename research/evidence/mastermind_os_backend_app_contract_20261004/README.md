# Mastermind OS backend / app contract qualification — 2026-10-04

## Outcome and scope

This contribution adds an optional original work reference to strict-v2 CEO intent receipts and qualifies the authenticated launch/recovery path used by the Mastermind OS launch controller.

Operation: `mastermind-os-backend-app-contract-20261004-astra-001`. Protected implementation base: `03f7ca04cd5b0a3abf7166221dd77d403c7f95df`. Consumer source: [#1150](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1150), frozen at `37d02586eeb97d92e6fb9ed6dbc7cd142dd6449c`.

The backend source change is implemented in this contribution. The V3 consumer compatibility change is a **proposed, unadopted patch**, applied only to disposable copies of the frozen consumer for qualification. No incumbent app source, installed service, credential, worker, or production Runtime was modified. This is component evidence, not a backend-completion or installed-acceptance certificate.

## Receipt contract

`mastermind.ceo_intent_receipt.v2` may now contain `work_ref` when its original strict-v2 intent supplied a valid `workstream`.

- The first accepted receipt uses the original validated intent after the existing durable Job write.
- Duplicate and status receipts reconstruct the value from the original durable `JOB_CREATED.payload.provenance.workstream`, using the existing workstream grammar and length constraint.
- A legacy v2 record without that field omits it. A present malformed durable field fails validation.
- Current UI configuration does not replace or relabel the original reference. A conflicting payload under the same intent identity remains a conflict and creates no additional Job.
- v1, service, and principal receipt families retain their existing shapes and behavior.
- There is no new registry, query plane, identity source, authority grant, dispatch path, or Job owner.

The reference describes the original workstream provenance. It does **not** prove that a Program/Workspace association currently exists or that work has started or completed.

Section 14.3 of [the frozen command-binding specification](../../MASTERMIND_OS_COMMAND_BINDING_SPEC_V1.md) proposed a receipt-v3 field. This contribution takes the narrower compatible approach: the optional field is added to the already extensible receipt-v2 shape. Existing consumers accept v1/v2 and a new global receipt-v3 discriminator would exceed their declared contract. The frozen #1150 consumer still selects the original workstream from its persisted operation pointer; this contribution does not change that selection policy.

## Real backend journey

`tests/test_executive_mcp_launch_journey.py` covers eight combinations:

| Dimension | Values |
|---|---|
| Public MCP profile | web_ceo_v2, web_ceo_v3 |
| Service admission | Generic receipt-v1, strict receipt-v2 |
| Submit delivery | Accepted reply, reply lost after durable acceptance |

Each case uses a genuinely signed temporary RS256 token, the real MCP ASGI application, a temporary Unix proxy and control-service socket, actual temporary Git grounding, and a disposable SQLite Runtime.

The strict-v2 cases supply the host dialogue-source provider with the fixture's real Git commit and tracked README content digest. Terminal-return arming remains false and the supervisor cannot execute. The host source is deliberately made unavailable after admission; a newly created MCP app still resolves the original intent from durable state.

The assertions establish:

1. A read-only token cannot submit. A foreign signed subject is rejected before any socket frame or Job creation.
2. Exactly one submit frame reaches Runtime and exactly one queued root is created.
3. Accepted, backend, durable, and recovered strict-v2 receipts contain the original work reference. Generic v1 receipts omit it.
4. Lost-reply recovery uses the original derived intent ID and a status read, without resubmission or fresh source admission.
5. Every case ends with zero attempts and zero workers; source provenance remains unchanged.

The RSA issuer, principal/generation, pointer store, source provider, and backend database are disposable fixtures. This does not establish installed OAuth composition, installed persistent storage, public-host delivery, worker/provider execution, or actual Mission presentation.

## Frozen consumer integration and V3 gap

The manual cross-layer probe reads five exact Git objects, records their hashes, bundles the actual #1150 port/controller, and forwards its actual generated tool calls through the real backend journey above. Backend envelopes are passed unchanged into the actual TypeScript consumer. No synthetic success envelope substitutes for the positive path.

Unmodified #1150 results:

| Profile | Accepted reply | Lost reply / status recovery |
|---|---|---|
| V2, server 1.2.0 | Accepted in both receipt modes | Accepted in both receipt modes |
| V3, source server 1.4.0 | Accepted in both receipt modes | **Unknown in both receipt modes** |

The baseline records six successes and two compatibility failures. It exits 1 while preserving the observed results. V3's status receipt identifies the correct durable Job, but the frozen consumer's closed E1 validator accepts only server 1.2.0. The pending pointer remains present, so a duplicate submit stays blocked.

This is a compatibility gap when pairing current V3 source with the V2-scoped #1150 consumer. It does not invalidate #1150's declared V2-only acceptance.

The proposed patch changes only the E1 version check to an explicit set containing **1.2.0 and 1.4.0**. All schema, tool, mode, key-set, error, JSON, intent, and receipt guards remain unchanged.

With that patch applied only to the temporary snapshot:

- All eight real consumer/backend journeys pass.
- All 52 negative controls pass: 13 per recovered profile/receipt-mode combination.
- Negative controls reject unsupported versions, non-string versions, extra envelope fields, a foreign tool, wrong mode, foreign intent identity, malformed degradation data, and an unsupported receipt schema.
- Every rejected status leaves the exact pending pointer intact and issues no second submit.
- Changing the current UI workstream before recovery does not alter the original mission selection.

The observed installed Executive version **1.3.1 is deliberately unqualified and remains unsupported by this proposed patch**. This contribution has not reproduced that installed producer's exact closed response contract. Version adjacency is not compatibility evidence.

## Evidence and reproduction

Committed reports:

- [Unmodified consumer baseline](cross-layer-baseline.json)
- [Proposed V3 patch qualification](cross-layer-v3-patch.json)
- [Verification record](verification.json)
- [Proposed consumer patch](../../../tests/fixtures/mastermind_os_v3_recovery_compat.patch)

The JSON reports record the original five-file source manifest, consumer commit, actual producer-envelope digests, receipt schemas/work references, observed UI states, Job/attempt/worker counts, and negative controls. The patched report also records the exact patch and modified-source hashes.

The consumer commit must be available as a Git object. On a new checkout, fetch that exact object from the existing origin before running the probe. No checkout or worktree switch is required.

```bash
npm ci --prefix app/mastermind_os --include=dev --ignore-scripts

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
  tests/fixtures/mastermind_os_launch_cross_layer_probe.py \
  --consumer-ref 37d02586eeb97d92e6fb9ed6dbc7cd142dd6449c \
  --output /tmp/mastermind-os-baseline.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
  tests/fixtures/mastermind_os_launch_cross_layer_probe.py \
  --consumer-ref 37d02586eeb97d92e6fb9ed6dbc7cd142dd6449c \
  --consumer-patch tests/fixtures/mastermind_os_v3_recovery_compat.patch \
  --output /tmp/mastermind-os-v3-patch.json
```

The baseline is expected to exit 1 for the two recorded V3 recovery failures; the proposed patch run exits 0. Python requires the repository's declared test/MCP dependencies. This qualification used task-local Python 3.14.7, Node 26.5.0, MCP 1.28.1, and PyJWT 2.13.0. The protected CI environment uses Python 3.12 and Node 22.14.0 and remains a separate release gate.

The relevant nine-module regression run collected 609 tests: 608 passed and one pre-existing synthetic credential fixture failed because its default temporary tree inherited GID 0 while the process expected GID 20. The credential source and test were byte-identical to protected base. Rerunning that exact test under a new task-local GID-20 temporary parent passed (1/1). No source or credential check was changed. The separate principal-intent module passed 47/47. These are separate executed runs, not one combined green invocation.

## Integration and remaining acceptance

Parent backend carrier: [#600](https://github.com/mastermindx-market-intelligence/Mastermind/pull/600). This engineering evidence does not transfer any incumbent's source or effect custody.

| Remaining edge | Existing carrier / obligation |
|---|---|
| Receipt source adoption | This contribution needs exact-head review and protected CI before merge; installed adoption follows its own release gate. |
| App command host and authenticated owner generation | [#1046](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1046) and stacked [#1150](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1150). The factory exists but the actual app host composition and original Mission acceptance remain owed. The proposed patch must be adopted and reviewed by that source owner. |
| Installed V3 response compatibility | Reproduce the exact installed 1.3.1 producer and qualify its response contract, or release an already-qualified producer through the authorized installed-service path. Neither action is performed here. |
| Authenticated STOP and message-turn producer | Existing Executive/COO control owner; the command specification's stop/message gaps are not closed by a launch receipt change. |
| Full execution, terminal accounting, review/aggregation, and shutdown | [#1041](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1041) and its existing Runtime owner. Historical R133 review restrictions remain intact. |
| Safe resolution of sticky unknown/not-found operations | A canonical terminal no-effect settlement remains a backend obligation. Client-side deletion or automatic resubmission is not introduced. |
| Public installation and production proof | Existing Product/Runtime owners retain installation, credential, service and first-root custody, including unresolved I1-C acceptance. |

The next integration sequence is: review and merge the receipt change; adopt the proposed consumer version delta within the held app carrier; compose the actual authenticated command host; qualify the installed producer; and complete the existing execution/control and original Mission acceptance gates. Green component tests do not close those gates.
