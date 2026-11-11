# Publish an exact successor gateway

The existing root `publish-os-gateway` operation supports a successor with one
additional optional digest. Without that option, the original first-publication
rule is unchanged: a terminal gateway receipt must be absent.

This operation does not install source, migrate Runtime, grant a principal,
start services, repair an interrupted publication, or change Control/worker
configuration. Complete the normal successor install and its own acceptance
first. The real gateway, Studio, root custody, source, current-config, stopped
Control/worker, Runtime and UID admission predicates still apply.

## Before publication

Select the actual installed protected successor R and its own qualified Launch
bundle. Preserve the genuine current policies, Workspace memberships/action
grants and Content/Steward settings. The dedicated Studio profile must be staged
through its normal owner from R and stopped; do not relabel the old source or
treat a running Studio instance as absent.

Read the exact current MCP config, MCP plist, commission grant and terminal
receipt. The existing receipt is at:

`/Library/Application Support/MastermindExecutive/config/os-gateway-publication-v1.json`

That fixed filename remains the current-receipt location for both supported
schemas. The predecessor must name a distinct release, match all three actual
target hashes, and join its retained source/build bundle. A later independent
configuration edit is not inferred to be part of that completed publication.
Such drift refuses and requires its actual owner to establish a coherent
transition; this operation never rewrites or fabricates the predecessor proof.

```bash
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$R/ops/executive_os/service-control.sh" \
  publish-os-gateway \
  --expected-sha "$R" \
  --expected-bundle-digest "$R_BUNDLE_DIGEST" \
  --expected-mcp-config-sha256 "$CURRENT_MCP_SHA256" \
  --expected-mcp-plist-sha256 "$CURRENT_PLIST_SHA256" \
  --expected-grant-sha256 "$CURRENT_GRANT_SHA256" \
  --expected-predecessor-receipt-sha256 "$CURRENT_RECEIPT_SHA256"
```

Every digest is taken from actual qualified bytes. The new option accepts no
path or release override and cannot be combined with `--expected-grant-absent`.
A wrong or absent receipt, changed file identity, unsafe custody, same-release
request or occupied predecessor archive refuses before a new target write.

## Evidence and interruption behavior

The existing `AUTONOMY_TRANSACTION` owner seals the predecessor bytes and its
physical identity with the original target preimages before publication. After
that intent is durable, it creates one exclusive root:wheel `0444` archive:

`config/os-gateway-publication-<predecessor-receipt-SHA256>.json`

The archive holds the original receipt bytes exactly. Its publication uses the
existing configuration-directory mutex and a kernel no-replace rename; an entry
that appears late is preserved and refuses publication. A retained phase binds
the archive's post-rename file identity before the first target changes. The archive survives normal
transaction cleanup; it is not an additional lock, registry or scheduler.
The current predecessor receipt remains unchanged until final replacement. The
successor bytes are fully staged and synced first. Under the existing mutex,
the owner then rechecks the retained marker, archive and exact predecessor
identity immediately before descriptor-relative replacement. Every target phase
also rechecks the original identity and archive. A same-byte replacement still
refuses. This serializes admitted publication owners; it is not an atomic
inode-CAS guarantee against an unrelated root writer outside that mutex.

A successful successor emits the same typed `PUBLISHED` / `OS_GATEWAY_PUBLISHED`
result. Its current receipt uses `mastermind.executive_os_gateway_receipt/v2`
and adds exactly `predecessor_receipt_sha256`; the existing v1 fields retain
their meanings. First publication still emits v1. A completed v2 receipt can
itself be the explicit predecessor of the next distinct release.

An interruption leaves the original transaction for the existing
`reconcile-os-gateway` command, using R, its bundle digest and the original
transaction ID. Reconciliation remains **postimage-only**: it does not repeat
target writes, reconstruct a missing archive, recreate a receipt or choose a
new predecessor. It can close a lost terminal acknowledgement only when the
actual successor receipt, all postimages and both retained predecessor copies
are present and consistent. Missing or partial effects remain UNKNOWN for the
same owner's reconciliation. Do not remove the receipt, archive or transaction
to manufacture another first publication.

After terminal publication, use the existing R `restart-gateway` owner and
normal public-edge cutover/activation. The restart preflight validates the
already-published R configuration and source; it grants no publication effect.
The one-shot S operational adapter remains S-bound. If macOS KeepAlive requires
normal cleanup at the strict UID gate, compose that genuine owner against the
actual R source; do not weaken the UID predicate or pass R to an S helper.
