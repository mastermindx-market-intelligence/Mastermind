# Project help and requester returns in one API enrollment

The explicit `coo.project_help_requester.v1` catalogue lets one currently
enrolled T3 or Paperclip API principal read its project's help and operate
an already admitted, host-selected child. It composes the existing help
reader and requester-return owner. It adds no admission, scheduler, task
store, identity registry, OAuth service or native-origin assertion.

## Exact source contract

The joint tools/list digest is
`f98abf1e3928b1c56d6e58aeeeb2eacba04db07e6d96f8e38aeb8d9f1b65b905`.
Every help descriptor is reused unchanged; only `mmx_delegate` uses the
existing requester-return descriptor that includes explicit
`acknowledge_result`. The per-operation help and return result schemas are
unchanged. The prior help, requester-return and native publication
catalogues retain their original descriptors and digests.

| API surface | New source profile | Exact capability grant |
| --- | --- | --- |
| `t3-api-principal` | `principal.t3-api.executive-coo.project-help-requester.v1` | `mastermind-executive-coo-t3-api-project-help-requester-v1` |
| `paperclip-api-principal` | `principal.paperclip-api.executive-coo.project-help-requester.v1` | `mastermind-executive-coo-paperclip-api-project-help-requester-v1` |

Both profiles are disabled in source. Existing profiles, grants and
`production_armed` defaults are preserved. A caller must be explicitly
enrolled with the matching enabled profile digest and catalogue; an
existing help or requester profile does not gain the joint contract.

The installed mission must use authority version 4 and explicitly include
both `read_project_help` and `acknowledge_selected_child_result`, alongside
its existing bounded-intent and governed-orchestration actions. Its closed
`project_help` scope retains one original Executive root and the adopted
source-plan tuple and contract digest. Root or source changes alter the
existing authority-generation digest; they cannot reuse the old captured
target or requester claim as current authority.

## Resource and owner boundaries

| Operation | Authenticated resources | Authority and result |
| --- | --- | --- |
| `executive_project_help({"work_ref": ...})` | Executive OAuth plus independently verified Workspace companion | Existing Mission, DATA, Plan, Session Bridge, Company and Capacity owners; read evidence only |
| `mmx_delegate` / `selected_child_submit` | Executive OAuth | Existing host-frozen command and admitted selected-child owner |
| `mmx_delegate` / `selected_child_status` | Executive OAuth | Canonical result for the original selected-child command |
| `mmx_delegate` / `acknowledge_result` | Executive OAuth | Deliberate acknowledgment of the exact reviewed requester-return descriptor |

Missing Workspace authentication refuses help. It neither removes the
principal's separately granted requester authority nor supplies Workspace
authority to delegation. A help read does not reserve capacity or grant
placement. Its `execution_authority` and `native_origin_attested` remain
false.

For joint profiles, the selected-child capture and Control operation
reprove that the installed help scope's work and original root match the
actual frozen target. The same work reference cannot authorize discovery
under Root A and execution or acknowledgment under Root B. Execution
continues to prove its current Mission, installed authority generation,
admitted plan, child, immediate coordinator and original root through the
existing owners. It does not borrow the help caller's Workspace bearer or
create an adoption watcher.

The public model arguments contain a work selector or an original command
and result descriptor. They cannot grant a root, role, worker, child,
principal or native identity. The retained requester family is
`coo_api_principal` for both API profiles.

## Use the actual execution avenue

A newly admitted project can already progress through the existing
durable or attended Executive service and `CooCycle` owner. That bootstrap
does not require a previously completed child, a consumed wake, or a
generic Mission `CURRENT` observation. This catalogue does not replace
that owner or run another project loop.

The manually selected-child avenue preserves its existing generic Mission
and currentness gates. A session should read the observed state and
determine whether the durable root already owns progression before trying
to operate a separately selected admitted child. A read-only
`CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH` help qualification does not
open those execution gates.

Once the original selected-child command completes, review its canonical
result and exact `requester_return` descriptor. Invoke `acknowledge_result`
only deliberately. Status and help never acknowledge automatically. A
changed descriptor or foreign principal cannot consume the result;
concurrent identical acknowledgments retain one canonical receipt. If a
response is lost, reconcile the original command through status. Do not
replace its command or reinterpret uncertainty as rollback.

Requester acknowledgment retains `parent_consumed=false` and
`acceptance=not_accepted`. Native-parent consumption, independent review,
product acceptance and any further admission remain separate owners.

## Ordinary sessions and credential custody

The API profiles are ordinary MCP contracts. A correctly enrolled T3
session can use its existing model-visible authenticated MCP connection.
An ordinary finite Paperclip Hermes session can use the existing Hermes
profile-local MCP configuration, OAuth token owner, discovery and tool
dispatch. Neither avenue requires a native context-prefetch consumer slot
or a claim that a particular T3 thread or Paperclip issue originated the
request.

Paperclip's run JWT is not Executive OAuth. Executive credentials must
come from the explicitly enrolled, profile-isolated OAuth owner. The
existing Paperclip finite-run and Operator Managed Harness custody remain
in force. The paired Workspace token needed by help must likewise be
supplied by its real credential owner; source catalogue availability does
not establish that it is installed or refreshed in a running session.

## Qualification

`tests/test_joint_api_contract.py` checks exact grants, surfaces, disabled
defaults, unchanged prior catalogues and the installed v4 mission rules.
`tests/test_joint_api_project_owner.py` uses actual local Git CREATE,
adoption, current-C AgentOS projection, canonical Runtime admission and
Mission/Plan owners. Its positive is a continuation fixture with a prior
consumed planner return and original navigation evidence. It does not
claim to prove fresh-project bootstrap or to repair current-DATA root
ambiguity. Its negatives cover foreign roots, changed source generation,
wrong parsed contract and revoked enrollment without fabricating a
`CURRENT` Mission.

`tests/test_joint_api_ingress.py` uses real signed resource tokens, the
installed catalogue/target factories, SDK `ClientSession` and the actual
App. Two read cases cover T3 and Paperclip API profiles with a genuinely
current project owner and the explicit in-process private READ boundary.
Its nine separate Unix cases use the original private client, Control
service, Runtime namespace custody, selected-child claim, canonical
completion and explicit acknowledgment. They require an execution host
with the existing Unix-socket test capability. Collection alone is not
service qualification. Physical provider and prior native receiver edges
remain explicitly inert disposable fixtures; no model is launched.

Replay the affected source proof with bytecode writes disabled, because
the actual source guard correctly treats unexpected generated files in a
disposable current-C source tree as a change:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q \
  tests/test_joint_api_contract.py \
  tests/test_t3_api_requester_contract.py \
  tests/test_joint_api_project_owner.py \
  tests/test_joint_api_ingress.py
```

Ordinary Hermes loader and OAuth isolation qualification uses the exact
native source and native MCP SDK separately; it does not vendor that
runtime into this repository. Runtime source installation, OAuth
enrollment, service activation and the original Paperclip credential
cutover are independent delivery steps. None is claimed by this source
contract or its disposable tests.
