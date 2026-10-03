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

## Direct Business migration — issue #1011

Chairman direction, 2026-09-26: build the private **Mastermind Paper** direct route first, reuse one
existing tunnel, and leave credentials, Business workspace enrollment, activation and live canary
until the final attended setup. See `docs/PAPER_DIRECT_CHATGPT.md` for installation and acceptance.

Target normal Business path: private Mastermind Paper app -> OpenAI Secure MCP Tunnel -> existing
guarded stdio `mcp_server.py` -> the same `bridge.py` -> fixed Paper loopback. The direct app exposes
no generic workstation tools and does not depend on Studio Direct/DC for normal Paper calls.
The previous blanket dedicated-app prohibition is superseded for this commissioned migration.
It does not authorize public publication, duplicate tunnels, unattended account changes, or a second
Paper guard/auth/retry owner. The direct build uses Paper's explicit-file contract: `paper_prepare`
validates one target by bare `fileId` and returns that target's snapshot without requiring the
user-active file to switch or exposing arbitrary host/raw `open_file` control. Subsequent direct
edits validate and post-read the same explicit target file.

Staging and local stdio proof are not enrollment or cutover. After the actual Business app and
scratch-file path are accepted, retire Studio Direct's primary Paper-Web requirement for that
workspace. Other seats retain their legacy route until separately migrated. No denial or unknown
effect ever authorizes a carrier/account/model switch. A migration canary is an explicit single-carrier operation. That carrier/effect fence is scoped to
that logical canary; it is not a file-wide writer lease for unrelated Paper edits.

Direct target-binding qualification — 2026-09-27: live Paper 0.5.12 evidence showed that raw vendor
`open_file` can return the requested file's `get_basic_info` while the user-active file remains
unchanged. A separate read-only probe proved `get_basic_info(fileId=...)` succeeds for a recent file
that is not open, without changing the active file. All 12 guarded edit schemas require `fileId`.
Therefore UI focus is not a write-safety prerequisite for the direct route; exact target identity and
target snapshot are. Legacy Studio `paper_prepare` publication behavior remains a separate client path.
The resulting target-aware bridge is immutable runtime generation **v6**, SHA-256
`938c45356f95f3a57df2290e2da045eae9a6c4a0c3507dfff81c40a87e85b72a`. Legacy Studio Direct
remains pinned to runtime v5 until separately selected for upgrade; the Business direct canary may
stage v6 without moving that legacy carrier.

### Direct Business multi-seat transport — 2026-09-27

The direct route may serve multiple ChatGPT accounts/workspaces concurrently without multiplying the
Paper control plane. Each Business seat owns one exact tunnel-client process, loopback health endpoint,
private bundle state and seat-specific transport singleton/launchd label. Every seat's MCP child still
loads the same guarded bridge implementation and all Paper calls contend on the existing per-OS-user
`desktop.lock`. Ordinary same-host overlap waits on that local mutex for at most 30 seconds before any
Paper call is sent; prolonged contention fails closed as `DESKTOP_BUSY`. This preserves one Paper Desktop
execution plane and one shared safety/effect contract while allowing C1/C2/C3/C4/admin ChatGPT transports
to remain connected simultaneously. The bounded lock wait is not a retry owner or persistent queue, and no
transport seat creates a Paper user identity, document lease or second auth plane.

Seat-aware install schema v3 requires a safe stable `seat_id`; legacy v2 bundles remain backward
compatible. v3 local binding requires the exact tunnel ID but does not require a guessed backend
workspace ID. When an exact workspace ID is independently observed it may be recorded; otherwise the
OpenAI tunnel/workspace association is proven through attended account setup and direct app discovery.

## Architecture — shared adapter and legacy/non-migrated clients

Local Claude/Codex/Cursor/OpenCode/VS Code client -> approved project-scoped MCP
configuration -> `mcp_server.py` (official MCP SDK, stdio) -> `bridge.py` ->
Paper's fixed loopback MCP `http://127.0.0.1:29979/mcp`.

ChatGPT Web -> existing Studio Direct private Secure MCP Tunnel -> Studio Direct
gateway-owned `paper_inspect` / `paper_catalog` / `paper_read` / `paper_prepare` /
`paper_edit` tools -> the SAME SHA-pinned `bridge.py` -> Paper's fixed loopback endpoint.
Screenshots remain native MCP image blocks. The Web caller cannot provide an
arbitrary host path, Paper endpoint, account or credential.

