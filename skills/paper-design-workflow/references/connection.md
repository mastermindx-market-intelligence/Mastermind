# Connection contract

Native MCP requires a current approved project configuration pointing to the
installed `mcp_server.py`, a dedicated Python environment with the pinned SDK,
and Paper Desktop open on the intended file. The guarded adapter can be read-only
or write-capable. Clients control their actual approval prompts and workspace trust.

For ChatGPT Web, use the existing Remote Desktop Commander connector. Call its
`start_process` with the exact installed CLI path, using shell-quoted JSON or an
owned bounded JSON argument file. Read generated images with `read_file` on the
same device, not from ChatGPT's sandbox.

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

A dedicated ChatGPT app is optional: enroll the same stdio adapter through OpenAI's
Secure MCP Tunnel with the actual account/workspace gates. This skill does not install
an app, authenticate it, publish it to other accounts or grant write entitlements.
Do not public-tunnel `127.0.0.1:29979`, build a new auth service, or hide mutations
behind read-only declarations. Current official onboarding: `tunnel-client help quickstart`.

The full source/acceptance contract is `docs/PAPER_DESIGN_INTEGRATION.md` in the
Mastermind candidate. Re-read current protected procedure before modifying work.
