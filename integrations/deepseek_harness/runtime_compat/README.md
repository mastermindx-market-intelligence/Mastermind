# Current full-app runtime compatibility

This ports the accepted governed-tool boundary to the complete DeepSeek Harness
donor at `687f282e8625c6b8d11ff58211a90524be2e4317`. It does not replace the
native app, install an Executive route, or authorize a provider. The separate
[attended app package](../ATTENDED_DEPLOYMENT.md) retains the donor's existing
native provider/auth/session owners and does not depend on paid worker admission.

## Changes

- Opt-in `strictDispatchBinding` captures the original tool definition and result
  owner, then rechecks cancellation, guards and exact identity at the actual
  native staged scheduler body boundary. Non-opted-in behavior is retained.
- Governed MCP admission binds a frozen catalog and selected raw tool names to
  one live generation. Discovery replacement retires the old generation before
  suspension; failure rolls back registration and namespace ownership.
- The pinned MCP client SDK receives the exact `toolDefinition`, preventing its
  schema-mismatch retry. Governed rich results are refused before attachment or
  model-service processing. Ordinary native MCP behavior is retained.
- A bound ACP workspace reader declares the known Python MCP 1.28.1 legacy
  protocol to SDK 2.2.0. Other MCP connections keep native automatic negotiation.
  This avoids a speculative discovery sibling for that fixed target.
- `integrations/acp_worker/dsh_native_agent.mjs` joins the existing inherited-FD
  admission channel to one already-created native Agent. Its opted-in v3
  exchange observes that exact Agent/Session and binds the standard ACP session
  result before prompt admission. MCP discovery and the original owner ACK
  precede model work. Agent-owned restrictions survive MCP-fiber revocation.
  ACP remains the prompt/cancel/result lifecycle owner. Generic v1/v2 hosts
  retain their original contracts; the actual-Agent entry requires a v3 gate.

No donor checkout is edited. `prepare.py` verifies the clean pin, lockfile,
15 source inputs, patch identities and output hashes, then creates ignored
pristine/patched artifacts. A partial patch effect is refused for reconciliation.

## Reproduce focused proof

Use the already-built, dependency-installed accepted donor. This does not install
dependencies or use provider credentials.

```sh
python3 integrations/deepseek_harness/runtime_compat/prepare.py "$DSH_SOURCE"
cd integrations/deepseek_harness/runtime_compat
ln -s "$DSH_SOURCE/node_modules" node_modules  # fresh artifact directory only
DSH_SOURCE="$DSH_SOURCE" node "$DSH_SOURCE/node_modules/vitest/vitest.mjs" run --config vitest.config.mts
node build-native-fixture.mjs "$DSH_SOURCE"
cd ../../..
MMX_DSH_FULLAPP_NATIVE_SUPPLY="$PWD/integrations/deepseek_harness/runtime_compat" \
  python3 -m pytest -q tests/harness_convergence/test_dsh_fullapp_native_agent.py \
    tests/harness_convergence/test_dsh_fullapp_native_history.py
```

The Python environment needs the repository test dependencies and MCP 1.28.1.
Without the explicit native supply, the nine real-process tests skip; a skip is
not successful native-path evidence. The builder uses the donor TypeScript
decorator transform and verifies a single shared scheduler identity across the
native Agent and the admitted tool runtime.

Observed on 2026-11-07: **42 runtime cases passed**, followed by **five actual
native-process cases passed**, then **seven passed with cold-process history**.
The native history fixture copies only the donor-verified platform addon into its
own hashed closure. It recovers the original persisted model delta boundaries
and tool results after process exit, preserves the retained JSONL bytes, and
refuses a second writer until the original writer actually closes. The Agent cases prove read → observed search → actual
result through the current Agent/ACP/real source MCP reader; late revocation;
original-owner cancellation; wrong-contract refusal before model work; and
owner abort without inherited-tool reappearance. The refusal preserves the
adapter's conservative original-operation classification while independently
proving child and task cleanup.

## Exact native Session observation and normal shutdown

The existing fixed `AcpNativeToolGate` selects v3 only with
`native_session_required=True` and an exact sealed Attempt overlay. The original
child observes the actual Agent's Session object and ID after governed discovery,
checks the same object/current binding before readiness and after ACK, and sends
only that ID as the additional closed reply field. The parent rechecks the
original process, artifacts and Attempt deadline and rejects a different standard
ACP session before prompt. The descriptor still closes after its original ACK.
The false/default gate preserves the historical installed packet digest; opting
in changes that digest. A v2 helper cannot negotiate or echo its way into v3.

