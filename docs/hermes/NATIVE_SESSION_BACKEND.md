# Native Hermes session backend

## Status and consumer

The source composes the pinned native Hermes GatewayRunner inside the existing
Hermes ServiceRuntime child slot, the authenticated Secretary gateway and
SessionBridge/Runtime request family, and Office's explicit native Secretary
SEND/reply/recovery path. Source composition does not establish installation,
provider authentication or a production conversation.

The existing role/proxy installation and activation hold remains in force.
Focused source tests use explicit native-authority and custody doubles. They do
not prove provider authentication, a model turn, Linux PID1 policy, or browser
acceptance.

## Ownership

- Executive OS retains admission, the frozen installation input, and the
  immutable installed-release owner.
- ServiceRuntime retains its existing bounded supervisor/restart lifecycle.
- Pinned Hermes GatewayRunner owns SessionAuthority, tickets, native sessions,
  durable admissions/results, mailbox recovery, and native shutdown.
- The Secretary adapter registers one closed verb on the runner's existing
  private control socket. It creates no listener, durable queue, identity
  database, session registry, or retry controller.
- DeepSeek and the other supported model choices remain explicit provider
  selections under the existing model contract; selecting a provider does not
  introduce another runtime owner.

Upstream identity:
[NousResearch/hermes-agent at 1c0cd667746d3395fe9e1b6c74f8f85952486f18](https://github.com/NousResearch/hermes-agent/tree/1c0cd667746d3395fe9e1b6c74f8f85952486f18).

## Explicit selection and launch

Legacy profiles retain their serialized form and standalone backend. A native
profile explicitly selects `gateway.backend: native-session-authority`, an
existing native provider ID, the role's existing private address, and distinct
fixed gateway/backend ports. An omitted or unqualified native installation
refuses before a model credential is read or a child is launched.

The native child uses the real owned launcher named `hermes` with the actual
arguments `-p <role> gateway run --external-supervisor`. This preserves upstream
process recognition. The selected interpreter runs with `-I -S -B`; the release
entry verifies CPython 3.12, the installed startup recipe, actual process image,
role identity, source bytes, and import namespaces. The child rechecks the
existing PID1 role cgroup, credential isolation, address profile, and Landlock
port policy before importing native code.

Native startup normally moves its project root to the front of `sys.path`.
The release entry establishes precisely that approved order before its existing
source finder freezes the path. Other native dependency roots are explicit,
immutable installation inputs. Site startup and ambient package discovery do not
supply authority. The distinct role UID receives process-scoped Git trust for
only the qualified vendor path, so upstream code identity can read the root-owned
checkout. User/system Git configuration and optional index-refresh writes are
disabled for these native commands; no global safe-directory setting is changed.

The owned API factory wrapper takes only the original runner and passes the
selected role address and fixed backend port to the original native factory.
It preserves the returned native handle and normal lifecycle. Native vendor
classes and files are not rewritten.

## Frozen dependency inventory

The optional `native_gateway` member of each existing installation role row has
a closed schema:

- Selected Python path, real path, and expected executable digest.
- Existing no-site startup recipe.
- Pinned vendor root and an ordered, bounded list of import roots.
- External inventory path, independently frozen SHA-256, and size.

The inventory schema is `mastermind.hermes_native_dependencies/v1`. It lists
the complete selected namespaces, including directory membership, file modes,
sizes, and hashes. Root-owned files must be readable and directories traversable
by the distinct service principals. Symlinks, multiple-link files, ACLs, unknown
members, unexpected bytes, and namespace drift refuse qualification.

The existing Linux enroller calls the release owner's
`prepare-hermes-dependencies` operation after the immutable first-party release
reaches its final path and before gateway configuration/unit selection. Both
new-release and exact-adoption paths perform this step.

An existing inventory is adopted only through the frozen bytes and custody
checks; it is never overwritten. A missing inventory may be generated from the
prepared namespaces only when the deterministic candidate bytes match the
already supplied digest and size. Publication is exclusive, followed by fsync
and consumer verification. The inventory must be outside both the import roots
and the immutable Executive release. Its parent must already be qualified.

This step does not resolve packages, download dependencies, alter a live vendor
tree, or choose its own expected hash. Failure leaves an inert source release
and prevents the following gateway configuration/unit step.

## Secretary private-control protocol

The closed private verb is `mastermind-secretary-v1`; it exists only for
`mmsecretary`. The native private socket verifies the actual same-UID peer.
The handler also requires that exact native principal and supports three
operations:

| Operation | Behavior |
| --- | --- |
| `observe` | Read the exact owned session and current authority/profile/instance/revision/generation from native owners. |
| `submit` | Redeem an actual native interactive ticket, resume the exact target, verify returned lineage, then dispatch one finite `prompt.submit`. |
| `read_original` | Read the existing admission by its original principal, session, submission ID, input digest, and optional admission ID. Never submit to discover a result. |

The synchronous private handler schedules onto the runner's existing event
loop. The actual native `AuthorityConnection` runs inside native owner/activity
scopes. Native `StdioTransport` writes to a capped request-local sink, not
stdout; the native storage owner retains the result. This adapter does not
supply interactive desktop approvals or streaming UI delivery.

Cleanup detaches the request's viewer through `AuthorityConnection.close()`
without a session end reason, then seals the sink under the same write lock.
It does not cancel admitted work.

After exact resume, the adapter uses the native connection's submission parser
and the existing SessionAuthority finite-admission API. A request-local
authorization guard runs inside the native admission transaction, beneath the
owner's existing mutation lock. It rechecks principal, source instance, epoch,
revision, generation and local lineage on that same database connection. Native
idle checks exclude queued/running/unknown work, transcript leases and
compression. The native deduplication owner remains unchanged. Interactive
voice-stop shortcuts do not apply to this finite Secretary question path.

An admission receipt remains distinct from started or completed execution.
A lost reply, timeout, oversized result, or absent original admission after a
possible write is `EFFECT_UNKNOWN`; it never authorizes resubmission.
Historical terminal recovery retains the original principal and request
identity without requiring the old authority epoch to be the current epoch.

## Existing role gateway consumer

For a selected native Secretary profile, the existing role front door can expose
one closed POST path, `/api/secretary/v1`. It forwards the three operations above
to the actual same-UID native private owner. The optional credential
`HERMES_SECRETARY_CONVERSATION_TOKEN` comes from the existing role secret file.
It must be distinct from health, dashboard, provider, and every other secret
value, and is never forwarded to the native model child. The legacy gateway and
the health credential retain their read-only behavior.

The outer request schema is `mastermind.hermes_secretary_role_request/v1`,
with exactly `schema`, `implementation_sha`, and `request`. The selected
immutable first-party source must match before dispatch. The response schema is
`mastermind.hermes_secretary_role_response/v1`, with that source identity
and the native result. HTTP callers supply no native interactive ticket.

Framing, duplicate keys, request size, response size, source continuity, selected
role home, and child readiness are checked. The handler sends once. Failure after
a possible native submission remains uncertainty; neither the HTTP path nor the
native client retries it. The supervisor keeps its originally qualified role
home across child restarts and refuses an unexpected home change.

The native entry preloads the qualified `urllib3.util.connection` dependency
after role isolation and before upstream bootstrap. This preserves upstream's
native socket patch without allowing its lazy compatibility finder to precede
the installed source/YAML owners.

## Selected child result read

The native selected-child tool uses its existing selected_child_status request
and original frozen command. Executive Control resolves the Attempt owned by that
command, obtains Runtime.validated_role_completion, and reduces the same
terminal candidate used by the existing return owner. For a verified completed
work/repair child, its response can include a closed result_capsule with the
original command, job, Attempt and root; complete summary and next actions; and
the existing result, terminal, artifact, validation and grant receipt digests.

The capsule is limited to 32 KiB of serialized UTF-8. No text is sliced. If a
valid synopsis exceeds that budget, the response preserves completed metadata
and returns EXECUTIVE_RESULT_CONTENT_TOO_LARGE without a capsule. An absent
capsule is not evidence that the model has read the full result.

The shared receiving decoder joins the capsule to the outer original
observation. The native transport and final handler recheck currentness and
caller lineage after the read before exposing content. A late change withholds
content and retains the original command. parent_consumed: false means this
read did not write a consumption, acceptance or acknowledgement; it makes no
claim about another owner's earlier actions.

This completes a result-reading path inside an already retained native turn.
It creates no model call, polling loop, wake, new Attempt or acceptance event.
It does not automatically resume a conversation whose turn has ended.

## Remaining product integration

The closed Secretary mTLS request family, Runtime commit/recovery variant and
explicit Office question/answer consumer are source-composed. The remaining
installed/product work is:

1. Select the actual protected release and finish qualified host preparation,
   credential-free role isolation and exact native enrollment.
2. Supply the existing secure provider inputs, qualify the selected provider
   turn and prove the authenticated production browser/native journey.
3. For autonomous return after a native turn ends, capture and rejoin its real
   originating request/turn through the existing owners. Never choose the latest
   request for a root or equate native UID/session identity with the Office or
   COO OAuth principal.
4. Complete the separately scoped Meta-CEO participant. The current private
   conversation adapter admits mmsecretary only; a role label does not enroll
   mmmeta or authorize it as a COO Attempt.

The installed role/proxy/provider/canary/cutover restrictions remain separate
from source completion. Independent review is not a blanket prerequisite for
this Web-session source work; required source/release rules and actual effect
reconciliation still apply.
