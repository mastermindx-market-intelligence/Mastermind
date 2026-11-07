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

The consumer still selects one sealed manifest. The route union does not claim
dual-release byte serving or continuity for stale HTML. Saved Caddyfile startup
durability, unrelated TLS policy and service lifecycle remain separate owners;
none is changed by this module. Tests use actual byte qualification and the real
`OsStaticApp` with inert HTTP and explicitly substituted platform ownership. They
are source evidence, not production publication or host acceptance.
