# OS edge publication ordering

`python -m ops.executive_os.os_public_edge_publication --help` exposes four
explicit root-owner commands. Importing the module has no effect.

1. `stage-host` verifies the old sealed release and its real single-manifest
   consumer. It qualifies the new build using the existing protected-source and
   asset-bundle owners, and captures both releases, source/build provenance and
   complete configuration into a new private directory. Its returned digest
   identifies the complete stage. Root-owned transport to the existing VPS is a
   separate custody prerequisite; this receipt is not a remote signature.
2. `prepare` requires that exact stage, current listener PID, complete live
   preimage and ETag. It validates the exact candidate with `/usr/bin/caddy`,
   verifies the currently served OLD HTML/callback/assets, writes an exclusive
   durable intent, and publishes only the planner's old+new route union with
   If-Match. An exact full readback and durable receipt are required for PREPARED.
3. `verify-cutover` binds that original successful prepare receipt to the same
   stage, new source and new build digest. Only then may the existing sole host
   perform its separately governed whole installation. The publisher cannot
   install, switch the consumer, or call an installation callback.
4. `finalize` requires the original PREPARED operation, an unchanged prepared
   live configuration and fresh ETag, and actual NEW HTML/callback/assets from
   the exact listener before retiring old-only paths. It has a distinct exclusive
   intent in the same operation directory and the same readback requirement.

Any phase intent without a fully matching success receipt is unresolved. Files
are never replaced, cleared, refunded or replayed, including after a successful
POST whose reply/readback/receipt was lost. This module has no recovery command.
The existing release/source/authentication/host gates remain prerequisites; an
arbitrary PR, queue head or supplied `AssetBundle` is not qualification.

The current closed OS POST profile adds the native Executive endpoints
`/os/executive/direct-native/result`, `/os/executive/direct-native/consume` and
`/os/executive/direct-native/correction`. The existing backend owns bearer
authentication, principal/scope/expiry checks and operation admission. These
three exact POST paths retain the normal 64,000-byte bound and proxy headers.
All existing GET, Session SEND and MCP routes remain unchanged, as does the
separate 98,304-byte source-operation branch. The 31 existing method-specific
route pairs remain valid transition inputs, including the complete 39-POST
profile preceding these additions; a partial native-route upgrade is refused.

There is no same-source route-only publication command. `stage-host` still
requires distinct old/new source IDs and a genuinely qualified new protected
source and build. Its normal `prepare` can publish the closed route upgrade
while the old accepted release still serves the old assets; that receipt never
claims the new release is installed. The existing installation owner and actual
new served-byte checks still precede `finalize`. A completed historical stage
keeps its original source owner and immutable journal; this change does not
permit replay or relabel the old release as a new candidate.

The consumer still selects one sealed manifest. The route union does not claim
dual-release byte serving or continuity for stale HTML. Saved Caddyfile startup
durability, unrelated TLS policy and service lifecycle remain separate owners;
none is changed by this module. Tests use actual byte qualification and the real
`OsStaticApp` with inert HTTP and explicitly substituted platform ownership. They
are source evidence, not production publication or host acceptance.

## Public MCP route pair and the COO pair

The public edge carries two fixed public-MCP matcher branches, kept out of the
OS route profiles so a previously installed three-branch configuration stays
plannable:

| Matcher | Method | Paths | Upstream Host | Body cap |
| --- | --- | --- | --- | --- |
| `@mcpmeta` | GET | `/.well-known/oauth-protected-resource/mcp`, `/.well-known/oauth-protected-resource/mcp/coo` | `mcp.mastermind-x.com` | none |
| `@mcp` | POST | `/mcp`, `/mcp/coo` | `127.0.0.1` | 64000 bytes |

Metadata and transport stay separate: one GET matcher and one POST matcher, each
with its own path list, never a merged branch. The metadata branch presents the
public Host; the transport branch presents the gateway's loopback Host because
the gateway's SDK transport fence admits only loopback hosts. Both strip the
same fixed forwarding and client-identity headers and rewrite the forwarding
identity to loopback/https. The 64000-byte cap is the gateway's own ceiling and
is not 65536. Caddy performs no authentication, token handling or audience
check on any branch.

The receiving COO composition uses the shared OAuth resource
`https://mcp.mastermind-x.com/mcp`, with `/mcp/coo` as its role transport.
The canonical protected-resource metadata is
`/.well-known/oauth-protected-resource/mcp`. CEO and COO authority remains
separated by the exact scope contracts, the enrolled principal binding and
the existing role handlers.

The edge retains its accepted forwarding path for
`/.well-known/oauth-protected-resource/mcp/coo`, but the receiver does not
register that metadata alias and returns **404**. It does not establish a
second OAuth resource. This source composition does not prove installation,
live enrollment or a credentialed role turn.

The transition admits exactly two coherent public-MCP profiles:

- **CEO-only** — metadata `["/.well-known/oauth-protected-resource/mcp"]` and
  transport `["/mcp"]`. This is the exact installed predecessor.
- **Complete CEO+COO** — the two paths above in each list.

An observed CEO-only pair is upgraded in place to the complete pair; an already
complete pair is idempotent. A partial upgrade (one list complete, the other
not), a duplicate, a wildcard, an extra path, an extra method, a changed body
cap, a changed Host, a changed header-strip list, a changed proxy or a
reordering outside the incumbent accepted structure fails closed. A topology
with no public-MCP family at all never gains one: an unrelated asset transition
must not invent permission for a new MCP family.

The renderer checks the template's complete intended metadata and transport path
lists, not placeholder counts, so a template still carrying the CEO-only pair —
or one that widens either list — cannot be rendered at all.
