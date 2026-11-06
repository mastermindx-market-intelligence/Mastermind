# H24-04 — Authenticated API and original-effect conformance

## Outcome and scope

This packet supplies an executable, source-only qualification harness for the
incumbent Workspace, Executive MCP, COO and Secretary clients. It uses real
application entrypoints and independently signed, disposable fixture principals.
It does not implement an authentication runtime, endpoint, issuer or enrollment
owner.

**Harness outcome:** delivered with explicit unmet requirements.
**Incumbent end-to-end conformance at this pin:** PARTIAL.
**Production capability:** BUILT_NOT_PROVEN; this report supplies no activation or
serving proof.

| Identity | Exact value |
| --- | --- |
| Packet | H24-04 |
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Source base | `b54cb10e4abdd3766c62d4088f6a576ecfe80437` |
| Source branch | `sol/h24-04-api-auth-20261106` |
| Protected procedure pin | `535d510d5ec7dc1de65349c3cbd34692deb1ae8a` |
| Placement | Chairman's current concurrent authorization; no H24-01 or soft wave-seal dependency |
| Owned additions | `integrations/hermes_qualification/api_conformance.py`; `integrations/hermes_qualification/tests/test_h24_api_conformance.py`; this document |

No PR #2120 integration source or C29–C34 exclusive path is changed. The harness
does not install packages or services, register clients, provision credentials,
contact an OAuth issuer, dispatch workers, submit provider requests, send Slack
messages, merge, approve or activate a production route. Temporary Unix sockets,
disposable Runtime databases and the existing in-memory Slack test double are
test fixtures only.

## Incumbent owners and exercised path

The imported owners remain the implementation under test:

- [ASGI and MCP composition](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/executive_mcp/server.py):
  the actual Workspace mount, six-tool COO MCP catalogue, closed tool arguments,
  literal COO route, and opt-in ruling route.
- [COO application](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_executive_app/coo.py)
  and [COO binding](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_executive_app/coo_binding.py):
  verified principal, sealed permission receipt, authority generation, current
  Mission, fresh submit and original status separation.
- [Workspace application](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_workspace_app/app.py),
  [membership contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_workspace_app/contract.py)
  and [Workspace read service](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/workspace_read_service.py):
  the real ASGI → Unix → Workspace read, including authorization before disclosure.
- [JWT verifier](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/business_mcp_auth/jwt_verifier.py):
  cryptographic signature and exact issuer/resource/scope verification.
- [Original COO request](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/coo_principal_request.py)
  and [incumbent ingress](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/executive_ceo_ingress.py):
  canonical `req-coo`, immutable operation identity and original-command lookup.
- [Secretary client](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/secretary_team_access/client.py)
  and [host-injection contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/docs/GROK_SECRETARY_TEAM_INTEGRATION.md):
  fixed clients and one submit followed by explicit original-status reconciliation.
- [Ruling boundary](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_executive_app/principal_ruling_http.py),
  [decision source fence](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/slack_agent_dialogue/principal_decision_source_fence.py)
  and [current target reader](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/slack_agent_dialogue/principal_current_reader.py):
  strict ruling JSON, fixed host obligation, current unanswered predecessor,
  current worker tuple and the existing COMMIT fence.

The adapter supplies only in-memory public keys, synthetic signed claims, explicit
ASGI transports, observation counters and response-loss injection. It does not copy
the verifier, application handler, permission reducer, request-identity algorithm
or effect reconciliation logic.

The two clients have different RSA keys, key IDs, subjects and client IDs. Both
enter the real verifier. Workspace's existing multi-member binding authorizes
both for one Mission simultaneously. The current COO binding is a singleton;
its two principals are therefore tested in separate application instances, and
this limitation is explicitly retained as a C32 gap. The fixture does not swap
one shared binding between concurrent requests to simulate multi-principal support.

Permission digests are synthetic receipt markers supplied through the existing
fixture binding owner. Signature success and receipt shape/currentness checks are
not real OAuth enrollment or proof that a production enrollment receipt exists.

## Route, resource and authority matrix

The following resources describe the **exercised fixture configuration**:

- `WORKSPACE` = `https://mcp.mastermind-x.com/workspace/read`, the incumbent
  Workspace resource required by its contract.
