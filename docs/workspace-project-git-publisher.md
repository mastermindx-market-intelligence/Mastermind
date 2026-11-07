# Fixed CREATE_PROJECT Git publisher

`control_plane.workspace_project_git_publisher.FixedProjectGitPublisher` is the
source implementation for one canonical project proposal. The private owner
supplies a fixed Macro clone/origin/default branch, the real canonical compiler,
action authorizer and permission stamp, actual publisher qualifier, PR owner,
and `principal_scope(VerifiedPrincipal)`. The last seam uses
`integrations.mastermind_workspace_app.owner_context.workspace_principal_scope`; a grant
receipt digest or public sign-in state does not identify an operation owner.
No credential is mapped from Workspace identity to Git identity.

The public methods are `publish(request, principal)` and
`reconcile(request, principal)`. The compiler returns the closed
`agentos.project_proposal.v1` envelope. Effect-bearing request IDs are exactly
`mmos-project-create-<40 lowercase hex>`. Work references are canonical
`WS:KEY`; the only writable record is `agentos/workstreams/WS-KEY.md`.
The isolated clone's index, HEAD, dirty files and default branch remain intact.
The implementation never merges, force pushes or writes the default branch.

The proposal branch hashes the actual Workspace principal scope, original
request ID and work reference. Payload fingerprints remain separate. Existing
local/remote branch or PR evidence sends repeated `publish` calls into read-only
reconciliation before new Git objects are built. The commit subject binds the
original request fingerprint in addition to exact parent, one-file delta and
content. Changing a payload under the same identity conflicts; it cannot create
a second branch or PR. An existing refused or uncertain PR creation is never
called again. The existing operation controller must preserve unknown pointers;
this publisher introduces no alternative operation store or retry authority.

`PROJECT_CREATED` requires a fresh upstream default-ref observation, fetching
that exact immutable commit without changing refs or FETCH_HEAD, an exact
regular-file blob match and a second upstream/current-permission check. Local
main and remote tracking refs are insufficient. `PROPOSAL_PUBLISHED` means a
verified branch plus actual matching PR receipt; it does not mean protected
merge or Runtime/session creation. `PREPARED` means retained branch evidence
without a PR receipt. Reconciliation with no visible evidence returns
`EFFECT_UNKNOWN`, never proof of no effect or permission to retry.

Authority, permission stamp, principal scope, injected owner identities, fetch
and push URLs, and upstream expected revision are checked immediately before
Git object/ref/push/PR writes. Revocation before the first object produces no
Git publication objects. Revocation after an attempted write remains unknown.
Git subprocesses use fixed argv/cwd and remove inherited location/index/object
and inline-config overrides. Every Git invocation disables replacement objects,
so a local replacement ref cannot falsify an upstream commit blob. A later
read/authorization failure after any attempted publication remains EFFECT_UNKNOWN.
Two independent reviewer regression probes verify these repaired paths. A distinct push URL refuses before publication.
Read failures are distinguished from a genuinely absent canonical path.

The original24 focused tests use temporary local bare repositories and inert PR owners.
They cover original publication/reconciliation, real upstream versus local
state, stable identity with changed payload, PR refusal without replay,
revocation before/after effects, malicious Git environment/push URL, exact
content/parent/path conflicts and preservation of unrelated caller state.
These are source checks; they do not attest a production Git credential,
installed authoring grant, protected publication, Runtime admission or a usable
conversation. Production composition must supply the independently qualified
owner seams and pass the scoped consequence review before any effect.
