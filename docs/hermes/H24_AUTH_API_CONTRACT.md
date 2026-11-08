# H24-04 — Authenticated API and original-effect conformance

## Current source compatibility — November 7, 2026

The packet is composed with protected source
`f4f8ddc552866d2ab4bb2c7f229b0f2be283485c`. The strict parser changes stay in
their existing owners. The current COO builder retains its private/public
composition and selected-child implementation.

The v1 fixture still proves cross-principal isolation and independent revocation.
Its trailing check now accepts a valid v2 document in the binding owner's canonical
digest order and deliberately reverses that order for the negative case. It does
not change the validator, enrolled identity, receipt, authority or selection policy.

Current protected source includes the seven-tool legacy catalogue with
`mmx_delegate` and opt-in v2 multi-client bindings. Their presence does not prove
real enrollment or every selected-child acceptance path. H24's resource-sharing
fixture exercises the legacy default, not the explicit public v3 composer.

Current focused qualification passed **531 cases across 13 complete modules**,
including all **118 H24 cases**, with zero failures, errors or skips. The pytest
summary is `531 passed in 56.68s`; the complete native invocation returned exit0.
The selection retains the ten original H24/affected-owner modules and adds the
current public COO composition, discovery and public-audience owner suites.

This run used an isolated environment on Darwin with CPython3.12.13,
pytest9.2.0, MCP1.28.1, PyJWT2.14.0, FastAPI0.162.2 and Starlette1.10.0.
The environment installed the repository's declared development dependencies;
`pip check` passed. It did not change global packages or install a service.
Its profile is distinct from hosted Linux/CPython3.12.16.

