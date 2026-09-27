# Connection contract

Paper has one guarded adapter and multiple lawful clients. Carrier choice changes how the session
reaches that adapter; it does not create a second Paper auth, lifecycle, retry, or ownership plane.

## Business direct Web route — staged, enrollment separate

The private **Mastermind Paper** app is the normal Business Paper route after explicit enrollment
and accepted direct-path scratch-file proof. Its path is Secure MCP Tunnel -> guarded stdio
`mcp_server.py` -> the same `bridge.py` -> Paper loopback. It has no generic workstation tools.
`direct_service.py` stages and verifies this deployment; `docs/PAPER_DIRECT_CHATGPT.md` owns its
operator procedure. Use one existing tunnel, not a replacement for the Chairman-created tunnel.

The previous blanket rule against a dedicated Paper ChatGPT app is superseded for this explicitly
commissioned Business migration. It does not authorize unattended enrollment or publication.
The direct build supports explicit-file target binding through `paper_prepare`: Paper 0.5.12 can
read/write an addressed file by `fileId` while another file remains user-active, so direct prepare
validates the target and returns its snapshot without using raw `open_file` as a focus surrogate.
Retain one carrier per logical modifying operation, no fallback after a denial, and original-carrier
reconciliation of EFFECT_UNKNOWN. This carrier fence is not a file-wide ownership lease. Source/config/
stdio proof is not a working ChatGPT app or accepted cutover.

The ChatGPT app's approved action snapshot may lag an accepted runtime/source revision. When exact
source/runtime now declares `MULTI_WRITER_PER_FILE_TARGET_SCOPED` but the current app tool
description still says one designer/exclusive ownership or describes prepare as active-file focus,
classify **DIRECT_TOOL_PUBLICATION_DRIFT / EFFECT_NONE**. Keep the same app/tunnel identity and
refresh/recreate that app's approved action snapshot through its normal attended admin ceremony
after the accepted runtime is deployed. Do not create a second Paper plane, infer a file lease from
stale metadata, or use publication drift to bypass a denial or unresolved effect.

For multi-seat Business rollout, each ChatGPT seat may have its own exact tunnel-client transport,
seat-specific launchd label and transport singleton. All such transports reuse the same stdio server
implementation/bridge contract and the same host-global Paper `desktop.lock`; do not create a Paper
account, bridge, auth plane, retry queue or raw-port listener per ChatGPT account. A seat-aware v3
binding may omit a backend workspace ID when it is not independently observable; never fabricate one.
The OpenAI-side tunnel/workspace association remains authoritative and must be completed in that
account's attended app setup. Multiple admitted sessions/hosts may modify the same exact `fileId`,
including the same page. Coordinate by board/artboard/node target: prefer disjoint boards, and when
same-board work overlaps, partition node targets and re-read/re-plan the next operation. The host-global
`desktop.lock` is only a local bridge-call mutex, never a distributed document or page lease.

The Studio/RDC selection matrix below applies only to legacy/non-migrated seats. Do not apply it
to evade a direct-app denial or unknown effect. At accepted Business cutover, Studio Direct's
primary Paper-Web requirement is retired for that workspace; other Studio host capabilities and
non-migrated seats are not silently removed. There is one primary route per accepted workspace.

## Legacy/non-migrated ChatGPT Web — Studio Direct preferred

For ChatGPT Web, first inspect the current effective tool surface for the Paper action family itself.
When a connected Studio Direct seat advertises `paper_inspect`, `paper_catalog`, `paper_read`
and `paper_edit`, call those gateway-owned tools directly. Use `paper_prepare` when it is actually
exposed and an exact file transition is needed. Generic Studio filesystem/process actions are not
evidence that Paper actions are missing.

The gateway pins the local Python interpreter, bridge path, bridge SHA and Paper app. A Web caller
cannot choose an arbitrary host path, Paper endpoint, account, credential or application.
`paper_inspect` returns a fail-closed `gateway_surface` contract naming the exact Paper tools the
gateway advertises. If that contract includes `paper_prepare` while the current ChatGPT tool surface
does not, the state is `STUDIO_TOOL_PUBLICATION_DRIFT / EFFECT_NONE`: current-file inspect/read/edit
may remain usable, but another-file transition is held until the **same Studio Direct app's
approved action snapshot** is brought current and `paper_prepare` is directly surfaced. ChatGPT does
not auto-apply MCP tool changes after workspace approval. Current OpenAI Business behavior also does
not support updating a published app in place: recreate + republish is required; draft/dev apps use
their tool scan/recreation flow. Never reproduce the transition with generic Studio process/filesystem
actions, Desktop Commander, raw `open_file`, shell, or UI automation. After the workspace action
snapshot is current, start a fresh chat/tool selection, call `paper_inspect` again, then the direct
`paper_prepare(file_id)`, then inspect once more before the first edit.