Qualification on 2026-11-07: **126 parent/startup/installed-source cases passed**
(process 63274 rc0), and **nine actual current-donor Agent/history cases passed**
(process 63411 rc0). The latter bind the actual Agent ID to the original ACP
result, exercise real granted read/search, refuse a foreign selected session
before model work, cancel startup before readiness, and retain original cold
history and writer-lock behavior. Model responses remain deterministic fixtures.

The real run also exposed a normal-shutdown defect: the existing native owner
sent SIGTERM 250 ms after stdin EOF although its configured finish budget still
had time. A child with 450 ms cooperative cleanup reproduced exit -15 against
the original owner. Successful completion now uses the remaining original finish
budget with a bounded reserve for the same signal/capture settlement; explicit
cancellation retains its short initial wait. Nonzero exit remains a failed
result. No retry, extra process owner or extended deadline was added.

| Receipt | SHA-256 |
|---|---|
| Parent/startup/installed-source qualification | `82a0220f5ede6c363e744cfb264f175b400ac6ccccd4a480ce2f8615ae080cc0` |
| Actual Agent/history qualification | `84c6d49bb57030c1b32eb4ff6b751126716322d4ca91f9204ad8e751ae5403a8` |
| Shutdown regression on original source | `7be07102f19339ee2e62de541bad0cc010beee24a1b85284f51e8973de23ec10` |
| Current native fixture manifest | `0faa36be36ade0de420c41a52bd86c5fc7244064d4a329d883a4b178b9da6411` |

The observed ID is startup evidence for the original ACP Attempt. It does not
activate an operator-harness epoch, adopt a standalone web session, or make the
current-authority evidence-only contract dispatchable.

## Native command admission and cancellation

`prepare_native_session.py` prepares a separate four-file patch to the original
SessionController, command, Agent-resolution and history owners. It verifies the
same clean donor pin, lockfile, all 34 tracked TypeScript package inputs, exact
patch scope and four postimages. It refuses partial patch states and never edits
the donor. The original resume map, factory, request-ID deduplication, inbox,
streaming events and native Stop `keepInbox: true` behavior remain the owners.

The patch carries the admitted operation's cancellation signal through existing
asynchronous resolution, preset composition and attachment work, into the
factory's supported creation-only signal, and checks it before native inbox
admission. Stop checks the actual Gateway invocation before its synchronous
command. A retired follow opening cannot promote a cold writer. Cancelling a
joining waiter cannot cancel the original shared-resume initiator. Generic
Gateway unary semantics are unchanged.

Run this additional gate with the same already-built donor:

```sh
python3 integrations/deepseek_harness/runtime_compat/prepare_native_session.py "$DSH_SOURCE"
cd integrations/deepseek_harness/runtime_compat
DSH_SOURCE="$DSH_SOURCE" node "$DSH_SOURCE/node_modules/vitest/vitest.mjs" run --config vitest.session.config.mts
DSH_SOURCE="$DSH_SOURCE" node check-native-session.mjs
```

The eight cases exercise the actual native Connection/Gateway, session
controllers, AgentLoop and JSONL owner with an explicit fixture model. They cover
revocation during attachment admission; original request-ID deduplication;
retired and current Stop; cold-resume cancellation during composition and
unpublished setup; independently cancelled shared-resume waiters; and retired
follow promotion. The two prompt/Stop regressions fail against the unchanged
preimage (`MMX_NATIVE_SESSION_PREIMAGE=1`, restricted to those cases). The patched
portable source passed all eight, and the donor-strict host TypeScript program
plus the company reader reported zero diagnostics. Generated receipts and test
logs stay in `.cache/native-session/`.

Native resume may retain legitimate crash-repair bytes before cancellation. The
qualified claim is no new prompt/model admission and no surviving newly acquired
writer in the tested cases, not blanket absence of storage effects. Stop remains
an acknowledgment, not terminal-turn proof. This patch consumes an existing
trusted operation signal; it does not authenticate the stock browser, establish
a company session association or authorize a provider.

## Required native host admission and original full-profile lifecycle

The separate `native-host-admission.patch` composes a runtime-only admission
callback into the original Agent factory before Session preparation and writer
acquisition. It rechecks the exact caller, bound callback and native abort signal
after asynchronous setup and before publication. The root requirement survives
child-scope isolation. The original factory retains rollback and live teardown.

The original `runProfile` accepts a synchronous trusted host initializer before
plugin/configuration setup. A root-required stock-owner hold closes Gateway
calls, event delivery and raw upload/file/open routes until trusted composition
supplies the required authority. The existing cookie, exact-origin, non-owner
policy and native lifecycle owners remain in place. No serialized configuration
creates an admission grant.

The native factory/owner suite passed **36 cases** in process60758, exit0.
The unchanged preimage failed the unauthorized-creation regression before this
patch. The patch and seven postimages are pinned in `native-host-source.json`;
the donor checkout is never edited.

