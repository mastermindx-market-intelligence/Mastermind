# Paper.design integration - bounded local and web design capability

## Mission and frozen boundary

Chairman direction, 2026-09-13: make Paper ready for local agents and ChatGPT Web,
without buying a plan. The useful end-state is brief -> editable Paper design ->
screenshot/review -> JSX -> integrated, browser-proven product, not merely an MCP entry.

Procedure source: Mastermind protected master
`9ed16bf0fcc5b47e870350ff2413ff5c8c73b447`, Sol Skillpack 1.0.1 / bootstrap 1.
Paper official plugin reference: `paper-design/agent-plugins` at
`f6d4f13343dd924fabaadd0898725f1b8718459d`.
No production lifecycle, queue, identity, credential or authentication store is added.
The only shared runtime file is a per-OS-user advisory mutex for the Paper desktop.
It is not an ownership lease, Job state, deduplication ledger or authorization token.

## Architecture

Local Claude/Codex/Cursor/OpenCode/VS Code client -> approved project-scoped MCP
configuration -> `mcp_server.py` (official MCP SDK, stdio) -> `bridge.py` ->
Paper's fixed loopback MCP `http://127.0.0.1:29979/mcp`.

ChatGPT Web -> existing authorized Remote Desktop Commander -> same `bridge.py`
CLI on the selected Mac -> same Paper endpoint. Images are saved to a private
artifact directory and read with Remote Desktop Commander's native image reader.
This uses the installed transport, not a second public gateway or new auth system.
It works only in sessions/accounts with that app, device authorization and tool permission.

Optional dedicated ChatGPT app -> official OpenAI Secure MCP Tunnel -> the SAME
stdio adapter. Enrollment is a separate admin/account action. Do not expose the
raw unauthenticated Paper port through a public tunnel, add another OAuth service,
or put design tools into Executive OS's bounded CEO-admission API.

No MCP tool is disguised as read-only to bypass client write permissions.
`paper_edit` is explicitly modifying/destructive/non-idempotent; it exists only
when the local server is started with `--allow-write`.

## Existing harness integration boundary

Protected `control_plane/executive_agent_capabilities.py` already owns named MCP,
skill and plugin grants, exact schemas and profile digests. Its default policy
`config/executive_agent_capabilities.json` currently has `production_armed:false`.
Sealed workers deliberately clear ambient MCP/plugins/skills. Adding a personal
MCP config does NOT enroll an Executive worker or grant a Job new powers.

This candidate stages actual client config files in a NEW isolated workspace:
`.mcp.json`, `.cursor/mcp.json`, `.codex/config.toml`, `.vscode/mcp.json`, and
`opencode.json`. Provider-account homes and running worker processes are untouched.
Qwen/MiniMax/GLM/Grok access follows the tools supported by their hosting harness;
a model subscription alone is not evidence of MCP execution support.

Next Executive integration is an additive reviewed stdio grant in the EXISTING
registry, bound to the exact installed runtime/SDK and observed adapter tool-schema
digest. Use the existing resource/placement owner for one active design operator
per Paper desktop. Do not loosen the current HTTPS validation to point the whole
fleet at localhost, invent a parallel policy file, auto-arm production, or fabricate
a schema digest before a real `initialize` + `tools/list` capture. This candidate
has NOT changed that registry and must not be described as routed-production-ready.

## Installation and user gates

The CLI requires Python 3.9+ and no packages. The optional MCP server requires
Python 3.10+ and `mcp==1.30.0`; use a dedicated virtual environment, not system pip.
The dependency pin intentionally stays on the documented maintenance-line SDK API.
Transitive dependency resolution must be captured/reviewed before an immutable
Executive grant. Current configuration staging is not such a sealed installation.

Run `install.py --destination <new-path> --python <venv-python> --allow-write` for a
dry run, then the same command with `--apply`. Existing destinations refuse rather
than overwrite. It creates runtime files, actual isolated project configurations,
and `INSTALLATION.json`. This receipt is installation evidence, not runtime authority.

Launch Paper, sign in through its normal UI, and open the intended design file.
No paid plan is needed for initial smoke proof. If `get_basic_info` lacks a stable
file ID, the adapter requires an existing artboard anchor; create one starter
artboard manually in the intended scratch file. Unrecognized response shapes fail
closed as `DOCUMENT_SCHEMA_UNVERIFIED`, not a guessed target. A live schema capture
must precede any compatibility adaptation.

Native clients must open/trust the new workspace and approve the MCP connection
according to their own rules. Do not automatically trust a workspace, disable
sandboxing or enable arbitrary tools across all worker accounts.

## Deterministic behavior and limits

`status` observes server/document; `catalog` discovers real upstream input schemas;
`read` allows the documented inspection/screenshot/JSX tools; `edit` requires an
explicit opt-in, operation ID and immediately compared basic-info snapshot hash.
Paper validates its current input schema. Unknown tools, native path-writing export
and node deletion are excluded. Image artifacts accept only PNG/JPEG into an
explicit private output directory, content-addressed and never overwritten.

