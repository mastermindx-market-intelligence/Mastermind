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

## Remote Desktop Commander — same bridge, bounded fallback

Remote Desktop Commander is an authorized fallback when the intended host is explicitly available
and the Studio Direct Paper family is technically absent or unserviceable before any Paper mutation.
It is also valid for host diagnosis and installation. It is **not** another Paper gateway.

Never choose a runtime by directory recency, a remembered `vN`, or an old `INSTALLATION.json`.
At the same protected repository commit used for the task, read
`integrations/studio_direct_mcp/private_service.py` and obtain the current
`PAPER_RUNTIME_REL`, `PAPER_RUNTIME_SCHEMA`, and `PAPER_BRIDGE_SHA256` pins. On the target host:

1. read `~/<PAPER_RUNTIME_REL>/RUNTIME.json`;
2. verify the receipt schema/generation and its `bridge_sha256` / `source_sha256.bridge.py`;
3. hash the exact `source/bridge.py` and require the protected SHA match;
4. use the receipt's exact `python_source` when present and valid;
5. run the bridge's `status`, then `catalog`, before any edit;
6. confirm the exact Paper file identity again immediately before a modifying call.

Conceptual command shapes — values come only from the verified current receipt/source pin:

```sh
"$PYTHON" "$BRIDGE" status
"$PYTHON" "$BRIDGE" catalog
"$PYTHON" "$BRIDGE" read --tool get_screenshot --arguments @/owned/args.json --artifact-dir /owned/private-artifacts
"$PYTHON" "$BRIDGE" edit --allow-write --tool write_html --arguments @/owned/args.json --expected-snapshot <observed-sha256> --operation-id <same-operation-id>
```

Use Desktop Commander's `start_process` with those exact verified values. Keep returned image
artifacts on that same device. `catalog` is the live upstream schema owner; never guess Paper tool
arguments. An unavailable endpoint is not proof of logged-out status.

If a different Paper file must be focused, prefer Studio Direct's bounded `paper_prepare` when
available. Do not synthesize an arbitrary host/application transition from memory. If the current
surface lacks a reviewed file-transition action, keep that as the exact blocker or use a separately
authorized current source-law path; do not broaden the bridge's raw `open_file` capability.

## Mutation and fallback fence

A pre-dispatch technical absence with proven `EFFECT_NONE` may justify choosing the other lawful
carrier before the first Paper edit. An explicit safety/permission denial never does. After any Paper
edit dispatch, the logical mutation remains on that carrier until its post-read/effect is reconciled.
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
