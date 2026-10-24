# Control-owned read-only child workspaces

The normal paid-enabled COO Service composition supplies the fixed host policy
`mastermind.coo_readonly_child_workspace/v1` to **new** roots. Public intent
constraints cannot supply it. Existing roots, Jobs, assignments, host-binding
digests and write-capable cycles keep their original behavior. There is no arm,
socket command, caller path, receipt DTO or migration that promotes an old root.

This initial profile permits only READ/RESEARCH roots and leaves, with no write
paths or validation commands. Incompatible root grants refuse before any Job or
Event is created; authorities are never silently stripped. Work, independent review and repair Jobs each receive a
separate deterministic `job-NNN` credentialless clone and branch, committed in
the existing Job before execution. Coordinators and planners keep the existing
root workspace. The original root, parent, budget, reserved Job/Attempt counts,
worker quotas and authority checks remain the existing Runtime owners.

## Allocation and uncertainty

The normal serialized Service dispatch calls
`JobRegistry.prepare_coo_child_workspace` with its qualified source repository
and shared GID. The Runtime appends `COO_CHILD_WORKSPACE_REQUESTED` before calling
the existing local allocator. Only that allocator's same-call private return can
produce `COO_CHILD_WORKSPACE_COMPLETED`; both records use the existing immutable
Events store. The completion binds the root/parent/child/role, creation payload,
authority-policy hash, exact source commit, source directory custody, assigned
branch/path and actual independent `.git` directory and metadata identities.
It also requires a clean checkout, exact HEAD and the existing shared handoff.

Same-Job replay after a completed allocation validates and returns the original
assignment. It never clones again. A REQUESTED record without COMPLETED is an
unresolved physical operation, including a failure before creation, a partial
clone, lost reply, cancellation or process loss. It cannot automatically retry,
adopt a coincident path, delete a clone or manufacture completion. Existing or
foreign paths and forged return objects refuse. A changed clone/source, Git
metadata, branch/ref, remote configuration or content refuses before claim.

Claim-time validation independently requires the committed allocator provenance,
including for a direct Runtime dispatch that bypasses the Service method.
Service revalidates the assignment and the existing Supervisor consumes the
child Job's actual worktree in its launch specification. All clone allocation is
local Control work; no Git remote acquisition, credentials or additional lease
is introduced.

## Review and scope

Each review clone uses the exact root source commit and the existing typed
reviewed-result input. Its assignment binds the subject Job, authenticated
completed Attempt and role-result digest. A repair additionally binds the actual
rejected review and its completed result digest. It does not silently review a
different root, writable subject or shared clone. This is an analysis journey;
it is not a source snapshot/merge protocol for code-writing children.

The canonical paid worker still receives sealed text only and has no remote
filesystem or tool authority. Its separate clone is Control-owned source
custody, not evidence that the remote model can read that filesystem. A genuine
Codex reviewer uses its own clone and the sealed paid result. Original-parent
aggregation and visible return continue through the existing result owners.

The offline tests exercise authenticated HTTP/AF_UNIX admission, actual temporary
Git repositories and allocator, real Runtime/Events/claims, normal Service
dispatch ordering and real Supervisor launch-spec/result code. Provider/process
observations and attendance/host-binding inputs in those fixtures are inert and
explicit; they do not establish live capacity, identity readiness, enrolled
workers, arms, live H1 completion, H5 permission proof, H6 failure/repair proof or
the full programme. Installation and any real mission require their separate
qualified existing gates. The held historical workspace worker and unread
artifacts are neither consumed nor replaced by this local source change.
