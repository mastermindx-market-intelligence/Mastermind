# Connection contract

Native MCP requires a current approved project configuration pointing to the
installed `mcp_server.py`, a dedicated Python environment with the pinned SDK,
and Paper Desktop open on the intended file. The guarded adapter can be read-only
or write-capable. Clients control their actual approval prompts and workspace trust.

For ChatGPT Web, the normal path is the existing **Studio Direct** private MCP
tunnel. When the connected seat advertises `paper_prepare`, `paper_inspect`, `paper_catalog`,
`paper_read` and `paper_edit`, call those gateway-owned tools directly. The
gateway pins the local Python interpreter, bridge path and bridge SHA. `paper_prepare`
uses the host-qualified `~/Applications/Paper.app` and accepts only an exact Paper
file ID; the Web caller cannot select an application path, arbitrary URL, Paper
endpoint, account or credential.

Remote Desktop Commander is retained for authorized host diagnosis and installation,
or for an explicitly assigned legacy session. If that carrier is used, call its
`start_process` with the exact installed CLI path and keep any returned image
artifact on that same device. Do not treat RDC as another Paper auth/gateway plane.

Command shapes (replace the path only from the actual installation receipt):

```sh
python3 /verified/install/runtime/bridge.py status
python3 /verified/install/runtime/bridge.py catalog
python3 /verified/install/runtime/bridge.py read --tool get_screenshot --arguments @/owned/args.json --artifact-dir /owned/private-artifacts
python3 /verified/install/runtime/bridge.py edit --allow-write --tool write_html --arguments @/owned/args.json --expected-snapshot <observed-sha256> --operation-id <same-operation-id>
```

Do not use these examples to guess upstream arguments or a device path. `catalog`
is the live schema owner. CLI `status` returns `CONNECTED` only after initialization
and document inspection; an unavailable endpoint is not proof of logged-out status.

The installed ChatGPT app path is Studio Direct: its existing Secure MCP Tunnel
fronts the guarded gateway, and the gateway owns the normalized Paper tools. Do not
enroll a second dedicated Paper app, public-tunnel `127.0.0.1:29979`, build a new
auth service, or hide mutations behind read-only declarations. Seat enrollment and
tunnel publication remain Studio Direct's existing account/admin ceremony.

The full source/acceptance contract is `docs/PAPER_DESIGN_INTEGRATION.md` in the
Mastermind candidate. Re-read current protected procedure before modifying work.