## Remote Desktop Commander — same bridge, independently authorized alternative

Remote Desktop Commander can reach the same guarded Paper bridge, but Studio Direct absence never
grants authority to use it. Before selecting RDC for a Paper modifying action, establish
`INDEPENDENT_RDC_AUTHORIZATION` from existing owners; do not create a new grant or registry.

`INDEPENDENT_RDC_AUTHORIZATION` means **all** of the following are already true:

1. current live Chairman intent/delegated authority or accepted canonical placement covers the exact
   Paper task **and** the exact target host carrier;
2. the current session directly observes RDC access/resource permission for that exact host;
3. no explicit provider, Studio Direct, Paper, workspace, account, safety, or organizational denial
   applies to the intended effect;
4. no conflicting mutation for the same logical operation/target on another carrier is STARTed,
   pending, or `EFFECT_UNKNOWN`; disjoint target mutations in the same file/page do not block; and
5. current same-pinned source procedure, document identity, source custody, and action-specific write
   gates are satisfied.

A missing/unserviceable Studio action is only capability evidence. It satisfies none of these
authorization predicates. If independent RDC authorization cannot be established, stop at the exact
carrier/permission gate instead of using host access as a substitute for permission.

<!-- PAPER_CARRIER_DECISION_V1_START -->
```json
{
  "schema": "mastermind.paper_carrier_decision.v1",
  "match_semantics": "FIRST_MATCH_WITH_ANY_WILDCARD",
  "default_decision": "BLOCK_UNRECOGNIZED_STATE",
  "cases": [
    {"studio_state":"ANY","rdc_independently_authorized":"ANY","effect_state":"EFFECT_UNKNOWN","decision":"BLOCK_RECONCILE_ORIGINAL_CARRIER"},
    {"studio_state":"EXPLICIT_DENIAL","rdc_independently_authorized":"ANY","effect_state":"NONE","decision":"BLOCK_NO_FALLBACK"},
    {"studio_state":"PAPER_ACTION_AVAILABLE","rdc_independently_authorized":"ANY","effect_state":"NONE","decision":"USE_STUDIO"},
    {"studio_state":"SURFACE_DRIFT_ADVERTISED","rdc_independently_authorized":"ANY","effect_state":"NONE","decision":"REPAIR_SAME_STUDIO_PUBLICATION"},
    {"studio_state":"ACTION_ABSENT_OR_UNSERVICEABLE","rdc_independently_authorized":true,"effect_state":"NONE","decision":"RDC_ELIGIBLE_PRE_EFFECT"},
    {"studio_state":"ACTION_ABSENT_OR_UNSERVICEABLE","rdc_independently_authorized":false,"effect_state":"NONE","decision":"BLOCK_EXACT_CARRIER_GATE"}
  ]
}
```
<!-- PAPER_CARRIER_DECISION_V1_END -->

Evaluate the matrix top-to-bottom. `ANY` is a wildcard. Here `effect_state` is scoped to the
logical mutation/target being selected, not every other edit in the same Paper file. `EFFECT_UNKNOWN`
for that operation therefore blocks before all carrier-selection logic, and `EXPLICIT_DENIAL` blocks
regardless of RDC authorization. If no row matches, `default_decision` applies and fails closed; an
unrecognized future state never becomes implicit fallback authority.


RDC remains valid for authorized host diagnosis/installation even when it is not authorized to edit
Paper. It is **not** another Paper gateway.

Never choose a runtime by directory recency, a remembered `vN`, or an old `INSTALLATION.json`.
At the same protected repository commit used for the task, read
`integrations/studio_direct_mcp/private_service.py`. Treat its current
`_verify_paper_runtime()`, `PAPER_RUNTIME_REL`, `PAPER_RUNTIME_SCHEMA`, and
`PAPER_BRIDGE_SHA256` as the fail-closed runtime owner. On the target host:

