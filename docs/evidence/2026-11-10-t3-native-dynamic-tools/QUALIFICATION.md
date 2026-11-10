# Native Codex dynamic-tool typed bindings

## Result and scope

A three-file source patch fixes a reproduced protocol defect in `chriswong6031-creator/t3code@924ad5d194287441f825b8f2f6054e9539808534`: the existing typed client silently removed `dynamicTools` from an outgoing `thread/start` request. The patch restores only this supported experimental input through the incumbent schema generator and tests the real client encoder and incoming dynamic-call decoder over its existing in-memory stdio transport.

This is source qualification. It does not advertise a production host tool, register a provider callback in `CodexAdapterV2`, dispatch Executive work, attest a native requester, launch a provider/model/session, modify an installed app/profile, or publish a fork ref. The two inspected publication identities remain pull-only. The existing API-principal COO route can proceed under its own authenticated requester/acknowledgment family independently.

## Why the field is supported

Official Codex `rust-v0.167.0` source pin: `086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`.

| Source owner | Exact finding |
|---|---|
| [ThreadStartParams](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/app-server-protocol/src/protocol/v2/thread.rs), blob `aba591b9502774ba018aac144fe94c8041a6ba18` | `dynamic_tools: Option<Vec<DynamicToolSpec>>` is marked `#[experimental("thread/start.dynamicTools")]` and uses the native `deserialize_dynamic_tool_specs` implementation. |
| [Schema export](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/app-server-protocol/src/export.rs), blob `6f51edce88aadd7a9ccbe77ab61da308e220831d` | Stable export filters registered experimental properties out of root and nested schemas. This does not establish that their supporting type definitions or runtime implementations are absent. |
| [Precomputed export owner](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/app-server-protocol/src/precomputed_exports.rs), blob `51af299a4620a5be7c7d4b1d524ad9acfc7f06b3` | Stable and experimental bundles are separate; the default is stable. |
| [Initialize processor](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/app-server/src/request_processors/initialize_processor.rs), blob `f6b282e7e107b4bfed3604b22cb2b372885c212b` | The connection retains `capabilities.experimental_api`. |
| [Request gate](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/app-server/src/message_processor.rs), blob `c234acbc8b2a9e6cafaf1d88c433ee648ebcd49a` | Experimental request usage is refused unless that initialized connection opted in. |
| [T3 Codex adapter](https://github.com/chriswong6031-creator/t3code/blob/924ad5d194287441f825b8f2f6054e9539808534/apps/server/src/orchestration-v2/Adapters/CodexAdapterV2.ts), blob `831b240d8bba215e9bf1f5b3c35e896b144628b0` | `CODEX_CLIENT_CAPABILITIES.experimentalApi` is already `true`, the actual initialize request supplies it, and `ensureThread` awaits that initialization before `thread/start`. Source-requested negotiation is not a live connection receipt. |

## Canonical versus legacy specification compatibility

The generator's upstream pin remains `687a119f0fcaace47e1f1abcc77cec6c813fd6da`. Its `schema/json/v2/ThreadStartParams.json` blob `5164caf6a208e4e0aa1d21baff108df8430c9d54` already contains the canonical DynamicToolSpec and DynamicToolNamespaceTool definitions. Their shape was compared directly with official 0.167 [dynamic_tools.rs](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/protocol/src/dynamic_tools.rs), blob `bbe92b8fe0c75802cc1784d900926612b170a6b5`:

| Form | Pinned typed schema and official serde behavior |
|---|---|
| Function | Tagged `type: "function"`; required `name`, `description`, `inputSchema`; optional boolean `deferLoading`. Official serde defaults its omission to `false`. |
| Namespace | Tagged `type: "namespace"`; required `name`, `description`, `tools`. Children are tagged functions with the same function fields. |
| Nullable field | The added optional `dynamicTools` accepts an array or `null`, matching `Option<Vec<DynamicToolSpec>>`. |
| Legacy flat tools | Official normalization additionally accepts a consistently legacy array, including old `namespace` and `exposeToContext` fields. This patch does not add a legacy typed form. |
| Mixed legacy/canonical tools | Official normalization rejects a mixture, including legacy fields inside otherwise canonical namespace tools. No conversion or compatibility claim for such mixtures is added. |

This is source-level deserializer compatibility, not execution of native Rust tests or proof that every possible tool name/schema passes later backend validation. The wire regression covers a canonical top-level function and a canonical namespace with a deferred function. No real native backend/model was invoked.

## Exact implementation and generated scope

`packages/effect-codex-app-server/scripts/generate.ts` restores the one experimental property for `ThreadStartParams` before the generator rewrites references. It applies to the standalone type and its nested ClientRequest representation, preserves a future upstream definition if already present, and retains the existing pinned stable schema baseline. No raw-client bypass or broad experimental-schema switch was added.

The incumbent `node scripts/generate.ts` completed successfully. The emitted schema contains 2,328 declarations before and after, with none added or removed. Only four declaration bodies differ: the two ThreadStartParams representations gain the optional input; their two existing DynamicToolSpec declarations receive generator reference annotations. Required dependency ordering changes are emitted by the generator. The schema file is kept exactly as generated, including its generated-source header.

The generator also emitted its normal three-line headers into `meta.gen.ts` and `namespaces.gen.ts`. Those files had no semantic changes and were restored byte-for-byte to the original source pin to keep them outside the patch. No generated type was hand-edited.

The focused test in `src/client.test.ts` sends `thread/start` through the actual typed encoder, observes its stdio frame, and proves both canonical forms survive. A deliberate peer error ends that fixture request without starting a native thread. It then uses the actual existing `item/tool/call` handler decoder to preserve opaque native thread/turn/call IDs, return the original RPC request ID, and reject a malformed callback lacking `callId` before the handler is called. Its synthetic handler returns a refusal and makes no Control call.

## Executed checks

Commands were run from `source/packages/effect-codex-app-server` in the isolated checkout, using the pinned dependency versions and incumbent `@effect/vitest` patch. Local Node was `v24.22.1`; the repository declares Node `26.12.1`, so this is not an exact installed-host build qualification.

- Before the generator change, the new actual wire regression failed: outgoing `request.params.dynamicTools` was `undefined`. The focused command used `-t 'preserves experimental host tools'` and exited 1. Namespace coverage was then added to that same test for the compatibility check.
- `../../node_modules/.bin/vp test run --config ../../vite.config.ts src/client.test.ts src/schema.test.ts`: **10 passed**, 2 files, 2.83 seconds on the final test source.
- `../../node_modules/.bin/effect-tsgo tsrs --noEmit`: **exit 0**. It reports existing missing-brand suggestions in the unchanged error classes; no typecheck error.
- `../../node_modules/.bin/vp lint scripts/generate.ts src/client.test.ts --report-unused-disable-directives`: **exit 0**.
- `vp fmt` on the two edited source/test files and `git diff --check`: **exit 0**.
- The frozen patch is reapplied to exact original file bytes and all resulting SHA256 values are compared with the source manifest.

Retained actual logs are under `.qualification-logs/`. The source manifest records all changed files, original Git blobs, final SHA256 values, patch SHA256 and application verification.

## Held next integration

The next provider composition must capture the existing qualified Control connection, advertise only its fixed supported tools through this typed path, and handle `item/tool/call` against the exact active native turn/thread context and opaque call ID. It must not adopt a latest/settled turn or a new connection on retry. Original selected-child command/target and canonical Runtime/WorkerBroker result owners remain authoritative.

Current observed Control enrollment authenticates the COO API principal, installed mission/profile and Unix App peer. That does not attest a native T3 provider call. Ordinary caller `_meta` cannot acquire native authority. Therefore no Executive-dispatch tool or native-origin envelope was composed in this patch. Once the existing enrolled-source/connection owner supplies that authority, qualify the actual callback → captured MCP owner → authenticated ingress → original selected child → WorkerBroker/result/return path, with forged, foreign, settled, revoked, conflicting and lost-response cases. Source publication and any later isolated/runtime activation remain separate actions under the existing holds.
