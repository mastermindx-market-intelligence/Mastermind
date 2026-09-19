# Paper.design integration - bounded local and web design capability

## Mission and frozen boundary

Chairman direction, 2026-09-13: make Paper ready for local agents and ChatGPT Web,
without buying a plan. The useful end-state is brief -> editable Paper design ->
screenshot/review -> JSX -> integrated, browser-proven product, not merely an MCP entry.

Procedure source: Mastermind protected master
`55473bb43c3ae1908f53ddd4ccfe724643dd6c69`, Sol Skillpack 1.0.1 / bootstrap 1.
Paper official plugin reference: `paper-design/agent-plugins` at
`f6d4f13343dd924fabaadd0898725f1b8718459d`.
No production lifecycle, queue, identity, credential or authentication store is added.
The only shared runtime file is a per-OS-user advisory mutex for the Paper desktop.
It is not an ownership lease, Job state, deduplication ledger or authorization token.

## Architecture

Local Claude/Codex/Cursor/OpenCode/VS Code client -> approved project-scoped MCP
configuration -> `mcp_server.py` (official MCP SDK, stdio) -> `bridge.py` ->
Paper's fixed loopback MCP `http://127.0.0.1:29979/mcp`.

ChatGPT Web -> existing Studio Direct private Secure MCP Tunnel -> Studio Direct
gateway-owned `paper_inspect` / `paper_catalog` / `paper_read` / `paper_edit`
tools -> the SAME SHA-pinned `bridge.py` -> Paper's fixed loopback endpoint.
Screenshots remain native MCP image blocks. The Web caller cannot provide an
arbitrary host path, Paper endpoint, account or credential.

Studio Direct is the existing Web gateway/auth/transport owner; Paper does not get a
second public gateway. Remote Desktop Commander remains an authorized local-ops and
diagnostic carrier and supplied the original native proof, but is no longer the
normal product path once a Studio Direct seat is Paper-enabled. Do not expose the raw
unauthenticated Paper port through a public tunnel, add another OAuth service, or put
design tools into Executive OS's bounded CEO-admission API.

No MCP tool is disguised as read-only to bypass client write permissions.
`paper_edit` is explicitly modifying/destructive/non-idempotent; it exists only
when the local server is started with `--allow-write`.

## Team/account and seat model - 2026-09-18

Use **one real signed-in Paper editor identity as the agent execution seat**, not
one Paper user account per ChatGPT/local agent. Agents are software clients behind
the governed bridge; they do not need Paper member identities merely to call MCP.
Paper's current Terms prohibit password/account sharing, false identities, creating
accounts for someone else, and holding more than one account at a time. Do not
accept pending agent-email invitations into fabricated Paper user accounts.

Human collaborators should use their own real member identities. Paper currently
makes unlimited editors/viewers free on the Free team. On Pro, billing is explicitly
per editor seat while viewers remain free, so separate agent-editor memberships
would create unnecessary paid seats. Pro advertises 1M MCP tool calls/week, but its
public pricing page does not state whether that allowance is pooled per team or
measured per editor; keep quota scope UNKNOWN until Paper exposes it authoritatively.

Paper 0.5.11 supports multiple desktop tabs, and Paper's August 2026 build log says
agents may work across multiple open files, including background tabs. That makes a
single real execution seat compatible with multiple governed agent workflows without
credential sharing between fake Paper members. Our bridge still serializes modifying
calls on one desktop until stronger multi-file isolation is explicitly proven.

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
No paid plan is needed for initial smoke proof. Paper 0.5.11 returns a compact
structured file header plus a richer JSON text block from `get_basic_info`; the
adapter merges them only when file identities/names agree, preserving provider file
ID plus page/artboard state. Every stable-ID edit must also pass that exact `fileId`.
Legacy artboard-anchor fallback remains fail-closed for older supported shapes.
Unknown/conflicting shapes still refuse as `DOCUMENT_SCHEMA_UNVERIFIED`.

Native clients must open/trust the new workspace and approve the MCP connection
according to their own rules. Do not automatically trust a workspace, disable
sandboxing or enable arbitrary tools across all worker accounts.