`build-company-host-fixture.py` composes the already-qualified native Session
patch and this host patch into a separate complete original donor application.
All seven original build gates passed, including host/client compilers and the
web build (process63073, exit0). Its sealed runtime inventory contains116,133
file/link entries and325 client artifacts. This is an isolated fixture closure;
building it does not install or launch an application.

The real-process test then passed **new → original close → exact cold resume**
(process26485, exit0). Both runs use one original web Context and its private
stock ACP connection. They observe the same actual Agent/Session objects through
the existing web controller and company reader, refuse a second new session,
and await original ACP close and root shutdown. The same native Session ID
survives the cold process restart. Original compressed `session.v4.jsonl.zstd`
storage remains the owner; legitimate resume bytes change its digest.

Actual native HTTP checks return401 without authentication,200 for the
authenticated Mastermind index, and403 for the held file route and foreign
Origin. The stock owner remains held before ACP readiness. An early root model
listener counts and refuses model dispatch; both runs report zero. Fresh native
home/workspace state is isolated, and retiring the company reader does not
dispose the original Agent.

The complete source, build, process and log identities are retained in
[evidence/native-company-profile-20261107.json](evidence/native-company-profile-20261107.json).
Reproduce from the existing sealed fixture closure:

```sh
MMX_DSH_COMPANY_PROFILE_SUPPLY="$PWD/integrations/deepseek_harness/runtime_compat/.cache/company-host-profile-20261107-c6" \
  python3 -m pytest -q tests/harness_convergence/test_dsh_fullapp_company_profile.py::test_original_profile_new_close_and_exact_cold_resume
```

These checks establish original native host/session composition. They do not
establish a company-authorized OHF writer, live provider account, production
authentication or public browser acceptance.

## Executive concurrent Stop ownership

The existing Executive broker now permits one interrupt for the exact validated
collecting TurnRef while the original collection retains its ordinary exclusive
slot. A wrong turn or another interrupt refuses. All other run operations remain
exclusive. Original Runtime reservation, deduplication and unknown-effect
classification remain authoritative.

The same broker retains and shields both physical collection and interrupt tasks
when a requesting handler is cancelled. Completion releases only that task's
own fields. If collection finishes first, the pending interrupt still prevents
a successor operation. Shutdown drains those actual calls before original
provider cleanup and the final sweep.

The unchanged broker reproduced the legitimate Stop refusal. The repaired
existing suite passed **58 cases** (process13508, exit0), followed by the
additional shutdown-race case (process18964, exit0). The native same-prompt
correlation is now qualified below. The authenticated Executive/ACP writer join
remains required; a broker interrupt ACK alone is not terminal-turn evidence.

## Evidence boundary

The native fixture uses a deterministic test model and a synthetic registry
projection whose digests cannot become an installed host packet. Ordinary Agent
cases use explicit ephemeral test persistence; the two durable cases use the
unchanged native JSONL owner and its real platform file lock. It runs the real
source workspace reader, not the canonical installed launcher. It does not prove
paid provider access, dedicated-UID containment, installed ACP activation or
production browser acceptance. The attended package independently retains the
full app's native persistence implementation.

Source identities are in `source-manifest.json`; generated receipts and bundles
remain in ignored `.cache/`. Preserve the [upstream license](NOTICE.md).


## Native ACP claim, exact Stop and original flush

`native-acp-lifecycle.patch` is an opt-in extension of the original two ACP
source files. A trusted runtime callback enables the extension; JSON metadata
provides correlation only. The original `session/prompt` records its actual SDK
request ID, first native inbox message/turn claim and inclusive observed journal
watermark. It sends that immutable claim on the original output tail.

Exact Stop accepts only that closed claim while the original Agent, Session,
in-flight prompt and first native turn are current. It preserves unrelated
queued input through the donor's `keepInbox:true`. It refuses after the first
turn closes or is superseded. A cancellation receipt remains distinct from the
original prompt's terminal response. The original Session owner flushes before
terminal metadata is returned. A pre-enqueue cancellation can legitimately have
no claim and a watermark of -1. Default ACP behavior remains unchanged.

The original 150 ACP cases and 16 extension cases pass together (process 2373,
exit 0), and the original ACP project has zero type diagnostics (process 3037).
The preimage failures distinguish missing admission and unrelated-inbox loss.
Exact source and log identities are in
[evidence/native-acp-lifecycle-20261107.json](evidence/native-acp-lifecycle-20261107.json).

## Retained SDK connection and complete native streaming proof

The physical process resource is extracted beneath the incumbent ACP worker.
Worker admission, schema, private startup, tool gate and results remain there.
The named second consumer, `../native_connection.py`, retains one full native
web process and its exclusive inherited ACP connection. Native stdout remains
application output. The existing SDK and `StrictFrameReader` remain the only
protocol decoder and framing boundary. The SDK-generated request ID is bound at
its message transport before send can yield to a fast native claim.

