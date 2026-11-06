# H24-04 — Authenticated API and original-effect conformance

## Outcome and scope

This packet supplies an executable, source-only qualification harness for the
incumbent Workspace, Executive MCP, COO and Secretary clients. It uses real
application entrypoints and independently signed, disposable fixture principals.
It does not implement an authentication runtime, endpoint, issuer or enrollment
owner.

**Harness outcome:** implemented and expanded; 94 focused cases execute with
89 passes and five strict expected failures for actual incumbent defects.
**Incumbent end-to-end conformance:** PARTIAL at both the immutable build base and
the protected-source qualification snapshot described below.
**Production capability:** BUILT_NOT_PROVEN; this report supplies no activation or
serving proof.

| Identity | Exact value |
| --- | --- |
| Packet | H24-04 |
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Source base | `b54cb10e4abdd3766c62d4088f6a576ecfe80437` |
| Source branch | `sol/h24-04-api-auth-20261106` |
| Protected procedure pin on resumption | `609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1` |
| Additional protected-source qualification | `609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1`, tree `344e2ec1d9d699983f1566fcd7fa4c149e42ba2d` |
| Initial publication | `90f11efe414fa50d6076889146eeaca90b3966e0`; [draft PR #2138](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2138) |
| Placement | Chairman's current concurrent authorization; no H24-01 or soft wave-seal dependency |
| Owned additions | `integrations/hermes_qualification/api_conformance.py`; `integrations/hermes_qualification/tests/test_h24_api_conformance.py`; this document |

The resumption adds 17 cases, repairs the actual stdlib CI discovery regression,
and extends the executable route matrix. The source branch retains the immutable
base; the protected-source run is an isolated source export with only the three
owned files overlaid, not a rebase or a change to protected source.

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
this limitation is explicitly retained as a C32 gap. Both separately bound COO
instances also share one real disposable Unix admission owner for concurrent
original-request collision and ownership tests. The fixture does not swap one
shared binding between concurrent requests to simulate multi-principal support.

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

The matrix is also exposed by `route_resource_matrix()` in the owned adapter;
the private Unix row below describes the existing downstream boundary.

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
C29's planned `mmx_delegate` MCP join is absent from this immutable base and the
protected-source qualification snapshot. Presence of other selected-child code
in the merged foundation does not establish this API join.

## Acceptance evidence

| Packet concern | Executed evidence | Result on both qualified source pins |
| --- | --- | --- |
| Distinct GB1 / Secretary identities | Different key, subject and client; real JWT verification; signature substitution rejected | PASS |
| Same authorized Mission | Concurrent outer ASGI → actual Unix service → Workspace reads; same work/root/results; each read has its own stable observation receipt | PASS |
| Independent revocation / wrong work | Revoke one member, leave the other working; foreign work/root and model-selected authority fields refused | PASS |
| Principal continuity | Rotate receipt, replace subject or disable membership during Workspace and COO reads | PASS; successful inner data withheld |
| Ambiguous bearer selection | Two Authorization headers, with identical or different valid tokens, on HTTP COO, MCP COO and ruling routes | PASS; 401 before disclosure or forwarding |
| Issuer, audience, scope and client enforcement | Wrong issuer/resource/subject/client, empty scopes, wrong scopes and expired token | PASS; refused before owner disclosure |
| Dedicated COO resource | Real verifier rejects wrong audience; real composition refuses distinct-resource policy | C34 integration requirement unmet |
| Multi-principal COO application | Each signed client works with its own v1 binding; foreign client denied; v2 container rejected by pinned owner | C32 integration requirement unmet |
| Bounded authority | Actual host guard rejects unknown authority, stale generation, rotated permission, disabled or historical Mission | PASS |
| Unknown approval / public selector | Unknown or stale-shaped `approval`, supplied principal/actor/root/generation or bogus `target_digest` refused before send | PASS for unsupported input; not a typed approval-receipt implementation |
| Stale decision approval context | Existing end-to-end source fence: current unanswered request positive; edited, answered, revoked authority, binding drift, invalid option or denied policy negative | PASS; no Relay post or COMMIT for these pre-COMMIT rejections |
| Policy revoked at COMMIT | Existing source-fence fixture changes policy after the COMMIT boundary | PASS; COMMIT_STARTED remains EFFECT_UNKNOWN; no Relay post, no false clean refusal |
| Current host target | Original current target reader refuses changed attempt, worker or root | PASS; this is tuple continuity, not C29's future target-digest join |
| Truncated / oversized JSON | Actual COO HTTP, COO MCP and ruling boundary | PASS, HTTP 400 / 413 respectively |
| Duplicate-key JSON | Valid retained values at root and nested depth, through HTTP tool and MCP boundaries | Four unmet rejection cases; see below |
| Nonfinite JSON | COO HTTP malformed argument and ruling RPC ID refused; COO MCP RPC ID `NaN` receives 202 | One additional unmet MCP rejection case |
| Original submit timeout | Lose the completed HTTP response after actual application/Unix admission; Secretary returns EFFECT_UNKNOWN | PASS; identical canonical `req-coo` |
| No second submit | Record actual HTTP invocations and actual Unix frames; explicit status-only reconciliation | PASS; one submit frame, one status frame, one disposable Job |
| Fresh versus original-status policy | Close fresh admission and remove the current Mission provider result after admission | PASS; authorized original status returns ADMISSION_ACCEPTED, `dispatched=false` |
| Original status authorization | No bearer, another principal, then revoked original binding | PASS; 401 / 403, no additional Job |
| Immutable request / changed payload | Same operation/work keeps the request reference; changed semantic payload conflicts | PASS |
| Concurrent original ownership | Two valid COO bindings share one real Unix owner; same or distinct operation keys | PASS; same key yields one accepted Job and one conflict; distinct keys yield two Jobs; exactly one initial submit per caller |
| Foreign original status | Another valid principal asks through its own authorized COO app, after fresh admission closes | PASS; owner returns operation_conflict without a Job receipt |
| Revocation immediately before send | Disable binding or rotate receipt after actual grounding returns | PASS; Secretary REFUSED with its original req-coo; zero Unix submit frames and zero Jobs |
| Revocation immediately after send | Disable binding or rotate receipt after actual submit completes, before receipt disclosure | PASS; Secretary EFFECT_UNKNOWN with the same req-coo; one submit and one Job; no accepted receipt disclosed |
| Original-context restoration | Restore only the exact original fixture binding, then read status with fresh admission closed | PASS; original receipt reconciles without resubmission; a rotated receipt cannot borrow it |
| Direct COO transport classification | Existing transport seam returns not_sent, lost response, exception or malformed receipt | PASS; the COO app refuses proven not_sent; possible-send remains uncertain |
| Secretary classification of HTTP 5xx | An inner not_sent becomes HTTP 503 at the app boundary | PASS; Secretary conservatively retains EFFECT_UNKNOWN and the original req-coo; no automatic retry |
| Separate ruling | Each signed fixture identity uses fixed host work/root/obligation; injected target fields refused | PASS for fixture forwarding; no real ruling or provider effect |

The original-submit fixture proves durable local admission and reconciliation, not
execution of a worker or a physically exactly-once remote action. Admission,
dispatch, completion and acceptance remain separate facts.

Canonical `req-coo` depends on work and the original operation key, not the caller's
principal. Concurrent callers with the same work/key therefore intentionally share
the request reference. Their distinct authenticated binding digests make the
second context conflict; the harness never invents a principal-specific replacement
request namespace. One initial send per caller is different from retrying an
uncertain original operation.

The direct app and Secretary observe different evidence. The app can know its Unix
transport returned `not_sent`; an HTTP consumer seeing a modifying 503 retains
uncertainty. A real post-grounding 403 with zero submit frames is the separately
proved pre-send refusal. Restoring an exact synthetic fixture binding is only a
reconciliation test, not a production permission-restoration procedure.

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
the other routes. The same five strict failures execute against protected source
`609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1`; merging the parent did not satisfy them.

## C29 / C32 / C34 source joins and explicit edit boundary

| Source commission | Gap still present at the qualified pins | Required source join / falsifier |
| --- | --- | --- |
| [C29 — incumbent ingress / selected child](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6680534154) | The six-tool COO MCP surface has no `mmx_delegate` join carrying a frozen selected-child command and private `target_digest`/`ExecutiveSelectedChildTarget` context. HTTP/MCP parsing requirements above also remain unmet at the receiving boundary. | Compose the authorized owner implementation; require selected-child submit/status to retain the original command and target/context/capability digest. Refuse a wrong private digest before send. Preserve possible-send uncertainty without retry. Fix strict decoding in its owning paths; remove strict xfail markers only when those cases reject. |
| [C32 — Hermes OAuth principal](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6681329609) | Workspace supports two member records, but COO v1 supports one binding. Fixture signatures are not enrolled GB1/Secretary clients or Hermes profile qualification. | Qualify the planned bounded v2 binding container and per-principal Mission rows in one composed application. Repeat concurrent access and independent revocation with distinct verified clients and receipts; retain host selection and prohibit model principal selectors. |
| [C34 — exact COO resource path](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6681341295) | Current application settings force shared CEO/COO resource and metadata. Dedicated audience and public edge composition remain absent from this base. | Join exact POST `/mcp/coo` and GET `/.well-known/oauth-protected-resource/mcp/coo` separately from CEO `/mcp` and its metadata. The application resource/cache composition must accept the distinct policy; rerun audience and scope isolation. C34's planned 64,000-byte edge cap and the application's 65,536-byte cap need receiving proof. |

No new typed approval token, permission registry or OAuth provider is invented to
fill these gaps. Unsupported approval objects are rejected now; current bounded
authority and unanswered decision fences are separately tested. New approval or
target-digest contracts must be supplied by their accepted source owner.

These commission links establish the packet's planned joins; they do not establish
current worker activity, installation or serving proof. The qualified source shows
the joins above remain absent. This packet leaves their explicitly excluded files
untouched and does not wait for an old author or an unobserved worker.

The smallest runtime repair for the five JSON requirements has two existing
entrypoints:

1. `_read_body_arguments` in
   [`integrations/mastermind_executive_app/app.py`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1/integrations/mastermind_executive_app/app.py)
   must reject duplicate object names at every depth and nonfinite numbers before
   returning arguments.
2. The literal COO MCP receive boundary in
   [`integrations/executive_mcp/server.py`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1/integrations/executive_mcp/server.py)
   must validate bounded original bytes before the SDK normalizes the RPC object;
   checking the decoded tool arguments is too late to detect duplicate names.

The repair must preserve byte bounds, authentication and literal-path checks,
original bytes, and application lifespan behavior. At this pin,
[`PreAuthMcpBodyApp`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1/integrations/executive_mcp/e1_http.py)
matches only POST `/mcp`; it does not supply its receive deadline/empty-body guard
to `/mcp/coo`. Do not assume that wrapper already bounds a new COO pre-parser's
receive lifetime. The authenticated COO `BoundedRequestApp` still supplies the
65,536-byte limit tested here. This deadline observation is source inspection,
not a new slow-request test receipt.

Existing ruling strict parsing is a source precedent, not a handler copied into
the H24 fixture. A Unix JSON-frame decoder requiring one trailing newline is not
an HTTP JSON decoder.

The original H24-04 packet explicitly permits only the three owned additions and
forbids edits to those runtime owners. Finishing those owner changes therefore
requires an explicit expansion of that edit scope. The strict failing assertions
already make the proposed correction concrete and reviewable. The C32 binding,
C34 resource composition and C29 selected-child API join are additional, separate
source changes; none can be established by altering fixture claims or masking the
failures.

## Reproduction and test receipts

### Recovered immutable-base branch

Execution directory:

```text
/home/ubuntu3/.mastermind/agent-workspaces/sol/h24-04-api-auth-20261106
```

The initial worktree was acquired through the installed `mmx-workspace` launcher
at the exact assigned base and branch. On resumption, the clean published branch
was reacquired at `90f11efe414fa50d6076889146eeaca90b3966e0`; its original parent
remains `b54cb10e4abdd3766c62d4088f6a576ecfe80437`. Tests used an already installed
interpreter; no installation was performed. Observed versions: Python 3.12.3,
pytest 9.1.1, httpx 0.28.1, PyJWT 2.14.0, MCP 1.28.1, Starlette 1.10.0,
cryptography 41.0.7.

Resumed focused command, run from that directory:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -ra -p no:cacheprovider \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py --tb=short
```

```text
89 passed, 5 xfailed in 9.99s
exit code 0
```

Local receipt: `/tmp/h24-04-resume-pytest.txt`. This is 17 additional executed cases
over the initial publication's 72 passes and five expected failures.

### Stdlib CI discovery repair

The existing offline Hermes workflow uses stdlib `unittest` and installs only its
lightweight dependency profile. Its initial run at the published H24 head failed
during discovery because this pytest module imported `httpx` first:
[Python 3.12 job](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208816917/job/127862090054),
[Python 3.13 job](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208816917/job/127862089691).

The module now emits one explicit `unittest.SkipTest` before third-party imports
when pytest is not the runner. Stdlib cannot execute its pytest-style functions.
This does not turn missing integration dependencies into a conformance pass:
under pytest, the actual imports are unconditional and missing dependencies still
fail collection. A new regression test runs discovery in a subprocess with
site-packages disabled.

Commands run from the recovered branch:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m unittest discover -v \
  -s integrations/hermes_qualification/tests -p 'test_*.py'
```

```text
Ran 49 tests in 0.563s
OK (skipped=1)
exit code 0
```

```bash
/usr/bin/python3 -S -m unittest discover -v \
  -s integrations/hermes_qualification/tests -p test_h24_api_conformance.py
```

```text
Ran 1 test
OK (skipped=1)
exit code 0
```

The explicit skip qualifies compatibility with the lightweight discovery profile.
The 94-case pytest run above supplies the API qualification.

### Protected-source qualification without changing branch ancestry

Parent [PR #2120](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120)
merged as `28a894186eb56654ab4e833eb11a183d2eed46ae`. Its source branch was deleted
and GitHub retargeted draft #2138 to `master`. The initial retargeted PR view shows
88 changed files because the frozen branch carries the former foundation's
ancestry. That PR-wide comparison is not the three-file owned diff to the assigned
base. No rebase, parent merge, integration-branch recreation or unrelated repair
was performed to disguise this distinction.

To check the merged foundation while preserving the user-frozen branch, export
the exact protected source and overlay only the three owned files:

```bash
python3 - <<'PY'
import pathlib
import shutil
import subprocess
import tarfile
import tempfile

source = "609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1"
owned = (
    "integrations/hermes_qualification/api_conformance.py",
    "integrations/hermes_qualification/tests/test_h24_api_conformance.py",
    "docs/hermes/H24_AUTH_API_CONTRACT.md",
)
destination = pathlib.Path(tempfile.mkdtemp(prefix="h24-04-qualification-"))
with tempfile.TemporaryFile() as archive:
    subprocess.run(["git", "archive", source], stdout=archive, check=True)
    archive.seek(0)
    with tarfile.open(fileobj=archive, mode="r:") as files:
        files.extractall(destination, filter="data")
for name in owned:
    target = destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(name, target)
print(destination)
PY
```

This requires the exact source object already fetched. The observed disposable
export was `/tmp/h24-04-qualification-201ap349`; its source tree was
`344e2ec1d9d699983f1566fcd7fa4c149e42ba2d`. No other source files were changed.
Executable overlay SHA-256 values at test time:

| Owned executable | SHA-256 |
| --- | --- |
| `api_conformance.py` | `1be31d3af2305f82682bcb1b64d35c7383a553372ae5f8a1287f95b74e22b38f` |
| `test_h24_api_conformance.py` | `b2820f129bc795fc3c14ed797b13f4750807a91506d017ff1a867032378fa45e` |

Run the combined API and actual COO owner regressions from the exported directory:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -ra -p no:cacheprovider \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  tests/test_executive_coo_app.py \
  tests/test_executive_coo_binding.py \
  tests/test_coo_principal_request.py --tb=short
```

```text
219 passed, 5 xfailed in 15.09s
exit code 0
```

Local receipt: `/tmp/h24-04-resume-current-source.txt`.

The initial PR's broader checks also failed in inherited foundation files:
[shard 4](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208816900/job/127865424656)
and [shard 5](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208816900/job/127865424593).
Those root-test shards do not collect this H24 module. The current protected
snapshot contains the repaired source; no such repairs were copied into H24's
branch. Run the exact former failing tests and the affected original-operation
module from the same export:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -p no:cacheprovider \
  tests/test_ceo_submit_armed_composition.py::test_d7_exact_event_loop_only_and_foreign_scope_refused \
  tests/test_executive_mcp_web_ceo_v3.py::test_v3_is_additive_and_prior_snapshot_hashes_remain_frozen \
  tests/test_hermes_secretary_forwarder.py::test_gateway_witness_comes_from_own_exclusive_listening_socket \
  tests/test_session_bridge_original_operation_read.py --tb=short
```

```text
105 passed in 24.47s
exit code 0
```

Local receipt: `/tmp/h24-04-resume-foundation-regressions.txt`. These are targeted
regressions on a pinned source export, not a claim that all current GitHub CI
checks, the complete repository suite or a rebased H24 PR are green.

### Initial publication receipts

The initial `90f11efe414fa50d6076889146eeaca90b3966e0` publication recorded:

| Historical run | Exact result |
| --- | --- |
| Focused command above before 17 added cases | 72 passed, 5 xfailed in 9.04s; exit 0 |
| Three COO owner test modules above on the immutable base | 130 passed in 3.29s; exit 0 |
| Diagnostic below, with strict expected-failure handling disabled | 5 failed, 6 passed, 66 deselected in 2.62s; exit 1 |

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/venv-mmx/bin/python -m pytest \
  -o addopts='' -q -p no:cacheprovider \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  -k 'duplicate-root or duplicate-nested or nonfinite' --runxfail --tb=no
```

The deselected count above belongs to the initial version. The resumed focused
and protected-source runs re-execute all five strict failing assertions. A
successful focused-suite exit code includes these known failures; it is not a
full conformance pass. The diagnostic deliberately exits 1 while the five
rejection requirements remain unmet.

## Parent checkpoint and next authorized change

The containing source commit is the implementation receipt. The parent checkpoint
reports its exact head and the SHA-256 of the cumulative owned diff:

```bash
git diff --binary --full-index \
  b54cb10e4abdd3766c62d4088f6a576ecfe80437 HEAD -- \
  integrations/hermes_qualification/api_conformance.py \
  integrations/hermes_qualification/tests/test_h24_api_conformance.py \
  docs/hermes/H24_AUTH_API_CONTRACT.md | sha256sum
```

The head and checksum remain outside the hashed document to avoid self-reference.
The initial implementation's sole parent is the immutable base. Continuation
commits descend from that implementation; verify the base remains an ancestor
and that the cumulative diff to it comprises exactly the three added paths.
Do not confuse that invariant with the auto-retargeted PR's broader ancestry.

The published draft and exact owned diff are the durable source checkpoint. A
complete runtime conformance change needs explicit permission to edit the
currently forbidden existing HTTP/MCP owners. A reviewable three-file PR on the
merged foundation also needs permission to move this branch off the originally
frozen base. These are concrete source-scope decisions from the user's packet,
not a review-seal prerequisite or a wait for an old owner. No merge or activation
is implied by either possible scope expansion.

**Do not redo:** accepted fixture identity, current Mission, continuity, original
request/reconciliation and source-fence coverage absent material source changes.
**Do not infer:** parent product completion, real enrollment, worker execution,
physical exactly-once delivery or production acceptance from this harness.
