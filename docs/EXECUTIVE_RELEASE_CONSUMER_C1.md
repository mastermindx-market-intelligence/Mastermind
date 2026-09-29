# Executive release consumer C1

This source connects the authenticated app, existing CeoIngress socket, serving
Control process, existing root broker and canonical Runtime approval Events.
It is a production-disarmed integration candidate. It does not install, upgrade,
roll back, claim maintenance, dispatch a worker or establish live qualification.

`create_release_control_app` is an explicit app composition with four closed
HTTP tool routes. Existing app/MCP profiles and their tool discovery stay
unchanged. No installed entrypoint selects this composition in C1. Release
commit always returns `RELEASE_COMMIT_DISARMED`, even with a valid token.

## Ownership and authentication

The existing JWT verifier authenticates the submit-scope token. Public arguments
cannot supply principal, grant, policy, target, path or command. The app projects
the verified principal, excluding the raw token and jti, onto the one existing
CeoIngress connection. Control captures and qualifies the installed Gateway
instance from its live socket in the serving process. Its thread receives a
same-process socket duplicate; no identity capture is serialized to a helper.

Control checks the connected root UID before sending on the fixed privileged
socket. The root broker independently qualifies the installed Control instance,
resolves the immutable transition from private owner composition, authorizes
against current installed policy and signs a closed approval. Control correlates
the original principal/action/operation and uses the existing Runtime
`record_approval`/`read_approval` transaction. There is no new table or ledger.
An exact replay returns the original sealed bytes and expiry. A changed effect,
foreign subject, altered seal, expired approval or revoked policy refuses.

The private snapshot callback must freshly verify installed policy, owner/key,
staged source/content, service identity, configuration and physical observations.
`ReleaseOwnerSnapshot.preconditions` supplies all closed precondition fields
except `approval_evidence_digest` and `grant_digest`; the root owner inserts those
two from the verified original approval. Snapshot identity is compared across
fresh observations before sealing/preparing. The current codec verifies the
seal again after the final snapshot. The callback is not exposed on the wire.

The codec takes already validated 32-byte key material. The existing Workbench
`ServiceConfig.action_key_file` and `_secure_action_key` define the owner-selected
key file format (64 lowercase hex, optional LF; exact 0600 and stable descriptor
checks). C1 adds no file format, key loader, provisioning or rotation. A future
installed root composition must additionally qualify root ownership, current
key/trust generation and stable installation identity. Workbench same-euid
validation alone does not establish those P4 facts. Root secrets never enter
Control, app frames, logs or Runtime Events.

## Preparation and recovery

Preparation verifies the original owner seal and current delegated authority,
then issues a private root-signed token bounded by wall and monotonic clocks,
the same boot, and the original approval's expiry (maximum 300 seconds).
It creates no reservation, Event, Job or Attempt. Control cannot sign a token.

Reconcile uses a separate fresh `ReleaseHistoryTrust` callback. It verifies the
original seal and subject/owner/target without requiring staged bytes or renewing
expired approval. The installed history owner must preserve resolvable trust for
unresolved families across rotation. An unavailable trust generation refuses;
it is not replaced with a new approval. The existing broker status reader is
queried once for the derived family id. C1 has no P4 actuator/terminal schema:
only `NOT_FOUND` is positively projected. A terminal/unknown historical family
without a qualified full P4 fingerprint returns `EFFECT_UNKNOWN`, preventing a
shortened-id collision with P2 from becoming a release-success claim. Existing
P2 status readers and effects retain their original schema and behavior.

Each transport sends once. Loss of a response remains `EFFECT_UNKNOWN`; it does
not trigger an automatic resubmit. Control retains physical work through client
disconnect using the existing owned-task/drain mechanism. The key and staged
factories are absent from the production broker by default, so approval and
prepare remain unavailable until the separate installed qualification.

## Acceptance boundaries

Tests drive actual signed JWT verification, a real Unix CeoIngress connection,
the real Control and broker handlers, real HMAC tokens, and real Runtime Events.
Only enrolled host/key/policy observations and installed-peer qualification are
synthetic. They are source proofs, not same-UID installed-peer proof.

Remaining release work belongs to the existing owners: Product's installed
qualification/profile/key and immutable staging composition; Hierarchy's
transactional maintenance exclusion; the fixed installer and sole terminal
writer; crash-boundary/reboot/recovery proof; and the native permitted release
journey. C1 neither claims those gates nor introduces another controller.
