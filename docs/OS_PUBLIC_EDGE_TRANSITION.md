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
