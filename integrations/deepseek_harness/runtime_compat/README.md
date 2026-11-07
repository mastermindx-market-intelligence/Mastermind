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