The staged install now emits `ENROLLMENT.md` with exact per-client gates. Codex
loads project `.codex/config.toml` only after the exact workspace is marked trusted
in the user-level Codex config. Claude Code separately requires project-MCP approval.
Neither ceremony is performed by `install.py`; both remain visible account/client
authorization boundaries.

## Deterministic behavior and limits

`status` observes server/document; `catalog` discovers real upstream input schemas;
`read` allows the documented inspection/screenshot/JSX tools; `edit` requires an
explicit opt-in, operation ID and immediately compared basic-info snapshot hash.
Paper validates its current input schema. Safe Paper 0.5.11 reads additionally include file listing, node search, tokens and
comment inspection. Guarded edits additionally cover page creation, token create/
update and comment-resolution state; token deletion is explicitly refused.
Cross-team `create_file`, document-transition `open_file`, native path-writing
exports and consequential node deletion remain excluded until they have their own
bounded transition/effect contract. Image artifacts accept only PNG/JPEG into an
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
4. Fresh ChatGPT Web session runs the same journey through a Paper-enabled Studio
   Direct seat and receives the native MCP image/JSX result. Tunnel health alone is
   not the design-journey proof.
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

## Observed native proof - 2026-09-18

Overall capability remains **PARTIAL** because sealed Executive worker enrollment,
fresh-session repeat and one real product design-to-code/browser journey are still
owed. The local Paper design path on the authorized Mac Mini is now proven live.

Paper was upgraded in place on the same carrier from 0.5.9 to signed/notarized
**0.5.11**; the prior application is retained as `Paper.app.prev-0.5.9`.
The official ARM64 DMG SHA-256 is
`03a027b2b1bc1df2e54f8db3d4cd5c1c404bf56994926113efe223e0b2a27079`.
Paper 0.5.11 listened on 127.0.0.1:29979 and a scratch file was created/opened
through the normal Paper UI.

The live 0.5.11 wire exposed a compact structured file header and a richer detail
block. That falsified the original parser assumption and produced
`DOCUMENT_SCHEMA_UNVERIFIED` despite a valid stable file ID. The same installed
bridge was repaired to reconcile agreeing shapes, preserve page/artboard state, and
require an exact file ID on every stable-ID edit.

Live canary effects on the scratch file were all observed on this original carrier:
a 900x560 artboard was created, incremental Inter typography was written, a JPEG
screenshot was returned and saved privately, JSX was extracted from the same
artboard, and Paper's required `finish_working_on_nodes` call returned OK.
No edit returned `EFFECT_UNKNOWN`; no operation was replayed. Screenshot SHA-256:
`d200166b831f154bcef7e59883c0193225961ed73b52c17b83d445a7fd195200`.
The JSX read contains "Native design tooling is live." with the expected dimensions,
Inter typography and colors.

Installed SHA-256 after hardening:
`bridge.py=cd34f98c1647ba52f392fb93aa9d7aed24eb39aac90d7de75bce39021444740d`;
wrapper/server and requirement pins are unchanged. This proves the local
read/write/screenshot/JSX substrate, not fleet production or visual product quality.

A first-class ChatGPT full-MCP write app remains behind OpenAI's current
Business/Enterprise/Edu developer-mode gate and Secure MCP Tunnel. Existing
authorized RDC remains the web-to-native carrier for this session.

### Observed local-client enrollment

The authorized Mac Mini now has an explicit Codex trust entry for only the isolated
Paper workspace; the previous user config was preserved as
`~/.codex/config.toml.pre-paper-20260918`. From that workspace, `codex mcp list`
shows `mastermindPaper` enabled and points at the guarded stdio adapter. A real
`codex exec` attempt then stopped at a distinct provider-authentication gate:
the stored ChatGPT refresh token is invalid (HTTP 401). The MCP configuration itself
is visible; exact human recovery is `codex logout` followed by interactive
`codex login`, then repeat the read-only Paper canary.

Claude Code independently sees `mastermindPaper` from the same workspace but reports
`Pending approval (run claude to approve)`. That approval is intentionally not bypassed.
Launch interactive Claude in the isolated workspace and approve only that project MCP,
then repeat the same Paper inspection canary.

These two account/client ceremonies are the remaining native-human gates; they are
not reasons to create additional Paper user accounts or another MCP gateway.
