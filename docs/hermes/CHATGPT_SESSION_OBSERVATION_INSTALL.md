# Installed ChatGPT profile-observation read

Status: source implementation and synthetic-path proof only. No live profile is enrolled by this change.

This extends the existing Executive MCP v3 and Session Bridge owners. It does not introduce
a browser controller, identity provider, session registry, transcript store, queue, service or listener.
Use it with the parent [session visibility master plan](../superpowers/plans/2026-11-06-chatgpt-session-observability.md)
and the [owner-wiring plan](../superpowers/plans/2026-11-06-chatgpt-web-observation-owner-wiring.md).

## Actual route

An authenticated `session_web_observe` call obtains an independent exact-principal grant
from the existing root-sealed Executive installation. The same installed Session Bridge client
submits the closed, READ-only `session_web_census` frame through the existing CeoIngress socket.
The Control-side owner independently reloads that same installation, qualifies its own process
identity and the original profile binding, and calls the original C2 `census_via_extension` once.
Both sides recheck permission/currentness before releasing a bounded observation projection.

The private operation is not a public MCP tool and has exactly empty arguments. No caller can
select a source path, socket, browser/profile, owner UID, grant, role or policy through it.
`session_continuity_read` is not installed by this slice: #2178 owns the adopted Agent OS reader.
Exact original-response reads and governed continuation retain their existing independent owners.

## Configuration, absent by default

Only the existing root-sealed `mastermind.executive_mcp_install.v1` document can contain
the optional `session_web_observation` member. It is accepted only for `web_ceo_v3`.
No installed file is changed by importing, testing, or publishing this source.

| Field | Exact meaning |
| --- | --- |
| `schema` | `mastermind.session_web_observation_install.v1` |
| `source.binding_id` | Canonical UUID of one existing original C2 navigation binding |
| `source.adapter_instance_id` | Independently authorized lowercase 64-hex managed-profile identity |
| `source.profile_owner_uid` | Exact non-root integer UID that genuinely owns the profile context |
| `permissions.generation` | Explicit lowercase 64-hex owner generation; rotate on every permission change, including restoration |
| `permissions.principals` | Zero to sixteen explicitly granted principal rows; empty means no authorized profile observations |

Each principal row contains exactly `policy_id`, `issuer_digest`, `resource`, `subject_digest`,
`client_ref`, and `adapter_instance_id`. Digests are lowercase 64-hex; the adapter must equal
the one frozen source. Policy/resource/issuer/subject must match an existing installed
READ-capable ResourcePolicy. `client_ref` must be the exact already-verified OAuth client digest,
not a role name, bearer token or the unavailable-client sentinel. A submit-policy principal is
eligible only if separately named by that exact policy; it does not inherit a read-policy row.
This read does not grant SEND, wake, admission, target registration or execution.

Do not derive rows from a tab list, a Slack role, a remembered account name or a model assertion.
Two bots/sessions sharing the same actual OAuth subject/client are the same principal for
this permission boundary. No authenticated group or ChatGPT-account identity is asserted.

## Physical ownership and revocation

The MCP network process never opens the browser socket. The private collector requires
`getuid() == geteuid() == profile_owner_uid` **before any profile I/O**, and confirms the
process home rather than changing HOME or borrowing another user's credentials.
The incumbent standard service templates use network UID458 and Control UID450; a
desktop browser owned by another user therefore remains unavailable through that placement.
Setting a number in the configuration does not create an authorized physical channel.

The existing bindings file must be private, non-symlinked, owner-correct, bounded and stable.
Loader warnings refuse. Exactly one binding must match, and its derived adapter must equal
the independently granted source. The original client still derives its own private socket;
its parent/socket must belong to the same owner. Descriptor-bound ACL checks protect the
binding file and profile ancestry. Only the exact harmless macOS home deny-delete ACL is
accepted. Unix sockets themselves cannot be opened as regular ACL descriptors; their
owner-only, ACL-free private parent prevents foreign traversal. The original private socket
challenge, nonce, request window, receipt validator and native host remain unchanged.

Only `permissions` may rotate while installed; source coordinates, authentication policies,
release identity and credentials remain frozen. Each permission revision includes the
actual sealed configuration file's device/inode/mode/owner/link-count/size/mtime/ctime and
the closed permission/source document. Replacement or same-grant rewrites invalidate old
in-flight revisions. Removal, malformed state, source drift, token expiry, changed Runtime
binding or detected revocation suppress the whole result. There is no last-good cache.

These are before/after detection guarantees, not atomic revocation across two processes;
a read already in progress cannot be undone. Cancellation returns no captured data and
does not retry; its already-running read thread may finish within the original bounded deadline.

## Honest coverage and budgets

One selected profile is observed in this vertical, not a new fleet collector. The original C2
receipt covers normal open ChatGPT tabs in that profile. Closed/archived/private chats, account
history, transcripts and hidden reasoning remain outside this observation. A profile can be
logged into a different ChatGPT account without changing its adapter ID; this output therefore
must not be presented as all sessions belonging to the Executive OAuth principal.

- One eight-second end-to-end monotonic budget begins before thread dispatch, inside C2's
  ten-second ceiling and the incumbent private client's ten-second read timeout. Custody work
  consumes that budget; C2 receives only the remaining window. A request-local cancellation
  fence prevents a stalled preflight from starting a fresh census after the caller has left.
  No retry or fallback is added.
- The original native receipt allows up to 128 rows/61,440 bytes. The existing private
  transport is only 32 KiB: this owner reserves 2 KiB for framing and explicitly refuses
  an oversized result. It never silently truncates the closed native receipt.
- The public projection independently returns at most 64 rows and preserves omitted counts,
  coverage, duplicate/stale/unknown cues and the existing 64-KiB output ceiling.
- The whole installation member is bounded to 32 KiB; its root-sealed parent file must be
  at most 256 KiB for this optional read. The profile bindings file has a 512-KiB outer bound.

## Qualification and rollback

Source tests exercise real signed HTTP, the actual Control factory and private socket, the
original Python C2 client/native host and original Node collector with synthetic browser APIs.
They do not prove live profile enrollment, actual Meta-CEO/Secretary grants or installation.
Do not reset, restart or overwrite the working GLM leadership profiles to make these tests pass.

Before live acceptance: select the original authorized profile-owner channel; qualify the
sealed source/configuration on both existing processes; independently grant the actual role
principals; then read two explicitly enrolled test sessions with no SEND. Confirm omissions,
expiry, revocation and both roles' consumption from the actual installed paths. #836's active
browser/runtime owner and #2172's native consumer are not modified or superseded here.

Rollback begins by withdrawing the permission rows with a new generation through the same
installation owner; ongoing detected-old reads withhold results. Removing the optional block
makes old reads unavailable; restarting the existing process without it removes the optional
tool from the catalogue. Do not remove existing session/reply capabilities or create another runner.
