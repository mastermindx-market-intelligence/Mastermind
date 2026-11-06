# Native Hermes session backend

## Status and consumer

This source slice composes the pinned native Hermes GatewayRunner inside the
existing Hermes ServiceRuntime child slot. It supplies the native owner and the
bounded Secretary admission/recovery adapter needed by the Office conversation
path. It does not claim that Office, the remote gateway, or a production role is
already using that adapter.

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

An admission receipt remains distinct from started or completed execution.
A lost reply, timeout, oversized result, or absent original admission after a
possible write is `EFFECT_UNKNOWN`; it never authorizes resubmission.
Historical terminal recovery retains the original principal and request
identity without requiring the old authority epoch to be the current epoch.

## Remaining product integration

The following consumers still need composition before this is the complete
Office Secretary journey:

1. A distinct existing-secret-owner conversation credential and the closed
   Secretary request family on the existing role gateway/mTLS transport.
2. The native request/return variant in the existing SessionBridge and Runtime
   aggregate, including a durable commit-started event before possible native
   admission and original-request recovery after refresh.
3. Office's selected mission question/answer flow using those actual receipts,
   without fabricating Fabric Attempt, worker, Slack, or wake identities.
4. Qualified host dependency preparation, role isolation witnesses, the
   selected provider turn, and the authenticated production browser path.

These are integration and execution requirements. Independent review is not a
blanket prerequisite for this Web-session source work; required source/release
rules and actual effect reconciliation still apply.