Studio Direct is the existing legacy Web gateway/auth/transport owner; Paper does not get a
second public gateway. It is the preferred attended-Web carrier for non-migrated seats when the
Paper tool family is actually exposed. Remote Desktop Commander is also a direct-host client of the
**same guarded bridge**, but Studio Direct absence grants it no authority. RDC may be
selected for a Paper effect only when the current Chairman assignment/delegation or
accepted canonical placement independently authorizes that exact host carrier and
Paper action, current host permission is observed, no explicit denial applies, and no
conflicting or unknown Paper effect exists. Otherwise the session stops at the exact
carrier gate. This is not a second gateway, auth plane, write authority, or permission
fallback. The current protected `private_service.py` runtime/schema/SHA pins, not folder recency
or an old installation receipt, determine the exact bridge that Desktop Commander may
invoke. Do not expose the raw unauthenticated Paper port through a public tunnel, add
another OAuth service, or put design tools into Executive OS's bounded CEO-admission API.

Capability discovery is action-specific. A session that sees Studio Direct filesystem/
process tools but has not checked for `paper_inspect`, `paper_catalog`, `paper_read`
and `paper_edit` has **not** established Paper unavailability. `paper_inspect` now
returns `gateway_surface`, which declares the exact Paper tool family the current gateway
is built to advertise. If that contract includes `paper_prepare` while the ChatGPT client
surface omits it, classify the mismatch as publication/surface drift: `STUDIO_TOOL_PUBLICATION_DRIFT / EFFECT_NONE`. Current-file
reads/edits may remain available, but exact-file transition is held until the same Studio
Direct app's **workspace-approved action snapshot** is current and `paper_prepare` is directly
surfaced. OpenAI documents that approved MCP apps use a frozen tool/input snapshot and do not
auto-update when the server changes. On Business, published custom apps currently cannot be
updated in place; recreate + republish is required. Draft/dev apps must re-scan/recreate their
tool catalog as applicable, then the caller starts a fresh chat/tool selection. Do not reproduce
prepare with generic Studio `start_process`/filesystem tools, RDC, raw upstream `open_file`,
shell, or UI automation. This keeps file transition inside the reviewed narrow action instead
of silently broadening workstation authority.
A proven pre-dispatch absence that remains after current same-Studio publication recovery
may make an **independently authorized** RDC carrier eligible under the separate carrier
law; absence itself never supplies permission. After edit dispatch, timeout/lost response
remains `EFFECT_UNKNOWN` on the original carrier and forbids cross-carrier replay.

### Paper 0.5.14 catalog qualification — 2026-10-01

Paper Desktop 0.5.14 later changed its full canonical catalog from accepted
`8cd27488a3adfc19c6c36d4349b75feebc71c159253c47f8a0f8d50c27043deb` to
`ac18857df0aa6323646333368e5798e7c28de7b4d5f5dc3cb320276e3535daa9`. Qualification used
the complete live 36-tool dictionary plus durable accepted `ca90...`/`8cd...` receipts. Rebuilding
the 34-tool predecessor by removing `rename_pages`, `list_resources`, `rename_resource` and restoring
the exact historical `list_files` descriptor reproduces `ca90...` exactly; adding the current
`rename_pages` descriptor reproduces accepted `8cd...` exactly. The current full map independently
reproduces `ac18857...`. Thus the accepted-to-current delta is exactly: remove `list_files`, add
blocked `list_resources`, add blocked `rename_resource`; no surviving descriptor changed.

Bridge 0.1.4 keeps the same 12 edit tools, reduces the read allowlist from 17 to 16 by removing
`list_files`, and does not expose either new resource tool. Immutable runtime generation v10 owns
bridge SHA-256 `7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc`; v9 remains unchanged.
Exact target, snapshot, token-delete, desktop mutex, and EFFECT_UNKNOWN/no-replay guards are preserved.
Evidence: `docs/evidence/paper_desktop/20261001_0514_catalog_compatibility.json`.

### Paper release-version compatibility ruling — 2026-09-30

Paper Desktop's reported release version is now **observational metadata, not a write-admission
boundary**. The guarded bridge still requires the exact `paper-desktop` server identity and the
reviewed full tool-catalog digest before a write. A release-number change by itself therefore does
not force Paper into read-only mode when the effective catalog is byte-for-byte compatible.

