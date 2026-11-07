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

The closed Secretary and Meta mTLS families, Runtime commit/recovery variants
and explicit Office question/answer consumers are source-composed. The remaining
installed/product work is:

1. Select the actual protected release and finish qualified host preparation,
   credential-free role isolation and exact native enrollment.
2. Supply the existing secure provider inputs, qualify the selected provider
   turn and prove the authenticated production browser/native journey.
3. For autonomous return after a native turn ends, capture and rejoin its real
   originating request/turn through the existing owners. Never choose the latest
   request for a root or equate native UID/session identity with the Office or
   COO OAuth principal.
Source support for both roles does not authorize a COO Attempt or establish
an installed Meta conversation.

The installed role/proxy/provider/canary/cutover restrictions remain separate
from source completion. Independent review is not a blanket prerequisite for
this Web-session source work; required source/release rules and actual effect
reconciliation still apply.


### Installed enrollment compatibility

The existing finite enrollment command accepts both the held v2 enrollment
recipe and the held v3 recipe with an Executive consumer. Each repeated profile
qualification checks the exact consumer-aware native configuration from that
same held recipe. Earlier recipes without an enrollment capability remain
disarmed, and only qualified absence can create the original session.

The v3 renderer preserves the approved, disabled Steward environment placeholder.
The added Executive MCP connection and plugin grant separately reject bearer
material; neither carries a credential. This source compatibility does not
execute an installed enrollment or satisfy the held host/provider proof.

### Explicit Meta native enrollment

The existing native enrollment and private-control owners now select one closed
role contract: mmsecretary or mmmeta. The Meta command is enroll-meta-session;
its enrollment receipt, private verb and result schema are distinct from the
Secretary's existing wire values. A runner installs one selected role, and a
client refuses a sibling-role result before opening the private socket.

Held v2/v3 installation recipes select the matching command and bind consumer
role, enrollment request and Unix principal. The prior Secretary command and
recipes retain their defaults. No role service is enabled by this source change.

The isolated release bootstrap stages bounded consumer data without importing
first-party modules. It then runs the existing publication validator through the
held source loader, checks exact candidate identity and qualifies native
dependency bytes while only the original stdlib paths are visible. The same
source owner survives two finite import scopes; each finder freezes its own
expected paths and continues to refuse drift. Dependency preparation performs
the same semantic checks before preparing its inventory.

Focused proof includes actual command/renderer qualification, original native
enrollment recovery with owner doubles, and fresh isolated Python runtime and
dependency-preparation entries with explicit held-descriptor/effect doubles.
These checks are source evidence, not installed enrollment or a provider turn.

### Explicit role conversation gateway

The existing gateway selects one finite role contract at construction. Meta uses
/api/meta/v1 and its own role/native schemas; Secretary keeps /api/secretary/v1
and its existing schemas. A request cannot choose or change that role. The same
supervised child, profile home, source owner and private-client identity are
checked before and after dispatch, including uncertain submission outcomes.

The existing secrets owner selects the corresponding role conversation token.
A sibling-role token in the role's secrets file is a preflight refusal, even
when no selected token is present. Both conversation tokens remain reserved from
child registration and are unconditionally excluded from child environments.
The selected credential cannot alias gateway, dashboard or provider authority.

Listener-bearing v3 status retains its existing shape and exact role field. The
only accepted listener pairs are mmsecretary/127.0.0.2 and mmmeta/127.0.0.3. Both
fresh listener measurements and both main-process custody measurements remain
required; profile configuration is not a socket witness. Earlier v1/v2 status
formats and default Secretary behavior are unchanged.

The source tests exercise HTTP through the actual native private-client wire
using a socket pair, cross-role refusals, startup wiring and measured-listener
doubles. The following sections supply remote and Office source composition.
Installed service/provider qualification and activation remain separately owed.

### Dual-role remote transport and preserved composition

The incumbent mTLS listener accepts two closed conversation families. Meta uses
mastermind.remote_hermes_meta_request/v1 and its matching response/native-result
schemas. The client binds one family, host, original root/session and exact
configuration/source digests before connecting. Wrong-family calls fail before
connection; after a possible submission, failures retain their existing
EFFECT_UNKNOWN classification. No retry, admission queue or second listener is
introduced.

