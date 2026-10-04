# Mastermind OS shared product

This read-only React/TypeScript product installs a fixed web or Tauri host before
mounting. At the inspected protected source `a2646f458f9f`, the app consumes the
closed Programs envelope, Mission v3 (with the existing v2 fallback), and exact
Result reads from the workspace service, preserving Program selection,
generation and abort fences. Historical v1 fixtures remain decoder regression
inputs. Use the pinned code references in the daily-flow specification when
reconciling this documentation branch with the current implementation.

Programs join one `work_ref` to exactly one Runtime root. Mission reads carry
exactly `work_ref` and `root_job_id`; no recent-root guessing is performed.
`CURRENT` means current as of the bounded owner observation, under the service's
source-validity checks. It is not a linearizable claim about the moment the UI
renders. The frontend validates the closed receipt, matching selection, sample
consistency, digest formats and the facts in the Mission DTO. The authenticated
service owns binding digests to the full source documents, which are absent
from the Mission response. Runtime completion never implies acceptance.

The Conversation view consumes only the current server-permitted managed turn
window, displays text as text, and clears its contents on authentication or
selection changes. It does not establish full history or product acceptance.
The client has no enrollment, provider-control, send, shell, generic HTTP, or
caller-selected URL command.

## Public configuration still required

No viewer client IDs have been registered or invented in this source change.
Without the build input for its platform, the app displays **Sign-in setup
pending**. Registration and permissions are separate operator-owned work.

| Field | Web | Native macOS |
| --- | --- | --- |
| Public client ID build input | `VITE_MM_WEB_CLIENT_ID` | `MM_NATIVE_CLIENT_ID` |
| Client type | Distinct public SPA with PKCE S256 | Distinct public native client with PKCE S256 |
| Exact callback | `https://mcp.mastermind-x.com/os/auth/callback` | `com.mastermind.os://oauth/callback` |
| App origin/base | `https://mcp.mastermind-x.com`, `/os/` | Bundle `com.mastermind.os` |

The fixed issuer is `https://dev-eo0jf8us5mup7wd5.us.auth0.com/`.
Acquisition requests use only audience
`https://mcp.mastermind-x.com/workspace/read` and scope
`mastermind.workspace.read`. Content uses a separate token for audience
`https://mcp.mastermind-x.com/workspace/window/current` and scope
`mastermind.workspace.content.read`. There are no OIDC identity scopes or
refresh tokens. Each audience requires its corresponding enrolled service
permission; a content refusal can leave acquisition usable.

The web client opens one popup directly in the user gesture, reuses it for two
one-use PKCE transactions, checks exact callback origin/window/state, and
cleans callback query/fragment before the handoff. Codes and tokens never reach
React. Tokens remain in private module memory and disappear on sign-out or
reload. Sign-out is local token disposal, not an Auth0 SSO logout.

Native Rust opens the system browser and receives the registered deep link.
Tokens stay in Rust memory. React uses only `auth_status`, `sign_in`, `sign_out`,
`read_programs`, `read_mission`, `read_mission_v3`, `read_result`, and
`read_current_window`; it has no token getter or arbitrary URL bridge. The macOS app must be installed/registered for
its custom scheme before an actual callback can be qualified. This source
change neither installs nor launches it.

The inspected fixed public GET routes are `/workspace/programs/current`,
`/workspace/mission/current`, `/workspace/mission/v3/current`,
`/workspace/result/current`, and `/workspace/window/current`. Every public
response is capped at 2,000,000 bytes. Token responses are capped at 32,768
bytes. The content service's separate internal frame limit remains 544 KiB.
Web hosting must serve the product and exact callback through the `/os/` SPA
fallback and permit the fixed issuer token endpoint in its CSP. The issuer's
web-origin/CORS configuration must match the exact product origin. Native
HTTP runs through Rust and uses no JavaScript network permission.

## Validation

```sh
npm ci --ignore-scripts
npm run typecheck
npm test
npm run build
npm run build -- --mode native
```

The normal web build uses `/os/`; the Tauri pre-build uses `native` mode and
relative packaged assets. Rust checks require a full source revision and a
review build identity, and should place build products in owned external
storage:

```sh
MM_SOURCE_REVISION="$(git rev-parse HEAD)" \
MM_BUILD_IDENTITY="mastermind-os-review" \
CARGO_TARGET_DIR="/path/to/owned/external/target" \
cargo test --manifest-path src-tauri/Cargo.toml
```

The tests use local fixtures and injected transports. Their success is source
validation, not proof of actual Auth0 registration, native callback delivery,
installed workspace services, enrolled content permissions or live product
acceptance. The readiness command retains `BUILT_NOT_PROVEN` until an external
installation qualification exists. No updater, native signing, service
installation, registration, or release is performed by these checks.