The exercised working tree was `91662aac9eb7e21d0656f85b4bebb7e56cf6a966`.
Only this report changed afterward; the five executable postimages stayed
identical. Complete log:661 bytes, SHA256
`a395c3197b188dae7c4a0a99117e4d140d2646a1095e7bd14efd493f184b383e`.
[The original PR's qualification record](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2138#issuecomment-6714329386)
retains the exact invocation, module totals and source identities.

The original hosted six-shard run did not execute this pytest-only H24 module.
Fresh hosted qualification of the final published composition remains required.
The historical118/437 evidence below is not relabeled as this531-case run.

## November 6 qualification at the b0a-based source

At that earlier source the author reported all five previously recorded JSON
rejection defects repaired, **118 passing H24 cases with no xfails**, and
**437 passing cases** in the combined affected-owner run. The reproduction
commands, measurements and executable hashes below retain that historical scope.

The source supplies independently signed fixture principals, actual
ASGI/Unix/Workspace/COO entrypoints, principal continuity and immutable original
request tests, plus strict HTTP and COO MCP parsing in the existing runtime owners.
At that earlier pin, C29 selected-child, C32 multi-principal binding and C34
distinct-resource composition were recorded as separate integration requirements.
The current source and the remaining acceptance boundaries are distinguished below.
Successful fixture signatures do not prove real OAuth enrollment.

| Identity | Exact value |
| --- | --- |
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Packet / branch | H24-04 / `sol/h24-04-api-auth-20261106` |
| Existing PR | [#2138](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2138) |
| Original packet base | `b54cb10e4abdd3766c62d4088f6a576ecfe80437` |
| Last pre-rebase published head | `8ac20b38dc8a24e766c6734b01100db8587934c8` |
| Earlier authorized rebase / procedure pin | `b0a280be474ae67e7681f68dc0dfe3af2aea1626` |
| Scope expansion | Chairman explicitly authorized the bounded parser repair and rebase on November 6, 2026 |
| Current source scope | Three original H24 additions plus three existing parser/composition files |
| Capability boundary | Source implemented and fixture-qualified; no installed or production-serving proof |

The original concurrent placement remains applicable. The source work did not
wait for H24-01, a soft wave seal, an archived author or a separate approval chat.
The later explicit authorization supersedes the frozen-base and excluded-path
instructions only for this bounded repair and rebase. No merge, activation,
credential or production authorization follows from it.

## Exact implementation scope

| File | Change |
| --- | --- |
| [api_conformance.py](../../integrations/hermes_qualification/api_conformance.py) | Signed fixtures, observation adapters and executable route/resource matrix |
| [test_h24_api_conformance.py](../../integrations/hermes_qualification/tests/test_h24_api_conformance.py) | Actual incumbent-entrypoint qualification; five xfails removed; 24 additional parser/effect/framing cases |
| This document | Current behavior, reproducible evidence and remaining integration requirements |
| [mastermind_executive_app/app.py](../../integrations/mastermind_executive_app/app.py) | Shared HTTP argument reader uses strict decoding; authentication, empty-body and envelope behavior retained |
| [executive_mcp/e1_http.py](../../integrations/executive_mcp/e1_http.py) | SDK-free strict decoder; compile-time path/strictness selection in the existing bounded pre-auth receiver |
| [executive_mcp/server.py](../../integrations/executive_mcp/server.py) | Existing COO composition selects literal `/mcp/coo` and strict decoding |

There is no new endpoint, issuer, authentication owner, permission registry,
principal selector, queue, retry loop, request-identity namespace or lifecycle.
C32 binding files, C34 proxy/resource configuration and C30 installed source
remain untouched. No production package installation, real client registration, provider
request, live worker dispatch, Slack message, self-approval or merge is part of
this source change.

## Strict parsing repair

The shared `strict_json_loads` helper in the existing `e1_http.py` owner:

- decodes the original bytes as UTF-8;
- rejects duplicate names at every object depth, including escaped equivalents;
- rejects `NaN`, `Infinity` and `-Infinity`;
- rejects floating-point overflow such as `1e999`, which `parse_constant` alone
  would not catch;
- translates invalid UTF-8 and actual parser recursion failures into invalid input;
- returns the value to the existing caller's schema checks.

It does not define a new JSON-RPC or authority schema. It does not impose a new
deterministic HTTP nesting limit. Syntactically valid deep JSON with invalid RPC
parameter shape can still be rejected by the existing SDK schema with HTTP 400.

### HTTP tool boundary

`_read_body_arguments` now invokes the shared strict decoder. It retains the
existing 65,536-byte check, empty-body-to-empty-arguments behavior and closed
`{"arguments": {...}}` envelope.

This is the shared CEO/COO tool argument reader. The affected CEO HTTP and MCP
composition tests therefore run alongside COO tests. The separate release parser
and CEO original-status handler are outside this repair and unchanged.

Direct COO HTTP still verifies its caller/binding before reading arguments.
Malformed modifying requests are rejected before authority/Mission lookup,
grounding, Unix submission or Job creation. The harness does not claim
that direct HTTP syntax rejection precedes JWT verification.

### COO MCP boundary

The existing `PreAuthMcpBodyApp` now accepts compiled path and strictness options.
Its defaults remain `/mcp` with legacy decoding behavior. The incumbent
`_build_coo_mcp_app` selects `/mcp/coo` and strict JSON for its existing legacy
and explicit public callers. Their separate configuration and authority gates
remain unchanged.

Validation happens on the original bytes before the MCP SDK normalizes the RPC
object. Invalid bytes are not reserialized into a synthetic valid request.
The existing receiver counts actual streamed bytes, rejects overflow, incomplete
and empty bodies, applies its existing five-second default receive deadline,
and replays accepted original bytes once.

Before this repair, the wrapper matched only `/mcp`, so its outer receive
deadline/empty-body guard did not apply to COO. COO now selects that same existing
receiver rather than gaining a parallel body reader.

Literal-route/raw-path/query/method checks, the duplicate-Authorization guard,
authentication middleware, exact scope policy, SDK manager and Starlette lifespan
shape remain unchanged. Legacy CEO/E1 nonempty whitespace requests still reach
authentication as before; strict MCP parsing is opt-in for COO.

### Previously failing requirements, now passing

| Boundary | Request | Previous response | Required and observed now |
| --- | --- | --- | --- |
| COO HTTP | Duplicate root `arguments` | 200 | 400 |
| COO HTTP | Duplicate nested `work_ref` | 200 | 400 |
| COO MCP | Duplicate RPC `id` | 200 | 400 |
| COO MCP | Duplicate nested `work_ref` | 200 | 400 |
| COO MCP | Nonfinite RPC `id: NaN` | 202 | 400 |

All five are ordinary passing assertions. No xfail markers remain in H24-04.
The former MCP 202 was never proof of a tool effect.

Additional negatives include escaped duplicate keys, both infinities, exponent
overflow, invalid UTF-8 and deep invalid parameters. Actual modifying requests
with duplicate/escaped keys or overflow are exercised through both HTTP and MCP:
400 with **zero authority/Mission calls, zero Unix frames and zero Jobs**.

The actual COO MCP framing test splits a request across ASGI events, supplies a
misleading `Content-Length`, proves exact 65,536-byte acceptance and unchanged
original bytes at the SDK, and proves 65,537-byte refusal before SDK dispatch.
Empty, disconnected, timed-out and unexpected-event bodies also refuse before
SDK dispatch. The deadline fixture shortens the existing timer to 20 ms; it does
not claim an observed production latency.

## Incumbent owners and exercised path

The imported owners remain the implementations under test:

- [ASGI/MCP composition](../../integrations/executive_mcp/server.py):
  real Workspace mount, COO catalogue, literal route and opt-in ruling route.
- [COO application](../../integrations/mastermind_executive_app/coo.py) and
  [binding](../../integrations/mastermind_executive_app/coo_binding.py):
  verified principal, current receipt, authority generation, current Mission,
  fresh submit and original status.
- [Workspace application](../../integrations/mastermind_workspace_app/app.py),
  [membership contract](../../integrations/mastermind_workspace_app/contract.py)
  and [read service](../../control_plane/workspace_read_service.py):
  actual ASGI -> Unix -> Workspace read with authorization before disclosure.
- [JWT verifier](../../integrations/business_mcp_auth/jwt_verifier.py):
  real signature, issuer, audience/resource, subject/client and scope checks.
- [Original COO request](../../control_plane/coo_principal_request.py) and
  [ingress](../../control_plane/executive_ceo_ingress.py):
  canonical `req-coo`, immutable original command and original-context receipt.
- [Secretary client](../../integrations/secretary_team_access/client.py):
  fixed host-injected clients, one submit and explicit status reconciliation.
- [Ruling boundary](../../integrations/mastermind_executive_app/principal_ruling_http.py),
  [source fence](../../integrations/slack_agent_dialogue/principal_decision_source_fence.py)
  and [current target reader](../../integrations/slack_agent_dialogue/principal_current_reader.py):
  fixed host obligation, current unanswered predecessor, worker tuple and COMMIT.

The adapter supplies synthetic signed claims, in-memory public keys, explicit ASGI
transports, observations and response-loss injection. It does not copy handlers,
verifiers, permission reducers, request identity or effect reconciliation.

GB1 and Secretary fixtures have different RSA keys, key IDs, subjects and client
IDs. Both enter the real verifier. Workspace authorizes both concurrently for one
Mission. This COO fixture intentionally uses singleton v1 bindings, so its two
clients use separate application instances. The current owner separately supports
opt-in v2; the packet now validates that contract without changing its v1 fixtures.
Those instances also share one real disposable Unix owner
for original-operation collision and ownership tests.

The fixture never swaps one shared COO binding between concurrent requests to
simulate multi-principal support. Permission digests are synthetic receipt markers
through the existing binding owner. No real OAuth enrollment, production receipt
or external credential is implied.

## Route, resource and authority matrix

Fixture resources:

- `WORKSPACE` = `https://mcp.mastermind-x.com/workspace/read`
- `CEO` = `https://executive.h24.example.test/mcp`
- `COO-DESIRED` = `https://executive.h24.example.test/mcp/coo`
- Fixture issuer = `https://issuer.h24.example.test`
- `COO-SCOPES` = `mastermind.executive.coo.act` + `mastermind.executive.read`

Every HTTP request uses an in-process ASGI transport. These URLs are not created,
network-accessed or certified as production-serving. The public-route matrix is
also exposed by `route_resource_matrix()` in the adapter.

| Route / boundary | Method | Exercised resource | Authority / behavior |
| --- | --- | --- | --- |
| `/workspace/mission/v3/current` | GET | WORKSPACE | Workspace read scope; independent member/receipt; explicit work/root; continuity |
| `/mcp` | POST | CEO | Exact CEO read policy; COO-scoped token refused |
| `/mcp/coo` | POST | Shared CEO resource | COO-SCOPES; v1 fixture; current seven-tool catalogue; strict original JSON before SDK |
| `/v1/tools/executive_mandate` | POST | Shared CEO resource | Read-only mandate; current authority/Mission; post-read continuity |
| `/v1/tools/submit_principal_intent` | POST | Shared CEO resource | Bounded original submit; host-derived principal context; strict HTTP arguments |
| `/v1/tools/principal_intent_status` | POST | Shared CEO resource | Current authentication and original context; available when fresh admission closes |
| `/mcp/principal-ruling` | POST | CEO in ruling fixture | Fixed host work/root/obligation; separate ruling; existing strict JSON |
| Existing private Unix ingress | Local frame | Existing peer/context contract | Immutable original submit/status identity; no replacement request or retry |

The current legacy COO tools are `executive_mandate`, `executive_state`,
`executive_inbox`, `executive_fabric`, `submit_principal_intent`,
`principal_intent_status` and `mmx_delegate`. The harness compares the actual
catalogue and schemas; it does not hard-code an obsolete six-tool count.

Legacy resource sharing remains explicit. `CooAppSettings.__post_init__` requires
shared resource metadata and the same `_jwks_cache_contract`, which includes
`policy.resource`, in this legacy/default fixture. Its distinct-resource negative
still exercises that boundary. Current source has a separate explicit public v3
composition; H24 does not exercise or claim its enrollment/serving acceptance.
The actual verifier separately accepts a correctly scoped COO-DESIRED token and
rejects the CEO audience.

Exact scopes still isolate the legacy routes: the CEO read token is refused at
`/mcp/coo` and the COO token is refused at `/mcp`. Shared metadata does not itself
establish unauthorized cross-route access.

## Identity, authority and effect acceptance evidence

| Concern | Executed evidence | Result |
| --- | --- | --- |
| Distinct identities | Independent keys/subjects/clients; real verification; signature substitution | PASS |
| Same authorized Mission | Concurrent ASGI/Unix/Workspace reads; same work/root/results, independent observations | PASS; no Job |
| Independent revocation / wrong work | Revoke one member while the other works; foreign work/root, model-selected authority | PASS |
| Same-subject continuity | Receipt rotation, subject replacement, disabling during Workspace/COO reads | PASS; inner data withheld |
| Authentication | Wrong issuer/resource/subject/client, empty/wrong scopes, expired token | PASS |
| Ambiguous bearer | Two identical/distinct Authorization values on HTTP COO, MCP COO and ruling | PASS; 401 |
| Bounded authority | Unknown authority, stale generation, rotated receipt, disabled/historical Mission | PASS |
| Public approval/target selectors | Unsupported approval, principal/actor/root/generation, bogus target digest | PASS; refused before send; no invented approval receipt |
| Decision-source fence | Edited/answered predecessor, revoked authority, binding drift, invalid option, policy denial | PASS; no Relay post or pre-COMMIT effect |
| Policy revoked at COMMIT | Existing fence crosses COMMIT before policy loss | PASS; COMMIT_STARTED/EFFECT_UNKNOWN retained |
| Current target tuple | Changed attempt, worker or root | PASS; not a selected-child digest API join |
| Lost submit response | Drop completed response after actual local admission | PASS; Secretary EFFECT_UNKNOWN, identical req-coo |
| No resubmit | Count HTTP calls and Unix frames; explicit status-only reconciliation | PASS; one submit/status and disposable Job |
| Fresh/status separation | Close fresh admission and remove current Mission result after acceptance | PASS; original status available, dispatched=false |
| Original status auth | Missing bearer, foreign principal, revoked original binding | PASS; no extra Job |
| Immutable request | Same work/operation retains ID; changed semantic payload conflicts | PASS |
| Concurrent original ownership | Two valid COO contexts, shared Unix owner, same/distinct operation keys | PASS; same key one winner/conflict, distinct keys two Jobs |
| Foreign original status | Query through foreign principal's own authorized app | PASS; owner conflict, no receipt |
| Revocation before send | Disable/rotate after actual grounding | PASS; REFUSED, original req-coo, zero submit/Job |
| Revocation after send | Disable/rotate after actual submission | PASS; EFFECT_UNKNOWN, original req-coo, one submit/Job |
| Exact fixture restoration | Restore original binding; reconcile with fresh gate closed | PASS; no resubmit; rotated context cannot borrow receipt |
| Direct transport evidence | not_sent, lost, exception, malformed receipt at existing seam | PASS; proven not_sent refused, possible-send uncertain |
| Secretary HTTP 5xx | Inner not_sent becomes HTTP 503 | PASS; conservative EFFECT_UNKNOWN, original req-coo, no retry |

`req-coo` depends on work and original operation key, not the caller's principal.
The two callers intentionally share it for the same operation; distinct binding
digests make the second context conflict. No principal-specific replacement
request namespace is created.

The app and Secretary observe different evidence. The inner transport can know
`not_sent`; its HTTP consumer seeing a modifying 503 retains uncertainty. The
separately tested post-grounding 403 with zero submit frames proves pre-send
refusal.

Disposable admission/reconciliation does not prove worker execution or physically
exactly-once remote actions. Admission, dispatch, completion and acceptance remain
distinct. Exact synthetic fixture restoration is not a production revocation-
reversal procedure.

## C29 / C32 / C34 source and acceptance boundaries

Strict parsing remains this packet's runtime change. The table distinguishes
current source from acceptance that this fixture does not establish:

| Commission | Current source / fixture boundary | Acceptance not established by H24 |
| --- | --- | --- |
| [C29 ingress / selected child](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6680534154) | Current legacy COO MCP includes `mmx_delegate` and the protected selected-child implementation; H24 catalogue coverage is not the complete selected-child path | Submit/status retain original command and target/context/capability digests; wrong digest refused before send; uncertainty preserved |
| [C32 Hermes OAuth principal](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6681329609) | Workspace supports members; COO supports preserved v1 plus opt-in bounded, canonically ordered v2 bindings; H24 keeps separate v1 app fixtures | One composed app with enrolled principals, bounded per-principal Mission rows, concurrent access and independent revocation |
| [C34 exact COO resource](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6681341295) | Legacy H24 defaults require shared metadata; the explicit public v3 composer is separate | Distinct COO resource and `/.well-known/oauth-protected-resource/mcp/coo`; audience/scope isolation and authorized edge composition |

The commission links identify the original contracts, not current live workers
or serving proof. Protected source presence and this packet's fixture checks do
not establish installed enrollment, activation or every original acceptance path.
No issuer, registry, approval token or public target selector is added here.

## Historical reproduction and receipts — November 6, 2026

Managed authoring/test directory:

`/home/ubuntu3/.mastermind/agent-workspaces/sol/h24-04-api-auth-20261106`

The installed `mmx-workspace` launcher recovered the previously published head.
The authorized rebase replayed only the two H24 commits after the original packet
base onto protected `b0a280be474ae67e7681f68dc0dfe3af2aea1626`. Inherited foundation
changes are not candidate changes. Tests used the existing interpreter; no install.

### H24 plus affected owner regression run

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -ra -p no:cacheprovider \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  tests/test_executive_coo_app.py \
  tests/test_executive_coo_binding.py \
  tests/test_coo_principal_request.py \
  tests/test_executive_coo_mcp.py \
  tests/test_mastermind_executive_app_asgi.py \
  tests/test_executive_mcp_e1_composition.py \
  tests/test_executive_mcp_app_composition.py \
  tests/test_mastermind_executive_app_static_fences.py \
  tests/test_session_bridge_http_foreground.py --tb=short
```

```text
437 passed in 18.21s
exit code 0
```

This includes all 118 H24 cases. No tests in this run were skipped or xfailed.
The other 319 cover COO owners, shared CEO HTTP parsing, legacy E1/native app
composition, static import boundaries and session lifetime.
Local full receipt: `/tmp/h24-04-parser-qualified.txt`.

The initial repair run had 117 passes and one overly specific expectation:
deep syntactically valid RPC data returned HTTP 400 with the SDK's schema error
rather than decoder `invalid_input`. The final assertion retains HTTP 400 and
allows that existing schema owner. Runtime behavior was not weakened.

### Lightweight stdlib discovery

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m unittest discover -v \
  -s integrations/hermes_qualification/tests -p 'test_*.py'
```

```text
Ran 49 tests in 0.572s
OK (skipped=1)
exit code 0
```

Local receipt: `/tmp/h24-04-parser-unittest.txt`.

The explicit skip separates stdlib discovery from pytest integration functions
whose dependencies its lightweight CI profile does not install. Under pytest,
imports are unconditional and missing dependencies fail collection. The
437-test run includes a `python -S` subprocess regression proving this separation.

### Source inspection

A distinct read-only native advisory task inspected the runtime and test delta.
It found no blocking defect and confirmed defaults, validation order, original
bytes, literal routing and lifespans. The parent consumed the result and executed
the tests. This is technical assurance, not formal GitHub approval or an
independently executed test result.

| Reviewed executable | SHA-256 |
| --- | --- |
| `integrations/executive_mcp/e1_http.py` | `2e0cb5337fc073324984e0964ade02639475d0de1bc7a007e41116843ca56696` |
| `integrations/mastermind_executive_app/app.py` | `a193e129fc38028a1f105a2eac59a371b47e4d01069d824781b3e459e861930c` |
| `integrations/executive_mcp/server.py` | `49bb75124ef131a9b3aad17072fbd8e1fb7ba2dba7f2082c04921d53e6797c6b` |
| `integrations/hermes_qualification/tests/test_h24_api_conformance.py` | `e5ca0388398e31950d7af86a71bebef2f822007e9dff5756daaf7dbeff87c74c` |

### Superseded historical receipts

Initial `90f11efe414fa50d6076889146eeaca90b3966e0` had 72 passes/five strict xfails.
Later `8ac20b38dc8a24e766c6734b01100db8587934c8` had 89 passes/the same five xfails
and repaired the stdlib discovery import failure.

The prior turn qualified a source export at
`609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1` with 219 passes/five xfails and 105
targeted foundation regression passes. These are historical receipts. The current
repair supersedes the five parsing failures and the prior request for permission
to edit their runtime owners.

Parent #2120 merged as `28a894186eb56654ab4e833eb11a183d2eed46ae`. GitHub deleted
its source branch and retargeted H24 to master, exposing 88 inherited files and
conflicts. The authorized rebase removes that obsolete candidate ancestry:
the intended current diff to the new base comprises exactly six files. PR #2138
records GitHub's post-publication comparison and checks; local tests alone do
not assert hosted CI success.

## Parent checkpoint and durability

The published head and checksum belong in PR #2138's checkpoint, outside this
hashed document to avoid self-reference. The cumulative authorized diff is:

```bash
git diff --binary --full-index \
  f4f8ddc552866d2ab4bb2c7f229b0f2be283485c HEAD -- \
  integrations/hermes_qualification/api_conformance.py \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  docs/hermes/H24_AUTH_API_CONTRACT.md \
  integrations/mastermind_executive_app/app.py \
  integrations/executive_mcp/e1_http.py \
  integrations/executive_mcp/server.py | sha256sum
```

Verify the new base is an ancestor, the diff is exactly these six paths and the
published bytes match tested/reviewed executables. The old published head remains
the historical pre-rebase receipt.

**Completed:** original harness, discovery repair, principal/effect expansions,
all five strict-JSON corrections, affected-owner regressions and authorized
foundation reconciliation.

**Acceptance outside this packet:** current C29/C32/C34 source is distinguished
above from any separately authorized enrollment, installation, activation and
original real-path acceptance.
This result does not activate a service or claim production qualification.

**Do not redo:** accepted fixture identity, current Mission, continuity,
original-request reconciliation, source-fence and parser coverage absent material
source/authority/behavior changes. Retain the existing branch/PR; no replacement
operation or reinterpretation of fixture receipts as production effects.