- `CEO` = `https://executive.h24.example.test/mcp`.
- `COO-DESIRED` = `https://executive.h24.example.test/mcp/coo`.
- All newly signed fixture tokens use issuer
  `https://issuer.h24.example.test`.
- `COO-SCOPES` = exact set
  `mastermind.executive.coo.act` + `mastermind.executive.read`.

All HTTP requests use an explicit in-process ASGI transport, including requests
whose test Host header uses the incumbent public hostname. No listed URL is
created, accessed over the network or certified as production-serving.

| Route / boundary | Method | Accepted fixture resource | Required scope / authority | Behavior proved |
| --- | --- | --- | --- | --- |
| `/workspace/mission/v3/current` | GET | WORKSPACE | `mastermind.workspace.read`; independently matched member and permission receipt; explicit work/root | Two simultaneous CURRENT reads of the same Mission; no Job creation; post-read revocation withholds disclosure |
| `/mcp` | POST | CEO | Exact CEO read policy, `mastermind.executive.read` | CEO catalogue readable; COO-scoped token rejected here |
| `/mcp/coo` | POST | CEO at this pin | COO-SCOPES plus singleton COO binding | Exact six-tool catalogue/schema and role separation; literal route; parsing gaps below |
| `/v1/tools/executive_mandate` | POST | CEO at this pin | COO-SCOPES, selected binding, authority and Mission | Read-only mandate; post-read principal and permission continuity |
| `/v1/tools/submit_principal_intent` | POST | CEO at this pin | COO-SCOPES, original request and host-derived admission context | One bounded original submit; uncertain post-send outcome retains its `req-coo` |
| `/v1/tools/principal_intent_status` | POST | CEO at this pin | Current authenticated binding and original context | Original status remains readable with fresh admission closed; absent/revoked/wrong subject refused |
| `/mcp/principal-ruling` | POST | CEO in the ruling fixture | COO-SCOPES, current caller facts, fixed host work/obligation/surface | Separate ruling operation; model cannot select principal or target; strict JSON rejection |
| Existing private Unix ingress | Local frame | No new bearer audience | Existing peer fence plus immutable principal context | Same original submit/status identity; closed fresh guard does not prevent authorized original reconciliation |

The legacy resource sharing is intentional characterization of the pinned source.
`CooAppSettings.__post_init__` requires shared resource metadata and a shared
`_jwks_cache_contract`; that contract includes `policy.resource`. Therefore a
dedicated COO resource cannot be composed at this base. The actual verifier
separately accepts a correctly scoped COO-DESIRED token and rejects a CEO audience,
but inserting that distinct policy into the incumbent COO settings is refused.

Exact scopes still isolate the legacy routes: the CEO read token is refused at
`/mcp/coo`, and the COO token is refused at `/mcp`. The shared-resource finding
does **not** establish unauthorized cross-route access.

The six incumbent COO tools are `executive_mandate`, `executive_state`,
`executive_inbox`, `executive_fabric`, `submit_principal_intent` and
`principal_intent_status`. The harness consumes their existing schemas directly.
C29's planned `mmx_delegate` is absent from this immutable base.

## Acceptance evidence