## Approved visual design

The Chairman approved **Noir Atelier** as the canonical visual direction for the
entire Mastermind OS project on **3 October 2026, America/Chicago**
(2026-10-04 UTC).

The current design entry point is [Paper page 12 — Canonical Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-D-0)
in the Mastermind OS file `01M3NRCX55B452A12819WNE1RH`:

- **AT00 `KSB-0`** records the project-wide ruling and current route index.
- **AT90 `KSQ-0`** defines the shared shell, typography, palette and spacing.
- **AT91 `NDE-0`** defines loading, empty, unavailable, withheld, unknown-outcome
  and control states.
- [Paper page 11 — Chat Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-C-0)
  remains the originating conversation family; **CH91 `KDN-0`** provides its
  detailed visual and interaction contract.
- **CV01 `SD8-0` / CV01M `SI5-0`** on Page 12 define the Conversations
  destination: the durable company office, exact permitted project conversations,
  scoped filtering, and source/access recovery.

Apply the ink and graphite surfaces, ivory reading hierarchy, champagne primary
actions, original sculptural artwork and progressive disclosure consistently
across every OS route and responsive layout. Keep the five primary destinations:
Today, Projects, Inbox, Conversations and Knowledge. Work, sessions, evidence,
journal and resources remain accessible in project context.

The earlier #702 workspace, #704 consumer freeze and retained Paper state
families remain feature and behavior references. Preserve owner attribution,
permissions, source freshness, exact action identity and the distinction between
returned, accepted and released work while adopting the current visual family.

These are approved editable designs. Visual approval and screenshot review do
not establish frontend implementation, installed behavior, keyboard or enlarged-
text validation, deployment, or product acceptance. The cumulative design and
verification record remains
[`research/MASTERMIND_OS_NOIR_INITIATION_2026-09-26.md`](../../research/MASTERMIND_OS_NOIR_INITIATION_2026-09-26.md).

## Daily workflow and builder starting point

Read the [Daily Experience Builder Flow Specification](../../docs/design/MASTERMIND_OS_DAILY_FLOW_SPEC.md)
before wiring the mockups. It grounds the intended experience in protected
product law and implementation source `a2646f458f9ff41ddcedd89b338be4a4349e6cd6`.
A continuation comparison through protected `28be2ce2d481fd542ec869344e178e5cec4d7d75`
found no app-source delta; dated candidate observations remain separate in §18.2.

[Paper page 13 — Daily Experience](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-E-0)
connects the route family through eight editable workflow notes:

- UX00 `PBO-0`: daily loop, roles and directory.
- UX01 `PBP-0`: complete, partial, historical and unprojected Today states.
- UX02 `PBQ-0`: direction, accountable next result and named project creation.
- UX03 `PAY-0`: exact decision, one final action and confirmed/uncertain outcomes.
- UX04 `PAZ-0`: scoped drafts, evidence detours, session succession and access loss.
- UX05 `PBR-0`: route/owner/capability boundaries and first build slice.
- UX06 `SMO-0`: exact conversation selection, scoped filtering and empty/access states.
- UX07 `SMP-0`: Options + Send, draft continuity, delivery stages and recovery.

The daily product shows what needs the Chairman's judgment and what the team
owns. Meta-CEO remains one durable company office; project conversations retain
their Project Sol and project scope. Ordinary supported messages do not require
a blanket approval step. Work, decisions, receipts, acceptance and release keep
their distinct canonical meanings.

For the connected chat journey, start with UX06 and CV01/CV01M, then CH1/CH6,
CH2 evidence and CH3 context, using UX07 for composition states. Evidence and
context reads preserve the same scoped unsent draft. Submission, owner acceptance,
recipient delivery and received reply remain distinct. A late receipt never erases
a newer draft; unresolved delivery stays with its original operation. Inbox keeps
routine team review with the project owner and opens the exact reserved decision
packet directly. The specification records the actual control IDs and return rules.

The specification includes actual Paper action anchors, source-owner mappings,
transition and recovery matrices, twelve illustrative fixtures and fifteen
implementation acceptance scenarios, with continuation checks for directory
identity, message stages, draft revision, IME and actual focus restoration.
The current protected app remains a
read-only consumer; message send, project creation, decision recording, full
history and execution continuation are target capabilities with separate owner
and implementation gates. The #1046/#1150 draft custody and source-release
boundaries are not cleared by this design work. No working prototype links,
installed UX or live command behavior are claimed from Paper screenshots.