The connection retains the actual prompt and exact-cancel tasks after a waiter
times out. A subsequent observation rejoins the original cancel task; it cannot
send another cancellation while the outcome is unknown. A successor prompt
requires the original result and any cancel outcome. Generation and per-turn
frame budgets remain finite. The native result digest covers observed claim,
terminal and stop-reason facts; the original Session remains the transcript owner.
Filesystem, terminal, permission and unrelated extension calls deny by default.
Governed tool observation and authenticated OHF wiring are still separate work.

The focused Python qualification passes **166 cases** (process 47112, exit 0),
including existing worker/broker/startup/tool observations and the new transport,
correlation, timeout and settlement cases. The existing source identity guards
pass **294 cases** (process 55665). The probe digest now commits each accepted
callback once; frame prevalidation remains pure and the original worker's
polymorphic tool-validation seam is preserved.

A fresh complete donor copy composes the native Session, host and ACP patches.
All seven original build gates pass (process 11511), with 325 client artifacts
and a sealed 116,133-entry runtime inventory. The actual full-profile test passes
(process 47383, exit 0): new session, original partial assistant stream, exact
Stop, original interrupted-message/history flush, original close and natural
process shutdown, exact cold resume, recovered interrupted text, and a normal
completed native turn. Both generations observe the same native Session ID and
one original Agent/Session owner each. No external process signal or provider
call is used. Model stream calls are deterministic fixture adapter calls.

Reproduce the lifecycle scenario from its qualified complete closure:

```sh
MMX_DSH_COMPANY_PROFILE_SUPPLY="$PWD/integrations/deepseek_harness/runtime_compat/.cache/company-acp-profile-20261107-c8" \
  python3 -m pytest -q tests/harness_convergence/test_dsh_fullapp_company_profile.py::test_original_profile_claim_stop_flush_and_exact_cold_resume
```

Full source, build, process, claim, terminal, storage and log evidence is in
[evidence/native-connection-20261107.json](evidence/native-connection-20261107.json).
The independently qualified scoped owner-access package is reconciled in
[evidence/native-owner-access-20261107.json](evidence/native-owner-access-20261107.json).
That package and this ACP fixture are distinct closures; neither is an installed
production receipt. The remaining join is the original OHF adapter/result
consumer, a distinct authenticated native profile and its actual authority/
attestation producers, eligible governed tools, and the signed-in production
browser journey. No local build or green CI establishes that acceptance.

### Retained OHF adapter / native result qualification

The composed 502-case source-frozen receipt is
[`evidence/native-operator-20261107.json`](evidence/native-operator-20261107.json).
It includes the original full application through the retained Python OHF
adapter, exact native Stop, clean close and same-Session cold resume. The
fixture uses explicitly supplied laboratory authority, not installed Executive
or provider-account admission. The result wire is a closed native observation;
it never manufactures a planner envelope or Job completion.

The original v3 access/upload/package receipt is
[`evidence/native-owner-access-v3-20261107.json`](evidence/native-owner-access-v3-20261107.json).
Its full package composes the qualified native ACP patch, preserves the full
encoded-upload authorization arguments and remains uninstalled. See
[`../NATIVE_COMPANY_JOIN_FRONTIER.md`](../NATIVE_COMPANY_JOIN_FRONTIER.md)
for the exact Runtime, authenticated consumer, governed-tool and production
work still owed.

### Passive native observation on the retained SDK connection

The exact opt-in prompt extension v2 adds `_mastermind/native_observe` beside
the existing claim and exact-cancel methods. It requires both original runtime
admission and a callable runtime observer. Admission-only v1 and default ACP
remain unchanged; the observation hook is not serializable configuration.

Observation resolves the current idle Agent/Session, captures model selection
and journal watermark, awaits its trusted callback, validates and detaches the
closed 32 KiB OHF result, then rechecks original service/object/callback/lifetime
identities. It never discovers, creates, resumes, prompts, cancels or flushes.
The Python native connection uses the same retained SDK and rechecks its owner
after the await; the OHF adapter repeats launch/turn admission before publication.
Closed-turn passive responses do not consume that turn's frame budget, while
the original global frame limits and late-callback refusal remain.

C21 qualifies **191 donor/extension cases**, zero TypeScript diagnostics,
**85 Python/package cases**, all seven full native build gates, and the actual
full-process SDK observation/Stop/same-Session recovery test. Exact source,
receipt, failed-attempt and physical evidence is in
[the C21 evidence](../../../research/evidence/deepseek-native-passive-observation-20261107.json).
The full-process observer is explicitly a laboratory fixture. The installed
observer and launcher must supply actual original account/model/capability and
confinement facts before production admission.