Live Studio observation on 2026-09-30 reported Paper **0.5.14** with catalog digest
`8cd27488a3adfc19c6c36d4349b75feebc71c159253c47f8a0f8d50c27043deb`, exactly the already
reviewed catalog qualified below for 0.5.12. Runtime **v9** / bridge **0.1.3**
(`a784fefceb7b1bb1164289700b22a6f53d09ae60d007f506ac015ebaca8c3725`) encodes that policy. If the server identity changes or the catalog digest changes,
writes still fail closed as `UPSTREAM_SCHEMA_UNREVIEWED` until that schema is reviewed. Do not
weaken this to tool-name subset matching or auto-accept a changed catalog.

This fixes compatibility admission only. Existing installed v5/v8/direct bundles do not become v9
merely because source changed; normal immutable-runtime staging/deployment and route readback remain
separate effects. Because the public Paper action schemas are unchanged, a version-only runtime
upgrade does not by itself require a duplicate app/tunnel or an action-snapshot republish.

### Paper 0.5.12 catalog drift qualification — 2026-09-26

A later Paper 0.5.12 observation changed the full upstream catalog digest from
`ca90a537ee97f3e371ac945a8a3b9a928ba7fac9ffaeb67e31491075a0790570` to
`8cd27488a3adfc19c6c36d4349b75feebc71c159253c47f8a0f8d50c27043deb`.
The release owner compared the exact current name-keyed tool dictionaries with the
durable prior raw catalog. Tool count changed **34 -> 35**; `rename_pages` was the
only added tool; no tool was removed and **no existing tool definition changed**.
The bridge therefore keeps the same 17 read and 12 edit allowlists and leaves
`rename_pages` blocked alongside `create_file`, `delete_nodes`, exports and raw
`open_file`. Exact full-catalog pinning remains fail closed rather than weakening to
a subset/schema-family check.

The compatible bridge is version `0.1.1`, SHA-256
`d3301a1466d46ae081ded963f438c019fabf39c9bccfc8c669f16562a52bf7f6`,
owned by immutable Paper runtime generation `v5`. This source qualification is not a
deployment or write canary; installed `v4` seats remain valid historical runtimes
until the normal release owner moves an explicitly selected canary. Evidence:
`docs/evidence/paper_desktop/20260926_0512_catalog_compatibility.json`.

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
single real Paper editor identity/seat compatible with multiple governed agent workflows without
credential sharing between fake Paper members. Our bridge serializes individual calls
from one OS user through `desktop.lock`; that local call mutex is not a document lease
and does not make one designer the owner of a Paper file.

### Multi-writer collaboration boundary - 2026-09-27

The same real Paper editor identity may back governed Paper Desktop processes on M1, M2,
and other admitted hosts; do not buy or fabricate separate Paper members merely because
another agent session runs on another owned Mac. Each host remains a separate local MCP
process and may work on the same or a different Paper file in parallel.

Concurrency is **target-scoped, not file-scoped**. Multiple modifying sessions/hosts may
work on the same exact `fileId`, including the same Paper page. Prefer disjoint
board/artboard/node target sets. Same-board editing is allowed when target sets are
partitioned; if overlap is known or suspected, re-read the current target and coordinate
or re-plan the next operation rather than acquiring a file-wide or page-wide lease.
This contract is advertised as `MULTI_WRITER_PER_FILE_TARGET_SCOPED`.

The local per-OS-user mutex remains only a bridge-call serialization primitive. Its
bounded acquisition wait absorbs transient same-host session overlap before dispatch; it
does not provide a distributed lock, effect retry, or persistent queue. `paper_prepare`
does not mint ownership or replace the existing Capacity/routing owner. A fresh exact-target
snapshot is optimistic evidence for one bounded edit, not a global revision or collaboration lock. Every logical mutation still
binds to one carrier + operation identity until its effect is reconciled; `EFFECT_UNKNOWN`
remains original-carrier sticky.

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