A snapshot is NOT a revision, identity credential, authorization or full content
hash. `get_basic_info` may not change after an inner text/style edit. It cannot
prove serializable isolation. The mutex serializes bridge calls from one OS user,
not manual UI edits, raw Paper clients, other OS users or whole multi-call tasks.
The artboard anchor is an observed guard, not globally proven file identity.
Keep ONE assigned designer per desktop document; other agents can research or
review artifacts concurrently. Do not advertise arbitrary concurrent canvas writers.

Reads and edits are bounded, with no proxy environment, arbitrary URL, redirects,
background polling, automatic replay or resumable mutation transport. A missing
reply or error after edit dispatch is `EFFECT_UNKNOWN`, even when it might be an
input error, because partial effects are possible. Inspect the original document
and reconcile on the same carrier. `operation_id` is a correlation label, NOT an
exactly-once guarantee. This component stores no alternate retry state.

`APPLIED_RESPONSE_OBSERVED` means a successful response and matching post-read
context, not visual correctness or production acceptance. Keep screenshot/browser
acceptance separate. Plan and remaining quota are UNKNOWN unless observed from an
authoritative source; do not subtract a guessed allowance into another quota DB.
Use the existing routing/usage owner for real usage events when integrating it.

## Model workflow and token budget

Deterministic components own transport, bounds, locking and refusal. A capable
least-scarce design agent owns visual reasoning; a reviewer checks the screenshot
and user journey. Fable is not required for a census or routine MCP calls. Budget
one catalog discovery per workflow and deliberate screenshots at meaningful changes;
no idle loops. Every guarded edit currently costs three Paper tool calls (pre-read,
edit, post-read); plan this explicitly on the 100-call Free tier.

## Figma migration

Keep Figma as a read-only reference/archive until representative journeys pass.
Migrate our own tokens, typography, spacing, components and content; rebuild original
layouts with Paper's web-native structure. Paper documents a Figma token workflow
and known conversion limits (SVG overrides, spacing, code-connected components).
Do not promise a lossless import or cancel Figma based on an MCP connection alone.

Prove one real Mastermind screen through: all meaningful states -> Paper screenshot
-> JSX -> existing frontend components/tokens -> responsive browser review. Design
code output is a starting point, not automatic tested production implementation.

## Acceptance and continuation

1. Exact source runtime installed without changing other worker homes.
2. Native MCP initialize/list and real CLI read against Paper after login/file-open.
3. Approved scratch edit, screenshot, JSX extraction; no wrong-document changes.
4. Fresh ChatGPT Web session runs the same journey through authorized RDC and sees
   the image (or uses an enrolled dedicated MCP app with honest write annotations).
5. Existing capability registry attests a bounded worker; no second control plane.
6. One real product design-to-code/browser journey before Figma retirement.

Stop at login, app approval, absent host transport, unknown effects or an unproven
sealed-worker grant. Do not turn synthetic fixtures, downloads, PRs or config
staging into PROVEN_LIVE. Continue at the first unmet item, retaining this carrier.

## Sources checked 2026-09-13

- https://paper.design/docs/mcp - endpoint, tools, current-file context, code export, migration.
- https://paper.design/downloads - desktop distribution.
- https://paper.design/pricing - Free 100 MCP calls/week; Pro 1M/week,
  $20/editor/month monthly or $16/month billed yearly. No purchase performed.
- https://help.openai.com/en/articles/12584461 - custom app write/admin/plan gates;
  Pro custom developer-mode MCP currently documented read/fetch only.
- https://github.com/openai/tunnel-client - private outbound Secure MCP Tunnel, stdio support.
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports - HTTP/SSE/session rules.
- https://pypi.org/project/mcp/1.30.0/ - pinned official SDK maintenance line.

## Observed native staging - 2026-09-13

This candidate is PARTIAL / BUILT_NOT_PROVEN for design operations, not accepted
production. The reachable Mac Mini now has Paper 0.5.9 installed and launched from
`~/Applications/Paper.app`; code signature and Apple notarization passed. An
isolated Python 3.14.6 / MCP 1.30.0 environment and real project-scoped workspace
exist at `~/.local/share/mastermind-paper/paper-20260913-sol01/workbench/workspace`.
No provider home, live worker, billing, Figma file or Executive gate was changed.

Actual stdio initialization/list-tools passed for both read-only (3 tools) and
write-capable (4 tools) modes, with correct write annotations. The native probe
found and fixed a postponed local type-annotation error that syntax/unit tests
could not prove. Reproduce the SDK check with `smoke_sdk.py` in the pinned venv.

Paper is listening on 127.0.0.1:29979 but its own initialize endpoint returns
HTTP 500: `Could not find Paper. Is it running?`. A usable editor file is not
proven; login state is UNKNOWN, not diagnosed from the HTTP error. No design was
read or changed. Open the intended file through normal Paper UI after login as
needed, then resume with the installed CLI `status`. Native receipts and exact
hashes are in `docs/evidence/paper_desktop/20260913_native_staging.json`.

The Mac Studio answered initially, then its remote commands/pings timed out. It
was not modified; no modifying operation was retried or failed over. This is a
separate, authorized Mac Mini staging, not a claim that Studio worker routing
has been enrolled. No paid plan, public tunnel or standalone ChatGPT app was
created. The existing RDC route executed the real native adapter from this web
session, but successful visual design use and a fresh-session repeat remain due.