1. resolve `RUNTIME = $HOME / PAPER_RUNTIME_REL` and read `RUNTIME/RUNTIME.json`;
2. require receipt `schema == PAPER_RUNTIME_SCHEMA`;
3. require receipt `generation == Path(PAPER_RUNTIME_REL).name`;
4. require receipt `bridge_sha256 == PAPER_BRIDGE_SHA256` and
   `source_sha256 == {"bridge.py": PAPER_BRIDGE_SHA256}`;
5. require `network_install_performed is false` and `production_acceptance is false`;
6. require the runtime/source directories and bridge/receipt files to satisfy the same owner,
   private-mode, regular-file, and non-symlink predicates as `_verify_paper_runtime()`;
7. hash `RUNTIME/source/bridge.py` and require `PAPER_BRIDGE_SHA256`;
8. use only `RUNTIME/venv/bin/python`, requiring a regular non-symlink executable. The receipt's
   `python_source` is staging provenance only and is never runtime interpreter selection;
9. run the bridge's `status`, then `catalog`, before any edit; and
10. confirm the exact Paper file identity again immediately before a modifying call.

Conceptual command shapes — values come only from those same-pinned protected predicates:

```sh
"$RUNTIME/venv/bin/python" "$RUNTIME/source/bridge.py" status
"$RUNTIME/venv/bin/python" "$RUNTIME/source/bridge.py" catalog
"$RUNTIME/venv/bin/python" "$RUNTIME/source/bridge.py" read --tool get_screenshot --arguments @/owned/args.json --artifact-dir /owned/private-artifacts
"$RUNTIME/venv/bin/python" "$RUNTIME/source/bridge.py" edit --allow-write --tool write_html --arguments @/owned/args.json --expected-snapshot <observed-sha256> --operation-id <same-operation-id>
```

Use Desktop Commander's `start_process` only after the independent authorization and exact runtime
checks above. Keep returned image artifacts on that same device. `catalog` is the live upstream
schema owner; never guess Paper tool arguments. An unavailable endpoint is not proof of logged-out
status.

If a different Paper file must be focused, use Studio Direct's bounded `paper_prepare`. If
`paper_inspect.gateway_surface` says that action is part of the gateway contract but the current
client surface omitted it, repair/refresh that same Studio publication first; generic Studio host
commands are not a substitute for the missing action. If the refreshed current surface still lacks
a reviewed file-transition action, keep that as the exact blocker or use only a separately authorized
current source-law path; never broaden the bridge's raw `open_file` capability.

## Mutation and fallback fence

A pre-dispatch technical absence with proven `EFFECT_NONE` may justify choosing another carrier
before the first Paper edit **only when that carrier is independently authorized under the predicates
above**. Technical absence does not grant that authorization. An explicit safety/permission denial
never permits fallback. After any Paper edit dispatch, the logical mutation remains on that carrier until its post-read/effect
is reconciled. This is an operation/target fence, not a file-wide or page-wide lease; disjoint admitted
writers may continue in the same file. A timeout or lost response is `EFFECT_UNKNOWN`; do not replay through Desktop Commander,
Studio Direct, another mode, account or provider.

Read-only diagnosis through the other carrier does not grant it write authority and must not be used
to hide an unresolved original effect.

## Native MCP

Native MCP requires an approved project configuration pointing to the installed `mcp_server.py`, a
dedicated Python environment with the pinned SDK, and Paper Desktop on the intended file. The guarded
adapter can be read-only or write-capable. Clients control their approval prompts and workspace trust.
Use `paper_inspect`, `paper_catalog`, `paper_read`, `paper_prepare` and `paper_edit` only
when those actions are actually exposed and approved.

Do not public-tunnel `127.0.0.1:29979`, build a new auth service, or hide mutations behind read-only
declarations. The commissioned Business migration may enroll one private Mastermind Paper app at
the final attended setup boundary. Account/admin ceremony is still required; a staged bundle,
model-mode change, or direct tool discovery never grants permission or transfers an unknown effect.

The full source/acceptance contract is `docs/PAPER_DESIGN_INTEGRATION.md`. Re-read current protected
procedure before modifying work.