Gateway config v4 selects metadata plus separate Secretary and Meta conversation
bindings at the existing canonical conversation-config path. Each role has its
own fixed credential path. The same protected file reader enforces root/group
custody, mode0440, one link and descriptor identity. Equal retained token values
refuse before the listener starts. The forwarder qualifies only its selected
role's current main process and exclusive kernel listener, so an inactive sibling
does not invalidate that role. The paired metadata observer still reads both.

Fabric composition v5 adds an explicit Meta member to v4. Both roles must join
the same qualified metadata host, transport and configuration/source pins.
Their native session/responsibility selections remain independently bound. Existing v1-v4
documents retain their interfaces and defaults; absence of Meta has no fallback.

The existing Control component writer now carries complete qualified conversation
members through initial qualification, compiler inputs, publication and recovery.
An incompatible metadata source change refuses before a transaction is claimed.
Recovery derives its policy from the original sealed candidate: v4/v5 preserve
their matching original members, while an older v3 transaction retains its
original bytes. It never selects replacement inputs or republishes an artifact.

These are source integration changes. Installed credentials, role services,
provider admission and production Office behavior require their own qualification.

### Meta Runtime continuation and original-result recovery

The same pure continuation owner now joins one of two immutable schema families.
Meta uses the hermes_meta target prefix, its own binding/target/operation/request/
commit/public-result schemas and the session-meta submission prefix. Secretary
keeps all existing wire values and defaults. The common request/commit Event
types, command prefixes, aggregate and Runtime writers remain unchanged.

A family is resolved from exact validated kind or stored schema, never inferred
from an unknown value. The binding, target material, operation digest, submission
and commit must agree on that family. Public results join the stored original
family, native result, target, operation and original read/request references.
Answer budget, original admission checks and parent_consumed:false remain intact.

The installed Session Bridge explicitly discovers either enrolled role. A missing
Meta selection returns no Meta target; it never selects Secretary. SEND still has
exactly four fields. Original command recovery precedes fresh target observation
and submission, and the synchronous original commit precedes possible native
bytes. Recovery reads the original stored binding and preserves journal facts
when that route cannot answer. Both native families refuse the legacy live-writer
path before Attempt/worker lookup.

The existing bounded Runtime history can return legacy, Secretary and Meta
original references together under the same principal, scope and pagination
rules. The public session_reply_read owner validates both closed result families.
The session_targets tool advertises the explicit Meta kind; installing this source
therefore owes the normal exact tool-publication identity qualification. This
change does not republish a live tool or activate a role.

The Office/native consumer is described below. Authenticated installed-provider
proof remains separate from this backend source integration.


### Explicit Meta in the existing Office and native path

The existing Session target selector offers Fabric, Hermes Secretary and Hermes
Meta-CEO. The exact selected kind survives its current URL route, context
qualification and native command. A kind change uses the existing selection
epoch; unresolved original operations keep that selector locked. Unsupported
or absent Meta context stays unavailable without querying another role.

The TypeScript and Rust SEND grammars still accept exactly target_ref,
operation_key, instruction and stop_condition, with unchanged text bounds.
The same authenticated BFF calls the installed Bridge once. It validates the
native family through the Runtime producer and joins the returned target and
operation to the requested original. READ uses only the original operation key;
a missing current target does not replace that operation or prevent an otherwise
qualified original read.

The frontend keeps the original Secretary exported interfaces and adds Meta
peers with shared native unions. Schema, target prefix and operation domain must
resolve to the same family before a native result is displayed. Actual native
success/failure, answer text and original references survive unchanged; native
answers have no fabricated next step and parent_consumed remains false.

Both native kinds use the same existing IndexedDB principal slot, database
version, record shape and atomic compare-clear. The original pointer clears
only after its qualified answer actually commits to the current view. Historical
Fabric/Secretary/Meta answers use the same bounded reference/read path and cannot
clear another pending operation. The UI compares the actual success value as
well as native family, text and original reference.

A late native phase is retained under the requesting controller's captured
binding, principal, generation and selection sequence. Replacing a live host
cannot transfer a previous controller's phase to the replacement identity.
The existing auth and committed-view checks also apply before presentation.

Source proof exercises the actual pure native producers through the real signed
BFF, then consumes those exact fixtures through NativeClient, Host, App and the
durable pending store. The Secretary producer fixture remains byte-identical.
Focused cases cover both roles, refusal without fallback, lost-result recovery,
auth withdrawal, target disappearance, mixed history and replacement-host
presentation. These fixtures do not claim installed OAuth, provider execution
or browser acceptance. Local Rust execution remains deferred to the existing
native-macos CI check.
