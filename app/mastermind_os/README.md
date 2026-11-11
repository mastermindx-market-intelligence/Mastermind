# Mastermind OS shared product

This React/TypeScript product composes a fixed web or Tauri host before
mounting. Its Workspace reads consume closed envelopes and versioned Mission
data while preserving selection, generation and abort fences. Historical
fixtures remain decoder regression inputs. Conditional Executive composition
and its current source limits are documented below.

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
The permitted-window DTO supplies no Send or provider-control authority. The
baseline read/auth surface provides no enrollment, shell, generic HTTP or
caller-selected URL command. Conditional Executive and selected-session
transports are separate source capabilities; see the pinned map below.

## Project team candidate — 6 November 2026

The current project-team implementation adds a source-qualified Start work path,
goal and handoff capture, nested COO teams, retained project run history, and
explicit follow-ups from completed results. It reuses the Executive Runtime,
original input store, worker placements, workspace allocator and app operation
controller. The standard app composition mounts that existing Executive command
owner when the client supplies an Executive transport, even without a legacy
Launch manifest. Current-project Start work, new conversations and completed-run
follow-ups keep the same authenticated context and operation store. An absent
manifest supplies no legacy Launch choices or submit authority. After confirmed
project creation, Open project refreshes the existing catalogue and opens the
exact saved project, where Start work is a separate action. It preserves the
setup draft and original operation if the project cannot yet be read. See
[Project team execution](docs/project-team-execution.md) for the architecture,
code artifact continuity, transport boundaries and remaining installed journey
qualification.

