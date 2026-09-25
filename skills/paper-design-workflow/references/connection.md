# Connection contract

Paper has one guarded adapter and multiple lawful clients. Carrier choice changes how the session
reaches that adapter; it does not create a second Paper auth, lifecycle, retry, or ownership plane.

## ChatGPT Web — Studio Direct preferred

For ChatGPT Web, first inspect the current effective tool surface for the Paper action family itself.
When a connected Studio Direct seat advertises `paper_inspect`, `paper_catalog`, `paper_read`
and `paper_edit`, call those gateway-owned tools directly. Use `paper_prepare` when it is actually
exposed and an exact file transition is needed. Generic Studio filesystem/process actions are not
evidence that Paper actions are missing.

The gateway pins the local Python interpreter, bridge path, bridge SHA and Paper app. A Web caller
cannot choose an arbitrary host path, Paper endpoint, account, credential or application. A missing
`paper_prepare` action is action-specific surface degradation; it does not by itself invalidate
current-file inspect/read/edit capability.

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
4. no Paper mutation on another carrier is STARTed, pending, or `EFFECT_UNKNOWN`; and
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
    {"studio_state":"ACTION_ABSENT_OR_UNSERVICEABLE","rdc_independently_authorized":true,"effect_state":"NONE","decision":"RDC_ELIGIBLE_PRE_EFFECT"},
    {"studio_state":"ACTION_ABSENT_OR_UNSERVICEABLE","rdc_independently_authorized":false,"effect_state":"NONE","decision":"BLOCK_EXACT_CARRIER_GATE"}
  ]
}
```
<!-- PAPER_CARRIER_DECISION_V1_END -->

Evaluate the matrix top-to-bottom. `ANY` is a wildcard. `EFFECT_UNKNOWN` therefore blocks before
all carrier-selection logic, and `EXPLICIT_DENIAL` blocks regardless of RDC authorization. If no
row matches, `default_decision` applies and fails closed; an unrecognized future state never becomes
implicit fallback authority.


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

If a different Paper file must be focused, prefer Studio Direct's bounded `paper_prepare` when
available. Do not synthesize an arbitrary host/application transition from memory. If the current
surface lacks a reviewed file-transition action, keep that as the exact blocker or use a separately
authorized current source-law path; do not broaden the bridge's raw `open_file` capability.

## Mutation and fallback fence

A pre-dispatch technical absence with proven `EFFECT_NONE` may justify choosing another carrier
before the first Paper edit **only when that carrier is independently authorized under the predicates
above**. Technical absence does not grant that authorization. An explicit safety/permission denial
never permits fallback. After any Paper edit dispatch, the logical mutation remains on that carrier
until its post-read/effect is reconciled.
A timeout or lost response is `EFFECT_UNKNOWN`; do not replay through Desktop Commander, Studio
Direct, another mode, account or provider.

Read-only diagnosis through the other carrier does not grant it write authority and must not be used
to hide an unresolved original effect.

## Native MCP

Native MCP requires an approved project configuration pointing to the installed `mcp_server.py`, a
dedicated Python environment with the pinned SDK, and Paper Desktop on the intended file. The guarded
adapter can be read-only or write-capable. Clients control their approval prompts and workspace trust.
Use `paper_inspect`, `paper_catalog`, `paper_read`, `paper_prepare` and `paper_edit` only
when those actions are actually exposed and approved.

Do not enroll a second dedicated Paper ChatGPT app, public-tunnel `127.0.0.1:29979`, build a new
auth service, or hide mutations behind read-only declarations. Seat enrollment and tunnel publication
remain Studio Direct's existing account/admin ceremony.

The full source/acceptance contract is `docs/PAPER_DESIGN_INTEGRATION.md`. Re-read current protected
procedure before modifying work.