Launch Paper and sign in through its normal UI. The private Studio Direct host pins
`~/Applications/Paper.app`; a Web caller cannot supply another application path, URL,
account or credential. When the exact Paper file ID is known, `paper_prepare(file_id)`
may launch/focus that pinned app through the observed `paper://file/<id>` desktop URL,
then repeatedly observes the guarded bridge until the exact file identity is proven.
If the transition cannot be proven, it returns
`PAPER_DOCUMENT_TRANSITION_UNCONFIRMED`, performs no automatic replay, and exposes no
content edit capability. When the file is already active, prepare skips the desktop
launch entirely and returns the current snapshot plus write-schema qualification.
The reviewed 0.5.14 catalog no longer exposes `list_files`, and resource discovery remains blocked.
When the file ID is unknown, obtain the exact identity from accepted task context or stop at a typed
binding gap; do not guess a file or substitute `list_resources`.

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
`read` allows the documented inspection/screenshot/JSX tools; the Studio Direct
`paper_prepare` wrapper performs only a bounded host-pinned desktop/file transition
and exact-file verification; `edit` requires an explicit opt-in, operation ID and
immediately compared basic-info snapshot hash.
Paper validates its current input schema. Safe Paper 0.5.11 reads additionally include file listing, node search, tokens and
comment inspection. Guarded edits additionally cover page creation, token create/
update and comment-resolution state; token deletion is explicitly refused.
Cross-team `create_file`, the raw upstream document-transition `open_file`, native
path-writing exports and consequential node deletion remain excluded. Studio Direct
uses only its separately bounded `paper_prepare` wrapper for file focus; callers cannot
forward an arbitrary Paper URL or application path. Image artifacts accept only PNG/JPEG into an
explicit private output directory, content-addressed and never overwritten.

A snapshot is NOT a revision, identity credential, authorization or full content
hash. `get_basic_info` may not change after an inner text/style edit. It cannot
prove serializable isolation. The mutex serializes bridge calls from one OS user,
not manual UI edits, raw Paper clients, other OS users or whole multi-call tasks.
The artboard anchor is an observed guard, not globally proven file identity.
Multiple designers may be assigned to the same Paper file across hosts, including the
same page. Partition work by board/artboard/node where practical; for known same-board
overlap, use disjoint node targets and fresh re-read/re-plan before the next bounded edit.
Do not advertise a file-wide or page-wide modifying lease.

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

For a Paper-canvas assignment, an HTML prototype or review package may support reasoning but cannot
replace the required Paper effect while either lawful Paper route remains unprobed. If both routes
are genuinely blocked, label the artifact `NOT_APPLIED_TO_PAPER` and preserve the exact carrier/
permission/file-transition gate instead of reporting the canvas as updated.

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
4. Fresh ChatGPT Web session runs `paper_inspect` and confirms its
   `gateway_surface` names the five exact Paper actions. When another file is needed, the
   **client surface itself** must expose `paper_prepare`; resolve a known exact `fileId` from accepted
   task context -> direct `paper_prepare(file_id)` -> exact-file read/edit/screenshot/JSX. If no exact
   file identity is known, stop rather than guessing or invoking blocked resource discovery. Generic
   host-command emulation does not satisfy this acceptance.
   Tunnel health alone is not the design-journey proof.
5. Existing capability registry attests a bounded worker; no second control plane.
6. One real product design-to-code/browser journey before Figma retirement.

Stop at login, app approval, absent host transport, unknown effects or an unproven
sealed-worker grant. Do not turn synthetic fixtures, downloads, PRs or config
staging into PROVEN_LIVE. Continue at the first unmet item, retaining this carrier.

## Sources checked through 2026-10-02

- https://paper.design/docs/mcp - endpoint, tools, current-file context, code export, migration.
- https://paper.design/downloads - desktop distribution.
- https://paper.design/pricing - Free 100 MCP calls/week; Pro 1M/week,
  $20/editor/month monthly or $16/month billed yearly. No purchase performed.
- https://help.openai.com/en/articles/12584461 and
  https://developers.openai.com/plugins/deploy/connect-chatgpt - current MCP app/tool-update
  lifecycle. Developer-mode MCP connections support an explicit **Refresh** after tool names,
  descriptions, schemas, annotations, auth, or UI resources change; confirm refreshed metadata
  and start a new conversation. Published plugin definitions use their supported review/rescan
  lifecycle, and workspace action controls may expose their own refresh flow. Do not generalize
  this into a blanket Business recreate+republish rule or create a duplicate Paper app/tunnel
  merely because an older chat still shows stale tool metadata.
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

At this historical native-proof checkpoint, ChatGPT Web reused the Studio Direct Secure MCP
Tunnel and gateway-owned Paper tools. The former blanket dedicated-app prohibition is superseded
only by the explicit Business migration above, not merely by existence of the stdio projection. Remote Desktop Commander remains
an authorized host-diagnostic/local-ops carrier, not the normal design product path.

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