This candidate also composes the published native Session Send source from
[9679d5e](https://github.com/mastermindx-market-intelligence/Mastermind/commit/9679d5e864be2d742abbd35eaf976ed090b7a82e).
Native Send uses its fixed private Executive command and current source owner;
it does not borrow Workspace or Content authorization. The dated source audit
below remains historical evidence of the earlier read-only native surface.
Source changes do not establish installation or a successful provider response.

## Source capability reconciliation — 5 November 2026

This is a bounded documentation audit at protected `f030206fdad98900c81ca8b97540a47e992610c3`.
It records the existing source composition and guards; it does not register a
client, enable an audience, alter a catalog, install a build or prove an
authenticated user journey. The October 5 source census and UX15 are retained
as a dated design baseline, not the current capability inventory.

| Surface | Observed source and boundary | Pinned source |
| --- | --- | --- |
| App composition | The standard bootstrap calls `composeMissionHost(client)`, mounts its host and registers guarded page-exit and hot-dispose cleanup. A blanket statement that bootstrap supplies only a read/auth host is obsolete at this pin. | [main.tsx](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/main.tsx#L25-L37) |
| Launch configuration | Launch composition requires both the selected configuration and `client.executive`. The release builder uses a closed environment, excludes ambient VITE inputs and requires the complete qualified Executive-resource/Launch-manifest pair when Launch is enabled. Its default path omits that pair. | [composition](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/compose-mission-host.ts#L17-L49), [release builder](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/ops/executive_os/os_release_assets.py#L219-L261) |
| Web selected session | The existing session host is composed independently of the Launch catalog. The Web transport requires configured, valid Executive authentication; submit and session Send additionally require the SEND capability. Source presence is not an authenticated or installed Send acceptance. | [composition](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/compose-mission-host.ts#L10-L49), [Web guards](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/web-auth.ts#L1041-L1055) |
| Native selected session | The native session projection deprivileges `send` to false and rejects Send with `NATIVE_SESSION_READ_ONLY`. The separate `executive_submit` review boundary is not adjudicated by this documentation change. | [native transport](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/native-executive-transport.ts#L19-L29), [session methods](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/native-executive-transport.ts#L141-L170) |
| Launch receipt and command scope | The Launch adapter requires `accepted=true` and `dispatched=false`; that receipt does not prove a running parent or accepted product. This Launch binding maps message and STOP to null. That fact does not remove the separate selected-session host. | [receipt decoder](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/orchestration/executive-launch-command-port.ts#L362-L384), [Launch mapping](https://github.com/mastermindx-market-intelligence/Mastermind/blob/f030206fdad98900c81ca8b97540a47e992610c3/app/mastermind_os/src/orchestration/executive-launch-command-port.ts#L503-L505) |

These rows describe existing owners and their conditional source behavior.
They are not a new capability registry, a runtime grant or a release decision.
Unconfigured or unqualified capability remains unavailable under its existing
owner. Source composition, authenticated operation, installation and complete
product acceptance remain separate evidence.

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
`mastermind.workspace.content.read`. The baseline acquisition/content flow
requests no OIDC identity scopes. Since the 2026-11-09 native persistence
rollout, the packaged native app compiles the rotating Keychain refresh path
(`MM_NATIVE_REFRESH_ENABLED=1` at build). A client-configured install then
requests `offline_access` for Acquisition and Content and silently renews
across restarts without re-login; see
[the rollout record](docs/native-persistence-rollout-20261109.md) for the
tenant requirements and honest limits. Executive remains non-persistent by
design. Each audience requires its corresponding
enrolled service permission; a content refusal can leave acquisition usable.

The web client opens one popup directly in the user gesture, reuses it for two
one-use PKCE transactions, checks exact callback origin/window/state, and
cleans callback query/fragment before the handoff. Codes and tokens never reach
React. Tokens remain in private module memory and disappear on sign-out or
reload. Sign-out is local token disposal, not an Auth0 SSO logout.

Native Rust opens the system browser and receives the registered deep link.
Access tokens stay in Rust memory. The baseline Workspace/Content read-auth
bridge includes `auth_status`, `sign_in`, `sign_out`, `read_programs`,
`read_mission` and `read_current_window`; these examples are not an exhaustive
list of the later source-owned reads or optional Executive commands. There is
no token getter or arbitrary URL bridge. The macOS app must be installed/registered
for
its custom scheme before an actual callback can be qualified. This source
change neither installs nor launches it.

The baseline public GET routes include `/workspace/programs/current`,
`/workspace/mission/current` and `/workspace/window/current`. These responses
are capped at 2,000,000 bytes; other closed read DTOs retain their own limits.
Token responses are capped at 32,768
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

The design and workflow inventory below was recorded on **5 October 2026**.
Its approval, artboard contracts and intended journeys are preserved.
Implementation observations and remaining gaps in that inventory are dated
unless the November 5 source map explicitly reconciles them. This
documentation repair does not retest those user journeys.

The Chairman approved **Noir Atelier** as the canonical visual direction for the
entire Mastermind OS project on **3 October 2026, America/Chicago**
(2026-10-04 UTC).

The approved design entry point recorded on 5 October 2026 is [Paper page 12 — Canonical Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-D-0)
in the Mastermind OS file `01M3NRCX55B452A12819WNE1RH`:

- **AT00 `KSB-0`** records the project-wide ruling and current route index.
- **AT90 `KSQ-0`** defines the shared shell, typography, palette and spacing.
- **AT91 `NDE-0`** defines loading, empty, unavailable, withheld, unknown-outcome
  and control states.
- **AU01/AU01M `TEP-0` / `TGL-0`** and **AU02/AU02M `THK-0` / `TIQ-0`**
  extend Atelier to public private-workspace entry and browser sign-in pending.
  UX14 defines explicit sign-in, supported Cancel, honest failure states and
  reacquisition before returning to permitted daily content.
- [Paper page 11 — Chat Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-C-0)
  remains the originating conversation family; **CH91 `KDN-0`** provides its
  detailed visual and interaction contract.
- **CV01 `SD8-0` / CV01M `SI5-0`** on Page 12 define the Conversations
  destination: the durable company office, exact permitted project conversations,
  scoped filtering, and source/access recovery.
- **AT05/AT05M `L0Z-0` / `MNM-0`** and **AT06/AT06M `L3N-0` / `MNN-0`**
  define Knowledge and Search with qualified coverage and exact source destinations.
- **AT02/AT02M `M4J-0` / `N28-0`** define project finding within the shown
  scope, an exact project destination and same-list return. UX12 supplies the
  filtered example and the distinct empty, limited, unavailable and unresolved states.
- **AT10/AT10M `LF7-0` / `MOG-0`** now separate Returned, Review, Acceptance
  and Release, with an explicit optional result read and an accountable next actor.
  **AT18/AT18M `OE8-0` / `OKF-0`** identify the selected review finding,
  show qualified source identity/clocks and return to the actual Work origin.
  UX13 connects the complete Project → Work → evidence → return path.
- **AT07/AT07M `L6N-0` / `MNO-0`** now focus Sources/access on the actual
  reading task. **SA01/SA01M `T0U-0` / `T0V-0`** show the exact evidence read,
  partial content, separate freshness/clocks, bounded recheck and retained origin.
- **KD01/KD01M `SPU-0` / `STU-0`** show the source reader and original scoped
  draft. UX09 specifies the added-draft state, conditional Undo, full mobile
  append payload and expanded source details. Mobile payload/details and visible
  status/Close chrome remain reader amendments recorded in the handoff.

Apply the ink and graphite surfaces, ivory reading hierarchy, champagne primary
actions, original sculptural artwork and progressive disclosure consistently
across every OS route and responsive layout. Keep the five primary destinations:
Today, Projects, Inbox, Conversations and Knowledge. Work, sessions, evidence,
journal and resources remain accessible in project context.

The earlier #702 workspace, #704 consumer freeze and retained Paper state
families remain feature and behavior references. Preserve owner attribution,
permissions, source freshness, exact action identity and the distinction between
returned, reviewed, accepted and released work while adopting the current visual family.

These are approved editable designs. Visual approval and screenshot review do
not establish frontend implementation, installed behavior, keyboard or enlarged-
text validation, deployment, or product acceptance. The cumulative design and
verification record remains
[`research/MASTERMIND_OS_NOIR_INITIATION_2026-09-26.md`](../../research/MASTERMIND_OS_NOIR_INITIATION_2026-09-26.md).

## Daily workflow and builder starting point

Read the [Daily Experience Builder Flow Specification](../../docs/design/MASTERMIND_OS_DAILY_FLOW_SPEC.md)
before wiring the mockups. It preserves the original census at
`a2646f458f9ff41ddcedd89b338be4a4349e6cd6` and the dated observations through
`5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f` and
`7eac3ec252475600147ec9a376b8ca16403ac4c5`. The `5b…7eac` comparison and its
five-commit / 34-file / 27-app-path counts belong to the October 5 audit.
The November 5 source map above supersedes that audit's bootstrap and
command-absence statements only for the inspected source facts. Historical
candidate status, source custody and all original acceptance scenarios remain
dated evidence; neither census establishes current installation or permissions.

[Paper page 13 — Daily Experience](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-E-0)
connects the route family through sixteen editable workflow notes:

- UX00 `PBO-0`: daily loop, roles and directory.
- UX01 `PBP-0`: complete, partial, historical and unprojected Today states.
- UX02 `PBQ-0`: direction, accountable next result and named project creation.
- UX03 `PAY-0`: exact decision, one final action and confirmed/uncertain outcomes.
- UX04 `PAZ-0`: scoped drafts, evidence detours, session succession and access loss.
- UX05 `PBR-0`: route/owner/capability boundaries and first build slice.
- UX06 `SMO-0`: exact conversation selection, scoped filtering and empty/access states.
- UX07 `SMP-0`: Options + Send, draft continuity, delivery stages and recovery.
- UX08 `SXT-0`: Search/Knowledge, exact-source opening, coverage and return context.
- UX09 `SXU-0`: explicit excerpt/source-label insertion, draft/Undo states and source details.
- UX10 `T7J-0`: Sources/access, independent read facts, exact evidence recheck and outcomes.
- UX11 `T7K-0`: partial access, configured sign-in, pending/cancel state, protected-data clearing and actual return.
- UX12 `T9B-0`: Projects Find/Clear, limited and empty states, exact opening and retained list position.
- UX13 `TDM-0`: exact Project → Work → selected returned evidence → actual origin, with team-owned review and separate acceptance/release.
- UX14 `TJP-0`: private entry, browser sign-in, blocked/incomplete/setup states, cancellation and permitted return.
- UX15 `TMP-0`: the October 5 protected Work/command map and its recorded integration gaps.

Start with UX00 for the product loop and UX15 for the dated October 5
implementation census; read the November 5 source reconciliation above before
using its old absence claims. Then follow the specific journey. UX15 remains a
guide to specification §18.5, not a new capability registry or owner plane.

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

For source reuse, follow UX08 from Search or Knowledge into KD01, then UX09.
Reading leaves the original draft unchanged. A separately supported Add action
inserts the visibly previewed excerpt and source label into that same draft,
keeping Project Sol, project/topic scope and newer edits intact. Nothing is
sent. Return restores the actual permitted origin and focus; changed sources,
partial coverage, repeated Add, missing draft support and permission loss have
explicit states. Undo is shown only when the existing draft owner can reverse
the exact unchanged insertion; otherwise the person edits the draft.

For source recovery, follow UX10 from AT07 into SA01, with UX11 for access and
return. A partial read keeps permitted metadata useful while the selected
reference, missing clocks and unknown cause stay visible. Recheck runs only an
existing, admitted owner read; it does not ping GitHub or reconnect a service.
Back/Close restores the actual query, scope, selection, focus and eligible unsent
draft. Access loss clears protected content immediately, including Work; late reads
cannot restore it. Supported Cancel ends the local pending read/display wait,
not the native HTTP request or a prior action. Preferences stays secondary to the current reading task. Current
Connections is a Mission relationship view, not a source-inventory API.

For everyday project finding, use AT02/AT02M and UX12. Find filters only admitted
project titles or references. Clear removes the query, keeps the status facet
and restores input focus. Counts describe shown rows; a no-match is different
from an empty source, limited coverage or a failed read. Open uses the selected
row's exact qualified project/root binding, and return restores the query,
facet, selected row, position and actual focus. Active/Archived needs an owner-
defined classification; local Find and richer return remain design requirements
at the inspected protected source. New project is a separate creation-gated draft.

For work follow-through, use UX13 with AT03 → AT10 → AT18. The main action is
Inspect return or Open returned result, an optional read rather than a Chairman
review obligation. Sol owns the retained freshness-correction specimen. Return,
review, acceptance and release keep distinct source facts. Evidence identifies
one selected finding, exposes missing revision/digest/source time honestly and
preserves the existing illustrative observation clock. Source inspection returns
to that finding; evidence returns to Work when Work was its actual origin. A
root-only Work DTO cannot supply the missing project/work-ref join by guesswork.

For opening the app, use AU01/AU01M → AU02/AU02M and UX14. Show public identity
until independently permitted content is available. One configured explicit
Sign in opens the existing web popup or native browser flow. The pending state
offers supported Cancel sign-in; blocked, closed, expired, setup-unavailable and
partial-access states each have an honest next step. Cancel clears the transaction
and invalidates/advances the auth generation; it does not stop unrelated work.
Reacquire the actual permitted origin before restoring route/focus. Rich origin
and draft restoration remain build requirements rather than callback guarantees.

UX15 records the protected `7eac…` implementation observed on October 5.
At the November 5 pin, standard bootstrap composes the existing optional
Launch binding and independent selected-session host; their configuration,
authentication and platform limits are in the source map above. The Launch
receipt still requires `dispatched=false`, and its own message/STOP mappers
remain null. The historical guide's Work drilldown/clocks, labeling,
form/adapter, cancellation, scoped-draft, keyboard and startup-recovery gaps
are retained as the design baseline. This documentation reconciliation does
not claim those product journeys have been implemented or accepted.

The specification includes actual Paper action anchors, source-owner mappings,
transition and recovery matrices, illustrative fixtures and fifteen
implementation acceptance scenarios, extended for directory identity, message
stages, source reading/reuse, draft revision, bounded evidence recheck, partial
access, cancellation, project filtering/return, selected Work/evidence return,
private entry/browser recovery, current command limits, IME and actual focus restoration. These scenarios and their
extensions were not executed by the design continuation. No new app-scenario
execution is claimed by this documentation repair. The older read/auth-only
bootstrap and blanket Send-absence descriptions are historical; the current
source includes the separately guarded composition described above. Source
presence alone does not establish installed Search/Knowledge/source reuse,
effective Send/STOP, named project creation, decision recording, full history
or accepted execution continuation. Fresh-read the current owner carrier and
source custody before action work; historical #1046/#1150 draft status is not
a current permission or release. This design documentation clears no live
command boundary. Paper screenshots do not prove installed UX or product
acceptance.

The design handoff records unresolved Paper copy and note-text responses on
their original targets. No verified KD02 product variant is claimed. UX09 holds
the reviewable added-state, mobile-payload and details specifications; the full
contract also records the pending mobile header correction. Those exact target
writes remain paused until the original operations are reconciled. Other
completed screens and notes retain their reviewed state.

### Original external design effects remain unresolved

- Paper `mm-knowledge-flow-added-state-shells-20261004-001`: duplicate
  `SPU-0` / `STU-0`; original reply unreadable and not retained —
  **EFFECT_UNKNOWN**. Unchanged counts are not proof of no effect.
- Paper `mm-knowledge-guide-mobile-chrome-amendment-20261004-001`: note
  `T0J-0`; retained connection timeout — **EFFECT_UNKNOWN**. Previously
  observed text does not settle the original write.
- The separate historical broad Figma component-creation request was an
  explicit platform safety refusal, **EFFECT_NONE / NO_RETRY** absent material
  platform recovery. It is not one of the Paper unknown effects.

No verified KD02 variant, completed mobile payload/details/header amendment,
Paper/Figma recheck or retry, authenticated Send acceptance or newly executed
app scenario is claimed here. P-series custody and all existing design/runtime
holds remain with their original carriers.

## Web SSO restoration candidate (review required)

The web client now attempts hidden-frame authorization-code + PKCE (`prompt=none`) on
startup and after silent tokens expire. The fixed callback hands a code only to a
same-origin, state/source-checked parent. Access tokens remain in memory, with no
refresh token or bearer serialized into browser storage. A nonsecret localStorage
logout marker prevents an explicit local sign-out being undone by page reload;
interactive sign-in clears that marker. Resource audiences remain distinct.

This is **best-effort SSO restoration, not unlimited sign-in**: third-party cookie
blocking, Auth0 session expiration, tenant iframe restrictions, revocation, and
browser profile cleanup can require interactive sign-in. Full persistence across
those conditions requires a separately reviewed first-party/BFF session owner or
qualified rotating refresh-token implementation, with explicit revoke/logout,
rotation and server-side revocation guarantees. Native macOS Keychain renewal is
the implemented first-party path for the installed app since the 2026-11-09
rollout (see `docs/native-persistence-rollout-20261109.md`); the browser web
client remains on in-memory SSO restoration. Source tests do not prove live
Auth0 tenant behavior.

## Same-tab fallback when the live edge forbids silent frames (stacked draft)

The existing production edge serves `default-src 'none'` without `frame-src`,
and its callback sets `frame-ancestors 'none'`. Consequently hidden-iframe
Auth0 restoration is currently **blocked by CSP**, independently of cookie
availability. The follow-up web-auth candidate does not weaken those headers.
It detects a frame-source CSP denial and, **only for a browser profile with a
previously completed Workspace login**, attempts a single top-level
`prompt=none` PKCE authorization on the fixed Auth0 issuer. The registered
same-tab callback validates state, client, issuer and TTL, scrubs its code and
exchanges it privately before the React app mounts. A nonsecret prior-login
hint and one-attempt marker live in browser storage; tokens never do. Failed
Auth0 SSO restores the ordinary manual sign-in path without an endless loop.
Explicit logout prevents redirect, including if a subsequent popup is blocked.

**This only reacquires the Workspace acquisition audience**: the separate
Content and optional Executive grants can remain unavailable if their iframe
attempts are also blocked. The existing user-initiated Auth0 popup may recover
those scopes. The subsequent OS static-response candidate narrowly permits
`frame-src` to the exact pinned Auth0 issuer and its own callback origin on the OS app, and allows only
the exact OAuth callback to be framed by its own OS origin (`frame-ancestors
'self'`); the app shell and all other assets remain `frame-ancestors 'none'`.
That repairs the OS-controlled CSP denial without permitting arbitrary
embedding. It does **not** alter the Auth0 tenant, its own iframe policy, browser
third-party cookie restrictions, or the deployed edge until installed and
verified. True unattended, all-resource, cross-restart persistence in
privacy-restricted browsers requires an independently reviewed first-party
Auth0 custom domain + scoped CSP changes or a secure cookie/BFF credential
custodian. The redirect fallback and CSP candidate are scoped incremental
repairs, not substitutes for those release/tenant and real-browser acceptance
requirements.

### Authentication restoration and multi-tab safety follow-up

A prior Workspace user whose token expires can try the same **single bounded**
first-party browser-tab `prompt=none` authorization fallback after the
iframe's CSP failure, subject to the user's existing Auth0 cookie/session and
standard expiry policy. A tab that observes an explicit logout from another
tab immediately invalidates its private bearer owner, read generations and
Executive/Research capabilities; it never converts logout into an automatic
new sign-in. Manual Workspace and Research logins reauthorize only after a
successful new grant. Complete Content/Executive renewal remains a distinct
first-party backend/session-owner or qualified Auth0 integration gate.

**Unsent work and automatic authentication:** OS keeps an in-memory navigation
hold on unsent Office and Conversation notes, Session messages, Launch goals,
and unresolved command effects. An automatic Auth0 top-level redirect is
deferred while any such work is active, rather than silently discarding it.
This is a user-data safety gate, not an implementation of indefinite login;
a saved/finished draft may be followed by explicit sign-in or page reopen.
All draft/credential storage, live Auth0 tenant, Content/Executive authorization
and deployment remain with their existing qualified owners.

**Browser-session expiry and privacy:** On an unambiguous passive web token
expiry, user-authored unsent Office/Conversation/Launch/Session text is kept
only in the mounted page until explicitly copied, discarded or replaced by
new authentication. Source data and command authority remain invalid. Both
same-tab and cross-tab logout immediately clear the retained text even if
browser quota prevents writing the logout marker. No draft or credential is
persisted as a workaround for third-party-cookie restrictions.

## Native Keychain refresh-token persistence candidate (not installed)

The macOS Tauri native client has a separate opt-in Auth0 refresh-token
candidate, compiled only with `MM_NATIVE_REFRESH_ENABLED=1` **after**
the existing native public Auth0 client and the Workspace acquisition/content
APIs have been verified to permit `offline_access`, rotating refresh tokens,
and the intended expiration/revocation policy. With the option absent, the
protected native behavior is unchanged: in-memory access tokens only.

In the candidate, the native credential owner stores individual rotating
refresh tokens by client/audience in macOS Keychain; access tokens are never
stored in React or Keychain. Native reads and startup restore per-resource
credentials without requiring the login popup after normal application restart.
Only the acquisition and content grants participate. Executive SEND authority
does not acquire offline renewal by default. The owner serializes refreshes
per resource and records a Keychain pending marker before a rotating exchange;
a crash or unknown response refuses replay and requires explicit sign-in.
Sign-out invalidates the generation and deletes both credentials and markers,
returning an error if deletion could not be confirmed.

**Limitations:** This is source code pending native macOS build/test, independent
security review, configured tenant/client readback, signed installed-app restart
and Keychain access-control acceptance. Keychain locked/refused, token revocation,
absolute/inactivity expiration, ambiguous token rotation, or damaged credentials
can still require interactive sign-in. Never represent the candidate as a
permanent or irrevocable Auth0 login.