| Packet concern | Executed evidence | Result at immutable base |
| --- | --- | --- |
| Distinct GB1 / Secretary identities | Different key, subject and client; real JWT verification; signature substitution rejected | PASS |
| Same authorized Mission | Concurrent outer ASGI → actual Unix service → Workspace reads; same work/root/results; each read has its own stable observation receipt | PASS |
| Independent revocation / wrong work | Revoke one member, leave the other working; foreign work/root and model-selected authority fields refused | PASS |
| Principal continuity | Rotate receipt, replace subject or disable membership during Workspace and COO reads | PASS; successful inner data withheld |
| Issuer, audience, scope and client enforcement | Wrong issuer/resource/subject/client, empty scopes, wrong scopes and expired token | PASS; refused before owner disclosure |
| Dedicated COO resource | Real verifier rejects wrong audience; real composition refuses distinct-resource policy | C34 integration requirement unmet |
| Multi-principal COO application | Each signed client works with its own v1 binding; foreign client denied; v2 container rejected by pinned owner | C32 integration requirement unmet |
| Bounded authority | Actual host guard rejects unknown authority, stale generation, rotated permission, disabled or historical Mission | PASS |
| Unknown approval / public selector | Unknown or stale-shaped `approval`, supplied principal/actor/root/generation or bogus `target_digest` refused before send | PASS for unsupported input; not a typed approval-receipt implementation |
| Stale decision approval context | Existing end-to-end source fence: current unanswered request positive; edited, already answered, revoked authority or binding drift negative | PASS; no Relay post or COMMIT for those rejected cases |
| Current host target | Original current target reader refuses changed attempt, worker or root | PASS; this is tuple continuity, not C29's future target-digest join |
| Truncated / oversized JSON | Actual COO HTTP, COO MCP and ruling boundary | PASS, HTTP 400 / 413 respectively |
| Duplicate-key JSON | Valid retained values at root and nested depth, through HTTP tool and MCP boundaries | Four unmet rejection cases; see below |
| Nonfinite JSON | COO HTTP malformed argument and ruling RPC ID refused; COO MCP RPC ID `NaN` receives 202 | One additional unmet MCP rejection case |
| Original submit timeout | Lose the completed HTTP response after actual application/Unix admission; Secretary returns EFFECT_UNKNOWN | PASS; identical canonical `req-coo` |
| No second submit | Record actual HTTP invocations and actual Unix frames; explicit status-only reconciliation | PASS; one submit frame, one status frame, one disposable Job |
| Fresh versus original-status policy | Close fresh admission and remove the current Mission provider result after admission | PASS; authorized original status returns ADMISSION_ACCEPTED, `dispatched=false` |
| Original status authorization | No bearer, another principal, then revoked original binding | PASS; 401 / 403, no additional Job |
| Immutable request / changed payload | Same operation/work keeps the request reference; changed semantic payload conflicts | PASS |
| Pre-send versus possible-send | Existing transport seam returns not-sent, lost response, exception or malformed receipt | PASS; proven not-sent remains a refusal, possible-send remains uncertain |
| Separate ruling | Each signed fixture identity uses fixed host work/root/obligation; injected target fields refused | PASS for fixture forwarding; no real ruling or provider effect |

The original-submit fixture proves durable local admission and reconciliation, not
execution of a worker or a physically exactly-once remote action. Admission,
dispatch, completion and acceptance remain separate facts.

### Five explicit parsing nonconformances

`test_malformed_duplicate_nonfinite_and_oversized_json_refuse` retains two strict
expected failures for the existing HTTP tool parser:

1. Duplicate top-level `arguments`: expected 400; observed 200.
2. Duplicate nested `work_ref`: expected 400; observed 200.

`test_coo_mcp_strict_json_requirement` retains three strict expected failures:

3. Duplicate root RPC `id`: expected 400; observed 200.
4. Duplicate nested `work_ref` on `executive_mandate`: expected 400; observed 200.
5. Nonfinite RPC `id: NaN`: expected 400; observed 202.

The HTTP owner uses ordinary `json.loads` in
[`_read_body_arguments`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/mastermind_executive_app/app.py).
The outer COO MCP path lacks the ruling path's strict duplicate/nonfinite decoding
boundary. In the nonfinite MCP case the SDK logs an invalid notification; HTTP 202
is not proof of a tool effect.

These are unmet requirements, not waived acceptance. Each is `xfail(strict=True,
raises=AssertionError)`: a future fix produces a strict XPASS until the receiving
owner removes the corresponding marker. A separate run with `--runxfail` exposes
the unmet assertions directly. The harness does not patch, normalize or intercept
invalid requests to manufacture a rejection.

The separate ruling boundary rejects duplicate keys, nonfinite values, truncated
JSON and oversized bodies before forwarding. Its behavior cannot be generalized to
the other routes.

## C29 / C32 / C34 receiving joins

| Owner and source commission | Gap specific to this pin | Required source join / falsifier |
| --- | --- | --- |
| [C29 — incumbent ingress / selected child](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6680534154) | No `mmx_delegate`, frozen selected-child command, private `target_digest` or `ExecutiveSelectedChildTarget` join exists here. HTTP/MCP parsing requirements above also remain unmet at the receiving boundary. | Compose the authorized owner implementation; require selected-child submit/status to retain the original command and target/context/capability digest. Refuse a wrong private digest before send. Preserve possible-send uncertainty without retry. Fix strict decoding in its owning paths; remove strict xfail markers only when those cases reject. |
| [C32 — Hermes OAuth principal](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6681329609) | Workspace supports two member records, but COO v1 supports one binding. Fixture signatures are not enrolled GB1/Secretary clients or Hermes profile qualification. | Qualify the planned bounded v2 binding container and per-principal Mission rows in one composed application. Repeat concurrent access and independent revocation with distinct verified clients and receipts; retain host selection and prohibit model principal selectors. |
| [C34 — exact COO resource path](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6681341295) | Current application settings force shared CEO/COO resource and metadata. Dedicated audience and public edge composition remain absent from this base. | Join exact POST `/mcp/coo` and GET `/.well-known/oauth-protected-resource/mcp/coo` separately from CEO `/mcp` and its metadata. The application resource/cache composition must accept the distinct policy; rerun audience and scope isolation. C34's planned 64,000-byte edge cap and the application's 65,536-byte cap need receiving proof. |

No new typed approval token, permission registry or OAuth provider is invented to
fill these gaps. Unsupported approval objects are rejected now; current bounded
authority and unanswered decision fences are separately tested. New approval or
target-digest contracts must be supplied by their accepted source owner.

C29, C32 and C34 are live disjoint commissions, not proof of an installed service.
This packet leaves their exclusive files untouched. The parent can consume the
three-file source change now; eventual source composition is a separate authorized
action and does not require reopening the accepted fixture-only work.

## Reproduction and test receipts

Execution directory:

```text
/home/ubuntu3/.mastermind/agent-workspaces/sol/h24-04-api-auth-20261106
```

The directory was acquired through the installed `mmx-workspace` launcher at the
exact base and branch. Tests used an already installed interpreter; no installation
was performed. Observed versions: Python 3.12.3, pytest 9.1.1, httpx 0.28.1,
PyJWT 2.14.0, MCP 1.28.1, Starlette 1.10.0, cryptography 41.0.7.

Focused command:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -ra -p no:cacheprovider \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py --tb=short
```

```text
72 passed, 5 xfailed in 9.04s
exit code 0
```

Incumbent regression command:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -p no:cacheprovider \
  tests/test_executive_coo_app.py tests/test_executive_coo_binding.py \
  tests/test_coo_principal_request.py --tb=short
```

```text
130 passed in 3.29s
exit code 0
```

Unmet-requirement diagnostic command, with expected-failure handling disabled:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -p no:cacheprovider \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  -k 'duplicate-root or duplicate-nested or nonfinite' --runxfail --tb=no
```

```text
5 failed, 6 passed, 66 deselected in 2.62s
exit code 1 (expected: demonstrates the five unmet requirements)
```

A successful focused-suite exit code includes known expected failures; it is not
a full conformance pass. The diagnostic deliberately exits 1 while the five
rejection requirements remain unmet.

No GitHub CI, release, deployment, external OAuth enrollment or production serving
receipt is asserted by these local test results.

## Parent checkpoint and next action

The containing source commit is the immutable implementation receipt. The parent
checkpoint reports its exact head and the SHA-256 of this owned diff:

```bash
git diff --binary --full-index \
  b54cb10e4abdd3766c62d4088f6a576ecfe80437 HEAD -- \
  integrations/hermes_qualification/api_conformance.py \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  docs/hermes/H24_AUTH_API_CONTRACT.md | sha256sum
```

The head and checksum are kept outside the hashed document to avoid self-reference.
Before source publication, verify that the commit's only parent is the immutable
base and that exactly these three added paths comprise the diff.

**Next action:** the currently assigned receiving integration owner can consume
this source checkpoint and use its explicit gaps when composing the authorized
C29/C32/C34 work. Re-run the affected assertions on that composed head. This is not
a self-merge, activation recommendation or authorization for an external effect.

**Do not redo:** accepted fixture identity, current Mission, continuity, original
request/reconciliation and source-fence coverage absent material source changes.
**Do not infer:** parent product completion, real enrollment, worker execution,
physical exactly-once delivery or production acceptance from this harness.
